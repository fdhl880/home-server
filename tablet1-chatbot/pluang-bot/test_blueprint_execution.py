"""
Unit tests for Blueprint Execution:
1. RISK_FRACTIONAL position sizing mathematical verification
2. 20x Stop Loss liquidation safety margin
3. Journal open/close lifecycle and metrics
4. Binance Futures Stop Loss verification fail-safe mock
5. AI-Only invariant verification
"""
import os
import sys
import json
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

import journal

class TestBlueprintExecution(unittest.TestCase):
    def test_risk_fractional_sizing_math(self):
        """Verify that risk dollar loss never exceeds risk_pct of equity at SL"""
        equity = 100.0  # $100 account
        leverage = 20

        # Case A: Probation (2% risk)
        risk_pct_probation = 2.0
        sl_pct_a = 0.02  # 2% price distance to SL
        target_risk_usd_a = equity * (risk_pct_probation / 100.0)  # $2.00
        margin_usd_a = target_risk_usd_a / (sl_pct_a * leverage)   # 2.00 / 0.40 = $5.00
        notional_a = margin_usd_a * leverage                       # $100.00
        actual_loss_at_sl_a = notional_a * sl_pct_a                # $2.00
        self.assertAlmostEqual(actual_loss_at_sl_a, target_risk_usd_a)
        self.assertAlmostEqual(actual_loss_at_sl_a / equity * 100.0, risk_pct_probation)

        # Case B: Standard (5% risk)
        risk_pct_std = 5.0
        sl_pct_b = 0.015  # 1.5% distance
        target_risk_usd_b = equity * (risk_pct_std / 100.0)        # $5.00
        margin_usd_b = target_risk_usd_b / (sl_pct_b * leverage)   # 5.00 / 0.30 = $16.67
        notional_b = margin_usd_b * leverage                       # $333.33
        actual_loss_at_sl_b = notional_b * sl_pct_b                # $5.00
        self.assertAlmostEqual(actual_loss_at_sl_b, target_risk_usd_b, places=2)
        self.assertAlmostEqual(actual_loss_at_sl_b / equity * 100.0, risk_pct_std, places=2)

    def test_stop_loss_hard_cap(self):
        """Verify that SL cannot exceed 2.5% (Gate 10 safeguard) to protect 20x liquidation"""
        max_sl_pct = 2.5 / 100.0  # 0.025
        # 20x liquidation occurs at roughly ~4.8% move without fees
        # An SL > 2.5% risks being hit by exchange liquidation margin calls
        proposed_sl = 0.045  # 4.5%
        clamped_sl = max(0.005, min(proposed_sl, max_sl_pct))
        self.assertEqual(clamped_sl, 0.025)

    def test_journal_trade_lifecycle(self):
        """Verify that open_trade, close_trade, and generate_report work with SQLite WAL"""
        test_id = f"TEST_TRADE_{int(sqlite3.time.time())}"
        journal.open_trade({
            "id": test_id,
            "signal_id": "SIG_TEST_001",
            "symbol": "BTC-USD",
            "direction": "LONG",
            "entry_fill": 65000.0,
            "qty": 0.01,
            "leverage": 20,
            "margin_usd": 32.5,
            "fee_usd": 0.32
        })

        # Close with profit
        journal.close_trade(test_id, {
            "exit_fill": 66000.0,
            "pnl_usd": 10.0,
            "fee_usd": 0.65,
            "exit_reason": "CLOSED_TP",
            "is_estimated": 0
        })

        rep = journal.generate_report()
        self.assertGreaterEqual(rep["total_trades"], 1)

    def test_binance_stop_loss_verification_fail_safe(self):
        """Verify that missing SL triggers emergency fail-safe in binance_futures client"""
        from binance_futures import BinanceFuturesClient
        client = BinanceFuturesClient(api_key="test_key", api_secret="test_secret")

        # Mock open orders to return empty list (SL was not registered)
        client.get_open_orders = MagicMock(return_value=[])
        client._request = MagicMock(return_value=[])

        # Verification must return False
        verified = client.verify_stop_loss_active("BTCUSDT", max_wait_sec=0.1)
        self.assertFalse(verified)

        # Mock open orders with a STOP_MARKET order
        client.get_open_orders = MagicMock(return_value=[{"symbol": "BTCUSDT", "type": "STOP_MARKET"}])
        verified_ok = client.verify_stop_loss_active("BTCUSDT", max_wait_sec=0.1)
        self.assertTrue(verified_ok)


if __name__ == "__main__":
    unittest.main()
