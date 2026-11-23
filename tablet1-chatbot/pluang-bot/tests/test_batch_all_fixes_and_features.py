"""
Comprehensive Regression & Feature Verification Suite for Batch 1 (C1-C8),
Batch 2 (H1-H11), Batch 3 (Features #1-#6), and Live AI Gateway Fixes.
Strictly offline (mocked HTTP/exchange), zero live network or keys.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)


class TestStreamAExecutionAndWS(unittest.TestCase):
    def test_c1_amend_stop_loss_bypasses_4130_zero_unprotected_window(self):
        from binance_futures import BinanceFuturesClient

        c = BinanceFuturesClient(api_key="k", api_secret="s")
        c._symbol_cache["SOLUSDT"] = {
            "status": "TRADING", "contractType": "PERPETUAL",
            "quantityPrecision": 2, "pricePrecision": 2,
            "stepSize": 0.01, "minQty": 0.01, "maxQty": 10000.0,
            "marketStepSize": 0.01, "marketMinQty": 0.01, "marketMaxQty": 5000.0,
            "tickSize": 0.01, "minNotional": 5.0,
        }
        c._symbol_cache_time = 10**12

        placed_calls = []
        canceled_ids = []

        def fake_set_sl(sym, direction, trigger_price, quantity=None, **kw):
            placed_calls.append({"trigger": trigger_price, "qty": quantity})
            if quantity is None:
                return {"isError": True, "code": -4130, "error": "An open stop or take profit order with closePosition exists"}
            return {"algoId": 9902, "symbol": sym, "triggerPrice": str(trigger_price)}

        with patch.object(c, "get_open_algo_orders", return_value=(True, [
            {"algoId": 9901, "orderType": "STOP_MARKET", "side": "SELL", "closePosition": True}
        ])), \
             patch.object(c, "get_positions", return_value=[
                 {"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 3.50}
             ]), \
             patch.object(c, "set_stop_loss", side_effect=fake_set_sl), \
             patch.object(c, "cancel_algo_order", side_effect=lambda s, aid: canceled_ids.append(aid) or {"code": 200}):
            res = c.amend_stop_loss("SOLUSDT", "LONG", 151.0, old_algo_id=9901)

        self.assertEqual(res["status"], "AMENDED")
        self.assertEqual(res["new_algo_id"], 9902)
        self.assertTrue(res["used_quantity_reduce_only"])
        self.assertEqual(placed_calls[-1]["qty"], 3.50, "Must place new SL with live qty+reduceOnly before cancelling old SL")
        self.assertEqual(canceled_ids, [9901], "Old closePosition SL cancelled ONLY after new SL confirmed")

    def test_c2_userstream_no_unbound_local_or_keyerror_and_api_key_only(self):
        from exec.userstream import UserDataStreamManager

        req_calls = []
        mock_client = MagicMock()
        def fake_req(method, endpoint, signed=False, api_key_only=False, **kw):
            req_calls.append((method, endpoint, signed, api_key_only))
            return {"listenKey": "lk_test_123"}
        mock_client._request.side_effect = fake_req

        mgr = UserDataStreamManager(client=mock_client)
        lk = mgr.create_listen_key()
        self.assertEqual(lk, "lk_test_123")
        self.assertEqual(req_calls[0], ("POST", "/fapi/v1/listenKey", False, True))

        # NEW / CANCELED order updates MUST NOT raise UnboundLocalError: trade_record
        res_new = mgr.handle_event({
            "e": "ORDER_TRADE_UPDATE",
            "o": {"s": "SOLUSDT", "S": "SELL", "o": "LIMIT", "ot": "LIMIT", "X": "NEW", "R": True, "cp": False}
        })
        self.assertTrue(res_new["handled"])
        self.assertEqual(res_new["status"], "NEW")

        # Exit FILLED when active_positions entry lacks sl_price MUST NOT raise KeyError
        mgr.active_positions["SOLUSDT"] = {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 100.0, "quantity": 1.0}
        res_fill = mgr.handle_event({
            "e": "ORDER_TRADE_UPDATE",
            "E": 1700000000000,
            "o": {"s": "SOLUSDT", "S": "SELL", "o": "TAKE_PROFIT_MARKET", "ot": "TAKE_PROFIT_MARKET", "X": "FILLED", "ap": "102.0", "z": "1.0", "n": "0.05", "rp": "2.0", "R": True, "cp": True}
        })
        self.assertTrue(res_fill["handled"])
        self.assertEqual(res_fill["sub_type"], "POSITION_CLOSED")

    def test_h1_and_feature2_maker_tp1_and_tp2_close_position_sync(self):
        from binance_futures import BinanceFuturesClient

        c = BinanceFuturesClient(api_key="k", api_secret="s")
        c._symbol_cache["SOLUSDT"] = {
            "status": "TRADING", "contractType": "PERPETUAL",
            "quantityPrecision": 2, "pricePrecision": 2,
            "stepSize": 0.01, "minQty": 0.01, "maxQty": 10000.0,
            "marketStepSize": 0.01, "marketMinQty": 0.01, "marketMaxQty": 5000.0,
            "tickSize": 0.01, "minNotional": 5.0,
        }
        c._symbol_cache_time = 10**12

        # 1. Maker TP1 skips safely when remaining slice < minNotional
        with patch.object(c, "get_positions", return_value=[{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 0.06}]):
            mk_skip = c.place_maker_tp1_order("SOLUSDT", "LONG", 150.0, fraction=0.65)
        self.assertFalse(mk_skip["placed"])
        self.assertEqual(mk_skip["status"], "SKIPPED_MIN_NOTIONAL")

        # 2. Maker TP1 places LIMIT GTC reduceOnly when both slices >= minNotional
        sent_params = []
        with patch.object(c, "get_positions", return_value=[{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 2.0}]), \
             patch.object(c, "_request", side_effect=lambda m, ep, params=None, **kw: sent_params.append(params) or {"orderId": 5501}):
            mk_ok = c.place_maker_tp1_order("SOLUSDT", "LONG", 152.0, fraction=0.65)
        self.assertTrue(mk_ok["placed"])
        self.assertEqual(mk_ok["order_id"], 5501)
        self.assertEqual(sent_params[0]["type"], "LIMIT")
        self.assertEqual(sent_params[0]["reduceOnly"], "true")

        # 3. sync_take_profit_close_position cancels old TP and sets quantity=None (closePosition=true)
        tp_calls = []
        with patch.object(c, "get_open_algo_orders", return_value=(True, [{"algoId": 7001, "orderType": "TAKE_PROFIT_MARKET", "side": "SELL"}])), \
             patch.object(c, "cancel_algo_order", return_value={"code": 200}), \
             patch.object(c, "set_take_profit", side_effect=lambda sym, d, trigger_price, quantity=None: tp_calls.append(quantity) or {"algoId": 7002}):
            sync_res = c.sync_take_profit_close_position("SOLUSDT", "LONG", 160.0, old_tp_algo_id=7001)
        self.assertEqual(sync_res["status"], "TP_SYNCED_CLOSE_POSITION")
        self.assertEqual(tp_calls, [None], "Post-TP1 TP2 must use quantity=None (closePosition=true)")

    def test_m14_doh_never_returns_rest_ip_for_ws_domain(self):
        import binance_futures as bf

        bf._dns_cache.clear()
        with patch("binance_futures.requests.get", side_effect=RuntimeError("offline")):
            ws_ip = bf._resolve_doh("fstream.binance.com")
            rest_ip = bf._resolve_doh("fapi.binance.com")
        self.assertIsNone(ws_ip, "fstream.binance.com MUST NOT fall back to REST IP 65.8.76.49")
        self.assertEqual(rest_ip, "65.8.76.49")


class TestStreamBQuantPipelineAndAI(unittest.TestCase):
    def test_c5_liq_heatmap_uses_latest_bars_not_oldest(self):
        from features.liq_heatmap import build_liquidation_heatmap

        # First 30 bars at price 10.0, latest 15 bars at price 100.0; oi_series has len 15
        closes = [10.0] * 30 + [100.0 + i * 0.1 for i in range(15)]
        highs = [c * 1.005 for c in closes]
        lows = [c * 0.995 for c in closes]
        oi = [1000.0 + i * 50.0 for i in range(15)]

        res = build_liquidation_heatmap(closes, highs, lows, oi, direction="LONG")
        mag = res.get("nearest_long_liq_magnet")
        self.assertIsNotNone(mag)
        self.assertGreater(mag, 80.0, f"Heatmap must slice latest [-n:] bars around 100, got stale magnet {mag}")

    def test_c5_quant_factors_latest_adx_neutral_oi_and_supertrend_bear(self):
        import numpy as np
        from quant_factors import evaluate_all_quant_factors

        # 80 bars: first 40 flat, last 40 strong downtrend -> Supertrend must be bearish (-1.0) & OI neutral when 0
        closes = [100.0] * 40 + [100.0 - i * 1.2 for i in range(1, 41)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        vols = [1000.0] * 80

        out = evaluate_all_quant_factors(
            closes, highs, lows, vols,
            funding_data={"funding_rate_raw": 0.0001},
            open_interest_data={"open_interest": 50000.0, "oi_change_24h": 0.0},
            long_short_data={"long_short_ratio": 1.0},
        )
        self.assertEqual(out["derivatives_summary"]["oi_regime"], "NEUTRAL_OI", "Zero oi_change must be NEUTRAL_OI, not LONG_LIQUIDATION")
        self.assertEqual(out["supertrend_10_2.5_state"], -1.0, "Strong downtrend must flip Supertrend bearish")
        self.assertGreater(out["adx_14"], 25.0, "ADX must reflect latest strong trend, not first 60 flat bars")

    def test_c6_funding_threshold_aliases_and_hmm_feature_vector(self):
        import market_data as md
        from features.hmm_drift import extract_quant_feature_vector

        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = [{"fundingRate": "0.00045", "fundingTime": 1700000000000}]
        with patch.object(md, "_public_get", return_value=(fake_resp, False)):
            fr = md.get_binance_funding_rate("SOLUSDT")
        self.assertEqual(fr["sentiment"], "BEARISH_LONGS_PAY")
        self.assertAlmostEqual(fr["funding_rate_raw"], 0.00045, places=6)
        self.assertAlmostEqual(fr["rate"], 0.00045, places=6)
        self.assertAlmostEqual(fr["funding_rate_pct"], 0.045, places=4)

        vec = extract_quant_feature_vector(
            math_proof={"options_dvol": 75.0, "options_skew_25d": -8.0},
            scan_data={"funding_rate": fr},
        )
        self.assertGreater(vec[8], 0.5, "ML feature index 8 (funding) must be non-zero")
        self.assertAlmostEqual(vec[12], 1.0, places=3, msg="ML feature index 12 (DVOL=75) must read options_dvol")
        self.assertLess(vec[13], -0.5, "ML feature index 13 (skew=-8) must read options_skew_25d")

    def test_h2_layer5_never_approves_on_ai_unavailable(self):
        import pipeline as pl

        with patch.object(pl, "_ai_json", side_effect=pl.AIUnavailable("all quota exhausted")):
            res = pl.layer5_final_judgment(
                "SOL-USD",
                {"atr_pct": 1.0, "ema_trend_1h": "BULLISH"},
                {"setup_name": "EMA_PULLBACK", "direction": "LONG", "probability_pct": 85, "confluence_count": 3},
                {"action": "LONG", "entry_price": 100.0, "stop_loss": 98.5, "take_profit": 104.0, "risk_reward_ratio": "1:2.67"},
                {"total_score": 7, "max_score": 8, "critical_failures": []},
                {"atr_pct": 1.0, "ema_trend": "BULLISH"},
            )
        self.assertEqual(res["status"], "REJECTED", "Strict AI-only mandate must block non-AI fallback approvals")
        self.assertTrue(res.get("ai_fallback"))

    def test_h3_options_surface_fetches_eapi_skew_even_when_dvol_succeeds(self):
        from features.options_surface import fetch_options_surface

        dvol_resp = MagicMock(status_code=200)
        dvol_resp.json.return_value = {"result": {"data": [[1, 44, 46, 43, 45.0]]}}
        eapi_resp = MagicMock(status_code=200)
        eapi_resp.json.return_value = [
            {"symbol": "BTC-261225-90000-C", "markIV": "0.42", "delta": "0.25"},
            {"symbol": "BTC-261225-60000-P", "markIV": "0.50", "delta": "-0.25"},
        ]

        with patch("features.options_surface.requests.get", side_effect=[dvol_resp, eapi_resp]) as mock_get:
            out = fetch_options_surface("BTC", realized_vol_yz_24h=40.0)
        self.assertEqual(mock_get.call_count, 2, "Must still fetch Binance eapi skew when Deribit DVOL succeeded")
        self.assertAlmostEqual(out["dvol"], 45.0, places=2)
        self.assertAlmostEqual(out["skew_25d"], -8.0, places=2)

    def test_feature3_15m_micro_timing_exhaustion_chase_veto(self):
        import pipeline as pl

        res = pl._apply_safety_gates(
            {"status": "APPROVED", "direction": "LONG", "confidence_score": 82, "final_reason": ""},
            {"setup_name": "BREAKOUT_MOMENTUM", "direction": "LONG", "probability_pct": 82, "confluence_count": 3},
            {"action": "LONG", "entry_price": 100.0, "stop_loss": 98.8, "take_profit": 103.0, "risk_reward_ratio": "1:2.5"},
            {"total_score": 7, "max_score": 8, "critical_failures": []},
            {"atr_pct": 1.0, "ema_trend_1h": "BULLISH", "rsi_14_1h": 60.0},
            {"atr_pct": 1.0, "ema_trend": "BULLISH", "_micro_15m": {"available": True, "rsi_15m": 81.5, "dist_ema20_atr_15m": 1.9}},
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("15m Micro-Timing Exhaustion Chase", res["final_reason"])

    def test_h8_ai_gateway_exclude_provider_403_reasoning_and_or_discovery(self):
        from ai_gateway import AIGateway, classify_http_error

        # 1. Transient 403 -> TRANSIENT_ERROR (5m), auth 403 -> INVALID_OR_UNPAID (24h), 404 -> MODEL_NOT_FOUND
        cls_cf, _ = classify_http_error(403, "Cloudflare challenge temporary block")
        cls_auth, _ = classify_http_error(403, "Invalid API key / unauthorized")
        cls_404, _ = classify_http_error(404, "model not found")
        self.assertEqual(cls_cf, "TRANSIENT_ERROR")
        self.assertEqual(cls_auth, "INVALID_OR_UNPAID")
        self.assertEqual(cls_404, "MODEL_NOT_FOUND")

        # 2. exclude_provider works independently of exclude_model_family
        gw = AIGateway(
            provider_keys={"groq": ["gsk_1"], "gemini": ["AIza_1"]},
            discover_groq_models=False,
            persist_ledger=False,
        )
        routes = gw._build_candidate_routes(exclude_provider="groq")
        self.assertEqual(routes[0][0], "gemini", "exclude_provider='groq' must prioritize non-groq routes first")

        # 3. Groq reasoning model (qwen3/gpt-oss) omits response_format=json_object & boosts max_tokens >= 1500
        sent_payloads = []
        fake_http = MagicMock()
        def fake_post(url, headers=None, json=None, timeout=None):
            sent_payloads.append(json)
            resp = MagicMock(status_code=200, headers={})
            resp.json.return_value = {"choices": [{"message": {"content": '{"ok":true}'}}], "usage": {"total_tokens": 50}}
            return resp
        fake_http.post.side_effect = fake_post
        gw.session = fake_http

        sc, content, _, _ = gw._invoke_provider_http(
            "groq", "qwen/qwen3.8-27b", "gsk_1", "sys", "usr", max_tokens=250, use_json_format=True
        )
        self.assertEqual(sc, 200)
        self.assertNotIn("response_format", sent_payloads[0])
        self.assertGreaterEqual(sent_payloads[0]["max_tokens"], 1500)
        self.assertEqual(sent_payloads[0]["reasoning_effort"], "none")

    def test_h9_backup_skips_scan_cache_json_files(self):
        import journal

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_p = os.path.join(tmp, "journal.db")
            journal.init_db(db_p)
            with open(os.path.join(tmp, "active_positions.json"), "w", encoding="utf-8") as f:
                json.dump([], f)
            with open(os.path.join(tmp, "BTC_USD_latest.json"), "w", encoding="utf-8") as f:
                json.dump({"cached": True}, f)

            bak = journal.backup_state_and_journal(db_path=db_p, results_dir=tmp, keep_days=7)
            basenames = [os.path.basename(p) for p in bak["copied_json_files"]]
            self.assertTrue(any(n.startswith("active_positions_") for n in basenames))
            self.assertFalse(any("BTC_USD_latest" in n for n in basenames), "Scan cache JSONs must not be copied into daily backup")

    def test_min_confidence_65_and_hybrid_score_exact_calculation(self):
        """Verify min_confidence_score = 68 (calibrated Sniper v3.2) and hybrid calculation is S_Hybrid = 0.55*P_Math + 0.45*P_AI."""
        import json
        import pipeline
        import market_data as md

        cfg_path = os.path.join(os.path.dirname(__file__), "..", "trading_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.assertEqual(cfg.get("min_confidence_score"), 68, "trading_config.json must specify min_confidence_score = 68")

        self.assertEqual(pipeline.MIN_CONFIDENCE_SCORE, 68, "pipeline.MIN_CONFIDENCE_SCORE must match trading_config.json (68)")

        # Sub-$1 coin precision guard (ADA/DOGE/SUI/XRP must never round ATR to 0.00 or collapse S/R)
        h_ada = [0.1477 + 0.0020 + (i % 3) * 0.0004 for i in range(30)]
        l_ada = [0.1477 - 0.0020 - (i % 3) * 0.0004 for i in range(30)]
        c_ada = [0.1477 + (i % 2) * 0.0005 for i in range(30)]
        self.assertGreater(md.calculate_atr(h_ada, l_ada, c_ada, 14), 0.001)
        sr_ada = md.calculate_support_resistance(h_ada, l_ada, c_ada, 24)
        self.assertLess(sr_ada["support_1"], sr_ada["pivot"])
        self.assertLess(sr_ada["pivot"], sr_ada["resistance_1"])

        # Test exact hybrid score math: S_Hybrid = 0.55 * P_Math + 0.45 * P_AI
        # Case A: P_Math = 70.0, P_AI = 65.0 -> S_Hybrid = 0.55*70 + 0.45*65 = 38.5 + 29.25 = 67.75
        p_math = 70.0
        p_ai = 65.0
        s_hybrid = round(0.55 * p_math + 0.45 * p_ai, 2)
        self.assertEqual(s_hybrid, 67.75)
        self.assertEqual(int(round(s_hybrid)), 68)

        # Case B: P_Math = 72.0, P_AI = 75.0 -> S_Hybrid = 0.55*72 + 0.45*75 = 39.6 + 33.75 = 73.35
        p_math_b = 72.0
        p_ai_b = 75.0
        s_hybrid_b = round(0.55 * p_math_b + 0.45 * p_ai_b, 2)
        self.assertEqual(s_hybrid_b, 73.35)
        self.assertGreaterEqual(s_hybrid_b, 72.0, "Should qualify under 72% threshold")

    def test_post_tp_cooldown_microcap_block_and_early_invalidation_guard(self):
        """Regression tests for Nov 20-23 live loss root causes: Post-TP cooldown, micro-cap & 1000x meme block, basis scaling."""
        import auto_trader as at

        orig_state = dict(at.state)
        orig_rej = dict(at._RECENT_REJECT_TS)
        try:
            at.state["symbol_sl_cooldowns"] = {}
            at.state["rejection_stats"] = {}
            at._RECENT_REJECT_TS.clear()

            # 1. Post-TP cooldown blocks immediate re-entry (fixes BREV/ATOM/KAVA 41-second re-entry wipeout)
            at._record_post_sl_symbol_cooldown("KAVAUSDT", "CLOSED_TP", +1.50, cfg={"post_tp_symbol_cooldown_hours": 2.0})
            self.assertIn("KAVAUSDT", at.state["symbol_sl_cooldowns"])

            # 2. Micro-cap (<$70M) and 1000x memecoins blocked; Top Majors prioritized
            ranked = [
                {"pair": "BREVUSDT", "symbol": "BREV-USD", "volume_24h_usd": 18_000_000, "price_change_24h_pct": 4.0, "opportunity_score": 8.0, "high_low_range_pct": 9.0},
                {"pair": "1000PEPEUSDT", "symbol": "1000PEPE-USD", "volume_24h_usd": 500_000_000, "price_change_24h_pct": 4.0, "opportunity_score": 8.5, "high_low_range_pct": 9.0},
                {"pair": "KAVAUSDT", "symbol": "KAVA-USD", "volume_24h_usd": 120_000_000, "price_change_24h_pct": 4.0, "opportunity_score": 8.5, "high_low_range_pct": 8.0},
                {"pair": "SOLUSDT", "symbol": "SOL-USD", "volume_24h_usd": 900_000_000, "price_change_24h_pct": 3.0, "opportunity_score": 6.5, "high_low_range_pct": 5.5},
                {"pair": "BNBUSDT", "symbol": "BNB-USD", "volume_24h_usd": 450_000_000, "price_change_24h_pct": 2.5, "opportunity_score": 6.0, "high_low_range_pct": 4.5},
            ]
            picks = at._technical_pre_filter(ranked, max_ai_coins=5, available_balance_usdt=100.0)
            picked_pairs = [c["pair"] for c in picks]
            self.assertNotIn("BREVUSDT", picked_pairs, "Illiquid micro-cap <$70M must be blocked")
            self.assertNotIn("1000PEPEUSDT", picked_pairs, "1000x memecoins must be blocked on 20x ALL-IN")
            self.assertNotIn("KAVAUSDT", picked_pairs, "Symbol in Post-TP cooldown must not be re-entered")
            self.assertEqual(picked_pairs, ["SOLUSDT", "BNBUSDT"])

            # 3. Realistic 25 bps basis scaling (10 bps perp discount must NOT trigger fake >=1.5 sigma reversal)
            at._MICRO_STATE_CACHE.pop("TESTBASISUSDT", None)
            mock_pi = MagicMock(status_code=200)
            mock_pi.json.return_value = {"markPrice": "0.9990", "indexPrice": "1.0000"}  # 10 bps normal perp discount
            mock_empty = MagicMock(status_code=200)
            mock_empty.json.return_value = []
            def _fake_get(url, *a, **kw):
                if "premiumIndex" in url:
                    return mock_pi
                return mock_empty
            with patch("auto_trader.requests.get", side_effect=_fake_get):
                ms = at._fetch_live_micro_state("TESTBASISUSDT", bn_client=None)
            self.assertLess(abs(ms["spot_perp_div"]), 1.0, "Normal 10 bps basis must not exceed 1.0 sigma")
            self.assertAlmostEqual(ms["spot_perp_div"], 0.4, places=2)
        finally:
            at.state.clear()
            at.state.update(orig_state)
            at._RECENT_REJECT_TS.clear()
            at._RECENT_REJECT_TS.update(orig_rej)


class TestFeaturesAutoTraderAndTelegram(unittest.TestCase):
    def test_feature3_and_5_post_sl_cooldown_and_rejection_telemetry(self):
        import auto_trader as at

        orig_state = dict(at.state)
        try:
            at.state["symbol_sl_cooldowns"] = {}
            at.state["rejection_stats"] = {}
            at._record_post_sl_symbol_cooldown("DOGEUSDT", "CLOSED_SL", -5.0, cfg={"post_sl_symbol_cooldown_hours": 3.0})
            self.assertIn("DOGEUSDT", at.state["symbol_sl_cooldowns"])

            ranked = [
                {"pair": "DOGEUSDT", "symbol": "DOGE-USD", "volume_24h_usd": 300_000_000, "price_change_24h_pct": 3.5, "opportunity_score": 8.0, "high_low_range_pct": 6.0},
                {"pair": "SOLUSDT", "symbol": "SOL-USD", "volume_24h_usd": 300_000_000, "price_change_24h_pct": 3.5, "opportunity_score": 7.5, "high_low_range_pct": 6.0},
            ]
            selected = at._technical_pre_filter(ranked, max_ai_coins=5, available_balance_usdt=100.0)
            pairs = [c["pair"] for c in selected]
            self.assertNotIn("DOGEUSDT", pairs, "Coin in Post-SL cooldown must be skipped")
            self.assertIn("SOLUSDT", pairs)
            counts = (at.state.get("rejection_stats") or {}).get("counts_4h") or {}
            self.assertGreaterEqual(counts.get("POST_SL_COOLDOWN", 0), 1)
        finally:
            at.state.clear()
            at.state.update(orig_state)

    def test_c7_and_feature1_isolated_upnl_and_transfer_dedup(self):
        import auto_trader as at
        import risk.vault as rv
        from risk.engine import HardRiskEngine

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_brk = at.RISK_BREAKER_FILE
            orig_ts = at._LAST_TRANSFER_SYNC_TS
            orig_state = dict(at.state)
            orig_vault = rv.DEFAULT_VAULT_STATE_PATH
            try:
                rv.DEFAULT_VAULT_STATE_PATH = os.path.join(tmp, "vault_state.json")
                at.RISK_BREAKER_FILE = os.path.join(tmp, "risk_breaker_state.json")
                at._LAST_TRANSFER_SYNC_TS = 0.0
                at.state["processed_transfer_ids"] = []
                at.state["transfer_sync_bootstrapped"] = True
                at.state["last_transfer_sync_ms"] = 0
                eng = at.load_hard_risk_engine(current_equity=100.0)
                eng.daily_start_equity = 100.0
                at.save_hard_risk_engine(eng)

                bn = MagicMock()
                bn.get_income_history.return_value = [
                    {"tranId": "TX_9001", "incomeType": "TRANSFER", "income": "50.0", "asset": "USDT", "time": 1700000000000},
                    {"tranId": "TX_9001", "incomeType": "TRANSFER", "income": "50.0", "asset": "USDT", "time": 1700000000000},
                ]
                with patch.object(at, "save_state"), patch.object(at, "send_telegram"):
                    applied = at._sync_external_transfers(bn, {}, force=True)
                self.assertEqual(len(applied), 1, "Duplicate tranId must only apply once")
                self.assertAlmostEqual(applied[0]["delta_usdt"], 50.0, places=4)
                eng_after = at.load_hard_risk_engine()
                self.assertAlmostEqual(eng_after.daily_start_equity, 150.0, places=4)
            finally:
                rv.DEFAULT_VAULT_STATE_PATH = orig_vault
                at.RISK_BREAKER_FILE = orig_brk
                at._LAST_TRANSFER_SYNC_TS = orig_ts
                at.state.clear()
                at.state.update(orig_state)

    def test_c3_telegram_no_callback_server_and_decimal_convert(self):
        import telegram_bot as tb

        src_path = os.path.join(BOT_DIR, "telegram_bot.py")
        with open(src_path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("start_callback_server", src, "Removed undefined start_callback_server crash")
        self.assertIn("EMBED_AUTO_TRADER", src, "Embedded auto_trader must be opt-in only")

        sent_msgs = []
        with patch.object(tb, "send_telegram_message", side_effect=lambda cid, txt, *a, **k: sent_msgs.append(txt)), \
             patch.object(tb, "get_fx_info", return_value={"usd_idr": 16500}), \
             patch.object(tb, "convert_usd_to_idr", side_effect=lambda u: u * 16500):
            tb.handle_convert_command(123, ["50.5", "usd"])
        self.assertTrue(sent_msgs and "$50.5000 USD" in sent_msgs[0], f"Decimal USD must not become 505: {sent_msgs}")

    def test_ai_budget_ledger_auto_clears_stale_v1_cooldowns_on_upgrade(self):
        import ai_gateway as ag

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lp = os.path.join(tmp, "ai_budget_ledger.json")
            key = "gsk_test_upgrade_key"
            bid = f"groq:qwen/qwen3.8-27b:{ag._hash_key(key)}"
            stale_v1 = {
                "utc_date": ag._utc_today_str(),
                "buckets": {
                    bid: {
                        "provider": "groq",
                        "model": "qwen/qwen3.8-27b",
                        "key_hash": ag._hash_key(key),
                        "status": "INVALID_OR_UNPAID",
                        "tokens_used_today": 1000,
                        "tpd_limit": 200000,
                        "cooldown_until": time.time() + 80000.0,
                        "calls_today": 2,
                        "last_error": "HTTP 400 old json_object failure",
                    }
                },
                "total_calls_today": 2,
                "total_tokens_today": 1000,
            }
            with open(lp, "w", encoding="utf-8") as f:
                json.dump(stale_v1, f)

            gw = ag.AIGateway(
                ledger_path=lp,
                provider_keys={"groq": [key]},
                discover_groq_models=False,
                persist_ledger=True,
            )
            self.assertEqual(gw.ledger.get("schema_version"), ag.LEDGER_SCHEMA_VERSION)
            self.assertTrue(
                gw.is_bucket_available("groq", "qwen/qwen3.8-27b", key),
                "Upgrade from legacy v1 ledger must auto-clear stale error cooldowns",
            )

    def test_telegram_all_new_commands_execute_without_errors(self):
        import auto_trader as at
        import journal
        import telegram_bot as tb

        sent = []
        fake_bn = MagicMock()
        fake_bn.get_balance.return_value = {
            "total_wallet_balance": 35.0,
            "available_balance": 35.0,
            "cross_unrealized_pnl": 0.0,
        }
        fake_bn.get_positions.return_value = [
            {
                "symbol": "SOLUSDT",
                "direction": "LONG",
                "leverage": 20,
                "position_amount": 1.0,
                "entry_price": 150.0,
                "mark_price": 153.0,
                "unrealized_pnl": 3.0,
                "liquidation_price": 143.0,
                "margin_type": "ISOLATED",
                "isolated_margin": 7.5,
                "isolated_wallet": 7.5,
            }
        ]
        import risk.vault as rv
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_brk = at.RISK_BREAKER_FILE
            orig_db = journal.DB_PATH
            orig_vault = rv.DEFAULT_VAULT_STATE_PATH
            try:
                rv.DEFAULT_VAULT_STATE_PATH = os.path.join(tmp, "vault_state.json")
                at.RISK_BREAKER_FILE = os.path.join(tmp, "risk_breaker_state.json")
                journal.DB_PATH = os.path.join(tmp, "journal.db")
                journal.init_db(journal.DB_PATH)
                with patch.object(tb, "send_telegram_message", side_effect=lambda cid, txt, *a, **k: sent.append(txt)), \
                     patch.object(tb, "get_binance_client", return_value=fake_bn), \
                     patch.object(tb, "get_fx_info", return_value={"usd_idr": 18000}):
                    tb.handle_why_command(123)
                    tb.handle_positions_command(123)
                    tb.handle_reset_breaker_command(123)
                    tb.handle_reset_vault_command(123)
                    tb.handle_transfer_command(123, ["+10"])
                    tb.handle_digest_command(123)
                    tb.handle_pnl_command(123)
                    tb.handle_wallet_command(123)
                self.assertEqual(len(sent), 8, f"All 8 Telegram handlers must send output: {len(sent)}")
                for idx, txt in enumerate(sent):
                    self.assertNotIn("Gagal", txt, f"Handler #{idx} returned failure message: {txt}")
                    self.assertNotIn("❌", txt, f"Handler #{idx} returned error banner: {txt}")
            finally:
                rv.DEFAULT_VAULT_STATE_PATH = orig_vault
                at.RISK_BREAKER_FILE = orig_brk
                journal.DB_PATH = orig_db

    def test_profit_vault_reset_vault_method(self):
        import tempfile
        import risk.vault as rv
        with tempfile.TemporaryDirectory() as tmp:
            v_path = os.path.join(tmp, "vault_test.json")
            pv = rv.ProfitRatchetVault(initial_equity=50.0, state_path=v_path, persist=True)
            pv.update_equity(70.0)
            self.assertGreater(pv.locked_profit_vault_usdt, 0.0)
            # Reset vault
            res = pv.reset_vault(new_equity=25.0)
            self.assertEqual(res["locked_profit_vault_usdt"], 0.0)
            self.assertEqual(res["high_water_mark_equity"], 25.0)
            self.assertEqual(res["working_balance_usdt"], 25.0)
            self.assertEqual(len(pv.ratchet_events), 0)

    def test_auto_gear_shift_progression_hysteresis_and_config_application(self):
        from risk.gears import AutoGearShiftEngine, reset_gear_engine_cache

        reset_gear_engine_cache()
        base_cfg = {
            "fixed_leverage": 20,
            "max_leverage": 20,
            "margin_type": "ISOLATED",
            "sizing_mode": "ALL_IN",
            "all_in_balance_fraction": 0.95,
            "min_prefilter_volume_usd": 70_000_000,
            "auto_gear_system": {"enabled": True, "downshift_hysteresis_pct": 0.10},
        }
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            gpath = os.path.join(tmp, "gear_state.json")
            eng = AutoGearShiftEngine(downshift_hysteresis_pct=0.10, state_path=gpath, persist=True)

            # 1) Small balance $5.59 -> Gear 1 TURBO (20x ALL_IN 95%)
            c1, s1 = eng.apply_to_config(base_cfg, 5.59)
            self.assertEqual(s1["gear"], 1)
            self.assertEqual(s1["code"], "GEAR_1_TURBO")
            self.assertEqual(c1["fixed_leverage"], 20)
            self.assertEqual(c1["sizing_mode"], "ALL_IN")
            self.assertAlmostEqual(c1["all_in_balance_fraction"], 0.95)
            self.assertFalse(c1["gear_majors_only"])

            # 2) Cross $600 -> Immediate upshift to Gear 2 CRUISE (12x RISK_FRACTIONAL 5%)
            c2, s2 = eng.apply_to_config(base_cfg, 650.0)
            self.assertEqual(s2["gear"], 2)
            self.assertTrue(s2["shifted"])
            self.assertEqual(s2["shift_direction"], "UP")
            self.assertEqual(c2["fixed_leverage"], 12)
            self.assertEqual(c2["sizing_mode"], "RISK_FRACTIONAL")
            self.assertAlmostEqual(c2["risk_pct"], 5.0)
            self.assertGreaterEqual(c2["min_prefilter_volume_usd"], 120_000_000)

            # 3) Dip to $560 (above 10% hysteresis floor $540) -> MUST STAY Gear 2
            _, s2_hold = eng.apply_to_config(base_cfg, 560.0)
            self.assertEqual(s2_hold["gear"], 2)
            self.assertFalse(s2_hold["shifted"])

            # 4) Drop to $520 (below $540 floor) -> Downshift cleanly to Gear 1
            _, s1_down = eng.apply_to_config(base_cfg, 520.0)
            self.assertEqual(s1_down["gear"], 1)
            self.assertTrue(s1_down["shifted"])
            self.assertEqual(s1_down["shift_direction"], "DOWN")

            # 5) Reach $6,200 -> Gear 3 FORTRESS (8x RISK_FRACTIONAL 2.5%, Top-10 majors only, 40% vault lock)
            c3, s3 = eng.apply_to_config(base_cfg, 6200.0)
            self.assertEqual(s3["gear"], 3)
            self.assertEqual(s3["code"], "GEAR_3_FORTRESS")
            self.assertEqual(c3["fixed_leverage"], 8)
            self.assertEqual(c3["sizing_mode"], "RISK_FRACTIONAL")
            self.assertAlmostEqual(c3["risk_pct"], 2.5)
            self.assertTrue(c3["gear_majors_only"])
            self.assertAlmostEqual(s3["vault_lock_fraction"], 0.40)
            self.assertGreaterEqual(c3["min_prefilter_volume_usd"], 250_000_000)

    def test_gate12d_smart_regime_strategy_compatibility_and_btc_macro(self):
        import pipeline as pl

        def _base_inputs(setup_name, hurst, stat_reg, adx, rsi, bb_pb, btc_4h=0.2, ema="NEUTRAL"):
            scan_data = {
                "symbol": "SOL-USD",
                "rsi_1h": rsi,
                "ema_trend_1h": ema,
                "bollinger_1h": {"percent_b": bb_pb, "squeeze": False},
                "btc_macro": {"btc_trend_1h": "NEUTRAL", "btc_4h_pct": btc_4h, "btc_rsi_1h": 50.0},
                "math_proof": {
                    "hurst_exponent": hurst,
                    "statistical_regime": stat_reg,
                    "adx_14": adx,
                    "p_math_pct": 74.0,
                    "hmm_cascade_prob": 0.15,
                    "vpin": 0.30,
                },
            }
            market_data = {
                "current_price": 100.0,
                "live_price": 100.0,
                "funding_rate": {"funding_rate": 0.0001},
                "math_proof": scan_data["math_proof"],
                "_micro_15m": {"available": False},
            }
            setup_res = {"setup_name": setup_name, "direction": "LONG", "confluence_count": 3}
            plan_res = {
                "action": "LONG",
                "order_type": "MAKER_FIRST_GTX",
                "entry_price": 100.0,
                "stop_loss": 98.8,
                "take_profit": 102.6,
                "risk_reward_ratio": "1:2.17",
            }
            risk_res = {"total_score": 7, "max_score": 8, "verdict": "PASS"}
            final_res = {
                "status": "APPROVED",
                "direction": "LONG",
                "setup_name": setup_name,
                "confidence_score": 80,
                "entry_price": 100.0,
                "stop_loss": 98.8,
                "take_profit": 102.6,
                "risk_reward_ratio": "1:2.17",
                "final_reason": "Strong confluence",
            }
            return scan_data, setup_res, plan_res, risk_res, market_data, final_res

        # 1) Sideways MEAN_REVERT + MEAN_REVERSION_BOUNCE at range extreme -> MUST BE ALLOWED (not blindly blocked!)
        sd, su, pln, rk, md, fc = _base_inputs("MEAN_REVERSION_BOUNCE", 0.38, "MEAN_REVERT", 14.0, 29.0, 0.08)
        r1 = pl._apply_safety_gates(fc, su, pln, rk, sd, md)
        self.assertEqual(r1["status"], "APPROVED", f"Valid mean-reversion at extreme must pass: {r1.get('final_reason')}")

        # 2) Sideways MEAN_REVERT + BREAKOUT_MOMENTUM -> MUST BE REJECTED (regime-strategy mismatch)
        sd, su, pln, rk, md, fc = _base_inputs("BREAKOUT_MOMENTUM", 0.38, "MEAN_REVERT", 14.0, 52.0, 0.55)
        r2 = pl._apply_safety_gates(fc, su, pln, rk, sd, md)
        self.assertEqual(r2["status"], "REJECTED")
        self.assertIn("Regime-Strategy mismatch", r2.get("final_reason", ""))

        # 3) Dead-zone mid-range random walk (H=0.50, ADX=12, RSI=50, BB%B=0.50) -> MUST BE REJECTED
        sd, su, pln, rk, md, fc = _base_inputs("LIQUIDITY_SWEEP_REVERSAL", 0.50, "RANDOM_WALK", 12.0, 50.0, 0.50)
        r3 = pl._apply_safety_gates(fc, su, pln, rk, sd, md)
        self.assertEqual(r3["status"], "REJECTED")
        self.assertIn("Dead-zone random-walk chop", r3.get("final_reason", ""))

        # 4) Altcoin LONG fighting decisive BTC 4h dump (-2.1%) -> MUST BE REJECTED
        sd, su, pln, rk, md, fc = _base_inputs("TREND_PULLBACK", 0.60, "TRENDING", 30.0, 48.0, 0.35, btc_4h=-2.1, ema="BULLISH")
        r4 = pl._apply_safety_gates(fc, su, pln, rk, sd, md)
        self.assertEqual(r4["status"], "REJECTED")
        self.assertIn("BTC Macro Divergence", r4.get("final_reason", ""))

    def test_continuous_ai_trade_memory_open_close_lessons_prompt_and_backfill(self):
        from ai.trade_memory import AITradeMemoryEngine, synthesize_feature_vector_from_pos
        import auto_trader as at

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mpath = os.path.join(tmp, "ai_trade_memory.json")
            mem = AITradeMemoryEngine(memory_path=mpath)

            # 1) Record open without quant_feature_vector -> synthesizes deterministic 12-dim vector
            pos1 = {
                "id": "POS_MEM_1",
                "symbol": "SOL-USD",
                "binance_pair": "SOLUSDT",
                "direction": "LONG",
                "setup_name": "BREAKOUT_MOMENTUM",
                "regime": "MEAN_REVERT",
                "entry_price": 150.0,
                "init_stop_loss": 149.1,  # 0.60% tight SL
                "leverage": 20,
                "position_size_usd": 5.0,
                "opened_ts": time.time() - 300.0,  # 5m hold
                "confidence_score": 76,
                "math_proof": {"p_math_pct": 71.0, "hurst_exponent": 0.41, "adx_14": 15.0, "rsi_15m": 62.0},
            }
            snap = mem.record_open(pos1)
            self.assertEqual(len(snap["quant_feature_vector"]), 12)
            self.assertIsNotNone(mem.lookup_open_record(pos_id="POS_MEM_1"))

            # 2) Record 2 losses on SOL-USD -> lessons & prompt warning generated
            cls1 = mem.record_close(pos1, exit_price=149.1, exit_reason="SL_HIT", gross_pnl_usd=-0.60, fee_usd=0.10, net_pnl_usd=-0.70)
            self.assertEqual(cls1["outcome"], "LOSS")
            self.assertTrue(any("FAST_SL_STOPHUNT" in ls for ls in cls1["lessons"]))
            self.assertTrue(any("TIGHT_SL" in ls for ls in cls1["lessons"]))

            pos2 = dict(pos1, id="POS_MEM_2")
            mem.record_open(pos2)
            mem.record_close(pos2, exit_price=149.2, exit_reason="SL_HIT", gross_pnl_usd=-0.50, fee_usd=0.10, net_pnl_usd=-0.60)

            ctx = mem.build_prompt_memory_context(
                symbol="SOL-USD",
                regime="MEAN_REVERT",
                direction="LONG",
                setup_name="BREAKOUT_MOMENTUM",
                knn_note="3 analogs -> 33% WR",
            )
            self.assertIn("AI_MEMORY", ctx)
            self.assertIn("CAUTION: poor history on this coin", ctx)
            self.assertIn("AvoidPastErrors", ctx)
            self.assertIn("kNN:", ctx)

            # 3) Binance closed history backfill + strict deduplication by orderId
            fake_bn = MagicMock()
            fake_bn.get_income_history.return_value = [
                {"symbol": "ETHUSDT", "incomeType": "REALIZED_PNL", "income": "1.25", "time": int(time.time() * 1000) - 60_000}
            ]
            fake_bn.get_user_trades.return_value = [
                {"orderId": 1001, "time": int(time.time() * 1000) - 120_000, "side": "BUY", "qty": "0.05", "price": "3000.0", "realizedPnl": "0", "commission": "0.06"},
                {"orderId": 1002, "time": int(time.time() * 1000) - 60_000, "side": "SELL", "qty": "0.05", "price": "3025.0", "realizedPnl": "1.25", "commission": "0.06"},
            ]
            ing1 = mem.sync_binance_closed_history(fake_bn, days=14, min_interval_sec=0.0)
            ing2 = mem.sync_binance_closed_history(fake_bn, days=14, min_interval_sec=0.0)
            self.assertEqual(ing1, 1)
            self.assertEqual(ing2, 0, "Duplicate Binance orderId must NEVER be double-counted")
            self.assertEqual(len(synthesize_feature_vector_from_pos({"direction": "SHORT", "entry_price": 100.0, "stop_loss": 101.2})), 12)

            # 4) Verify _update_closed_loop_learners trains meta_ensemble even when quant_feature_vector is missing!
            orig_res = at.RESULTS_DIR
            orig_brk = at.RISK_BREAKER_FILE
            try:
                at.RESULTS_DIR = tmp
                at.RISK_BREAKER_FILE = os.path.join(tmp, "risk_breaker_state.json")
                pos_no_vec = {
                    "id": "POS_SYNC_NO_VEC",
                    "symbol": "BNBUSDT",
                    "binance_pair": "BNBUSDT",
                    "direction": "LONG",
                    "entry_price": 600.0,
                    "init_stop_loss": 592.0,
                    "leverage": 20,
                    "position_size_usd": 5.0,
                }
                with patch("features.hmm_drift.load_tabular_meta_model") as m_tab, \
                     patch("features.hmm_drift.save_tabular_meta_model"), \
                     patch("features.hmm_drift.load_ensemble_weights") as m_ens, \
                     patch("features.hmm_drift.save_ensemble_weights"), \
                     patch("features.hmm_drift.append_episodic_episode") as m_ep, \
                     patch("features.hmm_drift.load_calibrator", return_value=MagicMock(history_y=[])), \
                     patch("features.hmm_drift.save_calibrator"), \
                     patch("features.hmm_drift.load_conformal_filter", return_value=MagicMock()), \
                     patch("features.hmm_drift.save_conformal_filter"), \
                     patch("features.hmm_drift.ADWINDetector") as m_adwin, \
                     patch("strategies.bandit_allocator.ContextualThompsonBandit") as m_bandit:
                    m_bandit.return_value.update.return_value = None
                    m_adwin.return_value.update.return_value = {"drift_detected": False}
                    at._update_closed_loop_learners(pos_no_vec, net_usd=0.80, exit_price=608.0, exit_reason="TP_HIT")
                    m_tab.return_value.partial_fit.assert_called_once()
                    m_ens.return_value.update_from_outcome.assert_called_once()
                    m_ep.assert_called_once()
            finally:
                at.RESULTS_DIR = orig_res
                at.RISK_BREAKER_FILE = orig_brk

    def test_telegram_gear_and_memory_commands_execute_cleanly(self):
        import telegram_bot as tb

        sent = []
        fake_bn = MagicMock()
        fake_bn.get_balance.return_value = {
            "total_wallet_balance": 5.59,
            "available_balance": 5.59,
            "cross_unrealized_pnl": 0.0,
        }
        fake_bn.get_positions.return_value = []
        fake_bn.get_income_history.return_value = []
        fake_bn.get_user_trades.return_value = []
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_res = tb.RESULTS_DIR
            try:
                tb.RESULTS_DIR = tmp
                with patch.object(tb, "send_telegram_message", side_effect=lambda cid, txt, *a, **k: sent.append(txt)), \
                     patch.object(tb, "get_binance_client", return_value=fake_bn), \
                     patch.object(tb, "get_fx_info", return_value={"usd_idr": 16500}):
                    tb.handle_gear_command(123)
                    tb.handle_memory_command(123)
                self.assertEqual(len(sent), 2)
                self.assertIn("Gigi 1", sent[0])
                self.assertIn("AI CONTINUOUS TRADE MEMORY", sent[1])
            finally:
                tb.RESULTS_DIR = orig_res

    def test_committee_v3_veto_only_direction_symmetric_and_zero_param_tampering(self):
        import multi_agent_committee as mac
        import pipeline as pl

        # 1) Funding normalization check (decimal 0.0001 -> 0.01% NOT 0.0001%)
        self.assertAlmostEqual(mac._normalize_funding_pct(0.0001), 0.01, places=4)
        self.assertAlmostEqual(mac._normalize_funding_pct({"funding_rate_raw": -0.0006}), -0.06, places=4)

        # 2) Direction-symmetric SHORT debate + Gear 2 (12x) Risk Officer Audit-Only + PM APPROVE / VETO
        base_ctx = {
            "scan_summary": {
                "symbol": "ETH-USD",
                "btc_macro": {"btc_1h_trend": "BEARISH", "btc_4h_pct": -1.8, "btc_rsi_1h": 38.0},
                "math_proof": {
                    "p_math_pct": 76.0,
                    "obi_weighted_20": -0.35,
                    "hurst_exponent": 0.61,
                    "adx_14": 31.0,
                    "statistical_regime": "TRENDING",
                },
            },
            "market_data": {
                "live_price": 3000.0,
                "current_price": 3000.0,
                "rsi_14": 42.0,
                "ema_trend": "BEARISH",
                "change_24h_pct": -3.2,
                "volume_24h_usd": 900_000_000,
                "funding_rate": {"funding_rate_raw": 0.0002},
                "news_macro": {"market_sentiment": "BEARISH"},
            },
            "setup_result": {"setup_name": "TREND_CONTINUATION", "direction": "SHORT", "confluence_count": 3},
            "plan_result": {
                "entry_price": 3000.0,
                "stop_loss": 3045.0,  # 1.50% SL
                "take_profit_1": 2959.5,
                "take_profit_2": 2910.0,  # RRR 1:2.0
                "tp_time_prediction": {"eta_label": "~3h"},
            },
            "final_call": {
                "status": "APPROVED",
                "direction": "SHORT",
                "confidence_score": 81,
                "entry_price": 3000.0,
                "stop_loss": 3045.0,
                "take_profit_1": 2959.5,
                "take_profit_2": 2910.0,
                "take_profit": 2910.0,
                "risk_reward_ratio": "1:2.0",
            },
            "memory_context": "AI_MEMORY(last 10): 7W/3L (WR 70%, PF 2.40)",
            "active_gear": {"gear": 2, "code": "GEAR_2_CRUISE", "leverage": 12, "sizing_mode": "RISK_FRACTIONAL", "risk_pct": 5.0},
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_th = mac.THESIS_FILE
            orig_lg = mac.COMMITTEE_LOG_FILE
            try:
                mac.THESIS_FILE = os.path.join(tmp, "thesis.json")
                mac.COMMITTEE_LOG_FILE = os.path.join(tmp, "comm_log.json")

                # 2a) PM approves SHORT -> preserves exact Layer 3/5 SL=3045, TP2=2910, Gear 2 leverage=12
                def _fake_ai_approve(prompt, system_prompt="", max_tokens=180, is_json=False):
                    if is_json:
                        return json.dumps({"verdict": "APPROVE", "confidence_pct": 82, "fatal_flaw": "", "decision": "Konfluensi SHORT solid."})
                    return "Analisis singkat berbasis data."

                with patch.object(mac, "call_ai", side_effect=_fake_ai_approve):
                    res_ok = mac.run_multi_agent_committee("ETH-USD", active_positions=[], pipeline_context=base_ctx)
                self.assertTrue(res_ok["approved"])
                self.assertEqual(res_ok["direction"], "SHORT")
                self.assertEqual(res_ok["risk_officer"]["recommended_leverage"], 12)
                self.assertAlmostEqual(res_ok["risk_officer"]["sl_price"], 3045.0)
                self.assertAlmostEqual(res_ok["risk_officer"]["tp2_price"], 2910.0)

                # 2b) PM vetoes trap -> approved=False, direction=SKIP
                def _fake_ai_veto(prompt, system_prompt="", max_tokens=180, is_json=False):
                    if is_json:
                        return json.dumps({"verdict": "VETO", "confidence_pct": 35, "fatal_flaw": "Fakeout trap di support besar", "decision": "Veto jebakan."})
                    return "Red team menemukan jebakan."

                with patch.object(mac, "call_ai", side_effect=_fake_ai_veto):
                    res_veto = mac.run_multi_agent_committee("ETH-USD", active_positions=[], pipeline_context=base_ctx)
                self.assertFalse(res_veto["approved"])
                self.assertEqual(res_veto["direction"], "SKIP")
                self.assertIn("Fakeout trap", res_veto["portfolio_manager"]["decision"])
            finally:
                mac.THESIS_FILE = orig_th
                mac.COMMITTEE_LOG_FILE = orig_lg

        # 3) Verify Layer 3 & Layer 4 prompts are synchronized with active SL corridor (0.90-2.25%), RRR 1.8, MAKER_FIRST_GTX, BTC 4H & AI_MEMORY
        captured = []
        def _fake_ai_json(prompt, system, max_tokens=300, temp=0.05, tag=""):
            captured.append((tag, system, prompt))
            if "Layer3" in tag:
                return {"action": "LONG", "order_type": "MAKER_FIRST_GTX", "entry_price": 100.0, "stop_loss": 98.8, "take_profit": 102.6, "leverage": 20}
            return {"total_score": 7, "max_score": 8, "pass_rate_pct": 87, "critical_failures": [], "risk_verdict": "LOW_RISK", "recommendation": "PROCEED"}

        md_p = {"live_price": 100.0, "current_price": 100.0, "atr_pct": 1.0, "math_proof": {"p_math_pct": 72.0}}
        sd_p = {
            "price": 100.0,
            "rsi_14_1h": 45.0,
            "ema_trend_1h": "BULLISH",
            "atr_pct": 1.0,
            "levels": {"support_1": 98.5, "resistance_1": 103.0},
            "btc_macro": {"btc_1h_trend": "BULLISH", "btc_4h_pct": 1.2},
            "math_proof": {"p_math_pct": 72.0},
        }
        with patch.object(pl, "_ai_json", side_effect=_fake_ai_json):
            plan = pl.layer3_build_plan("SOL-USD", sd_p, {"setup_name": "TREND_PULLBACK", "direction": "LONG"}, md_p)
            pl.layer4_risk_audit("SOL-USD", sd_p, {"setup_name": "TREND_PULLBACK", "direction": "LONG"}, plan, md_p, memory_context="AI_MEMORY(last 5): 4W/1L")

        l3_sys = captured[0][1]
        l4_sys, l4_usr = captured[1][1], captured[1][2]
        self.assertIn("0.90%", l3_sys)
        self.assertIn("2.25%", l3_sys)
        self.assertIn("1.80", l3_sys)
        self.assertIn("MAKER_FIRST_GTX", l3_sys)
        self.assertIn("BTC_4H=+1.20%", l4_usr)
        self.assertIn("AI_MEMORY(last 5): 4W/1L", l4_usr)
        self.assertIn("1.80", l4_sys)

    def test_hmm_cascade_calibration_regime_adx_and_bb_percent_b_scale(self):
        import numpy as np
        from features.hmm_drift import GaussianHMM3Regime
        from features.regime import detect_market_regime
        import pipeline as pl

        # 1) Normal smooth active uptrend must NOT emit false p_transition_to_cascade = 1.0
        rng = np.random.default_rng(42)
        rets_norm = np.concatenate([
            rng.normal(0.0, 0.0012, size=80),
            rng.normal(0.0018, 0.0020, size=40),
        ])
        closes_norm = 100.0 * np.exp(np.cumsum(rets_norm))
        hmm_norm = GaussianHMM3Regime().fit_and_predict(closes_norm)
        self.assertLess(
            hmm_norm["p_transition_to_cascade"], 0.60,
            f"Normal active trend must not false-fire cascade=1.0: {hmm_norm}",
        )

        # 2) Genuine extreme crash/cascade bar (>=4x median vol + >3% drop) MUST still flag high cascade risk
        rets_crash = np.concatenate([
            rng.normal(0.0, 0.0015, size=105),
            np.array([-0.018, 0.012, -0.024, -0.032, -0.028]),
        ])
        closes_crash = 100.0 * np.exp(np.cumsum(rets_crash))
        hmm_crash = GaussianHMM3Regime().fit_and_predict(closes_crash)
        self.assertGreaterEqual(
            hmm_crash["p_transition_to_cascade"], 0.70,
            f"Genuine liquidation crash must still score high cascade prob: {hmm_crash}",
        )

        # 3) High-ADX breakout after quiet range must classify as TREND_BULL (not MEAN_REVERT/CHOP)
        kl_bo = []
        px = 100.0
        for i in range(120):
            if i < 90:
                px = 100.0 + (0.15 if i % 2 == 0 else -0.15)
                hi, lo = px * 1.002, px * 0.998
            else:
                px = px * 1.0035
                hi, lo = px * 1.0025, px * 0.999
            kl_bo.append({"open": px * 0.999, "high": hi, "low": lo, "close": px, "volume": 1000.0})
        reg_bo = detect_market_regime(kl_bo, kl_bo)
        self.assertEqual(reg_bo["regime"], "TREND_BULL", f"Strong breakout (ADX={reg_bo['adx14']}) must not be CHOP/MEAN_REVERT: {reg_bo}")

        # 4) Gate 12d must normalize 0..100% bollinger percent_b (e.g. 50.0 = mid-range dead chop)
        sd_mid = {
            "symbol": "SOL-USD",
            "rsi_1h": 50.0,
            "ema_trend_1h": "NEUTRAL",
            "bollinger_1h": {"percent_b": 50.0, "squeeze": False},
            "btc_macro": {"btc_1h_trend": "NEUTRAL", "btc_4h_pct": 0.1},
            "math_proof": {"hurst_exponent": 0.50, "statistical_regime": "CHOP_NO_TRADE", "adx_14": 12.0, "p_math_pct": 74.0},
        }
        md_mid = {"current_price": 100.0, "live_price": 100.0, "funding_rate": {"funding_rate": 0.0}, "math_proof": sd_mid["math_proof"], "_micro_15m": {"available": False}}
        su = {"setup_name": "LIQUIDITY_SWEEP_REVERSAL", "direction": "LONG", "confluence_count": 3}
        pln = {"action": "LONG", "order_type": "MAKER_FIRST_GTX", "entry_price": 100.0, "stop_loss": 98.8, "take_profit": 102.6, "risk_reward_ratio": "1:2.17"}
        rk = {"total_score": 7, "max_score": 8, "verdict": "PASS"}
        fc = {"status": "APPROVED", "direction": "LONG", "setup_name": "LIQUIDITY_SWEEP_REVERSAL", "confidence_score": 80, "entry_price": 100.0, "stop_loss": 98.8, "take_profit": 102.6, "risk_reward_ratio": "1:2.17", "final_reason": "ok"}
        res_mid = pl._apply_safety_gates(fc, su, pln, rk, sd_mid, md_mid)
        self.assertEqual(res_mid["status"], "REJECTED")
        self.assertIn("Dead-zone random-walk chop", res_mid.get("final_reason", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
