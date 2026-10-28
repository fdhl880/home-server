"""
===========================================================================
PYROFUEL NEURO-SYMBOLIC HYBRID AI ENSEMBLE v3.0 (T5.5 & T7.4)
===========================================================================
Implements the 3-Brain Co-Intelligence Stack:
1. Brain 1 — `TabularMetaModel` (Online L2-Regularized Logistic / Ridge Quant
   Classifier):
   - Trained specifically on binary Meta-Labeling target:
       Y = 1 iff price hits TP1 (+0.55R) before SL (-1.0R) and before T_max.
   - Supports batch Newton-IRLS L2 fit + incremental Online SGD with L2 penalty.
   - Outputs calibrated tabular probability `p_quant_ml` and top-3 positive &
     negative feature attributions (`w_j * z_j`).
2. Brain 2 — `EpisodicMarketMemory` (`p_knn`, T5.4):
   - Non-parametric distance-weighted prior from k=7 closest historical analogs.
3. Brain 3 — LLM Meta-Reasoner + Red-Team Auditor (`p_llm`, T5.1):
   - Contextual reasoning across signals; strictly enforces the AI-Only mandate.
4. Combination via Online Bayesian Log-Odds Pool:
     logit(p_hybrid) = w_ml * logit(p_quant_ml)
                     + w_knn * logit(p_knn)
                     + w_llm * logit(p_llm)
   with weights updated online via Exponential Brier-Loss Hedge:
     w_m^{(t+1)} proportional to w_m^{(t)} * exp(-eta * BrierLoss_m^{(t)})
   over the rolling window of 50 most recent trades.
===========================================================================
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

import numpy as np


def _clip_p(p: float, eps: float = 1e-4) -> float:
    return float(max(eps, min(1.0 - eps, float(p))))


def _logit(p: float) -> float:
    pc = _clip_p(p)
    return math.log(pc / (1.0 - pc))


def _sigmoid(z: float) -> float:
    zc = max(-30.0, min(30.0, float(z)))
    return 1.0 / (1.0 + math.exp(-zc))


class TabularMetaModel:
    """
    Online L2-Regularized Logistic / Ridge Quant Classifier trained specifically
    on hitting TP1 (+0.55R) before SL (-1.0R) and before vertical barrier T_max.
    """

    def __init__(
        self,
        feature_dim: int = 25,
        l2_penalty: float = 1.0,
        learning_rate: float = 0.05,
        tp1_trigger_r: float = 0.55,
        feature_names: Optional[Sequence[str]] = None,
    ):
        self.feature_dim = int(feature_dim)
        self.l2_penalty = float(l2_penalty)
        self.learning_rate = float(learning_rate)
        self.tp1_trigger_r = float(tp1_trigger_r)

        if feature_names is not None and len(feature_names) == self.feature_dim:
            self.feature_names = [str(f) for f in feature_names]
        else:
            self.feature_names = [f"factor_{i:02d}" for i in range(self.feature_dim)]

        self.weights: np.ndarray = np.zeros(self.feature_dim, dtype=float)
        self.bias: float = 0.0
        self.n_updates: int = 0

    def _format_x(self, x: Sequence[float]) -> np.ndarray:
        arr = np.asarray(x, dtype=float).ravel()
        if arr.size == self.feature_dim:
            return arr
        if arr.size > self.feature_dim:
            return arr[: self.feature_dim].copy()
        out = np.zeros(self.feature_dim, dtype=float)
        out[: arr.size] = arr
        return out

    def label_tp1_outcome(
        self,
        mfe_r: float,
        mae_r: float,
        hit_tp1_first: Optional[bool] = None,
        tp1_r: Optional[float] = None,
    ) -> int:
        """
        Compute binary target Y = 1 iff price reached +0.55R (TP1) before hitting SL (-1.0R).
        """
        if hit_tp1_first is not None:
            return 1 if hit_tp1_first else 0
        target_r = float(tp1_r) if tp1_r is not None else self.tp1_trigger_r
        if float(mfe_r) >= target_r and abs(float(mae_r)) < 1.0:
            return 1
        return 0

    def fit(
        self, X: np.ndarray, y: Sequence[int], max_iter: int = 50
    ) -> "TabularMetaModel":
        """
        Batch fit L2-regularized logistic regression via damped Newton-IRLS.
        """
        X_mat = np.asarray(X, dtype=float)
        if X_mat.ndim == 1:
            X_mat = X_mat.reshape(1, -1)
        n, d = X_mat.shape
        if d != self.feature_dim:
            if d > self.feature_dim:
                X_mat = X_mat[:, : self.feature_dim]
            else:
                pad = np.zeros((n, self.feature_dim), dtype=float)
                pad[:, :d] = X_mat
                X_mat = pad

        y_vec = np.asarray([1.0 if float(v) > 0.5 else 0.0 for v in y], dtype=float)
        if n == 0:
            return self

        w = np.zeros(self.feature_dim, dtype=float)
        b = _logit(float(np.clip(np.mean(y_vec), 0.05, 0.95)))
        reg = max(1e-4, self.l2_penalty)
        eye = np.eye(self.feature_dim, dtype=float)

        for _ in range(max_iter):
            logits = np.clip(X_mat @ w + b, -25.0, 25.0)
            probs = 1.0 / (1.0 + np.exp(-logits))
            diff = probs - y_vec
            s_vec = probs * (1.0 - probs) + 1e-6

            grad_w = (X_mat.T @ diff) + reg * w
            grad_b = float(np.sum(diff))

            # Hessian for weights: X^T diag(s) X + reg * I
            XS = X_mat * s_vec[:, None]
            H_w = (X_mat.T @ XS) + reg * eye
            try:
                step_w = np.linalg.solve(H_w, grad_w)
            except np.linalg.LinAlgError:
                step_w = grad_w / ( float(np.sum(s_vec)) + reg )

            step_b = grad_b / (float(np.sum(s_vec)) + 1e-6)
            w -= 0.7 * step_w
            b -= 0.7 * step_b

            if float(np.linalg.norm(step_w)) + abs(step_b) < 1e-5:
                break

        self.weights = w
        self.bias = float(b)
        self.n_updates += n
        return self

    def partial_fit(self, x: Sequence[float], y_tp1_hit: int) -> float:
        """
        Online Stochastic Gradient Descent update with L2 penalty on a single completed trade.
        Returns updated prediction on x.
        """
        x_vec = self._format_x(x)
        y_val = 1.0 if float(y_tp1_hit) > 0.5 else 0.0
        p_pred = self.predict_proba(x_vec)
        err = p_pred - y_val

        # Decaying learning rate schedule with floor
        lr = self.learning_rate / math.sqrt(1.0 + 0.01 * self.n_updates)
        reg_step = min(0.2, lr * self.l2_penalty / max(10.0, float(self.n_updates + 10)))

        self.weights = (1.0 - reg_step) * self.weights - lr * err * x_vec
        self.bias -= lr * err
        self.n_updates += 1
        return self.predict_proba(x_vec)

    def predict_proba(self, x: Sequence[float]) -> float:
        x_vec = self._format_x(x)
        z = float(np.dot(self.weights, x_vec) + self.bias)
        return _clip_p(_sigmoid(z))

    def predict_with_attribution(
        self, x: Sequence[float], feature_names: Optional[Sequence[str]] = None
    ) -> Dict[str, Any]:
        """
        Compute p_quant_ml and identify the top 3 positive and top 3 negative
        contributing features (w_j * x_j).
        """
        x_vec = self._format_x(x)
        names = (
            [str(f) for f in feature_names]
            if (feature_names is not None and len(feature_names) == self.feature_dim)
            else self.feature_names
        )
        contribs = self.weights * x_vec
        p_ml = self.predict_proba(x_vec)

        order = np.argsort(contribs)
        top_pos_idx = [int(i) for i in order[::-1][:3] if contribs[i] > 0]
        top_neg_idx = [int(i) for i in order[:3] if contribs[i] < 0]

        top_pos = [
            {"feature": names[i], "contribution": float(contribs[i]), "value": float(x_vec[i])}
            for i in top_pos_idx
        ]
        top_neg = [
            {"feature": names[i], "contribution": float(contribs[i]), "value": float(x_vec[i])}
            for i in top_neg_idx
        ]
        return {
            "p_quant_ml": p_ml,
            "logit_quant_ml": _logit(p_ml),
            "top_positive_features": top_pos,
            "top_negative_features": top_neg,
            "n_updates": self.n_updates,
        }


class NeuroSymbolicEnsemble:
    """
    Combines TabularMetaModel (p_quant_ml), EpisodicMarketMemory (p_knn),
    and LLM Meta-Reasoner (p_llm) via Online Bayesian Log-Odds Stacking
    with Exponential Brier-Loss Hedge weights (T5.5).
    """

    def __init__(
        self,
        tabular_model: Optional[TabularMetaModel] = None,
        initial_weights: Tuple[float, float, float] = (0.40, 0.25, 0.35),
        eta_hedge: float = 2.0,
        rolling_window: int = 50,
        min_weight_floor: float = 0.10,
    ):
        self.tabular_model = tabular_model or TabularMetaModel()
        w = np.asarray(initial_weights, dtype=float)
        w = w / np.sum(w)
        self.weights: Dict[str, float] = {
            "ml": float(w[0]),
            "knn": float(w[1]),
            "llm": float(w[2]),
        }
        self.eta_hedge = float(eta_hedge)
        self.rolling_window = max(5, int(rolling_window))
        self.min_weight_floor = float(min_weight_floor)

        # Rolling history of (p_ml, p_knn, p_llm, p_hybrid, y_true)
        self.history: Deque[Dict[str, float]] = deque(maxlen=self.rolling_window)

    def combine_probabilities(
        self, p_quant_ml: float, p_knn: float, p_llm: float
    ) -> Dict[str, Any]:
        """
        Combine the 3 brains in log-odds space:
          logit(p_hybrid) = w_ml * logit(p_quant_ml) + w_knn * logit(p_knn) + w_llm * logit(p_llm)
        """
        p_ml_c = _clip_p(p_quant_ml)
        p_knn_c = _clip_p(p_knn)
        p_llm_c = _clip_p(p_llm)

        w_ml = self.weights["ml"]
        w_knn = self.weights["knn"]
        w_llm = self.weights["llm"]

        logit_hybrid = (
            w_ml * _logit(p_ml_c)
            + w_knn * _logit(p_knn_c)
            + w_llm * _logit(p_llm_c)
        )
        p_hybrid = _clip_p(_sigmoid(logit_hybrid))

        return {
            "p_hybrid": p_hybrid,
            "logit_hybrid": logit_hybrid,
            "p_quant_ml": p_ml_c,
            "p_knn": p_knn_c,
            "p_llm": p_llm_c,
            "weights": dict(self.weights),
        }

    def update_from_outcome(
        self,
        p_quant_ml: float,
        p_knn: float,
        p_llm: float,
        outcome_tp1_win: bool,
        feature_vector: Optional[Sequence[float]] = None,
    ) -> Dict[str, Any]:
        """
        Update online ensemble weights using Exponential Brier-Loss Hedge on the rolling
        50-trade window and optionally update TabularMetaModel online.
        """
        y = 1.0 if outcome_tp1_win else 0.0
        combined = self.combine_probabilities(p_quant_ml, p_knn, p_llm)
        p_hyb = combined["p_hybrid"]

        self.history.append(
            {
                "ml": _clip_p(p_quant_ml),
                "knn": _clip_p(p_knn),
                "llm": _clip_p(p_llm),
                "hybrid": p_hyb,
                "y": y,
            }
        )

        # Online Hedge weight update: w_m^{(t+1)} \propto w_m^{(t)} * exp(-eta * BrierLoss_m^{(t)})
        loss_ml = (_clip_p(p_quant_ml) - y) ** 2
        loss_knn = (_clip_p(p_knn) - y) ** 2
        loss_llm = (_clip_p(p_llm) - y) ** 2

        raw_w = np.array(
            [
                self.weights["ml"] * math.exp(-self.eta_hedge * loss_ml),
                self.weights["knn"] * math.exp(-self.eta_hedge * loss_knn),
                self.weights["llm"] * math.exp(-self.eta_hedge * loss_llm),
            ],
            dtype=float,
        )
        raw_w = raw_w / np.sum(raw_w)
        # Apply floor so no brain is permanently zeroed out
        floor = self.min_weight_floor
        raw_w = np.maximum(raw_w, floor)
        raw_w = raw_w / np.sum(raw_w)

        self.weights = {
            "ml": float(raw_w[0]),
            "knn": float(raw_w[1]),
            "llm": float(raw_w[2]),
        }

        if feature_vector is not None and self.tabular_model is not None:
            self.tabular_model.partial_fit(feature_vector, int(y))

        return {
            "weights": dict(self.weights),
            "brier_losses_step": {"ml": loss_ml, "knn": loss_knn, "llm": loss_llm},
            "rolling_metrics": self.get_rolling_metrics(),
        }

    def get_rolling_metrics(self) -> Dict[str, Any]:
        if not self.history:
            return {"n": 0, "brier_ml": 0.0, "brier_knn": 0.0, "brier_llm": 0.0, "brier_hybrid": 0.0}
        y_arr = np.array([h["y"] for h in self.history], dtype=float)
        ml_arr = np.array([h["ml"] for h in self.history], dtype=float)
        knn_arr = np.array([h["knn"] for h in self.history], dtype=float)
        llm_arr = np.array([h["llm"] for h in self.history], dtype=float)
        hyb_arr = np.array([h["hybrid"] for h in self.history], dtype=float)

        return {
            "n": len(self.history),
            "brier_ml": float(np.mean((ml_arr - y_arr) ** 2)),
            "brier_knn": float(np.mean((knn_arr - y_arr) ** 2)),
            "brier_llm": float(np.mean((llm_arr - y_arr) ** 2)),
            "brier_hybrid": float(np.mean((hyb_arr - y_arr) ** 2)),
            "weights": dict(self.weights),
        }
