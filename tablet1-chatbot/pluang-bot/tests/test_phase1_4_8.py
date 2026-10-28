"""
PYROFUEL BOT - COMPREHENSIVE TEST SUITE FOR PHASE 1, PHASE 4 & PHASE 8
Compatible with both `pytest` and `python -m unittest` / `python tests/test_phase1_4_8.py`.
Verifies:
- T1.1: `journal.py` (SQLite WAL, decisions, trades, shadow_trades, base-rate, feature vectors, gate report)
- T1.2: `backtest/fetch.py` (11-column normalization with taker_buy_base & taker_buy_quote)
- T1.3: `backtest/triple_barrier.py`, `backtest/cpcv.py`, `backtest/engine.py` (anti-lookahead, Sniper TP1 lock, DSR)
- T1.4: `backtest/stress_simulator.py` (Flash-Wick -3.5%, Unmitigated Cascade -10%, API Latency Storm)
- T4.1: `features/regime.py` (Hurst, Lo-MacKinlay Variance Ratio, Yang-Zhang Vol, ADX14, 5 Regimes)
- T4.2: `strategies/base.py` & `s1..s4` (SetupCandidate schema, Sniper SL clamping, S1-S4 signals)
- T8.1 & T8.2: `shadow/engine.py` & `shadow/promote.py` (Shadow lifecycle, Auto-Degradation, 80-trade Promotion)
- T8.3: `strategies/bandit_allocator.py` (Discounted Beta-Bernoulli Thompson Sampling delta=0.96)
"""
import os
import sys
import copy
import shutil
import tempfile
import unittest
import subprocess
from pathlib import Path
import numpy as np

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import journal
from features.regime import (
    hurst_exponent,
    variance_ratio,
    yang_zhang_volatility,
    adx_14,
    detect_market_regime,
)
from strategies.base import SetupCandidate, build_sniper_candidate
from strategies import (
    s1_trend_pullback,
    s2_oi_breakout,
    s3_liq_exhaustion,
    s4_funding_reversion,
    ContextualThompsonBandit,
    generate_all_candidates,
)
from backtest.triple_barrier import simulate_triple_barrier, compute_liquidation_price
from backtest.cpcv import (
    generate_purged_walk_forward_splits,
    purge_and_embargo_trades,
    bootstrap_ci95,
    deflated_sharpe_ratio,
)
from backtest.stress_simulator import (
    simulate_flash_wick_stop_hunt,
    simulate_unmitigated_cascade_10pct,
    simulate_api_latency_storm,
    run_all_stress_scenarios,
)
from backtest.fetch import normalize_kline_row, CSV_COLUMNS
from backtest.engine import evaluate_bar_no_lookahead, run_backtest
from shadow.engine import ShadowEngine
from shadow.promote import (
    evaluate_auto_degradation,
    evaluate_shadow_promotion,
    StrategyLifecycleManager,
)


# ============================================================================
# PHASE 1: JOURNAL SQLite WAL (`journal.py`)
# ============================================================================

def test_journal_wal_and_lifecycle(tmp_path=None):
    own_dir = tmp_path is None
    if own_dir:
        tmp_dir = tempfile.mkdtemp(prefix="pf3_jrn_")
        tmp_path = Path(tmp_dir)
    try:
        db_file = str(tmp_path / "test_pyrofuel_journal.db")
        journal.init_db(db_file)

        with journal.get_db(db_file) as conn:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            assert str(mode).lower() == "wal"

        dec_id = journal.record_decision(
            {
                "decision_id": "DEC_SOL_001",
                "ts_ms": 1790000000000,
                "symbol": "SOLUSDT",
                "regime": "TREND_BULL",
                "strategy_id": "S1_TREND_PULLBACK",
                "direction": "LONG",
                "decision": "TRADE",
                "p_raw": 0.78,
                "p_cal": 0.76,
                "ev_r": 0.42,
                "ai_model_primary": "qwen3-32b",
                "ai_model_auditor": "gemini-2.5-flash",
                "latency_ms": 420,
                "tokens_used": 980,
                "features": {"f1": 1.25, "f2": -0.45},
            },
            db_path=db_file,
        )
        assert dec_id == "DEC_SOL_001"

        tr_id = journal.record_trade_open(
            {
                "trade_id": "TRD_SOL_001",
                "decision_id": dec_id,
                "symbol": "SOLUSDT",
                "direction": "LONG",
                "sizing_mode": "ALL_IN",
                "leverage": 20,
                "margin_usdt": 10.0,
                "notional_usdt": 200.0,
                "qty": 1.0,
                "entry_plan": 200.0,
                "sl_plan": 198.0,  # 1.0% SL -> $2.00 risk
                "tp_plan": 204.0,
                "entry_fill": 200.0,
                "opened_at": 1790000001000,
            },
            db_path=db_file,
        )
        assert tr_id == "TRD_SOL_001"

        close_res = journal.record_trade_close(
            tr_id,
            {
                "exit_fill": 203.6,  # +1.8% gross = +$3.60
                "fee_usdt": 0.14,
                "funding_usdt": 0.02,
                "mae_pct": 0.25,
                "mfe_pct": 1.95,
                "close_reason": "TP_EXCHANGE",
                "closed_at": 1790003601000,
            },
            db_path=db_file,
        )
        assert close_res is not None
        assert close_res["r_multiple_net"] > 1.5
        assert close_res["holding_sec"] == 3600

        base_rate = journal.get_empirical_base_rate("S1_TREND_PULLBACK", "TREND_BULL", db_path=db_file)
        assert base_rate["historical_n"] == 1
        assert base_rate["historical_win_rate_pct"] == 100.0

        vecs = journal.get_recent_feature_vectors(regime="TREND_BULL", limit=100, db_path=db_file)
        assert len(vecs) == 1
        assert vecs[0]["win"] == 1
        assert vecs[0]["features"]["f1"] == 1.25

        gate_rep = journal.generate_gate_report(db_path=db_file)
        assert gate_rep["total_trades"] == 1
        assert gate_rep["win_rate"] == 100.0
        assert "S1_TREND_PULLBACK|TREND_BULL" in gate_rep["by_strategy_regime"]
    finally:
        if own_dir:
            shutil.rmtree(str(tmp_path), ignore_errors=True)


def test_journal_cli_report_gate():
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT_DIR, "journal.py"), "report", "--gate"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0
    assert "PYROFUEL" in proc.stdout


# ============================================================================
# PHASE 4: STATISTICAL REGIME CLASSIFIER (`features/regime.py`)
# ============================================================================

def test_regime_classifier_random_walk_trend_and_ou():
    rng = np.random.default_rng(12345)

    # 1. Pure Geometric Brownian Walk with low directional drift & low volatility -> CHOP_NO_TRADE
    steps = rng.choice([-0.001, 0.001], size=150)
    rw_closes = 100.0 * np.exp(np.cumsum(steps))
    h_rw = hurst_exponent(rw_closes)
    assert 0.40 <= h_rw <= 0.60

    rw_klines = [
        {
            "open": float(rw_closes[i - 1] if i > 0 else rw_closes[i]),
            "high": float(rw_closes[i] * 1.0005),
            "low": float(rw_closes[i] * 0.9995),
            "close": float(rw_closes[i]),
            "volume": 100.0,
        }
        for i in range(len(rw_closes))
    ]
    res_rw = detect_market_regime(rw_klines, rw_klines)
    assert res_rw["regime"] in ("CHOP_NO_TRADE", "MEAN_REVERT")

    # 2. Persistent Bullish Trend -> TREND_BULL
    t_idx = np.arange(150, dtype=np.float64)
    trend_closes = 100.0 * np.exp(0.0045 * t_idx + 0.001 * np.sin(t_idx * 0.2))
    h_tr = hurst_exponent(trend_closes)
    vr_tr, z_tr = variance_ratio(trend_closes, lag=4)
    assert h_tr > 0.55
    assert vr_tr > 1.12

    trend_klines = [
        {
            "open": float(trend_closes[i - 1] if i > 0 else trend_closes[i]),
            "high": float(trend_closes[i] * (1.002 + 0.003 * (i / 150.0))),
            "low": float(trend_closes[i] * 0.999),
            "close": float(trend_closes[i]),
            "volume": 500.0,
        }
        for i in range(len(trend_closes))
    ]
    res_tr = detect_market_regime(trend_klines, trend_klines)
    assert res_tr["regime"] == "TREND_BULL"
    assert res_tr["adx14"] >= 24.0

    # 3. Anti-persistent Ornstein-Uhlenbeck / Alternating Series -> MEAN_REVERT
    ou = np.zeros(150, dtype=np.float64)
    ou[0] = 100.0
    for i in range(1, 150):
        ou[i] = 100.0 - 0.75 * (ou[i - 1] - 100.0) + (0.4 if i % 2 == 0 else -0.4)
    h_ou = hurst_exponent(ou)
    vr_ou, _ = variance_ratio(ou, lag=4)
    assert h_ou < 0.45
    assert vr_ou < 0.85

    ou_klines = [
        {
            "open": float(ou[i - 1] if i > 0 else ou[i]),
            "high": float(max(ou[i], ou[i - 1] if i > 0 else ou[i]) + 0.15),
            "low": float(min(ou[i], ou[i - 1] if i > 0 else ou[i]) - 0.15),
            "close": float(ou[i]),
            "volume": 200.0,
        }
        for i in range(len(ou))
    ]
    res_ou = detect_market_regime(ou_klines, ou_klines)
    assert res_ou["regime"] == "MEAN_REVERT"

    # 4. Cascade Exhaustion via micro_state
    res_cas = detect_market_regime(
        ou_klines,
        ou_klines,
        micro_state={"liq_zscore": 3.4, "delta_oi_pct": -1.8, "cascade_exhaustion_trigger": True},
    )
    assert res_cas["regime"] == "CASCADE_EXHAUSTION"


# ============================================================================
# PHASE 4: TRIPLE-BARRIER STRATEGIES S1..S4 (`strategies/*.py`)
# ============================================================================

def test_sniper_candidate_clamping_and_strategies():
    cand_wide = build_sniper_candidate(
        strategy_id="S1_TREND_PULLBACK",
        direction="LONG",
        entry_price=100.0,
        raw_sl_price=95.0,  # 5% raw SL -> must clamp to <= 1.80%
        raw_tp2_price=108.0,
        vertical_barrier_bars=16,
        structural_anchor_desc="Test wide SL",
        confluence_tags=["TEST"],
    )
    assert 0.45 <= cand_wide.sl_distance_pct <= 1.80
    assert cand_wide.rrr_net >= 1.60
    assert cand_wide["strategy_id"] == "S1_TREND_PULLBACK"

    # S1: Trend Pullback to EMA21 in TREND_BULL
    s1_klines = []
    px = 100.0
    for i in range(45):
        px *= 1.003
        s1_klines.append({
            "open": px * 0.998, "high": px * 1.002, "low": px * 0.997,
            "close": px, "volume": 1000.0,
        })
    ema21_approx = np.mean([k["close"] for k in s1_klines[-15:]])
    s1_klines.append({
        "open": ema21_approx * 1.001,
        "high": px * 1.004,
        "low": ema21_approx * 0.996,
        "close": px * 1.002,
        "volume": 1500.0,
    })
    c_s1 = s1_trend_pullback.evaluate(
        s1_klines,
        {"regime": "TREND_BULL"},
        micro_state={"tfi_5m": 0.25, "oi_quadrant": "Q1_NEW_LONGS"},
        symbol="SOLUSDT",
    )
    assert c_s1 is not None
    assert c_s1.strategy_id == "S1_TREND_PULLBACK"
    assert c_s1.direction == "LONG"

    # S2: OI + Vol Squeeze Breakout
    s2_klines = []
    for i in range(35):
        s2_klines.append({
            "open": 100.0, "high": 100.4, "low": 99.6, "close": 100.1, "volume": 500.0
        })
    s2_klines.append({
        "open": 100.1, "high": 101.8, "low": 100.0, "close": 101.5, "volume": 1500.0
    })
    c_s2 = s2_oi_breakout.evaluate(
        s2_klines,
        {"regime": "TREND_BULL"},
        micro_state={"oi_quadrant": "Q1_NEW_LONGS", "delta_oi_pct": 1.4, "ofi_z": 1.8},
        symbol="ETHUSDT",
    )
    assert c_s2 is not None
    assert c_s2.strategy_id == "S2_OI_VOL_BREAKOUT"
    assert c_s2.direction == "LONG"

    # S3: Liquidation Cascade Exhaustion Fade (tight Sniper SL 0.50% - 0.85%)
    s3_klines = []
    for i in range(25):
        s3_klines.append({
            "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 800.0
        })
    s3_klines.append({
        "open": 99.6, "high": 100.2, "low": 98.4, "close": 99.9, "volume": 3200.0
    })
    c_s3 = s3_liq_exhaustion.evaluate(
        s3_klines,
        {"regime": "CASCADE_EXHAUSTION"},
        micro_state={
            "liq_zscore": 3.5,
            "oi_quadrant": "Q4_LONG_LIQ_FLUSH",
            "hawkes_state": "CASCADE_EXHAUSTED_INFLECTION",
            "tfi_5m": 0.30,
            "bullish_absorption": True,
        },
        symbol="XRPUSDT",
    )
    assert c_s3 is not None
    assert c_s3.strategy_id == "S3_LIQ_CASCADE_FADE"
    assert 0.50 <= c_s3.sl_distance_pct <= 0.85

    # S4: Extreme Funding Reversion in MEAN_REVERT
    s4_klines = []
    for i in range(35):
        s4_klines.append({
            "open": 100.0, "high": 100.3, "low": 99.7, "close": 100.0, "volume": 600.0
        })
    s4_klines.append({
        "open": 102.5, "high": 103.2, "low": 101.6, "close": 101.8, "volume": 1400.0
    })
    c_s4 = s4_funding_reversion.evaluate(
        s4_klines,
        {"regime": "MEAN_REVERT"},
        micro_state={
            "funding_zscore": 2.6,
            "tfi_5m": -0.22,
            "bearish_absorption": True,
        },
        symbol="DOGEUSDT",
    )
    assert c_s4 is not None
    assert c_s4.strategy_id == "S4_EXTREME_FUNDING_REVERSION"
    assert c_s4.direction == "SHORT"


# ============================================================================
# PHASE 1: TRIPLE-BARRIER, CPCV, DSR, ANTI-LOOKAHEAD & STRESS SIMULATOR
# ============================================================================

def test_triple_barrier_sniper_lock_and_intrabar_sl_tiebreak():
    cand = build_sniper_candidate(
        strategy_id="S3_LIQ_CASCADE_FADE",
        direction="LONG",
        entry_price=100.0,
        raw_sl_price=99.2,  # 0.80% SL -> TP1 at 100.44 (+0.55R), SL lock at 100.304 (+0.38R)
        raw_tp2_price=101.6,
        vertical_barrier_bars=10,
        structural_anchor_desc="Sniper test",
        confluence_tags=["TEST"],
    )

    both_touched = [{"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "open_time": 1000, "close_time": 2000}]
    res_tie = simulate_triple_barrier(cand, both_touched, sniper_mode=True)
    assert res_tie["outcome"] == "SL"
    assert res_tie["r_multiple_net"] < 0

    tp1_then_pullback = [
        {"open": 100.0, "high": 100.55, "low": 99.85, "close": 100.45, "open_time": 1000, "close_time": 2000},
        {"open": 100.45, "high": 100.48, "low": 99.90, "close": 100.00, "open_time": 2000, "close_time": 3000},
    ]
    res_lock = simulate_triple_barrier(cand, tp1_then_pullback, sniper_mode=True)
    assert res_lock["tp1_hit"] is True
    assert res_lock["outcome"] == "TP1_LOCK_WIN"
    assert res_lock["r_multiple_net"] > 0.30


def test_cpcv_dsr_and_anti_lookahead():
    splits = generate_purged_walk_forward_splits(n_samples=500, n_splits=3, min_train_bars=120, purge_bars=16)
    assert len(splits) >= 2
    for sp in splits:
        assert sp["train_end"] + sp["purge_bars"] <= sp["test_start"]

    r_sample = [0.55, 0.50, -0.80, 1.65, 0.52, 0.48, 1.70, -0.75, 0.55, 0.60, 1.55, 0.50] * 4
    mean_r, ci_lo, ci_hi = bootstrap_ci95(r_sample, n_boot=500)
    assert mean_r > 0.30
    assert ci_lo > 0.0

    dsr_res = deflated_sharpe_ratio(r_sample, num_trials=4)
    assert dsr_res["dsr"] >= 0.95

    base_candles = []
    px = 100.0
    for i in range(80):
        px *= 1.002 if i % 3 != 0 else 0.998
        base_candles.append({
            "open_time": i * 3600_000,
            "open": px * 0.999,
            "high": px * 1.003,
            "low": px * 0.996,
            "close": px,
            "volume": 1000.0 + (i % 5) * 200.0,
            "close_time": (i + 1) * 3600_000 - 1,
        })

    t_idx = 55
    res_orig = evaluate_bar_no_lookahead(base_candles, t_idx, symbol="BTCUSDT")

    mutated_candles = copy.deepcopy(base_candles)
    for k in range(t_idx + 1, len(mutated_candles)):
        mutated_candles[k]["close"] *= 5.0
        mutated_candles[k]["high"] *= 6.0
        mutated_candles[k]["low"] *= 0.1
        mutated_candles[k]["volume"] *= 100.0

    res_mutated = evaluate_bar_no_lookahead(mutated_candles, t_idx, symbol="BTCUSDT")
    assert res_orig["regime_state"] == res_mutated["regime_state"]
    assert [c.to_dict() for c in res_orig["candidates"]] == [c.to_dict() for c in res_mutated["candidates"]]


def test_stress_simulator_all_scenarios():
    res = run_all_stress_scenarios()
    assert res["all_passed"] is True
    assert res["S1_FLASH_WICK"]["survived_flash_wick"] is True
    assert res["S2_UNMITIGATED_CASCADE_10PCT"]["liquidations"] == 0
    assert res["S2_UNMITIGATED_CASCADE_10PCT"]["vault_preserved_100pct"] is True
    assert res["S3_API_LATENCY_STORM"]["final_sl_state"] == "CONFIRMED"


def test_fetch_kline_row_normalization():
    raw_kline = [
        1790000000000, "65000.0", "65500.0", "64800.0", "65200.0", "1200.5",
        1790003599999, "78260000.0", 45210, "680.2", "44350000.0", "0"
    ]
    norm = normalize_kline_row(raw_kline)
    assert len(norm) == len(CSV_COLUMNS)
    assert norm[9] == "680.2"
    assert norm[10] == "44350000.0"


# ============================================================================
# PHASE 8: THOMPSON BANDIT, SHADOW ENGINE & AUTO-DEGRADATION / PROMOTION
# ============================================================================

def test_contextual_thompson_bandit_convergence(tmp_path=None):
    own_dir = tmp_path is None
    if own_dir:
        tmp_dir = tempfile.mkdtemp(prefix="pf3_bnd_")
        tmp_path = Path(tmp_dir)
    try:
        state_file = str(tmp_path / "bandit_state.json")
        bandit = ContextualThompsonBandit(discount_factor=0.96, state_path=state_file, seed=7)

        for _ in range(25):
            bandit.update("S3_LIQ_CASCADE_FADE", "CASCADE_EXHAUSTION", r_net=0.85)
            bandit.update("S4_EXTREME_FUNDING_REVERSION", "CASCADE_EXHAUSTION", r_net=-0.75)

        assert os.path.exists(state_file)
        reloaded = ContextualThompsonBandit(state_path=state_file, seed=7)
        assert reloaded.get_posterior_mean("S3_LIQ_CASCADE_FADE", "CASCADE_EXHAUSTION") > 0.80
        assert reloaded.get_posterior_mean("S4_EXTREME_FUNDING_REVERSION", "CASCADE_EXHAUSTION") < 0.20

        c1 = build_sniper_candidate("S4_EXTREME_FUNDING_REVERSION", "LONG", 100.0, 99.0, 102.0, 12, "S4", [])
        c2 = build_sniper_candidate("S3_LIQ_CASCADE_FADE", "LONG", 100.0, 99.2, 101.8, 12, "S3", [])
        ranked = reloaded.rank_candidates([c1, c2], regime="CASCADE_EXHAUSTION", deterministic=True)
        assert ranked[0].strategy_id == "S3_LIQ_CASCADE_FADE"
    finally:
        if own_dir:
            shutil.rmtree(str(tmp_path), ignore_errors=True)


def test_shadow_engine_and_auto_degradation_promotion(tmp_path=None):
    own_dir = tmp_path is None
    if own_dir:
        tmp_dir = tempfile.mkdtemp(prefix="pf3_shd_")
        tmp_path = Path(tmp_dir)
    try:
        db_file = str(tmp_path / "shadow_test.db")
        sh_engine = ShadowEngine(db_path=db_file)

        cand = build_sniper_candidate(
            strategy_id="S1_TREND_PULLBACK",
            direction="LONG",
            entry_price=100.0,
            raw_sl_price=99.0,
            raw_tp2_price=102.0,
            vertical_barrier_bars=12,
            structural_anchor_desc="Shadow test",
            confluence_tags=["SHADOW"],
            regime="TREND_BULL",
            symbol="SOLUSDT",
        )
        sh_id = sh_engine.register_candidate(cand, ai_decision="SKIP")
        assert sh_id.startswith("SHD_SOLUSDT")

        resolved = sh_engine.update_open_shadows("SOLUSDT", {"high": 102.5, "low": 99.8, "close": 102.2})
        assert len(resolved) == 1
        assert resolved[0]["outcome"] == "SHADOW_WIN"
        assert resolved[0]["r_multiple_net"] > 1.0

        for idx in range(15):
            tid = journal.record_trade_open(
                {
                    "trade_id": f"DEG_{idx}",
                    "symbol": "SOLUSDT",
                    "direction": "LONG",
                    "strategy_id": "S2_OI_VOL_BREAKOUT",
                    "regime": "TREND_BULL",
                    "entry_plan": 100.0,
                    "sl_plan": 99.0,
                    "tp_plan": 102.0,
                    "entry_fill": 100.0,
                    "notional_usdt": 100.0,
                },
                db_path=db_file,
            )
            journal.record_trade_close(
                tid,
                {"exit_fill": 99.0, "r_multiple_net": -0.95, "close_reason": "SL_EXCHANGE"},
                db_path=db_file,
            )

        deg_res = evaluate_auto_degradation("S2_OI_VOL_BREAKOUT", window=15, db_path=db_file)
        assert deg_res["degraded"] is True
        assert deg_res["shadow_only"] is True
        assert deg_res["action"] == "DEMOTE_TO_SHADOW"

        promo_before = evaluate_shadow_promotion("S1_TREND_PULLBACK", min_shadow_trades=80, db_path=db_file)
        assert promo_before["promote_to_live"] is False

        for idx in range(82):
            sh_engine.register_candidate(cand, ai_decision="SKIP")
            sh_engine.update_open_shadows("SOLUSDT", {"high": 102.5, "low": 99.8, "close": 102.2})

        promo_after = evaluate_shadow_promotion("S1_TREND_PULLBACK", min_shadow_trades=80, db_path=db_file)
        assert promo_after["n"] >= 80
        assert promo_after["ci95_low"] > 0.10
        assert promo_after["promote_to_live"] is True
        assert promo_after["shadow_only"] is False
    finally:
        if own_dir:
            shutil.rmtree(str(tmp_path), ignore_errors=True)


class TestPhase1Phase4Phase8Suite(unittest.TestCase):
    def test_01_journal_wal_and_lifecycle(self):
        test_journal_wal_and_lifecycle()

    def test_02_journal_cli_report_gate(self):
        test_journal_cli_report_gate()

    def test_03_regime_classifier(self):
        test_regime_classifier_random_walk_trend_and_ou()

    def test_04_sniper_candidate_and_strategies(self):
        test_sniper_candidate_clamping_and_strategies()

    def test_05_triple_barrier_sniper_lock(self):
        test_triple_barrier_sniper_lock_and_intrabar_sl_tiebreak()

    def test_06_cpcv_dsr_and_anti_lookahead(self):
        test_cpcv_dsr_and_anti_lookahead()

    def test_07_stress_simulator(self):
        test_stress_simulator_all_scenarios()

    def test_08_fetch_kline_row_normalization(self):
        test_fetch_kline_row_normalization()

    def test_09_thompson_bandit_convergence(self):
        test_contextual_thompson_bandit_convergence()

    def test_10_shadow_engine_and_auto_degradation(self):
        test_shadow_engine_and_auto_degradation_promotion()


if __name__ == "__main__":
    unittest.main(verbosity=2)
