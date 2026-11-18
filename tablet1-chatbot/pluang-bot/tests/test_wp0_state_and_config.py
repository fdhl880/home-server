"""
WP-0 TDD Test Suite: Core Reliability, Atomic State I/O, Locking & Config Schema.
Covers:
  - state_io (get_file_lock, atomic_write_json, read_json_safe, CorruptedStateError)
  - config_schema (bounds/types, breaker aliases, SHA-256 startup log, invalid reload fallback)
  - pipeline.get_trading_config / max_drawdown_pct alignment
  - auto_trader (POSITIONS_FILE RLock & merge-by-id, _ensure_perf_ledger, load/save_hard_risk_engine)
  - risk.vault (get_profit_vault singleton, concurrent update_equity, .bak recovery)
  - bandit_allocator, hmm_drift (append_episodic_episode), calibration, ai.conformal locking & atomic I/O
  - housekeeping (pipeline.py.bak_before_ai_only removed, unused exec/* docstrings)
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)


class TestStateIO(unittest.TestCase):
    def test_get_file_lock_normalized_paths(self):
        import state_io

        with tempfile.TemporaryDirectory() as tmp:
            p1 = os.path.join(tmp, "sub", "..", "state.json")
            p2 = os.path.abspath(os.path.join(tmp, "state.json"))
            p3 = os.path.join(tmp, "other.json")
            l1 = state_io.get_file_lock(p1)
            l2 = state_io.get_file_lock(p2)
            l3 = state_io.get_file_lock(p3)
            self.assertIs(l1, l2)
            self.assertIsNot(l1, l3)
            if os.name == "nt":
                l_upper = state_io.get_file_lock(p2.upper())
                self.assertIs(l1, l_upper)

    def test_atomic_write_creates_bak_and_rejects_nan(self):
        import state_io

        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "data.json")
            bak = f"{target}.bak"

            ok1 = state_io.atomic_write_json(target, {"v": 1, "items": ["a"]})
            self.assertTrue(ok1)
            self.assertTrue(os.path.exists(target))
            self.assertFalse(os.path.exists(bak))

            ok2 = state_io.atomic_write_json(target, {"v": 2, "items": ["a", "b"]})
            self.assertTrue(ok2)
            self.assertTrue(os.path.exists(bak))
            with open(bak, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"v": 1, "items": ["a"]})
            with open(target, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"v": 2, "items": ["a", "b"]})

            # NaN must fail cleanly (allow_nan=False), log error, preserve primary & bak, leave no .tmp
            with self.assertLogs("state_io", level="ERROR"):
                ok_nan = state_io.atomic_write_json(target, {"bad": float("nan")})
            self.assertFalse(ok_nan)
            with open(target, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"v": 2, "items": ["a", "b"]})
            leftover = [fn for fn in os.listdir(tmp) if ".tmp" in fn]
            self.assertEqual(leftover, [])

    def test_atomic_write_retries_permission_error_and_cleans_tmp(self):
        import state_io

        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "retry.json")
            real_replace = os.replace
            calls = {"n": 0}

            def flaky_replace(src, dst):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise PermissionError("simulated AV lock")
                return real_replace(src, dst)

            with patch("state_io.os.replace", side_effect=flaky_replace), \
                 patch("state_io.time.sleep") as mock_sleep:
                ok = state_io.atomic_write_json(target, {"ok": True}, make_bak=False)
            self.assertTrue(ok)
            self.assertEqual(calls["n"], 3)
            self.assertEqual(mock_sleep.call_count, 2)
            mock_sleep.assert_called_with(0.05)
            self.assertEqual([fn for fn in os.listdir(tmp) if ".tmp" in fn], [])

            # Permanent PermissionError -> returns False, logs error, cleans .tmp
            with patch("state_io.os.replace", side_effect=PermissionError("locked forever")), \
                 patch("state_io.time.sleep"), \
                 self.assertLogs("state_io", level="ERROR"):
                ok_fail = state_io.atomic_write_json(target, {"ok": False}, make_bak=False)
            self.assertFalse(ok_fail)
            self.assertEqual([fn for fn in os.listdir(tmp) if ".tmp" in fn], [])
            with open(target, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"ok": True})

    def test_read_json_safe_corrupt_fallback_and_strict_mode(self):
        import state_io

        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "missing.json")
            default_list = []
            res_missing = state_io.read_json_safe(missing, default=default_list, strict_on_corrupt=True)
            self.assertEqual(res_missing, [])
            self.assertIsNot(res_missing, default_list)

            target = os.path.join(tmp, "positions.json")
            state_io.atomic_write_json(target, [{"id": "P1", "status": "OPEN"}])
            state_io.atomic_write_json(target, [{"id": "P1", "status": "OPEN"}, {"id": "P2", "status": "OPEN"}])

            # Truncate primary to simulate crash corruption
            corrupt_bytes = '[{"id": "P1", "stat'
            with open(target, "w", encoding="utf-8") as f:
                f.write(corrupt_bytes)

            # Should recover from .bak AND never overwrite the corrupt file
            with self.assertLogs("state_io", level="WARNING"):
                recovered = state_io.read_json_safe(target, default=[], strict_on_corrupt=True)
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0]["id"], "P1")
            with open(target, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), corrupt_bytes)

            # Remove .bak -> strict_on_corrupt=True MUST raise CorruptedStateError
            os.remove(f"{target}.bak")
            with self.assertLogs("state_io", level="ERROR"):
                with self.assertRaises(state_io.CorruptedStateError):
                    state_io.read_json_safe(target, default=[], strict_on_corrupt=True)
            # Non-strict returns deepcopy(default) without overwriting corrupt primary
            with self.assertLogs("state_io", level="ERROR"):
                fallback = state_io.read_json_safe(target, default=[], strict_on_corrupt=False)
            self.assertEqual(fallback, [])
            with open(target, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), corrupt_bytes)


class TestConfigSchemaAndPipelineAlignment(unittest.TestCase):
    def test_validate_live_trading_config(self):
        import config_schema

        cfg_path = os.path.join(BOT_DIR, "trading_config.json")
        cache_key = config_schema._norm_path(cfg_path)
        config_schema._LAST_LOGGED_HASH.pop(cache_key, None)
        with self.assertLogs("config_schema", level="INFO") as cm:
            cfg = config_schema.load_trading_config(cfg_path)
        self.assertTrue(any("sha256=" in m.lower() for m in cm.output))
        self.assertEqual(cfg["fixed_leverage"], 20)
        self.assertEqual(cfg["max_drawdown_pct"], 25.0)
        self.assertEqual(cfg["circuit_breaker_consecutive_losses"], 2)
        self.assertEqual(cfg["breaker_consecutive_losses"], 2)

    def test_breaker_alias_normalization_and_bounds(self):
        import config_schema

        c1 = config_schema.validate_trading_config({"circuit_breaker_consecutive_losses": 3})
        self.assertEqual(c1["circuit_breaker_consecutive_losses"], 3)
        self.assertEqual(c1["breaker_consecutive_losses"], 3)

        c2 = config_schema.validate_trading_config({"breaker_consecutive_losses": 4})
        self.assertEqual(c2["circuit_breaker_consecutive_losses"], 4)
        self.assertEqual(c2["breaker_consecutive_losses"], 4)

        with self.assertRaises(config_schema.ConfigValidationError):
            config_schema.validate_trading_config({
                "circuit_breaker_consecutive_losses": 2,
                "breaker_consecutive_losses": 4,
            })

        bad_cases = [
            {"fixed_leverage": 0},
            {"fixed_leverage": 21},
            {"fixed_leverage": True},
            {"fixed_leverage": 2.5},
            {"all_in_balance_fraction": 0.0},
            {"all_in_balance_fraction": 0.99},
            {"all_in_balance_fraction": -0.1},
            {"max_sl_pct": 0.0},
            {"max_sl_pct": 5.5},
            {"min_sl_pct": 3.0, "max_sl_pct": 2.0},
            {"breaker_daily_dd_pct": 0.0},
            {"breaker_daily_dd_pct": 55.0},
            {"breaker_cooldown_hours": 0},
            {"breaker_cooldown_hours": 169},
            {"margin_type": "INVALID"},
            {"max_drawdown_pct": float("nan")},
        ]
        for bad in bad_cases:
            with self.subTest(bad=bad):
                with self.assertRaises(config_schema.ConfigValidationError):
                    config_schema.validate_trading_config(bad)

    def test_sha256_startup_log_and_invalid_runtime_reload_fallback(self):
        import config_schema
        import state_io

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = os.path.join(tmp, "trading_config.json")
            valid_a = {
                "fixed_leverage": 20,
                "max_leverage": 20,
                "margin_type": "ISOLATED",
                "sizing_mode": "ALL_IN",
                "all_in_balance_fraction": 0.90,
                "max_sl_pct": 2.0,
                "min_sl_pct": 0.45,
                "min_confidence_score": 77,
                "max_drawdown_pct": 25.0,
                "breaker_daily_dd_pct": 12.0,
                "circuit_breaker_consecutive_losses": 3,
                "breaker_cooldown_hours": 10,
            }
            state_io.atomic_write_json(cfg_path, valid_a, make_bak=False)

            with self.assertLogs("config_schema", level="INFO") as cm:
                loaded_a = config_schema.load_trading_config(cfg_path)
            self.assertEqual(loaded_a["min_confidence_score"], 77)
            self.assertEqual(loaded_a["breaker_consecutive_losses"], 3)
            self.assertTrue(any("sha256=" in m.lower() for m in cm.output))

            # Runtime edit introduces out-of-range leverage -> must reject & return last known-good (77, NOT default 68)
            bad_cfg = dict(valid_a, fixed_leverage=50, min_confidence_score=10)
            state_io.atomic_write_json(cfg_path, bad_cfg, make_bak=False)
            with self.assertLogs("config_schema", level="ERROR"):
                reloaded_bad = config_schema.load_trading_config(cfg_path)
            self.assertEqual(reloaded_bad["fixed_leverage"], 20)
            self.assertEqual(reloaded_bad["min_confidence_score"], 77)
            self.assertEqual(reloaded_bad["all_in_balance_fraction"], 0.90)

            # Corrupt JSON at runtime -> must reject & return last known-good
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write("{corrupt_json")
            with self.assertLogs("config_schema", level="ERROR"):
                reloaded_corrupt = config_schema.load_trading_config(cfg_path)
            self.assertEqual(reloaded_corrupt["min_confidence_score"], 77)

    def test_pipeline_max_drawdown_default_aligned(self):
        import pipeline as pl

        self.assertEqual(pl.MAX_DRAWDOWN_PCT, 25.0)
        with tempfile.TemporaryDirectory() as tmp:
            orig_cfg_file = pl.CONFIG_FILE
            try:
                pl.CONFIG_FILE = os.path.join(tmp, "nonexistent_trading_config.json")
                cfg = pl.get_trading_config()
                self.assertEqual(cfg["max_drawdown_pct"], 25.0)
                self.assertEqual(cfg["breaker_consecutive_losses"], 2)
                self.assertEqual(cfg["circuit_breaker_consecutive_losses"], 2)
            finally:
                pl.CONFIG_FILE = orig_cfg_file


class TestAutoTraderAndConcurrency(unittest.TestCase):
    def test_corrupt_positions_and_ledger_refuse_wipe(self):
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory() as tmp:
            orig_res = at.RESULTS_DIR
            orig_pos = at.POSITIONS_FILE
            orig_led = at.PERF_LEDGER_FILE
            orig_brk = at.RISK_BREAKER_FILE
            try:
                at.RESULTS_DIR = tmp
                at.POSITIONS_FILE = os.path.join(tmp, "active_positions.json")
                at.PERF_LEDGER_FILE = os.path.join(tmp, "performance_ledger.json")
                at.RISK_BREAKER_FILE = os.path.join(tmp, "risk_breaker_state.json")

                # 1. Corrupt POSITIONS_FILE without .bak -> refuses overwrite
                corrupt_pos = '[{"id": "POS_KEEP", "status": "OPEN"'
                with open(at.POSITIONS_FILE, "w", encoding="utf-8") as f:
                    f.write(corrupt_pos)
                with self.assertRaises(state_io.CorruptedStateError):
                    at._load_positions_safe(strict=True)
                res_mon = at.monitor_and_update_positions()
                self.assertEqual(res_mon, [])
                with open(at.POSITIONS_FILE, "r", encoding="utf-8") as f:
                    self.assertEqual(f.read(), corrupt_pos)

                guard = at.check_wallet_and_position_guard()
                self.assertTrue(guard["pause_scanning"])
                with open(at.POSITIONS_FILE, "r", encoding="utf-8") as f:
                    self.assertEqual(f.read(), corrupt_pos)

                # 2. Corrupt PERF_LEDGER_FILE without .bak -> raises CorruptedStateError, refuses overwrite
                corrupt_led = '{"winning_trades": 42, "broken'
                with open(at.PERF_LEDGER_FILE, "w", encoding="utf-8") as f:
                    f.write(corrupt_led)
                with self.assertRaises(state_io.CorruptedStateError):
                    at._ensure_perf_ledger()
                with open(at.PERF_LEDGER_FILE, "r", encoding="utf-8") as f:
                    self.assertEqual(f.read(), corrupt_led)

                # 3. With .bak present, PERF_LEDGER_FILE recovers real stats
                state_io.atomic_write_json(at.PERF_LEDGER_FILE + ".bak", {
                    "winning_trades": 7, "losing_trades": 2, "closed_trades": 9,
                    "win_rate_pct": 77.78, "realized_pnl_idr": 100000, "realized_pnl_usd": 6.0,
                    "recorded_trade_ids": ["T1"], "history": [], "updated_at": "2026-11-18"
                }, make_bak=False)
                # Write corrupt primary again (atomic_write_json above touched .bak directly)
                with open(at.PERF_LEDGER_FILE, "w", encoding="utf-8") as f:
                    f.write(corrupt_led)
                rec_led = at._ensure_perf_ledger()
                self.assertEqual(rec_led["winning_trades"], 7)

                # 4. Corrupt RISK_BREAKER_FILE without .bak fails closed (breaker active) without wiping
                corrupt_brk = '{"consecutive_losses": 2, "breaker_until'
                with open(at.RISK_BREAKER_FILE, "w", encoding="utf-8") as f:
                    f.write(corrupt_brk)
                eng = at.load_hard_risk_engine()
                self.assertTrue(eng.is_circuit_breaker_active())
                with open(at.RISK_BREAKER_FILE, "r", encoding="utf-8") as f:
                    self.assertEqual(f.read(), corrupt_brk)
            finally:
                at.RESULTS_DIR = orig_res
                at.POSITIONS_FILE = orig_pos
                at.PERF_LEDGER_FILE = orig_led
                at.RISK_BREAKER_FILE = orig_brk

    def test_concurrent_record_position_and_merge_lose_zero_entries(self):
        import auto_trader as at
        import state_io

        with tempfile.TemporaryDirectory() as tmp:
            orig_res = at.RESULTS_DIR
            orig_pos = at.POSITIONS_FILE
            orig_brk = at.RISK_BREAKER_FILE
            orig_state = at.STATE_FILE
            try:
                at.RESULTS_DIR = tmp
                at.POSITIONS_FILE = os.path.join(tmp, "active_positions.json")
                at.RISK_BREAKER_FILE = os.path.join(tmp, "risk_breaker_state.json")
                at.STATE_FILE = os.path.join(tmp, "autotrader_state.json")

                class MockBNConcurrent:
                    def get_balance(self):
                        return {"available_balance": 100.0, "total_wallet_balance": 100.0}

                    def execute_full_trade(self, signal, config=None):
                        time.sleep(0.01)
                        return {
                            "binance_synced": True,
                            "order_id": f"ORD_{signal['symbol']}",
                            "entry_price": signal["entry_price"],
                            "take_profit": signal["take_profit"],
                            "stop_loss": signal["stop_loss"],
                            "sl_algo_id": 101,
                            "tp_algo_id": 202,
                            "sl_state": "CONFIRMED",
                            "quantity": 1.0,
                            "routing_used": "MAKER_GTX_FILLED",
                        }

                # Seed 1 already-closed position that must NEVER be lost or reopened
                closed_seed = {"id": "POS_CLOSED_0", "symbol": "BTC-USD", "status": "CLOSED_TP", "entry_price": 60000.0}
                state_io.atomic_write_json(at.POSITIONS_FILE, [closed_seed], make_bak=False)

                # Also simulate a stale reader trying to merge stale OPEN view after POS_CLOSED_0
                n_positions = 12
                parse_errors = []
                stop_reader = threading.Event()

                def reader_loop():
                    while not stop_reader.is_set():
                        try:
                            data = state_io.read_json_safe(at.POSITIONS_FILE, default=[], strict_on_corrupt=False)
                            if not isinstance(data, list):
                                parse_errors.append(f"bad_type:{type(data)}")
                        except Exception as exc:
                            parse_errors.append(str(exc))
                        time.sleep(0.002)

                reader_t = threading.Thread(target=reader_loop, daemon=True)
                reader_t.start()

                def open_one(idx: int):
                    sig = {
                        "id": f"POS_CONC_{idx}",
                        "symbol": f"COIN{idx}-USD",
                        "binance_pair": f"COIN{idx}USDT",
                        "direction": "LONG",
                        "entry_price": 100.0 + idx,
                        "stop_loss": 98.5 + idx,
                        "take_profit": 103.0 + idx,
                        "confidence_score": 82,
                        "setup_name": "EMA_PULLBACK",
                    }
                    return at.record_position(sig)

                def merge_update_loop(idx: int):
                    # Concurrent monitor-style updates on POS_CONC_0 or POS_CLOSED_0 stale guard
                    at._save_positions_merged([
                        {"id": "POS_CLOSED_0", "symbol": "BTC-USD", "status": "OPEN", "entry_price": 60000.0},
                        {"id": f"POS_MON_{idx}", "symbol": f"MON{idx}-USD", "status": "OPEN", "entry_price": 50.0},
                    ])

                fake_cfg = {
                    "max_budget_idr": 0,
                    "max_leverage": 20,
                    "fixed_leverage": 20,
                    "margin_type": "ISOLATED",
                    "sizing_mode": "ALL_IN",
                    "all_in_balance_fraction": 0.95,
                    "max_sl_pct": 2.25,
                    "min_sl_pct": 0.45,
                    "max_concurrent_positions": 50,
                    "max_daily_trades": 50,
                    "auto_execute": True,
                }
                with patch.object(at, "get_binance_client", return_value=MockBNConcurrent()), \
                     patch.object(at, "_get_config", return_value=fake_cfg), \
                     patch.object(at, "get_fx_info", return_value={"usd_idr": 16500}), \
                     patch("journal.open_trade", return_value=None):
                    with ThreadPoolExecutor(max_workers=8) as pool:
                        futs = [pool.submit(open_one, i) for i in range(n_positions)]
                        futs += [pool.submit(merge_update_loop, i) for i in range(4)]
                        results = [f.result() for f in futs[:n_positions]]
                        for f in futs[n_positions:]:
                            f.result()

                stop_reader.set()
                reader_t.join(timeout=1.0)

                self.assertEqual(parse_errors, [])
                self.assertTrue(all(r is not None for r in results))
                final_positions = state_io.read_json_safe(at.POSITIONS_FILE, default=[], strict_on_corrupt=True)
                ids = {p["id"] for p in final_positions}
                for i in range(n_positions):
                    self.assertIn(f"POS_CONC_{i}", ids)
                for i in range(4):
                    self.assertIn(f"POS_MON_{i}", ids)
                closed_row = next(p for p in final_positions if p["id"] == "POS_CLOSED_0")
                self.assertEqual(closed_row["status"], "CLOSED_TP")
                brk_state = state_io.read_json_safe(at.RISK_BREAKER_FILE, default={}, strict_on_corrupt=True)
                self.assertEqual(brk_state.get("daily_trades_count"), n_positions)
                leftovers = [fn for fn in os.listdir(tmp) if ".tmp" in fn]
                self.assertEqual(leftovers, [])
            finally:
                at.RESULTS_DIR = orig_res
                at.POSITIONS_FILE = orig_pos
                at.RISK_BREAKER_FILE = orig_brk
                at.STATE_FILE = orig_state


class TestVaultBanditDriftConcurrency(unittest.TestCase):
    def test_profit_vault_singleton_and_concurrent_update_equity(self):
        import risk.vault as rv
        import state_io

        with tempfile.TemporaryDirectory() as tmp:
            v_path = os.path.join(tmp, "vault_state.json")
            rv.reset_profit_vault_cache()
            v_a = rv.get_profit_vault(initial_equity=100.0, state_path=v_path, persist=True)
            v_b = rv.get_profit_vault(initial_equity=100.0, state_path=v_path, persist=True)
            self.assertIs(v_a, v_b)

            # Backward-compatible direct construction still works cleanly
            v_direct = rv.ProfitVault(state_path=v_path, persist=True)
            self.assertEqual(v_direct.high_water_mark_equity, 100.0)

            equities = [115.0 * (1.16 ** i) for i in range(1, 16)]
            # Mix calls across singleton and direct ProfitVault instances concurrently
            def worker(idx_eq):
                idx, eq = idx_eq
                inst = rv.get_profit_vault(state_path=v_path, persist=True) if idx % 2 == 0 else rv.ProfitVault(state_path=v_path, persist=True)
                return inst.update_equity(eq)

            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(worker, enumerate(equities)))

            # HWM must equal the max equity reached (since sequence is strictly rising by >15% steps or highest reached)
            final_v = rv.ProfitVault(state_path=v_path, persist=True)
            self.assertAlmostEqual(final_v.high_water_mark_equity, max(equities), places=4)
            self.assertGreater(final_v.locked_profit_vault_usdt, 0.0)
            self.assertTrue(os.path.exists(f"{v_path}.bak"))
            self.assertEqual([fn for fn in os.listdir(tmp) if ".tmp" in fn], [])
            disk = state_io.read_json_safe(v_path, default={}, strict_on_corrupt=True)
            self.assertAlmostEqual(disk["high_water_mark_equity"], max(equities), places=4)

    def test_bandit_allocator_concurrent_save_and_corrupt_bak(self):
        from strategies.bandit_allocator import ContextualThompsonBandit
        import state_io

        with tempfile.TemporaryDirectory() as tmp:
            b_path = os.path.join(tmp, "bandit_state.json")
            b1 = ContextualThompsonBandit(state_path=b_path, seed=11)

            def update_arm(i):
                b1.update("S1_TREND_PULLBACK", "TREND_BULL", r_net=1.2 if i % 2 == 0 else -0.5)

            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(update_arm, range(24)))

            self.assertEqual(b1.get_arm("S1_TREND_PULLBACK", "TREND_BULL")["n_updates"], 24)
            self.assertTrue(os.path.exists(f"{b_path}.bak"))
            self.assertEqual([fn for fn in os.listdir(tmp) if ".tmp" in fn], [])

            # Corrupt primary -> reloads from .bak without losing learned arm
            with open(b_path, "w", encoding="utf-8") as f:
                f.write('{"arms": {"S1_TREND_PULLBACK|TREND_BULL": {"alpha": ')
            b2 = ContextualThompsonBandit(state_path=b_path, seed=11)
            self.assertGreaterEqual(b2.get_arm("S1_TREND_PULLBACK", "TREND_BULL")["n_updates"], 23)

    def test_hmm_drift_episodic_concurrent_and_corrupt_protection(self):
        import features.hmm_drift as hd
        import state_io

        with tempfile.TemporaryDirectory() as tmp:
            ep_path = os.path.join(tmp, "episodic_memory.json")

            def add_ep(i):
                return hd.append_episodic_episode(
                    feature_vector=[0.1 * (i % 5)] * 15,
                    r_multiple_net=1.0,
                    outcome_win=True,
                    regime="TREND_BULL",
                    strategy_id="S1",
                    note=f"ep_{i}",
                    path=ep_path,
                )

            with ThreadPoolExecutor(max_workers=6) as pool:
                oks = list(pool.map(add_ep, range(16)))
            self.assertTrue(all(oks))
            rows = state_io.read_json_safe(ep_path, default=[], strict_on_corrupt=True)
            self.assertEqual(len(rows), 16)
            self.assertEqual([fn for fn in os.listdir(tmp) if ".tmp" in fn], [])

            # Corrupt primary AND remove .bak -> append_episodic_episode MUST refuse to overwrite with 1 item
            os.remove(f"{ep_path}.bak")
            corrupt_ep = '[{"vector": [0.1], "broken'
            with open(ep_path, "w", encoding="utf-8") as f:
                f.write(corrupt_ep)
            ok_corrupt = add_ep(99)
            self.assertFalse(ok_corrupt)
            with open(ep_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), corrupt_ep)

    def test_calibration_and_conformal_locks_and_state_io(self):
        from calibration import ProbabilityCalibrator
        from ai.conformal import AdaptiveConformalFilter

        with tempfile.TemporaryDirectory() as tmp:
            cal_path = os.path.join(tmp, "cal.json")
            conf_path = os.path.join(tmp, "conf.json")

            cal = ProbabilityCalibrator(state_path=cal_path)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda i: cal.record_outcome(0.75 + 0.01 * (i % 5), i % 2 == 0), range(12)))
            self.assertTrue(cal.save_state())
            cal2 = ProbabilityCalibrator(state_path=cal_path)
            self.assertEqual(len(cal2.history_y), 12)

            aci = AdaptiveConformalFilter(state_path=conf_path)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda i: aci.update(0.80, i % 3 != 0), range(12)))
            self.assertTrue(aci.save_state())
            aci2 = AdaptiveConformalFilter(state_path=conf_path)
            self.assertEqual(len(aci2.error_history), 12)
            self.assertAlmostEqual(aci2.alpha_t, aci.alpha_t, places=4)


class TestHousekeeping(unittest.TestCase):
    def test_unused_backup_removed_and_exec_docstrings_present(self):
        self.assertFalse(os.path.exists(os.path.join(BOT_DIR, "pipeline.py.bak_before_ai_only")))
        for rel in ("exec/engine.py", "exec/event_bus.py", "exec/native_pricematch.py"):
            full = os.path.join(BOT_DIR, rel)
            with open(full, "r", encoding="utf-8") as f:
                head = f.read(800)
            self.assertIn("NOT imported by the live auto_trader/binance_futures path", head, msg=rel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
