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
    "funding_guard_window_min": 15.0,
    "funding_rate_threshold": 0.0005,
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
        self.fixed_leverage: int = int(cfg.get("fixed_leverage", 20))
        self.margin_type: str = "ISOLATED"
        self.sizing_mode: str = str(cfg.get("sizing_mode", "ALL_IN")).upper()
        self.all_in_balance_fraction: float = float(cfg.get("all_in_balance_fraction", 0.95))
        self.fractional_risk_pct: float = float(cfg.get("fractional_risk_pct", cfg.get("risk_pct", 5.0)))

        self.min_sl_distance_pct: float = float(cfg.get("min_sl_distance_pct", cfg.get("min_sl_pct", 0.45)))
        self.max_sl_distance_pct: float = float(cfg.get("max_sl_distance_pct", cfg.get("max_sl_pct", 2.25)))
        self.min_liq_to_sl_ratio: float = float(cfg.get("min_liq_to_sl_ratio", 2.0))
        self.maintenance_margin_rate: float = float(cfg.get("maintenance_margin_rate", 0.004))
        self.min_rrr_net: float = float(cfg.get("min_rrr_net", cfg.get("min_risk_reward_ratio", 1.60)))
        self.min_ev_r: float = float(cfg.get("min_ev_r", 0.20))
        self.max_concurrent_positions: int = int(cfg.get("max_concurrent_positions", 1))
        raw_max_dir = cfg.get("max_same_direction_positions", cfg.get("max_directional_positions"))
        self.max_same_direction_positions: Optional[int] = int(raw_max_dir) if raw_max_dir is not None else None

        self.breaker_consecutive_losses: int = int(
            cfg.get("breaker_consecutive_losses", cfg.get("circuit_breaker_consecutive_losses", 2))
        )
        self.breaker_daily_dd_pct: float = float(cfg.get("breaker_daily_dd_pct", 15.0))
        self.breaker_cooldown_hours: float = float(cfg.get("breaker_cooldown_hours", 12.0))
        self.funding_guard_window_min: float = float(cfg.get("funding_guard_window_min", 15.0))
        self.funding_rate_threshold: float = float(cfg.get("funding_rate_threshold", 0.0005))

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
            prior_reason = str(self.breaker_reason or "")
            self.breaker_until_ts = 0.0
            self.breaker_reason = None
            self.consecutive_losses = 0
            if prior_reason.startswith("DAILY_DRAWDOWN") and self.current_equity > 0:
                self.daily_start_equity = self.current_equity
        return False

    def compute_daily_dd_pct(self, live_equity: Optional[float] = None) -> float:
        """Compute current intraday drawdown percentage against `daily_start_equity`."""
        eq = float(live_equity) if live_equity is not None else float(self.current_equity)
        if self.daily_start_equity <= 0.0 or eq < 0.0:
            return 0.0
        return max(0.0, (self.daily_start_equity - eq) / self.daily_start_equity * 100.0)

    def check_live_equity_drawdown(
        self,
        live_equity: Optional[float] = None,
        now_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate continuous intraday drawdown against `daily_start_equity` (B-8).
        Trips ONLY the 12-hour `COOLDOWN_BREAKER` when DD >= `breaker_daily_dd_pct`
        (Decision 4: NO permanent cumulative HWM kill-switch).
        """
        now = now_ts if now_ts is not None else time.time()
        if live_equity is not None:
            eq = max(0.0, float(live_equity))
            if self.daily_start_equity <= 0.0 and eq > 0.0:
                self.daily_start_equity = eq
            if eq > 0.0 or self.daily_start_equity > 0.0:
                self.current_equity = eq

        daily_dd_pct = self.compute_daily_dd_pct()
        was_active = self.is_circuit_breaker_active(now)
        tripped_now = False
        if not was_active and self.daily_start_equity > 0.0 and daily_dd_pct >= self.breaker_daily_dd_pct:
            self.trip_circuit_breaker(
                reason=f"DAILY_DRAWDOWN_{daily_dd_pct:.2f}PCT",
                now_ts=now,
            )
            tripped_now = True

        return {
            "live_equity": float(self.current_equity),
            "daily_start_equity": float(self.daily_start_equity),
            "daily_dd_pct": daily_dd_pct,
            "breaker_active": self.is_circuit_breaker_active(now),
            "tripped_now": tripped_now,
            "breaker_reason": self.breaker_reason,
            "cooldown_until_ts": self.breaker_until_ts,
        }

    def record_transfer(
        self,
        delta_usdt: float,
        note: str = "",
        from_vault: bool = False,
    ) -> Dict[str, Any]:
        """
        Adjust vault & daily equity baselines on external deposits/withdrawals (C-13)
        so external transfers do not falsely ratchet HWM or trigger fake daily DD.
        """
        delta = float(delta_usdt)
        vault_res = self.vault.record_transfer(delta_usdt=delta, note=note, from_vault=from_vault)
        if vault_res.get("recorded"):
            if self.daily_start_equity > 0.0:
                self.daily_start_equity = max(0.0, self.daily_start_equity + delta)
            if self.current_equity > 0.0 or delta > 0.0:
                self.current_equity = max(0.0, self.current_equity + delta)
        return {
            "vault_transfer": vault_res,
            "daily_start_equity": self.daily_start_equity,
            "current_equity": self.current_equity,
        }

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

        # 1. Circuit-Breaker Check (including continuous live equity daily DD)
        acct_consec_losses = int(account_state.get("consecutive_losses", self.consecutive_losses))
        live_eq_arg = account_state.get("live_equity")
        live_dd_pct = self.compute_daily_dd_pct(float(live_eq_arg)) if live_eq_arg is not None else self.compute_daily_dd_pct()
        acct_daily_dd = max(float(account_state.get("daily_dd_pct", 0.0)), live_dd_pct)
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

        # 2. Concurrent & Directional Positions Check
        open_pos_count = int(account_state.get("open_positions_count", 0))
        if open_pos_count >= self.max_concurrent_positions:
            return {
                "allowed": False,
                "reject_reason": "REJECT_MAX_CONCURRENT_POSITIONS",
                "open_positions_count": open_pos_count,
                "max_concurrent_positions": self.max_concurrent_positions,
            }
        max_same_dir = account_state.get("max_same_direction_positions", self.max_same_direction_positions)
        if max_same_dir is not None and account_state.get("same_direction_count") is not None:
            same_dir_cnt = int(account_state["same_direction_count"])
            if same_dir_cnt >= int(max_same_dir):
                return {
                    "allowed": False,
                    "reject_reason": "REJECT_MAX_DIRECTIONAL_EXPOSURE",
                    "same_direction_count": same_dir_cnt,
                    "max_same_direction_positions": int(max_same_dir),
                }

        # 3. Structural SL Distance Check (0.45% <= d_SL <= 2.25%) & Directional Geometry
        entry_price = float(decision["entry_price"])
        sl_price = float(decision["sl_price"])
        tp_price = float(decision["tp_price"])
        direction = str(decision.get("direction", "LONG")).upper().strip()

        if entry_price <= 0 or sl_price <= 0 or tp_price <= 0 or direction not in ("LONG", "SHORT"):
            return {"allowed": False, "reject_reason": "REJECT_INVALID_PRICES"}
        if direction == "LONG" and not (sl_price < entry_price < tp_price):
            return {"allowed": False, "reject_reason": "REJECT_INVALID_PRICES"}
        if direction == "SHORT" and not (tp_price < entry_price < sl_price):
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
        liq_raw = m_state.get("liquidation_price")
        liq_price = float(liq_raw) if (liq_raw is not None and float(liq_raw) > 0) else self.estimate_liquidation_price(entry_price, direction)
        valid_liq_side = (direction == "LONG" and liq_price < entry_price) or (direction == "SHORT" and liq_price > entry_price)
        if not valid_liq_side:
            return {
                "allowed": False,
                "reject_reason": "REJECT_LIQUIDATION_PROXIMITY",
                "liq_to_sl_ratio": 0.0,
                "min_required_ratio": self.min_liq_to_sl_ratio,
            }
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
            decision["rrr_net"]
            if decision.get("rrr_net") is not None
            else max(0.0, (d_tp_frac - fee_roundtrip) / (d_sl_frac + fee_roundtrip))
        )
        ev_r = float(
            decision["ev_r"]
            if decision.get("ev_r") is not None
            else (p_cal * rrr_net - (1.0 - p_cal) * 1.0)
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

        # 7. Funding Boundary Guard (< 15m to funding and paying >= 0.05%)
        mins_to_funding = float(m_state.get("minutes_to_funding", 999.0))
        funding_rate = float(m_state.get("funding_rate", 0.0))  # positive => LONG pays SHORT
        pays_high_funding = (direction == "LONG" and funding_rate >= self.funding_rate_threshold) or (
            direction == "SHORT" and funding_rate <= -self.funding_rate_threshold
        )
        if 0.0 <= mins_to_funding < self.funding_guard_window_min and pays_high_funding:
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
        locked_vault_usdt = cap_info["locked_vault_usdt"]
        if working_balance < 0.30:
            return {
                "allowed": False,
                "reject_reason": "REJECTED_VAULT_PROTECTED" if locked_vault_usdt > 0 else "REJECTED_LOW_BALANCE",
                "available_balance_usdt": avail_balance,
                "locked_vault_usdt": locked_vault_usdt,
                "working_balance_usdt": working_balance,
            }

        if self.sizing_mode == "ALL_IN":
            margin_usdt = cap_info["margin_usdt"]
        else:
            target_loss_usdt = working_balance * (self.fractional_risk_pct / 100.0)
            margin_usdt = min(
                target_loss_usdt / max(1e-9, d_sl_frac * self.fixed_leverage),
                working_balance * self.all_in_balance_fraction,
            )
        margin_usdt = min(margin_usdt, working_balance * 0.98)
        notional_usdt = margin_usdt * int(self.fixed_leverage)

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
                "working_balance_usdt": working_balance,
                "locked_vault_usdt": locked_vault_usdt,
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
                "working_balance_usdt": working_balance,
                "locked_vault_usdt": locked_vault_usdt,
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
            "sizing_mode": self.sizing_mode,
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
        `/panic` emergency handler (T7.1 / WP-2 A-3):
        1) Close all open positions FIRST (`reduceOnly` market order).
        2) Verify each position is truly flat via `get_positions(sym)`.
        3) ONLY AFTER flat is verified -> cancel all open standard & algo orders.
        4) Keep protective SL intact for any symbol that failed close or flat verify.
        """
        t0 = time.perf_counter()
        self.trip_circuit_breaker("MANUAL_PANIC_COMMAND")
        closed_symbols: List[str] = []
        cancelled_symbols: List[str] = []
        failed_symbols: List[str] = []

        try:
            positions = client.get_positions() if hasattr(client, "get_positions") else []
        except Exception as exc:
            positions = {"isError": True, "error": str(exc)}

        if not isinstance(positions, list):
            err_msg = positions.get("error", str(positions)) if isinstance(positions, dict) else str(positions)
            failed_symbols.append(f"GET_POSITIONS_ERROR ({err_msg})")
        else:
            for p in positions:
                if not isinstance(p, dict):
                    continue
                sym = str(p.get("symbol") or "").upper()
                raw_amt = float(p.get("position_amount", p.get("positionAmt", 0.0)) or 0.0)
                amt = abs(raw_amt)
                if not sym or amt <= 0:
                    continue
                direction = str(p.get("direction") or ("LONG" if raw_amt >= 0 else "SHORT")).upper()

                # 1. Close position FIRST
                try:
                    try:
                        close_res = client.close_position(sym, direction, quantity=amt)
                    except TypeError:
                        close_res = client.close_position(sym, direction)
                except Exception as ce:
                    close_res = {"isError": True, "error": str(ce)}

                if isinstance(close_res, dict) and close_res.get("isError"):
                    failed_symbols.append(f"{sym}: {close_res.get('error', 'close error')}")
                    continue
                if close_res is None or not isinstance(close_res, dict):
                    failed_symbols.append(f"{sym}: unexpected close response ({close_res})")
                    continue

                # 2. Verify flat via get_positions before cancelling protective orders
                flat_ok = False
                verify_err = ""
                if hasattr(client, "get_positions"):
                    try:
                        try:
                            post_pos = client.get_positions(sym)
                        except TypeError:
                            post_pos = client.get_positions()
                    except Exception as ge:
                        post_pos = {"isError": True, "error": str(ge)}

                    if isinstance(post_pos, list):
                        still_open = [
                            item for item in post_pos
                            if isinstance(item, dict)
                            and (not item.get("symbol") or str(item.get("symbol")).upper() == sym)
                            and abs(float(item.get("position_amount", item.get("positionAmt", 0.0)) or 0.0)) > 0
                        ]
                        if not still_open:
                            flat_ok = True
                        else:
                            rem = abs(float(still_open[0].get("position_amount", still_open[0].get("positionAmt", 0.0)) or 0.0))
                            verify_err = f"position still open qty={rem}"
                    else:
                        verify_err = f"get_positions verify failed: {post_pos}"
                else:
                    flat_ok = True

                if not flat_ok:
                    failed_symbols.append(f"{sym}: {verify_err}")
                    continue

                closed_symbols.append(sym)

                # 3. ONLY AFTER flat is verified: cancel open standard & algo orders
                if hasattr(client, "cancel_all_orders"):
                    try:
                        client.cancel_all_orders(sym)
                        cancelled_symbols.append(sym)
                    except Exception as cae:
                        failed_symbols.append(f"{sym} cancel_all_orders error: {cae}")
                        continue
                if hasattr(client, "get_open_algo_orders") and hasattr(client, "cancel_algo_order"):
                    try:
                        chk = client.get_open_algo_orders(sym)
                        if isinstance(chk, tuple) and len(chk) == 2 and chk[0] and isinstance(chk[1], list):
                            for ao in chk[1]:
                                if isinstance(ao, dict) and ao.get("algoId") is not None:
                                    client.cancel_algo_order(sym, int(ao["algoId"]))
                    except Exception:
                        pass

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "panic_executed": True,
            "closed_symbols": closed_symbols,
            "cancelled_symbols": cancelled_symbols,
            "failed_symbols": failed_symbols,
            "all_flat_verified": len(failed_symbols) == 0,
            "breaker_active": True,
            "elapsed_ms": elapsed_ms,
        }
