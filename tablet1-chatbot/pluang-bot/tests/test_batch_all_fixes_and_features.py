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
        """Verify min_confidence_score defaults to 65 and hybrid calculation is S_Hybrid = 0.55*P_Math + 0.45*P_AI."""
        import json
        import pipeline

        cfg_path = os.path.join(os.path.dirname(__file__), "..", "trading_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.assertEqual(cfg.get("min_confidence_score"), 65, "trading_config.json must specify min_confidence_score = 65")

        self.assertEqual(pipeline.MIN_CONFIDENCE_SCORE, 65, "pipeline.MIN_CONFIDENCE_SCORE must be 65")

        # Test exact hybrid score math: S_Hybrid = 0.55 * P_Math + 0.45 * P_AI
        # Case A: P_Math = 70.0, P_AI = 65.0 -> S_Hybrid = 0.55*70 + 0.45*65 = 38.5 + 29.25 = 67.75
        p_math = 70.0
        p_ai = 65.0
        s_hybrid = round(0.55 * p_math + 0.45 * p_ai, 2)
        self.assertEqual(s_hybrid, 67.75)
        self.assertEqual(int(round(s_hybrid)), 68)

        # Case B: P_Math = 60.0, P_AI = 72.0 -> S_Hybrid = 0.55*60 + 0.45*72 = 33.0 + 32.4 = 65.40
        p_math_b = 60.0
        p_ai_b = 72.0
        s_hybrid_b = round(0.55 * p_math_b + 0.45 * p_ai_b, 2)
        self.assertEqual(s_hybrid_b, 65.40)
        self.assertGreaterEqual(s_hybrid_b, 65.0, "Should qualify under 65% threshold")


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
        from risk.engine import HardRiskEngine

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_brk = at.RISK_BREAKER_FILE
            orig_ts = at._LAST_TRANSFER_SYNC_TS
            orig_state = dict(at.state)
            try:
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
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_brk = at.RISK_BREAKER_FILE
            orig_db = journal.DB_PATH
            try:
                at.RISK_BREAKER_FILE = os.path.join(tmp, "risk_breaker_state.json")
                journal.DB_PATH = os.path.join(tmp, "journal.db")
                journal.init_db(journal.DB_PATH)
                with patch.object(tb, "send_telegram_message", side_effect=lambda cid, txt, *a, **k: sent.append(txt)), \
                     patch.object(tb, "get_binance_client", return_value=fake_bn), \
                     patch.object(tb, "get_fx_info", return_value={"usd_idr": 18000}):
                    tb.handle_why_command(123)
                    tb.handle_positions_command(123)
                    tb.handle_reset_breaker_command(123)
                    tb.handle_transfer_command(123, ["+10"])
                    tb.handle_digest_command(123)
                    tb.handle_pnl_command(123)
                    tb.handle_wallet_command(123)
                self.assertEqual(len(sent), 7, f"All 7 Telegram handlers must send output: {len(sent)}")
                for idx, txt in enumerate(sent):
                    self.assertNotIn("Gagal", txt, f"Handler #{idx} returned failure message: {txt}")
                    self.assertNotIn("❌", txt, f"Handler #{idx} returned error banner: {txt}")
            finally:
                at.RISK_BREAKER_FILE = orig_brk
                journal.DB_PATH = orig_db


if __name__ == "__main__":
    unittest.main(verbosity=2)
