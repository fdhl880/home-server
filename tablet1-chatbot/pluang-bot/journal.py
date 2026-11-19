"""
PYROFUEL BOT - INSTITUTIONAL TRADE, DECISION & SHADOW JOURNAL (SQLite WAL v3)
Task T1.1: Pencatatan komprehensif seluruh keputusan AI (decisions), eksekusi live (trades),
dan akun bayangan (shadow_trades) berbasis fill nyata di SQLite mode WAL.
"""
import contextlib
import os
import re
import shutil
import sys
import math
import sqlite3
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BOT_DIR, "results", "pyrofuel_journal.db")
DEFAULT_ASSUMED_COST_PCT = 0.08


def _get_tca_jsonl_path(db_path: Optional[str] = None) -> str:
    target_db = os.path.abspath(db_path or DB_PATH)
    results_dir = os.path.dirname(target_db)
    os.makedirs(results_dir, exist_ok=True)
    return os.path.join(results_dir, "tca_metrics.jsonl")


def _append_tca_jsonl(payload: Dict[str, Any], db_path: Optional[str] = None) -> Optional[str]:
    try:
        jsonl_path = _get_tca_jsonl_path(db_path)
        with open(jsonl_path, "a", encoding="utf-8") as jf:
            jf.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return jsonl_path
    except Exception:
        return None


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

        CREATE TABLE IF NOT EXISTS tca_executions (
            exec_id TEXT PRIMARY KEY,
            trade_id TEXT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            routing_used TEXT NOT NULL,
            arrival_price REAL NOT NULL,
            fill_price REAL NOT NULL,
            arrival_slippage_bps REAL NOT NULL DEFAULT 0.0,
            fee_usdt REAL NOT NULL DEFAULT 0.0,
            margin_usdt REAL NOT NULL DEFAULT 0.0,
            fee_drag_roe_pct REAL NOT NULL DEFAULT 0.0,
            impact_bps_est REAL NOT NULL DEFAULT 0.0,
            markout_1m_bps REAL,
            markout_5m_bps REAL,
            markout_close_bps REAL,
            ts_ms INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_decisions_symbol_ts ON decisions(symbol, ts_ms);
        CREATE INDEX IF NOT EXISTS idx_decisions_strat_regime ON decisions(strategy_id, regime);
        CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
        CREATE INDEX IF NOT EXISTS idx_trades_strat_regime ON trades(strategy_id, regime);
        CREATE INDEX IF NOT EXISTS idx_trades_closed_at ON trades(closed_at);
        CREATE INDEX IF NOT EXISTS idx_shadow_status ON shadow_trades(status);
        CREATE INDEX IF NOT EXISTS idx_shadow_strat_regime ON shadow_trades(strategy_id, regime);
        CREATE INDEX IF NOT EXISTS idx_tca_symbol_ts ON tca_executions(symbol, ts_ms);
        CREATE INDEX IF NOT EXISTS idx_tca_trade_id ON tca_executions(trade_id);
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

        tca_row = conn.execute(
            "SELECT arrival_slippage_bps FROM tca_executions WHERE trade_id = ? ORDER BY ts_ms DESC LIMIT 1",
            (trade_id,),
        ).fetchone()
        slip_bps = float(
            close_data.get(
                "arrival_slippage_bps",
                tca_row["arrival_slippage_bps"] if tca_row and tca_row["arrival_slippage_bps"] is not None else 0.0,
            )
            or 0.0
        )
        eff_notional = notional if notional > 0 else max(float(row["margin_usdt"] or 0.0) * float(row["leverage"] or 20), 0.0)
        if "realized_cost_pct" in close_data and close_data["realized_cost_pct"] is not None:
            realized_cost_pct = float(close_data["realized_cost_pct"])
        else:
            fee_funding_pct = ((fee_usdt + funding_usdt) / eff_notional * 100.0) if eff_notional > 0 else 0.0
            slip_pct = max(0.0, slip_bps) / 100.0
            realized_cost_pct = fee_funding_pct + slip_pct

        assumed_cost_pct = float(close_data.get("assumed_cost_pct", DEFAULT_ASSUMED_COST_PCT) or DEFAULT_ASSUMED_COST_PCT)
        cost_drift_pct = realized_cost_pct - assumed_cost_pct
        gross_pnl_usdt = net_pnl_usdt + fee_usdt + funding_usdt

        tca_line = {
            "event_type": "TRADE_CLOSE",
            "trade_id": trade_id,
            "symbol": str(row["symbol"] or "UNKNOWN"),
            "direction": direction,
            "regime": str(row["regime"] or "UNKNOWN"),
            "strategy_id": str(row["strategy_id"] or "MANUAL"),
            "arrival_slippage_bps": round(slip_bps, 3),
            "fee_usdt": round(fee_usdt, 6),
            "funding_usdt": round(funding_usdt, 6),
            "gross_pnl_usdt": round(gross_pnl_usdt, 6),
            "net_pnl_usdt": round(net_pnl_usdt, 6),
            "r_multiple_net": round(r_multiple_net, 4),
            "realized_cost_pct": round(realized_cost_pct, 5),
            "assumed_cost_pct": round(assumed_cost_pct, 5),
            "cost_drift_pct": round(cost_drift_pct, 5),
            "ts_ms": closed_at,
        }
        _append_tca_jsonl(tca_line, db_path=db_path)

        return {
            "trade_id": trade_id,
            "gross_pnl_usdt": round(gross_pnl_usdt, 6),
            "fee_usdt": round(fee_usdt, 6),
            "funding_usdt": round(funding_usdt, 6),
            "net_pnl_usdt": round(net_pnl_usdt, 6),
            "r_multiple_net": round(r_multiple_net, 4),
            "realized_cost_pct": round(realized_cost_pct, 5),
            "assumed_cost_pct": round(assumed_cost_pct, 5),
            "cost_drift_pct": round(cost_drift_pct, 5),
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


def _signed_bps_move(direction: str, ref_price: float, cur_price: float) -> float:
    """Compute signed price move in bps relative to trade direction (+ = favorable)."""
    ref = float(ref_price or 0.0)
    cur = float(cur_price or 0.0)
    if ref <= 0 or cur <= 0:
        return 0.0
    sign = 1.0 if str(direction).upper() == "LONG" else -1.0
    return round(sign * ((cur - ref) / ref) * 10000.0, 3)


def record_tca_execution(tca_data: dict, db_path: Optional[str] = None) -> str:
    """Record execution arrival slippage, routing tier, fee drag, and impact estimate."""
    init_db(db_path)
    ts_ms = int(tca_data.get("ts_ms") or time.time() * 1000)
    sym = str(tca_data.get("symbol", "")).upper().strip()
    exec_id = str(tca_data.get("exec_id") or f"TCA_{sym}_{ts_ms}")
    direction = str(tca_data.get("direction", "LONG")).upper().strip()
    arrival_px = float(tca_data.get("arrival_price") or 0.0)
    fill_px = float(tca_data.get("fill_price") or arrival_px or 0.0)
    slip_bps = tca_data.get("arrival_slippage_bps")
    if slip_bps is None:
        if arrival_px > 0 and fill_px > 0:
            sign = 1.0 if direction == "LONG" else -1.0
            slip_bps = sign * ((fill_px - arrival_px) / arrival_px) * 10000.0
        else:
            slip_bps = 0.0
    fee_usdt = float(tca_data.get("fee_usdt") or 0.0)
    margin_usdt = float(tca_data.get("margin_usdt") or 0.0)
    fee_drag_roe = float(tca_data.get("fee_drag_roe_pct") or ((fee_usdt / margin_usdt) * 100.0 if margin_usdt > 0 else 0.0))

    with get_db(db_path) as conn:
        conn.execute("""
        INSERT OR REPLACE INTO tca_executions (
            exec_id, trade_id, symbol, direction, routing_used,
            arrival_price, fill_price, arrival_slippage_bps,
            fee_usdt, margin_usdt, fee_drag_roe_pct, impact_bps_est,
            markout_1m_bps, markout_5m_bps, markout_close_bps, ts_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            exec_id,
            tca_data.get("trade_id"),
            sym,
            direction,
            str(tca_data.get("routing_used", "UNKNOWN")),
            arrival_px,
            fill_px,
            round(float(slip_bps), 3),
            round(fee_usdt, 6),
            round(margin_usdt, 4),
            round(fee_drag_roe, 4),
            round(float(tca_data.get("impact_bps_est") or 0.0), 3),
            tca_data.get("markout_1m_bps"),
            tca_data.get("markout_5m_bps"),
            tca_data.get("markout_close_bps"),
            ts_ms,
        ))
        tr_row = None
        if tca_data.get("trade_id"):
            tr_row = conn.execute(
                "SELECT regime, strategy_id, notional_usdt, funding_usdt, net_pnl_usdt, r_multiple_net, leverage FROM trades WHERE trade_id = ?",
                (tca_data.get("trade_id"),),
            ).fetchone()

    regime = str(tca_data.get("regime") or (tr_row["regime"] if tr_row and tr_row["regime"] else "UNKNOWN"))
    strategy_id = str(tca_data.get("strategy_id") or (tr_row["strategy_id"] if tr_row and tr_row["strategy_id"] else "MANUAL"))
    funding_usdt = float(tca_data.get("funding_usdt", tr_row["funding_usdt"] if tr_row and tr_row["funding_usdt"] is not None else 0.0) or 0.0)
    net_pnl_usdt = float(tca_data.get("net_pnl_usdt", tr_row["net_pnl_usdt"] if tr_row and tr_row["net_pnl_usdt"] is not None else 0.0) or 0.0)
    r_multiple_net = float(tca_data.get("r_multiple_net", tr_row["r_multiple_net"] if tr_row and tr_row["r_multiple_net"] is not None else 0.0) or 0.0)
    notional_usdt = float(
        tca_data.get("notional_usdt")
        or (tr_row["notional_usdt"] if tr_row and tr_row["notional_usdt"] else (margin_usdt * float(tr_row["leverage"] if tr_row and tr_row["leverage"] else 20.0)))
        or 0.0
    )
    fee_funding_pct = ((fee_usdt + funding_usdt) / notional_usdt * 100.0) if notional_usdt > 0 else 0.0
    realized_cost_pct = float(tca_data.get("realized_cost_pct") or (fee_funding_pct + max(0.0, float(slip_bps)) / 100.0))
    assumed_cost_pct = float(tca_data.get("assumed_cost_pct", DEFAULT_ASSUMED_COST_PCT) or DEFAULT_ASSUMED_COST_PCT)
    cost_drift_pct = realized_cost_pct - assumed_cost_pct

    _append_tca_jsonl(
        {
            "event_type": "TCA_EXECUTION",
            "exec_id": exec_id,
            "trade_id": tca_data.get("trade_id"),
            "symbol": sym,
            "direction": direction,
            "regime": regime,
            "strategy_id": strategy_id,
            "routing_used": str(tca_data.get("routing_used", "UNKNOWN")),
            "arrival_slippage_bps": round(float(slip_bps), 3),
            "fee_usdt": round(fee_usdt, 6),
            "funding_usdt": round(funding_usdt, 6),
            "net_pnl_usdt": round(net_pnl_usdt, 6),
            "r_multiple_net": round(r_multiple_net, 4),
            "realized_cost_pct": round(realized_cost_pct, 5),
            "assumed_cost_pct": round(assumed_cost_pct, 5),
            "cost_drift_pct": round(cost_drift_pct, 5),
            "ts_ms": ts_ms,
        },
        db_path=db_path,
    )
    return exec_id


def update_tca_markout(trade_id_or_exec_id: str, horizon: str, price: float, db_path: Optional[str] = None) -> bool:
    """Update markout_1m_bps, markout_5m_bps, or markout_close_bps from fill price."""
    col_map = {
        "1m": "markout_1m_bps",
        "5m": "markout_5m_bps",
        "close": "markout_close_bps",
    }
    col = col_map.get(str(horizon).lower().strip())
    if not col or not trade_id_or_exec_id or float(price or 0.0) <= 0:
        return False
    init_db(db_path)
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT exec_id, direction, fill_price FROM tca_executions WHERE exec_id = ? OR trade_id = ? ORDER BY ts_ms DESC LIMIT 1",
            (trade_id_or_exec_id, trade_id_or_exec_id),
        ).fetchone()
        if not row:
            return False
        bps = _signed_bps_move(row["direction"], row["fill_price"], price)
        conn.execute(f"UPDATE tca_executions SET {col} = ? WHERE exec_id = ?", (bps, row["exec_id"]))
    return True


def get_tca_summary(limit: int = 50, db_path: Optional[str] = None) -> dict:
    """Summarize execution quality (arrival slippage, maker fill share, fee drag, markouts) for BTCA <GO>."""
    lim = max(1, min(500, int(limit)))
    init_db(db_path)
    with get_db(db_path) as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM tca_executions ORDER BY ts_ms DESC LIMIT ?", (lim,)
        ).fetchall()]

    n = len(rows)
    if n == 0:
        return {
            "count": 0,
            "avg_arrival_slippage_bps": 0.0,
            "p95_arrival_slippage_bps": 0.0,
            "maker_fill_rate_pct": 0.0,
            "avg_fee_drag_roe_pct": 0.0,
            "avg_impact_bps": 0.0,
            "avg_markout_1m_bps": None,
            "avg_markout_5m_bps": None,
            "avg_markout_close_bps": None,
            "by_routing": {},
            "recent": [],
        }

    slips = sorted(float(r["arrival_slippage_bps"] or 0.0) for r in rows)
    maker_count = sum(1 for r in rows if any(k in str(r.get("routing_used", "")).upper() for k in ("MAKER", "GTX", "QUEUE", "PRICEMATCH")))
    m1 = [float(r["markout_1m_bps"]) for r in rows if r.get("markout_1m_bps") is not None]
    m5 = [float(r["markout_5m_bps"]) for r in rows if r.get("markout_5m_bps") is not None]
    mc = [float(r["markout_close_bps"]) for r in rows if r.get("markout_close_bps") is not None]

    by_routing = {}
    for r in rows:
        rt = str(r.get("routing_used") or "UNKNOWN")
        bucket = by_routing.setdefault(rt, {"n": 0, "slips": [], "fees": []})
        bucket["n"] += 1
        bucket["slips"].append(float(r.get("arrival_slippage_bps") or 0.0))
        bucket["fees"].append(float(r.get("fee_drag_roe_pct") or 0.0))
    by_routing_out = {
        k: {
            "n": v["n"],
            "avg_slip_bps": round(sum(v["slips"]) / v["n"], 3),
            "avg_fee_drag_roe_pct": round(sum(v["fees"]) / v["n"], 3),
        }
        for k, v in by_routing.items()
    }

    p95_idx = min(n - 1, int(0.95 * (n - 1)))
    return {
        "count": n,
        "avg_arrival_slippage_bps": round(sum(slips) / n, 3),
        "p95_arrival_slippage_bps": round(slips[p95_idx], 3),
        "maker_fill_rate_pct": round((maker_count / n) * 100.0, 2),
        "avg_fee_drag_roe_pct": round(sum(float(r["fee_drag_roe_pct"] or 0.0) for r in rows) / n, 3),
        "avg_impact_bps": round(sum(float(r["impact_bps_est"] or 0.0) for r in rows) / n, 3),
        "avg_markout_1m_bps": round(sum(m1) / len(m1), 3) if m1 else None,
        "avg_markout_5m_bps": round(sum(m5) / len(m5), 3) if m5 else None,
        "avg_markout_close_bps": round(sum(mc) / len(mc), 3) if mc else None,
        "by_routing": by_routing_out,
        "recent": rows[:25],
    }


def generate_daily_observability_report(
    db_path: Optional[str] = None,
    assumed_cost_pct: float = DEFAULT_ASSUMED_COST_PCT,
    api_error_counts: Optional[Dict[str, int]] = None,
    window_hours: int = 24,
    cost_drift_threshold_pct: float = 0.04,
    days: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate daily net-of-fees PnL, max drawdown, realized-vs-backtest cost-drift report,
    and API error summary (`Gap #11`).
    """
    init_db(db_path)
    if days is not None:
        window_hours = max(1, int(days)) * 24
    now_ms = int(time.time() * 1000)
    win_ms = max(1, int(window_hours)) * 3600_000

    with get_db(db_path) as conn:
        all_closed = conn.execute(
            "SELECT * FROM trades WHERE closed_at IS NOT NULL ORDER BY closed_at ASC"
        ).fetchall()
        tca_rows = conn.execute("SELECT * FROM tca_executions ORDER BY ts_ms ASC").fetchall()

    tca_by_trade: Dict[str, float] = {}
    for tr in tca_rows:
        tid = tr["trade_id"]
        if tid:
            tca_by_trade[str(tid)] = float(tr["arrival_slippage_bps"] or 0.0)

    if all_closed:
        cutoff_now = now_ms - win_ms
        recent = [r for r in all_closed if int(r["closed_at"] or 0) >= cutoff_now]
        if not recent:
            max_ts = max(int(r["closed_at"] or 0) for r in all_closed)
            recent = [r for r in all_closed if int(r["closed_at"] or 0) >= (max_ts - win_ms)]
    else:
        recent = []

    err_map = {str(k): int(v) for k, v in (api_error_counts or {}).items() if v is not None}
    err_total = sum(err_map.values())
    assumed = float(assumed_cost_pct or DEFAULT_ASSUMED_COST_PCT)

    trade_count = len(recent)
    if trade_count == 0:
        return {
            "trade_count": 0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "win_rate_pct": 0.0,
            "gross_pnl_usdt": 0.0,
            "net_pnl_usdt": 0.0,
            "total_fee_usdt": 0.0,
            "fee_usdt": 0.0,
            "total_funding_usdt": 0.0,
            "funding_usdt": 0.0,
            "total_cost_usdt": 0.0,
            "expectancy_r_net": 0.0,
            "max_drawdown_usdt": 0.0,
            "max_drawdown_r": 0.0,
            "avg_arrival_slippage_bps": 0.0,
            "avg_realized_cost_pct": 0.0,
            "realized_cost_pct": 0.0,
            "assumed_cost_pct": round(assumed, 4),
            "cost_drift_pct": 0.0,
            "cost_drift_ratio": 0.0,
            "cost_drift_alert": False,
            "api_error_counts": err_map,
            "api_error_total": err_total,
            "by_strategy": {},
        }

    net_pnls: List[float] = []
    gross_pnls: List[float] = []
    fees: List[float] = []
    fundings: List[float] = []
    r_nets: List[float] = []
    slips_bps: List[float] = []
    realized_costs_pct: List[float] = []
    by_strategy: Dict[str, Dict[str, Any]] = {}

    for r in recent:
        tid = str(r["trade_id"])
        net_p = float(r["net_pnl_usdt"] or 0.0)
        fee_u = float(r["fee_usdt"] or 0.0)
        fund_u = float(r["funding_usdt"] or 0.0)
        gross_p = net_p + fee_u + fund_u
        r_net = float(r["r_multiple_net"] or 0.0)
        entry_px = float(r["entry_fill"] or r["entry_plan"] or 0.0)
        qty = float(r["qty"] or 0.0)
        lev = float(r["leverage"] or 20.0)
        margin_u = float(r["margin_usdt"] or 0.0)
        notional_u = float(r["notional_usdt"] or (qty * entry_px) or (margin_u * lev) or 0.0)

        slip_b = float(tca_by_trade.get(tid, 0.0))
        slips_bps.append(slip_b)
        fee_fund_pct = ((fee_u + fund_u) / notional_u * 100.0) if notional_u > 0 else 0.0
        rc_pct = fee_fund_pct + (max(0.0, slip_b) / 100.0)
        realized_costs_pct.append(rc_pct)

        net_pnls.append(net_p)
        gross_pnls.append(gross_p)
        fees.append(fee_u)
        fundings.append(fund_u)
        r_nets.append(r_net)

        sid = str(r["strategy_id"] or "MANUAL")
        sb = by_strategy.setdefault(sid, {"n": 0, "wins": 0, "net_pnl_usdt": 0.0, "gross_pnl_usdt": 0.0, "r_sum": 0.0})
        sb["n"] += 1
        if net_p > 0:
            sb["wins"] += 1
        sb["net_pnl_usdt"] = round(sb["net_pnl_usdt"] + net_p, 4)
        sb["gross_pnl_usdt"] = round(sb["gross_pnl_usdt"] + gross_p, 4)
        sb["r_sum"] = round(sb["r_sum"] + r_net, 4)

    wins = sum(1 for p in net_pnls if p > 0)
    losses = trade_count - wins
    win_rate = round((wins / trade_count) * 100.0, 2)

    cum_usd = 0.0
    peak_usd = 0.0
    max_dd_usd = 0.0
    for p in net_pnls:
        cum_usd += p
        if cum_usd > peak_usd:
            peak_usd = cum_usd
        dd = peak_usd - cum_usd
        if dd > max_dd_usd:
            max_dd_usd = dd

    cum_r = 0.0
    peak_r = 0.0
    max_dd_r = 0.0
    for rv in r_nets:
        cum_r += rv
        if cum_r > peak_r:
            peak_r = cum_r
        ddr = peak_r - cum_r
        if ddr > max_dd_r:
            max_dd_r = ddr

    avg_rc_pct = sum(realized_costs_pct) / trade_count
    cost_drift = avg_rc_pct - assumed
    cost_ratio = avg_rc_pct / max(assumed, 1e-9)
    drift_alert = bool(cost_drift > float(cost_drift_threshold_pct) or avg_rc_pct > assumed * 1.5)

    total_fee = round(sum(fees), 4)
    total_fund = round(sum(fundings), 4)
    return {
        "trade_count": trade_count,
        "total_trades": trade_count,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "win_rate_pct": win_rate,
        "gross_pnl_usdt": round(sum(gross_pnls), 4),
        "net_pnl_usdt": round(sum(net_pnls), 4),
        "total_fee_usdt": total_fee,
        "fee_usdt": total_fee,
        "total_funding_usdt": total_fund,
        "funding_usdt": total_fund,
        "total_cost_usdt": round(total_fee + total_fund, 4),
        "expectancy_r_net": round(sum(r_nets) / trade_count, 4),
        "max_drawdown_usdt": round(max_dd_usd, 4),
        "max_drawdown_r": round(max_dd_r, 4),
        "avg_arrival_slippage_bps": round(sum(slips_bps) / trade_count, 3),
        "avg_realized_cost_pct": round(avg_rc_pct, 4),
        "realized_cost_pct": round(avg_rc_pct, 4),
        "assumed_cost_pct": round(assumed, 4),
        "cost_drift_pct": round(cost_drift, 4),
        "cost_drift_ratio": round(cost_ratio, 3),
        "cost_drift_alert": drift_alert,
        "api_error_counts": err_map,
        "api_error_total": err_total,
        "by_strategy": by_strategy,
    }


def format_daily_telegram_report(report: Dict[str, Any]) -> str:
    """Format daily observability & cost-drift report into Telegram HTML message."""
    n = int(report.get("trade_count", 0) or 0)
    wr = float(report.get("win_rate", 0.0) or 0.0)
    gross_pnl = float(report.get("gross_pnl_usdt", 0.0) or 0.0)
    net_pnl = float(report.get("net_pnl_usdt", 0.0) or 0.0)
    fee_u = float(report.get("total_fee_usdt", 0.0) or 0.0)
    fund_u = float(report.get("total_funding_usdt", 0.0) or 0.0)
    dd_u = float(report.get("max_drawdown_usdt", 0.0) or 0.0)
    dd_r = float(report.get("max_drawdown_r", 0.0) or 0.0)
    rc_pct = float(report.get("avg_realized_cost_pct", 0.0) or 0.0)
    ac_pct = float(report.get("assumed_cost_pct", DEFAULT_ASSUMED_COST_PCT) or DEFAULT_ASSUMED_COST_PCT)
    drift_pct = float(report.get("cost_drift_pct", 0.0) or 0.0)
    drift_alert = bool(report.get("cost_drift_alert", False))
    err_counts = report.get("api_error_counts") or {}
    err_str = ", ".join(f"{k}={v}" for k, v in sorted(err_counts.items())) if err_counts else "None (0)"

    lines = [
        "📊 <b>PYROFUEL // DAILY OBSERVABILITY &amp; TCA REPORT</b>",
        "────────────────────────",
        f"📈 <b>Trades Closed:</b> {n} (Win Rate: <b>{wr:.1f}%</b>)",
        f"💰 <b>Gross PnL:</b> ${gross_pnl:+.2f} USDT",
        f"🧾 <b>Fees &amp; Funding:</b> -${fee_u:.2f} fee | -${fund_u:.2f} funding",
        f"💎 <b>Net PnL (After Costs):</b> <b>${net_pnl:+.2f} USDT</b>",
        f"📉 <b>Max Drawdown:</b> ${dd_u:.2f} USDT ({dd_r:.2f}R)",
        "────────────────────────",
        f"⚖️ <b>Realized vs Assumed Cost:</b> {rc_pct:.3f}% vs {ac_pct:.3f}% (Drift: {drift_pct:+.3f}%)",
    ]
    if drift_alert:
        lines.append(
            f"🚨 <b>COST DRIFT ALERT:</b> Realized friction ({rc_pct:.3f}%) significantly exceeds backtest assumption ({ac_pct:.3f}%)!"
        )
    lines.append(f"🛰️ <b>API Error Summary:</b> {err_str}")
    return "\n".join(lines)


def rotate_log_files(
    log_dir: Optional[str] = None,
    max_bytes: int = 20 * 1024 * 1024,
    keep: int = 3,
) -> List[str]:
    """
    Rotate `*.log` files in `log_dir` whose size >= `max_bytes`, keeping at most `keep` backups
    (`.log.1` .. `.log.{keep}`) and truncating the active `.log` file in place (`Gap #8`).
    """
    target_dir = os.path.abspath(log_dir or os.path.join(BOT_DIR, "logs"))
    if not os.path.isdir(target_dir):
        return []

    keep_n = max(1, int(keep))
    threshold = max(1, int(max_bytes))
    rotated: List[str] = []

    for fname in sorted(os.listdir(target_dir)):
        if not fname.endswith(".log"):
            continue
        log_path = os.path.join(target_dir, fname)
        if not os.path.isfile(log_path):
            continue
        try:
            size = os.path.getsize(log_path)
        except OSError:
            continue
        if size < threshold:
            continue

        # Remove any generation >= keep_n and shift .k -> .(k+1)
        for gen in range(keep_n, keep_n + 5):
            old_gen = f"{log_path}.{gen}"
            if os.path.exists(old_gen):
                try:
                    os.remove(old_gen)
                except OSError:
                    pass
        for gen in range(keep_n - 1, 0, -1):
            src_gen = f"{log_path}.{gen}"
            dst_gen = f"{log_path}.{gen + 1}"
            if os.path.exists(src_gen):
                try:
                    os.replace(src_gen, dst_gen)
                except OSError:
                    pass

        try:
            shutil.copy2(log_path, f"{log_path}.1")
            with open(log_path, "r+", encoding="utf-8", errors="ignore") as lf:
                lf.truncate(0)
            rotated.append(log_path)
        except OSError:
            continue

    return rotated


def backup_state_and_journal(
    db_path: Optional[str] = None,
    results_dir: Optional[str] = None,
    keep_days: int = 7,
) -> Dict[str, Any]:
    """
    Perform atomic online SQLite backup (`src_conn.backup(dst_conn)`) to
    `results/backups/journal_YYYYMMDD.db`, copy critical `results/*.json` state files,
    and prune backups older than `keep_days` (`Gap #8`).
    """
    target_db = os.path.abspath(db_path or DB_PATH)
    target_results = os.path.abspath(results_dir or os.path.dirname(target_db))
    backups_dir = os.path.join(target_results, "backups")
    os.makedirs(backups_dir, exist_ok=True)

    init_db(target_db)
    now_dt = datetime.now(timezone.utc)
    day_str = now_dt.strftime("%Y%m%d")
    backup_db_path = os.path.join(backups_dir, f"journal_{day_str}.db")

    with contextlib.closing(sqlite3.connect(target_db, timeout=20)) as src_conn:
        with contextlib.closing(sqlite3.connect(backup_db_path, timeout=20)) as dst_conn:
            src_conn.backup(dst_conn)

    # H9 Fix: Backup only critical state JSON files (skip hundreds of *_USD_latest.json / scan cache files)
    core_state_json_allowlist = {
        "active_positions.json",
        "autotrader_state.json",
        "trading_config.json",
        "risk_breaker_state.json",
        "vault_state.json",
        "performance_ledger.json",
        "bandit_state.json",
        "calibrator_state.json",
        "conformal_state.json",
        "adwin_state.json",
        "tabular_meta_weights.json",
        "ensemble_weights.json",
        "episodic_memory.json",
        "degraded_strategies.json",
        "promotion_ledger.json",
        "ai_quota_ledger.json",
        "heartbeat.json",
        "panic_lock.json",
    }
    copied_json: List[str] = []
    if os.path.isdir(target_results):
        for fname in sorted(os.listdir(target_results)):
            if fname not in core_state_json_allowlist:
                continue
            src_json = os.path.join(target_results, fname)
            if not os.path.isfile(src_json):
                continue
            stem = fname[:-5]
            dst_json = os.path.join(backups_dir, f"{stem}_{day_str}.json")
            try:
                shutil.copy2(src_json, dst_json)
                copied_json.append(dst_json)
            except OSError:
                continue

    pruned: List[str] = []
    cutoff_ts = time.time() - (max(1, int(keep_days)) * 86400.0)
    date_re = re.compile(r"_(\d{8})\.(?:db|json)$")

    for bname in sorted(os.listdir(backups_dir)):
        bpath = os.path.join(backups_dir, bname)
        if not os.path.isfile(bpath) or os.path.abspath(bpath) == os.path.abspath(backup_db_path):
            continue
        should_prune = False
        try:
            if os.path.getmtime(bpath) < cutoff_ts:
                should_prune = True
        except OSError:
            pass
        if not should_prune:
            m = date_re.search(bname)
            if m:
                try:
                    file_dt = datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
                    if (now_dt - file_dt).days > int(keep_days):
                        should_prune = True
                except ValueError:
                    pass
        if should_prune:
            try:
                os.remove(bpath)
                pruned.append(bpath)
            except OSError:
                pass

    return {
        "backup_db_path": backup_db_path,
        "backups_dir": backups_dir,
        "copied_json_files": copied_json,
        "pruned_files": pruned,
        "keep_days": int(keep_days),
    }


def backup_journal_and_rotate_logs(
    db_path: Optional[str] = None,
    results_dir: Optional[str] = None,
    log_dir: Optional[str] = None,
    keep_days: int = 7,
    max_bytes: int = 20 * 1024 * 1024,
    keep_logs: int = 3,
) -> Dict[str, Any]:
    """Combined convenience helper for daily SQLite/state backup and 20MB log rotation."""
    bak = backup_state_and_journal(db_path=db_path, results_dir=results_dir, keep_days=keep_days)
    rot = rotate_log_files(log_dir=log_dir, max_bytes=max_bytes, keep=keep_logs)
    return {
        **bak,
        "rotated_logs": rot,
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
