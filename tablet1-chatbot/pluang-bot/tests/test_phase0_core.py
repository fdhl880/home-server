"""
Unit tests for Phase 0 Core Execution & Safety Fixes (T0.1 - T0.9, T3.1, T6.6, T7.4).
"""
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from binance_futures import BinanceFuturesClient
from market_data import filter_eligible_symbols, get_binance_klines


class TestPhase0Core(unittest.TestCase):
    def setUp(self):
        self.client = BinanceFuturesClient(api_key="test_key", api_secret="test_secret")

    def test_t01_hosts_and_circuit_breaker(self):
        """T0.1: Broken fapi3.binance.com is removed; per-host circuit breaker works."""
        self.assertNotIn("https://fapi3.binance.com", self.client.endpoints)
        self.assertIn("https://fapi.binance.com", self.client.endpoints)
        self.client._mark_host_failure("https://fapi1.binance.com")
        self.client._mark_host_failure("https://fapi1.binance.com")
        self.assertGreater(self.client._host_cooldown["https://fapi1.binance.com"], 0)
        self.client._mark_host_success("https://fapi1.binance.com")
        self.assertEqual(self.client._host_fail_count["https://fapi1.binance.com"], 0)

    def test_t01_business_error_no_failover(self):
        """T0.1: Binance business error (code < 0, e.g. -2019 Margin insufficient) does not failover 4x."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"code": -2019, "msg": "Margin is insufficient."}
        with patch.object(self.client.session, "get", return_value=mock_resp) as mock_get:
            res = self.client._request("GET", "/fapi/v1/exchangeInfo", signed=False)
            self.assertEqual(res.get("code"), -2019)
            self.assertEqual(mock_get.call_count, 1)

    def test_t02_verify_stop_loss_tri_state(self):
        """T0.2: verify_stop_loss_active checks BOTH openAlgoOrders and openOrders and returns Tri-State."""
        # Case 1: Found in openAlgoOrders -> CONFIRMED
        with patch.object(self.client, "get_open_orders", return_value=[]), \
             patch.object(self.client, "get_open_algo_orders", return_value=(True, [
                 {"symbol": "SOLUSDT", "orderType": "STOP_MARKET", "closePosition": True, "algoId": 987654, "triggerPrice": "140.5"}
             ])):
            v = self.client.verify_stop_loss_active("SOLUSDT", max_wait_sec=0.1)
            self.assertEqual(v, "CONFIRMED")

        # Case 2: Both return empty list -> MISSING
        with patch.object(self.client, "get_open_orders", return_value=[]), \
             patch.object(self.client, "get_open_algo_orders", return_value=(True, [])):
            v2 = self.client.verify_stop_loss_active("SOLUSDT", max_wait_sec=0.1)
            self.assertEqual(v2, "MISSING")

        # Case 3: Both return error -> UNKNOWN (never trigger false emergency close!)
        with patch.object(self.client, "get_open_orders", return_value={"error": "timeout"}), \
             patch.object(self.client, "get_open_algo_orders", return_value=(False, [])):
            v3 = self.client.verify_stop_loss_active("SOLUSDT", max_wait_sec=0.1)
            self.assertEqual(v3, "UNKNOWN")

    def test_t04_execute_full_trade_never_closes_on_algo_id_or_unknown(self):
        """T0.4: execute_full_trade keeps position open when SL returns algoId or state is CONFIRMED/UNKNOWN."""
        with patch.object(self.client, "check_account_modes", return_value=None), \
             patch.object(self.client, "get_positions", return_value=[]), \
             patch.object(self.client, "get_balance", return_value={"available_balance": 5.0}), \
             patch.object(self.client, "get_market_price", return_value=150.0), \
             patch.object(self.client, "get_symbol_filters", return_value={"pricePrecision": 2, "quantityPrecision": 1, "minQty": 0.1, "stepSize": 0.1, "tickSize": 0.01, "minNotional": 5.0}), \
             patch.object(self.client, "set_margin_type", return_value={"code": 200}), \
             patch.object(self.client, "set_leverage", return_value={"leverage": 20}), \
             patch.object(self.client, "open_position", return_value={"orderId": 111, "avgPrice": "150.0", "executedQty": "0.6"}), \
             patch.object(self.client, "wait_for_position_open", return_value={"entry_price": 150.0, "liquidation_price": 143.0}), \
             patch.object(self.client, "set_stop_loss", return_value={"algoId": 555666, "algoStatus": "NEW"}), \
             patch.object(self.client, "verify_stop_loss_active", return_value="CONFIRMED"), \
             patch.object(self.client, "set_take_profit", return_value={"algoId": 777888, "algoStatus": "NEW"}), \
             patch.object(self.client, "close_position") as mock_close:
            res = self.client.execute_full_trade(
                signal={
                    "symbol": "SOLUSDT",
                    "direction": "LONG",
                    "entry_price": 150.0,
                    "take_profit": 155.0,
                    "stop_loss": 148.0,
                },
                config={"fixed_leverage": 20, "margin_type": "ISOLATED", "sizing_mode": "ALL_IN", "all_in_balance_fraction": 0.95},
            )
            self.assertEqual(res["status"], "EXECUTED")
            self.assertEqual(res["sl_state"], "CONFIRMED")
            self.assertEqual(res["sl_algo_id"], 555666)
            mock_close.assert_not_called()

    def test_t06_zero_unprotected_window_amend_sl(self):
        """T0.6: amend_stop_loss places new SL first, then cancels old algoId."""
        call_order = []
        def fake_set_sl(sym, direction, price, quantity=None, working_type="MARK_PRICE"):
            call_order.append(("set_sl", price))
            return {"algoId": 222}
        def fake_cancel_algo(sym, algo_id=None):
            call_order.append(("cancel_algo", algo_id))
            return {"code": 200}

        with patch.object(self.client, "set_stop_loss", side_effect=fake_set_sl), \
             patch.object(self.client, "cancel_algo_order", side_effect=fake_cancel_algo), \
             patch.object(self.client, "format_price", side_effect=lambda s, p: p):
            res = self.client.amend_stop_loss("SOLUSDT", "LONG", 151.25, old_algo_id=111)
            self.assertEqual(res["status"], "AMENDED")
            self.assertEqual(res["new_algo_id"], 222)
            self.assertEqual(call_order, [("set_sl", 151.25), ("cancel_algo", 111)])

    def test_t07_filter_eligible_symbols_min_notional(self):
        """T0.7: With $1.32 balance at 20x (notional $25.08), BTCUSDT ($50+ minNotional) is filtered out while SOLUSDT ($5) passes."""
        coins = [
            {"symbol": "BTC-USD", "pair": "BTCUSDT"},
            {"symbol": "SOL-USD", "pair": "SOLUSDT"},
            {"symbol": "XRP-USD", "pair": "XRPUSDT"},
        ]
        spec_map = {
            "BTCUSDT": {"minNotional": 100.0},
            "SOLUSDT": {"minNotional": 5.0},
            "XRPUSDT": {"minNotional": 5.0},
        }
        eligible, skipped = filter_eligible_symbols(
            coins,
            available_balance_usdt=1.32,
            leverage=20,
            balance_fraction=0.95,
            exchange_info_map=spec_map,
        )
        pairs = [c["pair"] for c in eligible]
        self.assertNotIn("BTCUSDT", pairs)
        self.assertIn("SOLUSDT", pairs)
        self.assertIn("XRPUSDT", pairs)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["symbol"], "BTCUSDT")

    def test_t31_closed_bar_integrity(self):
        """T3.1: get_binance_klines(closed_only=True) separates unclosed forming bar from closed bars."""
        now_ms = int(1700000000 * 1000)
        raw_bars = [
            [now_ms - 120000, "100", "102", "99", "101", "1000", now_ms - 60001, "100500", 50, "600", "60300", "0"],
            [now_ms - 60000, "101", "103", "100", "102", "1200", now_ms + 50000, "122000", 60, "700", "71400", "0"],
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = raw_bars
        with patch("market_data.requests.get", return_value=mock_resp), \
             patch("market_data.time.time", return_value=1700000000.0):
            res = get_binance_klines("SOLUSDT", interval="1m", limit=2, closed_only=True)
            self.assertEqual(res["count"], 1)
            self.assertEqual(res["closes"], [101.0])
            self.assertEqual(res["taker_buy_base"], [600.0])
            self.assertIsNotNone(res.get("forming_bar"))
            self.assertEqual(res["forming_bar"]["close"], 102.0)

    def test_t74_trading_config_locked_mandates(self):
        """T7.4: trading_config.json enforces 20x ISOLATED, ALL_IN 0.95, and sniper_75_mode."""
        cfg_path = os.path.join(BASE_DIR, "trading_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg["fixed_leverage"], 20)
        self.assertEqual(cfg["margin_type"], "ISOLATED")
        self.assertEqual(cfg["sizing_mode"], "ALL_IN")
        self.assertAlmostEqual(cfg["all_in_balance_fraction"], 0.95)
        self.assertTrue(cfg["sniper_75_mode"]["enabled"])
        self.assertAlmostEqual(cfg["sniper_75_mode"]["min_calibrated_p_tp1"], 0.76)
        self.assertAlmostEqual(cfg["sniper_75_mode"]["tp1_lock_trigger_r"], 0.55)
        self.assertAlmostEqual(cfg["sniper_75_mode"]["sl_lock_after_tp1_r"], 0.38)


if __name__ == "__main__":
    unittest.main()
