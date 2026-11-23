"""
===========================================================================
PYROFUEL CONTINUOUS AI TRADE MEMORY & EXPERIENCE ENGINE v1.0
===========================================================================
Guarantees the AI ALWAYS learns from EVERY position opened AND closed —
whether opened by the bot, auto-imported after a Termux restart, or closed
on Binance while offline:

1. `record_open(pos)` — immediately snapshots entry thesis, setup, regime,
   math/AI probabilities, microstructure (OFI/Hurst/ADX/RSI), SL/TP geometry,
   and 12-dim quant feature vector when ANY trade opens.
2. `record_close(...)` — immediately captures exit price, gross/net PnL,
   fees, R-multiple, hold duration, MFE, exit reason, and automated
   post-mortem lessons (e.g. FAST_SL_STOPHUNT, COUNTER_TREND_LOSS,
   HIGH_FEE_DRAG, TP2_RUNNER_WIN, TP1_LOCK_WIN) when ANY trade closes.
3. `sync_binance_closed_history(bn_client)` — deduplicated backfill of real
   Binance Futures round-trips so trades closed offline/manually are NEVER
   missed by AI learning!
4. `build_prompt_memory_context(...)` — compiles a compact (~120 token)
   experience brief injected DIRECTLY into Layer 2 Setup Hunter & Layer 5
   Supreme Judge prompts BEFORE every decision so the LLM actively uses its
   own historical win/loss memory & mistakes!
===========================================================================
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from state_io import atomic_write_json, get_file_lock, read_json_safe

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_AI_MEMORY_PATH = os.path.join(BASE_DIR, "results", "ai_trade_memory.json")

_MEM_LOCK = threading.RLock()


def synthesize_feature_vector_from_pos(pos: Dict[str, Any]) -> List[float]:
    """
    Build a deterministic 12-dim normalized feature vector when an auto-imported
    or exchange-synced position lacks `quant_feature_vector`, ensuring Brain-1
    (TabularMetaModel), Brain-2 (EpisodicMarketMemory), and Brain-3 ALWAYS train.
    """
    existing = pos.get("quant_feature_vector")
    if isinstance(existing, list) and len(existing) >= 10:
        return [round(float(x), 5) for x in existing[:12]]

    mp = pos.get("math_proof") if isinstance(pos.get("math_proof"), dict) else {}
    dir_sign = 1.0 if str(pos.get("direction", "LONG")).upper() == "LONG" else -1.0
    p_math = float(mp.get("p_math_pct") or pos.get("confidence_score") or 65.0)
    obi = float(mp.get("obi_weighted_20") or 0.0)
    hurst = float(mp.get("hurst_exponent") or 0.50)
    vr_z = float(mp.get("variance_ratio_z") or 0.0)
    adx = float(mp.get("adx_14") or 22.0)
    vpin = float(mp.get("vpin") or 0.35)
    hmm_c = float(mp.get("hmm_cascade_prob") or 0.10)
    fr_raw = float(mp.get("funding_rate_raw") or 0.0)
    rsi_15 = float(mp.get("rsi_15m") or 50.0)
    entry_px = float(pos.get("entry_price") or 0.0)
    sl_px = float(pos.get("init_stop_loss") or pos.get("stop_loss") or 0.0)
    sl_pct = (abs(entry_px - sl_px) / entry_px * 100.0) if (entry_px > 0 and sl_px > 0) else 1.2

    vec = [
        round(max(-1.0, min(1.0, (p_math - 50.0) / 50.0)), 5),
        round(max(-1.0, min(1.0, obi)), 5),
        round(max(-1.0, min(1.0, (hurst - 0.50) * 4.0)), 5),
        round(max(-1.0, min(1.0, vr_z / 3.0)), 5),
        round(max(0.0, min(1.0, adx / 50.0)), 5),
        round(max(0.0, min(1.0, vpin)), 5),
        round(max(0.0, min(1.0, hmm_c)), 5),
        round(max(-1.0, min(1.0, fr_raw * 1000.0)), 5),
        round(max(-1.0, min(1.0, (rsi_15 - 50.0) / 50.0)), 5),
        round(dir_sign, 5),
        round(max(0.0, min(1.0, sl_pct / 2.5)), 5),
        round(max(0.0, min(1.0, float(pos.get("confidence_score") or 70.0) / 100.0)), 5),
    ]
    return vec


def _derive_trade_lessons(rec: Dict[str, Any]) -> List[str]:
    """Derive concrete structured post-mortem tags from a closed trade."""
    lessons: List[str] = []
    outcome = str(rec.get("outcome") or "").upper()
    reason = str(rec.get("exit_reason") or "").upper()
    hold_m = float(rec.get("hold_minutes") or 0.0)
    sl_pct = float(rec.get("sl_pct") or 0.0)
    r_net = float(rec.get("r_multiple_net") or 0.0)
    gross = float(rec.get("gross_pnl_usd") or 0.0)
    fee = float(rec.get("fee_usd") or 0.0)
    net = float(rec.get("net_pnl_usd") or 0.0)
    max_r = float(rec.get("max_r_reached") or 0.0)

    if outcome == "LOSS":
        if hold_m > 0 and hold_m <= 15.0:
            lessons.append("FAST_SL_STOPHUNT(<15m): avoid chasing entry or tight SL on noisy spike")
        if 0 < sl_pct < 0.90:
            lessons.append(f"TIGHT_SL({sl_pct:.2f}%): SL too narrow for 20x noise")
        if gross > 0 and net < 0:
            lessons.append("FEE_FLIPPED_WIN_TO_LOSS: breakeven/exit too tight vs taker fee")
        if "EARLY_INVALIDATION" in reason:
            lessons.append("EARLY_PANIC_SCRATCH: cut before real SL")
        if max_r >= 0.60:
            lessons.append(f"GAVE_BACK_PROFIT(peak +{max_r:.2f}R): trend reversed before TP")
        if not lessons:
            lessons.append(f"SL_LOSS({r_net:+.2f}R) on {rec.get('setup_name', 'SETUP')} in {rec.get('regime', 'REGIME')}")
    elif outcome == "WIN":
        if r_net >= 1.20:
            lessons.append(f"STRONG_RUNNER_WIN({r_net:+.2f}R): high-edge setup worked cleanly")
        elif "TP1" in reason or "PROFIT_LOCK" in reason:
            lessons.append(f"TP1_LOCK_WIN({r_net:+.2f}R)")
        else:
            lessons.append(f"CLEAN_TP_WIN({r_net:+.2f}R)")
    if abs(gross) > 0 and fee > abs(gross) * 0.45 and fee >= 0.15:
        lessons.append("HIGH_FEE_DRAG: prefer maker GTX entries")
    return lessons[:3]


class AITradeMemoryEngine:
    """
    Persistent atomic memory of ALL opened and closed trades for continuous
    AI self-learning and prompt-level feedback.
    """

    def __init__(self, memory_path: Optional[str] = None, max_closed: int = 300):
        self.memory_path = memory_path or DEFAULT_AI_MEMORY_PATH
        self.max_closed = max(50, int(max_closed))
        self._lock = get_file_lock(self.memory_path)

    def _default_state(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "open_records": {},
            "closed_trades": [],
            "synced_binance_order_ids": [],
            "last_binance_sync_ts": 0.0,
            "stats_summary": {},
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

    def _load(self) -> Dict[str, Any]:
        data = read_json_safe(self.memory_path, default=None, strict_on_corrupt=False, expected_type=dict)
        if not isinstance(data, dict):
            return self._default_state()
        st = self._default_state()
        st.update(data)
        if not isinstance(st.get("open_records"), dict):
            st["open_records"] = {}
        if not isinstance(st.get("closed_trades"), list):
            st["closed_trades"] = []
        if not isinstance(st.get("synced_binance_order_ids"), list):
            st["synced_binance_order_ids"] = []
        return st

    def _recompute_summary(self, st: Dict[str, Any]) -> Dict[str, Any]:
        closed = st.get("closed_trades") or []
        total = len(closed)
        wins = [t for t in closed if t.get("outcome") == "WIN"]
        losses = [t for t in closed if t.get("outcome") == "LOSS"]
        net_sum = sum(float(t.get("net_pnl_usd") or 0.0) for t in closed)
        gross_win = sum(max(0.0, float(t.get("net_pnl_usd") or 0.0)) for t in wins)
        gross_loss = abs(sum(min(0.0, float(t.get("net_pnl_usd") or 0.0)) for t in losses))
        pf = round(gross_win / gross_loss, 3) if gross_loss > 1e-9 else (9.99 if gross_win > 0 else 0.0)

        by_sym: Dict[str, Dict[str, Any]] = {}
        by_setup: Dict[str, Dict[str, Any]] = {}
        by_dir_reg: Dict[str, Dict[str, Any]] = {}

        for t in closed:
            sym = str(t.get("symbol") or t.get("binance_pair") or "UNK").upper()
            setup = str(t.get("setup_name") or "UNKNOWN").upper()
            d_r = f"{str(t.get('direction') or 'UNK').upper()}@{str(t.get('regime') or 'NORMAL').upper()}"
            is_w = 1 if t.get("outcome") == "WIN" else 0
            is_l = 1 if t.get("outcome") == "LOSS" else 0
            net_v = float(t.get("net_pnl_usd") or 0.0)
            r_v = float(t.get("r_multiple_net") or 0.0)

            for bucket, key in ((by_sym, sym), (by_setup, setup), (by_dir_reg, d_r)):
                b = bucket.setdefault(key, {"w": 0, "l": 0, "net_usd": 0.0, "sum_r": 0.0})
                b["w"] += is_w
                b["l"] += is_l
                b["net_usd"] = round(b["net_usd"] + net_v, 4)
                b["sum_r"] = round(b["sum_r"] + r_v, 3)

        # Recent streak
        streak = 0
        streak_type = "NONE"
        for t in reversed(closed):
            oc = t.get("outcome")
            if oc not in ("WIN", "LOSS"):
                continue
            if streak_type == "NONE":
                streak_type = oc
                streak = 1
            elif oc == streak_type:
                streak += 1
            else:
                break

        summary = {
            "total_opened_tracked": len(st.get("open_records") or {}),
            "total_closed_learned": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round((len(wins) / max(1, len(wins) + len(losses))) * 100.0, 1),
            "net_pnl_usd": round(net_sum, 4),
            "profit_factor": pf,
            "streak": f"{streak}{streak_type[0]}" if streak > 0 else "0",
            "by_symbol": by_sym,
            "by_setup": by_setup,
            "by_dir_regime": by_dir_reg,
        }
        st["stats_summary"] = summary
        return summary

    def _save(self, st: Dict[str, Any]) -> None:
        self._recompute_summary(st)
        st["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        atomic_write_json(self.memory_path, st, make_bak=True)

    def record_open(self, pos: Dict[str, Any]) -> Dict[str, Any]:
        """Record every opened position immediately so its entry context is never lost."""
        pos_id = str(pos.get("id") or f"POS_{pos.get('binance_pair', 'UNK')}_{int(time.time()*1000)}")
        pair = str(pos.get("binance_pair") or pos.get("symbol", "").replace("-USD", "USDT")).upper()
        sym = str(pos.get("symbol") or pair.replace("USDT", "-USD")).upper()
        entry_px = float(pos.get("entry_price") or 0.0)
        sl_px = float(pos.get("init_stop_loss") or pos.get("stop_loss") or 0.0)
        sl_pct = round(abs(entry_px - sl_px) / entry_px * 100.0, 3) if (entry_px > 0 and sl_px > 0) else 0.0
        mp = pos.get("math_proof") if isinstance(pos.get("math_proof"), dict) else {}

        rec = {
            "trade_id": pos_id,
            "order_id": pos.get("order_id"),
            "symbol": sym,
            "binance_pair": pair,
            "direction": str(pos.get("direction") or "LONG").upper(),
            "setup_name": str(pos.get("setup_name") or "AI_SETUP"),
            "regime": str(pos.get("regime") or mp.get("statistical_regime") or "NORMAL").upper(),
            "entry_price": entry_px,
            "stop_loss": sl_px,
            "take_profit_1": float(pos.get("take_profit_1") or 0.0),
            "take_profit_2": float(pos.get("take_profit_2") or pos.get("take_profit") or 0.0),
            "sl_pct": sl_pct,
            "leverage": int(pos.get("leverage") or 20),
            "margin_usd": round(float(pos.get("initial_position_size_usd") or pos.get("position_size_usd") or 0.0), 4),
            "confidence_score": float(pos.get("confidence_score") or 0.0),
            "p_math_pct": float(mp.get("p_math_pct") or 0.0),
            "p_ai_pct": float(mp.get("p_ai_pct") or 0.0),
            "obi_20": float(mp.get("obi_weighted_20") or 0.0),
            "hurst": float(mp.get("hurst_exponent") or 0.50),
            "adx_14": float(mp.get("adx_14") or 0.0),
            "rsi_15m": float(mp.get("rsi_15m") or 50.0),
            "gear_id": (pos.get("active_gear") or {}).get("gear", 1) if isinstance(pos.get("active_gear"), dict) else 1,
            "quant_feature_vector": synthesize_feature_vector_from_pos(pos),
            "opened_ts": float(pos.get("opened_ts") or time.time()),
            "opened_at": pos.get("opened_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "source": pos.get("close_source") or ("AUTO_IMPORT" if str(pos.get("order_id", "")).startswith("SYNC_") else "BOT_LIVE"),
        }

        with self._lock:
            st = self._load()
            st["open_records"][pos_id] = rec
            # Keep open_records bounded (max 100 recent open snapshots)
            if len(st["open_records"]) > 100:
                keys_sorted = sorted(
                    st["open_records"].keys(),
                    key=lambda k: float((st["open_records"][k] or {}).get("opened_ts") or 0.0),
                )
                for old_k in keys_sorted[:-100]:
                    st["open_records"].pop(old_k, None)
            self._save(st)
        return rec

    def lookup_open_record(self, pos_id: Optional[str] = None, pair: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Recover persisted entry snapshot (including feature_vector/setup/regime) even after restart."""
        with self._lock:
            st = self._load()
            opens = st.get("open_records") or {}
            if pos_id and str(pos_id) in opens:
                return dict(opens[str(pos_id)])
            if pair:
                pair_u = str(pair).upper()
                matches = [
                    r for r in opens.values()
                    if isinstance(r, dict) and str(r.get("binance_pair") or "").upper() == pair_u
                ]
                if matches:
                    matches.sort(key=lambda r: float(r.get("opened_ts") or 0.0), reverse=True)
                    return dict(matches[0])
        return None

    def record_close(
        self,
        pos: Dict[str, Any],
        exit_price: float,
        exit_reason: str,
        gross_pnl_usd: float,
        fee_usd: float,
        funding_usd: float = 0.0,
        net_pnl_usd: Optional[float] = None,
        source: str = "BOT_CLOSE",
        binance_order_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Record every closed trade with post-mortem lessons; deduplicated by trade_id / order_id."""
        pos_id = str(pos.get("id") or f"CLS_{pos.get('binance_pair', 'UNK')}_{int(time.time()*1000)}")
        pair = str(pos.get("binance_pair") or pos.get("symbol", "").replace("-USD", "USDT")).upper()
        sym = str(pos.get("symbol") or pair.replace("USDT", "-USD")).upper()

        with self._lock:
            st = self._load()
            # Deduplicate
            if any(t.get("trade_id") == pos_id for t in st["closed_trades"]):
                existing = next(t for t in st["closed_trades"] if t.get("trade_id") == pos_id)
                return existing

            open_snap = st["open_records"].pop(pos_id, None)
            if open_snap is None and pair:
                # Match most recent open snapshot for same symbol if ID changed after auto-import
                cand_keys = [
                    k for k, v in st["open_records"].items()
                    if isinstance(v, dict) and str(v.get("binance_pair") or "").upper() == pair
                ]
                if cand_keys:
                    cand_keys.sort(key=lambda k: float(st["open_records"][k].get("opened_ts") or 0.0), reverse=True)
                    open_snap = st["open_records"].pop(cand_keys[0], None)

            open_snap = open_snap or {}
            entry_px = float(pos.get("entry_price") or open_snap.get("entry_price") or 0.0)
            sl_px = float(pos.get("init_stop_loss") or pos.get("stop_loss") or open_snap.get("stop_loss") or 0.0)
            lev = int(pos.get("leverage") or open_snap.get("leverage") or 20)
            margin_usd = float(
                pos.get("initial_position_size_usd")
                or pos.get("position_size_usd")
                or open_snap.get("margin_usd")
                or 1.0
            )
            net_v = float(net_pnl_usd) if net_pnl_usd is not None else (float(gross_pnl_usd) - float(fee_usd) - float(funding_usd))
            sl_pct = (abs(entry_px - sl_px) / entry_px * 100.0) if (entry_px > 0 and sl_px > 0) else float(open_snap.get("sl_pct") or 1.2)
            risk_usd = max(0.02, margin_usd * lev * max(0.0045, sl_pct / 100.0))
            r_mult = round(net_v / risk_usd, 3)

            now_ts = time.time()
            opened_ts = float(pos.get("opened_ts") or open_snap.get("opened_ts") or now_ts)
            hold_min = round(max(0.0, (now_ts - opened_ts) / 60.0), 1)
            dir_s = str(pos.get("direction") or open_snap.get("direction") or "LONG").upper()
            move_pct = 0.0
            if entry_px > 0 and exit_price > 0:
                move_pct = ((exit_price - entry_px) / entry_px * 100.0) * (1.0 if dir_s == "LONG" else -1.0)

            outcome = "WIN" if net_v > 0.005 else ("LOSS" if net_v < -0.005 else "SCRATCH")
            rec = {
                "trade_id": pos_id,
                "symbol": sym,
                "binance_pair": pair,
                "direction": dir_s,
                "setup_name": str(pos.get("setup_name") or open_snap.get("setup_name") or "AI_SETUP"),
                "regime": str(pos.get("regime") or open_snap.get("regime") or "NORMAL").upper(),
                "entry_price": round(entry_px, 6),
                "exit_price": round(float(exit_price or 0.0), 6),
                "sl_pct": round(sl_pct, 3),
                "move_pct": round(move_pct, 3),
                "leverage": lev,
                "margin_usd": round(margin_usd, 4),
                "gross_pnl_usd": round(float(gross_pnl_usd), 4),
                "fee_usd": round(float(fee_usd), 4),
                "funding_usd": round(float(funding_usd), 4),
                "net_pnl_usd": round(net_v, 4),
                "r_multiple_net": r_mult,
                "max_r_reached": round(float(pos.get("max_r_reached") or 0.0), 3),
                "hold_minutes": hold_min,
                "exit_reason": str(exit_reason or "CLOSED"),
                "outcome": outcome,
                "confidence_score": float(pos.get("confidence_score") or open_snap.get("confidence_score") or 0.0),
                "source": source,
                "closed_ts": now_ts,
                "closed_at": pos.get("closed_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            }
            rec["lessons"] = _derive_trade_lessons(rec)

            st["closed_trades"].append(rec)
            st["closed_trades"] = st["closed_trades"][-self.max_closed:]
            if binance_order_id is not None:
                oid_s = str(binance_order_id)
                if oid_s not in st["synced_binance_order_ids"]:
                    st["synced_binance_order_ids"].append(oid_s)
                    st["synced_binance_order_ids"] = st["synced_binance_order_ids"][-1000:]
            self._save(st)
            return rec

    def sync_binance_closed_history(self, bn_client, days: int = 14, min_interval_sec: float = 1800.0) -> int:
        """
        Auto-backfill any real closed Binance Futures trades not yet in AI memory
        (e.g. manual closes on Binance app, offline closes, or pre-upgrade history).
        Deduplicated strictly by closing orderId so zero double-counting occurs.
        """
        if bn_client is None or not hasattr(bn_client, "get_income_history") or not hasattr(bn_client, "get_user_trades"):
            return 0

        now = time.time()
        with self._lock:
            st_check = self._load()
            if (now - float(st_check.get("last_binance_sync_ts") or 0.0)) < float(min_interval_sec):
                return 0
            known_oids = set(str(x) for x in (st_check.get("synced_binance_order_ids") or []))

        start_ms = int((now - days * 86400.0) * 1000)
        try:
            inc = bn_client.get_income_history(limit=500, start_time=start_ms)
        except Exception as exc:
            logger.debug("AI memory Binance income sync skipped: %s", exc)
            return 0
        if not isinstance(inc, list) or not inc:
            return 0

        symbols = sorted({str(x.get("symbol") or "").upper() for x in inc if x.get("symbol") and x.get("incomeType") == "REALIZED_PNL"})
        ingested = 0
        for sym in symbols:
            try:
                fills = bn_client.get_user_trades(sym, limit=100, start_time=start_ms)
            except Exception:
                continue
            if not isinstance(fills, list) or not fills:
                continue

            # Group fills by orderId
            by_oid: Dict[str, Dict[str, Any]] = {}
            for tr in fills:
                oid = str(tr.get("orderId") or "")
                if not oid:
                    continue
                g = by_oid.setdefault(oid, {
                    "oid": oid,
                    "time": int(tr.get("time", 0) or 0),
                    "side": str(tr.get("side") or "").upper(),
                    "qty": 0.0,
                    "quote": 0.0,
                    "rpnl": 0.0,
                    "comm": 0.0,
                })
                q = float(tr.get("qty", 0) or 0)
                p = float(tr.get("price", 0) or 0)
                g["qty"] += q
                g["quote"] += q * p
                g["rpnl"] += float(tr.get("realizedPnl", 0) or 0)
                g["comm"] += float(tr.get("commission", 0) or 0)

            ordered = sorted(by_oid.values(), key=lambda x: x["time"])
            last_open = None
            for o in ordered:
                if abs(o["rpnl"]) < 1e-8:
                    last_open = o
                    continue
                oid_key = f"{sym}:{o['oid']}"
                if oid_key in known_oids or o["oid"] in known_oids:
                    continue
                exit_px = (o["quote"] / o["qty"]) if o["qty"] > 0 else 0.0
                entry_px = (last_open["quote"] / last_open["qty"]) if (last_open and last_open["qty"] > 0) else exit_px
                dir_s = "SHORT" if o["side"] == "BUY" else "LONG"
                notional = o["quote"] if o["quote"] > 0 else (last_open["quote"] if last_open else 20.0)
                est_margin = max(0.5, notional / 20.0)
                open_comm = last_open["comm"] if last_open else o["comm"]
                total_fee = o["comm"] + open_comm
                opened_ts = (last_open["time"] / 1000.0) if last_open else (o["time"] / 1000.0)
                close_ts_str = datetime.fromtimestamp(o["time"] / 1000.0, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

                pos_synth = {
                    "id": f"BN_HIST_{sym}_{o['oid']}",
                    "symbol": sym.replace("USDT", "-USD"),
                    "binance_pair": sym,
                    "direction": dir_s,
                    "setup_name": "BINANCE_LIVE_HISTORY",
                    "regime": "LIVE_SYNCED",
                    "entry_price": entry_px,
                    "leverage": 20,
                    "position_size_usd": est_margin,
                    "opened_ts": opened_ts,
                    "closed_at": close_ts_str,
                }
                self.record_close(
                    pos_synth,
                    exit_price=exit_px,
                    exit_reason="BINANCE_WIN" if (o["rpnl"] - total_fee) > 0 else "BINANCE_LOSS",
                    gross_pnl_usd=o["rpnl"],
                    fee_usd=total_fee,
                    funding_usd=0.0,
                    net_pnl_usd=o["rpnl"] - total_fee,
                    source="BINANCE_BACKFILL",
                    binance_order_id=oid_key,
                )
                known_oids.add(oid_key)
                ingested += 1

        with self._lock:
            st_done = self._load()
            st_done["last_binance_sync_ts"] = now
            self._save(st_done)
        return ingested

    def build_prompt_memory_context(
        self,
        symbol: str,
        regime: str = "NORMAL",
        direction: Optional[str] = None,
        setup_name: Optional[str] = None,
        active_positions: Optional[Sequence[Dict[str, Any]]] = None,
        knn_note: Optional[str] = None,
    ) -> str:
        """
        Build a compact (~100-140 token) learning brief injected into Layer 2 & Layer 5
        AI prompts so the LLM actively learns from ALL opened & closed trades.
        """
        with self._lock:
            st = self._load()
            closed = st.get("closed_trades") or []
            summary = st.get("stats_summary") or self._recompute_summary(st)

        parts: List[str] = []
        sym_u = str(symbol or "").upper()
        pair_u = sym_u.replace("-USD", "USDT")

        if closed:
            recent = closed[-20:]
            rw = sum(1 for t in recent if t.get("outcome") == "WIN")
            rl = sum(1 for t in recent if t.get("outcome") == "LOSS")
            r_wr = round(rw / max(1, rw + rl) * 100.0, 0)
            parts.append(
                f"AI_MEMORY(last {len(recent)}): {rw}W/{rl}L (WR {r_wr:.0f}%, PF {summary.get('profit_factor', 0):.2f}, streak {summary.get('streak', '0')})"
            )

            # Symbol-specific history
            sym_stats = (summary.get("by_symbol") or {}).get(sym_u) or (summary.get("by_symbol") or {}).get(pair_u)
            if sym_stats:
                sw, sl = sym_stats["w"], sym_stats["l"]
                caution = " [CAUTION: poor history on this coin, require extra confluence]" if (sl >= 2 and sl > sw) else ""
                parts.append(f"ThisCoin({sym_u}): {sw}W/{sl}L net=${sym_stats['net_usd']:+.2f}{caution}")

            # Direction x Regime history
            if direction:
                dr_key = f"{str(direction).upper()}@{str(regime).upper()}"
                dr_st = (summary.get("by_dir_regime") or {}).get(dr_key)
                if dr_st and (dr_st["w"] + dr_st["l"]) >= 2:
                    parts.append(f"{dr_key}: {dr_st['w']}W/{dr_st['l']}L (${dr_st['net_usd']:+.2f})")

            # Setup history
            if setup_name:
                su_st = (summary.get("by_setup") or {}).get(str(setup_name).upper())
                if su_st and (su_st["w"] + su_st["l"]) >= 2:
                    parts.append(f"Setup({setup_name}): {su_st['w']}W/{su_st['l']}L")

            # Recent losing lessons (avoid repeating!)
            loss_lessons: List[str] = []
            for t in reversed(closed[-12:]):
                if t.get("outcome") == "LOSS":
                    for ls in (t.get("lessons") or []):
                        tag = ls.split(":")[0]
                        if tag not in loss_lessons:
                            loss_lessons.append(tag)
                if len(loss_lessons) >= 3:
                    break
            if loss_lessons:
                parts.append(f"AvoidPastErrors: {', '.join(loss_lessons)}")
        else:
            parts.append("AI_MEMORY: 0 closed trades yet (apply strict high-conviction rules)")

        if knn_note:
            parts.append(f"kNN: {str(knn_note)[:120]}")

        if active_positions:
            open_str = ", ".join(
                f"{p.get('symbol') or p.get('binance_pair')}({p.get('direction')})"
                for p in active_positions
                if isinstance(p, dict) and p.get("status", "OPEN") == "OPEN"
            )
            if open_str:
                parts.append(f"OpenNow: {open_str}")

        return " | ".join(parts)

    def get_summary_report(self) -> Dict[str, Any]:
        """Return full memory & learning stats for Telegram /memory and UI."""
        with self._lock:
            st = self._load()
            summary = self._recompute_summary(st)
            return {
                "summary": summary,
                "open_records": list((st.get("open_records") or {}).values())[-10:],
                "recent_closed": (st.get("closed_trades") or [])[-10:],
                "updated_at": st.get("updated_at"),
            }


def get_trade_memory_engine(memory_path: Optional[str] = None) -> AITradeMemoryEngine:
    return AITradeMemoryEngine(memory_path=memory_path or DEFAULT_AI_MEMORY_PATH)
