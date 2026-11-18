"""
PYROFUEL BOT - AUTO-DEGRADATION GUARD, ADVISORY STRATEGY GATE & SHADOW PROMOTION (Task T8.2 / WP-6)
1. Auto-Degradation Guard: Jika strategi live mengalami Profit Factor < 0.80 ATAU
   E[R]_net < -0.15R pada 15 trade terakhir bergulir -> otomatis diturunkan ke `shadow_only = True`.
2. Advisory Strategy Gate (Decision 2.B): Membaca `results/strategy_gate.json` via
   `check_strategy_gate(strategy_id, config=None, gate_path=None)`.
   Default `enforce_backtest_gate = False`: menghasilkan `allowed_live = True` + `advisory_warning`
   bila verdict `SHADOW_ONLY`. Bila `enforce_backtest_gate = True`: memblokir eksekusi live.
3. Statistical Shadow Promotion Rule (Gap #7):
   Mensyaratkan `n >= 80`, `CI_95%_low > +0.10R`, minimal rentang kalender `>= 14` hari,
   keragaman rezim `>= 2` rezim berbeda, serta koreksi multiple-comparison Holm-Bonferroni / BHY.
"""
import contextlib
import math
import os
from typing import Any, Dict, List, Optional
import config_schema
import journal
from state_io import atomic_write_json, read_json_safe

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STRATEGY_GATE_PATH = os.path.join(BOT_DIR, "results", "strategy_gate.json")


def load_strategy_gate(gate_path: Optional[str] = None) -> Dict[str, Any]:
    """Safely load `results/strategy_gate.json` under file lock with `.bak` fallback."""
    target = os.path.abspath(gate_path or DEFAULT_STRATEGY_GATE_PATH)
    data = read_json_safe(target, default={}, strict_on_corrupt=False, expected_type=dict)
    return data if isinstance(data, dict) else {}


def write_strategy_gate(gate_payload: Dict[str, Any], gate_path: Optional[str] = None) -> bool:
    """Atomically write `strategy_gate.json` with `.bak` snapshot."""
    target = os.path.abspath(gate_path or DEFAULT_STRATEGY_GATE_PATH)
    return atomic_write_json(target, gate_payload, make_bak=True)


def check_strategy_gate(
    strategy_id: str,
    config: Optional[Dict[str, Any]] = None,
    gate_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluate `results/strategy_gate.json` for `strategy_id` per Decision 2.B:
    - When `enforce_backtest_gate` is False (default): returns `allowed_live=True`
      with `advisory_warning` if the backtest verdict is `SHADOW_ONLY` or missing.
    - When `enforce_backtest_gate` is True: blocks live execution (`allowed_live=False`,
      `shadow_only=True`) unless `verdict == "LIVE_APPROVED"`.
    """
    if config is None:
        try:
            cfg = config_schema.load_trading_config()
        except Exception:
            cfg = {}
    else:
        cfg = config

    enforce_gate = bool((cfg or {}).get("enforce_backtest_gate", False))
    gate_data = load_strategy_gate(gate_path=gate_path)

    strategies_map = gate_data.get("strategies") if isinstance(gate_data.get("strategies"), dict) else {}
    entry = strategies_map.get(strategy_id)
    if entry is None and isinstance(gate_data.get(strategy_id), dict):
        entry = gate_data.get(strategy_id)

    if not isinstance(entry, dict):
        warn_msg = (
            f"Strategy '{strategy_id}' missing from strategy_gate.json; "
            + ("blocking live (enforce_backtest_gate=true)." if enforce_gate else "allowed live under Decision 2.B (enforce_backtest_gate=false).")
        )
        return {
            "strategy_id": strategy_id,
            "gate_found": False,
            "verdict": "SHADOW_ONLY" if enforce_gate else "UNKNOWN",
            "enforce_backtest_gate": enforce_gate,
            "allowed_live": not enforce_gate,
            "shadow_only": enforce_gate,
            "advisory_warning": warn_msg,
            "reason": warn_msg,
            "dsr": 0.0,
            "pbo": 1.0,
            "ci95_low": 0.0,
            "n_oos": 0,
            "pf_oos": 0.0,
            "expectancy_r_oos": 0.0,
            "data_days": float(gate_data.get("data_days", 0.0) or 0.0),
            "updated_at": str(gate_data.get("updated_at", "")),
        }

    verdict = str(entry.get("verdict", "SHADOW_ONLY")).upper()
    dsr = float(entry.get("dsr", 0.0) or 0.0)
    pbo = float(entry.get("pbo", 1.0) or 1.0)
    ci95_low = float(entry.get("ci95_low", 0.0) or 0.0)
    n_oos = int(entry.get("n_oos", 0) or 0)
    pf_oos = float(entry.get("pf_oos", 0.0) or 0.0)
    exp_r_oos = float(entry.get("expectancy_r_oos", 0.0) or 0.0)
    data_days = float(entry.get("data_days", gate_data.get("data_days", 0.0)) or 0.0)
    updated_at = str(entry.get("updated_at", gate_data.get("updated_at", "")))

    is_approved = verdict == "LIVE_APPROVED"
    if is_approved:
        return {
            "strategy_id": strategy_id,
            "gate_found": True,
            "verdict": "LIVE_APPROVED",
            "enforce_backtest_gate": enforce_gate,
            "allowed_live": True,
            "shadow_only": False,
            "advisory_warning": "",
            "reason": f"Backtest gate LIVE_APPROVED (n_oos={n_oos}, DSR={dsr:.3f}, PBO={pbo:.3f}, CI95_low={ci95_low:+.3f}R)",
            "dsr": dsr,
            "pbo": pbo,
            "ci95_low": ci95_low,
            "n_oos": n_oos,
            "pf_oos": pf_oos,
            "expectancy_r_oos": exp_r_oos,
            "data_days": data_days,
            "updated_at": updated_at,
        }

    warn_msg = (
        f"Backtest gate verdict={verdict} for {strategy_id} "
        f"(n_oos={n_oos}, DSR={dsr:.3f}, PBO={pbo:.3f}, CI95_low={ci95_low:+.3f}R)"
    )
    if enforce_gate:
        return {
            "strategy_id": strategy_id,
            "gate_found": True,
            "verdict": verdict,
            "enforce_backtest_gate": True,
            "allowed_live": False,
            "shadow_only": True,
            "advisory_warning": warn_msg,
            "reason": f"Blocked by enforce_backtest_gate=true: {warn_msg}",
            "dsr": dsr,
            "pbo": pbo,
            "ci95_low": ci95_low,
            "n_oos": n_oos,
            "pf_oos": pf_oos,
            "expectancy_r_oos": exp_r_oos,
            "data_days": data_days,
            "updated_at": updated_at,
        }

    return {
        "strategy_id": strategy_id,
        "gate_found": True,
        "verdict": verdict,
        "enforce_backtest_gate": False,
        "allowed_live": True,
        "shadow_only": False,
        "advisory_warning": warn_msg,
        "reason": f"Advisory warning only (enforce_backtest_gate=false): {warn_msg}",
        "dsr": dsr,
        "pbo": pbo,
        "ci95_low": ci95_low,
        "n_oos": n_oos,
        "pf_oos": pf_oos,
        "expectancy_r_oos": exp_r_oos,
        "data_days": data_days,
        "updated_at": updated_at,
    }


def _one_sided_p_value(r_values: List[float]) -> float:
    """One-sided upper-tail z/normal p-value testing H0: E[R] <= 0 vs H1: E[R] > 0."""
    n = len(r_values)
    if n < 2:
        return 1.0
    mean_r = sum(r_values) / n
    var_r = sum((x - mean_r) ** 2 for x in r_values) / (n - 1)
    se = math.sqrt(var_r / n)
    if se <= 1e-12:
        return 0.0 if mean_r > 0.0 else 1.0
    z = mean_r / se
    return float(min(1.0, max(0.0, 0.5 * math.erfc(z / math.sqrt(2.0)))))


def adjust_pvalues(
    p_values_by_id: Dict[str, float],
    method: str = "holm",
    alpha: float = 0.05,
) -> Dict[str, Dict[str, Any]]:
    """
    Apply multiple-comparison p-value adjustment across strategies:
    - `"holm"`: Holm-Bonferroni step-down family-wise error rate control.
    - `"bhy"`: Benjamini-Hochberg-Yekutieli step-up FDR control under arbitrary dependence.
    """
    if not p_values_by_id:
        return {}

    m = len(p_values_by_id)
    sorted_items = sorted(p_values_by_id.items(), key=lambda kv: float(kv[1]))
    meth = str(method or "holm").lower()
    adj_vals = [1.0] * m

    if meth == "bhy":
        c_m = sum(1.0 / k for k in range(1, m + 1))
        running_min = 1.0
        for idx in range(m - 1, -1, -1):
            rank = idx + 1
            raw_p = float(sorted_items[idx][1])
            cand = min(1.0, (m * c_m / rank) * raw_p)
            running_min = min(running_min, cand)
            adj_vals[idx] = running_min
    else:
        meth = "holm"
        running_max = 0.0
        for idx in range(m):
            raw_p = float(sorted_items[idx][1])
            cand = min(1.0, (m - idx) * raw_p)
            running_max = max(running_max, cand)
            adj_vals[idx] = running_max

    out: Dict[str, Dict[str, Any]] = {}
    for idx, (sid, raw_p) in enumerate(sorted_items):
        p_adj = float(adj_vals[idx])
        out[sid] = {
            "p_raw": round(float(raw_p), 6),
            "p_adjusted": round(p_adj, 6),
            "alpha": float(alpha),
            "method": meth,
            "m_tests": m,
            "rejected_h0": bool(p_adj <= float(alpha)),
        }
    return out


def evaluate_auto_degradation(
    strategy_id: str,
    window: int = 15,
    min_trades: int = 15,
    min_pf: float = 0.80,
    min_expectancy_r: float = -0.15,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check rolling live performance over the last `window` trades.
    Demotes to `shadow_only = True` if `n >= min_trades` and (`PF < 0.80` or `E[R]_net < -0.15R`).
    """
    metrics = journal.get_rolling_strategy_metrics(
        strategy_id=strategy_id,
        window=window,
        include_shadow=False,
        db_path=db_path,
    )
    n = int(metrics["n"])
    pf = float(metrics["profit_factor"])
    exp_r = float(metrics["expectancy_r"])

    if n >= min_trades and (pf < min_pf or exp_r < min_expectancy_r):
        return {
            **metrics,
            "degraded": True,
            "shadow_only": True,
            "action": "DEMOTE_TO_SHADOW",
            "reason": f"Auto-Degradation triggered on {n} rolling trades: PF={pf:.2f} (<{min_pf}), E[R]={exp_r:+.3f}R (<{min_expectancy_r:+.2f}R)",
        }

    return {
        **metrics,
        "degraded": False,
        "shadow_only": False,
        "action": "KEEP_LIVE",
        "reason": f"Healthy live performance (n={n}, PF={pf:.2f}, E[R]={exp_r:+.3f}R)",
    }


def _query_shadow_metadata(
    strategy_id: str,
    window: int,
    db_path: Optional[str],
    n_strategies: int,
) -> Dict[str, Any]:
    """Fetch shadow timestamps, distinct regimes, and peer p-values for multiple-testing control."""
    journal.init_db(db_path)
    with contextlib.closing(journal.get_db(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT r_multiple_net, regime, opened_at, closed_at
            FROM shadow_trades
            WHERE strategy_id = ? AND status = 'CLOSED' AND r_multiple_net IS NOT NULL
            ORDER BY closed_at DESC LIMIT ?
            """,
            (strategy_id, window),
        ).fetchall()

        peer_rows = conn.execute(
            """
            SELECT strategy_id, r_multiple_net
            FROM shadow_trades
            WHERE status = 'CLOSED' AND r_multiple_net IS NOT NULL
            ORDER BY closed_at DESC
            """
        ).fetchall()

    timestamps: List[int] = []
    regimes = set()
    r_values: List[float] = []
    for r in rows:
        r_values.append(float(r["r_multiple_net"]))
        ts = r["closed_at"] or r["opened_at"]
        if ts is not None and int(ts) > 0:
            timestamps.append(int(ts))
        reg = str(r["regime"] or "").strip()
        if reg and reg.upper() != "UNKNOWN":
            regimes.add(reg)

    span_days = round((max(timestamps) - min(timestamps)) / 86_400_000.0, 4) if len(timestamps) >= 2 else 0.0

    peer_map: Dict[str, List[float]] = {}
    for pr in peer_rows:
        sid = str(pr["strategy_id"])
        lst = peer_map.setdefault(sid, [])
        if len(lst) < window:
            lst.append(float(pr["r_multiple_net"]))
    if strategy_id not in peer_map:
        peer_map[strategy_id] = r_values

    p_values: Dict[str, float] = {sid: _one_sided_p_value(vals) for sid, vals in peer_map.items()}
    pad_idx = 0
    while len(p_values) < max(1, int(n_strategies)):
        pad_idx += 1
        pad_key = f"__PEER_STRATEGY_{pad_idx}"
        if pad_key not in p_values:
            p_values[pad_key] = 1.0

    return {
        "span_days": span_days,
        "regimes_seen": sorted(regimes),
        "distinct_regimes": len(regimes),
        "p_values_by_id": p_values,
    }


def evaluate_shadow_promotion(
    strategy_id: str,
    min_shadow_trades: int = 80,
    min_ci95_low_r: float = 0.10,
    db_path: Optional[str] = None,
    min_span_days: Optional[int] = None,
    min_regimes: Optional[int] = None,
    n_strategies: int = 4,
    correction_method: str = "holm",
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Check if a `shadow_only` strategy qualifies for statistical promotion to live:
    Requires:
    - `n >= min_shadow_trades` (default 80) independent resolved shadow trades
    - `CI_95%_low(E[R]_net) > +0.10R`
    - Holm-Bonferroni / BHY multiple-comparison correction (`p_adjusted <= alpha`)
    - Optional / configurable `min_span_days` (e.g. `14` days) & `min_regimes` (e.g. `2` distinct regimes)
      enforced whenever provided (`> 0` / `> 1`) or via `StrategyLifecycleManager`.
    """
    window = max(int(min_shadow_trades), 250)
    metrics = journal.get_rolling_strategy_metrics(
        strategy_id=strategy_id,
        window=window,
        include_shadow=True,
        db_path=db_path,
    )
    n = int(metrics["n"])
    ci_low = float(metrics["ci95_low"])
    exp_r = float(metrics["expectancy_r"])

    meta = _query_shadow_metadata(strategy_id, window=window, db_path=db_path, n_strategies=n_strategies)
    span_days = float(meta["span_days"])
    distinct_regimes = int(meta["distinct_regimes"])
    regimes_seen = list(meta["regimes_seen"])

    adj_map = adjust_pvalues(meta["p_values_by_id"], method=correction_method, alpha=alpha)
    adj_info = adj_map.get(strategy_id, {"p_raw": 1.0, "p_adjusted": 1.0, "rejected_h0": False, "method": correction_method})
    mt_passed = bool(adj_info["rejected_h0"])

    span_ok = True if (min_span_days is None or int(min_span_days) <= 0) else (span_days >= float(min_span_days))
    regime_ok = True if (min_regimes is None or int(min_regimes) <= 1) else (distinct_regimes >= int(min_regimes))

    failures: List[str] = []
    if n < min_shadow_trades:
        failures.append(f"n={n}/{min_shadow_trades}")
    if ci_low <= min_ci95_low_r:
        failures.append(f"CI95_low={ci_low:+.3f}R (req > +{min_ci95_low_r:.2f}R)")
    if not mt_passed:
        failures.append(f"{adj_info['method']}_p_adj={adj_info['p_adjusted']:.4f} (> {alpha})")
    if not span_ok:
        failures.append(f"span={span_days:.2f}d (< {min_span_days}d)")
    if not regime_ok:
        failures.append(f"regimes={distinct_regimes} (< {min_regimes})")

    common_fields = {
        "span_days": span_days,
        "distinct_regimes": distinct_regimes,
        "regimes_seen": regimes_seen,
        "p_value": adj_info["p_raw"],
        "p_adjusted": adj_info["p_adjusted"],
        "correction_method": adj_info["method"],
        "multiple_testing_passed": mt_passed,
    }

    if not failures:
        return {
            **metrics,
            **common_fields,
            "promote_to_live": True,
            "shadow_only": False,
            "action": "PROMOTE_TO_LIVE",
            "reason": (
                f"Promoted to LIVE: n={n} (>= {min_shadow_trades}), CI95_low={ci_low:+.3f}R, "
                f"E[R]={exp_r:+.3f}R, {adj_info['method']}_p_adj={adj_info['p_adjusted']:.4f}, "
                f"span={span_days:.1f}d, regimes={distinct_regimes}"
            ),
        }

    return {
        **metrics,
        **common_fields,
        "promote_to_live": False,
        "shadow_only": True,
        "action": "KEEP_SHADOW",
        "reason": f"Insufficient shadow proof: {', '.join(failures)}",
    }


class StrategyLifecycleManager:
    def __init__(
        self,
        db_path: Optional[str] = None,
        enforce_backtest_gate: Optional[bool] = None,
        gate_path: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        min_span_days: int = 14,
        min_regimes: int = 2,
        correction_method: str = "holm",
    ):
        self.db_path = db_path
        self.gate_path = gate_path
        self.config = dict(config or {})
        if enforce_backtest_gate is None:
            if "enforce_backtest_gate" in self.config:
                self.enforce_backtest_gate = bool(self.config["enforce_backtest_gate"])
            else:
                try:
                    self.enforce_backtest_gate = bool(
                        config_schema.load_trading_config().get("enforce_backtest_gate", False)
                    )
                except Exception:
                    self.enforce_backtest_gate = False
        else:
            self.enforce_backtest_gate = bool(enforce_backtest_gate)

        self.min_span_days = int(min_span_days)
        self.min_regimes = int(min_regimes)
        self.correction_method = str(correction_method)
        self.status_map: Dict[str, Dict[str, bool]] = {
            "S1_TREND_PULLBACK": {"enabled": True, "shadow_only": False},
            "S2_OI_VOL_BREAKOUT": {"enabled": True, "shadow_only": False},
            "S3_LIQ_CASCADE_FADE": {"enabled": True, "shadow_only": False},
            "S4_EXTREME_FUNDING_REVERSION": {"enabled": True, "shadow_only": False},
        }

    def audit_strategy(self, strategy_id: str) -> Dict[str, Any]:
        st = self.status_map.setdefault(strategy_id, {"enabled": True, "shadow_only": False})
        gate_cfg = {**self.config, "enforce_backtest_gate": self.enforce_backtest_gate}
        gate_res = check_strategy_gate(strategy_id, config=gate_cfg, gate_path=self.gate_path)

        if not st["shadow_only"]:
            res = evaluate_auto_degradation(strategy_id, db_path=self.db_path)
            if res["degraded"]:
                st["shadow_only"] = True
        else:
            res = evaluate_shadow_promotion(
                strategy_id,
                db_path=self.db_path,
                min_span_days=self.min_span_days,
                min_regimes=self.min_regimes,
                correction_method=self.correction_method,
            )
            if res["promote_to_live"]:
                if self.enforce_backtest_gate and not gate_res["allowed_live"]:
                    res["promote_to_live"] = False
                    res["shadow_only"] = True
                    res["action"] = "KEEP_SHADOW"
                    res["reason"] = f"Shadow proof met, but blocked by enforce_backtest_gate=true ({gate_res['advisory_warning']})"
                else:
                    st["shadow_only"] = False

        if self.enforce_backtest_gate and not gate_res["allowed_live"]:
            st["shadow_only"] = True
            res["shadow_only"] = True
            res["allowed_live"] = False
        else:
            res["allowed_live"] = not bool(st["shadow_only"])

        res["backtest_gate"] = gate_res
        res["advisory_warning"] = gate_res.get("advisory_warning", "")
        return res
