"""
WP-5 TDD Test Suite: API Resilience, Dedicated Heartbeat Thread, Rate-Limit Governor,
Non-Blocking Monitor LLM, Data/TLS Hygiene & WS Reconcile.

Strictly offline (mocked HTTP / mocked WebSocket / TemporaryDirectory).
Covers:
  - Gap #4: HeartbeatWorker 30s thread, dynamic status (HEALTHY / DEGRADED_API / SCAN_STALLED / RATE_LIMITED),
            non-empty heartbeat even with 0 open positions, and start_termux.sh boot cleanup/grace/PID tracking.
  - Gap #5: Operational logging + rate-limited _alert_error_rate_limited helper (zero silent operational swallows).
  - B-13: X-MBX-USED-WEIGHT-1M governor (>= 80% pauses SCAN while CRITICAL passes), HTTP 429/418/-1003 Retry-After
          & cooldown without failover storm, plus market_data.py 429 cooldown.
  - B-14: Non-blocking monitor LLM evaluation via bounded ThreadPoolExecutor(max_workers=2) async future cache.
  - C-3: Periodic 10m server-time resync & recvWindow=5000.
  - C-4: Hedge mode (dualSidePosition=True) rejects new execute_full_trade (REJECTED_HEDGE_MODE_UNSUPPORTED),
         never sends illegal reduceOnly+positionSide together on SL/TP/trailing/close, and keys bn_live_map by (symbol, positionSide).
  - C-8: Remove Spot data-api.binance.vision & dead fapi3, enforce verify=True, reject NaN/Inf/non-positive/all-zero-vol/stale
         candles, remove px_now or 100.0 in pipeline.py, use state_io.atomic_write_json for *_latest.json.
  - C-11: UserDataStreamManager listenKeyExpired + ALGO_UPDATE + reconnect reconcile callback,
          WS 2..30s backoff, dynamic markPrice stream refresh, and post-reconnect REST reconcile.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)


def _make_resp(status_code: int, payload=None, headers=None, text: str = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = dict(headers or {})
    if text is not None:
        resp.text = text
    elif payload is not None:
        resp.text = json.dumps(payload)
    else:
        resp.text = ""
    if payload is not None:
        resp.json.return_value = payload
    else:
        resp.json.side_effect = ValueError("No JSON body")
    return resp


def _isolate_at_env(tmp: str) -> dict:
    import auto_trader as at
    import journal
    import risk.vault as rv

    saved = {
        "RESULTS_DIR": at.RESULTS_DIR,
        "STATE_FILE": at.STATE_FILE,
        "POSITIONS_FILE": at.POSITIONS_FILE,
        "PERF_LEDGER_FILE": at.PERF_LEDGER_FILE,
        "RISK_BREAKER_FILE": at.RISK_BREAKER_FILE,
        "DEGRADED_STRAT_FILE": at.DEGRADED_STRAT_FILE,
        "UNIVERSE_FILE": at.UNIVERSE_FILE,
        "state": dict(at.state),
        "journal_DB_PATH": journal.DB_PATH,
        "rv_DEFAULT": rv.DEFAULT_VAULT_STATE_PATH,
        "ERROR_ALERTS": dict(getattr(at, "_ERROR_ALERT_TIMESTAMPS", {})),
        "AI_FUTURES": dict(getattr(at, "_MONITOR_AI_FUTURES", {})),
        "AI_CACHE": dict(getattr(at, "_MONITOR_AI_CACHE", {})),
    }
    at.RESULTS_DIR = tmp
    at.STATE_FILE = os.path.join(tmp, "autotrader_state.json")
    at.POSITIONS_FILE = os.path.join(tmp, "active_positions.json")
    at.PERF_LEDGER_FILE = os.path.join(tmp, "performance_ledger.json")
    at.RISK_BREAKER_FILE = os.path.join(tmp, "risk_breaker_state.json")
    at.DEGRADED_STRAT_FILE = os.path.join(tmp, "degraded_strategies.json")
    at.UNIVERSE_FILE = os.path.join(tmp, "universe_state.json")
    at._THESIS_MONITOR = None
    if hasattr(at, "_ERROR_ALERT_TIMESTAMPS"):
        at._ERROR_ALERT_TIMESTAMPS.clear()
    if hasattr(at, "_MONITOR_AI_FUTURES"):
        at._MONITOR_AI_FUTURES.clear()
    if hasattr(at, "_MONITOR_AI_CACHE"):
        at._MONITOR_AI_CACHE.clear()
    journal.DB_PATH = os.path.join(tmp, "journal.db")
    journal.init_db(journal.DB_PATH)
    rv.reset_profit_vault_cache()
    rv.DEFAULT_VAULT_STATE_PATH = os.path.join(tmp, "vault_state.json")
    return saved


def _restore_at_env(saved: dict) -> None:
    import auto_trader as at
    import journal
    import risk.vault as rv

    at.RESULTS_DIR = saved["RESULTS_DIR"]
    at.STATE_FILE = saved["STATE_FILE"]
    at.POSITIONS_FILE = saved["POSITIONS_FILE"]
    at.PERF_LEDGER_FILE = saved["PERF_LEDGER_FILE"]
    at.RISK_BREAKER_FILE = saved["RISK_BREAKER_FILE"]
    at.DEGRADED_STRAT_FILE = saved["DEGRADED_STRAT_FILE"]
    at.UNIVERSE_FILE = saved["UNIVERSE_FILE"]
    at.state.clear()
    at.state.update(saved["state"])
    journal.DB_PATH = saved["journal_DB_PATH"]
    rv.reset_profit_vault_cache()
    rv.DEFAULT_VAULT_STATE_PATH = saved["rv_DEFAULT"]
    if hasattr(at, "_ERROR_ALERT_TIMESTAMPS"):
        at._ERROR_ALERT_TIMESTAMPS.clear()
        at._ERROR_ALERT_TIMESTAMPS.update(saved["ERROR_ALERTS"])
    if hasattr(at, "_MONITOR_AI_FUTURES"):
        at._MONITOR_AI_FUTURES.clear()
        at._MONITOR_AI_FUTURES.update(saved["AI_FUTURES"])
    if hasattr(at, "_MONITOR_AI_CACHE"):
        at._MONITOR_AI_CACHE.clear()
        at._MONITOR_AI_CACHE.update(saved["AI_CACHE"])


class TestB13RateLimitGovernor(unittest.TestCase):
    def setUp(self):
        from binance_futures import BinanceFuturesClient

        self.client = BinanceFuturesClient(api_key="k", api_secret="s")
        self.client.time_offset = 0

    def test_weight_80pct_blocks_scan_but_allows_critical_sl_close_positions(self):
        """B-13: At >= 80% of 2400 (>= 1920), SCAN requests pause/reject while SL/close/get_positions pass."""
        calls = []

        def fake_get(url, params=None, timeout=None):
            calls.append(("GET", url))
            if "positionRisk" in url:
                return _make_resp(200, [{"symbol": "SOLUSDT", "positionAmt": "1.0", "entryPrice": "150", "markPrice": "150", "unRealizedProfit": "0", "liquidationPrice": "143", "leverage": "20", "marginType": "isolated", "isolatedMargin": "7.5"}], headers={"X-MBX-USED-WEIGHT-1M": "1950"})
            return _make_resp(200, {"bids": [["149.9", "10"]], "asks": [["150.1", "10"]]}, headers={"X-MBX-USED-WEIGHT-1M": "1950"})

        def fake_post(url, data=None, timeout=None):
            calls.append(("POST", url))
            if "algoOrder" in url:
                return _make_resp(200, {"algoId": 9901, "algoStatus": "NEW"}, headers={"X-MBX-USED-WEIGHT-1M": "1955"})
            return _make_resp(200, {"orderId": 8801, "status": "FILLED"}, headers={"X-MBX-USED-WEIGHT-1M": "1960"})

        with patch.object(self.client.session, "get", side_effect=fake_get), \
             patch.object(self.client.session, "post", side_effect=fake_post):
            # First call reports weight=1950 (>= 1920)
            self.client.get_positions()
            self.assertEqual(self.client.last_used_weight, 1950)

            # Non-critical SCAN request must be rejected locally without hitting HTTP
            before_calls = len(calls)
            scan_res = self.client._request("GET", "/fapi/v1/depth", {"symbol": "SOLUSDT", "limit": 20}, priority="SCAN")
            self.assertTrue(scan_res.get("isError"))
            self.assertTrue(scan_res.get("rate_limited"))
            self.assertEqual(len(calls), before_calls, "SCAN request should not fire HTTP when weight >= 1920")

            # Critical SL, close_position, and get_positions MUST pass!
            self.client._symbol_cache["SOLUSDT"] = {"tickSize": 0.01, "pricePrecision": 2, "stepSize": 0.01, "minQty": 0.01, "quantityPrecision": 2, "minNotional": 5.0}
            self.client._symbol_cache_time = 10**12
            sl_res = self.client.set_stop_loss("SOLUSDT", "LONG", 148.0)
            self.assertEqual(sl_res.get("algoId"), 9901)
            cl_res = self.client.close_position("SOLUSDT", "LONG", quantity=1.0)
            self.assertEqual(cl_res.get("orderId"), 8801)
            pos_res = self.client.get_positions()
            self.assertIsInstance(pos_res, list)

    def test_429_and_418_honor_retry_after_set_cooldown_and_rate_limit_alert(self):
        """B-13: 429/418/-1003 honor Retry-After, set scan cooldown, avoid failover storm, and alert once."""
        alerts = []
        self.client.set_alert_callback(lambda k, msg: alerts.append((k, msg)))
        get_calls = []

        def fake_get_429(url, params=None, timeout=None):
            get_calls.append(url)
            return _make_resp(429, {"code": -1003, "msg": "Too many requests"}, headers={"Retry-After": "42"})

        with patch.object(self.client.session, "get", side_effect=fake_get_429):
            res1 = self.client._request("GET", "/fapi/v1/exchangeInfo", priority="SCAN")
            res2 = self.client._request("GET", "/fapi/v1/depth", {"symbol": "SOLUSDT"}, priority="SCAN")

        self.assertTrue(res1.get("isError"))
        self.assertTrue(res1.get("rate_limited"))
        self.assertGreaterEqual(res1.get("retry_after", 0), 42.0)
        self.assertEqual(len(get_calls), 1, "Must NOT failover across fapi hosts or hit HTTP during cooldown")
        self.assertTrue(res2.get("rate_limited"))
        self.assertEqual(len(alerts), 1, "Rate-limit Telegram alert must be sent once (rate-limited)")

        # 418 IP ban with non-JSON body must also trigger cooldown cleanly without failover storm
        self.client._rate_limit_until_ts = 0.0
        self.client._last_rate_limit_alert_ts = 0.0
        alerts.clear()
        get_calls.clear()

        def fake_get_418(url, params=None, timeout=None):
            get_calls.append(url)
            return _make_resp(418, payload=None, text="<html>banned</html>", headers={"Retry-After": "120"})

        with patch.object(self.client.session, "get", side_effect=fake_get_418):
            res418 = self.client._request("GET", "/fapi/v1/fundingInfo", priority="SCAN")

        self.assertTrue(res418.get("isError"))
        self.assertTrue(res418.get("rate_limited"))
        self.assertEqual(res418.get("http_status"), 418)
        self.assertEqual(len(get_calls), 1)
        self.assertEqual(len(alerts), 1)


class TestC3ClockResyncAndC4HedgeSafety(unittest.TestCase):
    def test_c3_recv_window_5000_and_periodic_10m_time_resync(self):
        """C-3: Default recvWindow=5000 and _sign triggers _sync_server_time every 10 minutes."""
        from binance_futures import BinanceFuturesClient

        c = BinanceFuturesClient(api_key="k", api_secret="s")
        sync_times = []

        def fake_sync():
            sync_times.append(time.time())
            c.time_offset = 123
            c._last_time_sync_ts = 1000.0 if len(sync_times) == 1 else 1605.0
            return 123

        with patch.object(c, "_sync_server_time", side_effect=fake_sync) as mock_sync, \
             patch("binance_futures.time.time", return_value=1000.0):
            signed1 = c._sign({"symbol": "SOLUSDT"})
            self.assertEqual(signed1["recvWindow"], 5000)
            self.assertEqual(mock_sync.call_count, 1)

        # Within 10 minutes (t=1500) -> no extra sync
        with patch.object(c, "_sync_server_time", side_effect=fake_sync) as mock_sync, \
             patch("binance_futures.time.time", return_value=1500.0):
            signed2 = c._sign({"symbol": "SOLUSDT"})
            self.assertEqual(signed2["recvWindow"], 5000)
            self.assertEqual(mock_sync.call_count, 0)

        # Past 10 minutes (t=1605 >= 1000+600) -> triggers periodic resync!
        with patch.object(c, "_sync_server_time", side_effect=fake_sync) as mock_sync, \
             patch("binance_futures.time.time", return_value=1605.0):
            c._sign({"symbol": "SOLUSDT"})
            self.assertEqual(mock_sync.call_count, 1)

    def test_c4_hedge_mode_rejects_new_entry_and_fixes_reduce_only_position_side(self):
        """C-4: Hedge mode blocks execute_full_trade & omits reduceOnly when positionSide is set."""
        from binance_futures import BinanceFuturesClient

        c = BinanceFuturesClient(api_key="k", api_secret="s")
        c.time_offset = 0
        c._symbol_cache["SOLUSDT"] = {
            "status": "TRADING", "contractType": "PERPETUAL",
            "quantityPrecision": 2, "pricePrecision": 2,
            "stepSize": 0.01, "minQty": 0.01, "tickSize": 0.01, "minNotional": 5.0,
        }
        c._symbol_cache_time = 10**12

        # 1. execute_full_trade rejects Hedge mode cleanly
        with patch.object(c, "check_account_modes", return_value={"dualSidePosition": True, "multiAssetsMargin": False, "ok": True}), \
             patch.object(c, "open_position") as mock_open:
            res = c.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.5, "take_profit": 154.0},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )
        self.assertEqual(res["status"], "REJECTED_HEDGE_MODE_UNSUPPORTED")
        self.assertFalse(res["binance_synced"])
        mock_open.assert_not_called()

        # 2. Existing open position protection in Hedge mode NEVER sends reduceOnly alongside positionSide!
        c.dual_side_position = True
        sent_payloads = []

        def fake_req(method, endpoint, params=None, signed=False, **kw):
            sent_payloads.append((method, endpoint, dict(params or {})))
            if endpoint == "/fapi/v2/positionRisk":
                return [
                    {"symbol": "SOLUSDT", "positionSide": "LONG", "positionAmt": "2.0", "entryPrice": "150", "markPrice": "150", "unRealizedProfit": "0", "liquidationPrice": "143", "leverage": "20", "marginType": "isolated", "isolatedMargin": "15"},
                    {"symbol": "SOLUSDT", "positionSide": "SHORT", "positionAmt": "-1.5", "entryPrice": "152", "markPrice": "150", "unRealizedProfit": "3", "liquidationPrice": "160", "leverage": "20", "marginType": "isolated", "isolatedMargin": "11.4"},
                ]
            if endpoint == "/fapi/v1/algoOrder":
                return {"algoId": 7771}
            return {"orderId": 8881, "status": "FILLED"}

        with patch.object(c, "_request", side_effect=fake_req):
            c.set_stop_loss("SOLUSDT", "SHORT", 155.0, quantity=1.5)
            c.set_take_profit("SOLUSDT", "SHORT", 145.0, quantity=1.5)
            c.set_trailing_stop("SOLUSDT", "SHORT", 1.0, quantity=1.5)
            c.close_position("SOLUSDT", "SHORT")

        order_reqs = [p for m, ep, p in sent_payloads if m == "POST"]
        self.assertEqual(len(order_reqs), 4)
        for payload in order_reqs:
            self.assertEqual(payload.get("positionSide"), "SHORT")
            self.assertNotIn("reduceOnly", payload, f"Illegal reduceOnly sent with positionSide in Hedge Mode: {payload}")
        # close_position for SHORT leg must pick SHORT qty=1.5, not LONG qty=2.0!
        self.assertEqual(order_reqs[3]["quantity"], 1.5)

    def test_c4_auto_trader_keys_live_map_by_symbol_and_position_side(self):
        """C-4: auto_trader monitor keys bn_live_map by (symbol, positionSide) so opposite hedge legs don't overwrite or trap."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_at_env(tmp)
            try:
                p_long = {
                    "id": "HEDGE_L", "symbol": "SOL-USD", "binance_pair": "SOLUSDT", "direction": "LONG",
                    "position_side": "LONG", "entry_price": 150.0, "stop_loss": 148.0, "init_stop_loss": 148.0,
                    "take_profit": 154.0, "leverage": 20, "position_size_usd": 15.0, "position_size_idr": 247500,
                    "status": "OPEN", "exchange": "BINANCE_FUTURES", "binance_synced": True, "sl_state": "CONFIRMED",
                    "opened_ts": time.time() - 60,
                }
                p_short = {
                    "id": "HEDGE_S", "symbol": "SOL-USD", "binance_pair": "SOLUSDT", "direction": "SHORT",
                    "position_side": "SHORT", "entry_price": 152.0, "stop_loss": 154.0, "init_stop_loss": 154.0,
                    "take_profit": 148.0, "leverage": 20, "position_size_usd": 11.4, "position_size_idr": 188100,
                    "status": "OPEN", "exchange": "BINANCE_FUTURES", "binance_synced": True, "sl_state": "CONFIRMED",
                    "opened_ts": time.time() - 60,
                }
                state_io.atomic_write_json(at.POSITIONS_FILE, [p_long, p_short], make_bak=False)

                class MockHedgeBN:
                    def get_positions(self, symbol=None):
                        return [
                            {"symbol": "SOLUSDT", "position_side": "LONG", "direction": "LONG", "position_amount": 2.0, "entry_price": 150.0, "mark_price": 150.1, "unrealized_pnl": 2.0, "liquidation_price": 143.0, "isolated_margin": 15.0, "leverage": 20},
                            {"symbol": "SOLUSDT", "position_side": "SHORT", "direction": "SHORT", "position_amount": 1.5, "entry_price": 152.0, "mark_price": 151.9, "unrealized_pnl": 1.5, "liquidation_price": 160.0, "isolated_margin": 11.4, "leverage": 20},
                        ]

                    def verify_stop_loss_active(self, *a, **kw):
                        return "CONFIRMED"

                with patch.object(at, "get_binance_client", return_value=MockHedgeBN()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[]), \
                     patch.object(at, "_fetch_live_micro_state", return_value={"ofi_20": 0.0, "tfi_5m": 0.0, "sigma": 0.35}), \
                     patch("exec.thesis_monitor.IntrabarThesisMonitor.evaluate_position", return_value={"p_survive": 0.7, "should_scratch": False, "consecutive_breaches": 0}):
                    res = at.monitor_and_update_positions()

                by_id = {p["id"]: p for p in res}
                self.assertEqual(by_id["HEDGE_L"]["status"], "OPEN")
                self.assertEqual(by_id["HEDGE_S"]["status"], "OPEN")
                self.assertEqual(by_id["HEDGE_L"]["unrealized_pnl"], 2.0)
                self.assertEqual(by_id["HEDGE_S"]["unrealized_pnl"], 1.5)
            finally:
                _restore_at_env(saved)


class TestGap4HeartbeatAndWatchdog(unittest.TestCase):
    def test_heartbeat_worker_writes_atomic_fields_and_dynamic_status(self):
        """Gap #4: HeartbeatWorker writes atomic heartbeat.json with pid/boot_ts/timestamps/dynamic status."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_at_env(tmp)
            try:
                hb_path = os.path.join(tmp, "heartbeat.json")
                at.update_runtime_health(
                    boot_ts=1000.0,
                    last_api_ok_ts=1050.0,
                    last_api_err_ts=0.0,
                    ws_last_msg_ts=1048.0,
                    last_scan_ts=1040.0,
                    last_monitor_ts=1050.0,
                )

                with patch("auto_trader.time.time", return_value=1060.0):
                    worker = at.HeartbeatWorker(interval_sec=30.0, heartbeat_path=hb_path)
                    ok = worker.write_once()
                self.assertTrue(ok)
                hb = state_io.read_json_safe(hb_path, default={}, strict_on_corrupt=True)
                for req_k in ("timestamp", "utc", "pid", "boot_ts", "last_api_ok_ts", "ws_last_msg_ts", "last_scan_ts", "last_monitor_ts", "open_positions", "ws_active", "status"):
                    self.assertIn(req_k, hb)
                self.assertEqual(hb["pid"], os.getpid())
                self.assertEqual(hb["status"], "HEALTHY")

                # API failure newer than last_api_ok_ts beyond grace -> DEGRADED_API
                at.update_runtime_health(last_api_err_ts=1200.0)
                with patch("auto_trader.time.time", return_value=1250.0):
                    worker.write_once()
                hb_deg = state_io.read_json_safe(hb_path, default={}, strict_on_corrupt=True)
                self.assertEqual(hb_deg["status"], "DEGRADED_API")

                # API recovered, but scanner stalled -> SCAN_STALLED
                at.update_runtime_health(last_api_ok_ts=2000.0, last_monitor_ts=2000.0, last_scan_ts=1000.0)
                at.state["is_running"] = True
                at.state["status"] = "RUNNING"
                at.state["scan_interval_sec"] = 300
                at.state["all_in_monitoring_mode"] = False
                with patch("auto_trader.time.time", return_value=2010.0):
                    worker.write_once()
                hb_stall = state_io.read_json_safe(hb_path, default={}, strict_on_corrupt=True)
                self.assertEqual(hb_stall["status"], "SCAN_STALLED")

                # Start & cleanly stop daemon thread
                worker_bg = at.HeartbeatWorker(interval_sec=0.05, heartbeat_path=hb_path)
                worker_bg.start()
                time.sleep(0.08)
                self.assertTrue(worker_bg.is_alive())
                worker_bg.stop(timeout=2.0)
                self.assertFalse(worker_bg.is_alive())
            finally:
                _restore_at_env(saved)

    def test_start_termux_sh_boot_cleanup_grace_and_pid_watchdog(self):
        """Gap #4: start_termux.sh clears stale heartbeat on boot, waits >=120s grace, and tracks SRV_PID/TG_PID/BOT_PID without pkill -f."""
        sh_path = os.path.join(BOT_DIR, "start_termux.sh")
        with open(sh_path, "r", encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("rm -f", txt)
        self.assertIn("heartbeat.json", txt)
        self.assertRegex(txt, r"STARTUP_GRACE_SEC=1[2-9][0-9]|STARTUP_GRACE_SEC=[2-9][0-9]{2}|UPTIME.*120")
        self.assertIn("SRV_PID", txt)
        self.assertIn("TG_PID", txt)
        self.assertIn("BOT_PID", txt)
        self.assertNotIn("pkill -9 -f", txt)


class TestB14NonBlockingMonitorLLMAndGap5Alerts(unittest.TestCase):
    def test_b14_slow_llm_does_not_block_monitor_loop(self):
        """B-14: Slow call_ai (1.5s) is offloaded to bounded ThreadPoolExecutor so monitor_and_update_positions returns in <200ms."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_at_env(tmp)
            try:
                pos = {
                    "id": "POS_B14", "symbol": "SOL-USD", "binance_pair": "SOLUSDT", "direction": "LONG",
                    "entry_price": 150.0, "stop_loss": 148.5, "init_stop_loss": 148.5, "take_profit": 154.5,
                    "leverage": 20, "position_size_usd": 50.0, "position_size_idr": 825000,
                    "status": "OPEN", "exchange": "BINANCE_FUTURES", "binance_synced": True, "sl_state": "CONFIRMED",
                    "opened_ts": time.time() - 60, "last_ai_eval_ts": 0,
                }
                state_io.atomic_write_json(at.POSITIONS_FILE, [pos], make_bak=False)

                class MockBNFast:
                    def get_positions(self, symbol=None):
                        return [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 2.0, "entry_price": 150.0, "mark_price": 150.2, "unrealized_pnl": 0.4, "liquidation_price": 143.0, "isolated_margin": 50.0, "leverage": 20}]

                    def verify_stop_loss_active(self, *a, **kw):
                        return "CONFIRMED"

                ai_release = threading.Event()

                def slow_ai(*a, **kw):
                    ai_release.wait(timeout=2.0)
                    return "HOLD: Struktur bullish terjaga, pertahankan SL."

                with patch.object(at, "get_binance_client", return_value=MockBNFast()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[]), \
                     patch.object(at, "_fetch_live_micro_state", return_value={"ofi_20": 0.1, "tfi_5m": 0.1, "sigma": 0.35}), \
                     patch("exec.thesis_monitor.IntrabarThesisMonitor.evaluate_position", return_value={"p_survive": 0.8, "should_scratch": False, "consecutive_breaches": 0}), \
                     patch("news_sentinel.get_news_sentiment_summary", return_value={"market_sentiment": "NEUTRAL"}), \
                     patch.object(at, "call_ai", side_effect=slow_ai):
                    t0 = time.perf_counter()
                    res1 = at.monitor_and_update_positions()
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    self.assertLess(elapsed_ms, 250.0, f"Monitor blocked for {elapsed_ms:.1f}ms on slow LLM!")
                    self.assertEqual(len(res1), 1)

                    # Release slow AI and confirm future completes & gets harvested cleanly
                    ai_release.set()
                    fut_entry = at._MONITOR_AI_FUTURES.get("POS_B14")
                    if fut_entry and fut_entry.get("future"):
                        fut_entry["future"].result(timeout=2.0)
                    res2 = at.monitor_and_update_positions()
                    self.assertIn("HOLD: Struktur bullish", res2[0].get("ai_evaluation", ""))
            finally:
                _restore_at_env(saved)

    def test_gap5_rate_limited_error_alert_and_logging(self):
        """Gap #5: _alert_error_rate_limited logs and throttles repeated Telegram alerts within cooldown."""
        import auto_trader as at

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_at_env(tmp)
            try:
                with patch.object(at, "send_telegram") as mock_tg, \
                     self.assertLogs("auto_trader", level="ERROR"):
                    sent1 = at._alert_error_rate_limited("SYNC_FAIL", "Sync error 1", cooldown_sec=60.0)
                    sent2 = at._alert_error_rate_limited("SYNC_FAIL", "Sync error 2", cooldown_sec=60.0)
                    sent3 = at._alert_error_rate_limited("OTHER_FAIL", "Other error", cooldown_sec=60.0)
                self.assertTrue(sent1)
                self.assertFalse(sent2)
                self.assertTrue(sent3)
                self.assertEqual(mock_tg.call_count, 2)
            finally:
                _restore_at_env(saved)


class TestC8DataHygieneAndTLS(unittest.TestCase):
    def tearDown(self):
        import market_data as md

        if hasattr(md, "_MARKET_RATE_LIMIT_UNTIL"):
            md._MARKET_RATE_LIMIT_UNTIL = 0.0
        if hasattr(md, "_MARKET_RATE_LIMIT_STREAK"):
            md._MARKET_RATE_LIMIT_STREAK = 0

    def test_c8_no_spot_urls_no_fapi3_and_verify_true_across_files(self):
        """C-8: Zero data-api.binance.vision, zero fapi3.binance.com, zero verify=False in WP-5 files."""
        for rel in ("market_data.py", "auto_trader.py", "pipeline.py"):
            with open(os.path.join(BOT_DIR, rel), "r", encoding="utf-8") as f:
                txt = f.read()
            self.assertNotIn("data-api.binance.vision", txt, msg=rel)
            self.assertNotIn("fapi3.binance.com", txt, msg=rel)
            self.assertNotIn("verify=False", txt, msg=rel)

    def test_c8_market_data_rejects_nan_inf_non_positive_zero_vol_stale_and_429_backoff(self):
        """C-8 & B-13: get_binance_klines validates finite/positive/volume/freshness and respects 429 cooldown."""
        import market_data as md

        now_ms = int(time.time() * 1000)

        def _row(close_px, vol="100.0", close_offset_ms=-60_000):
            ct = now_ms + close_offset_ms
            return [ct - 3600_000 + 1, "100.0", str(max(101.0, float(close_px) if str(close_px) not in ("NaN", "inf", "-inf") else 101.0)), "99.0", str(close_px), str(vol), ct, "10000", 10, "50", "5000", "0"]

        # 1. NaN close -> rejected
        with patch("market_data.requests.get", return_value=_make_resp(200, [_row("NaN"), _row("101.0")])):
            self.assertIsNone(md.get_binance_klines("SOLUSDT", "1h", limit=2))

        # 2. Inf volume -> rejected
        with patch("market_data.requests.get", return_value=_make_resp(200, [_row("101.0", "inf"), _row("102.0", "100")])):
            self.assertIsNone(md.get_binance_klines("SOLUSDT", "1h", limit=2))

        # 3. Non-positive price -> rejected
        with patch("market_data.requests.get", return_value=_make_resp(200, [_row("0"), _row("102.0")])):
            self.assertIsNone(md.get_binance_klines("SOLUSDT", "1h", limit=2))

        # 4. All-zero volume -> rejected
        with patch("market_data.requests.get", return_value=_make_resp(200, [_row("101.0", "0"), _row("102.0", "0")])):
            self.assertIsNone(md.get_binance_klines("SOLUSDT", "1h", limit=2))

        # 5. Stale candles (> 2 intervals old) -> rejected when check_freshness=True
        stale_offset = -5 * 3600_000
        with patch("market_data.requests.get", return_value=_make_resp(200, [_row("101.0", "100", stale_offset), _row("102.0", "100", stale_offset)])):
            self.assertIsNone(md.get_binance_klines("SOLUSDT", "1h", limit=2, check_freshness=True))

        # 6. HTTP 429 triggers cooldown without looping all endpoints
        get_calls = []

        def fake_429(*a, **kw):
            get_calls.append(a[0])
            return _make_resp(429, {"code": -1003}, headers={"Retry-After": "30"})

        with patch("market_data.requests.get", side_effect=fake_429):
            res_429 = md.get_binance_klines("SOLUSDT", "1h", limit=2)
            res_cool = md.get_binance_klines("ETHUSDT", "1h", limit=2)
        self.assertIsNone(res_429)
        self.assertIsNone(res_cool)
        self.assertEqual(len(get_calls), 1, "429 in market_data must break loop & apply cooldown")

    def test_c8_pipeline_removes_fake_100_price_and_uses_atomic_write(self):
        """C-8: pipeline fails safely on missing price (never 100.0) and writes *_latest.json atomically."""
        import pipeline as pl

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_res = pl.RESULTS_DIR
            try:
                pl.RESULTS_DIR = tmp
                # 1. Missing price -> FAILED (never synthetic $100)
                bad_md = {"current_price": 0.0, "live_price": None, "atr_pct": 1.0}
                bad_scan = {"symbol": "FAKE-USD", "price": 0.0}
                with patch.object(pl, "layer1_scanning", return_value=(bad_md, bad_scan)), \
                     patch.object(pl, "layer2_setup_hunter", return_value={"setup_name": "NO_CLEAR_SETUP", "direction": "NONE"}):
                    out_bad = pl.run_5_layer_pipeline("FAKE-USD")
                self.assertEqual(out_bad["status"], "FAILED")
                self.assertIn("PRICE", out_bad.get("error", "").upper())

                # 2. Valid NO_CLEAR_SETUP writes *_latest.json via state_io.atomic_write_json
                good_md = {"current_price": 150.0, "live_price": 150.0, "atr_pct": 1.0}
                good_scan = {"symbol": "SOL-USD", "price": 150.0}
                with patch.object(pl, "layer1_scanning", return_value=(good_md, good_scan)), \
                     patch.object(pl, "layer2_setup_hunter", return_value={"setup_name": "NO_CLEAR_SETUP", "direction": "NONE"}), \
                     patch("state_io.atomic_write_json", wraps=__import__("state_io").atomic_write_json) as mock_aw:
                    out_ok = pl.run_5_layer_pipeline("SOL-USD")
                self.assertEqual(out_ok["status"], "REJECTED")
                latest_path = os.path.join(tmp, "SOL_USD_latest.json")
                self.assertTrue(os.path.exists(latest_path))
                self.assertTrue(any(os.path.abspath(c.args[0]) == os.path.abspath(latest_path) for c in mock_aw.call_args_list))
            finally:
                pl.RESULTS_DIR = orig_res


class TestC11WSReconcileAndUserstream(unittest.TestCase):
    def test_c11_userstream_handles_listen_key_expired_and_algo_update(self):
        """C-11: UserDataStreamManager handles listenKeyExpired, refreshes key, sets reconnect_requested, invokes reconcile callback."""
        from exec.userstream import UserDataStreamManager

        reconcile_reasons = []
        mock_client = MagicMock()
        mock_client._request.return_value = {"listenKey": "lk_fresh_999"}

        mgr = UserDataStreamManager(
            client=mock_client,
            reconcile_callback=lambda reason: reconcile_reasons.append(reason),
        )
        mgr.listen_key = "lk_stale_111"
        mgr.register_tracked_position("SOLUSDT", "LONG", 150.0, 148.5, 154.5, 2.0)

        res_exp = mgr.handle_event({"e": "listenKeyExpired", "E": 1700000000000})
        self.assertTrue(res_exp["handled"])
        self.assertTrue(res_exp["reconnect_required"])
        self.assertTrue(mgr.reconnect_requested.is_set())
        self.assertEqual(mgr.listen_key, "lk_fresh_999")
        self.assertEqual(reconcile_reasons, ["listenKeyExpired"])

        # ALGO_UPDATE CANCELLED (double-L spelling) -> sl_state MISSING
        res_algo = mgr.handle_event({
            "e": "ALGO_UPDATE",
            "o": {"s": "SOLUSDT", "aid": 555, "X": "CANCELLED", "o": "STOP_MARKET", "tp": "148.5"},
        })
        self.assertTrue(res_algo["handled"])
        self.assertEqual(res_algo["sl_state"], "MISSING")
        self.assertEqual(mgr.active_positions["SOLUSDT"]["sl_state"], "MISSING")

    def test_c11_auto_trader_dynamic_mark_streams_and_reconnect_reconcile(self):
        """C-11: WS helper builds dynamic markPrice streams from OPEN positions and triggers REST reconcile."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_at_env(tmp)
            try:
                state_io.atomic_write_json(at.POSITIONS_FILE, [
                    {"id": "P1", "symbol": "SOL-USD", "binance_pair": "SOLUSDT", "status": "OPEN"},
                    {"id": "P2", "symbol": "ETH-USD", "binance_pair": "ETHUSDT", "status": "CLOSED_TP"},
                ], make_bak=False)
                streams = at._get_open_ws_mark_streams()
                self.assertEqual(streams, ["solusdt@markPrice@1s"])

                # Adding a second OPEN position updates dynamic stream list
                state_io.atomic_write_json(at.POSITIONS_FILE, [
                    {"id": "P1", "symbol": "SOL-USD", "binance_pair": "SOLUSDT", "status": "OPEN"},
                    {"id": "P3", "symbol": "XRP-USD", "binance_pair": "XRPUSDT", "status": "OPEN"},
                ], make_bak=False)
                streams2 = at._get_open_ws_mark_streams()
                self.assertEqual(streams2, ["solusdt@markPrice@1s", "xrpusdt@markPrice@1s"])

                # Post-reconnect reconcile calls monitor_and_update_positions & sets wakeup event
                at._WS_WAKEUP_EVENT.clear()
                with patch.object(at, "monitor_and_update_positions", return_value=[]) as mock_mon:
                    rec_out = at._reconcile_after_ws_reconnect(MagicMock(), reason="listenKeyExpired")
                self.assertTrue(rec_out["reconciled"])
                self.assertTrue(at._WS_WAKEUP_EVENT.is_set())
                mock_mon.assert_called_once()
            finally:
                _restore_at_env(saved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
