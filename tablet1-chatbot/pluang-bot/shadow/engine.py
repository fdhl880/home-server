"""
PYROFUEL BOT - SHADOW ACCOUNT SIMULATOR & COUNTERFACTUAL TRACKER (Task T8.1 / WP-6)
Melacak seluruh kandidat setup S1..S4 (termasuk yang di-SKIP oleh AI atau dari strategi
berstatus `shadow_only = True`) di tabel `shadow_trades` SQLite WAL terhadap harga nyata
hingga menyentuh Triple-Barrier (`SHADOW_WIN` / `SHADOW_LOSS` / `SHADOW_TIMEOUT`) dengan
paritas biaya penuh terhadap `backtest/triple_barrier.py` (Maker/Taker fee, volatility slippage,
wick/gap stop slippage, dan 8h funding boundaries).
"""
import contextlib
import json
import time
from typing import Any, Dict, List, Optional, Union
import numpy as np
import journal
from backtest.triple_barrier import (
    apply_stop_slippage,
    compute_barrier_costs,
    compute_liquidation_price,
    parse_funding_series,
)


class ShadowEngine:
    def __init__(self, db_path: Optional[str] = None, leverage: int = 20, mmr: float = 0.004):
        self.db_path = db_path
        self.leverage = int(leverage)
        self.mmr = float(mmr)
        journal.init_db(self.db_path)

    def register_candidate(
        self,
        candidate: Union[Any, Dict[str, Any]],
        decision_id: Optional[str] = None,
        ai_decision: str = "SKIP",
        p_raw: float = 0.50,
        p_cal: float = 0.50,
        features: Optional[Dict[str, Any]] = None,
        opened_at: Optional[int] = None,
        sniper_mode: bool = True,
    ) -> str:
        """
        Insert a new candidate setup into `shadow_trades` with `status='OPEN'`.
        """
        c = candidate
        symbol = str((c.get("symbol") if isinstance(c, dict) else getattr(c, "symbol", "")) or "UNKNOWN")
        strategy_id = str(c["strategy_id"] if isinstance(c, dict) else c.strategy_id)
        regime = str((c.get("regime") if isinstance(c, dict) else getattr(c, "regime", "UNKNOWN")) or "UNKNOWN")
        direction = str(c["direction"] if isinstance(c, dict) else c.direction).upper()
        entry_px = float(c["entry_price"] if isinstance(c, dict) else c.entry_price)
        sl_px = float(c["sl_price"] if isinstance(c, dict) else c.sl_price)
        tp1_px = float(
            (c.get("tp1_price") if isinstance(c, dict) else getattr(c, "tp1_price", 0.0))
            or (entry_px + (0.55 if direction == "LONG" else -0.55) * abs(entry_px - sl_px))
        )
        tp2_px = float(
            (c.get("tp2_price") or c.get("tp_price"))
            if isinstance(c, dict)
            else getattr(c, "tp2_price", getattr(c, "tp_price", 0.0))
        )
        sl_dist_pct = float(
            (c.get("sl_distance_pct") if isinstance(c, dict) else getattr(c, "sl_distance_pct", 0.0))
            or (abs(entry_px - sl_px) / max(entry_px, 1e-12) * 100.0)
        )
        rrr_net = float((c.get("rrr_net") if isinstance(c, dict) else getattr(c, "rrr_net", 1.8)) or 1.8)
        vb_bars = int(
            (c.get("vertical_barrier_bars") if isinstance(c, dict) else getattr(c, "vertical_barrier_bars", 16))
            or 16
        )
        entry_type = str(
            (c.get("entry_type") if isinstance(c, dict) else getattr(c, "entry_type", "MAKER_FIRST_GTX"))
            or "MAKER_FIRST_GTX"
        )
        atr_pct = c.get("atr_pct") if isinstance(c, dict) else getattr(c, "atr_pct", None)
        notional_usdt = float(
            (c.get("notional_usdt") if isinstance(c, dict) else getattr(c, "notional_usdt", 0.0)) or 0.0
        )

        ts_ms = int(opened_at if opened_at is not None else time.time() * 1000)
        shadow_id = f"SHD_{symbol}_{strategy_id[:2]}_{ts_ms}_{int(time.time_ns() % 100000)}"
        feat_payload = dict(features or {})
        feat_payload.setdefault(
            "_exec_meta",
            {
                "entry_type": entry_type,
                "atr_pct": float(atr_pct) if atr_pct is not None else None,
                "notional_usdt": notional_usdt,
            },
        )
        feat_str = json.dumps(feat_payload, ensure_ascii=False)

        with contextlib.closing(journal.get_db(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO shadow_trades (
                        shadow_id, decision_id, symbol, strategy_id, regime, direction,
                        entry_price, sl_price, tp1_price, tp2_price, sl_distance_pct,
                        rrr_net, vertical_barrier_bars, sniper_mode, status,
                        tp1_hit, current_sl_price, bars_elapsed, p_raw, p_cal,
                        ai_decision, features_json, opened_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 0, ?, 0, ?, ?, ?, ?, ?)
                    """,
                    (
                        shadow_id,
                        decision_id,
                        symbol,
                        strategy_id,
                        regime,
                        direction,
                        entry_px,
                        sl_px,
                        tp1_px,
                        tp2_px,
                        sl_dist_pct,
                        rrr_net,
                        vb_bars,
                        1 if sniper_mode else 0,
                        sl_px,
                        float(p_raw),
                        float(p_cal),
                        str(ai_decision),
                        feat_str,
                        ts_ms,
                    ),
                )
        return shadow_id

    @staticmethod
    def _extract_exec_meta(row: Any) -> Dict[str, Any]:
        raw_feat = row["features_json"] if "features_json" in row.keys() else "{}"
        try:
            parsed = json.loads(raw_feat or "{}")
            meta = parsed.get("_exec_meta", {}) if isinstance(parsed, dict) else {}
        except Exception:
            meta = {}
        return {
            "entry_type": str(meta.get("entry_type") or "MAKER_FIRST_GTX"),
            "atr_pct": float(meta["atr_pct"]) if meta.get("atr_pct") is not None else None,
            "notional_usdt": float(meta.get("notional_usdt") or 0.0),
        }

    def resolve_bar(
        self,
        shadow_row: Any,
        price_or_candle: Union[float, Dict[str, Any]],
        advance_bar: bool = True,
        closed_at: Optional[int] = None,
        cost_pct: Optional[float] = None,
        maker_fee_pct: float = 0.02,
        taker_fee_pct: float = 0.05,
        base_slippage_pct: float = 0.015,
        funding_rate_pct: float = 0.01,
        funding_interval_hours: int = 8,
        funding_series: Optional[Any] = None,
        stop_slip_fraction: float = 0.06,
        tp1_partial_weight: float = 0.35,
    ) -> Dict[str, Any]:
        """
        Resolve a single shadow row against a new price tick or closed candle `{open, high, low, close}`.
        Deducts maker/taker fees, volatility & size-scaled slippage, wick/gap stop slippage,
        and 8h funding boundaries matching `backtest/triple_barrier.py` cost parity.
        """
        if isinstance(price_or_candle, (int, float)):
            op = hi = lo = cl = float(price_or_candle)
            candle_obj = {"open": op, "high": hi, "low": lo, "close": cl}
        else:
            cl = float(price_or_candle.get("close", price_or_candle.get("mark_price", 0.0)))
            hi = float(price_or_candle.get("high", cl))
            lo = float(price_or_candle.get("low", cl))
            op = float(price_or_candle.get("open", cl))
            candle_obj = {"open": op, "high": hi, "low": lo, "close": cl}

        now_ms = int(
            closed_at
            if closed_at is not None
            else (
                price_or_candle.get("close_time")
                if isinstance(price_or_candle, dict) and price_or_candle.get("close_time")
                else time.time() * 1000
            )
        )

        direction = str(shadow_row["direction"]).upper()
        entry_px = float(shadow_row["entry_price"])
        init_sl = float(shadow_row["sl_price"])
        active_sl = float(shadow_row["current_sl_price"] or init_sl)
        tp1_px = float(shadow_row["tp1_price"])
        tp2_px = float(shadow_row["tp2_price"])
        sl_dist = abs(entry_px - init_sl)
        sl_dist_pct = float(shadow_row["sl_distance_pct"] or (sl_dist / max(entry_px, 1e-12) * 100.0))
        sniper_mode = bool(shadow_row["sniper_mode"])
        tp1_hit = bool(shadow_row["tp1_hit"])
        bars_elapsed = int(shadow_row["bars_elapsed"] or 0) + (1 if advance_bar else 0)
        max_bars = int(shadow_row["vertical_barrier_bars"] or 16)
        opened_at = int(shadow_row["opened_at"] or now_ms)

        locked_sl = (
            entry_px + 0.38 * sl_dist
            if direction == "LONG"
            else entry_px - 0.38 * sl_dist
        )
        liq_px = compute_liquidation_price(entry_px, direction, leverage=self.leverage, mmr=self.mmr)

        hit_reason = None
        exit_px = cl
        liquidated = False

        if direction == "LONG":
            if (lo <= liq_px and liq_px >= active_sl) or op <= liq_px:
                hit_reason = "LIQUIDATED"
                exit_px = min(liq_px, op) if op <= liq_px else liq_px
                liquidated = True
            elif not tp1_hit:
                if lo <= active_sl:
                    hit_reason = "SL"
                    exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                elif sniper_mode and hi >= tp2_px:
                    tp1_hit = True
                    hit_reason = "TP2"
                    exit_px = tp2_px
                elif sniper_mode and hi >= tp1_px:
                    tp1_hit = True
                    active_sl = locked_sl
                    if cl <= active_sl and op > active_sl:
                        hit_reason = "TP1_LOCK_WIN"
                        exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                elif (not sniper_mode) and hi >= tp2_px:
                    hit_reason = "TP"
                    exit_px = tp2_px
            else:
                if lo <= active_sl:
                    hit_reason = "TP1_LOCK_WIN"
                    exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                elif hi >= tp2_px:
                    hit_reason = "TP2"
                    exit_px = tp2_px
        else:  # SHORT
            if (hi >= liq_px and liq_px <= active_sl) or op >= liq_px:
                hit_reason = "LIQUIDATED"
                exit_px = max(liq_px, op) if op >= liq_px else liq_px
                liquidated = True
            elif not tp1_hit:
                if hi >= active_sl:
                    hit_reason = "SL"
                    exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                elif sniper_mode and lo <= tp2_px:
                    tp1_hit = True
                    hit_reason = "TP2"
                    exit_px = tp2_px
                elif sniper_mode and lo <= tp1_px:
                    tp1_hit = True
                    active_sl = locked_sl
                    if cl >= active_sl and op < active_sl:
                        hit_reason = "TP1_LOCK_WIN"
                        exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                elif (not sniper_mode) and lo <= tp2_px:
                    hit_reason = "TP"
                    exit_px = tp2_px
            else:
                if hi >= active_sl:
                    hit_reason = "TP1_LOCK_WIN"
                    exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                elif lo <= tp2_px:
                    hit_reason = "TP2"
                    exit_px = tp2_px

        if hit_reason is None and bars_elapsed >= max_bars:
            hit_reason = "TIME_BARRIER"
            exit_px = cl

        if hit_reason is None:
            return {
                "resolved": False,
                "tp1_hit": tp1_hit,
                "active_sl": round(active_sl, 8),
                "bars_elapsed": bars_elapsed,
            }

        exec_meta = self._extract_exec_meta(shadow_row)
        entry_is_maker = exec_meta["entry_type"] == "MAKER_FIRST_GTX"
        parsed_funding = parse_funding_series(funding_series)

        if cost_pct is not None:
            costs = {
                "entry_fee_pct": float(cost_pct) * 0.4,
                "exit_fee_pct": float(cost_pct) * 0.4,
                "entry_slippage_pct": float(cost_pct) * 0.1,
                "exit_slippage_pct": float(cost_pct) * 0.1,
                "slippage_pct": float(cost_pct) * 0.2,
                "funding_cost_pct": 0.0,
                "funding_events": 0,
                "cost_pct": float(cost_pct),
            }
        else:
            costs = compute_barrier_costs(
                direction=direction,
                outcome=hit_reason,
                entry_is_maker=entry_is_maker,
                entry_bar=candle_obj,
                exit_bar=candle_obj,
                open_time_ms=opened_at,
                close_time_ms=now_ms,
                sl_dist_pct=sl_dist_pct,
                atr_pct=exec_meta["atr_pct"],
                notional_usdt=exec_meta["notional_usdt"],
                maker_fee_pct=maker_fee_pct,
                taker_fee_pct=taker_fee_pct,
                base_slippage_pct=base_slippage_pct,
                funding_rate_pct=funding_rate_pct,
                funding_interval_hours=funding_interval_hours,
                parsed_funding=parsed_funding,
            )

        if liquidated:
            gross_ret_pct = -(100.0 / max(1.0, float(self.leverage)))
            total_cost_pct = float(costs["cost_pct"])
            net_ret_pct = gross_ret_pct
            r_gross = -1.0 / max(sl_dist_pct * float(self.leverage) / 100.0, 0.01)
            r_net = r_gross
        else:
            runner_ret_pct = (
                ((exit_px - entry_px) / max(entry_px, 1e-12) * 100.0)
                if direction == "LONG"
                else ((entry_px - exit_px) / max(entry_px, 1e-12) * 100.0)
            )
            if sniper_mode and tp1_hit:
                tp1_ret_pct = 0.55 * sl_dist_pct
                w1 = float(np.clip(tp1_partial_weight, 0.0, 1.0))
                gross_ret_pct = w1 * tp1_ret_pct + (1.0 - w1) * runner_ret_pct
            else:
                gross_ret_pct = runner_ret_pct

            total_cost_pct = float(costs["cost_pct"])
            net_ret_pct = gross_ret_pct - total_cost_pct
            r_gross = gross_ret_pct / max(sl_dist_pct, 1e-9)
            r_net = net_ret_pct / max(sl_dist_pct, 1e-9)

        if hit_reason == "TIME_BARRIER":
            outcome = "SHADOW_TIMEOUT"
        elif liquidated or r_net <= 0.0:
            outcome = "SHADOW_LOSS"
        else:
            outcome = "SHADOW_WIN"

        return {
            "resolved": True,
            "outcome": outcome,
            "hit_reason": hit_reason,
            "exit_price": round(float(exit_px), 8),
            "gross_r": round(float(r_gross), 4),
            "r_multiple_gross": round(float(r_gross), 4),
            "r_multiple_net": round(float(r_net), 4),
            "gross_return_pct": round(float(gross_ret_pct), 4),
            "cost_pct": round(float(total_cost_pct), 4),
            "net_return_pct": round(float(net_ret_pct), 4),
            "entry_fee_pct": round(float(costs["entry_fee_pct"]), 4),
            "exit_fee_pct": round(float(costs["exit_fee_pct"]), 4),
            "entry_slippage_pct": round(float(costs["entry_slippage_pct"]), 4),
            "exit_slippage_pct": round(float(costs["exit_slippage_pct"]), 4),
            "slippage_pct": round(float(costs["slippage_pct"]), 4),
            "funding_cost_pct": round(float(costs["funding_cost_pct"]), 4),
            "funding_events": int(costs["funding_events"]),
            "tp1_hit": bool(tp1_hit),
            "active_sl": round(float(active_sl), 8),
            "bars_elapsed": int(bars_elapsed),
            "liquidated": bool(liquidated),
            "closed_at": now_ms,
        }

    def update_open_shadows(
        self,
        symbol: str,
        price_or_candle: Union[float, Dict[str, Any]],
        advance_bar: bool = True,
        closed_at: Optional[int] = None,
        cost_pct: Optional[float] = None,
        maker_fee_pct: float = 0.02,
        taker_fee_pct: float = 0.05,
        base_slippage_pct: float = 0.015,
        funding_rate_pct: float = 0.01,
        funding_interval_hours: int = 8,
        funding_series: Optional[Any] = None,
        stop_slip_fraction: float = 0.06,
    ) -> List[Dict[str, Any]]:
        """
        Update all OPEN shadow trades for `symbol` with a new markPrice or candle `{high, low, close}`.
        Resolves any trade that hits SL, TP1->LockSL, TP2, liquidation, or vertical time barrier.
        Returns list of resolved shadow trade dicts.
        """
        resolved: List[Dict[str, Any]] = []

        with contextlib.closing(journal.get_db(self.db_path)) as conn:
            with conn:
                open_rows = conn.execute(
                    "SELECT * FROM shadow_trades WHERE symbol = ? AND status = 'OPEN'",
                    (symbol,),
                ).fetchall()

                for r in open_rows:
                    sh_id = r["shadow_id"]
                    bar_res = self.resolve_bar(
                        r,
                        price_or_candle,
                        advance_bar=advance_bar,
                        closed_at=closed_at,
                        cost_pct=cost_pct,
                        maker_fee_pct=maker_fee_pct,
                        taker_fee_pct=taker_fee_pct,
                        base_slippage_pct=base_slippage_pct,
                        funding_rate_pct=funding_rate_pct,
                        funding_interval_hours=funding_interval_hours,
                        funding_series=funding_series,
                        stop_slip_fraction=stop_slip_fraction,
                    )

                    if bar_res["resolved"]:
                        conn.execute(
                            """
                            UPDATE shadow_trades SET
                                status = 'CLOSED',
                                outcome = ?,
                                exit_price = ?,
                                r_multiple_net = ?,
                                tp1_hit = ?,
                                current_sl_price = ?,
                                bars_elapsed = ?,
                                closed_at = ?
                            WHERE shadow_id = ?
                            """,
                            (
                                bar_res["outcome"],
                                bar_res["exit_price"],
                                bar_res["r_multiple_net"],
                                1 if bar_res["tp1_hit"] else 0,
                                bar_res["active_sl"],
                                bar_res["bars_elapsed"],
                                bar_res["closed_at"],
                                sh_id,
                            ),
                        )
                        resolved.append({
                            "shadow_id": sh_id,
                            "symbol": symbol,
                            "strategy_id": r["strategy_id"],
                            "regime": r["regime"],
                            "ai_decision": r["ai_decision"],
                            **bar_res,
                        })
                    else:
                        conn.execute(
                            """
                            UPDATE shadow_trades SET
                                tp1_hit = ?,
                                current_sl_price = ?,
                                bars_elapsed = ?
                            WHERE shadow_id = ?
                            """,
                            (
                                1 if bar_res["tp1_hit"] else 0,
                                bar_res["active_sl"],
                                bar_res["bars_elapsed"],
                                sh_id,
                            ),
                        )

        return resolved

    def get_counterfactual_regret_summary(self, strategy_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluate Counterfactual Regret for candidates skipped by AI (`ai_decision == 'SKIP'`).
        """
        with contextlib.closing(journal.get_db(self.db_path)) as conn:
            if strategy_id:
                rows = conn.execute(
                    "SELECT outcome, r_multiple_net FROM shadow_trades WHERE status = 'CLOSED' AND ai_decision = 'SKIP' AND strategy_id = ?",
                    (strategy_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT outcome, r_multiple_net FROM shadow_trades WHERE status = 'CLOSED' AND ai_decision = 'SKIP'"
                ).fetchall()

        if not rows:
            return {
                "total_skipped_resolved": 0,
                "losses_avoided": 0,
                "missed_wins": 0,
                "net_saved_r": 0.0,
            }

        r_vals = [float(r["r_multiple_net"] or 0.0) for r in rows]
        losses_avoided = sum(1 for r in r_vals if r <= 0)
        missed_wins = sum(1 for r in r_vals if r > 0)
        net_saved_r = round(-sum(r_vals), 4)
        return {
            "total_skipped_resolved": len(rows),
            "losses_avoided": losses_avoided,
            "missed_wins": missed_wins,
            "net_saved_r": net_saved_r,
        }
