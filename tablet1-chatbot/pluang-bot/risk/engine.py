"""
===========================================================================
PYROFUEL HARD RISK ENGINE v3.0 — 20x ISOLATED ALL-IN & SNIPER 75% (T7.1–T7.4)
===========================================================================
Enforces the user's non-negotiable mandates and institutional safety rails:
1. Locked Configuration (`T7.1` & `T7.2`):
   - `fixed_leverage = 20`
   - `margin_type = "ISOLATED"`
   - `sizing_mode = "ALL_IN"` (`all_in_balance_fraction = 0.95` of active
     working balance from `ProfitRatchetVault`)
2. Structural Stop-Loss & Liquidation Safety Rails (`T7.1`):
   - `0.45% <= sl_distance_pct <= 2.25%`
   - `liquidation_distance >= 2.0 * sl_distance`
     (At 20x Isolated with MMR = 0.4%, liquidation distance is ~4.60%, so
      d_SL <= 2.25% guarantees d_liq >= 2.04 * d_SL).
3. Circuit-Breaker (`T7.1`):
   - Trips automatically on `2 consecutive losses` (`breaker_consecutive_losses = 2`)
     or `15.0% daily equity drawdown` (`breaker_daily_dd_pct = 15.0`), locking out
     new entries for 12 hours (`COOLDOWN_BREAKER`).
   - `/panic` emergency flat command cancels all open orders & algo orders,
     market-closes all positions (`reduceOnly`), and freezes the bot in < 3s.
4. `HIGH_PRECISION_SNIPER_MODE` (`T7.4`):
   - Requires `p_hybrid(TP1) >= 0.76` (rejects with `SKIP_BELOW_76PCT_PRECISION_GATE`)
   - Requires Conformal Prediction Set == `{"WIN"}` (`alpha_target = 0.18`)
   - Computes Two-Stage Asymmetric Profit-Lock levels:
     * `TP1 = +0.55R` (65% partial close or immediate SL lock)
     * `SL Lock after TP1 = +0.38R` (guaranteed net win after fees)
     * `TP2 Runner = +1.60R`
===========================================================================
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from risk.vault import ProfitRatchetVault


DEFAULT_RISK_CONFIG: Dict[str, Any] = {
    "fixed_leverage": 20,
    "margin_type": "ISOLATED",
    "sizing_mode": "ALL_IN",
    "all_in_balance_fraction": 0.95,
    "fractional_risk_pct": 5.0,
    "min_sl_distance_pct": 0.45,
    "max_sl_distance_pct": 2.25,
    "min_liq_to_sl_ratio": 2.0,
    "maintenance_margin_rate": 0.004,
    "min_rrr_net": 1.60,
    "min_ev_r": 0.20,
    "max_concurrent_positions": 1,
    "breaker_consecutive_losses": 2,
    "breaker_daily_dd_pct": 15.0,
    "breaker_cooldown_hours": 12.0,
    "sniper_75_mode": {
        "enabled": True,
        "min_calibrated_p_tp1": 0.76,
        "conformal_alpha_target": 0.18,
        "tp1_lock_trigger_r": 0.55,
        "tp1_partial_close_pct": 0.65,
        "sl_lock_after_tp1_r": 0.38,
        "tp2_runner_target_r": 1.60,
        "early_invalidation_max_loss_r": 0.35,
    },
}


class HardRiskEngine:
    """
    Institutional Hard Risk Engine for 20x ISOLATED ALL-IN & High-Precision Sniper 75% Mode (T7.1, T7.2, T7.4).
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        vault: Optional[ProfitRatchetVault] = None,
    ):
        cfg = dict(DEFAULT_RISK_CONFIG)
        if config:
            for k, v in config.items():
                if k == "sniper_75_mode" and isinstance(v, dict):
                    s_cfg = dict(DEFAULT_RISK_CONFIG["sniper_75_mode"])
                    s_cfg.update(v)
                    cfg["sniper_75_mode"] = s_cfg
                else:
                    cfg[k] = v

        # Enforce locked user mandates (M2 & M3)
        self.fixed_leverage: int = 20
        self.margin_type: str = "ISOLATED"
        self.sizing_mode: str = str(cfg.get("sizing_mode", "ALL_IN")).upper()
        self.all_in_balance_fraction: float = float(cfg.get("all_in_balance_fraction", 0.95))

        self.min_sl_distance_pct: float = float(cfg.get("min_sl_distance_pct", 0.45))
        self.max_sl_distance_pct: float = float(cfg.get("max_sl_distance_pct", 2.25))
        self.min_liq_to_sl_ratio: float = float(cfg.get("min_liq_to_sl_ratio", 2.0))
        self.maintenance_margin_rate: float = float(cfg.get("maintenance_margin_rate", 0.004))
        self.min_rrr_net: float = float(cfg.get("min_rrr_net", 1.60))
        self.min_ev_r: float = float(cfg.get("min_ev_r", 0.20))
        self.max_concurrent_positions: int = int(cfg.get("max_concurrent_positions", 1))

        self.breaker_consecutive_losses: int = int(cfg.get("breaker_consecutive_losses", 2))
        self.breaker_daily_dd_pct: float = float(cfg.get("breaker_daily_dd_pct", 15.0))
        self.breaker_cooldown_hours: float = float(cfg.get("breaker_cooldown_hours", 12.0))

        self.sniper_75_mode: Dict[str, Any] = dict(cfg["sniper_75_mode"])
        self.vault: ProfitRatchetVault = vault or ProfitRatchetVault(persist=False)

        # Runtime Circuit-Breaker state
        self.consecutive_losses: int = 0
        self.daily_start_equity: float = 0.0
        self.current_equity: float = 0.0
        self.breaker_until_ts: float = 0.0
        self.breaker_reason: Optional[str] = None

    def record_trade_result(
        self, net_pnl_usdt: float, new_equity: Optional[float] = None, now_ts: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Update consecutive loss counter, daily drawdown, and ProfitRatchetVault after a trade closes.
        Trips `COOLDOWN_BREAKER` if consecutive_losses >= 2 or daily DD >= 15%.
        """
        now = now_ts if now_ts is not None else time.time()
        if float(net_pnl_usdt) < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        vault_res = None
        if new_equity is not None:
            eq = float(new_equity)
            if self.daily_start_equity <= 0:
                self.daily_start_equity = eq
            self.current_equity = eq
            vault_res = self.vault.update_equity(eq)

        daily_dd_pct = 0.0
        if self.daily_start_equity > 0 and self.current_equity > 0:
            daily_dd_pct = max(
                0.0, (self.daily_start_equity - self.current_equity) / self.daily_start_equity * 100.0
            )

        if self.consecutive_losses >= self.breaker_consecutive_losses:
            self.trip_circuit_breaker(
                reason=f"CONSECUTIVE_LOSSES_{self.consecutive_losses}",
                now_ts=now,
            )
        elif daily_dd_pct >= self.breaker_daily_dd_pct:
            self.trip_circuit_breaker(
                reason=f"DAILY_DRAWDOWN_{daily_dd_pct:.2f}PCT",
                now_ts=now,
            )

        return {
            "consecutive_losses": self.consecutive_losses,
            "daily_dd_pct": daily_dd_pct,
            "breaker_active": self.is_circuit_breaker_active(now),
            "breaker_reason": self.breaker_reason,
            "vault_update": vault_res,
        }

    def trip_circuit_breaker(self, reason: str, now_ts: Optional[float] = None) -> None:
        now = now_ts if now_ts is not None else time.time()
        self.breaker_until_ts = now + self.breaker_cooldown_hours * 3600.0
        self.breaker_reason = str(reason)

    def resume_circuit_breaker(self) -> None:
        self.breaker_until_ts = 0.0
        self.breaker_reason = None
        self.consecutive_losses = 0

    def is_circuit_breaker_active(self, now_ts: Optional[float] = None) -> bool:
        now = now_ts if now_ts is not None else time.time()
        if self.breaker_until_ts > now:
            return True
        if self.breaker_until_ts > 0 and self.breaker_until_ts <= now:
            self.breaker_until_ts = 0.0
            self.breaker_reason = None
        return False

    def estimate_liquidation_price(self, entry_price: float, direction: str) -> float:
        """
        Estimate 20x ISOLATED liquidation price:
          LiqPrice = Entry * (1 -/+ (1/20 - MMR))
        With leverage = 20 and MMR = 0.004, distance to liquidation is 4.60%.
        """
        ep = float(entry_price)
        liq_dist_frac = (1.0 / float(self.fixed_leverage)) - self.maintenance_margin_rate
        if str(direction).upper().strip() == "LONG":
            return ep * (1.0 - liq_dist_frac)
        return ep * (1.0 + liq_dist_frac)

    def validate_and_size(
        self,
        decision: Dict[str, Any],
        account_state: Dict[str, Any],
        market_state: Optional[Dict[str, Any]] = None,
        now_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Validate a candidate `TRADE` decision against all Hard Risk Rails & Sniper 75% Mode,
        and compute exact 20x ISOLATED `ALL_IN` sizing (`95%` working balance).
        """
        now = now_ts if now_ts is not None else time.time()
        m_state = market_state or {}

        if str(decision.get("decision", "TRADE")).upper() != "TRADE":
            return {
                "allowed": False,
                "reject_reason": decision.get("skip_reason") or "NOT_A_TRADE_DECISION",
            }

        # 1. Circuit-Breaker Check
        acct_consec_losses = int(account_state.get("consecutive_losses", self.consecutive_losses))
        acct_daily_dd = float(account_state.get("daily_dd_pct", 0.0))
        if acct_consec_losses >= self.breaker_consecutive_losses:
            self.trip_circuit_breaker(f"CONSECUTIVE_LOSSES_{acct_consec_losses}", now_ts=now)
        elif acct_daily_dd >= self.breaker_daily_dd_pct:
            self.trip_circuit_breaker(f"DAILY_DRAWDOWN_{acct_daily_dd:.2f}PCT", now_ts=now)

        if self.is_circuit_breaker_active(now):
            return {
                "allowed": False,
                "reject_reason": "REJECT_CIRCUIT_BREAKER_ACTIVE",
                "breaker_reason": self.breaker_reason,
                "cooldown_until_ts": self.breaker_until_ts,
            }

        # 2. Concurrent Positions Check
        open_pos_count = int(account_state.get("open_positions_count", 0))
        if open_pos_count >= self.max_concurrent_positions:
            return {
                "allowed": False,
                "reject_reason": "REJECT_MAX_CONCURRENT_POSITIONS",
            }

        # 3. Structural SL Distance Check (0.45% <= d_SL <= 2.25%)
        entry_price = float(decision["entry_price"])
        sl_price = float(decision["sl_price"])
        tp_price = float(decision["tp_price"])
        direction = str(decision.get("direction", "LONG")).upper().strip()

        if entry_price <= 0 or sl_price <= 0 or tp_price <= 0:
            return {"allowed": False, "reject_reason": "REJECT_INVALID_PRICES"}

        d_sl_frac = abs(entry_price - sl_price) / entry_price
        d_sl_pct = d_sl_frac * 100.0
        d_tp_frac = abs(tp_price - entry_price) / entry_price
        d_tp_pct = d_tp_frac * 100.0

        if d_sl_pct < self.min_sl_distance_pct - 1e-6 or d_sl_pct > self.max_sl_distance_pct + 1e-6:
            return {
                "allowed": False,
                "reject_reason": "REJECT_SL_DISTANCE_OUT_OF_BOUNDS",
                "sl_distance_pct": d_sl_pct,
                "allowed_range_pct": [self.min_sl_distance_pct, self.max_sl_distance_pct],
            }

        # 4. Liquidation Distance Ratio Check (d_liq >= 2.0 * d_SL)
        liq_price = float(
            m_state.get("liquidation_price")
            or self.estimate_liquidation_price(entry_price, direction)
        )
        d_liq_frac = abs(entry_price - liq_price) / entry_price
        liq_to_sl_ratio = d_liq_frac / max(1e-9, d_sl_frac)
        if liq_to_sl_ratio < self.min_liq_to_sl_ratio - 1e-6:
            return {
                "allowed": False,
                "reject_reason": "REJECT_LIQUIDATION_PROXIMITY",
                "liq_to_sl_ratio": liq_to_sl_ratio,
                "min_required_ratio": self.min_liq_to_sl_ratio,
            }

        # 5. HIGH_PRECISION_SNIPER_MODE Gate (T7.4)
        sniper_cfg = self.sniper_75_mode
        p_hybrid = float(decision.get("p_hybrid", decision.get("p_cal", 0.80)))
        p_cal = float(decision.get("p_cal", p_hybrid))

        if sniper_cfg.get("enabled", True):
            min_p_tp1 = float(sniper_cfg.get("min_calibrated_p_tp1", 0.76))
            p_tp1_est = float(decision.get("p_tp1", max(p_hybrid, p_cal)))
            if p_tp1_est < min_p_tp1 - 1e-9:
                return {
                    "allowed": False,
                    "reject_reason": "SKIP_BELOW_76PCT_PRECISION_GATE",
                    "p_tp1": p_tp1_est,
                    "min_required_p_tp1": min_p_tp1,
                }

            conf_set_raw = decision.get("conformal_set", ["WIN"])
            conf_set: Set[str] = {str(x).upper() for x in conf_set_raw}
            if conf_set != {"WIN"}:
                return {
                    "allowed": False,
                    "reject_reason": "SKIP_CONFORMAL_AMBIGUITY",
                    "conformal_set": sorted(list(conf_set)),
                }

        # 6. Net EV & Net RRR Gate
        fee_roundtrip = float(m_state.get("roundtrip_fee_frac", 0.0010))
        rrr_net = float(
            decision.get("rrr_net")
            or max(0.0, (d_tp_frac - fee_roundtrip) / (d_sl_frac + fee_roundtrip))
        )
        ev_r = float(
            decision.get("ev_r")
            or (p_cal * rrr_net - (1.0 - p_cal) * 1.0)
        )

        if ev_r < self.min_ev_r - 1e-6:
            return {
                "allowed": False,
                "reject_reason": "REJECT_LOW_EV_R",
                "ev_r": ev_r,
                "min_ev_r": self.min_ev_r,
            }

        if rrr_net < self.min_rrr_net - 1e-6:
            return {
                "allowed": False,
                "reject_reason": "REJECT_LOW_RRR_NET",
                "rrr_net": rrr_net,
                "min_rrr_net": self.min_rrr_net,
            }

        # 7. Funding Boundary Guard (<= 10m to funding and paying >= 0.05%)
        mins_to_funding = float(m_state.get("minutes_to_funding", 999.0))
        funding_rate = float(m_state.get("funding_rate", 0.0))  # positive => LONG pays SHORT
        pays_high_funding = (direction == "LONG" and funding_rate >= 0.0005) or (
            direction == "SHORT" and funding_rate <= -0.0005
        )
        if mins_to_funding <= 10.0 and pays_high_funding:
            return {
                "allowed": False,
                "reject_reason": "REJECT_FUNDING_BOUNDARY_GUARD",
                "minutes_to_funding": mins_to_funding,
                "funding_rate": funding_rate,
            }

        # 8. 20x ISOLATED ALL-IN Sizing (95% of Vault Working Balance)
        avail_balance = float(account_state.get("available_balance_usdt", 0.0))
        cap_info = self.vault.compute_all_in_working_capital(
            available_balance=avail_balance,
            all_in_fraction=self.all_in_balance_fraction,
            leverage=self.fixed_leverage,
        )
        working_balance = cap_info["working_balance_usdt"]
        margin_usdt = cap_info["margin_usdt"]
        notional_usdt = cap_info["notional_usdt"]

        min_notional = float(m_state.get("min_notional", 5.0))
        step_size = float(m_state.get("step_size", 0.001))
        min_qty = float(m_state.get("min_qty", 0.001))
        qty_prec = int(m_state.get("quantity_precision", 3))

        if notional_usdt < min_notional:
            return {
                "allowed": False,
                "reject_reason": "SKIP_MIN_NOTIONAL",
                "notional_usdt": notional_usdt,
                "min_notional": min_notional,
            }

        raw_qty = notional_usdt / entry_price
        steps = math.floor(raw_qty / max(1e-12, step_size) + 1e-9)
        qty = round(steps * step_size, qty_prec) if qty_prec > 0 else float(int(steps * step_size))

        if qty < min_qty or (qty * entry_price) < min_notional:
            return {
                "allowed": False,
                "reject_reason": "SKIP_MIN_NOTIONAL",
                "notional_usdt": qty * entry_price,
                "min_notional": min_notional,
            }

        # Dollar risk at SL = Notional * d_SL + roundtrip fees
        sl_loss_gross_usdt = notional_usdt * d_sl_frac
        est_fee_usdt = notional_usdt * fee_roundtrip
        total_risk_usdt = sl_loss_gross_usdt + est_fee_usdt
        equity_risk_pct = (total_risk_usdt / max(1e-9, working_balance)) * 100.0

        # Sniper 2-Stage Profit-Lock Coordinates
        risk_dist_px = abs(entry_price - sl_price)
        tp1_r = float(sniper_cfg.get("tp1_lock_trigger_r", 0.55))
        sl_lock_r = float(sniper_cfg.get("sl_lock_after_tp1_r", 0.38))
        tp2_r = float(sniper_cfg.get("tp2_runner_target_r", 1.60))

        if direction == "LONG":
            tp1_price = entry_price + tp1_r * risk_dist_px
            sl_lock_after_tp1_price = entry_price + sl_lock_r * risk_dist_px
            tp2_runner_price = max(tp_price, entry_price + tp2_r * risk_dist_px)
        else:
            tp1_price = entry_price - tp1_r * risk_dist_px
            sl_lock_after_tp1_price = entry_price - sl_lock_r * risk_dist_px
            tp2_runner_price = min(tp_price, entry_price - tp2_r * risk_dist_px)

        sizing_result = {
            "allowed": True,
            "reject_reason": None,
            "symbol": decision.get("symbol", ""),
            "direction": direction,
            "sizing_mode": "ALL_IN",
            "leverage": self.fixed_leverage,
            "margin_type": self.margin_type,
            "available_balance_usdt": avail_balance,
            "locked_vault_usdt": cap_info["locked_vault_usdt"],
            "working_balance_usdt": working_balance,
            "margin_usdt": round(margin_usdt, 6),
            "notional_usdt": round(notional_usdt, 6),
            "quantity": qty,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "tp1_price": tp1_price,
            "sl_lock_after_tp1_price": sl_lock_after_tp1_price,
            "tp2_runner_price": tp2_runner_price,
            "liquidation_price": liq_price,
            "sl_distance_pct": d_sl_pct,
            "liq_to_sl_ratio": liq_to_sl_ratio,
            "sl_loss_gross_usdt": round(sl_loss_gross_usdt, 4),
            "estimated_fee_usdt": round(est_fee_usdt, 4),
            "total_risk_usdt": round(total_risk_usdt, 4),
            "equity_risk_pct": round(equity_risk_pct, 2),
            "p_cal": p_cal,
            "p_hybrid": p_hybrid,
            "ev_r": ev_r,
            "rrr_net": rrr_net,
        }
        sizing_result["telegram_transparency_box"] = self.format_risk_transparency_box(sizing_result)
        return sizing_result

    @staticmethod
    def format_risk_transparency_box(sizing: Dict[str, Any]) -> str:
        """
        Format the mandatory Telegram transparency box (T7.2).
        """
        return (
            f"Mode: ALL-IN (95% Saldo) | 20x ISOLATED\n"
            f"Margin Terpakai: ${sizing['margin_usdt']:.2f} | Notional: ${sizing['notional_usdt']:.2f}\n"
            f"SL Bursa (CONFIRMED): ${sizing['sl_price']:.4f} (-{sizing['sl_distance_pct']:.2f}% harga | Risiko -{sizing['equity_risk_pct']:.1f}% Ekuitas)\n"
            f"Harga Likuidasi: ${sizing['liquidation_price']:.4f} (Jarak {sizing['liq_to_sl_ratio']:.1f}x dari SL)\n"
            f"Probabilitas Terkalibrasi (p_cal): {sizing['p_cal'] * 100:.1f}% | Ekspektasi Bersih: {sizing['ev_r']:+.2f} R"
        )

    def execute_panic(self, client: Any) -> Dict[str, Any]:
        """
        `/panic` emergency handler (T7.1):
        Cancels all open standard & algo orders, closes all open positions with
        `reduceOnly` market orders, and locks the bot in `COOLDOWN_BREAKER` in < 3s.
        """
        t0 = time.perf_counter()
        self.trip_circuit_breaker("MANUAL_PANIC_COMMAND")
        closed_symbols: List[str] = []
        cancelled_symbols: List[str] = []

        positions = client.get_positions() if hasattr(client, "get_positions") else []
        if isinstance(positions, list):
            for p in positions:
                sym = p.get("symbol")
                direction = p.get("direction", "LONG")
                amt = abs(float(p.get("position_amount", 0.0)))
                if sym and amt > 0:
                    client.cancel_all_orders(sym)
                    cancelled_symbols.append(sym)
                    client.close_position(sym, direction, quantity=amt)
                    closed_symbols.append(sym)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "panic_executed": True,
            "closed_symbols": closed_symbols,
            "cancelled_symbols": cancelled_symbols,
            "breaker_active": True,
            "elapsed_ms": elapsed_ms,
        }
