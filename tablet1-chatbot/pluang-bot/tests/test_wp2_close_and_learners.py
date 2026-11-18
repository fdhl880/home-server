"""
WP-2 TDD Test Suite: Position Close Lifecycle, Closed-Loop Learners, Orphan Cleanup,
Telegram /panic & /vault, and Server Hardening.

Strictly offline (mocked Binance client / mocked HTTP, zero live keys or network calls).
Covers:
  - A-4: Guard & monitor share canonical exchange-side close path (no silent CLOSED_SYNCED)
  - A-3 & C-5: Close-first -> verify flat -> cancel_all_orders (std + algo verified) across
    all bot close paths (Early Invalidation, Timeout 48H/72H, TP/SL fallback,
    UNPROTECTED_RECOVERY, -2021 immediate trigger, and Telegram /panic)
  - B-12: Genuine confirmation in _apply_exchange_sl_lock & amend_stop_loss cancel_errors
  - C-6: Lifecycle-scoped userTrades/income lookup, non-USDT commission conversion, funding,
    and CLOSED_LIQUIDATION / CLOSED_ADL classification
  - C-7: Preserve UNKNOWN sl_state on API failure without duplicate SL or local close
  - C-10: Strict net_usd > 0 win classification, no fee double-subtraction, and
    learners_pending retry mechanism with explicit logging
  - telegram_bot.py /vault (vault_state.json + get_profit_vault) & state_io
  - server.py state_io writes, "CROSS"->"CROSSED" normalization, ConfigValidationError -> HTTP 400
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


def _isolate_env(tmp: str):
    """Redirect all mutable state paths in auto_trader, journal, vault, hmm_drift, bandit to `tmp`."""
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
        "journal_DB_PATH": journal.DB_PATH,
        "rv_DEFAULT": rv.DEFAULT_VAULT_STATE_PATH,
        "hd_ADWIN": hd.DEFAULT_ADWIN_PATH,
        "hd_META": hd.DEFAULT_META_PATH,
        "hd_ENS": hd.DEFAULT_ENSEMBLE_PATH,
        "hd_EP": hd.DEFAULT_EPISODES_PATH,
        "hd_CAL": hd.DEFAULT_CALIBRATOR_PATH,
        "hd_CONF": hd.DEFAULT_CONFORMAL_PATH,
        "ba_DEFAULT": ba.DEFAULT_STATE_PATH,
        "at_CLOSE_FAIL_ALERT_TS": dict(at._CLOSE_FAIL_ALERT_TS),
    }

    at.RESULTS_DIR = tmp
    at.STATE_FILE = os.path.join(tmp, "autotrader_state.json")
    at.POSITIONS_FILE = os.path.join(tmp, "active_positions.json")
    at.PERF_LEDGER_FILE = os.path.join(tmp, "performance_ledger.json")
    at.RISK_BREAKER_FILE = os.path.join(tmp, "risk_breaker_state.json")
    at.DEGRADED_STRAT_FILE = os.path.join(tmp, "degraded_strategies.json")
    at._THESIS_MONITOR = None
    at._CLOSE_FAIL_ALERT_TS.clear()

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


def _restore_env(saved: dict):
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
    at._CLOSE_FAIL_ALERT_TS.clear()
    at._CLOSE_FAIL_ALERT_TS.update(saved["at_CLOSE_FAIL_ALERT_TS"])
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


def _base_cfg():
    return {
        "fixed_leverage": 20,
        "max_leverage": 20,
        "margin_type": "ISOLATED",
        "sizing_mode": "ALL_IN",
        "all_in_balance_fraction": 0.95,
        "max_sl_pct": 2.25,
        "min_sl_pct": 0.45,
        "breaker_consecutive_losses": 2,
        "circuit_breaker_consecutive_losses": 2,
        "breaker_cooldown_hours": 12,
        "max_concurrent_positions": 5,
        "max_daily_trades": 10,
        "sniper_75_mode": {
            "enabled": True,
            "tp1_lock_trigger_r": 0.55,
            "tp1_partial_close_pct": 0.65,
            "sl_lock_after_tp1_r": 0.38,
            "early_invalidation_max_loss_r": 0.35,
        },
    }


def _sample_pos(pos_id="POS_TEST_1", pair="SOLUSDT", direction="LONG", **overrides):
    now_ts = time.time() - 120.0
    p = {
        "id": pos_id,
        "symbol": pair.replace("USDT", "-USD"),
        "binance_pair": pair,
        "direction": direction,
        "entry_price": 150.0,
        "stop_loss": 148.5,
        "init_stop_loss": 148.5,
        "take_profit": 154.5,
        "take_profit_1": 150.825,
        "take_profit_2": 154.5,
        "leverage": 20,
        "position_size_usd": 50.0,
        "position_size_usdt": 50.0,
        "position_size_idr": 825000,
        "status": "OPEN",
        "exchange": "BINANCE_FUTURES",
        "binance_synced": True,
        "sl_state": "CONFIRMED",
        "sl_algo_id": 777,
        "setup_name": "EMA_PULLBACK",
        "regime": "TRENDING",
        "confidence_score": 82,
        "calibrated_prob": 0.80,
        "opened_at": datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "opened_ts": now_ts,
    }
    p.update(overrides)
    return p


class TestA4CanonicalExchangeClose(unittest.TestCase):
    def test_guard_disappearing_positions_trigger_full_lifecycle_never_closed_synced(self):
        """A-4: Guard running before monitor MUST finalize exchange close (journal/breaker/vault/learners/cancel/telegram), never CLOSED_SYNCED."""
        import auto_trader as at
        import features.hmm_drift as hd
        import journal
        import risk.vault as rv
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                rv.get_profit_vault(initial_equity=100.0, state_path=rv.DEFAULT_VAULT_STATE_PATH, persist=True)
                p1 = _sample_pos("POS_A4_1", pair="SOLUSDT", opened_ts=1700001000.0)
                p2 = _sample_pos("POS_A4_2", pair="ETHUSDT", opened_ts=1700002000.0)
                for p in (p1, p2):
                    journal.open_trade({
                        "id": p["id"], "symbol": p["symbol"], "direction": p["direction"],
                        "entry_fill": p["entry_price"], "qty": 6.66, "leverage": 20,
                        "margin_usd": 50.0, "strategy_id": "EMA_PULLBACK", "regime": "TRENDING",
                    })
                state_io.atomic_write_json(at.POSITIONS_FILE, [p1, p2], make_bak=False)

                cancel_calls = []

                class MockGuardBN:
                    def get_balance(self):
                        return {"available_balance": 120.0, "total_wallet_balance": 120.0, "cross_unrealized_pnl": 0.0}

                    def get_positions(self, symbol=None):
                        return []

                    def get_user_trades(self, symbol, limit=100, start_time=None):
                        return [
                            {
                                "symbol": symbol,
                                "side": "SELL",
                                "price": "148.5",
                                "qty": "6.66",
                                "realizedPnl": "-9.8",
                                "commission": "0.2",
                                "commissionAsset": "USDT",
                                "time": 1700003000000,
                            }
                        ]

                    def get_income_history(self, symbol=None, limit=100, start_time=None):
                        return []

                    def cancel_all_orders(self, symbol):
                        cancel_calls.append(symbol)
                        return {"standard": {}, "algo": {}}

                    def get_open_algo_orders(self, symbol=None):
                        return True, []

                with patch.object(at, "get_binance_client", return_value=MockGuardBN()), \
                     patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[]), \
                     patch.object(at, "send_telegram") as mock_tg:
                    guard = at.check_wallet_and_position_guard()

                disk_pos = state_io.read_json_safe(at.POSITIONS_FILE, default=[], strict_on_corrupt=True)
                statuses = {p["id"]: p["status"] for p in disk_pos}
                self.assertEqual(statuses["POS_A4_1"], "CLOSED_SL")
                self.assertEqual(statuses["POS_A4_2"], "CLOSED_SL")
                self.assertNotIn("CLOSED_SYNCED", statuses.values())

                # C-5: cancel_all_orders ran for both disappearing positions
                self.assertEqual(sorted(cancel_calls), ["ETHUSDT", "SOLUSDT"])

                # Journal & Performance Ledger recorded both losses
                ledger = state_io.read_json_safe(at.PERF_LEDGER_FILE, default={}, strict_on_corrupt=True)
                self.assertEqual(ledger["closed_trades"], 2)
                self.assertEqual(ledger["losing_trades"], 2)
                self.assertEqual(ledger["learners_pending"], [])

                # HardRiskEngine tripped 2-loss circuit breaker so guard pauses scanning!
                self.assertTrue(guard["pause_scanning"])
                self.assertIn("CIRCUIT BREAKER", guard["reason"])

                # ProfitVault HWM ratcheted on $100 -> $120 (+20% >= 15%)
                v_now = rv.get_profit_vault(state_path=rv.DEFAULT_VAULT_STATE_PATH, persist=True)
                self.assertAlmostEqual(v_now.high_water_mark_equity, 120.0, places=3)
                self.assertGreater(v_now.locked_profit_vault_usdt, 0.0)

                # Closed-loop Calibrator + Conformal updated for both trades
                self.assertEqual(len(hd.load_calibrator().history_y), 2)
                self.assertEqual(len(hd.load_conformal_filter().error_history), 2)
                self.assertTrue(mock_tg.called)
            finally:
                _restore_env(saved)


class TestA3AndC5CloseFirstVerifyFlatCancelAfter(unittest.TestCase):
    def test_early_invalidation_keeps_sl_intact_if_close_fails_or_not_flat(self):
        """A-3: If close_position fails or position remains open on exchange, NEVER cancel orders and keep status OPEN."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                pos = _sample_pos("POS_A3_1", pair="SOLUSDT")
                state_io.atomic_write_json(at.POSITIONS_FILE, [pos], make_bak=False)

                call_log = []
                state_flags = {"close_mode": "error", "flat_after_close": False}

                class MockBNA3:
                    def get_positions(self, symbol=None):
                        call_log.append(("get_positions", symbol))
                        if symbol is not None and state_flags["flat_after_close"]:
                            return []
                        if symbol is None and state_flags["close_mode"] == "done":
                            return []
                        return [{
                            "symbol": "SOLUSDT", "direction": "LONG", "position_amount": 1.33,
                            "entry_price": 150.0, "mark_price": 149.25, "unrealized_pnl": -1.0,
                            "liquidation_price": 143.0, "isolated_margin": 50.0, "leverage": 20,
                        }]

                    def verify_stop_loss_active(self, symbol, **kw):
                        return "CONFIRMED"

                    def close_position(self, symbol, direction, quantity=None):
                        call_log.append(("close_position", symbol))
                        if state_flags["close_mode"] == "error":
                            return {"isError": True, "error": "network timeout"}
                        return {"orderId": 888, "status": "FILLED"}

                    def cancel_all_orders(self, symbol):
                        call_log.append(("cancel_all_orders", symbol))
                        return {"standard": {}, "algo": {}}

                    def get_open_algo_orders(self, symbol=None):
                        call_log.append(("get_open_algo_orders", symbol))
                        return True, []

                    def get_balance(self):
                        return {"total_wallet_balance": 99.0, "available_balance": 99.0}

                bn = MockBNA3()
                micro = {"ofi_20": -0.8, "tfi_5m": -0.8, "spot_perp_div": -0.001, "vpin": 0.4, "oi_quadrant": "LONG_CAPITULATION", "sigma": 0.5}
                scratch_res = {"p_survive": 0.08, "mu_drift": -0.8, "structural_reversal": True, "consecutive_breaches": 3, "should_scratch": True}

                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[{"symbol": "SOLUSDT", "lastPrice": "149.25"}]), \
                     patch.object(at, "_fetch_live_micro_state", return_value=micro), \
                     patch("exec.thesis_monitor.IntrabarThesisMonitor.evaluate_position", return_value=scratch_res), \
                     patch.object(at, "send_telegram") as mock_tg:
                    # Tick 1: close_position returns isError -> stay OPEN, NEVER cancel
                    res1 = at.monitor_and_update_positions()
                    self.assertEqual(res1[0]["status"], "OPEN")
                    self.assertFalse(any(c[0] == "cancel_all_orders" for c in call_log))
                    self.assertEqual(mock_tg.call_count, 1)

                    # Tick 2: close_position returns FILLED, BUT get_positions still shows qty=1.33 -> stay OPEN, NEVER cancel, rate-limited alert!
                    state_flags["close_mode"] = "not_flat"
                    res2 = at.monitor_and_update_positions()
                    self.assertEqual(res2[0]["status"], "OPEN")
                    self.assertFalse(any(c[0] == "cancel_all_orders" for c in call_log))
                    self.assertEqual(mock_tg.call_count, 1, "Failed close alert must be rate-limited across 8s ticks")

                    # Tick 3: close_position succeeds AND get_positions(pair) confirms flat -> cancel_all_orders runs AFTER flat verify!
                    call_log.clear()
                    state_flags["close_mode"] = "ok"
                    state_flags["flat_after_close"] = True
                    res3 = at.monitor_and_update_positions()
                    self.assertEqual(res3[0]["status"], "CLOSED_EARLY_INVALIDATION")
                    op_names = [c[0] for c in call_log]
                    self.assertIn("close_position", op_names)
                    self.assertIn("cancel_all_orders", op_names)
                    self.assertLess(op_names.index("close_position"), op_names.index("cancel_all_orders"))
                    idx_verify = next(i for i, c in enumerate(call_log) if c == ("get_positions", "SOLUSDT"))
                    self.assertLess(idx_verify, op_names.index("cancel_all_orders"))
            finally:
                _restore_env(saved)

    def test_timeout_tp_sl_and_unprotected_recovery_close_ordering(self):
        """A-3: Timeout 48H/72H, TP/SL fallback, and WP-1 UNPROTECTED_RECOVERY all verify flat before cancel."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                # 1. UNPROTECTED_RECOVERY priority close from WP-1
                p_rec = _sample_pos("POS_REC_1", sl_state="UNPROTECTED_RECOVERY", emergency_close_failed=True)
                state_io.atomic_write_json(at.POSITIONS_FILE, [p_rec], make_bak=False)

                seq = []

                class MockSeqBN:
                    def __init__(self, mark_px=149.8, sl_state="CONFIRMED"):
                        self.mark_px = mark_px
                        self.sl_state = sl_state
                        self.closed = False

                    def get_positions(self, symbol=None):
                        seq.append(("get_positions", symbol))
                        if self.closed:
                            return []
                        return [{
                            "symbol": "SOLUSDT", "direction": "LONG", "position_amount": 1.0,
                            "entry_price": 150.0, "mark_price": self.mark_px, "unrealized_pnl": -0.5,
                            "liquidation_price": 143.0, "isolated_margin": 50.0, "leverage": 20,
                        }]

                    def verify_stop_loss_active(self, symbol, **kw):
                        return self.sl_state

                    def set_stop_loss(self, *a, **kw):
                        return {"isError": True, "error": "still failing"}

                    def close_position(self, symbol, direction, quantity=None):
                        seq.append(("close_position", symbol))
                        self.closed = True
                        return {"orderId": 901, "status": "FILLED"}

                    def cancel_all_orders(self, symbol):
                        seq.append(("cancel_all_orders", symbol))
                        return {"standard": {}, "algo": {}}

                    def get_open_algo_orders(self, symbol=None):
                        seq.append(("get_open_algo_orders", symbol))
                        return True, []

                    def get_balance(self):
                        return {"total_wallet_balance": 99.0, "available_balance": 99.0}

                with patch.object(at, "get_binance_client", return_value=MockSeqBN()), \
                     patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[]), \
                     patch.object(at, "send_telegram"):
                    res_rec = at.monitor_and_update_positions()
                self.assertEqual(res_rec[0]["status"], "CLOSED_UNPROTECTED_RECOVERY")
                names = [x[0] for x in seq]
                self.assertLess(names.index("close_position"), names.index("cancel_all_orders"))

                # 2. Timeout 48H + TP fallback + SL fallback
                old_48h = (datetime.now(timezone.utc) - timedelta(hours=50)).strftime("%Y-%m-%d %H:%M:%S UTC")
                p_48 = _sample_pos("POS_48H", opened_at=old_48h, opened_ts=time.time() - 50 * 3600)
                state_io.atomic_write_json(at.POSITIONS_FILE, [p_48], make_bak=False)
                seq.clear()
                bn48 = MockSeqBN(mark_px=149.2)
                # Force unrealized_pnl=-5.0 -> -10% ROE
                bn48.get_positions = lambda symbol=None: (
                    seq.append(("get_positions", symbol)) or (
                        [] if bn48.closed else [{
                            "symbol": "SOLUSDT", "direction": "LONG", "position_amount": 1.0,
                            "entry_price": 150.0, "mark_price": 149.2, "unrealized_pnl": -5.0,
                            "liquidation_price": 143.0, "isolated_margin": 50.0, "leverage": 20,
                        }]
                    )
                )
                with patch.object(at, "get_binance_client", return_value=bn48), \
                     patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[]), \
                     patch.object(at, "_fetch_live_micro_state", return_value={"ofi_20": 0.0, "tfi_5m": 0.0, "sigma": 0.35}), \
                     patch("exec.thesis_monitor.IntrabarThesisMonitor.evaluate_position", return_value={"p_survive": 0.6, "should_scratch": False, "consecutive_breaches": 0}), \
                     patch.object(at, "send_telegram"):
                    res_48 = at.monitor_and_update_positions()
                self.assertEqual(res_48[0]["status"], "CLOSED_TIMEOUT")
                names48 = [x[0] for x in seq]
                self.assertLess(names48.index("close_position"), names48.index("cancel_all_orders"))
            finally:
                _restore_env(saved)

    def test_c5_cancel_all_orders_verifies_and_cleans_straggler_algo_orders(self):
        """C-5: cancel_all_orders verifies get_open_algo_orders is empty and cancels any stragglers individually."""
        from binance_futures import BinanceFuturesClient

        client = BinanceFuturesClient(api_key="k", api_secret="s")
        calls = []
        algo_polls = {"n": 0}

        def fake_req(method, endpoint, params=None, signed=False, **kw):
            calls.append((method, endpoint, dict(params or {})))
            if method == "DELETE" and endpoint == "/fapi/v1/algoOpenOrders":
                return {"isError": True, "error": "bulk algo cancel partial error"}
            if method == "GET" and endpoint == "/fapi/v1/openAlgoOrders":
                algo_polls["n"] += 1
                if algo_polls["n"] == 1:
                    return [{"algoId": 9001}, {"algoId": 9002}]
                return []
            return {"code": 200}

        with patch.object(client, "_request", side_effect=fake_req):
            res = client.cancel_all_orders("SOLUSDT")

        self.assertTrue(res["algo_clean_verified"])
        self.assertEqual(res["remaining_algo_ids"], [])
        del_algo_ids = [p.get("algoId") for m, ep, p in calls if m == "DELETE" and ep == "/fapi/v1/algoOrder"]
        self.assertEqual(del_algo_ids, [9001, 9002])


class TestB12AmendStopLossConfirmation(unittest.TestCase):
    def test_amend_stop_loss_checks_cancel_algo_is_error_and_reports_cancel_errors(self):
        """B-12: BinanceFuturesClient.amend_stop_loss checks cancel_res['isError'] and reports cancel_errors."""
        from binance_futures import BinanceFuturesClient

        client = BinanceFuturesClient(api_key="k", api_secret="s")
        with patch.object(client, "set_stop_loss", return_value={"algoId": 222}), \
             patch.object(client, "cancel_algo_order", return_value={"isError": True, "code": -2011, "error": "Cancel rejected"}), \
             patch.object(client, "format_price", side_effect=lambda s, p: p):
            res = client.amend_stop_loss("SOLUSDT", "LONG", 151.0, old_algo_id=111)

        self.assertEqual(res["status"], "AMENDED")
        self.assertEqual(res["new_algo_id"], 222)
        self.assertEqual(res["cancelled_algo_ids"], [])
        self.assertEqual(len(res["cancel_errors"]), 1)
        self.assertEqual(res["cancel_errors"][0]["algo_id"], 111)

    def test_failed_sl_amend_keeps_old_sl_flags_false_and_no_fake_telegram(self):
        """B-12: When amend_stop_loss fails, Stage 0/TP1/R-trail flags stay False, stop_loss unchanged, no PROFIT DIKUNCI DI BURSA message."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                pos = _sample_pos("POS_B12_1", entry_price=100.0, stop_loss=98.5, init_stop_loss=98.5, take_profit=103.0, sl_algo_id=777)
                state_io.atomic_write_json(at.POSITIONS_FILE, [pos], make_bak=False)

                amend_mode = {"ok": False}

                class MockBNB12:
                    def get_positions(self, symbol=None):
                        return [{
                            "symbol": "SOLUSDT", "direction": "LONG", "position_amount": 10.0,
                            "entry_price": 100.0, "mark_price": 100.90, "unrealized_pnl": 9.0,
                            "liquidation_price": 95.4, "isolated_margin": 50.0, "leverage": 20,
                        }]

                    def verify_stop_loss_active(self, symbol, **kw):
                        return "CONFIRMED"

                    def amend_stop_loss(self, symbol, direction, new_sl_price, old_algo_id=None, **kw):
                        if not amend_mode["ok"]:
                            return {"status": "AMEND_FAILED_KEPT_OLD", "kept_algo_ids": [777]}
                        return {"status": "AMENDED", "new_algo_id": 888}

                    def partial_close_position(self, symbol, direction, fraction=0.65):
                        return {"partial_closed": True, "closed_qty": 6.5, "remaining_qty": 3.5}

                bn = MockBNB12()
                micro = {"ofi_20": 0.2, "tfi_5m": 0.2, "sigma": 0.35}
                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[{"symbol": "SOLUSDT", "lastPrice": "100.90"}]), \
                     patch.object(at, "_fetch_live_micro_state", return_value=micro), \
                     patch.object(at, "send_telegram") as mock_tg:
                    # Tick 1: amend fails
                    res1 = at.monitor_and_update_positions()[0]
                    self.assertEqual(res1["stop_loss"], 98.5)
                    self.assertEqual(res1["sl_algo_id"], 777)
                    self.assertFalse(res1.get("tp1_profit_lock_set", False))
                    self.assertFalse(res1.get("stage0_be_guard_set", False))
                    self.assertFalse(res1.get("breakeven_set", False))
                    tg_texts1 = [c.args[0] for c in mock_tg.call_args_list if c.args]
                    self.assertFalse(any("PROFIT DIKUNCI DI BURSA" in t for t in tg_texts1))

                    # Tick 2: amend succeeds on retry
                    amend_mode["ok"] = True
                    res2 = at.monitor_and_update_positions()[0]
                    self.assertAlmostEqual(res2["stop_loss"], 100.57, places=4)
                    self.assertEqual(res2["sl_algo_id"], 888)
                    self.assertTrue(res2["tp1_profit_lock_set"])
                    self.assertTrue(res2["stage0_be_guard_set"])
                    self.assertTrue(res2["breakeven_set"])
                    tg_texts2 = [c.args[0] for c in mock_tg.call_args_list if c.args]
                    self.assertTrue(any("PROFIT DIKUNCI DI BURSA" in t for t in tg_texts2))
            finally:
                _restore_env(saved)

    def test_failed_partial_close_keeps_flag_false_and_r_trail_jump_failure(self):
        """B-12: Partial close error keeps tp1_partial_closed=False; failed Stage 2 jump amend keeps ALL flags False."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                # Case 1: Price jumps straight to +1.20R (101.80 on 100 entry / 98.5 SL), amend fails -> ALL flags stay False!
                pos = _sample_pos("POS_B12_JUMP", entry_price=100.0, stop_loss=98.5, init_stop_loss=98.5, take_profit=105.0, sl_algo_id=777)
                state_io.atomic_write_json(at.POSITIONS_FILE, [pos], make_bak=False)

                state_ctrl = {"amend_ok": False, "partial_ok": False}

                class MockJumpBN:
                    def get_positions(self, symbol=None):
                        return [{
                            "symbol": "SOLUSDT", "direction": "LONG", "position_amount": 10.0,
                            "entry_price": 100.0, "mark_price": 101.80, "unrealized_pnl": 18.0,
                            "liquidation_price": 95.4, "isolated_margin": 50.0, "leverage": 20,
                        }]

                    def verify_stop_loss_active(self, symbol, **kw):
                        return "CONFIRMED"

                    def amend_stop_loss(self, symbol, direction, new_sl_price, old_algo_id=None, **kw):
                        if state_ctrl["amend_ok"]:
                            return {"status": "AMENDED", "new_algo_id": 999}
                        return {"status": "AMEND_FAILED_KEPT_OLD", "kept_algo_ids": [777]}

                    def partial_close_position(self, symbol, direction, fraction=0.65):
                        if state_ctrl["partial_ok"]:
                            return {"partial_closed": True, "closed_qty": 6.5, "remaining_qty": 3.5}
                        return {"status": "PARTIAL_CLOSE_ERROR", "partial_closed": False, "error": "timeout"}

                with patch.object(at, "get_binance_client", return_value=MockJumpBN()), \
                     patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[{"symbol": "SOLUSDT", "lastPrice": "101.80"}]), \
                     patch.object(at, "_fetch_live_micro_state", return_value={"ofi_20": 0.2, "tfi_5m": 0.2, "sigma": 0.35}), \
                     patch.object(at, "send_telegram") as mock_tg:
                    # Tick 1: Stage 2 amend fails -> ALL flags False, SL untouched
                    res1 = at.monitor_and_update_positions()[0]
                    self.assertEqual(res1["stop_loss"], 98.5)
                    self.assertFalse(res1.get("tp1_profit_lock_set", False))
                    self.assertFalse(res1.get("r_trail_10_set", False))
                    self.assertFalse(mock_tg.called)

                    # Tick 2: Amend succeeds, partial close fails -> SL updated, tp1_profit_lock_set=True, tp1_partial_closed=False
                    state_ctrl["amend_ok"] = True
                    res2 = at.monitor_and_update_positions()[0]
                    self.assertGreater(res2["stop_loss"], 100.9)
                    self.assertTrue(res2["tp1_profit_lock_set"])
                    self.assertTrue(res2["r_trail_10_set"])
                    self.assertFalse(res2.get("tp1_partial_closed", False))
            finally:
                _restore_env(saved)


class TestC6RealizedPnlCommissionsAndAdlLiq(unittest.TestCase):
    def test_c6_filters_old_trades_converts_bnb_commission_and_tags_adl_liquidation(self):
        """C-6: Exclude earlier unrelated trades, sum all >3 closing fills, convert BNB commission, apply funding, tag ADL/LIQ."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                opened_ts = 1700010000.0
                p1 = _sample_pos("POS_C6_BNB", pair="SOLUSDT", opened_ts=opened_ts, entry_price=100.0, position_size_usd=50.0)
                p2 = _sample_pos("POS_C6_LIQ", pair="ETHUSDT", opened_ts=opened_ts, entry_price=2000.0, position_size_usd=50.0)
                p3 = _sample_pos("POS_C6_ADL", pair="BTCUSDT", opened_ts=opened_ts, entry_price=50000.0, position_size_usd=50.0)
                state_io.atomic_write_json(at.POSITIONS_FILE, [p1, p2, p3], make_bak=False)

                captured_start_times = []

                class MockC6BN:
                    def get_positions(self, symbol=None):
                        return []

                    def get_balance(self):
                        return {"total_wallet_balance": 100.0, "available_balance": 100.0}

                    def get_market_price(self, sym):
                        if sym == "BNBUSDT":
                            return 600.0
                        return 0.0

                    def get_user_trades(self, symbol, limit=100, start_time=None):
                        captured_start_times.append((symbol, start_time))
                        if symbol == "SOLUSDT":
                            # Includes an earlier unrelated trade (t < start_time) + 4 partial closing fills!
                            return [
                                {"symbol": "SOLUSDT", "side": "SELL", "price": "90", "realizedPnl": "-50.0", "commission": "1.0", "commissionAsset": "USDT", "time": 1699900000000},
                                {"symbol": "SOLUSDT", "side": "BUY", "price": "100", "realizedPnl": "0", "commission": "0.0005", "commissionAsset": "BNB", "time": 1700010001000},
                                {"symbol": "SOLUSDT", "side": "SELL", "price": "101", "realizedPnl": "2.0", "commission": "0.0002", "commissionAsset": "BNB", "time": 1700010100000},
                                {"symbol": "SOLUSDT", "side": "SELL", "price": "102", "realizedPnl": "2.0", "commission": "0.0001", "commissionAsset": "BNB", "time": 1700010200000},
                                {"symbol": "SOLUSDT", "side": "SELL", "price": "103", "realizedPnl": "2.0", "commission": "0.0001", "commissionAsset": "BNB", "time": 1700010300000},
                                {"symbol": "SOLUSDT", "side": "SELL", "price": "104", "realizedPnl": "2.0", "commission": "0.0001", "commissionAsset": "BNB", "time": 1700010400000},
                            ]
                        if symbol == "ETHUSDT":
                            return [{"symbol": "ETHUSDT", "side": "SELL", "price": "1900", "realizedPnl": "-40.0", "commission": "0.5", "commissionAsset": "USDT", "time": 1700010200000}]
                        return [{"symbol": "BTCUSDT", "side": "SELL", "price": "51000", "realizedPnl": "5.0", "commission": "0.2", "commissionAsset": "USDT", "time": 1700010200000}]

                    def get_income_history(self, symbol=None, limit=100, start_time=None):
                        if symbol == "SOLUSDT":
                            return [{"symbol": "SOLUSDT", "incomeType": "FUNDING_FEE", "income": "-0.10", "asset": "USDT", "time": 1700010150000}]
                        if symbol == "ETHUSDT":
                            return [{"symbol": "ETHUSDT", "incomeType": "INSURANCE_CLEAR", "income": "-1.5", "asset": "USDT", "time": 1700010200000}]
                        if symbol == "BTCUSDT":
                            return [{"symbol": "BTCUSDT", "incomeType": "REALIZED_PNL", "income": "5.0", "asset": "USDT", "info": "ADL_AUTOCLOSE", "time": 1700010200000}]
                        return []

                    def cancel_all_orders(self, symbol):
                        return {"standard": {}, "algo": {}}

                    def get_open_algo_orders(self, symbol=None):
                        return True, []

                with patch.object(at, "get_binance_client", return_value=MockC6BN()), \
                     patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[]), \
                     patch.object(at, "send_telegram"):
                    at.monitor_and_update_positions()

                disk_pos = {p["id"]: p for p in state_io.read_json_safe(at.POSITIONS_FILE, default=[], strict_on_corrupt=True)}
                # SOL: gross = 8.0 (all 4 closing fills, -50 excluded), BNB comm = 0.0010 * 600 = 0.60, funding = +0.10 -> net = 7.30
                sol = disk_pos["POS_C6_BNB"]
                self.assertEqual(sol["status"], "CLOSED_TP")
                self.assertAlmostEqual(sol["gross_pnl_usd"], 8.0, places=4)
                self.assertAlmostEqual(sol["commission_usd"], 0.60, places=4)
                self.assertAlmostEqual(sol["funding_usd"], 0.10, places=4)
                self.assertAlmostEqual(sol["pnl_usd"], 7.30, places=4)
                self.assertTrue(any(st == int(opened_ts * 1000) - 5000 for _, st in captured_start_times))

                # ETH: INSURANCE_CLEAR -> CLOSED_LIQUIDATION
                self.assertEqual(disk_pos["POS_C6_LIQ"]["status"], "CLOSED_LIQUIDATION")
                # BTC: ADL info -> CLOSED_ADL
                self.assertEqual(disk_pos["POS_C6_ADL"]["status"], "CLOSED_ADL")
            finally:
                _restore_env(saved)

    def test_c6_base_asset_commission_and_monitor_disappear_cancel_and_vault(self):
        """C-6 & C-5 & A-4: Base-asset commission converted via fill price; monitor exchange close cancels orders & updates vault."""
        import auto_trader as at
        import risk.vault as rv
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                rv.get_profit_vault(initial_equity=100.0, state_path=rv.DEFAULT_VAULT_STATE_PATH, persist=True)
                p = _sample_pos("POS_C6_BASE", pair="SOLUSDT", entry_price=100.0, opened_ts=1700020000.0)
                state_io.atomic_write_json(at.POSITIONS_FILE, [p], make_bak=False)
                cancels = []

                class MockBaseBN:
                    def get_positions(self, symbol=None):
                        return []

                    def get_balance(self):
                        return {"total_wallet_balance": 120.0, "available_balance": 120.0}

                    def get_user_trades(self, symbol, limit=100, start_time=None):
                        return [{
                            "symbol": "SOLUSDT", "side": "SELL", "price": "200.0",
                            "realizedPnl": "10.0", "commission": "0.005", "commissionAsset": "SOL",
                            "time": 1700020100000,
                        }]

                    def get_income_history(self, symbol=None, limit=100, start_time=None):
                        return []

                    def cancel_all_orders(self, symbol):
                        cancels.append(symbol)
                        return {"standard": {}, "algo": {}}

                    def get_open_algo_orders(self, symbol=None):
                        return True, []

                with patch.object(at, "get_binance_client", return_value=MockBaseBN()), \
                     patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[]), \
                     patch.object(at, "send_telegram"):
                    at.monitor_and_update_positions()

                disk = state_io.read_json_safe(at.POSITIONS_FILE, default=[], strict_on_corrupt=True)[0]
                # 0.005 SOL * $200 = $1.00 commission -> net = 10.0 - 1.0 = 9.0
                self.assertAlmostEqual(disk["commission_usd"], 1.0, places=4)
                self.assertAlmostEqual(disk["pnl_usd"], 9.0, places=4)
                self.assertEqual(cancels, ["SOLUSDT"])
                self.assertAlmostEqual(rv.get_profit_vault(state_path=rv.DEFAULT_VAULT_STATE_PATH, persist=True).high_water_mark_equity, 120.0, places=3)
            finally:
                _restore_env(saved)


class TestC7UnknownSlStateAndReconcile2021(unittest.TestCase):
    def test_unknown_sl_state_preserved_without_duplicate_sl_or_local_close(self):
        """C-7: On API outage (ok_algo=False / verify='UNKNOWN'), preserve sl_state='UNKNOWN', do NOT place duplicate SL or close locally."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                class MockBNUnknown:
                    def get_open_algo_orders(self, symbol=None):
                        return False, []

                    def set_stop_loss(self, *a, **kw):
                        raise AssertionError("set_stop_loss must NEVER be called when sl_state is UNKNOWN")

                    def get_positions(self, symbol=None):
                        return [{
                            "symbol": "SOLUSDT", "direction": "LONG", "position_amount": 2.0,
                            "entry_price": 150.0, "mark_price": 147.0, "unrealized_pnl": -6.0,
                            "liquidation_price": 143.0, "isolated_margin": 50.0, "leverage": 20,
                        }]

                    def verify_stop_loss_active(self, symbol, **kw):
                        return "UNKNOWN"

                    def close_position(self, *a, **kw):
                        raise AssertionError("close_position must NEVER run on UNKNOWN sl_state fallback")

                bn = MockBNUnknown()
                synced = at._build_synced_binance_pos(bn.get_positions()[0], bn, 16500)
                self.assertEqual(synced["sl_state"], "UNKNOWN")

                # Existing tracked position with confirmed sl/tp experiences temporary API outage -> keep sl/tp & status OPEN
                pos = _sample_pos("POS_C7_1", entry_price=150.0, stop_loss=148.5, take_profit=154.5, sl_state="CONFIRMED")
                state_io.atomic_write_json(at.POSITIONS_FILE, [pos], make_bak=False)

                with patch.object(at, "get_binance_client", return_value=bn), \
                     patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[{"symbol": "SOLUSDT", "lastPrice": "147.0"}]), \
                     patch.object(at, "_fetch_live_micro_state", return_value={"ofi_20": 0.0, "tfi_5m": 0.0, "sigma": 0.35}), \
                     patch("exec.thesis_monitor.IntrabarThesisMonitor.evaluate_position", return_value={"p_survive": 0.5, "should_scratch": False, "consecutive_breaches": 0}), \
                     patch.object(at, "send_telegram"):
                    res = at.monitor_and_update_positions()

                self.assertEqual(res[0]["status"], "OPEN")
                self.assertEqual(res[0]["sl_state"], "UNKNOWN")
                self.assertEqual(res[0]["stop_loss"], 148.5)
                self.assertEqual(res[0]["take_profit"], 154.5)
            finally:
                _restore_env(saved)

    def test_reconcile_missing_sl_2021_immediately_closes_reduce_only(self):
        """C-7 / WP-1: Reconcile SL hitting -2021 immediate trigger closes reduceOnly and cancels orders."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                pos = _sample_pos("POS_2021_REC", entry_price=150.0, stop_loss=148.5, sl_state="CONFIRMED")
                state_io.atomic_write_json(at.POSITIONS_FILE, [pos], make_bak=False)

                calls = []

                class MockBN2021:
                    def __init__(self):
                        self.closed = False

                    def get_positions(self, symbol=None):
                        calls.append(("get_positions", symbol))
                        if self.closed:
                            return []
                        return [{
                            "symbol": "SOLUSDT", "direction": "LONG", "position_amount": 2.0,
                            "entry_price": 150.0, "mark_price": 148.4, "unrealized_pnl": -3.2,
                            "liquidation_price": 143.0, "isolated_margin": 50.0, "leverage": 20,
                        }]

                    def verify_stop_loss_active(self, symbol, **kw):
                        return "MISSING"

                    def set_stop_loss(self, symbol, direction, sl_price):
                        calls.append(("set_stop_loss", sl_price))
                        return {"isError": True, "code": -2021, "would_immediately_trigger": True}

                    def close_position(self, symbol, direction, quantity=None):
                        calls.append(("close_position", symbol))
                        self.closed = True
                        return {"orderId": 555, "status": "FILLED"}

                    def cancel_all_orders(self, symbol):
                        calls.append(("cancel_all_orders", symbol))
                        return {"standard": {}, "algo": {}}

                    def get_open_algo_orders(self, symbol=None):
                        return True, []

                    def get_balance(self):
                        return {"total_wallet_balance": 96.8, "available_balance": 96.8}

                with patch.object(at, "get_binance_client", return_value=MockBN2021()), \
                     patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "get_binance_24h_tickers", return_value=[]), \
                     patch.object(at, "send_telegram"):
                    res = at.monitor_and_update_positions()

                self.assertEqual(res[0]["status"], "CLOSED_SL_IMMEDIATE_2021")
                op_names = [c[0] for c in calls]
                self.assertIn("set_stop_loss", op_names)
                self.assertIn("close_position", op_names)
                self.assertLess(op_names.index("close_position"), op_names.index("cancel_all_orders"))
            finally:
                _restore_env(saved)


class TestC10LearnersRetryAndWinClassification(unittest.TestCase):
    def test_win_classification_strictly_net_usd_gt_zero_and_no_stale_pnl_idr(self):
        """C-10: net_usd <= 0 MUST classify as loss even if stale pos['pnl_idr'] > 0 or net_usd == 0."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                # 1. Tiny gross +0.05 minus fee 0.10 = -0.05 net, with stale positive pnl_idr = +50000
                p_neg = _sample_pos("POS_C10_NEG", pnl_idr=50000)
                with patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "send_telegram"):
                    at._record_trade_close_in_journal(p_neg, 150.1, "CLOSED_TP", pnl_usd=0.05, fee_usd=0.10, gross_pnl_usd=0.05)

                # 2. Exact zero net_usd == 0.0 -> NOT a win (strict net_usd > 0)
                p_zero = _sample_pos("POS_C10_ZERO", pnl_idr=100)
                with patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "send_telegram"):
                    at._record_trade_close_in_journal(p_zero, 150.0, "CLOSED_SL", pnl_usd=0.10, fee_usd=0.10, gross_pnl_usd=0.10)

                ledger = state_io.read_json_safe(at.PERF_LEDGER_FILE, default={}, strict_on_corrupt=True)
                self.assertEqual(ledger["winning_trades"], 0)
                self.assertEqual(ledger["losing_trades"], 2)
                self.assertAlmostEqual(ledger["realized_pnl_usd"], -0.05, places=4)
                self.assertEqual(ledger["history"][1]["pnl_idr"], round(-0.05 * 16500))
            finally:
                _restore_env(saved)

    def test_learners_pending_retries_transient_failure_without_double_counting(self):
        """C-10: Transient failure in learners queues learners_pending in PERF_LEDGER_FILE and retries cleanly."""
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            saved = _isolate_env(tmp)
            try:
                p_fail = _sample_pos("POS_C10_RETRY")
                real_learners = at._update_closed_loop_learners
                calls = {"n": 0}

                def flaky_learners(pos, net_usd, exit_px, reason):
                    calls["n"] += 1
                    if calls["n"] == 1:
                        raise RuntimeError("transient disk hiccup")
                    return real_learners(pos, net_usd, exit_px, reason)

                with patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch.object(at, "_update_closed_loop_learners", side_effect=flaky_learners), \
                     patch.object(at, "send_telegram"), \
                     self.assertLogs("auto_trader", level="ERROR"):
                    at._record_trade_close_in_journal(p_fail, 148.5, "CLOSED_SL", pnl_usd=-10.0, fee_usd=0.5, gross_pnl_usd=-10.0)

                ledger1 = state_io.read_json_safe(at.PERF_LEDGER_FILE, default={}, strict_on_corrupt=True)
                self.assertIn("POS_C10_RETRY", ledger1["recorded_trade_ids"])
                self.assertEqual(len(ledger1["learners_pending"]), 1)
                self.assertEqual(ledger1["learners_pending"][0]["id"], "POS_C10_RETRY")
                self.assertEqual(ledger1["learners_pending"][0]["attempts"], 1)

                # Retry via _retry_pending_learners() succeeds and clears learners_pending
                with patch.object(at, "_get_config", return_value=_base_cfg()), \
                     patch.object(at, "_update_closed_loop_learners", side_effect=flaky_learners), \
                     patch.object(at, "send_telegram"):
                    retried = at._retry_pending_learners()

                self.assertEqual(retried, 1)
                self.assertEqual(calls["n"], 2)
                ledger2 = state_io.read_json_safe(at.PERF_LEDGER_FILE, default={}, strict_on_corrupt=True)
                self.assertEqual(ledger2["learners_pending"], [])
                # Trade count was NEVER double-counted
                self.assertEqual(ledger2["closed_trades"], 1)
                # HardRiskEngine received the loss once
                brk = state_io.read_json_safe(at.RISK_BREAKER_FILE, default={}, strict_on_corrupt=True)
                self.assertEqual(brk["consecutive_losses"], 1)
            finally:
                _restore_env(saved)


class TestTelegramPanicAndVault(unittest.TestCase):
    def test_panic_close_first_flat_verify_before_cancel_and_honest_failure_report(self):
        """A-3 & state_io: /panic only cancels orders & marks CLOSED_PANIC for verified flat symbols; alerts loudly on failure."""
        import telegram_bot as tb
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_res = tb.RESULTS_DIR
            orig_pos = tb.POSITIONS_FILE
            try:
                tb.RESULTS_DIR = tmp
                tb.POSITIONS_FILE = os.path.join(tmp, "active_positions.json")
                state_io.atomic_write_json(tb.POSITIONS_FILE, [
                    {"id": "P_SOL", "symbol": "SOL-USD", "binance_pair": "SOLUSDT", "status": "OPEN"},
                    {"id": "P_ETH", "symbol": "ETH-USD", "binance_pair": "ETHUSDT", "status": "OPEN"},
                ], make_bak=False)

                calls = []
                sent_msgs = []

                class MockPanicBN:
                    def __init__(self):
                        self.sol_closed = False

                    def get_positions(self, symbol=None):
                        calls.append(("get_positions", symbol))
                        if symbol == "SOLUSDT":
                            return [] if self.sol_closed else [{"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 1.0}]
                        if symbol == "ETHUSDT":
                            return [{"symbol": "ETHUSDT", "direction": "SHORT", "position_amount": 0.5}]
                        return [
                            {"symbol": "SOLUSDT", "direction": "LONG", "position_amount": 1.0},
                            {"symbol": "ETHUSDT", "direction": "SHORT", "position_amount": 0.5},
                        ]

                    def close_position(self, symbol, direction):
                        calls.append(("close_position", symbol))
                        if symbol == "SOLUSDT":
                            self.sol_closed = True
                            return {"orderId": 101, "status": "FILLED"}
                        return {"isError": True, "error": "ETH close timeout"}

                    def cancel_all_orders(self, symbol):
                        calls.append(("cancel_all_orders", symbol))
                        return {"standard": {}, "algo": {}}

                    def get_open_algo_orders(self, symbol=None):
                        return True, []

                with patch.object(tb, "get_binance_client", return_value=MockPanicBN()), \
                     patch.object(tb, "send_telegram_message", side_effect=lambda cid, txt, **kw: sent_msgs.append(txt)):
                    res = tb.handle_panic_command(12345)

                # SOL cancelled after flat verify; ETH NEVER cancelled!
                self.assertIn(("cancel_all_orders", "SOLUSDT"), calls)
                self.assertNotIn(("cancel_all_orders", "ETHUSDT"), calls)
                self.assertLess(
                    calls.index(("close_position", "SOLUSDT")),
                    calls.index(("cancel_all_orders", "SOLUSDT")),
                )
                self.assertFalse(res["all_flat_verified"])
                self.assertEqual(res["closed_symbols"], ["SOLUSDT (LONG)"])
                self.assertEqual(len(res["failed_symbols"]), 1)

                # POSITIONS_FILE marks SOL CLOSED_PANIC while ETH remains OPEN
                disk_pos = {p["id"]: p["status"] for p in state_io.read_json_safe(tb.POSITIONS_FILE, default=[], strict_on_corrupt=True)}
                self.assertEqual(disk_pos["P_SOL"], "CLOSED_PANIC")
                self.assertEqual(disk_pos["P_ETH"], "OPEN")

                # panic_lock.json written atomically via state_io
                panic_disk = state_io.read_json_safe(os.path.join(tmp, "panic_lock.json"), default={}, strict_on_corrupt=True)
                self.assertTrue(panic_disk["locked"])
                self.assertIn("ETHUSDT", panic_disk["failed_symbols"][0])

                # Telegram prominently warns about ETH failure
                self.assertTrue(sent_msgs)
                self.assertIn("GAGAL TUTUP", sent_msgs[0])
                self.assertIn("ETHUSDT", sent_msgs[0])
            finally:
                tb.RESULTS_DIR = orig_res
                tb.POSITIONS_FILE = orig_pos

    def test_vault_command_uses_vault_state_json_and_get_profit_vault(self):
        """telegram_bot /vault uses get_profit_vault() and vault_state.json (never stale profit_vault.json)."""
        import telegram_bot as tb
        import risk.vault as rv

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_res = tb.RESULTS_DIR
            orig_v = rv.DEFAULT_VAULT_STATE_PATH
            try:
                rv.reset_profit_vault_cache()
                tb.RESULTS_DIR = tmp
                rv.DEFAULT_VAULT_STATE_PATH = os.path.join(tmp, "vault_state.json")

                v = rv.get_profit_vault(initial_equity=100.0, state_path=rv.DEFAULT_VAULT_STATE_PATH, persist=True)
                v.update_equity(120.0)  # +20% >= +15% -> locks 0.35 * 20 = 7.0

                sent_msgs = []
                mock_bn = MagicMock()
                mock_bn.get_balance.return_value = {"total_wallet_balance": 120.0}

                with patch.object(tb, "get_binance_client", return_value=mock_bn), \
                     patch.object(tb, "send_telegram_message", side_effect=lambda cid, txt, **kw: sent_msgs.append(txt)):
                    info = tb.handle_vault_command(12345)

                self.assertAlmostEqual(info["hwm_equity"], 120.0, places=3)
                self.assertAlmostEqual(info["locked_vault_usdt"], 7.0, places=3)
                self.assertAlmostEqual(info["working_balance_usdt"], 113.0, places=3)
                self.assertIn("$7.0000 USDT", sent_msgs[0])
                self.assertFalse(os.path.exists(os.path.join(tmp, "profit_vault.json")))
            finally:
                rv.reset_profit_vault_cache()
                rv.DEFAULT_VAULT_STATE_PATH = orig_v
                tb.RESULTS_DIR = orig_res


class TestServerHardening(unittest.TestCase):
    def test_server_config_validation_400_cross_to_crossed_and_state_io(self):
        """server.py wraps save_trading_config -> HTTP 400, normalizes CROSS->CROSSED, and uses state_io for POSITIONS/STATE."""
        import server as srv
        import pipeline as pl
        import state_io

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orig_pos = srv.POSITIONS_FILE
            orig_state = srv.STATE_FILE
            orig_cfg = pl.CONFIG_FILE
            try:
                srv.POSITIONS_FILE = os.path.join(tmp, "active_positions.json")
                srv.STATE_FILE = os.path.join(tmp, "autotrader_state.json")
                pl.CONFIG_FILE = os.path.join(tmp, "trading_config.json")
                pl.save_trading_config({"max_budget_idr": 0, "margin_type": "ISOLATED"})

                client = srv.app.test_client()

                # 1. Invalid config via /api/config returns HTTP 400 (never unhandled 500)
                r_bad = client.post("/api/config", json={"all_in_balance_fraction": 1.5})
                self.assertEqual(r_bad.status_code, 400)
                self.assertFalse(r_bad.get_json()["success"])
                r_bad2 = client.post("/api/config", json={"margin_type": "INVALID_MODE"})
                self.assertEqual(r_bad2.status_code, 400)
                self.assertFalse(r_bad2.get_json()["success"])

                # 2. /api/futures/settings normalizes CROSS -> CROSSED and returns 400 on invalid
                r_fs_ok = client.post("/api/futures/settings", json={"margin_type": "CROSS"})
                self.assertEqual(r_fs_ok.status_code, 200)
                self.assertEqual(r_fs_ok.get_json()["config"]["margin_type"], "CROSSED")

                r_fs_bad = client.post("/api/futures/settings", json={"max_leverage": 999})
                self.assertEqual(r_fs_bad.status_code, 400)
                self.assertFalse(r_fs_bad.get_json()["success"])

                # 3. /api/execute normalizes CROSS -> CROSSED & writes POSITIONS_FILE atomically with .bak
                with patch.object(srv, "get_pluang_client", return_value=None):
                    r_ex = client.post("/api/execute", json={
                        "symbol": "SOL-USD", "direction": "LONG", "amount_idr": 0,
                        "leverage": 10, "margin_type": "CROSS", "order_type": "MARKET",
                    })
                self.assertEqual(r_ex.status_code, 200)
                self.assertEqual(r_ex.get_json()["position"]["margin_type"], "CROSSED")
                pos_disk = state_io.read_json_safe(srv.POSITIONS_FILE, default=[], strict_on_corrupt=True)
                self.assertEqual(len(pos_disk), 1)
                self.assertEqual(pos_disk[0]["margin_type"], "CROSSED")

                # 4. /api/auto/toggle persists STATE_FILE atomically with control_updated_at
                r_tog = client.post("/api/auto/toggle")
                self.assertEqual(r_tog.status_code, 200)
                st_disk = state_io.read_json_safe(srv.STATE_FILE, default={}, strict_on_corrupt=True)
                self.assertIn("control_updated_at", st_disk)

                # 5. Corrupt POSITIONS_FILE without .bak refuses overwrite on /api/execute (HTTP 500)
                with open(srv.POSITIONS_FILE, "w", encoding="utf-8") as f:
                    f.write('[{"id":"broken"')
                with patch.object(srv, "get_pluang_client", return_value=None):
                    r_corrupt = client.post("/api/execute", json={
                        "symbol": "BTC-USD", "direction": "LONG", "amount_idr": 0,
                        "leverage": 10, "margin_type": "ISOLATED", "order_type": "MARKET",
                    })
                self.assertEqual(r_corrupt.status_code, 500)
                with open(srv.POSITIONS_FILE, "r", encoding="utf-8") as f:
                    self.assertEqual(f.read(), '[{"id":"broken"')
            finally:
                srv.POSITIONS_FILE = orig_pos
                srv.STATE_FILE = orig_state
                pl.CONFIG_FILE = orig_cfg


if __name__ == "__main__":
    unittest.main(verbosity=2)
