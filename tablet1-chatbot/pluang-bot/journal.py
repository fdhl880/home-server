"""
PYROFUEL BOT - INSTITUTIONAL TRADE, DECISION & SHADOW JOURNAL (SQLite WAL v3)
Task T1.1: Pencatatan komprehensif seluruh keputusan AI (decisions), eksekusi live (trades),
dan akun bayangan (shadow_trades) berbasis fill nyata di SQLite mode WAL.
"""
import os
import sys
import math
import sqlite3
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BOT_DIR, "results", "pyrofuel_journal.db")


def get_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    target_path = db_path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path, timeout=20)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=OFF;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    with get_db(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS decisions (
            decision_id TEXT PRIMARY KEY,
            ts_ms INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            regime TEXT DEFAULT 'UNKNOWN',
            strategy_id TEXT DEFAULT 'NONE',
            direction TEXT DEFAULT 'NONE',
            decision TEXT NOT NULL,
            p_raw REAL DEFAULT 0.0,
            p_cal REAL DEFAULT 0.0,
            ev_r REAL DEFAULT 0.0,
            skip_reason TEXT DEFAULT '',
            ai_model_primary TEXT DEFAULT '',
            ai_model_auditor TEXT DEFAULT '',
            latency_ms INTEGER DEFAULT 0,
            tokens_used INTEGER DEFAULT 0,
            features_json TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS trades (
            trade_id TEXT PRIMARY KEY,
            decision_id TEXT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            regime TEXT DEFAULT 'UNKNOWN',
            strategy_id TEXT DEFAULT 'MANUAL',
            sizing_mode TEXT DEFAULT 'ALL_IN',
            leverage INTEGER DEFAULT 20,
            margin_usdt REAL DEFAULT 0.0,
            notional_usdt REAL DEFAULT 0.0,
            qty REAL DEFAULT 0.0,
            entry_plan REAL DEFAULT 0.0,
            sl_plan REAL DEFAULT 0.0,
            tp_plan REAL DEFAULT 0.0,
            entry_fill REAL DEFAULT 0.0,
            exit_fill REAL,
            fee_usdt REAL DEFAULT 0.0,
            funding_usdt REAL DEFAULT 0.0,
            net_pnl_usdt REAL DEFAULT 0.0,
            r_multiple_net REAL,
            mae_pct REAL DEFAULT 0.0,
            mfe_pct REAL DEFAULT 0.0,
            holding_sec INTEGER DEFAULT 0,
            close_reason TEXT,
            opened_at INTEGER NOT NULL,
            closed_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS shadow_trades (
            shadow_id TEXT PRIMARY KEY,
            decision_id TEXT,
            symbol TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            regime TEXT DEFAULT 'UNKNOWN',
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            sl_price REAL NOT NULL,
            tp1_price REAL NOT NULL,
            tp2_price REAL NOT NULL,
            sl_distance_pct REAL NOT NULL,
            rrr_net REAL DEFAULT 1.8,
            vertical_barrier_bars INTEGER DEFAULT 16,
            sniper_mode INTEGER DEFAULT 1,
            status TEXT DEFAULT 'OPEN',
            outcome TEXT,
            exit_price REAL,
            r_multiple_net REAL,
            tp1_hit INTEGER DEFAULT 0,
            current_sl_price REAL,
            bars_elapsed INTEGER DEFAULT 0,
            p_raw REAL DEFAULT 0.5,
            p_cal REAL DEFAULT 0.5,
            ai_decision TEXT DEFAULT 'SKIP',
            features_json TEXT DEFAULT '{}',
            opened_at INTEGER NOT NULL,
            closed_at INTEGER
        );

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

        CREATE INDEX IF NOT EXISTS idx_decisions_symbol_ts ON decisions(symbol, ts_ms);
        CREATE INDEX IF NOT EXISTS idx_decisions_strat_regime ON decisions(strategy_id, regime);
        CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
        CREATE INDEX IF NOT EXISTS idx_trades_strat_regime ON trades(strategy_id, regime);
        CREATE INDEX IF NOT EXISTS idx_trades_closed_at ON trades(closed_at);
        CREATE INDEX IF NOT EXISTS idx_shadow_status ON shadow_trades(status);
        CREATE INDEX IF NOT EXISTS idx_shadow_strat_regime ON shadow_trades(strategy_id, regime);
        """)


init_db()


def _parse_ts_ms(val: Any) -> int:
    if val is None:
        return int(time.time() * 1000)
    if isinstance(val, (int, float)):
        return int(val * 1000) if val < 1e11 else int(val)
    if isinstance(val, str):
        try:
            return int(float(val))
        except ValueError:
            try:
                dt = datetime.fromisoformat(val.replace(" UTC", "+00:00"))
                return int(dt.timestamp() * 1000)
            except Exception:
                return int(time.time() * 1000)
    return int(time.time() * 1000)


def record_decision(decision_data: Dict[str, Any], db_path: Optional[str] = None) -> str:
    """
    Record an AI / quantitative meta-labeling decision into `decisions` table.
    """
    init_db(db_path)
    ts_ms = _parse_ts_ms(decision_data.get("ts_ms") or decision_data.get("timestamp"))
    symbol = str(decision_data.get("symbol", "UNKNOWN"))
    decision_id = str(
        decision_data.get("decision_id")
        or decision_data.get("id")
        or f"DEC_{symbol}_{ts_ms}_{int(time.time_ns() % 100000)}"
    )
    features = decision_data.get("features", decision_data.get("features_json", {}))
    if isinstance(features, (dict, list)):
        features_str = json.dumps(features, ensure_ascii=False)
    else:
        features_str = str(features or "{}")

    with get_db(db_path) as conn:
        conn.execute("""
        INSERT OR REPLACE INTO decisions (
            decision_id, ts_ms, symbol, regime, strategy_id, direction,
            decision, p_raw, p_cal, ev_r, skip_reason,
            ai_model_primary, ai_model_auditor, latency_ms, tokens_used, features_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            decision_id,
            ts_ms,
            symbol,
            str(decision_data.get("regime", "UNKNOWN")),
            str(decision_data.get("strategy_id", decision_data.get("setup", "NONE"))),
            str(decision_data.get("direction", "NONE")),
            str(decision_data.get("decision", "SKIP")),
            float(decision_data.get("p_raw", decision_data.get("ai_prob", 0.0)) or 0.0),
            float(decision_data.get("p_cal", decision_data.get("calibrated_prob", decision_data.get("p_raw", 0.0))) or 0.0),
            float(decision_data.get("ev_r", 0.0) or 0.0),
            str(decision_data.get("skip_reason", decision_data.get("reject_reason", ""))),
            str(decision_data.get("ai_model_primary", decision_data.get("model", ""))),
            str(decision_data.get("ai_model_auditor", "")),
            int(decision_data.get("latency_ms", 0) or 0),
            int(decision_data.get("tokens_used", 0) or 0),
            features_str,
        ))
    return decision_id


def record_trade_open(trade_data: Dict[str, Any], db_path: Optional[str] = None) -> str:
    """
    Record a newly opened position in the `trades` table.
    """
    init_db(db_path)
    opened_at = _parse_ts_ms(trade_data.get("opened_at") or trade_data.get("open_ts"))
    symbol = str(trade_data.get("symbol", "UNKNOWN"))
    trade_id = str(
        trade_data.get("trade_id")
        or trade_data.get("id")
        or f"TRD_{symbol}_{opened_at}_{int(time.time_ns() % 100000)}"
    )
    decision_id = trade_data.get("decision_id") or trade_data.get("signal_id")
    leverage = int(trade_data.get("leverage", 20) or 20)
    margin_usdt = float(trade_data.get("margin_usdt", trade_data.get("margin_usd", 0.0)) or 0.0)
    entry_fill = float(trade_data.get("entry_fill", trade_data.get("entry_plan", 0.0)) or 0.0)
    qty = float(trade_data.get("qty", 0.0) or 0.0)
    notional_usdt = float(
        trade_data.get("notional_usdt")
        or (qty * entry_fill if qty > 0 and entry_fill > 0 else margin_usdt * leverage)
    )

    regime = str(trade_data.get("regime", "UNKNOWN"))
    strategy_id = str(trade_data.get("strategy_id", "MANUAL"))

    with get_db(db_path) as conn:
        if decision_id and (regime == "UNKNOWN" or strategy_id == "MANUAL"):
            dec_row = conn.execute(
                "SELECT regime, strategy_id, features_json FROM decisions WHERE decision_id = ?",
                (decision_id,)
            ).fetchone()
            if dec_row:
                if regime == "UNKNOWN" and dec_row["regime"]:
                    regime = dec_row["regime"]
                if strategy_id == "MANUAL" and dec_row["strategy_id"]:
                    strategy_id = dec_row["strategy_id"]

        conn.execute("""
        INSERT OR REPLACE INTO trades (
            trade_id, decision_id, symbol, direction, regime, strategy_id,
            sizing_mode, leverage, margin_usdt, notional_usdt, qty,
            entry_plan, sl_plan, tp_plan, entry_fill, fee_usdt, funding_usdt, opened_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id,
            decision_id,
            symbol,
            str(trade_data.get("direction", "LONG")),
            regime,
            strategy_id,
            str(trade_data.get("sizing_mode", "ALL_IN")),
            leverage,
            margin_usdt,
            notional_usdt,
            qty,
            float(trade_data.get("entry_plan", entry_fill) or entry_fill),
            float(trade_data.get("sl_plan", 0.0) or 0.0),
            float(trade_data.get("tp_plan", 0.0) or 0.0),
            entry_fill,
            float(trade_data.get("fee_usdt", trade_data.get("fee_usd", 0.0)) or 0.0),
            float(trade_data.get("funding_usdt", 0.0) or 0.0),
            opened_at,
        ))
    return trade_id


def record_trade_close(
    trade_id: str,
    close_data: Dict[str, Any],
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Update a closed position with real fill price, fees, funding, holding duration,
    and net R-multiple.
    """
    init_db(db_path)
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,)).fetchone()
        if not row:
            return None

        entry_px = float(row["entry_fill"] or row["entry_plan"] or 0.0)
        exit_px = float(close_data.get("exit_fill", entry_px) or entry_px)
        direction = str(row["direction"] or "LONG").upper()
        qty = float(row["qty"] or 0.0)
        notional = float(row["notional_usdt"] or (qty * entry_px) or 0.0)
        opened_at = int(row["opened_at"] or int(time.time() * 1000))
        closed_at = _parse_ts_ms(close_data.get("closed_at") or close_data.get("close_ts"))
        holding_sec = max(0, int(close_data.get("holding_sec", (closed_at - opened_at) // 1000)))

        fee_usdt = float(close_data.get("fee_usdt", close_data.get("fee_usd", row["fee_usdt"] or 0.0)) or 0.0)
        funding_usdt = float(close_data.get("funding_usdt", row["funding_usdt"] or 0.0) or 0.0)

        # Compute gross PnL if not explicitly given
        if "net_pnl_usdt" in close_data and close_data["net_pnl_usdt"] is not None:
            net_pnl_usdt = float(close_data["net_pnl_usdt"])
        elif "pnl_usd" in close_data and close_data["pnl_usd"] is not None:
            # Legacy compatibility: pnl_usd was gross, fee_usd subtracted
            net_pnl_usdt = float(close_data["pnl_usd"]) - fee_usdt - funding_usdt
        else:
            if entry_px > 0 and notional > 0:
                raw_ret = ((exit_px - entry_px) / entry_px) if direction == "LONG" else ((entry_px - exit_px) / entry_px)
                gross_pnl = notional * raw_ret
                net_pnl_usdt = gross_pnl - fee_usdt - funding_usdt
            else:
                net_pnl_usdt = 0.0

        # Calculate r_multiple_net
        if "r_multiple_net" in close_data and close_data["r_multiple_net"] is not None:
            r_multiple_net = float(close_data["r_multiple_net"])
        else:
            sl_plan = float(row["sl_plan"] or 0.0)
            if sl_plan <= 0 and row["decision_id"]:
                sig = conn.execute("SELECT sl FROM signals WHERE id = ?", (row["decision_id"],)).fetchone()
                if sig and sig["sl"]:
                    sl_plan = float(sig["sl"])

            if entry_px > 0 and sl_plan > 0 and abs(entry_px - sl_plan) > 1e-12:
                sl_dist_pct = abs(entry_px - sl_plan) / entry_px
                risk_usdt = notional * sl_dist_pct if notional > 0 else abs(entry_px - sl_plan)
                if risk_usdt > 0 and notional > 0:
                    r_multiple_net = net_pnl_usdt / risk_usdt
                else:
                    gain_per_unit = (exit_px - entry_px) if direction == "LONG" else (entry_px - exit_px)
                    r_multiple_net = gain_per_unit / abs(entry_px - sl_plan)
            else:
                # Default 1.0% SL risk unit fallback if sl_plan was not set
                default_risk = max(notional * 0.01, 1e-6)
                r_multiple_net = net_pnl_usdt / default_risk if notional > 0 else 0.0

        mae_pct = float(close_data.get("mae_pct", close_data.get("mae", row["mae_pct"] or 0.0)) or 0.0)
        mfe_pct = float(close_data.get("mfe_pct", close_data.get("mfe", row["mfe_pct"] or 0.0)) or 0.0)
        close_reason = str(close_data.get("close_reason", close_data.get("exit_reason", "CLOSED")))

        conn.execute("""
        UPDATE trades SET
            exit_fill = ?,
            fee_usdt = ?,
            funding_usdt = ?,
            net_pnl_usdt = ?,
            r_multiple_net = ?,
            mae_pct = ?,
            mfe_pct = ?,
            holding_sec = ?,
            close_reason = ?,
            closed_at = ?
        WHERE trade_id = ?
        """, (
            exit_px,
            round(fee_usdt, 6),
            round(funding_usdt, 6),
            round(net_pnl_usdt, 6),
            round(r_multiple_net, 4),
            round(mae_pct, 4),
            round(mfe_pct, 4),
            holding_sec,
            close_reason,
            closed_at,
            trade_id,
        ))

        return {
            "trade_id": trade_id,
            "net_pnl_usdt": round(net_pnl_usdt, 6),
            "r_multiple_net": round(r_multiple_net, 4),
            "holding_sec": holding_sec,
            "close_reason": close_reason,
        }


def _compute_ci95(values: List[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    mean_val = sum(values) / n
    if n < 2:
        return (mean_val, mean_val)
    var_val = sum((x - mean_val) ** 2 for x in values) / (n - 1)
    se = math.sqrt(var_val / n)
    margin = 1.96 * se
    return (round(mean_val - margin, 4), round(mean_val + margin, 4))


def get_empirical_base_rate(
    strategy_id: str,
    regime: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Query empirical out-of-sample / live + shadow base rate for (strategy_id, regime).
    Used by AI Meta-Labeling (T5.1) and ProbabilityCalibrator (T5.2).
    """
    init_db(db_path)
    r_values: List[float] = []

    with get_db(db_path) as conn:
        if regime and regime != "ANY":
            live_rows = conn.execute(
                "SELECT r_multiple_net FROM trades WHERE strategy_id = ? AND regime = ? AND closed_at IS NOT NULL AND r_multiple_net IS NOT NULL",
                (strategy_id, regime)
            ).fetchall()
            shadow_rows = conn.execute(
                "SELECT r_multiple_net FROM shadow_trades WHERE strategy_id = ? AND regime = ? AND status = 'CLOSED' AND r_multiple_net IS NOT NULL",
                (strategy_id, regime)
            ).fetchall()
        else:
            live_rows = conn.execute(
                "SELECT r_multiple_net FROM trades WHERE strategy_id = ? AND closed_at IS NOT NULL AND r_multiple_net IS NOT NULL",
                (strategy_id,)
            ).fetchall()
            shadow_rows = conn.execute(
                "SELECT r_multiple_net FROM shadow_trades WHERE strategy_id = ? AND status = 'CLOSED' AND r_multiple_net IS NOT NULL",
                (strategy_id,)
            ).fetchall()

        r_values.extend(float(r["r_multiple_net"]) for r in live_rows)
        r_values.extend(float(r["r_multiple_net"]) for r in shadow_rows)

    n = len(r_values)
    if n == 0:
        return {
            "strategy_id": strategy_id,
            "regime": regime or "ANY",
            "historical_n": 0,
            "win_rate": 0.50,
            "historical_win_rate_pct": 50.0,
            "historical_expectancy_r": 0.15,
            "breakeven_win_rate_pct": 38.8,
            "profit_factor": 1.25,
            "ci95_low": 0.0,
            "ci95_high": 0.30,
        }

    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r <= 0]
    win_rate = len(wins) / n
    exp_r = sum(r_values) / n
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss > 1e-9 else (99.0 if gross_win > 0 else 0.0)
    ci_low, ci_high = _compute_ci95(r_values)

    avg_win_r = (gross_win / len(wins)) if wins else 1.6
    be_wr = 1.0 / (1.0 + avg_win_r) if avg_win_r > 0 else 0.388

    return {
        "strategy_id": strategy_id,
        "regime": regime or "ANY",
        "historical_n": n,
        "win_rate": round(win_rate, 4),
        "historical_win_rate_pct": round(win_rate * 100.0, 2),
        "historical_expectancy_r": round(exp_r, 4),
        "breakeven_win_rate_pct": round(be_wr * 100.0, 2),
        "profit_factor": round(pf, 3),
        "ci95_low": ci_low,
        "ci95_high": ci_high,
    }


def get_recent_feature_vectors(
    regime: Optional[str] = None,
    limit: int = 5000,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve historical resolved feature vectors and outcomes (R_net, win)
    for k-NN Episodic Market Memory (T5.4) and Hybrid Ensemble (T5.5).
    """
    init_db(db_path)
    results: List[Dict[str, Any]] = []

    with get_db(db_path) as conn:
        # 1. Resolved live trades joined with decisions
        if regime:
            live_q = """
            SELECT t.trade_id AS id, t.symbol, t.strategy_id, t.regime, t.direction,
                   t.r_multiple_net, t.opened_at AS ts_ms, d.features_json, d.p_raw, d.p_cal
            FROM trades t
            LEFT JOIN decisions d ON t.decision_id = d.decision_id
            WHERE t.closed_at IS NOT NULL AND t.r_multiple_net IS NOT NULL AND t.regime = ?
            ORDER BY t.closed_at DESC LIMIT ?
            """
            live_rows = conn.execute(live_q, (regime, limit)).fetchall()
        else:
            live_q = """
            SELECT t.trade_id AS id, t.symbol, t.strategy_id, t.regime, t.direction,
                   t.r_multiple_net, t.opened_at AS ts_ms, d.features_json, d.p_raw, d.p_cal
            FROM trades t
            LEFT JOIN decisions d ON t.decision_id = d.decision_id
            WHERE t.closed_at IS NOT NULL AND t.r_multiple_net IS NOT NULL
            ORDER BY t.closed_at DESC LIMIT ?
            """
            live_rows = conn.execute(live_q, (limit,)).fetchall()

        for r in live_rows:
            try:
                f_dict = json.loads(r["features_json"] or "{}")
            except Exception:
                f_dict = {}
            r_net = float(r["r_multiple_net"])
            results.append({
                "id": r["id"],
                "source": "LIVE",
                "symbol": r["symbol"],
                "strategy_id": r["strategy_id"],
                "regime": r["regime"],
                "direction": r["direction"],
                "r_multiple_net": r_net,
                "win": 1 if r_net > 0 else 0,
                "p_raw": float(r["p_raw"] or 0.5),
                "p_cal": float(r["p_cal"] or 0.5),
                "features": f_dict,
                "ts_ms": int(r["ts_ms"] or 0),
            })

        # 2. Resolved shadow trades
        rem = max(0, limit - len(results))
        if rem > 0:
            if regime:
                sh_q = """
                SELECT shadow_id AS id, symbol, strategy_id, regime, direction,
                       r_multiple_net, opened_at AS ts_ms, features_json, p_raw, p_cal
                FROM shadow_trades
                WHERE status = 'CLOSED' AND r_multiple_net IS NOT NULL AND regime = ?
                ORDER BY closed_at DESC LIMIT ?
                """
                sh_rows = conn.execute(sh_q, (regime, rem)).fetchall()
            else:
                sh_q = """
                SELECT shadow_id AS id, symbol, strategy_id, regime, direction,
                       r_multiple_net, opened_at AS ts_ms, features_json, p_raw, p_cal
                FROM shadow_trades
                WHERE status = 'CLOSED' AND r_multiple_net IS NOT NULL
                ORDER BY closed_at DESC LIMIT ?
                """
                sh_rows = conn.execute(sh_q, (rem,)).fetchall()

            for r in sh_rows:
                try:
                    f_dict = json.loads(r["features_json"] or "{}")
                except Exception:
                    f_dict = {}
                r_net = float(r["r_multiple_net"])
                results.append({
                    "id": r["id"],
                    "source": "SHADOW",
                    "symbol": r["symbol"],
                    "strategy_id": r["strategy_id"],
                    "regime": r["regime"],
                    "direction": r["direction"],
                    "r_multiple_net": r_net,
                    "win": 1 if r_net > 0 else 0,
                    "p_raw": float(r["p_raw"] or 0.5),
                    "p_cal": float(r["p_cal"] or 0.5),
                    "features": f_dict,
                    "ts_ms": int(r["ts_ms"] or 0),
                })

    return results


def get_rolling_strategy_metrics(
    strategy_id: str,
    window: int = 15,
    include_shadow: bool = False,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compute rolling performance metrics for a given strategy over its last `window` trades.
    Used by Auto-Degradation Guard & Promotion Rule (T8.2).
    """
    init_db(db_path)
    r_values: List[float] = []

    with get_db(db_path) as conn:
        if not include_shadow:
            rows = conn.execute(
                """
                SELECT r_multiple_net FROM trades
                WHERE strategy_id = ? AND closed_at IS NOT NULL AND r_multiple_net IS NOT NULL
                ORDER BY closed_at DESC LIMIT ?
                """,
                (strategy_id, window)
            ).fetchall()
            r_values = [float(r["r_multiple_net"]) for r in rows]
        else:
            rows = conn.execute(
                """
                SELECT r_multiple_net FROM shadow_trades
                WHERE strategy_id = ? AND status = 'CLOSED' AND r_multiple_net IS NOT NULL
                ORDER BY closed_at DESC LIMIT ?
                """,
                (strategy_id, window)
            ).fetchall()
            r_values = [float(r["r_multiple_net"]) for r in rows]

    n = len(r_values)
    if n == 0:
        return {
            "strategy_id": strategy_id,
            "n": 0,
            "win_rate": 0.0,
            "profit_factor": 1.0,
            "expectancy_r": 0.0,
            "ci95_low": 0.0,
            "ci95_high": 0.0,
            "r_multiples": [],
        }

    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r <= 0]
    win_rate = len(wins) / n
    exp_r = sum(r_values) / n
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss > 1e-9 else (99.0 if gross_win > 0 else 0.0)
    ci_low, ci_high = _compute_ci95(r_values)

    return {
        "strategy_id": strategy_id,
        "n": n,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(pf, 4),
        "expectancy_r": round(exp_r, 4),
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "r_multiples": r_values,
    }


def generate_gate_report(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate comprehensive institutional journal & gate report including:
    n, Win-Rate, Profit Factor, E[R]_net +/- CI_95%, Max Drawdown, Brier Score,
    and per-(strategy, regime) breakdown.
    """
    init_db(db_path)
    with get_db(db_path) as conn:
        closed = conn.execute("""
            SELECT t.*, d.p_cal, d.p_raw
            FROM trades t
            LEFT JOIN decisions d ON t.decision_id = d.decision_id
            WHERE t.closed_at IS NOT NULL
            ORDER BY t.closed_at ASC
        """).fetchall()
        shadow_closed = conn.execute("""
            SELECT * FROM shadow_trades WHERE status = 'CLOSED' ORDER BY closed_at ASC
        """).fetchall()

    total_trades = len(closed)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy_r": 0.0,
            "ci95_low": 0.0,
            "ci95_high": 0.0,
            "max_drawdown_r": 0.0,
            "max_drawdown_usdt": 0.0,
            "brier_score": 0.0,
            "total_pnl_usd": 0.0,
            "shadow_trades_resolved": len(shadow_closed),
            "by_strategy_regime": {},
            "gate_passed": False,
            "reason": "Belum ada trade yang ditutup.",
        }

    r_values = [float(r["r_multiple_net"] or 0.0) for r in closed]
    pnl_values = [float(r["net_pnl_usdt"] or 0.0) for r in closed]
    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r <= 0]

    win_rate = round(len(wins) / total_trades * 100.0, 2)
    gross_win_r = sum(wins)
    gross_loss_r = abs(sum(losses))
    pf = round(gross_win_r / gross_loss_r, 3) if gross_loss_r > 1e-9 else (99.0 if gross_win_r > 0 else 0.0)
    expectancy_r = round(sum(r_values) / total_trades, 4)
    ci_low, ci_high = _compute_ci95(r_values)

    # Max Drawdown in R and USD
    cum_r = 0.0
    peak_r = 0.0
    max_dd_r = 0.0
    for rv in r_values:
        cum_r += rv
        if cum_r > peak_r:
            peak_r = cum_r
        dd = peak_r - cum_r
        if dd > max_dd_r:
            max_dd_r = dd

    cum_usd = 0.0
    peak_usd = 0.0
    max_dd_usd = 0.0
    for pv in pnl_values:
        cum_usd += pv
        if cum_usd > peak_usd:
            peak_usd = cum_usd
        dd_u = peak_usd - cum_usd
        if dd_u > max_dd_usd:
            max_dd_usd = dd_u

    # Brier Score
    brier_terms = []
    for r in closed:
        p = r["p_cal"] if r["p_cal"] is not None else r["p_raw"]
        if p is not None and float(p) > 0:
            p_val = float(p)
            if p_val > 1.0:
                p_val /= 100.0
            outcome = 1.0 if float(r["r_multiple_net"] or 0.0) > 0 else 0.0
            brier_terms.append((p_val - outcome) ** 2)
    brier_score = round(sum(brier_terms) / len(brier_terms), 4) if brier_terms else 0.25

    # Breakdown by (strategy_id, regime)
    breakdown: Dict[str, List[float]] = {}
    for r in closed:
        key = f"{r['strategy_id'] or 'MANUAL'}|{r['regime'] or 'UNKNOWN'}"
        breakdown.setdefault(key, []).append(float(r["r_multiple_net"] or 0.0))

    by_strat_regime = {}
    for key, r_list in breakdown.items():
        w_list = [x for x in r_list if x > 0]
        l_list = [x for x in r_list if x <= 0]
        gw = sum(w_list)
        gl = abs(sum(l_list))
        c_lo, c_hi = _compute_ci95(r_list)
        by_strat_regime[key] = {
            "n": len(r_list),
            "win_rate_pct": round(len(w_list) / len(r_list) * 100.0, 2),
            "profit_factor": round(gw / gl, 3) if gl > 1e-9 else (99.0 if gw > 0 else 0.0),
            "expectancy_r": round(sum(r_list) / len(r_list), 4),
            "ci95_r": [c_lo, c_hi],
        }

    total_pnl = round(sum(pnl_values), 4)
    gate_passed = bool(total_trades >= 20 and pf >= 1.2 and expectancy_r > 0 and ci_low > -0.05)

    return {
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "gross_profit_usd": round(sum(x for x in pnl_values if x > 0), 4),
        "gross_loss_usd": round(abs(sum(x for x in pnl_values if x <= 0)), 4),
        "profit_factor": pf,
        "expectancy_r": expectancy_r,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "max_drawdown_r": round(max_dd_r, 4),
        "max_drawdown_usdt": round(max_dd_usd, 4),
        "brier_score": brier_score,
        "total_pnl_usd": total_pnl,
        "shadow_trades_resolved": len(shadow_closed),
        "by_strategy_regime": by_strat_regime,
        "gate_passed": gate_passed,
    }


# ============================================================================
# Backward-Compatible Wrappers for Legacy Callers (auto_trader.py, pipeline.py)
# ============================================================================

def log_signal(signal_data: dict) -> str:
    """Legacy wrapper that records into both `signals` and `decisions`."""
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
    record_decision({
        "decision_id": sig_id,
        "symbol": signal_data.get("symbol", ""),
        "regime": signal_data.get("regime", "UNKNOWN"),
        "strategy_id": signal_data.get("setup", "N/A"),
        "direction": signal_data.get("direction", "NONE"),
        "decision": "TRADE" if signal_data.get("decision") in ("APPROVED", "TRADE") else "SKIP",
        "p_raw": signal_data.get("ai_prob", 0.0),
        "p_cal": signal_data.get("calibrated_prob", signal_data.get("ai_prob", 0.0)),
        "skip_reason": signal_data.get("reject_reason", ""),
        "ai_model_primary": signal_data.get("model", ""),
        "features": signal_data.get("features", {}),
    })
    return sig_id


def open_trade(trade_data: dict) -> str:
    """Legacy wrapper that delegates to `record_trade_open`."""
    return record_trade_open(trade_data)


def close_trade(trade_id: str, close_data: dict):
    """Legacy wrapper that delegates to `record_trade_close`."""
    return record_trade_close(trade_id, close_data)


def generate_report(gate_check: bool = False) -> dict:
    """Legacy wrapper that delegates to `generate_gate_report`."""
    return generate_gate_report()


if __name__ == "__main__":
    is_gate = "--gate" in sys.argv or "report" in sys.argv
    rep = generate_gate_report()
    print("=" * 68)
    print("  PYROFUEL v3 INSTITUTIONAL JOURNAL & GATE REPORT (SQLite WAL)")
    print("=" * 68)
    for k, v in rep.items():
        if k == "by_strategy_regime" and isinstance(v, dict):
            print("  by_strategy_regime  :")
            for sk, sv in v.items():
                print(f"    - {sk:28s}: n={sv['n']} | WR={sv['win_rate_pct']}% | PF={sv['profit_factor']} | E[R]={sv['expectancy_r']:+.3f}R (CI95: {sv['ci95_r']})")
        else:
            print(f"  {k:20s}: {v}")
    print("=" * 68)
