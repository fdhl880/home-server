"""
WP-6 TDD Test Suite: Backtest/Shadow Realism, Advisory Strategy Gate (Decision 2.B),
Historical Funding & Volatility Slippage, Genuine CSCV/PBO, Bandit OOS Freeze,
Shadow Cost Parity & Promotion Hardening, and $20 Account Ruin Monte Carlo Simulator.

Strictly offline (synthetic/fixture candles & mocked HTTP only, ZERO network calls).
"""
from __future__ import annotations

import csv
import gc
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)


def _make_trend_candles(
    n_bars: int = 420,
    start_px: float = 100.0,
    start_ms: int = 1700000000000,
    step_ms: int = 3_600_000,
    seed: int = 11,
) -> list[dict]:
    """Generate deterministic synthetic candles with trending + pullback + mean-revert phases."""
    rng = np.random.default_rng(seed)
    candles = []
    px = float(start_px)
    for i in range(n_bars):
        phase = (i // 70) % 3
        if phase == 0:
            # Bullish trend with periodic pullbacks
            drift = -0.004 if (i % 7 == 5) else 0.0038
        elif phase == 1:
            # Bearish trend with periodic bounces
            drift = 0.004 if (i % 7 == 5) else -0.0035
        else:
            # Oscillating range
            drift = 0.005 if (i % 2 == 0) else -0.0048
        noise = float(rng.normal(0.0, 0.0012))
        op = px
        cl = max(1.0, op * (1.0 + drift + noise))
        hi = max(op, cl) * (1.0 + abs(float(rng.normal(0.0025, 0.001))))
        lo = min(op, cl) * (1.0 - abs(float(rng.normal(0.0025, 0.001))))
        vol = 1000.0 + (450.0 if i % 7 == 6 else 100.0)
        tb_ratio = 0.68 if cl >= op else 0.32
        ot = start_ms + i * step_ms
        candles.append({
            "open_time": ot,
            "open": round(op, 6),
            "high": round(hi, 6),
            "low": round(lo, 6),
            "close": round(cl, 6),
            "volume": round(vol, 4),
            "close_time": ot + step_ms - 1,
            "taker_buy_base": round(vol * tb_ratio, 4),
            "taker_buy_quote": round(vol * tb_ratio * cl, 4),
        })
        px = cl
    return candles


def _write_kline_csv(path: str, candles: list[dict]) -> None:
    from backtest.fetch import CSV_COLUMNS
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for c in candles:
            w.writerow([
                c["open_time"], c["open"], c["high"], c["low"], c["close"], c["volume"],
                c["close_time"], round(c["volume"] * c["close"], 4), 100,
                c.get("taker_buy_base", c["volume"] * 0.5),
                c.get("taker_buy_quote", c["volume"] * c["close"] * 0.5),
            ])


def _write_funding_csv(path: str, symbol: str, start_ms: int, count: int, rate: float = 0.0001) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["funding_time", "symbol", "funding_rate", "mark_price"])
        for i in range(count):
            ft = start_ms + i * 8 * 3_600_000
            w.writerow([ft, symbol, f"{rate:.8f}", "100.0"])


class TestConfigAndDecision2B(unittest.TestCase):
    def test_trading_config_decision_2b_and_mandates_intact(self):
        import config_schema
        cfg = config_schema.load_trading_config()
        self.assertIn("enforce_backtest_gate", cfg)
        self.assertFalse(cfg["enforce_backtest_gate"])
        self.assertEqual(cfg["fixed_leverage"], 20)
        self.assertEqual(cfg["sizing_mode"], "ALL_IN")
        self.assertAlmostEqual(cfg["all_in_balance_fraction"], 0.95)
        self.assertEqual(cfg["margin_type"], "ISOLATED")


class TestHistoricalFetch365AndFunding(unittest.TestCase):
    def test_fetch_all_symbols_365d_1h_15m_and_funding_offline(self):
        import argparse
        from backtest import fetch

        class FakeResp:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self._payload = payload

            def json(self):
                return self._payload

        now_ms = int(1_795_000_000_000)

        def fake_get(url, params=None, timeout=None):
            params = params or {}
            if "fundingRate" in url:
                st = int(params.get("startTime", now_ms - 86_400_000))
                # Return 1000 records on first page to exercise 365-day funding pagination (>1000 entries)
                count = 1000 if st < (now_ms - 100 * 28_800_000) else 95
                rows = [
                    {"symbol": params["symbol"], "fundingTime": st + i * 28_800_000, "fundingRate": "0.00025000", "markPrice": "100.0"}
                    for i in range(count)
                    if (st + i * 28_800_000) <= now_ms
                ]
                return FakeResp(200, rows)
            iv = params.get("interval", "1h")
            step = fetch.INTERVAL_MS.get(iv, 3_600_000)
            st = int(params.get("startTime", now_ms - 10 * step))
            lim = min(int(params.get("limit", 100)), 1500)
            bars = []
            for i in range(lim):
                ot = st + i * step
                ct = ot + step - 1
                if ct > now_ms:
                    break
                bars.append([ot, "100.0", "101.0", "99.5", "100.5", "500.0", ct, "50250.0", 40, "260.0", "26130.0", "0"])
            return FakeResp(200, bars)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            with patch("backtest.fetch.requests.get", side_effect=fake_get), \
                 patch("backtest.fetch.time.time", return_value=now_ms / 1000.0), \
                 patch("backtest.fetch.time.sleep", return_value=None):
                res = fetch.fetch_all_symbols(
                    symbols=["BTCUSDT", "SOLUSDT"],
                    days=365,
                    intervals=("1h", "15m"),
                    include_funding=True,
                    data_dir=tmp,
                    sleep_sec=0.0,
                )

            for sym in ("BTCUSDT", "SOLUSDT"):
                self.assertIn(sym, res)
                self.assertTrue(os.path.exists(res[sym]["1h"]))
                self.assertTrue(os.path.exists(res[sym]["15m"]))
                self.assertTrue(os.path.exists(res[sym]["funding"]))
                f_map = fetch.load_funding_history(res[sym]["funding"])
                self.assertGreater(len(f_map), 1000)
                first_rate = next(iter(f_map.values()))
                self.assertAlmostEqual(first_rate, 0.00025, places=7)

        # Verify CLI parser default days >= 365
        parser = fetch.build_cli_parser() if hasattr(fetch, "build_cli_parser") else None
        self.assertIsNotNone(parser, "Expected build_cli_parser() helper exposing default CLI flags")
        args = parser.parse_args([])
        self.assertGreaterEqual(args.days, 365)


class TestTripleBarrierRealism(unittest.TestCase):
    def _cand(self, direction="LONG", entry=100.0, sl=99.0, tp2=102.0, entry_type="MAKER_FIRST_GTX"):
        from strategies.base import build_sniper_candidate
        return build_sniper_candidate(
            strategy_id="S1_TREND_PULLBACK",
            direction=direction,
            entry_price=entry,
            raw_sl_price=sl,
            raw_tp2_price=tp2,
            vertical_barrier_bars=12,
            structural_anchor_desc="WP6 test",
            confluence_tags=["TEST"],
            entry_type=entry_type,
        )

    def test_historical_funding_lookup_directional(self):
        from backtest.triple_barrier import simulate_triple_barrier

        # 8h boundary at 1_700_006_400_000 (divisible by 28_800_000: 1700006400000 / 28800000 = 59028.0)
        b_ts = 59028 * 28_800_000
        candles = [
            {"open_time": b_ts - 1_800_000, "close_time": b_ts + 1_800_000 - 1, "open": 100.0, "high": 100.3, "low": 99.8, "close": 100.1},
            {"open_time": b_ts + 1_800_000, "close_time": b_ts + 5_400_000 - 1, "open": 100.1, "high": 102.2, "low": 100.0, "close": 102.1},
        ]
        # High positive funding 0.0010 (0.10%) at b_ts -> LONG pays +0.10%, SHORT receives -0.10%
        funding_series = {b_ts: 0.0010}

        cand_long = self._cand(direction="LONG", entry=100.0, sl=99.0, tp2=102.0)
        res_long = simulate_triple_barrier(cand_long, candles, sniper_mode=True, funding_series=funding_series)
        self.assertGreaterEqual(res_long["funding_events"], 1)
        self.assertAlmostEqual(res_long["funding_cost_pct"], 0.10, places=4)

        cand_short = self._cand(direction="SHORT", entry=100.0, sl=101.0, tp2=98.0)
        candles_short = [
            {"open_time": b_ts - 1_800_000, "close_time": b_ts + 1_800_000 - 1, "open": 100.0, "high": 100.2, "low": 99.7, "close": 99.9},
            {"open_time": b_ts + 1_800_000, "close_time": b_ts + 5_400_000 - 1, "open": 99.9, "high": 100.0, "low": 97.8, "close": 97.9},
        ]
        res_short = simulate_triple_barrier(cand_short, candles_short, sniper_mode=True, funding_series=funding_series)
        self.assertAlmostEqual(res_short["funding_cost_pct"], -0.10, places=4)
        self.assertLess(res_short["cost_pct"], res_long["cost_pct"])

    def test_volatility_and_size_scaled_slippage(self):
        from backtest.triple_barrier import simulate_triple_barrier

        cand = self._cand(direction="LONG", entry=100.0, sl=99.0, tp2=102.0, entry_type="IMMEDIATE_IOC")
        calm_bars = [
            {"open_time": 1000, "close_time": 2000, "open": 100.0, "high": 100.2, "low": 99.9, "close": 100.1},
            {"open_time": 2000, "close_time": 3000, "open": 100.1, "high": 100.2, "low": 99.9, "close": 100.0},
        ]
        wild_bars = [
            {"open_time": 1000, "close_time": 2000, "open": 100.0, "high": 101.9, "low": 99.1, "close": 100.1},
            {"open_time": 2000, "close_time": 3000, "open": 100.1, "high": 101.9, "low": 99.1, "close": 100.0},
        ]
        res_calm = simulate_triple_barrier(cand, calm_bars, atr_pct=0.4, notional_usdt=400.0)
        res_wild = simulate_triple_barrier(cand, wild_bars, atr_pct=2.0, notional_usdt=400.0)
        res_big = simulate_triple_barrier(cand, wild_bars, atr_pct=2.0, notional_usdt=50000.0)

        self.assertGreater(res_wild["slippage_pct"], res_calm["slippage_pct"])
        self.assertGreater(res_big["slippage_pct"], res_wild["slippage_pct"])

    def test_wick_and_gap_stop_slippage_bounded_by_excursion(self):
        from backtest.triple_barrier import simulate_triple_barrier

        cand = self._cand(direction="LONG", entry=100.0, sl=99.0, tp2=102.0, entry_type="IMMEDIATE_IOC")

        # Wick overshoot past SL (99.0 -> low 96.5): exit worse than 99.0, bounded >= 96.5
        wick_bar = [{"open_time": 1000, "close_time": 2000, "open": 100.0, "high": 100.1, "low": 96.5, "close": 98.5}]
        res_wick = simulate_triple_barrier(cand, wick_bar, stop_slip_fraction=0.10)
        self.assertEqual(res_wick["outcome"], "SL")
        self.assertLess(res_wick["exit_price"], 99.0)
        self.assertGreaterEqual(res_wick["exit_price"], 96.5)

        # Gap open past SL (open 98.0 < SL 99.0, low 97.2)
        gap_bar = [{"open_time": 1000, "close_time": 2000, "open": 98.0, "high": 98.2, "low": 97.2, "close": 97.5}]
        res_gap = simulate_triple_barrier(cand, gap_bar, stop_slip_fraction=0.10)
        self.assertEqual(res_gap["outcome"], "SL")
        self.assertLessEqual(res_gap["exit_price"], 98.0)
        self.assertGreaterEqual(res_gap["exit_price"], 97.2)

    def test_maker_first_gtx_runaway_no_fill_and_taker_fallback(self):
        from backtest.triple_barrier import simulate_triple_barrier

        cand = self._cand(direction="LONG", entry=100.0, sl=99.0, tp2=102.0, entry_type="MAKER_FIRST_GTX")
        # Price immediately runs away upward: low=100.15 > entry=100.0
        runaway_bars = [
            {"open_time": 1000, "close_time": 2000, "open": 100.20, "high": 102.2, "low": 100.15, "close": 102.1},
        ]
        res_nofill = simulate_triple_barrier(cand, runaway_bars, maker_fallback_to_taker=False)
        self.assertEqual(res_nofill["outcome"], "MAKER_NO_FILL")
        self.assertEqual(res_nofill["r_multiple_net"], 0.0)
        self.assertEqual(res_nofill["entry_fill_mode"], "NO_FILL")

        res_fallback = simulate_triple_barrier(cand, runaway_bars, maker_fallback_to_taker=True)
        self.assertEqual(res_fallback["entry_fill_mode"], "TAKER_FALLBACK")
        self.assertEqual(res_fallback["entry_fee_pct"], 0.05)  # paid taker fee on chase!
        self.assertGreater(res_fallback["actual_entry_price"], 100.0)


class TestCpcvPboAndEngineGate(unittest.TestCase):
    def test_compute_cpcv_pbo_separates_persistent_vs_overfit(self):
        from backtest.cpcv import compute_cpcv_pbo

        rng = np.random.default_rng(77)
        t_len = 160
        # Persistent winner in col 0, mediocre/negative in cols 1..4
        m_good = np.column_stack([
            rng.normal(0.35, 0.25, size=t_len),
            rng.normal(-0.05, 0.30, size=t_len),
            rng.normal(-0.08, 0.30, size=t_len),
            rng.normal(0.00, 0.30, size=t_len),
        ])
        pbo_good = compute_cpcv_pbo(m_good, n_splits=8, purge_bars=2, embargo_bars=1)
        self.assertLess(pbo_good["pbo"], 0.25)
        self.assertGreater(pbo_good["n_combinations"], 10)

        # Overfit trial: col 0 shines ONLY in first half (IS) and collapses in second half (OOS)
        # While col 1 is reversed -> IS picks winner that underperforms OOS median!
        half = t_len // 2
        col0 = np.concatenate([np.full(half, 0.45), np.full(half, -0.45)]) + rng.normal(0.0, 0.05, size=t_len)
        col1 = np.concatenate([np.full(half, -0.40), np.full(half, 0.40)]) + rng.normal(0.0, 0.05, size=t_len)
        col2 = rng.normal(0.0, 0.05, size=t_len)
        col3 = rng.normal(0.0, 0.05, size=t_len)
        m_overfit = np.column_stack([col0, col1, col2, col3])
        pbo_bad = compute_cpcv_pbo(m_overfit, n_splits=2, purge_bars=0, embargo_bars=0)
        # Across 2-split IS/OOS inversion, IS winner flips to worst in OOS -> PBO = 1.0
        self.assertGreaterEqual(pbo_bad["pbo"], 0.50)

    def test_bandit_frozen_in_oos_and_honest_n_trials(self):
        from backtest.engine import run_symbol_walk_forward
        from backtest.cpcv import deflated_sharpe_ratio
        from strategies.bandit_allocator import ContextualThompsonBandit

        candles = _make_trend_candles(n_bars=260, seed=21)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            b_path = os.path.join(tmp, "bandit.json")
            bandit = ContextualThompsonBandit(state_path=b_path, seed=99)
            initial_arms = dict(bandit.arms)

            # Spy on _FrozenBanditProxy.update to confirm OOS bars never mutate frozen posteriors
            from backtest import engine as bt_engine
            orig_proxy_update = bt_engine._FrozenBanditProxy.update
            proxy_update_calls = []

            def spy_proxy_update(self_proxy, strategy_id, regime="UNKNOWN", r_net=None, won=None):
                proxy_update_calls.append((strategy_id, regime, r_net))
                return orig_proxy_update(self_proxy, strategy_id, regime=regime, r_net=r_net, won=won)

            with patch.object(bt_engine._FrozenBanditProxy, "update", spy_proxy_update):
                res = run_symbol_walk_forward(
                    symbol="BTCUSDT",
                    candles=candles,
                    btc_candles=candles,
                    sniper_mode=True,
                    bandit=bandit,
                    freeze_oos=True,
                )

            self.assertEqual(proxy_update_calls, [])
            # Caller bandit state must NOT be mutated by OOS bars (or dirty disk writes)
            self.assertEqual(bandit.arms, initial_arms)
            self.assertFalse(os.path.exists(b_path))

            # Verify OOS trades did not rely on mutating OOS bandit updates
            self.assertIn("oos_trades", res)

        # Honest trial count reduces DSR vs naive K=4
        r_vals = [0.55, -0.8, 1.5, 0.55, -0.7, 0.55, 1.6, -0.8, 0.55, 0.55, 1.4, -0.7] * 3
        dsr_4 = deflated_sharpe_ratio(r_vals, num_trials=4)["dsr"]
        dsr_40 = deflated_sharpe_ratio(r_vals, num_trials=40)["dsr"]
        self.assertLess(dsr_40, dsr_4)

    def test_run_backtest_emits_strategy_gate_json_and_breakdowns(self):
        from backtest.engine import run_backtest

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            data_dir = os.path.join(tmp, "data")
            os.makedirs(data_dir, exist_ok=True)
            btc_1h = _make_trend_candles(n_bars=280, start_px=60000.0, seed=1)
            sol_1h = _make_trend_candles(n_bars=280, start_px=150.0, seed=2)
            _write_kline_csv(os.path.join(data_dir, "BTCUSDT_1h.csv"), btc_1h)
            _write_kline_csv(os.path.join(data_dir, "SOLUSDT_1h.csv"), sol_1h)
            # Also place 15m CSVs to verify engine respects `interval="1h"` without overwriting!
            _write_kline_csv(os.path.join(data_dir, "BTCUSDT_15m.csv"), btc_1h[:100])
            _write_funding_csv(os.path.join(data_dir, "BTCUSDT_funding.csv"), "BTCUSDT", btc_1h[0]["open_time"], 40, rate=0.0002)
            _write_funding_csv(os.path.join(data_dir, "SOLUSDT_funding.csv"), "SOLUSDT", sol_1h[0]["open_time"], 40, rate=0.0003)

            gate_path = os.path.join(tmp, "strategy_gate.json")
            report_path = os.path.join(tmp, "report_v2.md")
            bt = run_backtest(
                sniper_mode=True,
                interval="1h",
                data_dir=data_dir,
                gate_output_path=gate_path,
                report_output_path=report_path,
            )

            self.assertTrue(os.path.exists(gate_path))
            self.assertTrue(os.path.exists(report_path))
            with open(gate_path, "r", encoding="utf-8") as f:
                gate = json.load(f)

            self.assertIn("strategies", gate)
            self.assertIn("by_regime_oos", gate)
            self.assertIn("by_symbol_oos", gate)
            self.assertIn("data_days", gate)
            self.assertIn("updated_at", gate)
            self.assertGreaterEqual(gate["n_trials"], 8)  # 4 strategies * >=2 symbols
            self.assertIn("monte_carlo_20_account", gate)

            for s_id in ("S1_TREND_PULLBACK", "S2_OI_VOL_BREAKOUT", "S3_LIQ_CASCADE_FADE", "S4_EXTREME_FUNDING_REVERSION"):
                self.assertIn(s_id, gate["strategies"])
                entry = gate["strategies"][s_id]
                for req_k in ("dsr", "pbo", "ci95_low", "n_oos", "pf_oos", "expectancy_r_oos", "verdict", "data_days", "updated_at", "by_regime_oos", "by_symbol_oos"):
                    self.assertIn(req_k, entry, msg=f"Missing {req_k} in {s_id}")
                self.assertIn(entry["verdict"], ("LIVE_APPROVED", "SHADOW_ONLY"))
                if entry["verdict"] == "LIVE_APPROVED":
                    self.assertGreaterEqual(entry["dsr"], 0.90)
                    self.assertGreater(entry["ci95_low"], 0.0)
                    self.assertLess(entry["pbo"], 0.50)

            self.assertIn("strategy_gate", bt)


class TestShadowCostParityAndPromotionGates(unittest.TestCase):
    def test_shadow_cost_parity_and_outcomes(self):
        from shadow.engine import ShadowEngine
        from strategies.base import build_sniper_candidate

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_file = os.path.join(tmp, "shadow_cost.db")
            se = ShadowEngine(db_path=db_file, leverage=20)
            b_ts = 59028 * 28_800_000  # Exact 8h funding boundary

            # Direct ShadowEngine.resolve_bar unit verification
            direct_row = {
                "direction": "LONG",
                "entry_price": 100.0,
                "sl_price": 99.0,
                "current_sl_price": 99.0,
                "tp1_price": 100.55,
                "tp2_price": 102.0,
                "sl_distance_pct": 1.0,
                "sniper_mode": 1,
                "tp1_hit": 0,
                "bars_elapsed": 0,
                "vertical_barrier_bars": 4,
                "opened_at": b_ts - 1_800_000,
                "features_json": json.dumps({"_exec_meta": {"entry_type": "MAKER_FIRST_GTX", "atr_pct": 1.0}}),
            }
            direct_res = se.resolve_bar(
                direct_row,
                {"open": 100.0, "high": 102.3, "low": 99.7, "close": 102.1},
                closed_at=b_ts + 600_000,
            )
            self.assertTrue(direct_res["resolved"])
            self.assertEqual(direct_res["outcome"], "SHADOW_WIN")
            self.assertGreater(direct_res["gross_r"], direct_res["r_multiple_net"])
            self.assertEqual(direct_res["funding_events"], 1)

            cand = build_sniper_candidate(
                strategy_id="S1_TREND_PULLBACK",
                direction="LONG",
                entry_price=100.0,
                raw_sl_price=99.0,  # 1.0% SL
                raw_tp2_price=102.0,
                vertical_barrier_bars=2,
                structural_anchor_desc="Parity",
                confluence_tags=["TEST"],
                entry_type="MAKER_FIRST_GTX",
                regime="TREND_BULL",
                symbol="SOLUSDT",
            )
            sh_id = se.register_candidate(cand, ai_decision="SKIP", opened_at=b_ts - 1_800_000)

            # Bar 1: doesn't resolve yet
            r1 = se.update_open_shadows(
                "SOLUSDT",
                {"open": 100.0, "high": 100.4, "low": 99.6, "close": 100.2},
                closed_at=b_ts + 600_000,
            )
            self.assertEqual(r1, [])

            # Bar 2: hits TIME_BARRIER at 100.5 -> SHADOW_TIMEOUT with funding + fees + vol slippage deducted
            r2 = se.update_open_shadows(
                "SOLUSDT",
                {"open": 100.2, "high": 100.5, "low": 99.8, "close": 100.4},
                closed_at=b_ts + 4_200_000,
            )
            self.assertEqual(len(r2), 1)
            rec = r2[0]
            self.assertEqual(rec["shadow_id"], sh_id)
            self.assertEqual(rec["outcome"], "SHADOW_TIMEOUT")
            self.assertIn("gross_r", rec)
            self.assertLess(rec["r_multiple_net"], rec["gross_r"])
            self.assertGreaterEqual(rec["funding_events"], 1)
            self.assertGreater(rec["funding_cost_pct"], 0.0)
            self.assertGreater(rec["cost_pct"], 0.08)  # entry maker + exit taker + slip + funding

            # SL wick overshoot case -> SHADOW_LOSS worse than -1.0R
            sh_id2 = se.register_candidate(cand, ai_decision="SKIP", opened_at=b_ts + 10_000_000)
            r_sl = se.update_open_shadows(
                "SOLUSDT",
                {"open": 100.0, "high": 100.1, "low": 97.5, "close": 98.5},
                closed_at=b_ts + 10_600_000,
            )
            self.assertEqual(len(r_sl), 1)
            self.assertEqual(r_sl[0]["shadow_id"], sh_id2)
            self.assertEqual(r_sl[0]["outcome"], "SHADOW_LOSS")
            self.assertLess(r_sl[0]["r_multiple_net"], -1.05)
            gc.collect()

    def test_check_strategy_gate_decision_2b_and_enforced_mode(self):
        import journal
        from shadow.promote import check_strategy_gate, write_strategy_gate, StrategyLifecycleManager

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            gate_path = os.path.join(tmp, "strategy_gate.json")
            write_strategy_gate(
                {
                    "strategies": {
                        "S1_TREND_PULLBACK": {
                            "dsr": 0.72, "pbo": 0.40, "ci95_low": -0.02, "n_oos": 50,
                            "pf_oos": 1.15, "expectancy_r_oos": 0.09, "verdict": "SHADOW_ONLY",
                        },
                        "S3_LIQ_CASCADE_FADE": {
                            "dsr": 0.96, "pbo": 0.18, "ci95_low": 0.12, "n_oos": 90,
                            "pf_oos": 1.85, "expectancy_r_oos": 0.35, "verdict": "LIVE_APPROVED",
                        },
                    }
                },
                gate_path=gate_path,
            )

            # Decision 2.B: enforce_backtest_gate=False -> SHADOW_ONLY still allowed live with advisory warning
            res_adv = check_strategy_gate("S1_TREND_PULLBACK", config={"enforce_backtest_gate": False}, gate_path=gate_path)
            self.assertTrue(res_adv["allowed_live"])
            self.assertFalse(res_adv["shadow_only"])
            self.assertEqual(res_adv["verdict"], "SHADOW_ONLY")
            self.assertTrue(bool(res_adv["advisory_warning"]))

            # When enforce_backtest_gate=True -> SHADOW_ONLY blocked & forced shadow_only=True
            res_blk = check_strategy_gate("S1_TREND_PULLBACK", config={"enforce_backtest_gate": True}, gate_path=gate_path)
            self.assertFalse(res_blk["allowed_live"])
            self.assertTrue(res_blk["shadow_only"])

            # LIVE_APPROVED passes even when enforced
            res_ok = check_strategy_gate("S3_LIQ_CASCADE_FADE", config={"enforce_backtest_gate": True}, gate_path=gate_path)
            self.assertTrue(res_ok["allowed_live"])
            self.assertFalse(res_ok["shadow_only"])

            # Missing gate file fails closed when enforced, stays open with warning when advisory
            missing_gate = os.path.join(tmp, "missing_gate.json")
            self.assertTrue(check_strategy_gate("S1_TREND_PULLBACK", config={"enforce_backtest_gate": False}, gate_path=missing_gate)["allowed_live"])
            self.assertFalse(check_strategy_gate("S1_TREND_PULLBACK", config={"enforce_backtest_gate": True}, gate_path=missing_gate)["allowed_live"])

            # StrategyLifecycleManager defaults to enforce_backtest_gate=False and respects config
            db_file = os.path.join(tmp, "mgr.db")
            mgr_adv = StrategyLifecycleManager(db_path=db_file, enforce_backtest_gate=False, gate_path=gate_path)
            audit_adv = mgr_adv.audit_strategy("S1_TREND_PULLBACK")
            self.assertFalse(audit_adv["shadow_only"])
            self.assertTrue(bool(audit_adv["advisory_warning"]))

            mgr_enf = StrategyLifecycleManager(db_path=db_file, enforce_backtest_gate=True, gate_path=gate_path)
            audit_enf = mgr_enf.audit_strategy("S1_TREND_PULLBACK")
            self.assertTrue(audit_enf["shadow_only"])
            self.assertFalse(audit_enf["allowed_live"])

            # Even under Decision 2.B (enforce_backtest_gate=False), rolling live auto-degradation stays active
            for idx in range(15):
                tid = journal.record_trade_open(
                    {
                        "trade_id": f"WP6_DEG_{idx}",
                        "symbol": "SOLUSDT",
                        "direction": "LONG",
                        "strategy_id": "S4_EXTREME_FUNDING_REVERSION",
                        "regime": "MEAN_REVERT",
                        "entry_plan": 100.0,
                        "sl_plan": 99.0,
                        "tp_plan": 102.0,
                        "entry_fill": 100.0,
                        "notional_usdt": 100.0,
                    },
                    db_path=db_file,
                )
                journal.record_trade_close(tid, {"exit_fill": 99.0, "r_multiple_net": -0.95}, db_path=db_file)
            deg_audit = mgr_adv.audit_strategy("S4_EXTREME_FUNDING_REVERSION")
            self.assertTrue(deg_audit["degraded"])
            self.assertTrue(deg_audit["shadow_only"])
            self.assertFalse(deg_audit["allowed_live"])
            gc.collect()

    def test_shadow_promotion_span_regime_diversity_and_holm_bhy(self):
        import journal
        from shadow.engine import ShadowEngine
        from shadow.promote import evaluate_shadow_promotion, adjust_pvalues, StrategyLifecycleManager
        from strategies.base import build_sniper_candidate

        # Multiple-comparison adjustment unit checks (Holm & BHY)
        adj_holm = adjust_pvalues({"S1": 0.005, "S2": 0.02, "S3": 0.30, "S4": 0.50}, method="holm", alpha=0.05)
        self.assertTrue(adj_holm["S1"]["rejected_h0"])
        self.assertFalse(adj_holm["S2"]["rejected_h0"])  # 3 * 0.02 = 0.06 > 0.05

        adj_bhy = adjust_pvalues({"S1": 0.002, "S2": 0.04, "S3": 0.30, "S4": 0.50}, method="bhy", alpha=0.05)
        self.assertTrue(adj_bhy["S1"]["rejected_h0"])
        self.assertFalse(adj_bhy["S2"]["rejected_h0"])

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_file = os.path.join(tmp, "promo_hardening.db")
            se = ShadowEngine(db_path=db_file)
            t0 = 1_700_000_000_000

            # 1. Insert 84 winning trades spanning only 5 days and 1 regime -> must REJECT with min_span_days=14 / min_regimes=2
            for i in range(84):
                c = build_sniper_candidate(
                    strategy_id="S1_TREND_PULLBACK",
                    direction="LONG",
                    entry_price=100.0,
                    raw_sl_price=99.0,
                    raw_tp2_price=102.0,
                    vertical_barrier_bars=12,
                    structural_anchor_desc="Short span",
                    confluence_tags=["T"],
                    regime="TREND_BULL",
                    symbol="SOLUSDT",
                )
                open_ts = t0 + i * 3_600_000  # ~3.5 days total
                se.register_candidate(c, ai_decision="SKIP", opened_at=open_ts)
                se.update_open_shadows("SOLUSDT", {"open": 100.0, "high": 102.5, "low": 99.8, "close": 102.2}, closed_at=open_ts + 1_800_000)

            res_short_span = evaluate_shadow_promotion("S1_TREND_PULLBACK", min_shadow_trades=80, db_path=db_file, min_span_days=14, min_regimes=2)
            self.assertFalse(res_short_span["promote_to_live"])
            self.assertLess(res_short_span["span_days"], 14.0)

            # 2. Spread trades across 18 days but STILL only 1 regime -> must REJECT on regime diversity
            for i in range(84):
                c = build_sniper_candidate(
                    strategy_id="S2_OI_VOL_BREAKOUT",
                    direction="LONG",
                    entry_price=100.0,
                    raw_sl_price=99.0,
                    raw_tp2_price=102.0,
                    vertical_barrier_bars=12,
                    structural_anchor_desc="Single regime",
                    confluence_tags=["T"],
                    regime="TREND_BULL",
                    symbol="ETHUSDT",
                )
                open_ts = t0 + i * 5 * 3_600_000  # 84 * 5h = 17.5 days
                se.register_candidate(c, ai_decision="SKIP", opened_at=open_ts)
                se.update_open_shadows("ETHUSDT", {"open": 100.0, "high": 102.5, "low": 99.8, "close": 102.2}, closed_at=open_ts + 1_800_000)

            res_single_reg = evaluate_shadow_promotion("S2_OI_VOL_BREAKOUT", min_shadow_trades=80, db_path=db_file, min_span_days=14, min_regimes=2)
            self.assertFalse(res_single_reg["promote_to_live"])
            self.assertEqual(res_single_reg["distinct_regimes"], 1)

            # 3. Spread trades across 18 days AND 2 regimes -> must PROMOTE cleanly!
            for i in range(84):
                reg = "TREND_BULL" if i % 2 == 0 else "MEAN_REVERT"
                c = build_sniper_candidate(
                    strategy_id="S3_LIQ_CASCADE_FADE",
                    direction="LONG",
                    entry_price=100.0,
                    raw_sl_price=99.0,
                    raw_tp2_price=102.0,
                    vertical_barrier_bars=12,
                    structural_anchor_desc="Full proof",
                    confluence_tags=["T"],
                    regime=reg,
                    symbol="XRPUSDT",
                )
                open_ts = t0 + i * 5 * 3_600_000
                se.register_candidate(c, ai_decision="SKIP", opened_at=open_ts)
                se.update_open_shadows("XRPUSDT", {"open": 100.0, "high": 102.5, "low": 99.8, "close": 102.2}, closed_at=open_ts + 1_800_000)

            res_full = evaluate_shadow_promotion("S3_LIQ_CASCADE_FADE", min_shadow_trades=80, db_path=db_file, min_span_days=14, min_regimes=2, correction_method="holm")
            self.assertTrue(res_full["promote_to_live"])
            self.assertGreaterEqual(res_full["span_days"], 14.0)
            self.assertGreaterEqual(res_full["distinct_regimes"], 2)
            self.assertTrue(res_full["multiple_testing_passed"])

            # Verify StrategyLifecycleManager uses 14-day + 2-regime default when auditing shadow_only
            mgr = StrategyLifecycleManager(db_path=db_file, enforce_backtest_gate=False)
            mgr.status_map["S1_TREND_PULLBACK"]["shadow_only"] = True
            mgr.status_map["S3_LIQ_CASCADE_FADE"]["shadow_only"] = True
            self.assertFalse(mgr.audit_strategy("S1_TREND_PULLBACK")["promote_to_live"])
            self.assertTrue(mgr.audit_strategy("S3_LIQ_CASCADE_FADE")["promote_to_live"])
            self.assertFalse(mgr.status_map["S3_LIQ_CASCADE_FADE"]["shadow_only"])


class TestTwentyDollarMonteCarloRuinSimulator(unittest.TestCase):
    def test_monte_carlo_20_account_min_notional_and_breaker(self):
        from backtest.stress_simulator import simulate_account_ruin_monte_carlo

        # 1. Negative-expectancy R series on $20 20x ALL-IN must show high ruin probability
        bad_r = [-1.05, -1.05, 0.50, -1.05, -1.05, 1.20, -1.05] * 10
        res_bad = simulate_account_ruin_monte_carlo(
            bad_r,
            initial_equity=20.0,
            leverage=20,
            all_in_fraction=0.95,
            min_notional=5.0,
            breaker_losses=2,
            n_paths=300,
            seed=42,
        )
        self.assertGreater(res_bad["ruin_probability"], 0.70)
        self.assertLess(res_bad["median_final_equity"], 20.0)

        # 2. Higher minNotional ($100 vs $5) raises lockout/ruin probability on borderline series
        mixed_r = [1.4, -1.05, -1.05, 1.4, -1.05, 0.4, -1.05, 1.5, -1.05, -1.05] * 6
        res_5 = simulate_account_ruin_monte_carlo(
            mixed_r,
            initial_equity=20.0,
            leverage=20,
            all_in_fraction=0.95,
            min_notional=5.0,
            breaker_losses=2,
            n_paths=400,
            seed=7,
        )
        res_100 = simulate_account_ruin_monte_carlo(
            mixed_r,
            initial_equity=20.0,
            leverage=20,
            all_in_fraction=0.95,
            min_notional=100.0,
            breaker_losses=2,
            n_paths=400,
            seed=7,
        )
        self.assertGreaterEqual(res_100["min_notional_lockout_probability"], res_5["min_notional_lockout_probability"])
        self.assertGreater(res_100["min_equity_required_for_min_notional"], res_5["min_equity_required_for_min_notional"])
        self.assertGreater(res_5["avg_breaker_triggers_per_path"], 0.0)

        # 3. Account starting below minNotional ($0.20 at 20x*0.95 = $3.80 < $5.0) immediately locks out (ruin=1.0)
        res_under = simulate_account_ruin_monte_carlo(
            [1.0, 1.0, 1.0],
            initial_equity=0.20,
            leverage=20,
            all_in_fraction=0.95,
            min_notional=5.0,
            breaker_losses=2,
            n_paths=50,
            seed=1,
        )
        self.assertEqual(res_under["ruin_probability"], 1.0)
        self.assertEqual(res_under["min_notional_lockout_probability"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
