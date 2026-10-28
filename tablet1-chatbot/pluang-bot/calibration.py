"""
===========================================================================
PYROFUEL PROBABILITY CALIBRATOR & NET EV ENGINE v3.0 (T5.2)
===========================================================================
Implements:
1. Empirical Base-Rate Bayesian Shrinkage:
     p_cal = (n * p_iso(p_raw) + n_0 * p_base(setup, regime)) / (n + n_0)
   with default prior strength n_0 = 25.0.
2. Isotonic Regression (Pool Adjacent Violators Algorithm — PAVA) &
   Platt Scaling (1D Logistic Calibration) over historical (p_raw, y) pairs,
   specifically supporting target Y = 1 for hitting TP1 (+0.55R) before SL
   as well as full Triple-Barrier win outcomes.
3. Rolling & Cumulative Brier Score Tracker:
     BS = (1 / N) * sum((p_i - y_i)^2)
4. Net Expected Value (EV_R) & Breakeven Win-Rate Gate:
     c_roundtrip = 2 * f_fee + s_slippage + f_funding_est
     RRR_net = (d_TP - c_roundtrip) / (d_SL + c_roundtrip)
     EV_R = p_cal * RRR_net - (1 - p_cal) * 1.0
     Requires EV_R >= +0.20R and p_cal >= p_breakeven + 0.05.
===========================================================================
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


def _clip_prob(p: float, eps: float = 1e-4) -> float:
    return float(max(eps, min(1.0 - eps, float(p))))


def _logit(p: float) -> float:
    p_c = _clip_prob(p)
    return math.log(p_c / (1.0 - p_c))


def _sigmoid(z: float) -> float:
    z_c = max(-30.0, min(30.0, float(z)))
    return 1.0 / (1.0 + math.exp(-z_c))


def fit_isotonic_pava(
    x_raw: Sequence[float], y_true: Sequence[float]
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Pool Adjacent Violators Algorithm (PAVA) for non-decreasing Isotonic Regression.
    Returns (knots_x, knots_y) suitable for piecewise linear interpolation (`np.interp`).
    """
    x_arr = np.asarray(x_raw, dtype=float)
    y_arr = np.asarray(y_true, dtype=float)
    if x_arr.size == 0:
        return np.array([0.0, 1.0]), np.array([0.0, 1.0])

    order = np.argsort(x_arr, kind="mergesort")
    x_sorted = x_arr[order]
    y_sorted = y_arr[order]

    # Each block stores: [sum_y, count, min_x, max_x]
    blocks: List[List[float]] = []
    for xi, yi in zip(x_sorted, y_sorted):
        blocks.append([float(yi), 1.0, float(xi), float(xi)])
        while len(blocks) >= 2:
            mean_prev = blocks[-2][0] / blocks[-2][1]
            mean_curr = blocks[-1][0] / blocks[-1][1]
            if mean_prev > mean_curr:
                # Pool adjacent violators
                b_curr = blocks.pop()
                blocks[-1][0] += b_curr[0]
                blocks[-1][1] += b_curr[1]
                blocks[-1][2] = min(blocks[-1][2], b_curr[2])
                blocks[-1][3] = max(blocks[-1][3], b_curr[3])
            else:
                break

    knots_x: List[float] = []
    knots_y: List[float] = []
    for b in blocks:
        val = _clip_prob(b[0] / b[1], eps=0.01)
        mid_x = 0.5 * (b[2] + b[3])
        knots_x.append(mid_x)
        knots_y.append(val)

    return np.asarray(knots_x, dtype=float), np.asarray(knots_y, dtype=float)


def fit_platt_scaling(
    x_raw: Sequence[float], y_true: Sequence[float], l2_reg: float = 0.05, max_iter: int = 80
) -> Tuple[float, float]:
    """
    Fit Platt scaling parameters (a, b) such that p_hat = sigmoid(a * logit(p_raw) + b).
    Uses damped Newton-Raphson with L2 regularization.
    """
    x_arr = np.asarray([_logit(p) for p in x_raw], dtype=float)
    y_arr = np.asarray(y_true, dtype=float)
    n = x_arr.size
    if n < 4:
        return 1.0, 0.0

    # Target regularization (Platt's Bayes prior smoothing to prevent +/- inf)
    n_pos = float(np.sum(y_arr > 0.5))
    n_neg = float(n - n_pos)
    t_pos = (n_pos + 1.0) / (n_pos + 2.0)
    t_neg = 1.0 / (n_neg + 2.0)
    targets = np.where(y_arr > 0.5, t_pos, t_neg)

    a, b = 1.0, 0.0
    for _ in range(max_iter):
        z = np.clip(a * x_arr + b, -25.0, 25.0)
        p = 1.0 / (1.0 + np.exp(-z))
        diff = p - targets
        w = p * (1.0 - p) + 1e-6

        g_a = float(np.sum(diff * x_arr) + l2_reg * (a - 1.0))
        g_b = float(np.sum(diff) + l2_reg * b)

        h_aa = float(np.sum(w * x_arr * x_arr) + l2_reg)
        h_ab = float(np.sum(w * x_arr))
        h_bb = float(np.sum(w) + l2_reg)

        det = h_aa * h_bb - h_ab * h_ab
        if abs(det) < 1e-9:
            break
        da = (h_bb * g_a - h_ab * g_b) / det
        db = (h_aa * g_b - h_ab * g_a) / det

        a -= 0.5 * da
        b -= 0.5 * db
        # Enforce non-negative slope so higher p_raw never maps to lower calibrated prob
        a = max(0.05, min(5.0, a))
        b = max(-5.0, min(5.0, b))
        if abs(da) + abs(db) < 1e-5:
            break

    return float(a), float(b)


class ProbabilityCalibrator:
    """
    Calibrates raw AI/ensemble probabilities via:
      1. Isotonic Regression (PAVA) and Platt Scaling over historical outcomes
      2. Empirical Base-Rate Bayesian Shrinkage:
           p_cal = (n * p_iso(p_raw) + n_0 * p_base(setup, regime)) / (n + n_0)
      3. Net Expected Value (EV_R) & Breakeven Win-Rate gate.
    """

    def __init__(
        self,
        n0_prior: float = 25.0,
        method: str = "isotonic",
        min_ev_r: float = 0.20,
        min_edge_over_breakeven: float = 0.05,
        default_base_rate: float = 0.48,
    ):
        self.n0_prior = float(n0_prior)
        self.method = method.lower().strip()
        self.min_ev_r = float(min_ev_r)
        self.min_edge_over_breakeven = float(min_edge_over_breakeven)
        self.default_base_rate = _clip_prob(default_base_rate)

        # Base-rate table keyed by (strategy_id, regime): {"p_base": float, "n": int}
        self.base_rates: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # Historical calibration samples: list of (p_raw, y_binary, p_cal_at_pred)
        self.history_p_raw: List[float] = []
        self.history_y: List[int] = []
        self.history_p_cal: List[float] = []

        # Fitted parameters
        self._iso_knots_x: np.ndarray = np.array([0.0, 1.0])
        self._iso_knots_y: np.ndarray = np.array([0.0, 1.0])
        self._platt_a: float = 1.0
        self._platt_b: float = 0.0
        self._is_fitted: bool = False

    def set_empirical_base_rate(
        self, strategy_id: str, regime: str, p_base: float, historical_n: int = 50
    ) -> None:
        key = (str(strategy_id).upper().strip(), str(regime).upper().strip())
        self.base_rates[key] = {
            "p_base": _clip_prob(p_base),
            "n": max(0, int(historical_n)),
        }

    def get_empirical_base_rate(
        self, strategy_id: Optional[str] = None, regime: Optional[str] = None, explicit_p_base: Optional[float] = None
    ) -> float:
        if explicit_p_base is not None:
            return _clip_prob(explicit_p_base)
        if strategy_id and regime:
            key = (str(strategy_id).upper().strip(), str(regime).upper().strip())
            if key in self.base_rates:
                return float(self.base_rates[key]["p_base"])
        if strategy_id:
            s_key = str(strategy_id).upper().strip()
            matches = [v["p_base"] for (s, _), v in self.base_rates.items() if s == s_key]
            if matches:
                return float(np.mean(matches))
        if self.history_y:
            return _clip_prob(float(np.mean(self.history_y)))
        return self.default_base_rate

    def fit(self, p_raw_seq: Sequence[float], y_true_seq: Sequence[int]) -> "ProbabilityCalibrator":
        """
        Fit Isotonic (PAVA) and Platt scaling parameters on historical (p_raw, y_true) pairs.
        """
        if len(p_raw_seq) != len(y_true_seq):
            raise ValueError("p_raw_seq and y_true_seq must have identical length")
        self.history_p_raw = [_clip_prob(p) for p in p_raw_seq]
        self.history_y = [1 if float(y) > 0.5 else 0 for y in y_true_seq]
        self._refit_internal()
        self.history_p_cal = [
            self.calibrate(p, sample_count=len(self.history_y)) for p in self.history_p_raw
        ]
        return self

    def record_outcome(
        self,
        p_raw: float,
        outcome_win: bool,
        strategy_id: Optional[str] = None,
        regime: Optional[str] = None,
        p_cal_used: Optional[float] = None,
    ) -> float:
        """
        Append a single realized trade outcome (e.g., hitting TP1 before SL) and refit online.
        """
        p_r = _clip_prob(p_raw)
        y_val = 1 if outcome_win else 0
        if p_cal_used is None:
            p_cal_used = self.calibrate(p_r, strategy_id=strategy_id, regime=regime)

        self.history_p_raw.append(p_r)
        self.history_y.append(y_val)
        self.history_p_cal.append(_clip_prob(p_cal_used))
        self._refit_internal()
        return float(p_cal_used)

    def _refit_internal(self) -> None:
        n = len(self.history_y)
        if n < 5:
            self._is_fitted = False
            return
        self._iso_knots_x, self._iso_knots_y = fit_isotonic_pava(
            self.history_p_raw, self.history_y
        )
        self._platt_a, self._platt_b = fit_platt_scaling(
            self.history_p_raw, self.history_y
        )
        self._is_fitted = True

    def predict_unshrunk(self, p_raw: float) -> float:
        """
        Evaluate p_hat_iso(p_raw) or p_hat_platt(p_raw) before Bayesian shrinkage.
        """
        p_r = _clip_prob(p_raw)
        if not self._is_fitted:
            return p_r

        p_iso = float(np.interp(p_r, self._iso_knots_x, self._iso_knots_y))
        p_platt = _sigmoid(self._platt_a * _logit(p_r) + self._platt_b)

        if self.method == "platt":
            return _clip_prob(p_platt)
        elif self.method == "blend":
            return _clip_prob(0.65 * p_iso + 0.35 * p_platt)
        return _clip_prob(p_iso)

    def calibrate(
        self,
        p_raw: float,
        strategy_id: Optional[str] = None,
        regime: Optional[str] = None,
        explicit_p_base: Optional[float] = None,
        sample_count: Optional[int] = None,
    ) -> float:
        """
        Compute calibrated probability with Empirical Base-Rate Bayesian Shrinkage:
          p_cal = (n * p_iso(p_raw) + n_0 * p_base) / (n + n_0)
        """
        p_r = _clip_prob(p_raw)
        n = len(self.history_y) if sample_count is None else max(0, int(sample_count))
        p_base = self.get_empirical_base_rate(
            strategy_id=strategy_id, regime=regime, explicit_p_base=explicit_p_base
        )

        if self._is_fitted and n >= 5:
            p_iso = self.predict_unshrunk(p_r)
        else:
            # When live calibration sample is tiny, dampen extreme raw confidence toward base rate
            p_iso = 0.5 * p_r + 0.5 * p_base

        n0 = max(1e-6, self.n0_prior)
        p_cal = (n * p_iso + n0 * p_base) / (n + n0)
        return _clip_prob(p_cal)

    @staticmethod
    def compute_ev_and_rrr_net(
        p_cal: float,
        d_sl: float,
        d_tp: float,
        fee_rate_per_side: float = 0.0004,
        slippage_rate: float = 0.0003,
        funding_rate_est: float = 0.0,
    ) -> Dict[str, float]:
        """
        Compute net RRR, cost in R, breakeven win-rate, and Net Expected Value EV_R.
        Note: d_sl and d_tp can be passed either as decimal fractions (e.g. 0.008 for 0.8%)
        or percentages (e.g. 0.8 for 0.8%) — automatically normalized to decimal fractions.
        """
        sl_frac = float(d_sl) / 100.0 if float(d_sl) > 0.15 else float(d_sl)
        tp_frac = float(d_tp) / 100.0 if float(d_tp) > 0.15 else float(d_tp)
        sl_frac = max(1e-5, sl_frac)
        tp_frac = max(1e-5, tp_frac)

        roundtrip_cost = 2.0 * float(fee_rate_per_side) + float(slippage_rate) + float(funding_rate_est)
        cost_r = roundtrip_cost / sl_frac
        rrr_gross = tp_frac / sl_frac
        rrr_net = max(0.0, (tp_frac - roundtrip_cost) / (sl_frac + roundtrip_cost))
        p_be = 1.0 / (1.0 + rrr_net) if rrr_net > 0 else 1.0
        ev_r = float(p_cal) * rrr_net - (1.0 - float(p_cal)) * 1.0

        return {
            "p_cal": float(p_cal),
            "d_sl_frac": sl_frac,
            "d_tp_frac": tp_frac,
            "roundtrip_cost_frac": roundtrip_cost,
            "cost_r": cost_r,
            "rrr_gross": rrr_gross,
            "rrr_net": rrr_net,
            "p_breakeven": p_be,
            "ev_r": ev_r,
        }

    def evaluate_ev_gate(
        self,
        p_cal: float,
        d_sl: float,
        d_tp: float,
        fee_rate_per_side: float = 0.0004,
        slippage_rate: float = 0.0003,
        funding_rate_est: float = 0.0,
    ) -> Tuple[bool, str, Dict[str, float]]:
        """
        Evaluate mandatory Net EV Gate:
          EV_R >= +0.20R AND p_cal >= p_breakeven + 0.05
        """
        metrics = self.compute_ev_and_rrr_net(
            p_cal=p_cal,
            d_sl=d_sl,
            d_tp=d_tp,
            fee_rate_per_side=fee_rate_per_side,
            slippage_rate=slippage_rate,
            funding_rate_est=funding_rate_est,
        )
        ev_r = metrics["ev_r"]
        p_be = metrics["p_breakeven"]

        if ev_r < self.min_ev_r:
            return (
                False,
                f"SKIP_LOW_EV_R (EV_R={ev_r:.3f}R < {self.min_ev_r:.2f}R)",
                metrics,
            )
        if p_cal < p_be + self.min_edge_over_breakeven:
            return (
                False,
                f"SKIP_BELOW_BREAKEVEN_MARGIN (p_cal={p_cal:.3f} < p_be+0.05={p_be + self.min_edge_over_breakeven:.3f})",
                metrics,
            )
        return True, "PASS_EV_GATE", metrics

    def brier_score_summary(self) -> Dict[str, Any]:
        """
        Compute Brier Score for raw vs calibrated predictions over recorded history.
        """
        n = len(self.history_y)
        if n == 0:
            return {"n": 0, "brier_raw": 0.0, "brier_calibrated": 0.0, "improvement": 0.0}
        y_arr = np.asarray(self.history_y, dtype=float)
        raw_arr = np.asarray(self.history_p_raw, dtype=float)
        cal_arr = np.asarray(
            [self.calibrate(p, sample_count=n) for p in self.history_p_raw], dtype=float
        )
        bs_raw = float(np.mean((raw_arr - y_arr) ** 2))
        bs_cal = float(np.mean((cal_arr - y_arr) ** 2))
        return {
            "n": n,
            "brier_raw": bs_raw,
            "brier_calibrated": bs_cal,
            "improvement": bs_raw - bs_cal,
        }

    def calibrate_prob(self, p_raw: float, **kwargs) -> float:
        return self.calibrate(p_raw, **kwargs)


IsotonicCalibrator = ProbabilityCalibrator
