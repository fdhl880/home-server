"""
PYROFUEL BOT - TRADE & SIGNAL JOURNAL (SQLite WAL)
Pencatatan komprehensif seluruh sinyal pipeline & rekonsiliasi PnL nyata dari Binance Futures.
"""
import os
import sys
import sqlite3
import json
import time
from datetime import datetime, timezone

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BOT_DIR, "results", "journal.db")


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT DEFAULT '1h',
            direction TEXT NOT NULL,
            setup TEXT NOT NULL,
            ai_prob REAL,
            calibrated_prob REAL,
            entry REAL,
            sl REAL,
            tp REAL,
            rrr TEXT,
            features_json TEXT,
            provider TEXT,
            model TEXT,
            decision TEXT NOT NULL,
            reject_reason TEXT
        );

        CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            signal_id TEXT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            open_ts TEXT NOT NULL,
            close_ts TEXT,
            entry_fill REAL,
            exit_fill REAL,
            qty REAL,
            leverage INTEGER DEFAULT 20,
            margin_usd REAL,
            fee_usd REAL DEFAULT 0.0,
            pnl_usd REAL DEFAULT 0.0,
            pnl_pct_margin REAL DEFAULT 0.0,
            r_multiple REAL DEFAULT 0.0,
            exit_reason TEXT,
            mae REAL DEFAULT 0.0,
            mfe REAL DEFAULT 0.0,
            is_estimated INTEGER DEFAULT 0,
            FOREIGN KEY(signal_id) REFERENCES signals(id)
        );

        CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
        CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
        CREATE INDEX IF NOT EXISTS idx_trades_open_ts ON trades(open_ts);
        """)


init_db()


def log_signal(signal_data: dict) -> str:
    """Catat keputusan sinyal (APPROVED atau REJECTED)."""
    sig_id = signal_data.get("pipeline_id") or f"{signal_data.get('symbol')}_{int(time.time())}"
    with get_db() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO signals (
            id, ts, symbol, timeframe, direction, setup,
            ai_prob, calibrated_prob, entry, sl, tp, rrr,
            features_json, provider, model, decision, reject_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sig_id,
            signal_data.get("timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            signal_data.get("symbol", ""),
            signal_data.get("timeframe", "1h"),
            signal_data.get("direction", "NONE"),
            signal_data.get("setup", "N/A"),
            signal_data.get("ai_prob", 0.0),
            signal_data.get("calibrated_prob", signal_data.get("ai_prob", 0.0)),
            signal_data.get("entry", 0.0),
            signal_data.get("sl", 0.0),
            signal_data.get("tp", 0.0),
            str(signal_data.get("rrr", "")),
            json.dumps(signal_data.get("features", {}), ensure_ascii=False),
            signal_data.get("provider", ""),
            signal_data.get("model", ""),
            signal_data.get("decision", "REJECTED"),
            signal_data.get("reject_reason", "")
        ))
    return sig_id


def open_trade(trade_data: dict) -> str:
    """Catat posisi baru yang berhasil dieksekusi."""
    trade_id = trade_data.get("id") or f"T_{trade_data.get('symbol')}_{int(time.time())}"
    with get_db() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO trades (
            id, signal_id, symbol, direction, open_ts, entry_fill,
            qty, leverage, margin_usd, fee_usd
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id,
            trade_data.get("signal_id"),
            trade_data.get("symbol"),
            trade_data.get("direction"),
            trade_data.get("open_ts") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            float(trade_data.get("entry_fill", 0.0)),
            float(trade_data.get("qty", 0.0)),
            int(trade_data.get("leverage", 20)),
            float(trade_data.get("margin_usd", 0.0)),
            float(trade_data.get("fee_usd", 0.0))
        ))
    return trade_id


def close_trade(trade_id: str, close_data: dict):
    """Update posisi yang ditutup dengan fill riil dan perhitungan R-multiple."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not row:
            return

        entry_px = row["entry_fill"]
        exit_px = float(close_data.get("exit_fill", 0.0))
        direction = row["direction"]
        leverage = row["leverage"]
        margin = row["margin_usd"] or 1.0

        pnl_usd = float(close_data.get("pnl_usd", 0.0))
        fee_usd = float(close_data.get("fee_usd", row["fee_usd"] or 0.0))
        net_pnl = pnl_usd - fee_usd
        pnl_pct = (net_pnl / margin) * 100.0 if margin > 0 else 0.0

        # Hitung R-multiple jika ada SL di sinyal
        r_mult = 0.0
        sig = None
        if row["signal_id"]:
            sig = conn.execute("SELECT * FROM signals WHERE id = ?", (row["signal_id"],)).fetchone()
        if sig and sig["entry"] and sig["sl"] and abs(sig["entry"] - sig["sl"]) > 0:
            risk_per_unit = abs(sig["entry"] - sig["sl"])
            gain_per_unit = (exit_px - entry_px) if direction == "LONG" else (entry_px - exit_px)
            r_mult = round(gain_per_unit / risk_per_unit, 2)

        conn.execute("""
        UPDATE trades SET
            close_ts = ?,
            exit_fill = ?,
            pnl_usd = ?,
            fee_usd = ?,
            pnl_pct_margin = ?,
            r_multiple = ?,
            exit_reason = ?,
            is_estimated = ?
        WHERE id = ?
        """, (
            close_data.get("close_ts") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            exit_px,
            round(pnl_usd, 4),
            round(fee_usd, 4),
            round(pnl_pct, 2),
            r_mult,
            close_data.get("exit_reason", "CLOSED"),
            int(close_data.get("is_estimated", 0)),
            trade_id
        ))


def generate_report(gate_check: bool = False) -> dict:
    """Hitung metrik statistik performa perdagangan."""
    with get_db() as conn:
        closed = conn.execute("SELECT * FROM trades WHERE close_ts IS NOT NULL").fetchall()
        total_trades = len(closed)
        if total_trades == 0:
            rep = {
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "expectancy_r": 0.0,
                "total_pnl_usd": 0.0,
                "gate_passed": False,
                "reason": "Belum ada trade yang ditutup."
            }
            return rep

        wins = [r for r in closed if (r["pnl_usd"] - r["fee_usd"]) > 0]
        losses = [r for r in closed if (r["pnl_usd"] - r["fee_usd"]) <= 0]
        win_rate = round(len(wins) / total_trades * 100.0, 2)

        gross_profit = sum((r["pnl_usd"] - r["fee_usd"]) for r in wins)
        gross_loss = abs(sum((r["pnl_usd"] - r["fee_usd"]) for r in losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        r_values = [r["r_multiple"] for r in closed if r["r_multiple"] is not None]
        expectancy_r = round(sum(r_values) / len(r_values), 2) if r_values else 0.0
        total_pnl = round(sum((r["pnl_usd"] - r["fee_usd"]) for r in closed), 4)

        # Kriteria evaluasi gerbang (probation exit)
        gate_passed = (total_trades >= 20 and profit_factor >= 1.2 and expectancy_r > 0)

        rep = {
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "gross_profit_usd": round(gross_profit, 4),
            "gross_loss_usd": round(gross_loss, 4),
            "profit_factor": profit_factor,
            "expectancy_r": expectancy_r,
            "total_pnl_usd": total_pnl,
            "gate_passed": gate_passed
        }
        return rep


if __name__ == "__main__":
    is_gate = "--gate" in sys.argv
    rep = generate_report(gate_check=is_gate)
    print("=" * 60)
    print("  PYROFUEL JOURNAL REPORT")
    print("=" * 60)
    for k, v in rep.items():
        print(f"  {k:20s}: {v}")
    print("=" * 60)
