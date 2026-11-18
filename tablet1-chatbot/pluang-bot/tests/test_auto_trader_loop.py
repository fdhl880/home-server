"""
WP-7 TDD Test Suite: Auto-Trader Full Scan Cycle End-to-End Integration.
Covers:
  - WP-6 Strategy Gate Hook in `auto_trader.py`:
      * Advisory mode (`enforce_backtest_gate=False`, verdict `SHADOW_ONLY`) -> logs `[STRATEGY GATE ADVISORY]` warning & allows live execution.
      * Enforced mode (`enforce_backtest_gate=True`, verdict `SHADOW_ONLY`) -> blocks live execution (`STRATEGY_GATE_SHADOW_ONLY`) & registers candidate in ShadowEngine.
  - Auto-Degradation Gate (`DEGRADED_STRAT_FILE`) -> demotes setup to `STRATEGY_DEMOTED_SHADOW_ONLY` & registers candidate in ShadowEngine.
  - Bidirectional BTC Guard -> blocks altcoin LONG on BTC dump (`REJECTED_BTC_DUMP`) and altcoin SHORT on BTC pump (`REJECTED_BTC_PUMP`).

Strictly offline (mocked pipeline/exchange, zero live network calls).
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

from tests.test_wp5_resilience import _isolate_at_env, _restore_at_env


def _mock_pipeline_approved(symbol: str = "SOL-USD", direction: str = "LONG", setup: str = "S1_TREND_PULLBACK"):
    entry = 150.0
    sl = 148.5 if direction == "LONG" else 151.5
    tp1 = 150.825 if direction == "LONG" else 149.175
    tp2 = 153.0 if direction == "LONG" else 147.0
    return {
        "symbol": symbol,
        "status": "APPROVED",
        "layer1_scan": {"symbol": symbol, "price": entry},
        "market_data": {"current_price": entry, "atr_pct": 1.2},
        "layer2_setup": {"setup_name": setup, "direction": direction},
        "layer3_plan": {
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "take_profit": tp2,
            "order_type": "MAKER_FIRST_GTX",
        },
        "layer5_final_call": {
            "status": "APPROVED",
            "direction": direction,
            "confidence_score": 82,
            "calibrated_prob": 0.80,
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "take_profit": tp2,
            "position_size_idr": 330000,
            "order_type": "MAKER_FIRST_GTX",
            "final_reason": "Strong quant & AI alignment",
            "math_proof": {"statistical_regime": "TREND_BULL" if direction == "LONG" else "TREND_BEAR"},
        },
        "committee": {
            "approved": True,
            "direction": direction,
            "confidence_pct": 84,
            "portfolio_manager": {"decision": "Approved by 9-agent consensus"},
            "trade_params": {
                "entry_price": entry,
                "sl_price": sl,
                "tp1_price": tp1,
                "tp2_price": tp2,
                "position_size_idr": 330000,
            },
        },
    }


class TestAutoTraderScanLoop(unittest.TestCase):
    def setUp(self):
        import shadow.promote as sp

        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp_dir = self._tmp.name
        self.saved = _isolate_at_env(self.tmp_dir)
        self.orig_gate_path = sp.DEFAULT_STRATEGY_GATE_PATH
        self.gate_path = os.path.join(self.tmp_dir, "strategy_gate.json")
        sp.DEFAULT_STRATEGY_GATE_PATH = self.gate_path

    def tearDown(self):
        import shadow.promote as sp

        sp.DEFAULT_STRATEGY_GATE_PATH = self.orig_gate_path
        _restore_at_env(self.saved)
        self._tmp.cleanup()

    def _write_gate(self, setup: str, verdict: str = "SHADOW_ONLY"):
        import shadow.promote as sp

        sp.write_strategy_gate(
            {
                "schema_version": 1,
                "data_days": 365.0,
                "strategies": {
                    setup: {
                        "strategy_id": setup,
                        "verdict": verdict,
                        "dsr": 0.45 if verdict == "SHADOW_ONLY" else 0.95,
                        "pbo": 0.60 if verdict == "SHADOW_ONLY" else 0.20,
                        "ci95_low": -0.10 if verdict == "SHADOW_ONLY" else 0.22,
                        "n_oos": 25,
                        "pf_oos": 0.85 if verdict == "SHADOW_ONLY" else 1.55,
                        "expectancy_r_oos": -0.05 if verdict == "SHADOW_ONLY" else 0.35,
                    }
                },
            },
            gate_path=self.gate_path,
        )

    def _run_cycle_with_mocks(self, cfg_override: dict, pipeline_res: dict, btc_indicators: dict = None):
        import auto_trader as at

        cand_list = [{"symbol": "SOL-USD", "pair": "SOLUSDT", "name": "Solana", "tier": "CORE", "opportunity_score": 7.5}]
        mock_bn = MagicMock()
        mock_bn.get_positions.return_value = []
        btc_ind = btc_indicators or {
            "rsi_14": 52.0,
            "current_price": 65000.0,
            "ema_20": 64800.0,
            "ema_9": 64900.0,
            "change_4h_pct": 0.4,
        }
        base_cfg = {
            "max_budget_idr": 0,
            "max_concurrent_positions": 1,
            "max_same_direction_positions": 1,
            "enforce_backtest_gate": False,
            "order_type": "MAKER_FIRST_GTX",
            **cfg_override,
        }

        with patch.object(at, "load_state"), \
             patch.object(at, "save_state"), \
             patch.object(at, "sync_control_flags_from_disk", return_value=True), \
             patch.object(at, "check_wallet_and_position_guard", return_value={"pause_scanning": False, "working_usdt": 50.0, "available_usdt": 50.0}), \
             patch.object(at, "_get_config", return_value=base_cfg), \
             patch.object(at, "rank_universe_by_opportunity", return_value=cand_list), \
             patch.object(at, "detect_market_regime", return_value={"regime": "TREND", "trending_pct": 70.0, "sideways_pct": 30.0, "avg_abs_change_24h": 3.2}), \
             patch.object(at, "_technical_pre_filter", return_value=cand_list), \
             patch.object(at, "get_binance_client", return_value=mock_bn), \
             patch.object(at, "_get_effective_open_positions", return_value=([], [], None)), \
             patch.object(at, "run_5_layer_pipeline", return_value=pipeline_res), \
             patch("market_data.get_market_indicators_fast", return_value=btc_ind), \
             patch.object(at, "send_telegram"), \
             patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
             patch.object(at, "record_position", return_value={"id": "POS_SOL_1", "symbol": "SOL-USD", "binance_synced": True, "order_id": 12345, "entry_price": 150.0, "stop_loss": 148.5, "take_profit_1": 150.825, "take_profit_2": 153.0, "position_size_idr": 330000, "position_size_usd": 20.0}) as mock_rec:
            at.run_full_scan_cycle()
            return mock_rec

    def test_strategy_gate_advisory_logs_warning_and_allows_live(self):
        """Decision 2.B: enforce_backtest_gate=False logs advisory warning on SHADOW_ONLY verdict and executes live."""
        import auto_trader as at

        self._write_gate("S1_TREND_PULLBACK", verdict="SHADOW_ONLY")
        pipe_res = _mock_pipeline_approved("SOL-USD", "LONG", "S1_TREND_PULLBACK")

        with self.assertLogs("auto_trader", level="WARNING") as cm:
            mock_rec = self._run_cycle_with_mocks({"enforce_backtest_gate": False}, pipe_res)

        self.assertTrue(any("[STRATEGY GATE ADVISORY]" in line for line in cm.output))
        mock_rec.assert_called_once()
        self.assertEqual(at.state["recent_signals"][0]["status"], "APPROVED")

    def test_strategy_gate_enforced_blocks_live_and_registers_shadow(self):
        """Decision 2.B: enforce_backtest_gate=True blocks SHADOW_ONLY strategy with STRATEGY_GATE_SHADOW_ONLY and records shadow trade."""
        import auto_trader as at
        import journal

        self._write_gate("S1_TREND_PULLBACK", verdict="SHADOW_ONLY")
        pipe_res = _mock_pipeline_approved("SOL-USD", "LONG", "S1_TREND_PULLBACK")

        mock_rec = self._run_cycle_with_mocks({"enforce_backtest_gate": True}, pipe_res)
        mock_rec.assert_not_called()
        self.assertEqual(at.state["recent_signals"][0]["status"], "STRATEGY_GATE_SHADOW_ONLY")

        with contextlib.closing(journal.get_db(journal.DB_PATH)) as conn:
            sh_rows = conn.execute("SELECT * FROM shadow_trades WHERE symbol = 'SOL-USD'").fetchall()
        self.assertEqual(len(sh_rows), 1)
        self.assertEqual(sh_rows[0]["strategy_id"], "S1_TREND_PULLBACK")
        self.assertEqual(sh_rows[0]["status"], "OPEN")

    def test_degraded_strat_file_blocks_live_and_registers_shadow(self):
        """Auto-Degradation file demotes degraded setup to STRATEGY_DEMOTED_SHADOW_ONLY and registers shadow trade."""
        import auto_trader as at
        import journal

        self._write_gate("S1_TREND_PULLBACK", verdict="LIVE_APPROVED")
        with open(at.DEGRADED_STRAT_FILE, "w", encoding="utf-8") as f:
            json.dump({"S1_TREND_PULLBACK": {"degraded": True, "reason": "Rolling 15 trades PF=0.62 < 0.80"}}, f)

        pipe_res = _mock_pipeline_approved("SOL-USD", "LONG", "S1_TREND_PULLBACK")
        mock_rec = self._run_cycle_with_mocks({"enforce_backtest_gate": False}, pipe_res)
        mock_rec.assert_not_called()
        self.assertEqual(at.state["recent_signals"][0]["status"], "STRATEGY_DEMOTED_SHADOW_ONLY")

        with contextlib.closing(journal.get_db(journal.DB_PATH)) as conn:
            sh_rows = conn.execute("SELECT * FROM shadow_trades WHERE symbol = 'SOL-USD'").fetchall()
        self.assertEqual(len(sh_rows), 1)

    def test_bidirectional_btc_guard_blocks_long_on_dump_and_short_on_pump(self):
        """T3.1: Altcoin LONG blocked when BTC dumps (REJECTED_BTC_DUMP); Altcoin SHORT blocked when BTC pumps (REJECTED_BTC_PUMP)."""
        import auto_trader as at

        self._write_gate("S1_TREND_PULLBACK", verdict="LIVE_APPROVED")

        # 1. Altcoin LONG during BTC dump (RSI=34 < 40)
        pipe_long = _mock_pipeline_approved("SOL-USD", "LONG", "S1_TREND_PULLBACK")
        mock_rec_long = self._run_cycle_with_mocks(
            {"enforce_backtest_gate": False},
            pipe_long,
            btc_indicators={"rsi_14": 34.0, "current_price": 60000.0, "ema_20": 62000.0, "ema_9": 61000.0, "change_4h_pct": -2.5},
        )
        mock_rec_long.assert_not_called()
        self.assertEqual(at.state["recent_signals"][0]["status"], "REJECTED_BTC_DUMP")

        # 2. Altcoin SHORT during BTC pump (RSI=68 > 62)
        pipe_short = _mock_pipeline_approved("SOL-USD", "SHORT", "S1_TREND_PULLBACK")
        mock_rec_short = self._run_cycle_with_mocks(
            {"enforce_backtest_gate": False},
            pipe_short,
            btc_indicators={"rsi_14": 68.0, "current_price": 68000.0, "ema_20": 65000.0, "ema_9": 66500.0, "change_4h_pct": 2.8},
        )
        mock_rec_short.assert_not_called()
        self.assertEqual(at.state["recent_signals"][0]["status"], "REJECTED_BTC_PUMP")


if __name__ == "__main__":
    unittest.main(verbosity=2)
