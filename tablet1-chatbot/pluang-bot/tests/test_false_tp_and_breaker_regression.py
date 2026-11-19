"""
Regression Tests for Live Bug Report:
  1. False Telegram "TAKE PROFIT / PROFIT LOCK TEREKSEKUSI DI EXCHANGE" on open One-Way SHORT positions
     (caused by `_norm_pos_side()` inspecting unsigned `position_amount` before `direction`).
  2. Instant false `CONSECUTIVE_LOSSES_2` Hard Risk Circuit Breaker triggered by repeated phantom closes
     and duplicate re-imports of still-open One-Way SHORT positions.
  3. Direct single-symbol Binance flat-confirmation guard inside `_finalize_exchange_closed_position()`
     so a still-open position or transient API error NEVER cancels SL/TP, never logs phantom PnL,
     never trips HardRiskEngine, and never sends a fake TP/SL Telegram alert.
  4. Stale cached `state["binance_wallet_balance_usdt"]` must NEVER initialize `daily_start_equity`
     or trip a fake `DAILY_DRAWDOWN` Hard Risk Circuit Breaker when `get_balance()` fails transiently.
  5. `HardRiskEngine.resume_circuit_breaker()` re-anchors `daily_start_equity` on DAILY_DRAWDOWN resume.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

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
        "at_state": dict(at.state),
        "journal_DB_PATH": journal.DB_PATH,
        "rv_DEFAULT": rv.DEFAULT_VAULT_STATE_PATH,
        "hd_ADWIN": hd.DEFAULT_ADWIN_PATH,
        "hd_META": hd.DEFAULT_META_PATH,
        "hd_ENS": hd.DEFAULT_ENSEMBLE_PATH,
        "hd_EP": hd.DEFAULT_EPISODES_PATH,
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
    at._THESIS_MONITOR = None
    at.state["binance_wallet_balance_usdt"] = 36.0
    at.state["binance_available_balance_usdt"] = 2.0
    at.state["binance_unrealized_pnl_usdt"] = 0.0

    journal.DB_PATH = os.path.join(tmp, "journal.db")
    journal.init_db(journal.DB_PATH)

    rv.reset_profit_vault_cache()
    rv.DEFAULT_VAULT_STATE_PATH = os.path.join(tmp, "vault_state.json")
    hd.DEFAULT_ADWIN_PATH = os.path.join(tmp, "adwin.json")
    hd.DEFAULT_META_PATH = os.path.join(tmp, "meta.json")
    hd.DEFAULT_ENSEMBLE_PATH = os.path.join(tmp, "ens.json")
    hd.DEFAULT_EPISODES_PATH = os.path.join(tmp, "episodes.json")
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
    at.state.clear()
    at.state.update(saved["at_state"])
    journal.DB_PATH = saved["journal_DB_PATH"]
    rv.reset_profit_vault_cache()
    rv.DEFAULT_VAULT_STATE_PATH = saved["rv_DEFAULT"]
    hd.DEFAULT_ADWIN_PATH = saved["hd_ADWIN"]
    hd.DEFAULT_META_PATH = saved["hd_META"]
    hd.DEFAULT_ENSEMBLE_PATH = saved["hd_ENS"]
    hd.DEFAULT_EPISODES_PATH = saved["hd_EP"]
    hd.DEFAULT_CALIBRATOR_PATH = saved["hd_CAL"]
    hd.DEFAULT_CONFORMAL_PATH = saved["hd_CONF"]
    ba.DEFAULT_STATE_PATH = saved["ba_DEFAULT"]


def _cfg() -> dict:
    return {
        "fixed_leverage": 20,
        "max_leverage": 20,
        "margin_type": "ISOLATED",
        "sizing_mode": "ALL_IN",
        "all_in_balance_fraction": 0.95,
        "max_sl_pct": 2.25,
        "min_sl_pct": 0.45,
        "breaker_daily_dd_pct": 15.0,
        "breaker_consecutive_losses": 2,
        "circuit_breaker_consecutive_losses": 2,
        "breaker_cooldown_hours": 12,
        "max_concurrent_positions": 1,
        "max_daily_trades": 10,
        "sniper_75_mode": {
            "enabled": True,
            "tp1_lock_trigger_r": 0.55,
            "tp1_partial_close_pct": 0.65,
            "sl_lock_after_tp1_r": 0.38,
            "early_invalidation_max_loss_r": 0.35,
        },
    }


def _short_pos(pos_id="POS_BNB_SHORT_1", pair="BNBUSDT", entry=600.0) -> dict:
    now_ts = time.time() - 90.0
    return {
        "id": pos_id,
        "order_id": "123456",
        "symbol": pair.replace("USDT", "-USD"),
        "binance_pair": pair,
        "direction": "SHORT",
        "entry_price": entry,
        "stop_loss": entry * 1.012,
        "init_stop_loss": entry * 1.012,
        "take_profit": entry * 0.975,
        "take_profit_1": entry * 0.9934,
        "take_profit_2": entry * 0.975,
        "leverage": 20,
        "margin_type": "ISOLATED",
        "position_size_usd": 34.0,
        "position_size_usdt": 34.0,
        "position_size_idr": 561000.0,
        "status": "OPEN",
        "exchange": "BINANCE_FUTURES",
        "binance_synced": True,
        "sl_state": "CONFIRMED",
        "sl_algo_id": 9001,
        "tp_algo_id": 9002,
        "setup_name": "AI_SHORT_SETUP",
        "regime": "TRENDING",
        "opened_at": datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "opened_ts": now_ts,
    }


class TestNormPosSideAndOneWayShortSync(unittest.TestCase):
    def test_norm_pos_side_respects_direction_over_unsigned_position_amount(self):
        """One-Way SHORT from BinanceFuturesClient.get_positions() has position_side='BOTH', direction='SHORT', position_amount=+1.5."""
        import auto_trader as at

        one_way_short = {
            "symbol": "BNBUSDT",
            "position_side": "BOTH",
            "direction": "SHORT",
            "position_amount": 1.5,  # BinanceFuturesClient.get_positions() stores abs(amt)!
        }
        one_way_long = {
            "symbol": "BNBUSDT",
            "position_side": "BOTH",
            "direction": "LONG",
            "position_amount": 1.5,
        }
        hedge_short = {"symbol": "BNBUSDT", "position_side": "SHORT", "direction": "SHORT", "position_amount": 1.5}
        raw_signed_short = {"symbol": "BNBUSDT", "positionSide": "BOTH", "positionAmt": "-1.5"}
        raw_signed_long = {"symbol": "BNBUSDT", "positionSide": "BOTH", "positionAmt": "1.5"}
        local_short = {"symbol": "BNB-USD", "direction": "SHORT"}

        self.assertEqual(at._norm_pos_side(one_way_short), "SHORT")
        self.assertEqual(at._norm_pos_side(one_way_long), "LONG")
        self.assertEqual(at._norm_pos_side(hedge_short), "SHORT")
        self.assertEqual(at._norm_pos_side(raw_signed_short), "SHORT")
        self.assertEqual(at._norm_pos_side(raw_signed_long), "LONG")
        self.assertEqual(at._norm_pos_side(local_short), "SHORT")

    def test_one_way_short_in_profit_does_not_emit_false_tp_or_cancel_orders(self):
        """Guard + monitor on an open One-Way SHORT in profit MUST keep it OPEN, zero fake TP Telegram, zero order cancels."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                pos = _short_pos("POS_SHORT_GREEN", pair="BNBUSDT", entry=600.0)
                state_io.atomic_write_json(at.POSITIONS_FILE, [pos], make_bak=False)

                cancels = []

                class MockShortGreenBN:
                    def get_balance(self):
                        return {"total_wallet_balance": 36.0, "available_balance": 2.0, "cross_unrealized_pnl": 0.0}

                    def get_positions(self, symbol=None):
                        return [{
                            "symbol": "BNBUSDT",
                            "position_side": "BOTH",
                            "direction": "SHORT",
                            "position_amount": 1.13,  # abs(amt) > 0
                            "entry_price": 600.0,
                            "mark_price": 598.5,      # +0.25% favorable (+5% ROE, < TP1)
                            "unrealized_pnl": 1.70,
                            "liquidation_price": 627.6,
                            "leverage": 20,
                            "margin_type": "ISOLATED",
                            "isolated_margin": 34.0,
                        }]

                    def verify_stop_loss_active(self, *a, **kw):
                        return "CONFIRMED"

                    def get_open_algo_orders(self, symbol=None):
                        return True, [{"algoId": 9001, "orderType": "STOP_MARKET", "triggerPrice": "607.2"}]

                    def cancel_all_orders(self, symbol):
                        cancels.append(symbol)
                        return {"standard": {}, "algo": {}}

                    def get_user_trades(self, symbol, limit=100, start_time=None):
                        return []

                    def get_income_history(self, symbol=None, limit=100, start_time=None):
                        return []

                bn = MockShortGreenBN()
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[{"symbol": "BNBUSDT", "lastPrice": "598.5"}]), \
                     patch.object(at, "_fetch_live_micro_state", return_value={"ofi_20": -0.2, "tfi_5m": -0.2, "sigma": 0.35}), \
                     patch("exec.thesis_monitor.IntrabarThesisMonitor.evaluate_position", return_value={"p_survive": 0.80, "should_scratch": False, "consecutive_breaches": 0}), \
                     patch.object(at, "send_telegram") as mock_tg:
                    guard = at.check_wallet_and_position_guard()
                    mon_res = at.monitor_and_update_positions()

                # Position MUST remain OPEN (single copy, never duplicated, never closed!)
                disk_pos = state_io.read_json_safe(at.POSITIONS_FILE, default=[], strict_on_corrupt=True)
                self.assertEqual(len(disk_pos), 1)
                self.assertEqual(disk_pos[0]["id"], "POS_SHORT_GREEN")
                self.assertEqual(disk_pos[0]["status"], "OPEN")
                self.assertEqual(len(guard["open_positions"]), 1)
                self.assertEqual(len(mon_res), 1)
                self.assertEqual(mon_res[0]["status"], "OPEN")

                # NEVER cancel live SL/TP orders and NEVER send fake TP/close Telegram!
                self.assertEqual(cancels, [])
                tg_msgs = [c.args[0] for c in mock_tg.call_args_list if c.args]
                self.assertFalse(any("TELAH DITUTUP" in m or "TAKE PROFIT" in m for m in tg_msgs), f"Unexpected Telegram: {tg_msgs}")

                # Breaker MUST NOT trip!
                brk = at.load_hard_risk_engine(_cfg())
                self.assertFalse(brk.is_circuit_breaker_active())
                self.assertEqual(brk.consecutive_losses, 0)
            finally:
                _restore_env(saved)

    def test_one_way_short_at_breakeven_or_red_never_trips_false_consecutive_loss_breaker(self):
        """Repeated guard+monitor cycles on an open One-Way SHORT in slight drawdown MUST NOT record phantom losses or trip breaker."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                pos = _short_pos("POS_SHORT_RED", pair="BNBUSDT", entry=600.0)
                state_io.atomic_write_json(at.POSITIONS_FILE, [pos], make_bak=False)

                class MockShortRedBN:
                    def get_balance(self):
                        return {"total_wallet_balance": 36.0, "available_balance": 2.0, "cross_unrealized_pnl": 0.0}

                    def get_positions(self, symbol=None):
                        return [{
                            "symbol": "BNBUSDT",
                            "position_side": "BOTH",
                            "direction": "SHORT",
                            "position_amount": 1.13,
                            "entry_price": 600.0,
                            "mark_price": 601.0,  # slightly red (-0.17% -> -0.14R, well above early invalidation)
                            "unrealized_pnl": -1.13,
                            "liquidation_price": 627.6,
                            "leverage": 20,
                            "margin_type": "ISOLATED",
                            "isolated_margin": 34.0,
                        }]

                    def verify_stop_loss_active(self, *a, **kw):
                        return "CONFIRMED"

                    def get_open_algo_orders(self, symbol=None):
                        return True, [{"algoId": 9001, "orderType": "STOP_MARKET", "triggerPrice": "607.2"}]

                    def cancel_all_orders(self, symbol):
                        raise AssertionError("cancel_all_orders MUST NEVER be called while position is still live!")

                    def get_user_trades(self, symbol, limit=100, start_time=None):
                        return []

                    def get_income_history(self, symbol=None, limit=100, start_time=None):
                        return []

                bn = MockShortRedBN()
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[{"symbol": "BNBUSDT", "lastPrice": "601.0"}]), \
                     patch.object(at, "_fetch_live_micro_state", return_value={"ofi_20": 0.0, "tfi_5m": 0.0, "sigma": 0.35}), \
                     patch("exec.thesis_monitor.IntrabarThesisMonitor.evaluate_position", return_value={"p_survive": 0.72, "should_scratch": False, "consecutive_breaches": 0}), \
                     patch.object(at, "send_telegram") as mock_tg:
                    for _ in range(3):
                        guard = at.check_wallet_and_position_guard()
                        at.monitor_and_update_positions()
                        self.assertNotIn("CIRCUIT BREAKER", guard.get("reason", ""))

                brk = at.load_hard_risk_engine(_cfg())
                self.assertFalse(brk.is_circuit_breaker_active())
                self.assertEqual(brk.consecutive_losses, 0)
                self.assertFalse(mock_tg.called)
            finally:
                _restore_env(saved)

    def test_one_way_short_genuine_close_still_finalizes_cleanly(self):
        """When a One-Way SHORT genuinely closes on Binance (get_positions()=[]), canonical close still runs accurately."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                opened_ts = 1700100000.0
                pos = _short_pos("POS_SHORT_REAL_TP", pair="BNBUSDT", entry=600.0)
                pos["opened_ts"] = opened_ts
                state_io.atomic_write_json(at.POSITIONS_FILE, [pos], make_bak=False)

                cancels = []

                class MockShortClosedBN:
                    def get_balance(self):
                        return {"total_wallet_balance": 45.0, "available_balance": 45.0, "cross_unrealized_pnl": 0.0}

                    def get_positions(self, symbol=None):
                        return []

                    def get_user_trades(self, symbol, limit=100, start_time=None):
                        return [
                            {
                                "symbol": "BNBUSDT",
                                "side": "SELL",
                                "price": "600.0",
                                "qty": "1.13",
                                "realizedPnl": "0",
                                "commission": "0.30",
                                "commissionAsset": "USDT",
                                "time": 1700100001000,
                            },
                            {
                                "symbol": "BNBUSDT",
                                "side": "BUY",
                                "price": "591.0",
                                "qty": "1.13",
                                "realizedPnl": "10.17",
                                "commission": "0.30",
                                "commissionAsset": "USDT",
                                "time": 1700100500000,
                            },
                        ]

                    def get_income_history(self, symbol=None, limit=100, start_time=None):
                        return []

                    def cancel_all_orders(self, symbol):
                        cancels.append(symbol)
                        return {"standard": {}, "algo": {}}

                    def get_open_algo_orders(self, symbol=None):
                        return True, []

                with patch.object(at, "get_binance_client", return_value=MockShortClosedBN()), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[]), \
                     patch.object(at, "send_telegram") as mock_tg:
                    guard = at.check_wallet_and_position_guard()

                self.assertEqual(guard["open_positions"], [])
                disk_pos = state_io.read_json_safe(at.POSITIONS_FILE, default=[], strict_on_corrupt=True)
                self.assertEqual(len(disk_pos), 1)
                self.assertEqual(disk_pos[0]["status"], "CLOSED_TP")
                self.assertAlmostEqual(disk_pos[0]["pnl_usd"], 9.57, places=2)
                self.assertFalse(disk_pos[0]["pnl_is_estimated"])
                self.assertEqual(cancels, ["BNBUSDT"])
                self.assertTrue(mock_tg.called)
            finally:
                _restore_env(saved)


class TestFinalizeExchangeCloseDirectFlatGuard(unittest.TestCase):
    def test_finalize_aborts_if_direct_symbol_query_shows_position_still_open_or_api_error(self):
        """Defense-in-depth: _finalize_exchange_closed_position MUST re-verify flat via get_positions(pair) before closing."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                pos = _short_pos("POS_GUARD_LIVE", pair="BNBUSDT", entry=600.0)
                state_io.atomic_write_json(at.POSITIONS_FILE, [pos], make_bak=False)

                cancel_calls = []

                class MockStillOpenBN:
                    def get_positions(self, symbol=None):
                        return [{
                            "symbol": "BNBUSDT",
                            "position_side": "BOTH",
                            "direction": "SHORT",
                            "position_amount": 1.13,
                            "entry_price": 600.0,
                            "mark_price": 595.0,
                            "unrealized_pnl": 5.65,
                        }]

                    def cancel_all_orders(self, symbol):
                        cancel_calls.append(symbol)
                        return {}

                with patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "send_telegram") as mock_tg:
                    out = at._finalize_exchange_closed_position(
                        pos, bn_client=MockStillOpenBN(), ticker_map={"BNBUSDT": 595.0}, fx_rate=16500
                    )

                self.assertIsNone(out)
                self.assertEqual(pos["status"], "OPEN")
                self.assertEqual(cancel_calls, [])
                self.assertFalse(mock_tg.called)

                # Also abort when get_positions(pair) returns an API error dict!
                class MockApiErrBN:
                    def get_positions(self, symbol=None):
                        return {"isError": True, "error": "temporary timeout"}

                    def cancel_all_orders(self, symbol):
                        cancel_calls.append(symbol)
                        return {}

                with patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "send_telegram") as mock_tg2:
                    out2 = at._finalize_exchange_closed_position(
                        pos, bn_client=MockApiErrBN(), ticker_map={"BNBUSDT": 595.0}, fx_rate=16500
                    )

                self.assertIsNone(out2)
                self.assertEqual(pos["status"], "OPEN")
                self.assertEqual(cancel_calls, [])
                self.assertFalse(mock_tg2.called)
            finally:
                _restore_env(saved)


class TestStaleBalanceCacheDailyDDGuard(unittest.TestCase):
    def test_transient_balance_api_error_does_not_seed_stale_daily_start_equity_or_trip_fake_dd(self):
        """If get_balance() fails on tick 1 with stale state=$50.89 and succeeds on tick 2 with real $36, NO fake DD breaker."""
        import auto_trader as at

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                # Stale cached wallet balance from days earlier (e.g. $50.89)
                at.state["binance_wallet_balance_usdt"] = 50.89
                at.state["binance_available_balance_usdt"] = 50.89
                at.state["binance_unrealized_pnl_usdt"] = 0.0

                bal_mode = {"ok": False}

                class MockFlakyBalBN:
                    def get_balance(self):
                        if not bal_mode["ok"]:
                            return {"isError": True, "error": "transient network error"}
                        return {"total_wallet_balance": 36.0, "available_balance": 36.0, "cross_unrealized_pnl": 0.0}

                    def get_positions(self, symbol=None):
                        return []

                with patch.object(at, "get_binance_client", return_value=MockFlakyBalBN()), \
                     patch.object(at, "_get_config", return_value=_cfg()), \
                     patch.object(at, "send_telegram") as mock_tg:
                    # Tick 1: get_balance() fails -> MUST NOT persist stale $50.89 as daily_start_equity!
                    g1 = at.check_wallet_and_position_guard()
                    self.assertFalse(g1["pause_scanning"])

                    # Tick 2: get_balance() succeeds with real $36.0 -> sets daily_start_equity=36.0, 0% DD, NO breaker!
                    bal_mode["ok"] = True
                    g2 = at.check_wallet_and_position_guard()
                    self.assertFalse(g2["pause_scanning"])
                    self.assertNotIn("DAILY_DRAWDOWN", g2.get("reason", ""))
                    self.assertFalse(mock_tg.called)

                brk = at.load_hard_risk_engine(_cfg())
                self.assertFalse(brk.is_circuit_breaker_active())
                self.assertAlmostEqual(brk.daily_start_equity, 36.0, places=2)
            finally:
                _restore_env(saved)

    def test_resume_circuit_breaker_reanchors_daily_start_equity_on_dd_reason(self):
        """Resuming a DAILY_DRAWDOWN breaker re-anchors daily_start_equity so next tick doesn't re-trip immediately."""
        from risk.engine import HardRiskEngine

        eng = HardRiskEngine(config=_cfg())
        eng.daily_start_equity = 100.0
        dd = eng.check_live_equity_drawdown(live_equity=80.0, now_ts=1000.0)
        self.assertTrue(dd["breaker_active"])
        self.assertIn("DAILY_DRAWDOWN", str(eng.breaker_reason))

        eng.resume_circuit_breaker()
        self.assertFalse(eng.is_circuit_breaker_active(now_ts=1001.0))
        self.assertAlmostEqual(eng.daily_start_equity, 80.0, places=4)
        dd_after = eng.check_live_equity_drawdown(live_equity=80.0, now_ts=1002.0)
        self.assertFalse(dd_after["breaker_active"])


class TestEntryStarvationFixes(unittest.TestCase):
    def test_options_gamma_veto_only_hard_rejects_under_actual_panic_not_neutral_skew(self):
        """Neutral options regime (DVOL=44, skew=-6.1%, vol_expansion_alert=False) MUST NOT blanket-ban all LONGs."""
        import pipeline as pl

        plan = {
            "entry_price": 100.0,
            "stop_loss": 98.8,
            "take_profit": 102.6,
            "take_profit_1": 100.66,
            "take_profit_2": 102.6,
            "risk_reward_ratio": "1:2.2",
        }
        risk_ok = {"checks_passed": 8, "total_checks": 10}

        # Case 1: Calm/NEUTRAL dealer gamma with structural -6.1% put skew -> LONG stays APPROVED
        mkt_neutral = {
            "ema_trend": "BULLISH",
            "atr_pct": 1.0,
            "math_proof": {"p_math_pct": 78.0, "obi_weighted_20": 0.25},
            "_micro_risk": {
                "hawkes": {"block_long": False, "block_short": False},
                "options": {
                    "dealer_gamma_regime": "NEUTRAL",
                    "dvol": 44.45,
                    "skew_25d": -6.1,
                    "vol_expansion_alert": False,
                    "veto_aggressive_long": True,
                    "veto_aggressive_short": False,
                },
                "vpin": {"veto_maker_long": False, "veto_maker_short": False},
                "hmm": {"p_transition_to_cascade": 0.15},
            },
        }
        setup_ok = {"setup_name": "EMA_PULLBACK_ENTRY", "direction": "LONG", "probability_pct": 82, "confluence_count": 3}
        scan_ok = {"ema_trend": "BULLISH", "rsi_14": 55.0, "atr_pct": 1.0}
        res_ok = pl._apply_safety_gates(
            {"status": "APPROVED", "direction": "LONG", "confidence_score": 82, "final_reason": ""},
            setup_ok,
            plan,
            risk_ok,
            scan_ok,
            mkt_neutral,
        )
        self.assertEqual(res_ok["status"], "APPROVED", f"Neutral put skew should not veto LONG: {res_ok}")

        # Case 2: Actual NEGATIVE_GAMMA_TREND_ACCELERATION panic -> LONG IS rejected
        mkt_panic = dict(mkt_neutral)
        mkt_panic["_micro_risk"] = {
            **mkt_neutral["_micro_risk"],
            "options": {
                "dealer_gamma_regime": "NEGATIVE_GAMMA_TREND_ACCELERATION",
                "dvol": 68.0,
                "skew_25d": -9.5,
                "vol_expansion_alert": True,
                "veto_aggressive_long": True,
                "veto_aggressive_short": False,
            },
        }
        res_rej = pl._apply_safety_gates(
            {"status": "APPROVED", "direction": "LONG", "confidence_score": 82, "final_reason": ""},
            setup_ok,
            plan,
            risk_ok,
            scan_ok,
            mkt_panic,
        )
        self.assertEqual(res_rej["status"], "REJECTED")
        self.assertIn("Options Dealer Gamma Veto LONG", res_rej.get("final_reason", ""))

    def test_pre_filter_penalizes_extreme_whipsaw_and_rotates_recent_rejects(self):
        """Pre-filter prefers clean 20x-tradable ranges (hl 3-18%) over 39% whipsaw traps and rotates rejected coins."""
        import auto_trader as at

        old_rej = dict(at._RECENT_REJECT_TS)
        try:
            at._RECENT_REJECT_TS.clear()
            coins = [
                {"pair": "WHIPSAWUSDT", "symbol": "WHIPSAW-USD", "price_change_24h_pct": 3.2, "volume_24h_usd": 80_000_000, "opportunity_score": 6.0, "high_low_range_pct": 39.5},
                {"pair": "CLEAN1USDT", "symbol": "CLEAN1-USD", "price_change_24h_pct": 3.8, "volume_24h_usd": 80_000_000, "opportunity_score": 5.2, "high_low_range_pct": 9.5},
                {"pair": "CLEAN2USDT", "symbol": "CLEAN2-USD", "price_change_24h_pct": 3.5, "volume_24h_usd": 75_000_000, "opportunity_score": 5.0, "high_low_range_pct": 8.0},
            ]
            picks1 = at._technical_pre_filter(coins, max_ai_coins=2, available_balance_usdt=36.0)
            self.assertEqual([c["pair"] for c in picks1], ["CLEAN1USDT", "CLEAN2USDT"])

            # After CLEAN1USDT was rejected recently, CLEAN2USDT rotates to #1
            at._RECENT_REJECT_TS["CLEAN1USDT"] = time.time()
            picks2 = at._technical_pre_filter(coins, max_ai_coins=2, available_balance_usdt=36.0)
            self.assertEqual(picks2[0]["pair"], "CLEAN2USDT")
        finally:
            at._RECENT_REJECT_TS.clear()
            at._RECENT_REJECT_TS.update(old_rej)

    def test_hard_risk_accepts_conformal_win_with_propagated_p_tp1(self):
        """Signal with cal_p=0.745 (Conformal WIN) and First-Passage blended p_tp1=0.78 passes HardRiskEngine."""
        from risk.engine import HardRiskEngine

        eng = HardRiskEngine(config=_cfg())
        res = eng.validate_and_size(
            decision={
                "decision": "TRADE",
                "symbol": "ZROUSDT",
                "direction": "LONG",
                "entry_price": 2.0,
                "sl_price": 1.976,
                "tp_price": 2.055,
                "p_cal": 0.745,
                "p_hybrid": 0.745,
                "p_tp1": 0.78,
                "conformal_set": ["WIN"],
            },
            account_state={"available_balance_usdt": 36.0, "live_equity": 36.0, "consecutive_losses": 0, "open_positions_count": 0},
            market_state={"min_notional": 5.0, "step_size": 0.1, "min_qty": 0.1, "quantity_precision": 1},
        )
        self.assertTrue(res["allowed"], f"Expected allowed with p_tp1=0.78: {res}")


if __name__ == "__main__":
    unittest.main()
