"""
PYROFUEL BOT - SHADOW ACCOUNT SIMULATOR & COUNTERFACTUAL TRACKER (Task T8.1)
Melacak seluruh kandidat setup S1..S4 (termasuk yang di-SKIP oleh AI atau dari strategi
berstatus `shadow_only = True`) di tabel `shadow_trades` SQLite WAL terhadap harga nyata
hingga menyentuh Triple-Barrier (`SHADOW_WIN` / `SHADOW_LOSS`).
"""
import json
import time
from typing import Any, Dict, List, Optional, Union
import journal


class ShadowEngine:
    def __init__(self, db_path: Optional[str] = None, leverage: int = 20):
        self.db_path = db_path
        self.leverage = int(leverage)
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

        ts_ms = int(opened_at if opened_at is not None else time.time() * 1000)
        shadow_id = f"SHD_{symbol}_{strategy_id[:2]}_{ts_ms}_{int(time.time_ns() % 100000)}"
        feat_str = json.dumps(features or {}, ensure_ascii=False)

        with journal.get_db(self.db_path) as conn:
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

    def update_open_shadows(
        self,
        symbol: str,
        price_or_candle: Union[float, Dict[str, Any]],
        advance_bar: bool = True,
        closed_at: Optional[int] = None,
        cost_pct: float = 0.08,
    ) -> List[Dict[str, Any]]:
        """
        Update all OPEN shadow trades for `symbol` with a new markPrice or candle `{high, low, close}`.
        Resolves any trade that hits SL, TP1->LockSL, TP2, or vertical time barrier.
        Returns list of resolved shadow trade dicts.
        """
        if isinstance(price_or_candle, (int, float)):
            hi = lo = cl = float(price_or_candle)
        else:
            cl = float(price_or_candle.get("close", price_or_candle.get("mark_price", 0.0)))
            hi = float(price_or_candle.get("high", cl))
            lo = float(price_or_candle.get("low", cl))

        now_ms = int(closed_at if closed_at is not None else time.time() * 1000)
        resolved: List[Dict[str, Any]] = []

        with journal.get_db(self.db_path) as conn:
            open_rows = conn.execute(
                "SELECT * FROM shadow_trades WHERE symbol = ? AND status = 'OPEN'",
                (symbol,),
            ).fetchall()

            for r in open_rows:
                sh_id = r["shadow_id"]
                direction = str(r["direction"]).upper()
                entry_px = float(r["entry_price"])
                init_sl = float(r["sl_price"])
                active_sl = float(r["current_sl_price"] or init_sl)
                tp1_px = float(r["tp1_price"])
                tp2_px = float(r["tp2_price"])
                sl_dist = abs(entry_px - init_sl)
                sl_dist_pct = float(r["sl_distance_pct"] or (sl_dist / max(entry_px, 1e-12) * 100.0))
                sniper_mode = bool(r["sniper_mode"])
                tp1_hit = bool(r["tp1_hit"])
                bars_elapsed = int(r["bars_elapsed"] or 0) + (1 if advance_bar else 0)
                max_bars = int(r["vertical_barrier_bars"] or 16)

                locked_sl = (
                    entry_px + 0.38 * sl_dist
                    if direction == "LONG"
                    else entry_px - 0.38 * sl_dist
                )

                hit_reason = None
                exit_px = cl

                if direction == "LONG":
                    if not tp1_hit:
                        if lo <= active_sl:
                            hit_reason = "SL"
                            exit_px = active_sl
                        elif sniper_mode and hi >= tp2_px:
                            tp1_hit = True
                            hit_reason = "TP2"
                            exit_px = tp2_px
                        elif sniper_mode and hi >= tp1_px:
                            tp1_hit = True
                            active_sl = locked_sl
                        elif (not sniper_mode) and hi >= tp2_px:
                            hit_reason = "TP"
                            exit_px = tp2_px
                    else:
                        if lo <= active_sl:
                            hit_reason = "TP1_LOCK_WIN"
                            exit_px = active_sl
                        elif hi >= tp2_px:
                            hit_reason = "TP2"
                            exit_px = tp2_px
                else:  # SHORT
                    if not tp1_hit:
                        if hi >= active_sl:
                            hit_reason = "SL"
                            exit_px = active_sl
                        elif sniper_mode and lo <= tp2_px:
                            tp1_hit = True
                            hit_reason = "TP2"
                            exit_px = tp2_px
                        elif sniper_mode and lo <= tp1_px:
                            tp1_hit = True
                            active_sl = locked_sl
                        elif (not sniper_mode) and lo <= tp2_px:
                            hit_reason = "TP"
                            exit_px = tp2_px
                    else:
                        if hi >= active_sl:
                            hit_reason = "TP1_LOCK_WIN"
                            exit_px = active_sl
                        elif lo <= tp2_px:
                            hit_reason = "TP2"
                            exit_px = tp2_px

                if hit_reason is None and bars_elapsed >= max_bars:
                    hit_reason = "TIME_BARRIER"
                    exit_px = cl

                if hit_reason is not None:
                    runner_ret_pct = (
                        ((exit_px - entry_px) / entry_px * 100.0)
                        if direction == "LONG"
                        else ((entry_px - exit_px) / entry_px * 100.0)
                    )
                    if sniper_mode and tp1_hit:
                        tp1_ret_pct = 0.55 * sl_dist_pct
                        gross_ret_pct = 0.35 * tp1_ret_pct + 0.65 * runner_ret_pct
                    else:
                        gross_ret_pct = runner_ret_pct

                    net_ret_pct = gross_ret_pct - float(cost_pct)
                    r_net = round(net_ret_pct / max(sl_dist_pct, 1e-9), 4)
                    outcome = "SHADOW_WIN" if r_net > 0 else "SHADOW_LOSS"

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
                            outcome,
                            round(exit_px, 8),
                            r_net,
                            1 if tp1_hit else 0,
                            round(active_sl, 8),
                            bars_elapsed,
                            now_ms,
                            sh_id,
                        ),
                    )
                    resolved.append({
                        "shadow_id": sh_id,
                        "symbol": symbol,
                        "strategy_id": r["strategy_id"],
                        "regime": r["regime"],
                        "outcome": outcome,
                        "hit_reason": hit_reason,
                        "exit_price": round(exit_px, 8),
                        "r_multiple_net": r_net,
                        "ai_decision": r["ai_decision"],
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
                        (1 if tp1_hit else 0, round(active_sl, 8), bars_elapsed, sh_id),
                    )

        return resolved

    def get_counterfactual_regret_summary(self, strategy_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluate Counterfactual Regret for candidates skipped by AI (`ai_decision == 'SKIP'`).
        """
        with journal.get_db(self.db_path) as conn:
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
        # Positive `net_saved_r` means skipping saved the account from negative sum of R
        net_saved_r = round(-sum(r_vals), 4)
        return {
            "total_skipped_resolved": len(rows),
            "losses_avoided": losses_avoided,
            "missed_wins": missed_wins,
            "net_saved_r": net_saved_r,
        }
