"""
WP-1 TDD Test Suite: Binance Futures Order Execution Safety & record_position Handoff.

Covers strictly offline (mocked HTTP / mocked client, zero live network or keys):
  - A-1: Idempotent order writes (clientOrderId/clientAlgoId injection <= 36 chars,
         pre-failover GET lookup on ambiguous 5xx/timeout/connection reset)
  - C-1 & A-2: check_account_modes error handling, Multi-Assets CROSS rejection,
         strict set_margin_type (-4046 allowed, -4168/-4047/-4048/network rejected),
         pre-sizing set_leverage capture & proportional resize on exchange cap,
         post-fill positionRisk marginType/leverage mismatch -> emergency reduceOnly close
  - B-1: Refuse trade on failed get_positions() check (REJECTED_POSITION_CHECK_ERROR)
  - C-2: Fail-closed symbol filters on exchangeInfo error or missing symbol,
         retry cooldown without infinite spin, status==TRADING & contractType==PERPETUAL,
         MARKET_LOT_SIZE & LOT_SIZE.maxQty, budget/max check after minQty bump
  - A-7: True fill verification via executedQty + positionRisk delta (zero phantom positions
         on CANCELED/EXPIRED 0-fill, maker_only_no_taker_fallback honored, partial fill synced)
  - A-6 & B-11: SL-first (closePosition=true without quantity) before TP,
         -2021 immediate close (NO 1.5% loosening!), mandatory reduceOnly close + flat verify
         on 3x SL failure (ABORTED_UNPROTECTED_SL, zero LOCAL_GUARD_MONITORED)
  - B-2: Post-fill exception recovery via positionRisk (EXECUTED_RECOVERY_PROTECTED vs
         ABORTED_UNPROTECTED_SL)
  - auto_trader.record_position handoff: sync effective leverage/margin/qty/tca_fee/sl_state,
         emergency-closed vs open recovery handling
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

from binance_futures import BinanceFuturesClient


def _make_resp(status_code: int, payload, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = json.dumps(payload)
    resp.json.return_value = payload
    return resp


def _exchange_info_payload(
    symbol: str = "SOLUSDT",
    status: str = "TRADING",
    contract_type: str = "PERPETUAL",
    step_size: str = "0.01",
    min_qty: str = "0.01",
    max_qty: str = "10000",
    mkt_step_size: str = "0.01",
    mkt_min_qty: str = "0.01",
    mkt_max_qty: str = "5000",
    tick_size: str = "0.01",
    min_notional: str = "5",
    qty_prec: int = 2,
    px_prec: int = 2,
):
    return {
        "symbols": [
            {
                "symbol": symbol,
                "status": status,
                "contractType": contract_type,
                "quantityPrecision": qty_prec,
                "pricePrecision": px_prec,
                "filters": [
                    {
                        "filterType": "LOT_SIZE",
                        "stepSize": step_size,
                        "minQty": min_qty,
                        "maxQty": max_qty,
                    },
                    {
                        "filterType": "MARKET_LOT_SIZE",
                        "stepSize": mkt_step_size,
                        "minQty": mkt_min_qty,
                        "maxQty": mkt_max_qty,
                    },
                    {
                        "filterType": "PRICE_FILTER",
                        "tickSize": tick_size,
                    },
                    {
                        "filterType": "MIN_NOTIONAL",
                        "notional": min_notional,
                    },
                ],
            }
        ]
    }


def _seed_symbol(client: BinanceFuturesClient, symbol: str = "SOLUSDT", **overrides):
    data = {
        "status": "TRADING",
        "contractType": "PERPETUAL",
        "quantityPrecision": 2,
        "pricePrecision": 2,
        "stepSize": 0.01,
        "minQty": 0.01,
        "maxQty": 10000.0,
        "marketStepSize": 0.01,
        "marketMinQty": 0.01,
        "marketMaxQty": 5000.0,
        "tickSize": 0.01,
        "minNotional": 5.0,
    }
    data.update(overrides)
    client._symbol_cache[symbol] = data
    client._symbol_cache_time = 10**12


class TestA1IdempotentWrites(unittest.TestCase):
    def setUp(self):
        self.client = BinanceFuturesClient(api_key="k", api_secret="s")
        self.client.time_offset = 0

    def test_post_order_injects_cid_and_recovers_before_failover(self):
        """A-1: Timeout/502 on fapi.binance.com queries GET /order; if found, NEVER POSTs to fapi1."""
        post_calls = []
        get_calls = []

        def fake_post(url, data=None, timeout=None):
            post_calls.append((url, dict(data or {})))
            raise requests.Timeout("read timed out")

        def fake_get(url, params=None, timeout=None):
            get_calls.append((url, dict(params or {})))
            cid = (params or {}).get("origClientOrderId")
            return _make_resp(200, {
                "orderId": 888001,
                "symbol": "SOLUSDT",
                "status": "FILLED",
                "executedQty": "1.5",
                "avgPrice": "150.0",
                "clientOrderId": cid,
            })

        with patch.object(self.client.session, "post", side_effect=fake_post), \
             patch.object(self.client.session, "get", side_effect=fake_get):
            res = self.client._request(
                "POST",
                "/fapi/v1/order",
                {"symbol": "SOLUSDT", "side": "BUY", "type": "MARKET", "quantity": 1.5},
                signed=True,
            )

        self.assertEqual(res.get("orderId"), 888001)
        self.assertEqual(len(post_calls), 1, "Must NOT duplicate POST to fapi1 once GET confirms order exists")
        injected_cid = post_calls[0][1].get("newClientOrderId")
        self.assertTrue(injected_cid)
        self.assertLessEqual(len(injected_cid), 36)
        self.assertEqual(len(get_calls), 1)
        self.assertEqual(get_calls[0][1].get("origClientOrderId"), injected_cid)

    def test_post_order_502_failover_reuses_identical_cid_when_not_found(self):
        """A-1: If GET returns -2013 (not found), failover to fapi1 reuses exact same newClientOrderId."""
        post_calls = []

        def fake_post(url, data=None, timeout=None):
            post_calls.append((url, dict(data or {})))
            if "fapi.binance.com" in url:
                return _make_resp(502, {"msg": "Bad Gateway"})
            return _make_resp(200, {
                "orderId": 888002,
                "symbol": "SOLUSDT",
                "status": "FILLED",
                "executedQty": "1.5",
                "clientOrderId": data.get("newClientOrderId"),
            })

        def fake_get(url, params=None, timeout=None):
            return _make_resp(400, {"code": -2013, "msg": "Order does not exist."})

        with patch.object(self.client.session, "post", side_effect=fake_post), \
             patch.object(self.client.session, "get", side_effect=fake_get):
            res = self.client._request(
                "POST",
                "/fapi/v1/order",
                {
                    "symbol": "SOLUSDT",
                    "side": "BUY",
                    "type": "MARKET",
                    "quantity": 1.5,
                    "newClientOrderId": "caller_supplied_id_12345",
                },
                signed=True,
            )

        self.assertEqual(res.get("orderId"), 888002)
        self.assertEqual(len(post_calls), 2)
        self.assertEqual(post_calls[0][1]["newClientOrderId"], "caller_supplied_id_12345")
        self.assertEqual(post_calls[1][1]["newClientOrderId"], "caller_supplied_id_12345")

    def test_post_algo_order_injects_client_algo_id_and_recovers(self):
        """A-1: Ambiguous 503 on POST /algoOrder checks openAlgoOrders by clientAlgoId before failover."""
        post_calls = []

        def fake_post(url, data=None, timeout=None):
            post_calls.append((url, dict(data or {})))
            return _make_resp(503, {"msg": "Service Unavailable"})

        def fake_get(url, params=None, timeout=None):
            caid = post_calls[0][1].get("clientAlgoId")
            return _make_resp(200, [{
                "algoId": 777001,
                "symbol": "SOLUSDT",
                "clientAlgoId": caid,
                "orderType": "STOP_MARKET",
                "algoStatus": "NEW",
            }])

        with patch.object(self.client.session, "post", side_effect=fake_post), \
             patch.object(self.client.session, "get", side_effect=fake_get):
            res = self.client._request(
                "POST",
                "/fapi/v1/algoOrder",
                {"algoType": "CONDITIONAL", "symbol": "SOLUSDT", "side": "SELL", "type": "STOP_MARKET", "triggerPrice": "148.0", "closePosition": "true"},
                signed=True,
            )

        self.assertEqual(res.get("algoId"), 777001)
        self.assertEqual(len(post_calls), 1)
        caid = post_calls[0][1].get("clientAlgoId")
        self.assertTrue(caid)
        self.assertLessEqual(len(caid), 36)

    def test_delete_order_ambiguous_checks_already_canceled(self):
        """A-1: Ambiguous ConnectionError on DELETE /order checks GET /order before failover."""
        del_calls = []

        def fake_delete(url, params=None, timeout=None):
            del_calls.append((url, dict(params or {})))
            raise requests.ConnectionError("reset by peer")

        def fake_get(url, params=None, timeout=None):
            return _make_resp(200, {"orderId": 555, "symbol": "SOLUSDT", "status": "CANCELED"})

        with patch.object(self.client.session, "delete", side_effect=fake_delete), \
             patch.object(self.client.session, "get", side_effect=fake_get):
            res = self.client._request("DELETE", "/fapi/v1/order", {"symbol": "SOLUSDT", "orderId": 555}, signed=True)

        self.assertEqual(res.get("status"), "CANCELED")
        self.assertEqual(len(del_calls), 1)

    def test_delete_algo_order_ambiguous_and_4116_duplicate_recovery(self):
        """A-1: Ambiguous 502 on DELETE /algoOrder confirms absence via openAlgoOrders; -4116 recovers existing order."""
        del_calls = []

        def fake_del(url, params=None, timeout=None):
            del_calls.append(url)
            return _make_resp(502, {"msg": "Bad Gateway"})

        with patch.object(self.client.session, "delete", side_effect=fake_del), \
             patch.object(self.client.session, "get", return_value=_make_resp(200, [])):
            res_del = self.client._request("DELETE", "/fapi/v1/algoOrder", {"symbol": "SOLUSDT", "algoId": 444}, signed=True)

        self.assertEqual(res_del.get("algoStatus"), "CANCELED")
        self.assertTrue(res_del.get("idempotent_confirmed"))
        self.assertEqual(len(del_calls), 1)

        # -4116 on POST /order recovers existing order via GET /order
        with patch.object(self.client.session, "post", return_value=_make_resp(400, {"code": -4116, "msg": "ClientOrderId is duplicated."})), \
             patch.object(self.client.session, "get", return_value=_make_resp(200, {"orderId": 888999, "status": "FILLED"})):
            res_dup = self.client._request(
                "POST",
                "/fapi/v1/order",
                {"symbol": "SOLUSDT", "side": "BUY", "type": "MARKET", "quantity": 1.0, "newClientOrderId": "dup_cid_1"},
                signed=True,
            )
        self.assertEqual(res_dup.get("orderId"), 888999)


class TestC1AndA2ModesMarginLeverage(unittest.TestCase):
    def setUp(self):
        self.client = BinanceFuturesClient(api_key="k", api_secret="s")
        self.client.time_offset = 0
        _seed_symbol(self.client, "SOLUSDT")

    def test_c1_check_account_modes_only_caches_when_both_succeed(self):
        """C-1: Failed positionSide/dual or multiAssetsMargin must NOT set _account_mode_checked=True."""
        with patch.object(
            self.client,
            "_request",
            side_effect=[
                {"isError": True, "isNetworkError": True, "error": "timeout"},
                {"multiAssetsMargin": False},
            ],
        ):
            res = self.client.check_account_modes()
        self.assertFalse(self.client._account_mode_checked)
        self.assertFalse(res.get("ok", True))

        with patch.object(
            self.client,
            "_request",
            side_effect=[
                {"dualSidePosition": False},
                {"multiAssetsMargin": True},
            ],
        ):
            res2 = self.client.check_account_modes()
        self.assertTrue(self.client._account_mode_checked)
        self.assertTrue(res2.get("ok"))
        self.assertTrue(res2.get("multiAssetsMargin"))

    def test_a2_multi_assets_margin_aborts_before_order(self):
        """A-2: multiAssetsMargin=True aborts execute_full_trade with REJECTED_MULTI_ASSETS_CROSS."""
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": True, "ok": True}), \
             patch.object(self.client, "open_position") as mock_open:
            res = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.0, "take_profit": 154.0},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )
        self.assertEqual(res["status"], "REJECTED_MULTI_ASSETS_CROSS")
        self.assertFalse(res["binance_synced"])
        mock_open.assert_not_called()

    def test_a2_margin_type_accepts_4046_and_rejects_4168_4047_4048(self):
        """A-2: -4046 succeeds; -4168/-4047/-4048/network errors abort open_position & execute_full_trade."""
        for bad_code in (-4168, -4047, -4048):
            with self.subTest(bad_code=bad_code):
                with patch.object(self.client, "set_margin_type", return_value={"isError": True, "code": bad_code, "error": "rejected"}), \
                     patch.object(self.client, "_request") as mock_req:
                    res_open = self.client.open_position("SOLUSDT", "LONG", 1.0, leverage=20, margin_type="ISOLATED")
                self.assertTrue(res_open.get("isError"))
                mock_req.assert_not_called()

                with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
                     patch.object(self.client, "get_positions", return_value=[]), \
                     patch.object(self.client, "get_balance", return_value={"available_balance": 20.0}), \
                     patch.object(self.client, "get_market_price", return_value=150.0), \
                     patch.object(self.client, "set_margin_type", return_value={"isError": True, "code": bad_code, "error": "rejected"}), \
                     patch.object(self.client, "open_position") as mock_open:
                    res_exec = self.client.execute_full_trade(
                        {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.0, "take_profit": 154.0},
                        {"fixed_leverage": 20, "margin_type": "ISOLATED"},
                    )
                self.assertEqual(res_exec["status"], "REJECTED_MARGIN_TYPE_ERROR")
                self.assertFalse(res_exec["binance_synced"])
                mock_open.assert_not_called()

        # -4046 ("No need to change margin type") must be accepted cleanly
        with patch.object(self.client, "set_margin_type", return_value={"isError": True, "code": -4046, "error": "No need to change margin type."}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "_request", return_value={"orderId": 1001, "status": "FILLED", "executedQty": "1.0"}):
            res_ok = self.client.open_position("SOLUSDT", "LONG", 1.0, leverage=20, margin_type="ISOLATED")
        self.assertEqual(res_ok.get("orderId"), 1001)

    def test_a2_leverage_capped_by_exchange_resizes_quantity_before_order(self):
        """A-2: When set_leverage returns 10x (requested 20x), qty/notional scale to 10x and sync back."""
        sent_qtys = []

        def fake_open(symbol, direction, quantity, leverage=20, **kw):
            sent_qtys.append((quantity, leverage))
            return {"orderId": 2001, "status": "FILLED", "executedQty": str(quantity), "avgPrice": "150.0"}

        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", side_effect=[[], [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 0.63, "entry_price": 150.0, "liquidation_price": 136.0, "leverage": 10, "margin_type": "ISOLATED"}]]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 10.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_order_book", return_value={}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"symbol": "SOLUSDT", "leverage": 10}), \
             patch.object(self.client, "open_position", side_effect=fake_open), \
             patch.object(self.client, "set_stop_loss", return_value={"algoId": 3001}), \
             patch.object(self.client, "set_take_profit", return_value={"algoId": 3002}):
            res = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.0, "take_profit": 154.0, "order_type": "MARKET"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED", "sizing_mode": "ALL_IN", "all_in_balance_fraction": 0.95},
            )

        self.assertEqual(res["status"], "EXECUTED")
        self.assertEqual(res["leverage"], 10)
        # working margin = 9.50 * 10x = $95 notional / 150 = 0.63 (NOT 1.26 from 20x!)
        self.assertEqual(sent_qtys, [(0.63, 10)])
        self.assertAlmostEqual(res["quantity"], 0.63, places=2)

    def test_a2_post_fill_margin_or_leverage_mismatch_triggers_emergency_close(self):
        """A-2: Live CROSSED margin or wrong leverage in positionRisk after fill -> immediate reduceOnly close."""
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", side_effect=[
                 [],
                 [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 1.26, "entry_price": 150.0, "liquidation_price": 143.0, "leverage": 20, "margin_type": "CROSSED"}],
                 [],
             ]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 10.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_order_book", return_value={}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "open_position", return_value={"orderId": 2002, "status": "FILLED", "executedQty": "1.26", "avgPrice": "150.0"}), \
             patch.object(self.client, "close_position", return_value={"orderId": 2003, "status": "FILLED"}) as mock_close, \
             patch.object(self.client, "cancel_all_orders", return_value={}):
            res = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.0, "take_profit": 154.0, "order_type": "MARKET"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )

        self.assertEqual(res["status"], "ABORTED_MODE_MISMATCH")
        self.assertFalse(res["binance_synced"])
        mock_close.assert_called_once()

    def test_a2_leverage_cap_below_min_notional_aborts_and_post_fill_lev_mismatch_closes(self):
        """A-2: Capped leverage falling below minNotional rejects; post-fill leverage mismatch flattens."""
        # 1. Working balance $0.80, exchange caps leverage at 5x -> max notional $4.00 < $5.00 minNotional -> reject!
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", return_value=[]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 0.80}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 5}), \
             patch.object(self.client, "open_position") as mock_open:
            r_cap = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.0, "take_profit": 154.0},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )
        self.assertEqual(r_cap["status"], "REJECTED_NOTIONAL_CAPACITY")
        mock_open.assert_not_called()

        # 2. Post-fill leverage mismatch (expected 10x, live 20x) -> immediate close
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", side_effect=[
                 [],
                 [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 0.63, "entry_price": 150.0, "liquidation_price": 143.0, "leverage": 20, "margin_type": "ISOLATED"}],
                 [],
             ]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 10.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_order_book", return_value={}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 10}), \
             patch.object(self.client, "open_position", return_value={"orderId": 2009, "status": "FILLED", "executedQty": "0.63", "avgPrice": "150.0"}), \
             patch.object(self.client, "close_position", return_value={"orderId": 2010, "status": "FILLED"}) as mock_close2, \
             patch.object(self.client, "cancel_all_orders", return_value={}):
            r_lev_mm = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.0, "take_profit": 154.0, "order_type": "MARKET"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )
        self.assertEqual(r_lev_mm["status"], "ABORTED_MODE_MISMATCH")
        mock_close2.assert_called_once()


class TestB1AndC2FailClosed(unittest.TestCase):
    def setUp(self):
        self.client = BinanceFuturesClient(api_key="k", api_secret="s")
        self.client.time_offset = 0

    def test_b1_refuses_trade_when_get_positions_fails(self):
        """B-1: Error dict or exception from get_positions aborts with REJECTED_POSITION_CHECK_ERROR."""
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", return_value={"isError": True, "error": "timeout"}), \
             patch.object(self.client, "open_position") as mock_open:
            res = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.0, "take_profit": 154.0},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )
        self.assertEqual(res["status"], "REJECTED_POSITION_CHECK_ERROR")
        self.assertFalse(res["binance_synced"])
        mock_open.assert_not_called()

        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", side_effect=RuntimeError("conn reset")), \
             patch.object(self.client, "open_position") as mock_open2:
            res2 = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.0, "take_profit": 154.0},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )
        self.assertEqual(res2["status"], "REJECTED_POSITION_CHECK_ERROR")
        mock_open2.assert_not_called()

    def test_c2_fail_closed_exchange_info_and_cooldown(self):
        """C-2: Failed exchangeInfo fails closed (no fake stepSize=0.001) and respects retry cooldown."""
        with patch.object(self.client, "get_exchange_info", return_value={"isError": True, "error": "503"}) as mock_ex:
            r1 = self.client.get_symbol_filters("SOLUSDT")
            r2 = self.client.get_symbol_filters("BTCUSDT")
        self.assertTrue(r1.get("isError"))
        self.assertTrue(r2.get("isError"))
        self.assertEqual(mock_ex.call_count, 1, "Retry cooldown must prevent infinite spin on exchangeInfo failures")
        with self.assertRaises(ValueError):
            self.client.format_quantity("SOLUSDT", 1.0)

    def test_c2_enforces_trading_status_perpetual_and_market_lot_size(self):
        """C-2: Rejects non-TRADING, non-PERPETUAL, budget violation on minQty bump, and respects MARKET_LOT_SIZE."""
        # 1. Status != TRADING -> rejected
        _seed_symbol(self.client, "DEADUSDT", status="SETTLING")
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", return_value=[]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 20.0}), \
             patch.object(self.client, "get_market_price", return_value=10.0), \
             patch.object(self.client, "open_position") as mock_open:
            r_dead = self.client.execute_full_trade(
                {"symbol": "DEADUSDT", "direction": "LONG", "entry_price": 10.0, "stop_loss": 9.8, "take_profit": 10.4},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )
        self.assertEqual(r_dead["status"], "REJECTED_SYMBOL_NOT_TRADING")
        mock_open.assert_not_called()

        # 2. contractType != PERPETUAL -> rejected
        _seed_symbol(self.client, "QTRUSDT", status="TRADING", contractType="CURRENT_QUARTER")
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", return_value=[]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 20.0}), \
             patch.object(self.client, "get_market_price", return_value=10.0), \
             patch.object(self.client, "open_position") as mock_open:
            r_qtr = self.client.execute_full_trade(
                {"symbol": "QTRUSDT", "direction": "LONG", "entry_price": 10.0, "stop_loss": 9.8, "take_profit": 10.4},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )
        self.assertEqual(r_qtr["status"], "REJECTED_INVALID_CONTRACT_TYPE")
        mock_open.assert_not_called()

        # 3. MARKET_LOT_SIZE stepSize & maxQty parsed from exchangeInfo
        with patch.object(
            self.client,
            "get_exchange_info",
            return_value=_exchange_info_payload(
                symbol="TESTUSDT",
                step_size="0.1",
                min_qty="0.1",
                max_qty="100",
                mkt_step_size="1",
                mkt_min_qty="1",
                mkt_max_qty="5",
                qty_prec=1,
            ),
        ):
            self.client._symbol_cache = {}
            self.client._symbol_fail_time = None
            rules = self.client.get_symbol_filters("TESTUSDT")
        self.assertEqual(rules["maxQty"], 100.0)
        self.assertEqual(rules["marketStepSize"], 1.0)
        self.assertEqual(rules["marketMinQty"], 1.0)
        self.assertEqual(rules["marketMaxQty"], 5.0)
        self.assertEqual(self.client.format_quantity("TESTUSDT", 2.7, order_type="MARKET"), 2.0)
        self.assertEqual(self.client.format_quantity("TESTUSDT", 2.7, order_type="LIMIT"), 2.7)

        # 4. format_quantity bumping to minQty above budget must reject
        _seed_symbol(self.client, "BIGMINUSDT", minQty=1.0, stepSize=1.0, marketMinQty=1.0, marketStepSize=1.0, minNotional=5.0, quantityPrecision=0)
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", return_value=[]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 2.0}), \
             patch.object(self.client, "get_market_price", return_value=100.0), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "open_position") as mock_open:
            r_bump = self.client.execute_full_trade(
                {"symbol": "BIGMINUSDT", "direction": "LONG", "entry_price": 100.0, "stop_loss": 98.5, "take_profit": 103.0, "order_type": "MARKET"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )
        self.assertEqual(r_bump["status"], "REJECTED_NOTIONAL_CAPACITY")
        mock_open.assert_not_called()

        # 5. Missing symbol in valid exchangeInfo fails closed, and open_position rejects qty > maxQty
        with patch.object(self.client, "get_exchange_info", return_value=_exchange_info_payload(symbol="SOLUSDT")):
            self.client._symbol_cache = {}
            self.client._symbol_fail_time = None
            r_miss = self.client.get_symbol_filters("NONEXISTENTUSDT")
        self.assertTrue(r_miss.get("isError"))

        with patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "_request") as mock_req_max:
            r_over_max = self.client.open_position("TESTUSDT", "LONG", 10.0, leverage=20, order_type="MARKET")
        self.assertTrue(r_over_max.get("isError"))
        mock_req_max.assert_not_called()


class TestA7A6B11B2ExecutionPipeline(unittest.TestCase):
    def setUp(self):
        self.client = BinanceFuturesClient(api_key="k", api_secret="s")
        self.client.time_offset = 0
        _seed_symbol(self.client, "SOLUSDT")

    def test_a7_unfilled_canceled_gtx_returns_unfilled_and_never_places_sl_tp(self):
        """A-7: CANCELED/EXPIRED 0-fill with positionRisk delta=0 returns UNFILLED, zero phantom position."""
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", return_value=[]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 20.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_order_book", return_value={"bids": [["149.99", "100"]], "asks": [["150.01", "100"]]}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "open_position", return_value={"orderId": 4001, "status": "NEW", "executedQty": "0"}) as mock_open, \
             patch.object(self.client, "query_order", return_value={"orderId": 4001, "status": "EXPIRED", "executedQty": "0"}), \
             patch.object(self.client, "cancel_order", return_value={"orderId": 4001, "status": "CANCELED"}), \
             patch.object(self.client, "set_stop_loss") as mock_sl, \
             patch.object(self.client, "set_take_profit") as mock_tp, \
             patch("binance_futures.time.sleep"):
            res = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.5, "take_profit": 154.0, "order_type": "MAKER_FIRST_GTX"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED", "maker_only_no_taker_fallback": True},
            )

        self.assertEqual(res["status"], "UNFILLED")
        self.assertFalse(res["binance_synced"])
        mock_sl.assert_not_called()
        mock_tp.assert_not_called()
        # Must NOT fall through to MARKET when maker_only_no_taker_fallback=True
        for call in mock_open.call_args_list:
            self.assertNotEqual(call.kwargs.get("order_type"), "MARKET")

    def test_a7_expired_ioc_zero_fill_returns_unfilled_and_partial_fill_syncs_qty(self):
        """A-7: EXPIRED 0-fill IOC returns UNFILLED; partial fill syncs actual qty & entry_price to TCA and TP."""
        # 1. Direct MARKET/IOC returning EXPIRED with executedQty=0 and positionRisk delta=0
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", return_value=[]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 20.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_order_book", return_value={}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "open_position", return_value={"orderId": 4010, "status": "EXPIRED", "executedQty": "0"}), \
             patch.object(self.client, "set_stop_loss") as mock_sl, \
             patch.object(self.client, "set_take_profit") as mock_tp:
            r_exp = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.5, "take_profit": 154.0, "order_type": "MARKET"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )
        self.assertEqual(r_exp["status"], "UNFILLED")
        self.assertFalse(r_exp["binance_synced"])
        mock_sl.assert_not_called()
        mock_tp.assert_not_called()

        # 2. Partial fill on GTX (0.80 out of 2.53 filled, positionRisk confirms 0.80)
        sl_calls = []
        tp_calls = []

        def fake_sl(sym, dir_, trigger_price, quantity=None, **kw):
            sl_calls.append(quantity)
            return {"algoId": 4021}

        def fake_tp(sym, dir_, trigger_price, quantity=None, **kw):
            tp_calls.append(quantity)
            return {"algoId": 4022}

        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", side_effect=[
                 [],
                 [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 0.80, "entry_price": 149.95, "liquidation_price": 143.0, "leverage": 20, "margin_type": "ISOLATED"}],
             ]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 20.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_order_book", return_value={"bids": [["149.99", "100"]], "asks": [["150.01", "100"]]}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "open_position", side_effect=[
                 {"orderId": 4020, "status": "NEW", "executedQty": "0"},
                 {"orderId": 4025, "status": "CANCELED", "executedQty": "0"},
             ]), \
             patch.object(self.client, "query_order", side_effect=[
                 {"orderId": 4020, "status": "PARTIALLY_FILLED", "executedQty": "0.80"},
                 {"orderId": 4020, "status": "PARTIALLY_FILLED", "executedQty": "0.80"},
                 {"orderId": 4020, "status": "PARTIALLY_FILLED", "executedQty": "0.80"},
                 {"orderId": 4020, "status": "CANCELED", "executedQty": "0.80", "avgPrice": "149.95"},
                 {"orderId": 4025, "status": "EXPIRED", "executedQty": "0"},
             ]), \
             patch.object(self.client, "cancel_order", return_value={"status": "CANCELED"}), \
             patch.object(self.client, "set_stop_loss", side_effect=fake_sl), \
             patch.object(self.client, "set_take_profit", side_effect=fake_tp), \
             patch("binance_futures.time.sleep"):
            r_part = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.5, "take_profit": 154.0, "order_type": "MAKER_FIRST_GTX"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED", "maker_only_no_taker_fallback": True},
            )
        self.assertEqual(r_part["status"], "EXECUTED")
        self.assertAlmostEqual(r_part["quantity"], 0.80, places=4)
        self.assertAlmostEqual(r_part["entry_price"], 149.95, places=4)
        self.assertEqual(sl_calls, [None], "SL must use closePosition=true without quantity")
        self.assertEqual(tp_calls, [0.80], "TP must use actual filled quantity 0.80")

    def test_a6_sl_placed_first_with_close_position_and_mandatory_flatten_on_3x_fail(self):
        """A-6: SL placed BEFORE TP with closePosition=true (no quantity); 3x SL fail -> emergency close + ABORTED_UNPROTECTED_SL."""
        call_order = []

        def rec_sl(sym, dir_, trigger_price, quantity=None, **kw):
            call_order.append(("SL", quantity))
            return {"algoId": 5001}

        def rec_tp(sym, dir_, trigger_price, quantity=None, **kw):
            call_order.append(("TP", quantity))
            return {"algoId": 5002}

        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", side_effect=[[], [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 2.53, "entry_price": 150.0, "liquidation_price": 143.0, "leverage": 20, "margin_type": "ISOLATED"}]]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 20.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_order_book", return_value={}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "open_position", return_value={"orderId": 5000, "status": "FILLED", "executedQty": "2.53", "avgPrice": "150.0"}), \
             patch.object(self.client, "set_stop_loss", side_effect=rec_sl), \
             patch.object(self.client, "set_take_profit", side_effect=rec_tp):
            res_ok = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.5, "take_profit": 154.0, "order_type": "MARKET"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )

        self.assertEqual(res_ok["status"], "EXECUTED")
        self.assertEqual(call_order[0], ("SL", None), "SL must run FIRST with quantity=None (closePosition=true)")
        self.assertEqual(call_order[1][0], "TP")

        # Now test 3x SL failure -> mandatory reduceOnly market close & verify flat
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", side_effect=[
                 [],
                 [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 2.53, "entry_price": 150.0, "liquidation_price": 143.0, "leverage": 20, "margin_type": "ISOLATED"}],
                 [],
             ]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 20.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_order_book", return_value={}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "open_position", return_value={"orderId": 5010, "status": "FILLED", "executedQty": "2.53", "avgPrice": "150.0"}), \
             patch.object(self.client, "set_stop_loss", return_value={"isError": True, "code": -1000, "error": "err"}), \
             patch.object(self.client, "verify_stop_loss_active", return_value="UNKNOWN"), \
             patch.object(self.client, "set_take_profit") as mock_tp2, \
             patch.object(self.client, "close_position", return_value={"orderId": 5011, "status": "FILLED"}) as mock_close, \
             patch.object(self.client, "cancel_all_orders", return_value={}), \
             patch("binance_futures.time.sleep"):
            res_fail = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.5, "take_profit": 154.0, "order_type": "MARKET"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )

        self.assertEqual(res_fail["status"], "ABORTED_UNPROTECTED_SL")
        self.assertFalse(res_fail["binance_synced"])
        self.assertNotEqual(res_fail.get("sl_state"), "LOCAL_GUARD_MONITORED")
        self.assertTrue(res_fail.get("emergency_closed"))
        mock_close.assert_called_once()
        mock_tp2.assert_not_called()

    def test_b11_2021_never_loosens_sl_and_triggers_immediate_close(self):
        """B-11: -2021 on set_stop_loss must NOT loosen SL by 1.5%; triggers immediate close in execute_full_trade."""
        sent_triggers = []

        def fake_req(method, endpoint, params=None, signed=False, **kw):
            if method == "POST" and endpoint == "/fapi/v1/algoOrder":
                sent_triggers.append((params.get("triggerPrice"), params.get("closePosition"), params.get("quantity")))
                return {"isError": True, "code": -2021, "error": "Order would immediately trigger."}
            return {}

        with patch.object(self.client, "_request", side_effect=fake_req):
            sl_res = self.client.set_stop_loss("SOLUSDT", "LONG", 148.5)

        self.assertEqual(len(sent_triggers), 1, "Must NOT retry with loosened 1.5% SL")
        self.assertEqual(sent_triggers[0][1], "true")
        self.assertIsNone(sent_triggers[0][2])
        self.assertTrue(sl_res.get("isError"))
        self.assertEqual(sl_res.get("code"), -2021)
        self.assertTrue(sl_res.get("would_immediately_trigger"))

        # amend_stop_loss hitting -2021 must preserve old SL and NOT cancel it
        with patch.object(self.client, "_request", side_effect=fake_req), \
             patch.object(self.client, "cancel_algo_order") as mock_cancel_algo:
            am_res = self.client.amend_stop_loss("SOLUSDT", "LONG", 149.9, old_algo_id=991)
        self.assertEqual(am_res["status"], "AMEND_FAILED_KEPT_OLD")
        self.assertEqual(am_res["kept_algo_ids"], [991])
        mock_cancel_algo.assert_not_called()

        # In execute_full_trade: immediate reduceOnly close without 3x backoff
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", side_effect=[
                 [],
                 [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 2.53, "entry_price": 150.0, "liquidation_price": 143.0, "leverage": 20, "margin_type": "ISOLATED"}],
                 [],
             ]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 20.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_order_book", return_value={}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "open_position", return_value={"orderId": 6001, "status": "FILLED", "executedQty": "2.53", "avgPrice": "150.0"}), \
             patch.object(self.client, "set_stop_loss", return_value={"isError": True, "code": -2021, "would_immediately_trigger": True}) as mock_sl, \
             patch.object(self.client, "close_position", return_value={"orderId": 6002, "status": "FILLED"}) as mock_close, \
             patch.object(self.client, "cancel_all_orders", return_value={}):
            res_2021 = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.5, "take_profit": 154.0, "order_type": "MARKET"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )

        self.assertEqual(mock_sl.call_count, 1)
        self.assertEqual(res_2021["status"], "ABORTED_UNPROTECTED_SL")
        self.assertFalse(res_2021["binance_synced"])
        mock_close.assert_called_once()

    def test_b2_post_fill_exception_recovery_protected_vs_emergency_closed(self):
        """B-2: Exception after open_position inspects positionRisk -> emergency SL -> EXECUTED_RECOVERY_PROTECTED or ABORTED_UNPROTECTED_SL."""
        # Case 1: Live position exists and emergency SL succeeds -> EXECUTED_RECOVERY_PROTECTED
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", side_effect=[
                 [],
                 [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 2.53, "entry_price": 150.0, "liquidation_price": 143.0, "leverage": 20, "margin_type": "ISOLATED"}],
             ]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 20.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_order_book", return_value={}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "open_position", return_value={"orderId": 7001, "status": "FILLED", "executedQty": "2.53"}), \
             patch.object(self.client, "wait_for_position_open", side_effect=RuntimeError("boom in wait")), \
             patch.object(self.client, "verify_stop_loss_active", return_value="MISSING"), \
             patch.object(self.client, "set_stop_loss", return_value={"algoId": 7002}):
            res_rec = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.5, "take_profit": 154.0, "order_type": "MARKET"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )

        self.assertEqual(res_rec["status"], "EXECUTED_RECOVERY_PROTECTED")
        self.assertTrue(res_rec["binance_synced"])
        self.assertEqual(res_rec["sl_state"], "CONFIRMED")
        self.assertEqual(res_rec["sl_algo_id"], 7002)

        # Case 2: Live position exists and emergency SL ALSO fails -> emergency close -> ABORTED_UNPROTECTED_SL
        with patch.object(self.client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
             patch.object(self.client, "get_positions", side_effect=[
                 [],
                 [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 2.53, "entry_price": 150.0, "liquidation_price": 143.0, "leverage": 20, "margin_type": "ISOLATED"}],
                 [],
             ]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 20.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_order_book", return_value={}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "open_position", return_value={"orderId": 7003, "status": "FILLED", "executedQty": "2.53"}), \
             patch.object(self.client, "wait_for_position_open", side_effect=RuntimeError("boom in wait")), \
             patch.object(self.client, "verify_stop_loss_active", return_value="MISSING"), \
             patch.object(self.client, "set_stop_loss", return_value={"isError": True, "error": "sl err"}), \
             patch.object(self.client, "close_position", return_value={"orderId": 7004, "status": "FILLED"}) as mock_close, \
             patch.object(self.client, "cancel_all_orders", return_value={}):
            res_abort = self.client.execute_full_trade(
                {"symbol": "SOLUSDT", "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.5, "take_profit": 154.0, "order_type": "MARKET"},
                {"fixed_leverage": 20, "margin_type": "ISOLATED"},
            )

        self.assertEqual(res_abort["status"], "ABORTED_UNPROTECTED_SL")
        self.assertFalse(res_abort["binance_synced"])
        mock_close.assert_called_once()


class TestAutoTraderRecordPositionHandoff(unittest.TestCase):
    def test_record_position_syncs_effective_fields_and_handles_recovery_and_abort(self):
        import auto_trader as at
        import journal
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_res = at.RESULTS_DIR
            orig_pos = at.POSITIONS_FILE
            orig_brk = at.RISK_BREAKER_FILE
            orig_db = journal.DB_PATH
            try:
                at.RESULTS_DIR = tmp
                at.POSITIONS_FILE = os.path.join(tmp, "active_positions.json")
                at.RISK_BREAKER_FILE = os.path.join(tmp, "risk_breaker.json")
                journal.DB_PATH = os.path.join(tmp, "journal.db")
                journal.init_db(journal.DB_PATH)

                fake_cfg = {
                    "fixed_leverage": 20,
                    "max_leverage": 20,
                    "margin_type": "ISOLATED",
                    "sizing_mode": "ALL_IN",
                    "all_in_balance_fraction": 0.95,
                    "max_sl_pct": 2.25,
                    "min_sl_pct": 0.45,
                    "max_concurrent_positions": 5,
                    "max_daily_trades": 10,
                    "auto_execute": True,
                }
                sig = {
                    "id": "POS_SYNC_1",
                    "symbol": "SOL-USD",
                    "binance_pair": "SOLUSDT",
                    "direction": "LONG",
                    "entry_price": 150.0,
                    "stop_loss": 148.5,
                    "take_profit": 154.5,
                    "confidence_score": 82,
                    "setup_name": "EMA_PULLBACK",
                }

                # 1. Capped leverage (10x) + TCA fee + recovery protected -> synced & persisted
                bn_rec = MagicMock()
                bn_rec.get_balance.return_value = {"available_balance": 20.0, "total_wallet_balance": 20.0}
                bn_rec.execute_full_trade.return_value = {
                    "status": "EXECUTED_RECOVERY_PROTECTED",
                    "binance_synced": True,
                    "order_id": 91001,
                    "entry_price": 150.5,
                    "take_profit": 154.5,
                    "stop_loss": 148.5,
                    "leverage": 10,
                    "margin_type": "ISOLATED",
                    "position_size_usdt": 18.06,
                    "quantity": 1.20,
                    "sl_algo_id": 91002,
                    "tp_algo_id": None,
                    "sl_state": "CONFIRMED",
                    "sl_verified": True,
                    "liquidation_price": 136.0,
                    "routing_used": "MAKER_GTX_FILLED",
                    "tca": {
                        "symbol": "SOLUSDT", "direction": "LONG", "routing_used": "MAKER_GTX_FILLED",
                        "arrival_price": 150.0, "fill_price": 150.5, "arrival_slippage_bps": 33.3,
                        "fee_usdt": 0.03612, "margin_usdt": 18.06, "fee_drag_roe_pct": 0.2, "impact_bps_est": 1.0,
                    },
                }

                with patch.object(at, "get_binance_client", return_value=bn_rec), \
                     patch.object(at, "_get_config", return_value=fake_cfg), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "send_telegram") as mock_tg:
                    pos = at.record_position(dict(sig))

                self.assertIsNotNone(pos)
                self.assertEqual(pos["leverage"], 10)
                self.assertAlmostEqual(pos["position_size_usd"], 18.06, places=4)
                self.assertEqual(pos["quantity"], 1.20)
                self.assertAlmostEqual(pos["fee_usd"], 0.03612, places=5)
                self.assertEqual(pos["sl_state"], "CONFIRMED")
                self.assertTrue(pos["recovery_protected"])
                self.assertTrue(mock_tg.called)
                with journal.get_db(journal.DB_PATH) as conn:
                    jrow = conn.execute("SELECT qty, leverage, margin_usdt, fee_usdt FROM trades WHERE trade_id=?", ("POS_SYNC_1",)).fetchone()
                self.assertIsNotNone(jrow)
                self.assertAlmostEqual(jrow["qty"], 1.20, places=4)
                self.assertEqual(jrow["leverage"], 10)
                self.assertAlmostEqual(jrow["margin_usdt"], 18.06, places=4)
                self.assertAlmostEqual(jrow["fee_usdt"], 0.03612, places=5)

                # 2. Emergency closed ABORTED_UNPROTECTED_SL -> returns None, no phantom entry
                sig2 = dict(sig, id="POS_ABORT_1")
                bn_rec.execute_full_trade.return_value = {
                    "status": "ABORTED_UNPROTECTED_SL",
                    "binance_synced": False,
                    "emergency_closed": True,
                    "binance_position_still_open": False,
                    "error": "SL failed 3x; emergency closed",
                    "critical_alert": "SL failed 3x; emergency closed",
                }
                with patch.object(at, "get_binance_client", return_value=bn_rec), \
                     patch.object(at, "_get_config", return_value=fake_cfg), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "send_telegram") as mock_tg2:
                    pos2 = at.record_position(sig2)

                self.assertIsNone(pos2)
                self.assertTrue(mock_tg2.called)
                disk_pos = state_io.read_json_safe(at.POSITIONS_FILE, default=[], strict_on_corrupt=True)
                self.assertEqual([p["id"] for p in disk_pos], ["POS_SYNC_1"])

                # 3. Emergency close FAILED while live Binance position still open -> tracks OPEN for recovery!
                sig3 = dict(sig, id="POS_STILL_OPEN_1")
                bn_rec.execute_full_trade.return_value = {
                    "status": "ABORTED_UNPROTECTED_SL",
                    "binance_synced": False,
                    "emergency_closed": False,
                    "binance_position_still_open": True,
                    "entry_price": 150.2,
                    "quantity": 1.25,
                    "leverage": 20,
                    "position_size_usdt": 9.3875,
                    "error": "Emergency close failed while position open",
                    "critical_alert": "Emergency close failed",
                }
                with patch.object(at, "get_binance_client", return_value=bn_rec), \
                     patch.object(at, "_get_config", return_value=fake_cfg), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "send_telegram") as mock_tg3:
                    pos3 = at.record_position(sig3)

                self.assertIsNotNone(pos3)
                self.assertEqual(pos3["status"], "OPEN")
                self.assertTrue(pos3["binance_synced"])
                self.assertEqual(pos3["sl_state"], "UNPROTECTED_RECOVERY")
                self.assertTrue(pos3["emergency_close_failed"])
                self.assertTrue(mock_tg3.called)
            finally:
                at.RESULTS_DIR = orig_res
                at.POSITIONS_FILE = orig_pos
                at.RISK_BREAKER_FILE = orig_brk
                journal.DB_PATH = orig_db

    def test_open_position_retries_and_trims_on_margin_insufficient_2019(self):
        """When Binance rejects order with code -2019 (Margin is insufficient), auto-trim quantity and retry."""
        client = BinanceFuturesClient()
        calls = []
        def fake_request(method, endpoint, params=None, signed=False, **kwargs):
            calls.append(dict(params or {}))
            if len(calls) == 1:
                return {"isError": True, "code": -2019, "error": "Margin is insufficient."}
            return {"orderId": 88123, "status": "FILLED", "executedQty": str(params.get("quantity")), "avgPrice": "150.0"}

        with patch.object(client, "_request", side_effect=fake_request), \
             patch.object(client, "get_symbol_filters", return_value={"stepSize": "0.01", "minQty": "0.01", "minNotional": "5.0", "quantityPrecision": 2, "pricePrecision": 2, "status": "TRADING", "contractType": "PERPETUAL"}), \
             patch.object(client, "get_market_price", return_value=150.0), \
             patch.object(client, "set_margin_type", return_value={"code": 200}), \
             patch.object(client, "set_leverage", return_value={"leverage": 20}):
            res = client.open_position(
                symbol="SOLUSDT",
                direction="LONG",
                quantity=1.0,
                leverage=20,
                order_type="MARKET",
            )
        self.assertEqual(res.get("orderId"), 88123)
        self.assertEqual(len(calls), 2)
        self.assertLess(calls[1]["quantity"], calls[0]["quantity"])
        self.assertAlmostEqual(calls[1]["quantity"], 0.96, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
