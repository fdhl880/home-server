"""
===========================================================================
PYROFUEL ADAPTIVE CONFORMAL INFERENCE (ACI) FILTER v3.0 (T5.3)
===========================================================================
Gibbs & Candès (2021) Online Adaptive Conformal Inference for distribution-free
uncertainty quantification under regime shifts:
1. Non-conformity score for historical trade i with calibrated win probability
   p_i and binary outcome y_i in {1 ("WIN"), 0 ("LOSS")}:
     s_i = (1 - p_i) if y_i == 1 else p_i
2. Online adaptive miscoverage update (default alpha_target = 0.18 for
   HIGH_PRECISION_SNIPER_MODE, step size gamma = 0.03):
     alpha_{t+1} = clip(alpha_t + gamma * (alpha_target - err_t), 0.05, 0.45)
   where err_t = 1 if true label y_t not in C_hat_t else 0.
3. Empirical (time-weighted) quantile:
     q_hat_t = Quantile_{1 - alpha_t}({s_i}_{i=t-W}^{t-1})
4. Prediction set C_hat_t(p_cal) subset of {"WIN", "LOSS"}:
     - Include "WIN"  iff (1 - p_cal) <= q_hat_t
     - Include "LOSS" iff p_cal <= q_hat_t
5. Strict 20x ALL-IN Execution Gate:
     - Trade is allowed ONLY when C_hat_t == {"WIN"} (singleton win set).
     - Any other set ({"WIN", "LOSS"}, {"LOSS"}, or empty set) is vetoed with
       skip_reason = "SKIP_CONFORMAL_AMBIGUITY".
===========================================================================
"""
from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, Optional, Sequence, Set, Tuple

import numpy as np


class AdaptiveConformalFilter:
    """
    Gibbs & Candès Adaptive Conformal Inference (ACI) filter for 20x ALL-IN Sniper gating.
    """

    def __init__(
        self,
        alpha_target: float = 0.18,
        gamma: float = 0.03,
        window_size: int = 100,
        alpha_min: float = 0.05,
        alpha_max: float = 0.45,
        decay_weight: float = 0.985,
        warm_start_scores: Optional[Sequence[float]] = None,
    ):
        self.alpha_target = float(alpha_target)
        self.alpha_t = float(np.clip(alpha_target, alpha_min, alpha_max))
        self.gamma = float(gamma)
        self.window_size = max(10, int(window_size))
        self.alpha_min = float(alpha_min)
        self.alpha_max = float(alpha_max)
        self.decay_weight = float(decay_weight)

        self.scores_window: Deque[float] = deque(maxlen=self.window_size)
        self.error_history: Deque[int] = deque(maxlen=500)

        if warm_start_scores is not None:
            for s in warm_start_scores:
                self.scores_window.append(float(np.clip(s, 0.0, 1.0)))
        else:
            # Default calibrated prior scores centered around [0.12, 0.34] so
            # q_hat_{1 - 0.18} ~ 0.26 initially (requiring p_cal >= 0.74 for singleton {"WIN"})
            default_prior = np.linspace(0.08, 0.30, 25)
            for s in default_prior:
                self.scores_window.append(float(s))

    @staticmethod
    def nonconformity_score(p_cal: float, outcome_win: bool) -> float:
        """
        Compute non-conformity score s_i = 1 - p_cal (if WIN) else p_cal (if LOSS).
        """
        p = float(np.clip(p_cal, 1e-4, 1.0 - 1e-4))
        return (1.0 - p) if outcome_win else p

    def compute_quantile(self) -> float:
        """
        Compute time-weighted (1 - alpha_t) quantile q_hat_t over recent non-conformity scores.
        """
        if not self.scores_window:
            return 1.0 - self.alpha_t

        scores = np.asarray(self.scores_window, dtype=float)
        n = scores.size
        q_level = float(np.clip(1.0 - self.alpha_t, 0.01, 0.99))

        if self.decay_weight >= 0.9999 or n < 5:
            return float(np.quantile(scores, q_level))

        # Exponentially time-weighted quantile
        exponents = np.arange(n - 1, -1, -1, dtype=float)
        weights = np.power(self.decay_weight, exponents)
        order = np.argsort(scores, kind="mergesort")
        sorted_scores = scores[order]
        sorted_weights = weights[order]
        cdf = np.cumsum(sorted_weights) / np.sum(sorted_weights)
        idx = int(np.searchsorted(cdf, q_level, side="left"))
        idx = min(max(idx, 0), n - 1)
        return float(sorted_scores[idx])

    def predict_set(self, p_cal: float) -> Set[str]:
        """
        Construct conformal prediction set C_hat_t(p_cal) subset of {"WIN", "LOSS"}.
        """
        p = float(np.clip(p_cal, 1e-4, 1.0 - 1e-4))
        q_hat = self.compute_quantile()
        pred_set: Set[str] = set()
        if (1.0 - p) <= q_hat + 1e-12:
            pred_set.add("WIN")
        if p <= q_hat + 1e-12:
            pred_set.add("LOSS")
        return pred_set

    def evaluate_gate(self, p_cal: float) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Evaluate Conformal Execution Gate:
        Allows trade ONLY if C_hat_t == {"WIN"}.
        Vetoes whenever C_hat_t != {"WIN"} with skip_reason = "SKIP_CONFORMAL_AMBIGUITY".
        """
        q_hat = self.compute_quantile()
        c_hat = self.predict_set(p_cal)
        is_singleton_win = c_hat == {"WIN"}
        skip_reason = "" if is_singleton_win else "SKIP_CONFORMAL_AMBIGUITY"
        info = {
            "p_cal": float(p_cal),
            "alpha_t": float(self.alpha_t),
            "alpha_target": float(self.alpha_target),
            "q_hat": float(q_hat),
            "prediction_set": sorted(list(c_hat)),
            "allowed": is_singleton_win,
            "skip_reason": skip_reason,
        }
        return is_singleton_win, skip_reason, info

    def update(self, p_cal: float, outcome_win: bool) -> Dict[str, Any]:
        """
        Online Gibbs & Candès ACI step:
          err_t = 1 if true_label not in C_hat_t(p_cal) else 0
          alpha_{t+1} = clip(alpha_t + gamma * (alpha_target - err_t), 0.05, 0.45)
        Then appends realized non-conformity score s_t to rolling window.
        """
        true_label = "WIN" if outcome_win else "LOSS"
        c_hat = self.predict_set(p_cal)
        err_t = 0 if true_label in c_hat else 1

        alpha_prev = self.alpha_t
        self.alpha_t = float(
            np.clip(
                self.alpha_t + self.gamma * (self.alpha_target - float(err_t)),
                self.alpha_min,
                self.alpha_max,
            )
        )
        s_t = self.nonconformity_score(p_cal, outcome_win)
        self.scores_window.append(float(s_t))
        self.error_history.append(int(err_t))

        empirical_coverage = (
            1.0 - float(np.mean(self.error_history)) if self.error_history else 1.0 - self.alpha_target
        )
        return {
            "true_label": true_label,
            "prediction_set": sorted(list(c_hat)),
            "err_t": err_t,
            "s_t": s_t,
            "alpha_prev": alpha_prev,
            "alpha_next": self.alpha_t,
            "empirical_coverage": empirical_coverage,
        }


class SplitConformalGate(AdaptiveConformalFilter):
    def __init__(self, alpha: float = 0.18, **kwargs):
        super().__init__(alpha_target=alpha, **kwargs)
