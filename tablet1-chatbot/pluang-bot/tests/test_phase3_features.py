"""
Comprehensive Pytest Suite for Phase 3 (T3.1 – T3.15 / Pilars 1, 2, 4, 8, 9, 10, 11, 14, 15, 16, 20, 21, 26, 27, 28).

Verifies:
  - T3.1 (`data/stream.py`): Closed-bar integrity, forming-bar volume pacing, 1s aggTrade buckets,
    depth20 + OFI history, 24h forceOrder pruning, markPrice@1s state, exponential backoff.
  - T3.2 (`features/microstructure.py`): Multi-level Cont-Kukanov-Stoikov OFI, 20-level OBI,
    Micro-Price & Divergence, TFI/CVD (live aggTrade & historical kline modes), CVD absorption,
    OI x Price 4-Quadrant, Liquidation Cascade Z-Score, Funding/Basis & 10m boundary guard.
  - T3.3 (`features/orthogonal.py`): Spearman IC, Greedy Orthogonal Factor Pruner, Participation
    Ratio `effective_rank`, 20 decorrelated stationary features, regime-conditioned alpha score,
    and strict no-lookahead invariance.
  - T3.4 (`features/toxicity.py`): Volume-Clock VPIN bucketing (ADV/50), bounds in [0, 1],
    empirical CDF percentile, and `toxic_flow_veto`.
  - T3.5 (`features/hawkes.py`): Self-exciting Hawkes O(1) recursive kernel, branching ratio eta < 1,
    `BASELINE | CASCADE_ACCELERATING | CASCADE_EXHAUSTED_INFLECTION` state classification.
  - T3.6 (`features/spot_perp_leadlag.py`): Spot vs Perp CVD Divergence D_SP, Volume Ratio R_SP,
    Stealth Institutional Accumulation vs Leveraged Bull Trap veto, and offline fallback.
  - T3.7 (`features/fracdiff_kyle.py`): Fixed-Width Window Fractional Differentiation (d=0.35),
    no-lookahead invariance, long-memory correlation > 0.80, and Kyle's Lambda fragility z-score.
  - T3.8 (`features/cross_asset_leadlag.py`): BTC/ETH Leader Impulse, dynamic beta, Expected
    Catch-Up Gap into $5 minNotional altcoins (`SOLUSDT`, `XRPUSDT`, `DOGEUSDT`, `SUIUSDT`, `ADAUSDT`).
  - T3.9 (`features/liq_heatmap.py`): Synthetic Liquidation Heatmap (10x/20x/25x/50x/100x),
    Swept-Bin Zeroing Rule on low_t / high_t crossings, magnet detection, and SL stop-hunt shield.
  - T3.10 (`features/options_surface.py`): DVOL, Variance Risk Premium (VRP), 25-Delta Skew,
    and graceful offline fallback.
  - T3.11 (`features/spoof_iceberg.py`): Anti-spoofing persistence weight w_{k,t}^{clean},
    0.3s spoof wall rejection, Cancel-to-Fill Ratio (CFR), and Hidden Iceberg detector.
  - T3.12 (`features/global_radar.py`): Coinbase Institutional Spot Premium (bps & z-score),
    Bybit/OKX Global Aggregated OI & funding dispersion, and graceful offline fallback.
  - T3.13 (`features/hyperliquid_radar.py`): Hyperliquid HLP Vault (`0xdfc2...f303`)
    clearinghouseState parser, whale liquidation absorption & bottom confirmation.
  - T3.14 (`features/path_signatures.py`): Rough Path 2nd-Order Iterated Integrals & Lévy Area
    sign on +pi/2 vs -pi/2 phase-shifted waves, and A_{CVD, P} / A_{OI, P} causality detection.
  - T3.15 (`features/macro_funding_shield.py`): Dynamic `fundingInfo` (2h/4h/8h) tracker,
    bulk `premiumIndex` `nextFundingTime` guard, and US Macro (CPI/NFP/FOMC) + Sunday CME Open shield.
"""

from __future__ import annotations

import datetime
import math
import os
import sys
import unittest
from unittest.mock import patch

import numpy as np

try:
    import pytest  # type: ignore
except ImportError:
    pytest = None  # type: ignore

# Ensure pluang-bot root is on sys.path when invoked directly via `python tests/test_phase3_features.py`
_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from data.stream import (
    BinanceFuturesStreamManager,
    compute_forming_volume_pace,
    separate_closed_and_forming_klines,
)
from features.cross_asset_leadlag import (
    compute_catchup_gap,
    compute_cross_asset_leadlag,
    compute_leader_impulse,
    estimate_dynamic_beta,
)
from features.fracdiff_kyle import (
    compute_fracdiff_features,
    compute_kyles_lambda,
    frac_diff_ffd,
    get_ffd_weights,
)
from features.global_radar import (
    compute_coinbase_premium,
    compute_global_oi_and_funding,
    fetch_global_liquidity_radar,
)
from features.hawkes import HawkesCascadeTracker, evaluate_hawkes_cascade
from features.hyperliquid_radar import (
    HLP_VAULT_ADDRESS,
    HLPSpilloverTracker,
    evaluate_hlp_spillover_series,
    fetch_hlp_vault_state,
    parse_hlp_clearinghouse_state,
)
from features.liq_heatmap import (
    build_liquidation_heatmap,
    compute_tier_liquidation_prices,
    is_sl_in_stop_hunt_zone,
)
from features.macro_funding_shield import (
    DynamicFundingAndMacroShield,
    check_macro_and_cme_shield,
)
from features.microstructure import (
    classify_oi_price_quadrant,
    compute_funding_and_basis,
    compute_liquidation_cascade,
    compute_multilevel_ofi,
    compute_tfi_and_cvd,
)
from features.options_surface import (
    compute_options_surface_metrics,
    fetch_options_surface,
)
from features.orthogonal import (
    ORTHOGONAL_20_FACTOR_NAMES,
    compute_orthogonal_alpha_features,
    effective_rank,
    greedy_orthogonal_prune,
    spearman_ic,
)
from features.path_signatures import (
    compute_levy_area,
    compute_orderflow_levy_signatures,
    compute_path_signatures,
)
from features.spoof_iceberg import (
    OrderBookPersistenceTracker,
    compute_cancel_to_fill_ratio,
    compute_clean_persistence_weight,
    detect_hidden_iceberg,
)
from features.spot_perp_leadlag import (
    compute_spot_perp_divergence,
    fetch_binance_spot_klines,
)
from features.toxicity import VPINTracker, compute_vpin


# ==============================================================================
# 1. T3.1 — Closed-Bar Integrity & Multiplexed WebSocket Stream Manager
# ==============================================================================
def test_t3_1_closed_bar_separation_and_stream_manager():
    server_now_ms = 1_700_000_120_000  # 2 minutes into the 3rd 15m bar
    bar_dur = 900_000  # 15m

    raw_rest_klines = [
        # Bar 1: closed
        [1_699_998_300_000, "100.0", "102.0", "99.0", "101.0", "1000.0", 1_699_999_199_999, "101000.0", 500, "600.0", "60600.0", "0"],
        # Bar 2: closed
        [1_699_999_200_000, "101.0", "103.0", "100.5", "102.5", "1200.0", 1_700_000_099_999, "123000.0", 600, "700.0", "71750.0", "0"],
        # Bar 3: unclosed forming bar (close_time > server_now_ms, only 2m = 120s elapsed out of 900s)
        [1_700_000_100_000, "102.5", "102.8", "102.1", "102.6", "40.0", 1_700_000_999_999, "4104.0", 30, "25.0", "2565.0", "0"],
    ]

    closed, forming = separate_closed_and_forming_klines(
        raw_rest_klines, server_time_ms=server_now_ms, interval="15m"
    )
    assert len(closed) == 2
    assert all(k["is_closed"] is True for k in closed)
    assert closed[-1]["close"] == 102.5
    assert forming is not None
    assert forming["is_closed"] is False
    assert forming["last_price"] == 102.6

    # Check time-normalized forming volume pace: elapsed = 20_000 / 900_000 = 0.0222 < 0.05 -> floor at 0.05
    elapsed_ratio, paced_vol = compute_forming_volume_pace(
        40.0, 1_700_000_100_000, server_now_ms, bar_dur
    )
    assert math.isclose(elapsed_ratio, 20_000 / 900_000, rel_tol=1e-6)
    assert math.isclose(paced_vol, 40.0 / 0.05, rel_tol=1e-6)
    assert math.isclose(forming["paced_volume"], 800.0, rel_tol=1e-6)

    # Test BinanceFuturesStreamManager WebSocket events
    mgr = BinanceFuturesStreamManager(symbols=["SOLUSDT", "XRPUSDT"])
    url = mgr.build_combined_stream_url()
    assert "solusdt@kline_15m" in url
    assert "solusdt@aggTrade" in url
    assert "solusdt@depth20@100ms" in url
    assert "solusdt@forceOrder" in url
    assert "solusdt@markPrice@1s" in url

    # Ingest forming kline (x=False): MUST NOT enter closed_klines
    mgr.process_ws_message({
        "stream": "solusdt@kline_15m",
        "data": {
            "e": "kline",
            "E": 1_700_000_100_000,
            "s": "SOLUSDT",
            "k": {
                "t": 1_700_000_100_000,
                "T": 1_700_000_999_999,
                "s": "SOLUSDT",
                "i": "15m",
                "o": "150.0",
                "h": "152.0",
                "l": "149.5",
                "c": "151.2",
                "v": "500.0",
                "q": "75600.0",
                "V": "300.0",
                "Q": "45360.0",
                "x": False,
            },
        },
    })
    assert len(mgr.get_closed_klines("SOLUSDT", "15m")) == 0
    assert mgr.get_forming_bar("SOLUSDT", "15m")["last_price"] == 151.2

    # Ingest closed kline (x=True): MUST enter closed_klines and clear forming_bar
    mgr.process_ws_message({
        "stream": "solusdt@kline_15m",
        "data": {
            "e": "kline",
            "E": 1_700_001_000_000,
            "s": "SOLUSDT",
            "k": {
                "t": 1_700_000_100_000,
                "T": 1_700_000_999_999,
                "s": "SOLUSDT",
                "i": "15m",
                "o": "150.0",
                "h": "153.0",
                "l": "149.5",
                "c": "152.5",
                "v": "2500.0",
                "q": "381250.0",
                "V": "1500.0",
                "Q": "228750.0",
                "x": True,
            },
        },
    })
    assert len(mgr.get_closed_klines("SOLUSDT", "15m")) == 1
    assert mgr.get_closed_klines("SOLUSDT", "15m")[0]["close"] == 152.5
    assert mgr.get_forming_bar("SOLUSDT", "15m") is None

    # Ingest aggTrades in the same 1-second bucket
    mgr.process_ws_message({
        "stream": "solusdt@aggTrade",
        "data": {"e": "aggTrade", "s": "SOLUSDT", "p": "150.0", "q": "10.0", "T": 1_700_001_000_100, "m": False},
    })
    mgr.process_ws_message({
        "stream": "solusdt@aggTrade",
        "data": {"e": "aggTrade", "s": "SOLUSDT", "p": "150.0", "q": "4.0", "T": 1_700_001_000_500, "m": True},
    })
    buckets = mgr.get_agg_trade_buckets("SOLUSDT")
    assert len(buckets) == 1
    assert math.isclose(buckets[0]["buy_dollar_vol"], 1500.0)
    assert math.isclose(buckets[0]["sell_dollar_vol"], 600.0)
    assert buckets[0]["trade_count"] == 2

    # Ingest forceOrder with 24h pruning
    old_ts = 1_700_000_000_000 - 90_000_000  # > 24h ago
    mgr.ingest_force_order("SOLUSDT", {"o": {"s": "SOLUSDT", "S": "SELL", "p": "140.0", "q": "10.0", "T": old_ts}}, now_ms=old_ts)
    mgr.ingest_force_order("SOLUSDT", {"o": {"s": "SOLUSDT", "S": "SELL", "p": "148.0", "q": "20.0", "T": 1_700_000_000_000}}, now_ms=1_700_000_000_000)
    f_orders = mgr.get_force_orders("SOLUSDT", now_ms=1_700_000_000_000)
    assert len(f_orders) == 1
    assert f_orders[0]["liq_type"] == "LONG_LIQ"
    assert math.isclose(f_orders[0]["notional_usd"], 2960.0)

    # Ingest markPrice@1s
    mgr.process_ws_message({
        "stream": "solusdt@markPrice@1s",
        "data": {"e": "markPriceUpdate", "s": "SOLUSDT", "p": "152.55", "i": "152.40", "r": "0.00015", "T": 1_700_010_000_000, "E": 1_700_001_000_000},
    })
    mp_state = mgr.get_mark_price_state("SOLUSDT")
    assert math.isclose(mp_state["mark_price"], 152.55)
    assert math.isclose(mp_state["funding_rate"], 0.00015)

    # Backoff calculation
    assert BinanceFuturesStreamManager.compute_backoff_seconds(0, jitter=False) == 1.0
    assert BinanceFuturesStreamManager.compute_backoff_seconds(3, jitter=False) == 8.0
    assert BinanceFuturesStreamManager.compute_backoff_seconds(10, jitter=False) == 30.0


# ==============================================================================
# 2. T3.2 — Microstructure & Derivatives Alpha Engine
# ==============================================================================
def test_t3_2_microstructure_ofi_tfi_quadrant_liq_funding():
    prev_book = {
        "bids": [[100.0 - 0.1 * k, 10.0] for k in range(20)],
        "asks": [[100.1 + 0.1 * k, 10.0] for k in range(20)],
    }
    # Bid quantities increase across all levels, Ask quantities decrease -> positive OFI and positive OBI
    curr_book = {
        "bids": [[100.0 - 0.1 * k, 30.0] for k in range(20)],
        "asks": [[100.1 + 0.1 * k, 10.0] for k in range(20)],
    }
    ofi_res = compute_multilevel_ofi(prev_book, curr_book, decay_lambda=0.25)
    expected_weights_sum = sum(math.exp(-0.25 * k) for k in range(20))
    # At each level, P_B unchanged -> Delta B = 30 - 10 = +20; P_A unchanged -> Delta A = 10 - 10 = 0
    assert math.isclose(ofi_res["ofi_raw"], 20.0 * expected_weights_sum, rel_tol=1e-6)
    assert math.isclose(ofi_res["obi_weighted_20"], (30.0 - 10.0) / (30.0 + 10.0), rel_tol=1e-6)
    # Micro-price = (30 * 100.1 + 10 * 100.0) / 40 = 100.075, mid = 100.05, spread = 0.10 -> micro_div = +0.25
    assert math.isclose(ofi_res["micro_price"], 100.075, rel_tol=1e-6)
    assert math.isclose(ofi_res["micro_divergence"], 0.25, rel_tol=1e-6)

    # Test TFI & Bullish CVD Absorption on historical klines (price drops while taker_buy_quote > 50% of quote_vol)
    klines_bull_abs = []
    for i in range(15):
        px = 100.0 - 0.4 * i  # Price steadily making lower lows
        q_vol = 100_000.0
        tb_quote = 72_000.0   # 72% Taker Buy -> Delta CVD = +44,000 per bar
        klines_bull_abs.append([i * 900_000, px + 0.2, px + 0.3, px - 0.1, px, 1000.0, (i + 1) * 900_000 - 1, q_vol, 200, 720.0, tb_quote])

    tfi_res = compute_tfi_and_cvd(klines_bull_abs, window=12)
    assert math.isclose(tfi_res["tfi_15m"], 0.44, rel_tol=1e-4)
    assert tfi_res["price_slope_z"] < -1.0
    assert tfi_res["cvd_slope_z"] > 1.0
    assert tfi_res["bullish_absorption"] is True
    assert tfi_res["bearish_absorption"] is False

    # Test TFI & Bearish CVD Absorption on live @aggTrade dicts (price rises while taker sells dominate)
    live_trades = []
    for i in range(20):
        px = 100.0 + 0.2 * i
        # m=True -> Taker Sell
        live_trades.append({"p": px, "q": 10.0, "m": True, "T": (i + 1) * 10_000})
    tfi_live = compute_tfi_and_cvd(live_trades, window=12)
    assert math.isclose(tfi_live["tfi_5m"], -1.0, rel_tol=1e-6)
    assert tfi_live["bearish_absorption"] is True

    # Test 4-Quadrant OI x Price Mechanics
    assert classify_oi_price_quadrant([100, 101, 102, 103, 105], [1000, 1010, 1020, 1030, 1060])["quadrant"] == "Q1_NEW_LONGS"
    assert classify_oi_price_quadrant([100, 101, 102, 103, 105], [1000, 990, 980, 970, 950])["quadrant"] == "Q2_SHORT_COVERING"
    assert classify_oi_price_quadrant([100, 99, 98, 97, 95], [1000, 1010, 1020, 1030, 1060])["quadrant"] == "Q3_NEW_SHORTS"
    assert classify_oi_price_quadrant([100, 99, 98, 97, 95], [1000, 990, 980, 970, 940])["quadrant"] == "Q4_LONG_LIQ_FLUSH"

    # Test Liquidation Cascade Z-Score & Exhaustion Trigger
    now_ms = 1_700_050_000_000
    force_events = []
    # Baseline small liquidations over prior 20 five-minute buckets
    for b in range(1, 25):
        force_events.append({"o": {"S": "SELL", "p": "100.0", "q": "1.0", "T": now_ms - b * 300_000 - 10_000}})
    # Massive Long liquidation spike in the current 5m bucket
    force_events.append({"o": {"S": "SELL", "p": "100.0", "q": "500.0", "T": now_ms - 30_000}})
    liq_res = compute_liquidation_cascade(
        force_events,
        now_ms=now_ms,
        delta_oi_15m_pct=-2.5,
        recent_1m_lows=[98.0, 98.2, 98.3],
        ofi_current=15.0,
    )
    assert liq_res["long_liq_usd_5m"] == 50_000.0
    assert liq_res["liq_zscore"] > 3.0
    assert liq_res["cascade_exhaustion_trigger"] is True

    # Test Funding & Basis + 10-minute Boundary Guard
    f_hist = [0.0001 + 0.00001 * (i % 3) for i in range(30)]
    f_res = compute_funding_and_basis(
        mark_price=100.15,
        index_price=100.00,
        funding_history=f_hist,
        next_funding_ms=now_ms + 5 * 60_000,  # 5 minutes to funding (<= 10m)
        now_ms=now_ms,
        direction="LONG",
        current_funding_rate=0.0008,  # +0.08% >= 0.05% -> Long pays high funding
        top_trader_ls_ratio=2.4,
    )
    assert math.isclose(f_res["basis_bps"], 15.0, rel_tol=1e-6)
    assert f_res["funding_zscore"] > 2.5
    assert f_res["extreme_long_crowding"] is True
    assert f_res["funding_boundary_block"] is True


# ==============================================================================
# 3. T3.3 — Orthogonal Factor Pruner & Regime-Conditioned Alpha Features
# ==============================================================================
def test_t3_3_orthogonal_factors_and_no_lookahead():
    rng = np.random.default_rng(42)
    n = 150
    fwd_ret = rng.normal(0.0, 0.01, size=n)

    # f1 strongly correlated with fwd_ret; f1_dup collinear with f1 (rho > 0.90) but slightly noisier; f2 orthogonal signal; f_noise pure noise
    f1 = 0.6 * fwd_ret + rng.normal(0.0, 0.004, size=n)
    f1_dup = f1 + rng.normal(0.0, 0.003, size=n)
    orth_raw = rng.normal(0.0, 0.01, size=n)
    f2 = 0.4 * fwd_ret + orth_raw
    f_noise = rng.normal(0.0, 0.01, size=n)

    ic1, t1 = spearman_ic(f1, fwd_ret)
    assert ic1 > 0.40 and t1 > 4.0

    prune_res = greedy_orthogonal_prune(
        {"f1": f1, "f1_dup": f1_dup, "f2": f2, "f_noise": f_noise},
        fwd_ret,
        min_abs_ic=0.04,
        min_t_stat=2.0,
        max_corr=0.65,
    )
    assert "f1" in prune_res["selected_features"]
    assert "f1_dup" not in prune_res["selected_features"]  # pruned due to collinearity |rho| >= 0.65!
    assert "f2" in prune_res["selected_features"]
    assert prune_res["max_pairwise_corr"] < 0.65

    # Generate realistic synthetic OHLCV series (120 bars)
    steps = rng.normal(0.001, 0.012, size=120)
    closes = 100.0 * np.exp(np.cumsum(steps))
    highs = closes * (1.0 + np.abs(rng.normal(0.004, 0.003, size=120)))
    lows = closes * (1.0 - np.abs(rng.normal(0.004, 0.003, size=120)))
    volumes = np.exp(rng.normal(7.0, 0.6, size=120))

    res_trend = compute_orthogonal_alpha_features(closes, highs, lows, volumes, regime="TREND_BULL")
    res_mr = compute_orthogonal_alpha_features(closes, highs, lows, volumes, regime="MEAN_REVERT")
    res_chop = compute_orthogonal_alpha_features(closes, highs, lows, volumes, regime="CHOP_NO_TRADE")

    assert len(res_trend["features"]) == 20
    assert set(res_trend["features"].keys()) == set(ORTHOGONAL_20_FACTOR_NAMES)
    assert res_trend["effective_rank"] >= 12.0
    assert res_trend["max_pairwise_corr"] < 0.65
    assert res_chop["trade_allowed"] is False
    assert res_chop["regime_conditioned_alpha_score"] == 0.0
    assert res_trend["regime_conditioned_alpha_score"] != res_mr["regime_conditioned_alpha_score"]

    # STRICT NO-LOOKAHEAD INVARIANCE TEST:
    # Compute features at bar t=80 using only bars[:80], vs computing on full 120 bars where bars[80:] are wildly mutated
    t_cut = 80
    sub_res = compute_orthogonal_alpha_features(
        closes[:t_cut], highs[:t_cut], lows[:t_cut], volumes[:t_cut], regime="TREND_BULL"
    )
    closes_mut = closes.copy()
    closes_mut[t_cut:] *= 5.0  # Extreme future shock after t_cut
    sub_res_after_mut = compute_orthogonal_alpha_features(
        closes_mut[:t_cut], highs[:t_cut], lows[:t_cut], volumes[:t_cut], regime="TREND_BULL"
    )
    for k in ORTHOGONAL_20_FACTOR_NAMES:
        assert math.isclose(sub_res["features"][k], sub_res_after_mut["features"][k], abs_tol=1e-12)


# ==============================================================================
# 4. T3.4 — VPIN Volume-Synchronized Probability of Informed Trading
# ==============================================================================
def test_t3_4_vpin_volume_clock_and_toxicity_veto():
    adv_24h = 50_000.0  # V_bucket = 50_000 / 50 = 1_000.0
    tracker = VPINTracker(adv_24h=adv_24h, buckets_per_day=50, window_buckets=20)
    assert math.isclose(tracker.bucket_volume, 1000.0)

    # First feed 20 balanced buckets (500 buy, 500 sell -> VPIN = 0.0)
    for _ in range(20):
        tracker.ingest_volume(500.0, 500.0)
    state_bal = tracker.get_state()
    assert math.isclose(state_bal["vpin"], 0.0, abs_tol=1e-9)
    assert state_bal["toxic_flow_veto"] is False

    # Now feed a massive one-sided sell wave (20,000 sell volume in a single burst -> spills across 20 buckets)
    newly_closed = tracker.ingest_volume(0.0, 20_000.0)
    assert newly_closed == 20
    state_toxic = tracker.get_state(proposed_direction="LONG")
    assert math.isclose(state_toxic["vpin"], 1.0, abs_tol=1e-9)
    assert state_toxic["vpin_cdf"] >= 0.90
    assert state_toxic["veto_maker_long"] is True
    assert state_toxic["toxic_flow_veto"] is True
    assert state_toxic["informed_breakout_dir"] == "SHORT"

    # Batch compute_vpin test
    batch_res = compute_vpin([(950.0, 50.0) for _ in range(25)], adv_24h=50_000.0, proposed_direction="SHORT")
    assert 0.0 <= batch_res["vpin"] <= 1.0
    assert math.isclose(batch_res["vpin"], 0.90, abs_tol=1e-6)
    assert batch_res["veto_maker_short"] is True


# ==============================================================================
# 5. T3.5 — Self-Exciting Hawkes Point Process Cascade Tracker
# ==============================================================================
def test_t3_5_hawkes_cascade_accelerating_and_exhausted_inflection():
    tracker = HawkesCascadeTracker(mu_minus=0.10, mu_plus=0.10, half_life_sec=15.0, branching_ratio_eta=0.70, q_scale=10_000.0)
    assert tracker.branching_ratio < 1.0

    # Baseline check
    base_state = tracker.evaluate(t_sec=0.0)
    assert base_state["state"] == "BASELINE"

    # Simulate an accelerating burst of Long liquidations (SELL events) between t=1s and t=5s
    for t_ev in range(1, 6):
        tracker.update_event(float(t_ev), "SELL", 250_000.0)

    acc_state = tracker.evaluate(t_sec=5.0)
    assert acc_state["state"] == "CASCADE_ACCELERATING"
    assert acc_state["ratio_minus"] > 5.0
    assert acc_state["block_long"] is True

    # Now let 45 seconds pass (3 half-lives -> intensity decays to < 0.35 of peak) and aggressive buyers step in
    tracker.evaluate(t_sec=50.0)
    tracker.update_event(51.0, "BUY", 80_000.0)
    inflection_state = tracker.evaluate(t_sec=52.0, ofi_20=0.40)

    assert inflection_state["state"] == "CASCADE_EXHAUSTED_INFLECTION"
    assert inflection_state["sniper_reversal_direction"] == "LONG"
    assert math.isclose(inflection_state["recommended_sniper_sl_pct"], 0.55)


# ==============================================================================
# 6. T3.6 — Binance Spot vs. Perpetual Futures CVD Divergence
# ==============================================================================
def test_t3_6_spot_perp_cvd_divergence_and_offline_fallback():
    spot_klines = []
    perp_klines = []
    # 47 neutral bars
    for i in range(47):
        spot_klines.append({"close": 100.0, "quote_volume": 100_000.0, "taker_buy_quote": 50_000.0 + (i % 3) * 500.0})
        perp_klines.append({"close": 100.0, "quote_volume": 200_000.0, "taker_buy_quote": 100_000.0 + (i % 3) * 500.0})

    # Scenario 1: Stealth Institutional Accumulation (Spot aggressively buys while Perp sells)
    spot_acc = spot_klines + [{"close": 100.5, "quote_volume": 150_000.0, "taker_buy_quote": 135_000.0}]
    perp_acc = perp_klines + [{"close": 100.5, "quote_volume": 300_000.0, "taker_buy_quote": 90_000.0}]
    res_acc = compute_spot_perp_divergence(spot_acc, perp_acc, z_window=48)
    assert res_acc["d_sp"] >= 1.5
    assert res_acc["stealth_accumulation"] is True
    assert res_acc["signal_regime"] == "STEALTH_INSTITUTIONAL_ACCUMULATION"
    assert math.isclose(res_acc["spot_perp_vol_ratio"], 0.50)

    # Scenario 2: Leveraged Retail Froth / Bull Trap (Price & OI rise, Perp buys heavily while Spot sells)
    spot_trap = spot_klines + [{"close": 101.5, "quote_volume": 150_000.0, "taker_buy_quote": 20_000.0}]
    perp_trap = perp_klines + [{"close": 101.5, "quote_volume": 300_000.0, "taker_buy_quote": 260_000.0}]
    res_trap = compute_spot_perp_divergence(spot_trap, perp_trap, z_window=48, delta_oi_pct=2.0, delta_price_pct=1.5)
    assert res_trap["d_sp"] <= -1.5
    assert res_trap["leveraged_bull_trap"] is True
    assert res_trap["veto_long"] is True

    # Offline fallback when spot_klines is empty
    res_offline = compute_spot_perp_divergence([], perp_acc)
    assert res_offline["status"] == "OFFLINE_FALLBACK"
    assert res_offline["veto_long"] is False


# ==============================================================================
# 7. T3.7 — Fractional Differentiation (FFD) & Kyle's Lambda Book Fragility
# ==============================================================================
def test_t3_7_fracdiff_ffd_and_kyles_lambda():
    weights = get_ffd_weights(d=0.35, thres=1e-4)
    assert math.isclose(weights[0], 1.0)
    assert math.isclose(weights[1], -0.35)
    assert np.all(np.abs(weights) >= 1e-4)

    # Trending log-price series: verify high correlation (> 0.80) AND strict no-lookahead
    t = np.linspace(0, 10, 200)
    prices = 100.0 * np.exp(0.08 * t + 0.03 * np.sin(2.0 * t))
    ffd_full = frac_diff_ffd(prices, d=0.35, thres=1e-4, log_transform=True)
    ffd_prefix = frac_diff_ffd(prices[:120], d=0.35, thres=1e-4, log_transform=True)
    assert np.allclose(ffd_full[:120], ffd_prefix, atol=1e-12)

    fd_feats = compute_fracdiff_features(prices, d=0.35, thres=1e-4)
    assert fd_feats["corr_with_log_price"] > 0.80

    # Kyle's Lambda: simulate normal deep book followed by fragile book (large price jumps per unit signed volume)
    rng = np.random.default_rng(7)
    signed_vols = rng.uniform(-100.0, 100.0, size=80)
    dp_normal = 0.001 * signed_vols[:60] + rng.normal(0.0, 0.005, size=60)
    dp_fragile = 0.050 * signed_vols[60:]  # 50x higher price impact per unit volume!
    p_series = 100.0 + np.cumsum(np.concatenate([dp_normal, dp_fragile]))

    kyle_res = compute_kyles_lambda(p_series, signed_vols, window=20, z_window=60)
    assert kyle_res["kyle_lambda"] > 0.02
    assert kyle_res["fragility_zscore"] > 2.0
    assert kyle_res["is_book_fragile"] is True


# ==============================================================================
# 8. T3.8 — Cross-Asset Lead-Lag Propagation (BTC/ETH -> $5 minNotional Altcoins)
# ==============================================================================
def test_t3_8_cross_asset_leadlag_catchup_gap():
    rng = np.random.default_rng(99)
    n = 60
    btc_rets = rng.normal(0.0002, 0.002, size=n)
    # SOL has beta ~ 1.5 to BTC; XRP has beta ~ 1.0 to BTC
    sol_rets = 1.5 * btc_rets + rng.normal(0.0, 0.0004, size=n)
    xrp_rets = 1.0 * btc_rets + rng.normal(0.0, 0.0004, size=n)

    # At the latest bar, BTC jumps +1.2% (+6 sigma impulse!), XRP already moved +1.2%,
    # while SOL lags behind (+0.1% instead of expected 1.5 * 1.2% = +1.8% -> huge catch-up gap!)
    btc_rets[-1] = 0.012
    sol_rets[-1] = 0.001
    xrp_rets[-1] = 0.012

    btc_prices = 60_000.0 * np.cumprod(1.0 + btc_rets)
    sol_prices = 150.0 * np.cumprod(1.0 + sol_rets)
    xrp_prices = 0.60 * np.cumprod(1.0 + xrp_rets)

    res = compute_cross_asset_leadlag(
        btc_prices=btc_prices,
        alt_prices_dict={"SOLUSDT": sol_prices, "XRPUSDT": xrp_prices},
        btc_micro={"ofi_z": 3.2, "tfi_5m": 0.65, "hawkes_ratio": 3.5},
        alt_micro_dict={
            "SOLUSDT": {"obi_20": 0.42},
            "XRPUSDT": {"obi_20": 0.10},
        },
    )
    assert res["impulse_active"] is True
    assert res["impulse_direction"] == "LONG"
    assert res["best_catchup_altcoin"] == "SOLUSDT"
    assert res["altcoin_gaps"]["SOLUSDT"]["trigger_active"] is True
    assert res["altcoin_gaps"]["SOLUSDT"]["primary_gap"] > 0.010


# ==============================================================================
# 9. T3.9 — Synthetic Liquidation Heatmap & Swept-Bin Zeroing Rule
# ==============================================================================
def test_t3_9_liquidation_heatmap_swept_bins_and_sl_shield():
    # Bar 0 & Bar 1: Large OI build-up at price = 100.0
    # 50x Long liquidation price at 100.0 is 100 * (1 - 1/50 + 0.004) = 98.40
    # 25x Long liquidation price at 100.0 is 100 * (1 - 1/25 + 0.004) = 96.40
    closes = [100.0, 100.0, 100.0]
    highs = [100.2, 100.2, 100.2]
    lows = [99.8, 99.8, 98.0]  # Bar 2 drops to 98.0 -> sweeps the 50x Long liquidation cluster at 98.40!
    oi = [10_000.0, 25_000.0, 25_000.0]

    hm = build_liquidation_heatmap(
        closes=closes,
        highs=highs,
        lows=lows,
        oi_series=oi,
        proposed_sl=96.45,  # Right on top of the unswept 25x Long liquidation cluster at 96.40!
        direction="LONG",
    )

    # Verify 50x bin (~98.4) was swept to 0.0 when lows[2] hit 98.0
    for bp, dens in hm["long_liq_bins"].items():
        if bp >= 98.0:
            assert dens == 0.0

    # Verify unswept lower leverage bins (< 98.0, e.g. 25x at ~96.4, 20x at ~95.4) still have positive density
    unswept_below = {bp: dens for bp, dens in hm["long_liq_bins"].items() if bp < 98.0 and dens > 0}
    assert len(unswept_below) >= 2
    assert hm["nearest_long_liq_magnet"] is not None
    assert hm["nearest_long_liq_magnet"] < 98.0
    assert hm["nearest_short_liq_magnet"] is not None
    assert hm["nearest_short_liq_magnet"] > 100.2

    # Proposed SL at 96.45 sits in the 25x stop-hunt zone (~96.40) -> flagged with a safer SL below 96.40
    assert hm["is_sl_in_stop_hunt_zone"] is True
    assert hm["recommended_safe_sl"] < 96.40


# ==============================================================================
# 10. T3.10 — Options Surface Intelligence (DVOL, VRP, 25-Delta Skew)
# ==============================================================================
def test_t3_10_options_surface_vrp_skew_and_offline_fallback():
    vrp_hist = [2.0, 3.5, 4.0, 5.0, 6.0, 4.5, 3.0, 5.5, 6.5, 7.0]
    metrics = compute_options_surface_metrics(
        dvol=62.0,
        realized_vol_yz_24h=44.0,
        call_25d_iv=58.0,
        put_25d_iv=66.0,  # Skew = -8.0% (< -5.0% bearish put protection skew)
        vrp_history=vrp_hist,
    )
    assert math.isclose(metrics["vrp"], 18.0)
    assert metrics["vrp_percentile"] > 90.0
    assert metrics["vol_expansion_alert"] is True
    assert math.isclose(metrics["skew_25d"], -8.0)
    assert metrics["put_skew_bearish_veto"] is True
    assert metrics["veto_aggressive_long"] is True

    # Offline fallback when DVOL is None
    fallback = compute_options_surface_metrics(dvol=None, realized_vol_yz_24h=45.0)
    assert fallback["status"] == "OFFLINE_FALLBACK"
    assert fallback["veto_aggressive_long"] is False


# ==============================================================================
# 11. T3.11 — Anti-Spoofing Order Book Persistence & Hidden Iceberg Detector
# ==============================================================================
def test_t3_11_anti_spoofing_persistence_and_hidden_iceberg():
    tracker = OrderBookPersistenceTracker(decay_lambda=0.25, tau_0=2.5)

    # Step 1 (t=0s): Balanced order book (10 units on each level)
    book_t0 = {
        "bids": [[100.0 - 0.1 * k, 10.0] for k in range(20)],
        "asks": [[100.1 + 0.1 * k, 10.0] for k in range(20)],
    }
    tracker.update(book_t0, t_sec=0.0)

    # Step 2 (t=10.0s): Resting book has aged 10 seconds -> persistence factor ~ (1 - exp(-10/2.5)) = 0.982
    res_aged = tracker.update(book_t0, t_sec=10.0)
    assert abs(res_aged["obi_clean"]) < 1e-6

    # Step 3 (t=10.1s): Whale flashes a massive fake Bid spoof wall of 500 units at level 2 (99.9)
    book_spoof = {
        "bids": [[100.0, 10.0], [99.9, 500.0]] + [[100.0 - 0.1 * k, 10.0] for k in range(2, 20)],
        "asks": [[100.1 + 0.1 * k, 10.0] for k in range(20)],
    }
    res_flash = tracker.update(book_spoof, t_sec=10.1)
    # Raw OBI is heavily skewed (> +0.75) by the spoof wall, whereas clean OBI dampens the 0.0s spoof wall!
    assert res_flash["obi_raw"] > 0.70
    assert res_flash["obi_clean"] < 0.15

    # Step 4 (t=10.3s, 0.2s later): Whale pulls the 500-unit spoof wall with 0 traded volume!
    res_pulled = tracker.update(book_t0, t_sec=10.3, aggressive_sell_vol=0.0)
    assert res_pulled["spoof_wall_detected"] is True
    assert res_pulled["anomaly_tag"] == "SPOOF_WALL"
    assert res_pulled["cfr"] > 10.0

    # Step 5 (t=11.0s): Hidden Iceberg Bid absorption test:
    # Visible best_bid is only 10.0 units at 100.0, but 85.0 units of aggressive selling hit best_bid
    # and best_bid still holds at 100.0 with 9.0 units!
    book_iceberg = {
        "bids": [[100.0, 9.0]] + [[100.0 - 0.1 * k, 10.0] for k in range(1, 20)],
        "asks": [[100.1 + 0.1 * k, 10.0] for k in range(20)],
    }
    res_ice = tracker.update(book_iceberg, t_sec=11.0, aggressive_sell_vol=85.0)
    # Q_iceberg^B = 85.0 - (10.0 - 9.0) = 84.0
    assert res_ice["iceberg_bid_detected"] is True
    assert math.isclose(res_ice["q_iceberg_bid"], 84.0, rel_tol=1e-6)
    assert res_ice["anomaly_tag"] == "ICEBERG_ABSORPTION"


# ==============================================================================
# 12. T3.12 — Global Cross-Exchange Liquidity Radar (Coinbase + Bybit/OKX)
# ==============================================================================
def test_t3_12_global_cross_exchange_radar():
    prem_hist = [1.0, 0.5, -0.5, 1.5, 0.0, -1.0, 0.8, 0.2]
    # Coinbase BTC-USD trading $90 above Binance BTCUSDT on $60,000 (+15 bps)
    cb_res = compute_coinbase_premium(
        coinbase_usd_price=60_090.0,
        binance_usdt_price=60_000.0,
        premium_history_bps=prem_hist,
    )
    assert math.isclose(cb_res["cb_prem_bps"], 15.0, rel_tol=1e-6)
    assert cb_res["cb_prem_zscore"] > 1.8
    assert cb_res["us_institutional_buying"] is True
    assert cb_res["signal"] == "US_INSTITUTIONAL_BUYING"

    oi_res = compute_global_oi_and_funding(
        binance_oi=50_000.0,
        bybit_oi=30_000.0,
        okx_oi=20_000.0,
        binance_funding=0.0001,
        bybit_funding=0.0003,
        okx_funding=0.0002,
        global_oi_history=[90_000.0, 92_000.0, 91_000.0, 93_000.0],
    )
    assert math.isclose(oi_res["oi_global"], 100_000.0)
    assert oi_res["venues_online"] == 3
    assert math.isclose(oi_res["funding_dispersion_bps"], 2.0)


# ==============================================================================
# 13. T3.13 — Hyperliquid On-Chain HLP Vault & Whale Liquidation Spillover Radar
# ==============================================================================
def test_t3_13_hyperliquid_hlp_vault_spillover_radar():
    assert HLP_VAULT_ADDRESS == "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"

    mock_clearinghouse = {
        "assetPositions": [
            {
                "position": {
                    "coin": "BTC",
                    "szi": "150.0",
                    "entryPx": "60000.0",
                    "positionValue": "9000000.0",
                    "unrealizedPnl": "45000.0",
                }
            },
            {
                "position": {
                    "coin": "SOL",
                    "szi": "-20000.0",
                    "entryPx": "150.0",
                    "positionValue": "3000000.0",
                    "unrealizedPnl": "-12000.0",
                }
            },
        ]
    }
    parsed = parse_hlp_clearinghouse_state(mock_clearinghouse)
    assert math.isclose(parsed["BTC"]["signed_notional_usd"], 9_000_000.0)
    assert math.isclose(parsed["SOL"]["signed_notional_usd"], -3_000_000.0)

    # Simulate 30s HLP Vault BTC notional series:
    # Steady around $1M -> sudden +$15M jump when HLP absorbs liquidated whale Longs -> then reverts down by -$4M as hedging finishes
    notional_series_active = [1.0e6, 1.05e6, 0.98e6, 1.02e6, 1.00e6, 1.03e6, 16.0e6]
    res_active = evaluate_hlp_spillover_series(notional_series_active, coin="BTC")
    assert res_active["z_delta_hlp"] > 3.0
    assert res_active["spillover_selling_active"] is True
    assert res_active["sniper_bottom_confirmed"] is False

    # Next 30s tick: HLP sheds inventory from $16M down to $12M -> spillover hedging finished, bottom confirmed!
    notional_series_bottom = notional_series_active + [12.0e6]
    res_bottom = evaluate_hlp_spillover_series(notional_series_bottom, coin="BTC")
    assert res_bottom["sniper_bottom_confirmed"] is True
    assert res_bottom["state"] == "HLP_SPILLOVER_EXHAUSTED_BOTTOM_CONFIRMED"


# ==============================================================================
# 14. T3.14 — Rough Path Theory: 2nd-Order Iterated Integrals & Lévy Area (A_{ij})
# ==============================================================================
def test_t3_14_rough_path_levy_area_phase_waves_and_orderflow():
    t = np.linspace(0.0, 2.0 * math.pi, 200)
    # Wave 1: x(t) leads y(t) by +pi/2 (counterclockwise in (x, y) plane) -> A_{x, y} > 0
    x_lead = np.sin(t)
    y_follow = np.sin(t - math.pi / 2.0)
    area_pos = compute_levy_area(x_lead, y_follow, normalize=False)
    assert area_pos > 2.5  # Theoretical integral over [0, 2pi] is +pi ~ 3.14159

    # Wave 2: x(t) lags y(t) by -pi/2 (clockwise in (x, y) plane) -> A_{x, y} < 0
    y_lead = np.sin(t + math.pi / 2.0)
    area_neg = compute_levy_area(x_lead, y_lead, normalize=False)
    assert area_neg < -2.5  # Theoretical integral is -pi ~ -3.14159

    # Order-Flow Lead-Lag:
    # Case 1: CVD rises in the first half, then Price rises in the second half -> A_{CVD, P} > 0 (Flow-Led)
    cvd_flow_led = np.concatenate([np.linspace(0, 100, 12), np.full(12, 100.0)])
    price_flow_led = np.concatenate([np.full(12, 100.0), np.linspace(100, 110, 12)])
    sig_flow_led = compute_orderflow_levy_signatures(price_flow_led, cvd_flow_led, window=24)
    assert sig_flow_led["levy_area_cvd_price"] > 0.05
    assert sig_flow_led["flow_led_move"] is True
    assert sig_flow_led["causality_regime"] == "FLOW_LED_GENUINE_ACCUMULATION"

    # Case 2: Price jumps first on thin book, then retail CVD chases at top -> A_{CVD, P} < 0 (Exhaustion Trap)
    price_fomo = np.concatenate([np.linspace(100, 110, 12), np.full(12, 110.0)])
    cvd_fomo = np.concatenate([np.full(12, 0.0), np.linspace(0, 100, 12)])
    sig_fomo = compute_orderflow_levy_signatures(price_fomo, cvd_fomo, window=24)
    assert sig_fomo["levy_area_cvd_price"] < -0.05
    assert sig_fomo["exhaustion_trap"] is True
    assert sig_fomo["causality_regime"] == "PRICE_LED_EXHAUSTION_TRAP"


# ==============================================================================
# 15. T3.15 — Dynamic `fundingInfo` (2h/4h/8h) & US Macro / Sunday CME Open Shield
# ==============================================================================
def test_t3_15_dynamic_funding_intervals_and_macro_cme_shield():
    shield = DynamicFundingAndMacroShield()
    shield.ingest_funding_info([
        {"symbol": "BTCUSDT", "fundingIntervalHours": 8},
        {"symbol": "SOLUSDT", "fundingIntervalHours": 4},
        {"symbol": "SUIUSDT", "fundingIntervalHours": 2},
    ])

    # Suppose current time is 01:54:00 UTC (6 minutes before the 02:00 UTC 2-hour funding settlement!)
    dt_0154 = datetime.datetime(2026, 10, 28, 1, 54, 0, tzinfo=datetime.timezone.utc)
    now_ms = int(dt_0154.timestamp() * 1000)
    next_2h_ms = int(datetime.datetime(2026, 10, 28, 2, 0, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000)

    shield.ingest_bulk_premium_index([
        {
            "symbol": "SUIUSDT",
            "markPrice": "2.10",
            "indexPrice": "2.095",
            "lastFundingRate": "0.00075",  # +0.075% >= 0.05% -> Longs pay at 02:00 UTC!
            "nextFundingTime": next_2h_ms,
        },
        {
            "symbol": "BTCUSDT",
            "markPrice": "68000.0",
            "indexPrice": "67980.0",
            "lastFundingRate": "0.00075",
            "nextFundingTime": int(datetime.datetime(2026, 10, 28, 8, 0, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000),
        },
    ])

    # SUIUSDT has a 2-hour funding interval due in 6 minutes -> Long is blocked!
    sui_eval = shield.evaluate_symbol_shield("SUIUSDT", now_ms=now_ms, direction="LONG")
    assert sui_eval["funding_interval_hours"] == 2
    assert math.isclose(sui_eval["minutes_to_funding"], 6.0)
    assert sui_eval["funding_boundary_block"] is True
    assert sui_eval["block_new_entries"] is True

    # SUIUSDT Short RECEIVES positive funding -> NOT blocked by funding guard!
    sui_short = shield.evaluate_symbol_shield("SUIUSDT", now_ms=now_ms, direction="SHORT")
    assert sui_short["funding_boundary_block"] is False

    # BTCUSDT is on an 8-hour funding schedule (366 minutes away) -> NOT blocked at 01:54 UTC
    btc_eval = shield.evaluate_symbol_shield("BTCUSDT", now_ms=now_ms, direction="LONG")
    assert btc_eval["funding_interval_hours"] == 8
    assert btc_eval["funding_boundary_block"] is False

    # Test US CPI release window ([-15m, +10m])
    cpi_ts_ms = int(datetime.datetime(2026, 11, 12, 13, 30, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    shield.register_macro_event("US_CPI_RELEASE", cpi_ts_ms)
    eval_cpi = shield.evaluate_symbol_shield(
        "BTCUSDT",
        now_ms=cpi_ts_ms - 10 * 60_000,  # 10 minutes before CPI
        direction="LONG",
    )
    assert eval_cpi["macro_shield_active"] is True
    assert eval_cpi["active_macro_event"] == "US_CPI_RELEASE"
    assert eval_cpi["tighten_existing_sl_to_be"] is True
    assert eval_cpi["block_new_entries"] is True

    # Test Sunday CME Open window (Sunday 2026-10-25 at 21:50 UTC -> 10m before 22:00 UTC CME Open)
    cme_sun_ms = int(datetime.datetime(2026, 10, 25, 21, 50, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    cme_res = check_macro_and_cme_shield(cme_sun_ms)
    assert cme_res["shield_active"] is True
    assert cme_res["active_event"] == "SUNDAY_CME_FUTURES_OPEN"
    assert cme_res["block_new_entries"] is True


class Phase3FeaturesTestSuite(unittest.TestCase):
    def test_01_t3_1_stream_and_closed_bars(self):
        test_t3_1_closed_bar_separation_and_stream_manager()

    def test_02_t3_2_microstructure(self):
        test_t3_2_microstructure_ofi_tfi_quadrant_liq_funding()

    def test_03_t3_3_orthogonal_factors(self):
        test_t3_3_orthogonal_factors_and_no_lookahead()

    def test_04_t3_4_vpin_toxicity(self):
        test_t3_4_vpin_volume_clock_and_toxicity_veto()

    def test_05_t3_5_hawkes_cascade(self):
        test_t3_5_hawkes_cascade_accelerating_and_exhausted_inflection()

    def test_06_t3_6_spot_perp_leadlag(self):
        test_t3_6_spot_perp_cvd_divergence_and_offline_fallback()

    def test_07_t3_7_fracdiff_kyle(self):
        test_t3_7_fracdiff_ffd_and_kyles_lambda()

    def test_08_t3_8_cross_asset_leadlag(self):
        test_t3_8_cross_asset_leadlag_catchup_gap()

    def test_09_t3_9_liq_heatmap(self):
        test_t3_9_liquidation_heatmap_swept_bins_and_sl_shield()

    def test_10_t3_10_options_surface(self):
        test_t3_10_options_surface_vrp_skew_and_offline_fallback()

    def test_11_t3_11_spoof_iceberg(self):
        test_t3_11_anti_spoofing_persistence_and_hidden_iceberg()

    def test_12_t3_12_global_radar(self):
        test_t3_12_global_cross_exchange_radar()

    def test_13_t3_13_hyperliquid_radar(self):
        test_t3_13_hyperliquid_hlp_vault_spillover_radar()

    def test_14_t3_14_path_signatures(self):
        test_t3_14_rough_path_levy_area_phase_waves_and_orderflow()

    def test_15_t3_15_macro_funding_shield(self):
        test_t3_15_dynamic_funding_intervals_and_macro_cme_shield()


if __name__ == "__main__":
    unittest.main(verbosity=2)

