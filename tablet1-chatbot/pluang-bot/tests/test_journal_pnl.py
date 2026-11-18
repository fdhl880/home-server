"""
WP-7 TDD Test Suite: Journal Gross vs Net PnL, Fee/Funding Drag, Structured TCA JSONL,
Daily Observability / Cost-Drift Report, Log Rotation (20MB), and SQLite Online Backups.

Strictly offline (TemporaryDirectory, zero live network calls).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

import journal


class TestJournalPnLAndObservability(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp_dir = self._tmp.name
        self.orig_db_path = journal.DB_PATH
        self.db_path = os.path.join(self.tmp_dir, "pyrofuel_journal.db")
        journal.DB_PATH = self.db_path
        journal.init_db(self.db_path)

    def tearDown(self):
        journal.DB_PATH = self.orig_db_path
        self._tmp.cleanup()

    def test_gross_vs_net_pnl_fees_funding_and_tca_jsonl_append(self):
        """Verify gross vs net PnL deduction of fee_usdt + funding_usdt, fee_drag_roe_pct, and tca_metrics.jsonl append."""
        now_ms = int(time.time() * 1000)
        dec_id = journal.record_decision(
            {
                "decision_id": "DEC_SOL_1",
                "ts_ms": now_ms - 7200_000,
                "symbol": "SOLUSDT",
                "regime": "TREND_BULL",
                "strategy_id": "S1_TREND_PULLBACK",
                "direction": "LONG",
                "decision": "TRADE",
                "p_raw": 0.80,
                "p_cal": 0.78,
            },
            db_path=self.db_path,
        )

        # Open LONG at 100.0 with margin=50 USDT, leverage=20 -> notional=1000 USDT, qty=10, SL=99.0 (1% = $10 risk)
        trade_id = journal.record_trade_open(
            {
                "trade_id": "TRD_SOL_1",
                "decision_id": dec_id,
                "symbol": "SOLUSDT",
                "direction": "LONG",
                "regime": "TREND_BULL",
                "strategy_id": "S1_TREND_PULLBACK",
                "leverage": 20,
                "margin_usdt": 50.0,
                "notional_usdt": 1000.0,
                "qty": 10.0,
                "entry_plan": 100.0,
                "sl_plan": 99.0,
                "tp_plan": 102.0,
                "entry_fill": 100.0,
                "fee_usdt": 0.20,
                "funding_usdt": 0.0,
                "opened_at": now_ms - 7200_000,
            },
            db_path=self.db_path,
        )
        self.assertEqual(trade_id, "TRD_SOL_1")

        # Record TCA execution with arrival=100.0, fill=100.02 (+2 bps slippage), fee=0.20 on margin=50.0 -> 0.40% ROE drag
        exec_id = journal.record_tca_execution(
            {
                "exec_id": "TCA_SOL_1",
                "trade_id": trade_id,
                "symbol": "SOLUSDT",
                "direction": "LONG",
                "routing_used": "MAKER_GTX_FILLED",
                "arrival_price": 100.0,
                "fill_price": 100.02,
                "fee_usdt": 0.20,
                "margin_usdt": 50.0,
                "impact_bps_est": 1.5,
                "ts_ms": now_ms - 7199_000,
            },
            db_path=self.db_path,
        )
        self.assertEqual(exec_id, "TCA_SOL_1")

        tca_sum = journal.get_tca_summary(limit=10, db_path=self.db_path)
        self.assertEqual(tca_sum["count"], 1)
        self.assertAlmostEqual(tca_sum["avg_arrival_slippage_bps"], 2.0, places=2)
        self.assertAlmostEqual(tca_sum["avg_fee_drag_roe_pct"], 0.40, places=3)

        # Close trade at 102.0 -> gross PnL = +$20.00, fee_usdt=0.70, funding_usdt=0.30 -> net PnL = +$19.00
        # Risk unit = $10.00 -> r_multiple_net = +1.90R
        close_res = journal.record_trade_close(
            trade_id,
            {
                "exit_fill": 102.0,
                "fee_usdt": 0.70,
                "funding_usdt": 0.30,
                "close_reason": "TP2",
                "closed_at": now_ms,
                "assumed_cost_pct": 0.08,
            },
            db_path=self.db_path,
        )
        self.assertIsNotNone(close_res)
        self.assertAlmostEqual(close_res["net_pnl_usdt"], 19.0, places=4)
        self.assertAlmostEqual(close_res["r_multiple_net"], 1.90, places=3)

        # Verify tca_metrics.jsonl was written in the temporary results directory
        jsonl_path = os.path.join(self.tmp_dir, "tca_metrics.jsonl")
        self.assertTrue(os.path.exists(jsonl_path), "tca_metrics.jsonl must be created alongside DB_PATH")
        with open(jsonl_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertGreaterEqual(len(lines), 2)

        close_line = [rec for rec in lines if rec.get("trade_id") == trade_id and rec.get("net_pnl_usdt") == 19.0][-1]
        required_keys = (
            "trade_id",
            "symbol",
            "direction",
            "regime",
            "strategy_id",
            "arrival_slippage_bps",
            "fee_usdt",
            "funding_usdt",
            "net_pnl_usdt",
            "r_multiple_net",
            "realized_cost_pct",
            "assumed_cost_pct",
            "cost_drift_pct",
            "ts_ms",
        )
        for k in required_keys:
            self.assertIn(k, close_line, f"Missing key {k} in tca_metrics.jsonl record")
        self.assertEqual(close_line["symbol"], "SOLUSDT")
        self.assertEqual(close_line["strategy_id"], "S1_TREND_PULLBACK")
        self.assertAlmostEqual(close_line["fee_usdt"], 0.70, places=4)
        self.assertAlmostEqual(close_line["funding_usdt"], 0.30, places=4)
        self.assertAlmostEqual(close_line["assumed_cost_pct"], 0.08, places=4)
        # realized_cost_pct = (0.70 + 0.30)/1000*100 (0.10%) + 2.0 bps (0.02%) = 0.12%
        self.assertAlmostEqual(close_line["realized_cost_pct"], 0.12, places=3)
        self.assertAlmostEqual(close_line["cost_drift_pct"], 0.04, places=3)

    def test_daily_observability_report_and_cost_drift_alert(self):
        """Verify generate_daily_observability_report & format_daily_telegram_report detect cost drift & net-of-fees PnL."""
        now_ms = int(time.time() * 1000)

        # Trade 1: Win with high fees/funding/slippage causing cost drift > assumed 0.08%
        journal.record_trade_open(
            {
                "trade_id": "TRD_DRIFT_1",
                "symbol": "ETHUSDT",
                "direction": "LONG",
                "regime": "TREND_BULL",
                "strategy_id": "S1_TREND_PULLBACK",
                "leverage": 20,
                "margin_usdt": 50.0,
                "notional_usdt": 1000.0,
                "qty": 0.5,
                "entry_plan": 2000.0,
                "sl_plan": 1980.0,
                "tp_plan": 2040.0,
                "entry_fill": 2000.0,
                "opened_at": now_ms - 3600_000,
            },
            db_path=self.db_path,
        )
        journal.record_tca_execution(
            {
                "exec_id": "TCA_DRIFT_1",
                "trade_id": "TRD_DRIFT_1",
                "symbol": "ETHUSDT",
                "direction": "LONG",
                "routing_used": "MARKET_TAKER",
                "arrival_price": 2000.0,
                "fill_price": 2001.6,  # +8 bps slippage (0.08%)
                "fee_usdt": 1.0,
                "margin_usdt": 50.0,
                "ts_ms": now_ms - 3599_000,
            },
            db_path=self.db_path,
        )
        journal.record_trade_close(
            "TRD_DRIFT_1",
            {
                "exit_fill": 2040.0,  # Gross = +$20.00
                "fee_usdt": 1.20,
                "funding_usdt": 0.40,  # Fee+Funding = $1.60 (0.16% of $1000 notional) + 0.08% slip = 0.24% realized cost
                "close_reason": "TP2",
                "closed_at": now_ms - 1800_000,
            },
            db_path=self.db_path,
        )

        # Trade 2: Loss
        journal.record_trade_open(
            {
                "trade_id": "TRD_DRIFT_2",
                "symbol": "SOLUSDT",
                "direction": "SHORT",
                "regime": "TREND_BEAR",
                "strategy_id": "S2_OI_VOL_BREAKOUT",
                "leverage": 20,
                "margin_usdt": 50.0,
                "notional_usdt": 1000.0,
                "qty": 10.0,
                "entry_plan": 100.0,
                "sl_plan": 101.0,
                "tp_plan": 98.0,
                "entry_fill": 100.0,
                "opened_at": now_ms - 1200_000,
            },
            db_path=self.db_path,
        )
        journal.record_trade_close(
            "TRD_DRIFT_2",
            {
                "exit_fill": 101.0,  # Gross = -$10.00
                "fee_usdt": 1.00,
                "funding_usdt": 0.20,  # Net = -$11.20
                "close_reason": "SL",
                "closed_at": now_ms - 600_000,
            },
            db_path=self.db_path,
        )

        rep = journal.generate_daily_observability_report(
            db_path=self.db_path,
            assumed_cost_pct=0.08,
            api_error_counts={"HTTP_429": 2, "HTTP_5XX": 1},
        )
        self.assertEqual(rep["trade_count"], 2)
        self.assertAlmostEqual(rep["win_rate"], 50.0, places=2)
        # Gross PnL = +20.00 - 10.00 = +10.00
        # Total Fees + Funding = (1.20 + 0.40) + (1.00 + 0.20) = 2.80
        # Net PnL = +18.40 - 11.20 = +7.20
        self.assertAlmostEqual(rep["gross_pnl_usdt"], 10.0, places=3)
        self.assertAlmostEqual(rep["net_pnl_usdt"], 7.20, places=3)
        self.assertAlmostEqual(rep["total_fee_usdt"], 2.20, places=3)
        self.assertAlmostEqual(rep["total_funding_usdt"], 0.60, places=3)
        self.assertGreater(rep["max_drawdown_usdt"], 0.0)
        self.assertTrue(rep["cost_drift_alert"], "Realized cost (~0.18%) >> assumed 0.08% must trigger cost_drift_alert")
        self.assertGreater(rep["cost_drift_pct"], 0.05)
        self.assertEqual(rep["api_error_total"], 3)

        msg = journal.format_daily_telegram_report(rep)
        self.assertIn("7.20", msg)
        self.assertIn("10.00", msg)
        self.assertIn("COST DRIFT", msg.upper())
        self.assertIn("HTTP_429", msg)

    def test_log_rotation_20mb_and_sqlite_backup_retention(self):
        """Verify rotate_log_files (>20MB, keep=3) and backup_state_and_journal (sqlite3.backup + 7-day retention)."""
        log_dir = os.path.join(self.tmp_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)

        small_log = os.path.join(log_dir, "server.log")
        big_log = os.path.join(log_dir, "bot.log")
        with open(small_log, "wb") as f:
            f.write(b"x" * 1024)

        # Pre-seed .1, .2, .3 backups to verify shift & cap at keep=3
        for idx in (1, 2, 3):
            with open(f"{big_log}.{idx}", "w", encoding="utf-8") as f:
                f.write(f"old_generation_{idx}")

        # Write slightly over 20MB to bot.log
        threshold_20mb = 20 * 1024 * 1024
        with open(big_log, "wb") as f:
            f.seek(threshold_20mb + 128)
            f.write(b"\n")

        rotated = journal.rotate_log_files(log_dir=log_dir, max_bytes=threshold_20mb, keep=3)
        self.assertIn(os.path.abspath(big_log), [os.path.abspath(p) for p in rotated])
        self.assertEqual(os.path.getsize(small_log), 1024, "Small log below 20MB must not be rotated")
        self.assertLess(os.path.getsize(big_log), 1024, "Active bot.log must be truncated after rotation")
        self.assertTrue(os.path.exists(f"{big_log}.1"))
        self.assertTrue(os.path.exists(f"{big_log}.2"))
        self.assertTrue(os.path.exists(f"{big_log}.3"))
        self.assertFalse(os.path.exists(f"{big_log}.4"), "Must keep at most 3 rotated backups")
        with open(f"{big_log}.2", "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "old_generation_1")
        with open(f"{big_log}.3", "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "old_generation_2")

        # Seed a trade and critical state JSON files, plus stale >7d backup files
        journal.record_trade_open(
            {"trade_id": "TRD_BAK_1", "symbol": "BTCUSDT", "direction": "LONG", "entry_fill": 60000.0, "qty": 0.01},
            db_path=self.db_path,
        )
        state_json = os.path.join(self.tmp_dir, "active_positions.json")
        with open(state_json, "w", encoding="utf-8") as f:
            json.dump([{"id": "POS_1", "symbol": "BTC-USD"}], f)

        backups_dir = os.path.join(self.tmp_dir, "backups")
        os.makedirs(backups_dir, exist_ok=True)
        stale_db = os.path.join(backups_dir, "journal_20200101.db")
        with open(stale_db, "w", encoding="utf-8") as f:
            f.write("stale")
        old_ts = time.time() - (10 * 86400)
        os.utime(stale_db, (old_ts, old_ts))

        bak_res = journal.backup_state_and_journal(
            db_path=self.db_path,
            results_dir=self.tmp_dir,
            keep_days=7,
        )
        self.assertTrue(os.path.exists(bak_res["backup_db_path"]))
        self.assertFalse(os.path.exists(stale_db), "Backups older than keep_days=7 must be pruned")

        # Verify the SQLite backup is a valid queryable SQLite database containing TRD_BAK_1
        with sqlite3.connect(bak_res["backup_db_path"]) as bconn:
            row = bconn.execute("SELECT trade_id, symbol FROM trades WHERE trade_id = 'TRD_BAK_1'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[1], "BTCUSDT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
