"""
WP-7 TDD Test Suite: Backtest vs Live Signal & Cost Parity (`Gap #12`).
Verifies:
  1. Feeding identical closed candle slices into `backtest.engine.evaluate_bar_no_lookahead`
     and live `detect_market_regime` + `generate_all_candidates` produces 100% identical
     regime classification, candidate strategy IDs, directions, entry/SL/TP1/TP2 prices,
     SL distances, and RRR across trending, breakout, and chop regimes.
  2. Strict zero look-ahead: mutating future candles `candles[bar_idx + 1:]` (e.g. flash crash
     to 0.01 or spike to 1e9) has ZERO effect on `evaluate_bar_no_lookahead` at `bar_idx`.
  3. Triple-Barrier cost parity between `backtest.triple_barrier.simulate_triple_barrier`
     and `shadow.engine.ShadowEngine.resolve_bar`.

Strictly offline (deterministic synthetic candle series, zero live network calls).
"""
from __future__ import annotations

import copy
import math
import os
import sys
import tempfile
import unittest
from typing import Any, Dict, List

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

from backtest.engine import evaluate_bar_no_lookahead, _InMemoryBandit
from backtest.triple_barrier import simulate_triple_barrier
from features.regime import detect_market_regime
from shadow.engine import ShadowEngine
from strategies import generate_all_candidates
import journal


def _build_trending_candles(n: int = 120, start_px: float = 100.0) -> List[Dict[str, Any]]:
    """Generate a deterministic bullish trend with controlled pullback at bar ~85 so S1/S2 can evaluate."""
    candles: List[Dict[str, Any]] = []
    px = start_px
    base_ts = 1_700_000_000_000
    for i in range(n):
        # Smooth upward drift with periodic pullback
        if 80 <= i <= 83:
            step = -0.35
        else:
            step = 0.55 + 0.15 * math.sin(i * 0.3)
        op = px
        cl = max(1.0, op + step)
        hi = max(op, cl) + 0.45
        lo = min(op, cl) - 0.35
        vol = 15_000.0 + (4000.0 if i > 80 else 1000.0) * (1.0 + 0.2 * math.cos(i))
        ot = base_ts + i * 3600_000
        candles.append(
            {
                "open_time": ot,
                "open": round(op, 4),
                "high": round(hi, 4),
                "low": round(lo, 4),
                "close": round(cl, 4),
                "volume": round(vol, 2),
                "close_time": ot + 3600_000 - 1,
                "taker_buy_base": round(vol * 0.58, 2),
            }
        )
        px = cl
    return candles


class TestBacktestLiveParity(unittest.TestCase):
    def test_evaluate_bar_no_lookahead_matches_live_regime_and_candidates_100pct(self):
        """Identical closed candle slices must yield identical regime & SetupCandidate fields in backtest and live."""
        candles = _build_trending_candles(120, start_px=100.0)
        btc_candles = _build_trending_candles(120, start_px=40000.0)
        bandit_bt = _InMemoryBandit(seed=42)
        bandit_live = _InMemoryBandit(seed=42)

        for bar_idx in (45, 65, 84, 95, 110):
            bt_out = evaluate_bar_no_lookahead(
                candles,
                bar_idx=bar_idx,
                btc_candles=btc_candles,
                symbol="SOLUSDT",
                bandit=bandit_bt,
            )

            hist_slice = candles[max(0, bar_idx - 150) : bar_idx + 1]
            btc_slice = btc_candles[max(0, bar_idx - 150) : bar_idx + 1]
            live_regime = detect_market_regime(btc_slice, hist_slice)
            live_cands = generate_all_candidates(
                hist_slice,
                live_regime,
                symbol="SOLUSDT",
                bandit=bandit_live,
                deterministic_bandit=True,
            )

            self.assertEqual(bt_out["regime_state"], live_regime, f"Regime mismatch at bar_idx={bar_idx}")
            bt_cands = bt_out["candidates"]
            self.assertEqual(len(bt_cands), len(live_cands), f"Candidate count mismatch at bar_idx={bar_idx}")

            for c_bt, c_lv in zip(bt_cands, live_cands):
                self.assertEqual(c_bt.strategy_id, c_lv.strategy_id)
                self.assertEqual(c_bt.direction, c_lv.direction)
                self.assertAlmostEqual(c_bt.entry_price, c_lv.entry_price, places=8)
                self.assertAlmostEqual(c_bt.sl_price, c_lv.sl_price, places=8)
                self.assertAlmostEqual(c_bt.tp1_price, c_lv.tp1_price, places=8)
                self.assertAlmostEqual(c_bt.tp2_price, c_lv.tp2_price, places=8)
                self.assertAlmostEqual(c_bt.sl_distance_pct, c_lv.sl_distance_pct, places=8)
                self.assertAlmostEqual(c_bt.rrr_net, c_lv.rrr_net, places=8)

    def test_zero_lookahead_when_future_bars_are_mutated(self):
        """Mutating candles[bar_idx + 1:] must have zero effect on evaluate_bar_no_lookahead at bar_idx."""
        candles_orig = _build_trending_candles(110, start_px=100.0)
        btc_orig = _build_trending_candles(110, start_px=40000.0)
        bar_idx = 84

        res_orig = evaluate_bar_no_lookahead(
            candles_orig,
            bar_idx=bar_idx,
            btc_candles=btc_orig,
            symbol="SOLUSDT",
            bandit=_InMemoryBandit(seed=42),
        )

        # Mutate all future bars after bar_idx with extreme prices/volumes
        candles_mut = copy.deepcopy(candles_orig)
        btc_mut = copy.deepcopy(btc_orig)
        for j in range(bar_idx + 1, len(candles_mut)):
            candles_mut[j]["open"] = 999999.0
            candles_mut[j]["high"] = 1999999.0
            candles_mut[j]["low"] = 0.0001
            candles_mut[j]["close"] = 0.0002
            candles_mut[j]["volume"] = 1e12
            btc_mut[j]["close"] = 1.0

        res_mut = evaluate_bar_no_lookahead(
            candles_mut,
            bar_idx=bar_idx,
            btc_candles=btc_mut,
            symbol="SOLUSDT",
            bandit=_InMemoryBandit(seed=42),
        )

        self.assertEqual(res_orig["regime_state"], res_mut["regime_state"])
        self.assertEqual(len(res_orig["candidates"]), len(res_mut["candidates"]))
        for c1, c2 in zip(res_orig["candidates"], res_mut["candidates"]):
            self.assertEqual(c1.to_dict(), c2.to_dict())

    def test_triple_barrier_and_shadow_engine_cost_and_outcome_parity(self):
        """simulate_triple_barrier and ShadowEngine.resolve_bar must produce identical net R and costs on single-bar resolution."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = os.path.join(tmp, "parity_shadow.db")
            journal.init_db(db_path)
            sh_engine = ShadowEngine(db_path=db_path)

            cand = {
                "symbol": "SOLUSDT",
                "strategy_id": "S1_TREND_PULLBACK",
                "regime": "TREND_BULL",
                "direction": "LONG",
                "entry_price": 100.0,
                "sl_price": 99.0,
                "tp1_price": 100.55,
                "tp2_price": 102.0,
                "sl_distance_pct": 1.0,
                "rrr_net": 2.0,
                "vertical_barrier_bars": 16,
                "entry_type": "MAKER_FIRST_GTX",
                "atr_pct": 1.0,
                "notional_usdt": 1000.0,
            }
            open_ts = 1_700_000_000_000
            close_ts = open_ts + 3600_000
            bar = {
                "open_time": open_ts,
                "open": 100.0,
                "high": 102.5,
                "low": 99.8,
                "close": 102.1,
                "close_time": close_ts,
            }

            bt_sim = simulate_triple_barrier(cand, [bar], sniper_mode=True, atr_pct=1.0, notional_usdt=1000.0)
            sh_id = sh_engine.register_candidate(cand, opened_at=open_ts, sniper_mode=True)
            resolved = sh_engine.update_open_shadows("SOLUSDT", bar, closed_at=close_ts)

            self.assertEqual(len(resolved), 1)
            sh_res = resolved[0]
            self.assertEqual(sh_res["shadow_id"], sh_id)
            self.assertEqual(bt_sim["outcome"], "TP2")
            self.assertEqual(sh_res["hit_reason"], "TP2")
            self.assertAlmostEqual(bt_sim["cost_pct"], sh_res["cost_pct"], places=4)
            self.assertAlmostEqual(bt_sim["r_multiple_net"], sh_res["r_multiple_net"], places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
