"""
SOTA Quantitative Regime & Online Drift Modules (Pure NumPy + Python stdlib, Termux-ready):
1. GaussianHMM3Regime: 3-state Hidden Markov Model on (Returns, Realized Vol, OI Velocity, Funding Skew)
   to quantify transition probability into Leverage-Buildup Squeeze or Liquidation Cascade regimes.
2. ADWINDetector: Adaptive Windowing Concept Drift Detector (Bifet & Gavaldà) for non-stationary
   crypto reward/error streams so online bandits & calibration reset stale regime weights automatically.
3. extract_quant_feature_vector: Shared 15-feature normalized vector across TabularMetaModel & EpisodicMarketMemory.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR_DEFAULT = os.path.join(BOT_DIR, "results")
DEFAULT_ADWIN_PATH = os.path.join(RESULTS_DIR_DEFAULT, "adwin_state.json")
DEFAULT_META_PATH = os.path.join(RESULTS_DIR_DEFAULT, "tabular_meta_weights.json")
DEFAULT_ENSEMBLE_PATH = os.path.join(RESULTS_DIR_DEFAULT, "ensemble_weights.json")
DEFAULT_EPISODES_PATH = os.path.join(RESULTS_DIR_DEFAULT, "episodic_memory.json")
DEFAULT_CALIBRATOR_PATH = os.path.join(RESULTS_DIR_DEFAULT, "calibrator_state.json")
DEFAULT_CONFORMAL_PATH = os.path.join(RESULTS_DIR_DEFAULT, "conformal_state.json")


def atomic_write_json(path: str, payload: Any) -> bool:
    """Write JSON atomically using thread-safe temporary file + os.replace to avoid torn reads."""
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_path = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
        return True
    except Exception:
        return False


def extract_quant_feature_vector(
    math_proof: Optional[Dict[str, Any]] = None,
    scan_data: Optional[Dict[str, Any]] = None,
) -> List[float]:
    """Build consistent 15-dimensional standardized feature vector for ML & k-NN episodic memory."""
    mp = math_proof or {}
    sc = scan_data or {}
    qf = sc.get("quant_factors") or {}
    vol = sc.get("volume") or {}
    fr = sc.get("funding_rate") or {}
    ls = sc.get("long_short") or {}
    news = sc.get("news_macro") or {}
    opt = mp.get("options_surface") or {}

    c_score = float(qf.get("composite_quant_score", mp.get("p_math_pct", 50.0)) or 50.0)
    ofi_20 = float(mp.get("obi_weighted_20", 0.0) or 0.0)
    micro_div = float(mp.get("micro_divergence", 0.0) or 0.0)
    hurst = float(mp.get("hurst_exponent", 0.54) or 0.54)
    vr_q = float(mp.get("variance_ratio_q4", 1.0) or 1.0)
    vpin = float(mp.get("vpin", 0.5) or 0.5)
    hawkes_net = float(mp.get("hawkes_ratio_plus", 1.0) or 1.0) - float(mp.get("hawkes_ratio_minus", 1.0) or 1.0)
    rsi = float(sc.get("rsi_14_1h", 50.0) or 50.0)
    fr_rate = float(fr.get("rate", 0.0) or 0.0)
    ls_ratio = max(0.1, float(ls.get("long_short_ratio", ls.get("ratio", 1.0)) or 1.0))
    vol_ratio = float(vol.get("volume_ratio", 1.0) or 1.0)
    atr_pct = float(sc.get("atr_pct", 1.2) or 1.2)
    dvol = float(opt.get("dvol", 50.0) or 50.0)
    skew_25d = float(opt.get("skew_25d", 0.0) or 0.0)
    news_score = float(news.get("sentiment_score", 50.0) or 50.0)

    raw = [
        (c_score - 50.0) / 25.0,
        ofi_20 * 2.0,
        micro_div * 2.0,
        (hurst - 0.50) * 5.0,
        (vr_q - 1.0) * 2.0,
        (vpin - 0.50) * 3.0,
        math.tanh(hawkes_net / 3.0),
        (rsi - 50.0) / 20.0,
        math.tanh(fr_rate * 2000.0),
        math.log(ls_ratio),
        math.tanh((vol_ratio - 1.0) / 2.0),
        (atr_pct - 1.5) / 1.5,
        (dvol - 50.0) / 25.0,
        math.tanh(skew_25d / 10.0),
        (news_score - 50.0) / 25.0,
    ]
    return [round(float(max(-3.0, min(3.0, v))), 5) for v in raw]


def _logsumexp(a: np.ndarray, axis: Optional[int] = None) -> np.ndarray:
    m = np.max(a, axis=axis, keepdims=True)
    res = m + np.log(np.maximum(np.sum(np.exp(a - m), axis=axis, keepdims=True), 1e-300))
    return np.squeeze(res, axis=axis) if axis is not None else float(np.asarray(res).item())


class GaussianHMM3Regime:
    """Pure NumPy 3-state diagonal Gaussian HMM for Squeeze/Cascade transition risk."""

    STATE_NAMES = (
        "STATE_0_LOW_VOL_CONSOLIDATION",
        "STATE_1_LEVERAGE_BUILDUP_SQUEEZE",
        "STATE_2_CASCADE_VOLATILITY",
    )

    def fit_and_predict(
        self,
        closes: Sequence[float],
        oi_series: Optional[Sequence[float]] = None,
        funding_rate: float = 0.0,
        n_iter: int = 8,
    ) -> Dict[str, Any]:
        c_arr = np.asarray(closes, dtype=float)
        if c_arr.size < 20:
            return {
                "current_state": self.STATE_NAMES[0],
                "state_index": 0,
                "state_probs": [0.7, 0.2, 0.1],
                "p_transition_to_cascade": 0.10,
                "squeeze_risk_score": 25.0,
                "recommended_risk_mult": 1.0,
            }

        rets = np.diff(np.log(np.maximum(c_arr, 1e-12)))
        n = rets.size
        vol_roll = np.array([
            float(np.std(rets[max(0, i - 5): i + 1])) + 1e-5 for i in range(n)
        ])

        if oi_series is not None and len(oi_series) >= c_arr.size:
            oi_arr = np.asarray(oi_series[-c_arr.size:], dtype=float)
            oi_vel = np.diff(oi_arr) / np.maximum(np.abs(oi_arr[:-1]), 1.0)
        elif oi_series is not None and len(oi_series) >= 12:
            oi_arr = np.asarray(oi_series, dtype=float)
            oi_vel_raw = np.diff(oi_arr) / np.maximum(np.abs(oi_arr[:-1]), 1.0)
            pad_len = n - oi_vel_raw.size
            oi_vel = np.concatenate([np.zeros(max(0, pad_len)), oi_vel_raw[-n:]])
        else:
            oi_vel = np.zeros(n, dtype=float)

        abs_fr = float(abs(funding_rate)) * 1000.0
        obs = np.column_stack([
            rets / max(float(np.std(rets)), 1e-5),
            (vol_roll - np.mean(vol_roll)) / max(float(np.std(vol_roll)), 1e-5),
            oi_vel / max(float(np.std(oi_vel)), 1e-4) if np.std(oi_vel) > 1e-9 else oi_vel,
        ])

        # Initialize 3 emission centers across empirical quantiles (Low vol, Medium+OI, Extreme vol)
        q_idx = np.argsort(obs[:, 1])
        thirds = np.array_split(q_idx, 3)
        means = np.array([np.mean(obs[idx], axis=0) for idx in thirds], dtype=float)
        vars_diag = np.array([np.maximum(np.var(obs[idx], axis=0), 0.15) for idx in thirds], dtype=float)

        pi = np.array([0.50, 0.35, 0.15], dtype=float)
        A = np.array([
            [0.84, 0.13, 0.03],
            [0.14, 0.72, 0.14],
            [0.08, 0.27, 0.65],
        ], dtype=float)

        k_states = 3
        d_feat = obs.shape[1]
        gamma = np.full((n, k_states), 1.0 / k_states)

        for _ in range(max(1, n_iter)):
            log_B = np.zeros((n, k_states), dtype=float)
            for k in range(k_states):
                diff = obs - means[k]
                log_B[:, k] = -0.5 * (
                    d_feat * math.log(2.0 * math.pi)
                    + np.sum(np.log(vars_diag[k]))
                    + np.sum((diff * diff) / vars_diag[k], axis=1)
                )

            log_A = np.log(np.maximum(A, 1e-8))
            log_alpha = np.zeros((n, k_states), dtype=float)
            log_alpha[0] = np.log(np.maximum(pi, 1e-8)) + log_B[0]
            for t in range(1, n):
                for k in range(k_states):
                    log_alpha[t, k] = _logsumexp(log_alpha[t - 1] + log_A[:, k]) + log_B[t, k]

            log_beta = np.zeros((n, k_states), dtype=float)
            for t in range(n - 2, -1, -1):
                for k in range(k_states):
                    log_beta[t, k] = _logsumexp(log_A[k, :] + log_B[t + 1] + log_beta[t + 1])

            log_gamma = log_alpha + log_beta
            log_gamma -= np.array([_logsumexp(row) for row in log_gamma])[:, None]
            gamma = np.exp(log_gamma)

            # Update transition matrix A with Dirichlet floor smoothing
            xi_sum = np.zeros((k_states, k_states), dtype=float)
            for t in range(n - 1):
                log_xi_t = log_alpha[t, :, None] + log_A + (log_B[t + 1] + log_beta[t + 1])[None, :]
                log_xi_t -= _logsumexp(log_xi_t.ravel())
                xi_sum += np.exp(log_xi_t)

            A_new = xi_sum + 0.05
            A = A_new / np.sum(A_new, axis=1, keepdims=True)
            pi = np.maximum(gamma[0], 1e-4)
            pi /= np.sum(pi)

            nk = np.maximum(np.sum(gamma, axis=0), 1e-3)
            for k in range(k_states):
                means[k] = (gamma[:, k] @ obs) / nk[k]
                diff = obs - means[k]
                vars_diag[k] = np.maximum((gamma[:, k] @ (diff * diff)) / nk[k], 0.12)

        # Canonical state ordering by emission realized-volatility dimension (index 1)
        order = np.argsort(means[:, 1])
        inv_order = np.argsort(order)
        gamma_sorted = gamma[:, order]
        A_sorted = A[order][:, order]

        curr_probs = gamma_sorted[-1]
        curr_idx = int(np.argmax(curr_probs))
        # One-step forward probability of entering STATE_2_CASCADE_VOLATILITY
        next_probs = curr_probs @ A_sorted
        p_cascade = float(np.clip(max(next_probs[2], curr_probs[2]) + min(0.15, abs_fr * 0.08), 0.0, 1.0))

        squeeze_score = float(np.clip((curr_probs[1] * 65.0 + curr_probs[2] * 95.0 + abs_fr * 12.0), 0.0, 100.0))
        risk_mult = 0.55 if curr_idx == 2 else (0.80 if curr_idx == 1 else 1.0)

        return {
            "current_state": self.STATE_NAMES[curr_idx],
            "state_index": curr_idx,
            "state_probs": [round(float(x), 4) for x in curr_probs],
            "p_transition_to_cascade": round(p_cascade, 4),
            "squeeze_risk_score": round(squeeze_score, 1),
            "recommended_risk_mult": round(risk_mult, 2),
        }


class ADWINDetector:
    """
    Lightweight ADWIN Concept Drift Detector for streaming trade performance / reward series.
    Persists recent window in JSON and cuts obsolete prefixes when two sub-windows differ significantly.
    """

    def __init__(
        self,
        delta: float = 0.02,
        max_window: int = 160,
        min_subwindow: int = 5,
        state_path: Optional[str] = None,
    ):
        self.delta = float(max(1e-4, min(0.5, delta)))
        self.max_window = int(max(20, max_window))
        self.min_subwindow = int(max(3, min_subwindow))
        self.state_path = state_path or DEFAULT_ADWIN_PATH
        self.window: List[float] = []
        self.drift_count: int = 0
        self.total_samples: int = 0
        self.last_drift_ts: float = 0.0
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    self.window = [float(x) for x in d.get("window", [])][-self.max_window:]
                    self.drift_count = int(d.get("drift_count", 0))
                    self.total_samples = int(d.get("total_samples", 0))
                    self.last_drift_ts = float(d.get("last_drift_ts", 0.0))
            except Exception:
                pass

    def _save(self) -> None:
        atomic_write_json(self.state_path, {
            "delta": self.delta,
            "window": [round(x, 5) for x in self.window[-self.max_window:]],
            "drift_count": self.drift_count,
            "total_samples": self.total_samples,
            "last_drift_ts": self.last_drift_ts,
        })

    def update(self, value: float) -> Dict[str, Any]:
        # Clip/scale R-multiple into [0, 1] scale using sigmoid or clamped band for bounded Hoeffding check
        scaled = float(max(0.0, min(1.0, 0.5 + 0.25 * float(value))))
        self.window.append(scaled)
        if len(self.window) > self.max_window:
            self.window = self.window[-self.max_window:]
        self.total_samples += 1

        n = len(self.window)
        drift_detected = False
        cut_index = 0

        if n >= self.min_subwindow * 2:
            arr = np.asarray(self.window, dtype=float)
            var_w = max(0.025, float(np.var(arr)))
            ln_term = math.log(4.0 * float(n) / self.delta)
            prefix_sum = np.cumsum(arr)
            total_sum = float(prefix_sum[-1])
            for k in range(self.min_subwindow, n - self.min_subwindow + 1):
                n0 = float(k)
                n1 = float(n - k)
                mu0 = float(prefix_sum[k - 1]) / n0
                mu1 = (total_sum - float(prefix_sum[k - 1])) / n1
                m = 1.0 / (1.0 / n0 + 1.0 / n1)
                eps_cut = math.sqrt((2.0 / m) * var_w * ln_term)
                if abs(mu0 - mu1) > eps_cut:
                    drift_detected = True
                    cut_index = k
            if drift_detected and cut_index > 0:
                self.window = self.window[cut_index:]
                self.drift_count += 1
                self.last_drift_ts = time.time()

        self._save()
        mean_recent = float(np.mean(self.window)) if self.window else 0.5
        return {
            "drift_detected": drift_detected,
            "window_len": len(self.window),
            "mean_recent_scaled": round(mean_recent, 4),
            "drift_count": self.drift_count,
            "total_samples": self.total_samples,
        }


# ===========================================================================
# Shared Persistence Helpers for 3-Brain Online Weights & Episodic Memory
# ===========================================================================

def load_tabular_meta_model(path: Optional[str] = None, feature_dim: int = 15):
    """Load TabularMetaModel with persisted online logistic weights from JSON."""
    from ai.hybrid_ensemble import TabularMetaModel
    target = path or DEFAULT_META_PATH
    model = TabularMetaModel(feature_dim=feature_dim)
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            w = np.asarray(data.get("weights", []), dtype=float).ravel()
            if w.size == feature_dim:
                model.weights = w
            model.bias = float(data.get("bias", 0.0))
            model.n_updates = int(data.get("n_updates", 0))
        except Exception:
            pass
    return model


def save_tabular_meta_model(model, path: Optional[str] = None) -> bool:
    """Atomically persist TabularMetaModel online weights."""
    target = path or DEFAULT_META_PATH
    return atomic_write_json(target, {
        "feature_dim": int(getattr(model, "feature_dim", 15)),
        "weights": [round(float(x), 6) for x in np.asarray(model.weights, dtype=float).tolist()],
        "bias": round(float(getattr(model, "bias", 0.0)), 6),
        "n_updates": int(getattr(model, "n_updates", 0)),
        "updated_at": time.time(),
    })


def load_ensemble_weights(path: Optional[str] = None):
    """Load NeuroSymbolicEnsemble with persisted Hedge brain weights."""
    from ai.hybrid_ensemble import NeuroSymbolicEnsemble
    target = path or DEFAULT_ENSEMBLE_PATH
    ens = NeuroSymbolicEnsemble()
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            w = data.get("weights")
            if isinstance(w, dict) and all(k in w for k in ("ml", "knn", "llm")):
                s = float(w["ml"]) + float(w["knn"]) + float(w["llm"])
                if s > 0:
                    ens.weights = {
                        "ml": float(w["ml"]) / s,
                        "knn": float(w["knn"]) / s,
                        "llm": float(w["llm"]) / s,
                    }
        except Exception:
            pass
    return ens


def save_ensemble_weights(ens, path: Optional[str] = None) -> bool:
    """Atomically persist NeuroSymbolicEnsemble brain weights."""
    target = path or DEFAULT_ENSEMBLE_PATH
    return atomic_write_json(target, {
        "weights": {k: round(float(v), 5) for k, v in getattr(ens, "weights", {}).items()},
        "updated_at": time.time(),
    })


def load_episodic_memory(path: Optional[str] = None, feature_dim: int = 15, max_episodes: int = 1500):
    """Load persisted episodic market feature vectors into EpisodicMarketMemory."""
    from ai.episodic_memory import EpisodicMarketMemory
    target = path or DEFAULT_EPISODES_PATH
    mem = EpisodicMarketMemory(feature_dim=feature_dim)
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                rows = json.load(f)
            if isinstance(rows, list):
                for row in rows[-max_episodes:]:
                    if isinstance(row, dict) and isinstance(row.get("vector"), list):
                        mem.add_episode(
                            feature_vector=row["vector"],
                            r_multiple_net=float(row.get("r_multiple_net", 0.0)),
                            outcome_win=bool(row.get("outcome_win", 0)),
                            regime=str(row.get("regime", "UNKNOWN")),
                            strategy_id=str(row.get("strategy_id", "AI_SETUP")),
                            note=str(row.get("note", "")),
                        )
        except Exception:
            pass
    return mem


def append_episodic_episode(
    feature_vector: Sequence[float],
    r_multiple_net: float,
    outcome_win: Optional[bool] = None,
    regime: str = "UNKNOWN",
    strategy_id: str = "AI_SETUP",
    note: str = "",
    path: Optional[str] = None,
    max_episodes: int = 1500,
) -> bool:
    """Append a resolved trade episode to persistent episodic memory store."""
    target = path or DEFAULT_EPISODES_PATH
    rows: List[Dict[str, Any]] = []
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    rows = loaded
        except Exception:
            rows = []

    vec = [round(float(x), 5) for x in list(feature_vector)[:15]]
    while len(vec) < 15:
        vec.append(0.0)
    win_flag = bool(r_multiple_net > 0) if outcome_win is None else bool(outcome_win)
    rows.append({
        "vector": vec,
        "r_multiple_net": round(float(r_multiple_net), 4),
        "outcome_win": 1 if win_flag else 0,
        "regime": str(regime or "UNKNOWN"),
        "strategy_id": str(strategy_id or "AI_SETUP"),
        "note": str(note or ""),
        "ts": time.time(),
    })
    if len(rows) > max_episodes:
        rows = rows[-max_episodes:]
    return atomic_write_json(target, rows)


def load_calibrator(path: Optional[str] = None):
    """Load persisted ProbabilityCalibrator sample history and fit PAVA isotonic knots."""
    from calibration import ProbabilityCalibrator
    target = path or DEFAULT_CALIBRATOR_PATH
    cal = ProbabilityCalibrator()
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            p_raw = [float(x) for x in data.get("history_p_raw", [])][-300:]
            y_val = [1 if int(y) > 0 else 0 for y in data.get("history_y", [])][-300:]
            if p_raw and len(p_raw) == len(y_val):
                cal.fit(p_raw, y_val)
        except Exception:
            pass
    return cal


def save_calibrator(cal, path: Optional[str] = None) -> bool:
    """Atomically persist ProbabilityCalibrator history across restarts."""
    target = path or DEFAULT_CALIBRATOR_PATH
    p_raw = [round(float(x), 5) for x in getattr(cal, "history_p_raw", [])[-300:]]
    y_val = [1 if int(y) > 0 else 0 for y in getattr(cal, "history_y", [])[-300:]]
    return atomic_write_json(target, {
        "history_p_raw": p_raw,
        "history_y": y_val,
        "n_samples": len(y_val),
        "is_fitted": bool(getattr(cal, "_is_fitted", False)),
        "updated_at": time.time(),
    })


def load_conformal_filter(path: Optional[str] = None, alpha_target: float = 0.18):
    """Load persisted AdaptiveConformalFilter nonconformity window and online alpha_t."""
    from ai.conformal import AdaptiveConformalFilter
    target = path or DEFAULT_CONFORMAL_PATH
    filt = AdaptiveConformalFilter(alpha_target=float(alpha_target))
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            scores = [float(x) for x in data.get("scores_window", [])]
            if scores:
                filt = AdaptiveConformalFilter(alpha_target=float(alpha_target), warm_start_scores=scores[-filt.window_size:])
            if "alpha_t" in data:
                filt.alpha_t = float(max(filt.alpha_min, min(filt.alpha_max, float(data["alpha_t"]))))
            for e in data.get("error_history", [])[-500:]:
                filt.error_history.append(1 if int(e) > 0 else 0)
        except Exception:
            pass
    return filt


def save_conformal_filter(filt, path: Optional[str] = None) -> bool:
    """Atomically persist AdaptiveConformalFilter scores window & adaptive alpha_t."""
    target = path or DEFAULT_CONFORMAL_PATH
    return atomic_write_json(target, {
        "alpha_t": round(float(getattr(filt, "alpha_t", 0.18)), 5),
        "alpha_target": round(float(getattr(filt, "alpha_target", 0.18)), 5),
        "scores_window": [round(float(x), 5) for x in list(getattr(filt, "scores_window", []))[-100:]],
        "error_history": [int(x) for x in list(getattr(filt, "error_history", []))[-200:]],
        "updated_at": time.time(),
    })
