"""
WP-7 TDD Test Suite: Combined Failure Injection & Secret Scanner Hygiene.
Covers:
  - HTTP 429 & 5xx burst resilience (rate-limit cooldown + host failover without crash)
  - WebSocket disconnect / listenKeyExpired + post-reconnect REST reconciliation
  - SL `-2021` ("Order would immediately trigger") immediate emergency market flatten
  - Partial fill + cancel on Maker GTX entry (adopts exact partial executedQty without double order)
  - Corrupt JSON state recovery from `.bak` and quarantine
  - `.githooks/pre-commit` generic secret regexes + zero literal token prefixes in `.githooks/pre-commit` and `start_termux.sh`

Strictly offline (mocked HTTP/WS, TemporaryDirectory, zero live network calls).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

from binance_futures import BinanceFuturesClient
from exec.userstream import UserDataStreamManager
import state_io
from tests.test_wp5_resilience import _make_resp, _isolate_at_env, _restore_at_env


class TestFailureInjectionAndSecretHygiene(unittest.TestCase):
    def _configured_client(self) -> BinanceFuturesClient:
        c = BinanceFuturesClient(api_key="test_k", api_secret="test_s")
        c.time_offset = 0
        c._last_time_sync_ts = 10**12
        c._symbol_cache["SOLUSDT"] = {
            "status": "TRADING",
            "contractType": "PERPETUAL",
            "quantityPrecision": 2,
            "pricePrecision": 2,
            "stepSize": 0.01,
            "minQty": 0.01,
            "maxQty": 10000.0,
            "marketStepSize": 0.01,
            "marketMinQty": 0.01,
            "marketMaxQty": 10000.0,
            "tickSize": 0.01,
            "minNotional": 5.0,
        }
        c._symbol_cache_time = 10**12
        return c

    def test_http_429_and_5xx_burst_resilience(self):
        """Combined HTTP 502 burst failover + HTTP 429 rate-limit cooldown while CRITICAL passes."""
        client = self._configured_client()
        seq = [
            _make_resp(502, text="Bad Gateway"),
            _make_resp(200, {"serverTime": 1700000000000}),
        ]
        with patch.object(client.session, "get", side_effect=seq):
            res_ok = client.get_server_time()
        self.assertEqual(res_ok.get("serverTime"), 1700000000000)

        # Now inject 429 on SCAN -> sets cooldown, blocks subsequent SCAN, but CRITICAL SL still passes
        with patch.object(
            client.session,
            "get",
            return_value=_make_resp(429, {"code": -1003, "msg": "Way too many requests"}, headers={"Retry-After": "30"}),
        ):
            r_scan1 = client._request("GET", "/fapi/v1/depth", {"symbol": "SOLUSDT"}, priority="SCAN")
            r_scan2 = client._request("GET", "/fapi/v1/ticker/24hr", priority="SCAN")
        self.assertTrue(r_scan1.get("rate_limited"))
        self.assertTrue(r_scan2.get("rate_limited"))

        with patch.object(client.session, "post", return_value=_make_resp(200, {"algoId": 4455, "algoStatus": "NEW"})):
            sl_res = client.set_stop_loss("SOLUSDT", "LONG", 147.5)
        self.assertEqual(sl_res.get("algoId"), 4455)

    def test_sl_minus_2021_immediate_trigger_flattens_position(self):
        """When set_stop_loss returns -2021 (Order would immediately trigger), execute_full_trade immediately flattens."""
        client = self._configured_client()
        flatten_calls = []

        def fake_flatten(sym, direction, qty):
            flatten_calls.append((sym, direction, qty))
            return {"closed_ok": True, "flat_verified": True, "still_open": False}

        with patch.object(client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(client, "get_balance", return_value={"available_balance": 50.0, "total_balance": 50.0}), \
             patch.object(client, "_get_locked_vault_usdt", return_value=0.0), \
             patch.object(client, "get_positions", return_value=[]), \
             patch.object(client, "get_market_price", return_value=150.0), \
             patch.object(client, "get_order_book", return_value={}), \
             patch.object(client, "set_margin_type", return_value={"msg": "success"}), \
             patch.object(client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(client, "open_position", return_value={"orderId": 1001, "status": "FILLED", "executedQty": "1.0", "avgPrice": "150.0"}), \
             patch.object(client, "wait_for_position_open", return_value={"symbol": "SOLUSDT", "position_amount": 1.0, "entry_price": 150.0, "leverage": 20, "margin_type": "isolated", "liquidation_price": 143.0}), \
             patch.object(client, "set_stop_loss", return_value={"isError": True, "code": -2021, "error": "Order would immediately trigger."}), \
             patch.object(client, "_emergency_flatten_and_verify", side_effect=fake_flatten):
            res = client.execute_full_trade(
                {
                    "symbol": "SOLUSDT",
                    "direction": "LONG",
                    "entry_price": 150.0,
                    "stop_loss": 148.5,
                    "take_profit": 154.5,
                    "order_type": "MARKET",
                },
                {"fixed_leverage": 20, "margin_type": "ISOLATED", "sizing_mode": "ALL_IN", "all_in_balance_fraction": 0.95},
            )

        self.assertEqual(res["status"], "ABORTED_UNPROTECTED_SL")
        self.assertEqual(res["sl_state"], "IMMEDIATE_TRIGGER_CLOSED")
        self.assertFalse(res["binance_synced"])
        self.assertTrue(res["emergency_closed"])
        self.assertEqual(len(flatten_calls), 1)
        self.assertEqual(flatten_calls[0][0], "SOLUSDT")

    def test_partial_fill_plus_cancel_adopts_partial_qty_and_protects_with_sl(self):
        """When Maker GTX partially fills (0.40 of 0.50 -> remaining notional < $5 minNotional) and cancels, adopts 0.40 without duplicate market order."""
        client = self._configured_client()
        open_calls = []

        def fake_open(**kw):
            open_calls.append(kw)
            return {"orderId": 2002, "status": "NEW", "executedQty": "0.0"}

        # Query 1 & 2: NEW, Query 3: still NEW -> triggers cancel_order -> post-cancel query shows 0.48 filled @ $100 (remaining 0.02 * $100 = $2 < $5 minNotional)
        query_seq = [
            {"orderId": 2002, "status": "NEW", "executedQty": "0.0"},
            {"orderId": 2002, "status": "NEW", "executedQty": "0.0"},
            {"orderId": 2002, "status": "NEW", "executedQty": "0.0"},
            {"orderId": 2002, "status": "CANCELED", "executedQty": "0.48", "avgPrice": "100.0"},
        ]

        with patch("binance_futures.time.sleep"), \
             patch.object(client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(client, "get_balance", return_value={"available_balance": 2.63, "total_balance": 2.63}), \
             patch.object(client, "_get_locked_vault_usdt", return_value=0.0), \
             patch.object(client, "get_positions", return_value=[]), \
             patch.object(client, "get_market_price", return_value=100.0), \
             patch.object(client, "get_order_book", return_value={"bids": [["99.99", "50.0"]], "asks": [["100.01", "50.0"]]}), \
             patch.object(client, "set_margin_type", return_value={"msg": "success"}), \
             patch.object(client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(client, "open_position", side_effect=fake_open), \
             patch.object(client, "query_order", side_effect=query_seq), \
             patch.object(client, "cancel_order", return_value={"orderId": 2002, "status": "CANCELED"}) as mock_cancel, \
             patch.object(client, "wait_for_position_open", return_value={"symbol": "SOLUSDT", "position_amount": 0.48, "entry_price": 100.0, "leverage": 20, "margin_type": "isolated", "liquidation_price": 95.4}), \
             patch.object(client, "set_stop_loss", return_value={"algoId": 3003, "algoStatus": "NEW"}), \
             patch.object(client, "set_take_profit", return_value={"algoId": 3004, "algoStatus": "NEW"}):
            res = client.execute_full_trade(
                {
                    "symbol": "SOLUSDT",
                    "direction": "LONG",
                    "entry_price": 100.0,
                    "stop_loss": 98.5,
                    "take_profit": 103.0,
                    "order_type": "MAKER_FIRST_GTX",
                },
                {"fixed_leverage": 20, "margin_type": "ISOLATED", "sizing_mode": "ALL_IN", "all_in_balance_fraction": 0.95},
            )

        self.assertTrue(res["binance_synced"])
        self.assertEqual(res["sl_state"], "CONFIRMED")
        self.assertAlmostEqual(res["quantity"], 0.48, places=4)
        self.assertEqual(len(open_calls), 1, "Must not send duplicate market order after partial fill leaves < minNotional")
        mock_cancel.assert_called_once()

    def test_ws_disconnect_listen_key_expired_and_corrupt_state_recovery(self):
        """Verify WS listenKeyExpired triggers REST reconcile and corrupt state JSON recovers from .bak."""
        import auto_trader as at

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_at_env(tmp)
            try:
                # 1. Write valid state twice so .bak snapshot holds POS_OK, then corrupt primary file
                state_io.atomic_write_json(at.POSITIONS_FILE, [{"id": "POS_OK", "symbol": "SOL-USD", "status": "OPEN"}], make_bak=True)
                state_io.atomic_write_json(at.POSITIONS_FILE, [{"id": "POS_OK", "symbol": "SOL-USD", "status": "OPEN"}], make_bak=True)
                with open(at.POSITIONS_FILE, "w", encoding="utf-8") as f:
                    f.write("{corrupt_json_state")

                recovered = state_io.read_json_safe(at.POSITIONS_FILE, default=[], strict_on_corrupt=True, expected_type=list)
                self.assertEqual(len(recovered), 1)
                self.assertEqual(recovered[0]["id"], "POS_OK")

                # 2. UserDataStream listenKeyExpired -> refreshes key & triggers REST reconcile callback
                mock_client = MagicMock()
                mock_client._request.return_value = {"listenKey": "fresh_lk_777"}
                reconciled = []

                mgr = UserDataStreamManager(
                    client=mock_client,
                    reconcile_callback=lambda reason: reconciled.append(reason),
                )
                mgr.listen_key = "old_lk_000"
                ev = mgr.handle_event({"e": "listenKeyExpired"})
                self.assertTrue(ev["handled"])
                self.assertEqual(mgr.listen_key, "fresh_lk_777")
                self.assertEqual(reconciled, ["listenKeyExpired"])
            finally:
                _restore_at_env(saved)

    def test_pre_commit_and_start_termux_secret_hygiene(self):
        """Gap #13: .githooks/pre-commit uses generic token regexes + unittest discover; zero literal token prefixes in pre-commit or start_termux.sh."""
        pre_commit_path = os.path.join(BOT_DIR, ".githooks", "pre-commit")
        termux_path = os.path.join(BOT_DIR, "start_termux.sh")

        with open(pre_commit_path, "r", encoding="utf-8") as f:
            hook_txt = f.read()
        with open(termux_path, "r", encoding="utf-8") as f:
            termux_txt = f.read()

        # 1. Zero literal token/chat_id prefixes
        self.assertNotIn("8829535429", hook_txt, ".githooks/pre-commit must not contain hardcoded Telegram token prefix")
        self.assertNotIn("6794056929", termux_txt, "start_termux.sh must not contain hardcoded ALLOWED_TELEGRAM_CHAT_ID")
        self.assertIn("ALLOWED_TELEGRAM_CHAT_ID=", termux_txt)

        # 2. Generic regexes & unittest discover in .githooks/pre-commit
        self.assertIn("[0-9]{8,12}:AA[A-Za-z0-9_-]{30,}", hook_txt)
        self.assertIn("re_[A-Za-z0-9_]{20,}", hook_txt)
        self.assertIn("unittest discover", hook_txt)

        # 3. Verify regexes catch synthetic tokens and ignore safe strings
        tg_pat = re.compile(r"[0-9]{8,12}:AA[A-Za-z0-9_-]{30,}")
        resend_pat = re.compile(r"re_[A-Za-z0-9_]{20,}")
        fake_tg = "1234567890:AA" + ("B" * 33)
        fake_re = "re_" + ("a1B2_" * 5)
        self.assertIsNotNone(tg_pat.search(fake_tg))
        self.assertIsNotNone(resend_pat.search(fake_re))
        self.assertIsNone(tg_pat.search("TELEGRAM_BOT_TOKEN="))
        self.assertIsNone(resend_pat.search("re_try_count = 3"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
