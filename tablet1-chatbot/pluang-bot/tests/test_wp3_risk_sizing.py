"""
WP-3 TDD Test Suite: 20x Protection Guards, Live HardRiskEngine Enforcement,
Profit Vault Isolation & Transfer Awareness, Entry Drift & Funding Gates.

Strictly offline (mocked Binance client / mocked HTTP, zero live keys or network calls).
Covers:
  - Decision 1.B & Decision 4: 20x ALL_IN (0.95) preserved, 12h breaker only (no CUMULATIVE_DD_KILL)
  - C-13 / BF:1793-1805 / AT:539: Locked Profit Vault protection (no $1 floor, strict working_usdt*0.98 cap)
    and external deposit/withdrawal transfer awareness on ProfitRatchetVault & HardRiskEngine
  - B-9 & WP-2 A-3: HardRiskEngine.validate_and_size wired live in record_position, and
    HardRiskEngine.execute_panic fixed to close-first -> verify flat -> cancel-after
  - B-8: Continuous live equity DD tracking (wallet_balance + cross_unrealized_pnl) in guard
  - B-10: Live price preference in market_data & pipeline, plus STALE_ENTRY_DRIFT rejection & re-anchor
  - C-9 & C-12: get_funding_info(symbol) /premiumIndex helper, <15m paying >=0.05% funding gate,
    cumulative funding in monitor time-cut, and live exchange concurrent/directional caps
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)


def _isolate_env(tmp: str) -> dict:
    import auto_trader as at
    import journal
    import risk.vault as rv
    import features.hmm_drift as hd
    import strategies.bandit_allocator as ba

    saved = {
        "at_RESULTS_DIR": at.RESULTS_DIR,
        "at_STATE_FILE": at.STATE_FILE,
        "at_POSITIONS_FILE": at.POSITIONS_FILE,
        "at_PERF_LEDGER_FILE": at.PERF_LEDGER_FILE,
        "at_RISK_BREAKER_FILE": at.RISK_BREAKER_FILE,
        "at_DEGRADED_STRAT_FILE": at.DEGRADED_STRAT_FILE,
        "at_UNIVERSE_FILE": at.UNIVERSE_FILE,
        "at_state": dict(at.state),
        "journal_DB_PATH": journal.DB_PATH,
        "rv_DEFAULT": rv.DEFAULT_VAULT_STATE_PATH,
        "hd_CAL": hd.DEFAULT_CALIBRATOR_PATH,
        "hd_CONF": hd.DEFAULT_CONFORMAL_PATH,
        "ba_DEFAULT": ba.DEFAULT_STATE_PATH,
    }

    at.RESULTS_DIR = tmp
    at.STATE_FILE = os.path.join(tmp, "autotrader_state.json")
    at.POSITIONS_FILE = os.path.join(tmp, "active_positions.json")
    at.PERF_LEDGER_FILE = os.path.join(tmp, "performance_ledger.json")
    at.RISK_BREAKER_FILE = os.path.join(tmp, "risk_breaker_state.json")
    at.DEGRADED_STRAT_FILE = os.path.join(tmp, "degraded_strategies.json")
    at.UNIVERSE_FILE = os.path.join(tmp, "universe_state.json")
    at._THESIS_MONITOR = None
    at.state["binance_wallet_balance_usdt"] = 0.0
    at.state["binance_available_balance_usdt"] = 0.0
    at.state["binance_unrealized_pnl_usdt"] = 0.0

    journal.DB_PATH = os.path.join(tmp, "journal.db")
    journal.init_db(journal.DB_PATH)

    rv.reset_profit_vault_cache()
    rv.DEFAULT_VAULT_STATE_PATH = os.path.join(tmp, "vault_state.json")
    hd.DEFAULT_CALIBRATOR_PATH = os.path.join(tmp, "cal.json")
    hd.DEFAULT_CONFORMAL_PATH = os.path.join(tmp, "conf.json")
    ba.DEFAULT_STATE_PATH = os.path.join(tmp, "bandit.json")
    return saved


def _restore_env(saved: dict) -> None:
    import auto_trader as at
    import journal
    import risk.vault as rv
    import features.hmm_drift as hd
    import strategies.bandit_allocator as ba

    at.RESULTS_DIR = saved["at_RESULTS_DIR"]
    at.STATE_FILE = saved["at_STATE_FILE"]
    at.POSITIONS_FILE = saved["at_POSITIONS_FILE"]
    at.PERF_LEDGER_FILE = saved["at_PERF_LEDGER_FILE"]
    at.RISK_BREAKER_FILE = saved["at_RISK_BREAKER_FILE"]
    at.DEGRADED_STRAT_FILE = saved["at_DEGRADED_STRAT_FILE"]
    at.UNIVERSE_FILE = saved["at_UNIVERSE_FILE"]
    at.state.clear()
    at.state.update(saved["at_state"])
    journal.DB_PATH = saved["journal_DB_PATH"]
    rv.reset_profit_vault_cache()
    rv.DEFAULT_VAULT_STATE_PATH = saved["rv_DEFAULT"]
    hd.DEFAULT_CALIBRATOR_PATH = saved["hd_CAL"]
    hd.DEFAULT_CONFORMAL_PATH = saved["hd_CONF"]
    ba.DEFAULT_STATE_PATH = saved["ba_DEFAULT"]


def _cfg(**overrides) -> dict:
    c = {
        "fixed_leverage": 20,
        "max_leverage": 20,
        "margin_type": "ISOLATED",
        "sizing_mode": "ALL_IN",
        "all_in_balance_fraction": 0.95,
        "max_sl_pct": 2.25,
        "min_sl_pct": 0.45,
        "min_liq_to_sl_ratio": 2.0,
        "min_risk_reward_ratio": 1.5,
        "min_ev_r": 0.20,
        "breaker_daily_dd_pct": 15.0,
        "breaker_consecutive_losses": 2,
        "circuit_breaker_consecutive_losses": 2,
        "breaker_cooldown_hours": 12,
        "max_concurrent_positions": 1,
        "max_daily_trades": 10,
        "auto_execute": True,
        "sniper_75_mode": {
            "enabled": True,
            "min_calibrated_p_tp1": 0.76,
            "conformal_alpha_target": 0.18,
            "tp1_lock_trigger_r": 0.55,
            "tp1_partial_close_pct": 0.65,
            "sl_lock_after_tp1_r": 0.38,
            "tp2_runner_target_r": 1.60,
            "early_invalidation_max_loss_r": 0.35,
        },
    }
    c.update(overrides)
    return c


class TestDecision1BAndDecision4Mandates(unittest.TestCase):
    def test_locked_20x_all_in_and_no_cumulative_kill_switch(self):
        """Decision 1.B & Decision 4: keep 20x ALL_IN (0.95) and NO permanent CUMULATIVE_DD_KILL."""
        from risk.engine import HardRiskEngine

        with open(os.path.join(BOT_DIR, "trading_config.json"), "r", encoding="utf-8") as f:
            live_cfg = json.load(f)
        self.assertEqual(live_cfg["fixed_leverage"], 20)
        self.assertEqual(live_cfg["sizing_mode"], "ALL_IN")
        self.assertAlmostEqual(live_cfg["all_in_balance_fraction"], 0.95)
        self.assertEqual(live_cfg["breaker_daily_dd_pct"], 15.0)
        self.assertEqual(live_cfg["circuit_breaker_consecutive_losses"], 2)
        self.assertEqual(live_cfg["breaker_cooldown_hours"], 12)

        for rel in ("risk/engine.py", "auto_trader.py"):
            with open(os.path.join(BOT_DIR, rel), "r", encoding="utf-8") as f:
                self.assertNotIn("CUMULATIVE_DD_KILL", f.read())

        # Deep cumulative drawdown across days resets cleanly after 12h cooldown (never permanently locked)
        eng = HardRiskEngine(config=_cfg())
        eng.daily_start_equity = 100.0
        eng.current_equity = 100.0
        eng.record_trade_result(-20.0, new_equity=80.0, now_ts=1000.0)
        self.assertTrue(eng.is_circuit_breaker_active(now_ts=1000.0))
        self.assertFalse(eng.is_circuit_breaker_active(now_ts=1000.0 + 12.1 * 3600.0))
        # Even after a second 20% day on another day, 12h expiry still allows trading again
        eng.record_trade_result(-16.0, new_equity=64.0, now_ts=60000.0)
        self.assertTrue(eng.is_circuit_breaker_active(now_ts=60000.0))
        self.assertFalse(eng.is_circuit_breaker_active(now_ts=60000.0 + 12.1 * 3600.0))


class TestProfitVaultProtectionAndTransfers(unittest.TestCase):
    def test_at_removes_1_dollar_floor_and_blocks_locked_vault(self):
        """C-13 / AT:539: When locked_vault >= avail_usdt - 0.30, NEVER trade with $1 floor."""
        import auto_trader as at
        import risk.vault as rv

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                v = rv.get_profit_vault(initial_equity=100.0, state_path=rv.DEFAULT_VAULT_STATE_PATH, persist=True)
                # Equity grows +100% -> locks 35% of 100 = $35.0; simulate drawdown leaving avail=$35.10 ($0.10 working)
                v.update_equity(200.0)
                self.assertAlmostEqual(v.locked_profit_vault_usdt, 35.0, places=4)

                bn = MagicMock()
                bn.get_balance.return_value = {"available_balance": 35.10, "total_wallet_balance": 35.10}
                bn.get_positions.return_value = []
                bn.get_market_price.return_value = 150.0

                sig = {
                    "symbol": "SOL-USD",
                    "binance_pair": "SOLUSDT",
                    "direction": "LONG",
                    "entry_price": 150.0,
                    "stop_loss": 148.5,
                    "take_profit": 154.5,
                    "confidence_score": 85,
                }
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}):
                    res = at.record_position(sig)

                self.assertIsNone(res)
                bn.execute_full_trade.assert_not_called()

                # Also when locked_vault > avail_usdt (e.g. avail=$20, locked=$35) -> working=0, rejected!
                bn.get_balance.return_value = {"available_balance": 20.0, "total_wallet_balance": 20.0}
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}):
                    res2 = at.record_position(sig)
                self.assertIsNone(res2)
                bn.execute_full_trade.assert_not_called()
            finally:
                _restore_env(saved)

    def test_bf_min_notional_bump_cannot_touch_locked_vault_and_caps_at_098(self):
        """BF:1793-1805: minNotional bump MUST respect working_usdt * 0.98 and NEVER touch locked_vault."""
        from binance_futures import BinanceFuturesClient
        import risk.vault as rv
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_v = rv.DEFAULT_VAULT_STATE_PATH
            try:
                rv.DEFAULT_VAULT_STATE_PATH = os.path.join(tmp, "vault_state.json")
                state_io.atomic_write_json(rv.DEFAULT_VAULT_STATE_PATH, {
                    "initial_session_equity": 100.0,
                    "high_water_mark_equity": 200.0,
                    "locked_profit_vault_usdt": 50.0,
                }, make_bak=False)

                client = BinanceFuturesClient(api_key="k", api_secret="s")
                client._symbol_cache["ETHUSDT"] = {
                    "status": "TRADING", "contractType": "PERPETUAL",
                    "quantityPrecision": 3, "pricePrecision": 2,
                    "stepSize": 0.001, "minQty": 0.001, "tickSize": 0.01, "minNotional": 20.0,
                }
                client._symbol_cache_time = 10**12

                # avail=$50.50, locked=$50.00 => working=$0.50; ETH minNotional=$20 needs $1.02 margin (>0.49 working cap)
                with patch.object(client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
                     patch.object(client, "get_positions", return_value=[]), \
                     patch.object(client, "get_balance", return_value={"available_balance": 50.50}), \
                     patch.object(client, "get_market_price", return_value=2000.0), \
                     patch.object(client, "set_margin_type", return_value={"code": 200}), \
                     patch.object(client, "set_leverage", return_value={"leverage": 20}), \
                     patch.object(client, "open_position") as mock_open:
                    res = client.execute_full_trade(
                        {"symbol": "ETHUSDT", "direction": "LONG", "entry_price": 2000.0, "stop_loss": 1970.0, "take_profit": 2060.0},
                        _cfg(all_in_balance_fraction=1.0),
                    )
                self.assertEqual(res["status"], "REJECTED_VAULT_PROTECTED")
                self.assertFalse(res["binance_synced"])
                mock_open.assert_not_called()

                # Even with locked_vault=0, budget_cap MUST NOT exceed working_usdt * 0.98
                state_io.atomic_write_json(rv.DEFAULT_VAULT_STATE_PATH, {"locked_profit_vault_usdt": 0.0}, make_bak=False)
                # working=$1.03 at 0.95 -> notional=$19.57 < $20, needed_margin=$1.02 > 1.03*0.98=$1.0094 -> rejected!
                with patch.object(client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
                     patch.object(client, "get_positions", return_value=[]), \
                     patch.object(client, "get_balance", return_value={"available_balance": 1.03}), \
                     patch.object(client, "get_market_price", return_value=2000.0), \
                     patch.object(client, "get_order_book", return_value={}), \
                     patch.object(client, "set_margin_type", return_value={"code": 200}), \
                     patch.object(client, "set_leverage", return_value={"leverage": 20}), \
                     patch.object(client, "open_position") as mock_open2:
                    res2 = client.execute_full_trade(
                        {"symbol": "ETHUSDT", "direction": "LONG", "entry_price": 2000.0, "stop_loss": 1970.0, "take_profit": 2060.0},
                        _cfg(all_in_balance_fraction=0.95),
                    )
                self.assertEqual(res2["status"], "REJECTED_NOTIONAL_CAPACITY")
                mock_open2.assert_not_called()

                # Even if config supplies all_in_balance_fraction=1.0, cap stays strictly 0.98
                with patch.object(client, "check_account_modes", return_value={"dualSidePosition": False, "multiAssetsMargin": False, "ok": True}), \
                     patch.object(client, "get_positions", return_value=[]), \
                     patch.object(client, "get_balance", return_value={"available_balance": 1.01}), \
                     patch.object(client, "get_market_price", return_value=2000.0), \
                     patch.object(client, "get_order_book", return_value={}), \
                     patch.object(client, "set_margin_type", return_value={"code": 200}), \
                     patch.object(client, "set_leverage", return_value={"leverage": 20}), \
                     patch.object(client, "open_position") as mock_open3:
                    res3 = client.execute_full_trade(
                        {"symbol": "ETHUSDT", "direction": "LONG", "entry_price": 2000.0, "stop_loss": 1970.0, "take_profit": 2060.0},
                        _cfg(all_in_balance_fraction=1.0),
                    )
                self.assertEqual(res3["status"], "REJECTED_NOTIONAL_CAPACITY")
                mock_open3.assert_not_called()
            finally:
                rv.DEFAULT_VAULT_STATE_PATH = orig_v

    def test_vault_record_transfer_prevents_false_hwm_lock_and_fake_dd(self):
        """C-13: External deposit shifts HWM/baseline without locking 35%; withdrawal adjusts baseline/DD."""
        from risk.vault import ProfitRatchetVault
        from risk.engine import HardRiskEngine

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            v_path = os.path.join(tmp, "vault_state.json")
            v = ProfitRatchetVault(initial_equity=100.0, state_path=v_path, persist=True)
            eng = HardRiskEngine(config=_cfg(), vault=v)
            eng.daily_start_equity = 100.0
            eng.current_equity = 100.0

            # External deposit +$100 -> must NOT lock 35% of user's deposit!
            tr_dep = eng.record_transfer(+100.0, note="deposit")
            self.assertTrue(tr_dep["vault_transfer"]["recorded"])
            self.assertAlmostEqual(v.high_water_mark_equity, 200.0, places=4)
            self.assertAlmostEqual(v.baseline_equity, 200.0, places=4)
            self.assertAlmostEqual(v.locked_profit_vault_usdt, 0.0, places=4)

            eq_res = v.update_equity(200.0)
            self.assertFalse(eq_res["ratcheted"])
            self.assertAlmostEqual(eq_res["locked_profit_vault_usdt"], 0.0, places=4)
            self.assertAlmostEqual(eq_res["working_balance_usdt"], 200.0, places=4)

            # Trading gain +15% above adjusted $200 -> $230 DOES lock 35% * 30 = $10.50
            eq_res2 = v.update_equity(230.0)
            self.assertTrue(eq_res2["ratcheted"])
            self.assertAlmostEqual(eq_res2["newly_locked_usdt"], 10.5, places=4)

            # External withdrawal -$50 -> adjusts HWM, baseline & daily_start_equity so NO fake DD breaker trips!
            eng.daily_start_equity = 230.0
            eng.current_equity = 230.0
            eng.record_transfer(-50.0, note="withdraw to spot")
            self.assertAlmostEqual(v.high_water_mark_equity, 180.0, places=4)
            self.assertAlmostEqual(v.locked_profit_vault_usdt, 10.5, places=4)
            dd_chk = eng.check_live_equity_drawdown(live_equity=180.0)
            self.assertAlmostEqual(dd_chk["daily_dd_pct"], 0.0, places=4)
            self.assertFalse(dd_chk["breaker_active"])


class TestHardRiskEngineLiveWiringAndExecutePanic(unittest.TestCase):
    def test_record_position_enforces_validate_and_size_bounds(self):
        """B-9: record_position invokes HardRiskEngine.validate_and_size BEFORE execute_full_trade."""
        import auto_trader as at

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                bn = MagicMock()
                bn.get_balance.return_value = {"available_balance": 100.0, "total_wallet_balance": 100.0}
                bn.get_positions.return_value = []
                bn.get_market_price.return_value = 100.0

                base_sig = {
                    "symbol": "SOL-USD",
                    "binance_pair": "SOLUSDT",
                    "direction": "LONG",
                    "entry_price": 100.0,
                    "stop_loss": 98.5,
                    "take_profit": 103.0,
                    "confidence_score": 82,
                }

                # 1. SL > 2.25% (3.0% SL) must be rejected by validate_and_size (NOT silently clamped!)
                wide_sig = dict(base_sig, stop_loss=97.0)
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}):
                    self.assertIsNone(at.record_position(wide_sig))
                bn.execute_full_trade.assert_not_called()

                # 2. Liquidation proximity < 2.0x SL (liq at 97.0 = 3.0% away while SL = 1.8% -> 1.67x < 2.0x)
                liq_sig = dict(base_sig, stop_loss=98.2, take_profit=104.0, liquidation_price=97.0)
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}):
                    self.assertIsNone(at.record_position(liq_sig))
                bn.execute_full_trade.assert_not_called()

                # 3. Low RRR (0.8 RRR < 1.5) rejected
                low_rrr_sig = dict(base_sig, stop_loss=98.5, take_profit=101.2)
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}):
                    self.assertIsNone(at.record_position(low_rrr_sig))
                bn.execute_full_trade.assert_not_called()

                # 4. Real pipeline conformal ambiguity / low p_cal rejected
                ambig_sig = dict(base_sig, calibrated_prob=0.70, conformal_set=["WIN", "LOSS"])
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}):
                    self.assertIsNone(at.record_position(ambig_sig))
                bn.execute_full_trade.assert_not_called()
            finally:
                _restore_env(saved)

    def test_execute_panic_closes_first_verifies_flat_before_cancel(self):
        """WP-2 A-3 handoff: HardRiskEngine.execute_panic closes first, verifies flat, THEN cancels orders."""
        from risk.engine import HardRiskEngine

        # Case 1: Successful close + verified flat -> close_position -> get_positions -> cancel_all_orders
        call_seq = []

        class MockPanicOK:
            def __init__(self):
                self.closed = False

            def get_positions(self, symbol=None):
                call_seq.append(("get_positions", symbol))
                if self.closed:
                    return []
                return [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 2.0}]

            def close_position(self, symbol, direction, quantity=None):
                call_seq.append(("close_position", symbol))
                self.closed = True
                return {"orderId": 101, "status": "FILLED"}

            def cancel_all_orders(self, symbol):
                call_seq.append(("cancel_all_orders", symbol))
                return {"standard": {}, "algo": {}}

        eng = HardRiskEngine(config=_cfg())
        res_ok = eng.execute_panic(MockPanicOK())
        self.assertTrue(res_ok["all_flat_verified"])
        self.assertEqual(res_ok["closed_symbols"], ["SOLUSDT"])
        self.assertEqual(res_ok["cancelled_symbols"], ["SOLUSDT"])
        self.assertLess(
            call_seq.index(("close_position", "SOLUSDT")),
            call_seq.index(("get_positions", "SOLUSDT")),
        )
        self.assertLess(
            call_seq.index(("get_positions", "SOLUSDT")),
            call_seq.index(("cancel_all_orders", "SOLUSDT")),
        )

        # Case 2: Close fails OR position remains open -> NEVER cancel orders!
        call_seq_fail = []

        class MockPanicFail:
            def get_positions(self, symbol=None):
                call_seq_fail.append(("get_positions", symbol))
                return [{"symbol": "ETHUSDT", "direction": "SHORT", "position_amount": 1.0}]

            def close_position(self, symbol, direction, quantity=None):
                call_seq_fail.append(("close_position", symbol))
                return {"orderId": 102, "status": "NEW"}  # Still not flat on verify!

            def cancel_all_orders(self, symbol):
                call_seq_fail.append(("cancel_all_orders", symbol))
                return {}

        eng2 = HardRiskEngine(config=_cfg())
        res_fail = eng2.execute_panic(MockPanicFail())
        self.assertFalse(res_fail["all_flat_verified"])
        self.assertEqual(res_fail["cancelled_symbols"], [])
        self.assertNotIn(("cancel_all_orders", "ETHUSDT"), call_seq_fail)
        self.assertTrue(len(res_fail["failed_symbols"]) == 1)


class TestLiveEquityDrawdownB8(unittest.TestCase):
    def test_guard_tracks_live_equity_with_unrealized_pnl_and_trips_12h_breaker(self):
        """B-8: Guard computes wallet + cross_unrealized_pnl, trips >=15% DD 12h breaker & saves disk."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                bal_state = {"total": 100.0, "avail": 100.0, "upnl": 0.0}

                class MockBalBN:
                    def get_balance(self):
                        return {
                            "total_wallet_balance": bal_state["total"],
                            "available_balance": bal_state["avail"],
                            "cross_unrealized_pnl": bal_state["upnl"],
                        }

                    def get_positions(self, symbol=None):
                        return []

                with patch.object(at, "get_binance_client", return_value=MockBalBN()), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "send_telegram") as mock_tg:
                    g1 = at.check_wallet_and_position_guard()
                    self.assertFalse(g1["pause_scanning"])
                    self.assertAlmostEqual(g1["live_equity"], 100.0, places=3)

                    # Simulate -16.5% unrealized drawdown without realizing close yet
                    bal_state["upnl"] = -16.5
                    g2 = at.check_wallet_and_position_guard()
                    self.assertTrue(g2["pause_scanning"])
                    self.assertAlmostEqual(g2["live_equity"], 83.5, places=3)
                    self.assertIn("DAILY_DRAWDOWN", g2["reason"])
                    self.assertTrue(mock_tg.called)

                brk_disk = state_io.read_json_safe(at.RISK_BREAKER_FILE, default={}, strict_on_corrupt=True)
                self.assertTrue(brk_disk["breaker_active"])
                self.assertGreaterEqual(brk_disk["daily_dd_pct"], 16.0)
            finally:
                _restore_env(saved)


class TestStaleEntryPlansAndDriftB10(unittest.TestCase):
    def test_market_data_and_pipeline_prefer_live_price_over_stale_close(self):
        """B-10: get_market_indicators_fast & layer3_build_plan prefer live_price over closed 1h close."""
        import market_data as md
        import pipeline as pl

        fake_klines = {
            "opens": [99.0] * 30,
            "highs": [101.0] * 30,
            "lows": [98.0] * 30,
            "closes": [100.0] * 30,  # stale closed 1h candle
            "volumes": [1000.0] * 30,
            "live_price": 103.5,     # forming bar live price
            "count": 30,
        }
        with patch("market_data.get_binance_klines", return_value=fake_klines), \
             patch("market_data.get_binance_funding_rate", return_value={"funding_rate": 0.0}), \
             patch("market_data.get_binance_open_interest", return_value={"open_interest": 1000}), \
             patch("market_data.get_binance_long_short_ratio", return_value={"long_short_ratio": 1.0}), \
             patch("market_data.get_crypto_fear_greed", return_value={"value": 50}), \
             patch("market_data.get_usd_idr_rate", return_value=16500):
            ind = md.get_market_indicators_fast("SOLUSDT", "SOL-USD")
        self.assertAlmostEqual(ind["current_price"], 103.5, places=4)
        self.assertAlmostEqual(ind["live_price"], 103.5, places=4)

        # layer3_build_plan fallback uses live_price (103.5), not stale 100.0
        with patch("pipeline._ai_json", side_effect=pl.AIUnavailable("ALL_AI_FAILED")):
            plan = pl.layer3_build_plan(
                "SOL-USD",
                {"levels": {"support_1": 101.0, "resistance_1": 108.0}},
                {"direction": "LONG", "setup_name": "EMA_PULLBACK", "ai_fallback": True},
                {"current_price": 100.0, "live_price": 103.5, "atr_pct": 1.0},
            )
        self.assertAlmostEqual(plan["entry_price"], 103.5, places=4)
        self.assertLess(plan["stop_loss"], 103.5)
        self.assertGreater(plan["take_profit"], 103.5)

    def test_record_position_rejects_stale_drift_and_reanchors_small_drift(self):
        """B-10: Reject STALE_ENTRY_DRIFT (>max(0.5%, 0.6*sl_pct)); re-anchor SL/TP within tolerance."""
        import auto_trader as at

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                bn = MagicMock()
                bn.get_balance.return_value = {"available_balance": 50.0, "total_wallet_balance": 50.0}
                bn.get_positions.return_value = []
                bn.execute_full_trade.return_value = {
                    "status": "EXECUTED", "binance_synced": True, "order_id": 501,
                    "entry_price": 100.3, "take_profit": 103.309, "stop_loss": 98.7955,
                    "quantity": 9.47, "sl_state": "CONFIRMED", "sl_verified": True, "leverage": 20,
                }

                # 1. Plan=100.0, SL=99.0 (1.0% SL -> tol=0.6%), live=101.0 (1.0% drift > 0.6%) -> REJECT!
                bn.get_market_price.return_value = 101.0
                sig_stale = {
                    "symbol": "SOL-USD", "binance_pair": "SOLUSDT", "direction": "LONG",
                    "entry_price": 100.0, "stop_loss": 99.0, "take_profit": 102.5,
                    "confidence_score": 84,
                }
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}):
                    self.assertIsNone(at.record_position(sig_stale))
                bn.execute_full_trade.assert_not_called()

                # 2. Small drift within tol: Plan=100.0, SL=98.5 (1.5% SL -> tol=0.9%), live=100.3 (0.3% drift)
                bn.get_market_price.return_value = 100.3
                sig_small = {
                    "symbol": "SOL-USD", "binance_pair": "SOLUSDT", "direction": "LONG",
                    "entry_price": 100.0, "stop_loss": 98.5, "take_profit": 103.0,
                    "confidence_score": 84,
                }
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch("journal.open_trade", return_value=None):
                    pos = at.record_position(sig_small)

                self.assertIsNotNone(pos)
                sent_sig = bn.execute_full_trade.call_args.kwargs["signal"]
                self.assertAlmostEqual(sent_sig["entry_price"], 100.3, places=4)
                # Preserved 1.5% SL & 3.0% TP distances around 100.3
                self.assertAlmostEqual(sent_sig["stop_loss"], round(100.3 * 0.985, 6), places=4)
                self.assertAlmostEqual(sent_sig["take_profit"], round(100.3 * 1.030, 6), places=4)
            finally:
                _restore_env(saved)


class TestFundingGateAndConcurrentDirectionalExposure(unittest.TestCase):
    def test_bf_get_funding_info_symbol_and_backward_compat(self):
        """C-9: get_funding_info() keeps /fundingInfo; get_funding_info(sym) queries /premiumIndex."""
        from binance_futures import BinanceFuturesClient

        c = BinanceFuturesClient(api_key="k", api_secret="s")
        with patch.object(c, "_request", side_effect=[
            [{"symbol": "SOLUSDT", "fundingIntervalHours": 4}],
            {"symbol": "SOLUSDT", "markPrice": "151.25", "lastFundingRate": "0.00075", "nextFundingTime": 1700005000000},
        ]) as mock_req:
            info_all = c.get_funding_info()
            info_sym = c.get_funding_info("SOL-USD")

        self.assertEqual(mock_req.call_args_list[0][0][:2], ("GET", "/fapi/v1/fundingInfo"))
        self.assertEqual(mock_req.call_args_list[1][0][:2], ("GET", "/fapi/v1/premiumIndex"))
        self.assertTrue(info_sym["ok"])
        self.assertAlmostEqual(info_sym["last_funding_rate"], 0.00075, places=6)
        self.assertEqual(info_sym["next_funding_time_ms"], 1700005000000)
        self.assertAlmostEqual(info_sym["mark_price"], 151.25, places=4)
        self.assertIsInstance(info_all, list)

    def test_record_position_funding_gate_and_monitor_time_cut_funding(self):
        """C-9: Block <15m paying >=0.05%; allow receiving funding; factor funding in 48h time-cut."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                now_ms = int(time.time() * 1000)
                bn = MagicMock()
                bn.get_balance.return_value = {"available_balance": 50.0, "total_wallet_balance": 50.0}
                bn.get_positions.return_value = []
                bn.execute_full_trade.return_value = {
                    "status": "EXECUTED", "binance_synced": True, "order_id": 601,
                    "entry_price": 150.0, "take_profit": 154.5, "stop_loss": 148.5,
                    "quantity": 6.33, "sl_state": "CONFIRMED", "sl_verified": True, "leverage": 20,
                }

                # 1. LONG paying +0.06% in 12m (< 15m) -> BLOCKED!
                bn.get_funding_info.return_value = {
                    "symbol": "SOLUSDT", "last_funding_rate": 0.0006,
                    "next_funding_time_ms": now_ms + 12 * 60_000, "mark_price": 150.0, "ok": True,
                }
                sig_long = {
                    "symbol": "SOL-USD", "binance_pair": "SOLUSDT", "direction": "LONG",
                    "entry_price": 150.0, "stop_loss": 148.5, "take_profit": 154.5, "confidence_score": 84,
                }
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}):
                    self.assertIsNone(at.record_position(sig_long))
                bn.execute_full_trade.assert_not_called()

                # 2. LONG receiving funding (-0.08% in 12m) -> ALLOWED!
                bn.get_funding_info.return_value = {
                    "symbol": "SOLUSDT", "last_funding_rate": -0.0008,
                    "next_funding_time_ms": now_ms + 12 * 60_000, "mark_price": 150.0, "ok": True,
                }
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch("journal.open_trade", return_value=None):
                    pos_ok = at.record_position(sig_long)
                self.assertIsNotNone(pos_ok)

                # 3. Monitor 48h timeout cut factors cumulative funding (-$3.50 funding flips +$0.50 uPnL to -6% ROE)
                old_50h = (datetime.now(timezone.utc) - timedelta(hours=50)).strftime("%Y-%m-%d %H:%M:%S UTC")
                open_ts = time.time() - 50 * 3600
                pos_f = {
                    "id": "POS_FUND_48H", "symbol": "SOL-USD", "binance_pair": "SOLUSDT",
                    "direction": "LONG", "entry_price": 150.0, "stop_loss": 148.0, "init_stop_loss": 148.0,
                    "take_profit": 156.0, "leverage": 20, "position_size_usd": 50.0, "position_size_idr": 825000,
                    "status": "OPEN", "exchange": "BINANCE_FUTURES", "binance_synced": True,
                    "sl_state": "CONFIRMED", "opened_at": old_50h, "opened_ts": open_ts,
                }
                state_io.atomic_write_json(at.POSITIONS_FILE, [pos_f], make_bak=False)

                class MockFundMonBN:
                    def __init__(self):
                        self.closed = False

                    def get_positions(self, symbol=None):
                        if self.closed:
                            return []
                        return [{
                            "symbol": "SOLUSDT", "direction": "LONG", "position_amount": 6.66,
                            "entry_price": 150.0, "mark_price": 150.05, "unrealized_pnl": 0.50,
                            "liquidation_price": 143.0, "isolated_margin": 50.0, "leverage": 20,
                        }]

                    def verify_stop_loss_active(self, *a, **kw):
                        return "CONFIRMED"

                    def get_income_history(self, symbol=None, limit=100, start_time=None):
                        return [
                            {"symbol": "SOLUSDT", "incomeType": "FUNDING_FEE", "income": "-3.50", "asset": "USDT", "time": int((open_ts + 3600) * 1000)}
                        ]

                    def close_position(self, symbol, direction, quantity=None):
                        self.closed = True
                        return {"orderId": 999, "status": "FILLED"}

                    def cancel_all_orders(self, symbol):
                        return {"standard": {}, "algo": {}}

                    def get_open_algo_orders(self, symbol=None):
                        return True, []

                    def get_balance(self):
                        return {"total_wallet_balance": 96.5, "available_balance": 96.5}

                with patch.object(at, "get_binance_client", return_value=MockFundMonBN()), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[]), \
                     patch.object(at, "_fetch_live_micro_state", return_value={"ofi_20": 0.0, "tfi_5m": 0.0, "sigma": 0.35}), \
                     patch("exec.thesis_monitor.IntrabarThesisMonitor.evaluate_position", return_value={"p_survive": 0.6, "should_scratch": False, "consecutive_breaches": 0}), \
                     patch.object(at, "send_telegram"):
                    mon_res = at.monitor_and_update_positions()
                self.assertEqual(mon_res[0]["status"], "CLOSED_TIMEOUT")
                self.assertAlmostEqual(mon_res[0]["funding_usd"], 3.50, places=3)
            finally:
                _restore_env(saved)

    def test_c12_live_concurrent_and_directional_cap_in_record_and_scan_loop(self):
        """C-12: Live exchange get_positions enforces max_concurrent & directional cap in record_position & scan loop."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                state_io.atomic_write_json(at.POSITIONS_FILE, [], make_bak=False)

                live_exchange_pos = [
                    {"symbol": "BTCUSDT", "direction": "LONG", "position_amount": 0.05}
                ]

                class MockLiveCapBN:
                    def __init__(self):
                        self.exec_calls = []

                    def get_balance(self):
                        return {"available_balance": 100.0, "total_wallet_balance": 100.0}

                    def get_positions(self, symbol=None):
                        if symbol:
                            return [p for p in live_exchange_pos if p["symbol"] == symbol]
                        return list(live_exchange_pos)

                    def get_market_price(self, symbol):
                        return 100.0

                    def execute_full_trade(self, signal, config=None):
                        self.exec_calls.append((signal["binance_pair"], signal["direction"]))
                        live_exchange_pos.append({
                            "symbol": signal["binance_pair"],
                            "direction": signal["direction"],
                            "position_amount": 1.0,
                        })
                        return {
                            "status": "EXECUTED", "binance_synced": True, "order_id": len(self.exec_calls),
                            "entry_price": signal["entry_price"], "take_profit": signal["take_profit"],
                            "stop_loss": signal["stop_loss"], "quantity": 1.0, "sl_state": "CONFIRMED", "leverage": 20,
                        }

                bn = MockLiveCapBN()
                sig_eth_long = {
                    "symbol": "ETH-USD", "binance_pair": "ETHUSDT", "direction": "LONG",
                    "entry_price": 100.0, "stop_loss": 98.5, "take_profit": 103.0, "confidence_score": 84,
                }
                sig_sol_short = {
                    "symbol": "SOL-USD", "binance_pair": "SOLUSDT", "direction": "SHORT",
                    "entry_price": 100.0, "stop_loss": 101.5, "take_profit": 97.0, "confidence_score": 84,
                }

                # 1. Local POSITIONS_FILE is empty, but exchange has 1 LONG BTCUSDT -> max_concurrent=1 blocks!
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg(max_concurrent_positions=1)), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}):
                    self.assertIsNone(at.record_position(sig_eth_long))
                self.assertEqual(bn.exec_calls, [])

                # 2. max_concurrent=3 (default max_same_direction=1 on live exchange):
                #    2nd LONG blocked by directional cap; 1st SHORT allowed!
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg(max_concurrent_positions=3)), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch("journal.open_trade", return_value=None):
                    self.assertIsNone(at.record_position(sig_eth_long))
                    p_short = at.record_position(sig_sol_short)
                self.assertIsNotNone(p_short)
                self.assertEqual(bn.exec_calls, [("SOLUSDT", "SHORT")])

                # 3. Scan loop stops at max_concurrent_positions and skips same-direction candidates
                live_exchange_pos.clear()
                bn.exec_calls.clear()
                state_io.atomic_write_json(at.POSITIONS_FILE, [], make_bak=False)
                at.save_state()

                ranked_fake = [
                    {"symbol": "ETH-USD", "pair": "ETHUSDT", "name": "ETH", "price_change_24h_pct": 3.0, "volume_24h_usd": 200e6, "opportunity_score": 8.0},
                    {"symbol": "XRP-USD", "pair": "XRPUSDT", "name": "XRP", "price_change_24h_pct": 3.0, "volume_24h_usd": 200e6, "opportunity_score": 7.5},
                    {"symbol": "SOL-USD", "pair": "SOLUSDT", "name": "SOL", "price_change_24h_pct": 3.0, "volume_24h_usd": 200e6, "opportunity_score": 7.0},
                    {"symbol": "ADA-USD", "pair": "ADAUSDT", "name": "ADA", "price_change_24h_pct": 3.0, "volume_24h_usd": 200e6, "opportunity_score": 6.5},
                ]

                scanned_syms = []

                def fake_pipe(sym, active_positions=None):
                    scanned_syms.append(sym)
                    d = "SHORT" if sym == "SOL-USD" else "LONG"
                    sl = 101.5 if d == "SHORT" else 98.5
                    tp = 97.0 if d == "SHORT" else 103.0
                    return {
                        "layer2_setup": {"setup_name": "EMA_PULLBACK"},
                        "layer3_plan": {"entry_price": 100.0, "stop_loss": sl, "take_profit": tp, "tp_time_prediction": {"eta_label": "2h"}},
                        "layer5_final_call": {
                            "status": "APPROVED", "direction": d, "confidence_score": 84,
                            "entry_price": 100.0, "stop_loss": sl, "take_profit": tp, "take_profit_2": tp,
                        },
                    }

                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg(max_concurrent_positions=2)), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "rank_universe_by_opportunity", return_value=ranked_fake), \
                     patch.object(at, "detect_market_regime", return_value={"regime": "TRENDING", "trending_pct": 70, "sideways_pct": 20, "avg_abs_change_24h": 3.0}), \
                     patch.object(at, "_technical_pre_filter", return_value=ranked_fake), \
                     patch.object(at, "run_5_layer_pipeline", side_effect=fake_pipe), \
                     patch("market_data.get_market_indicators_fast", return_value={"rsi_14": 50.0, "current_price": 100.0, "ema_20": 99.0, "ema_9": 99.5, "change_4h_pct": 0.5}), \
                     patch.object(at, "send_telegram"), \
                     patch("journal.open_trade", return_value=None):
                    at.run_full_scan_cycle()

                # ETH (LONG) opens #1, XRP (LONG) blocked by directional cap (1 LONG open),
                # SOL (SHORT) opens #2 -> max_concurrent=2 reached -> ADA never scanned/executed!
                self.assertEqual(bn.exec_calls, [("ETHUSDT", "LONG"), ("SOLUSDT", "SHORT")])
                self.assertEqual(scanned_syms, ["ETH-USD", "XRP-USD", "SOL-USD"])
                uni = state_io.read_json_safe(at.UNIVERSE_FILE, default={}, strict_on_corrupt=True)
                self.assertEqual(uni.get("approved_symbols"), ["ETH-USD", "SOL-USD"])
            finally:
                _restore_env(saved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
