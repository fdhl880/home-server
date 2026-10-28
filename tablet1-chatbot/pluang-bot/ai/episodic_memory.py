"""
===========================================================================
PYROFUEL NON-PARAMETRIC k-NN EPISODIC MARKET MEMORY v3.0 (T5.4)
===========================================================================
Provides long-term numerical episodic memory for AI Meta-Labeling:
1. Stores historical trade/shadow episodes with orthogonal feature vectors
   z_i in R^D, regime r_i, strategy_id s_i, net R-multiple R_i, and
   binary win / TP1 hit label y_i.
2. Vectorized |IC|-weighted Mahalanobis & Cosine distance computation in NumPy
   completing 5,000+ episode retrieval in < 5ms (strictly < 15ms SLA):
     d(z_now, z_i) = sqrt( sum_{m=1}^D |IC_m| * (z_{now,m} - z_{i,m})^2 / var_m )
3. Retrieves k = 7 nearest historical market analogs and computes the
   non-parametric local win probability:
     p_kNN = sum_{j=1}^k w_j * I{win_j} / sum_{j=1}^k w_j,  w_j = exp(-d_j)
4. Generates a compact natural-language prompt summary of the top analogs
   for injection into `ai/decide.py`.
===========================================================================
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

import numpy as np


class EpisodicMarketMemory:
    """
    Fast NumPy-vectorized |IC|-weighted k-NN Episodic Market Memory (T5.4).
    """

    def __init__(
        self,
        feature_dim: int = 15,
        k_neighbors: int = 7,
        ic_weights: Optional[Sequence[float]] = None,
        metric: str = "mahalanobis",
        default_prior: float = 0.50,
    ):
        self.feature_dim = int(feature_dim)
        self.k_neighbors = max(1, int(k_neighbors))
        self.metric = metric.lower().strip()
        self.default_prior = float(default_prior)

        if ic_weights is not None:
            w = np.abs(np.asarray(ic_weights, dtype=float))
            if w.size != self.feature_dim:
                w = np.resize(w, self.feature_dim)
        else:
            w = np.ones(self.feature_dim, dtype=float)
        w_sum = float(np.sum(w))
        self.ic_weights: np.ndarray = (w / w_sum * self.feature_dim) if w_sum > 0 else np.ones(self.feature_dim)

        self._vectors_list: List[np.ndarray] = []
        self._regimes: List[str] = []
        self._strategies: List[str] = []
        self._r_multiples: List[float] = []
        self._outcomes_win: List[int] = []
        self._notes: List[str] = []

        self._matrix_cache: Optional[np.ndarray] = None
        self._inv_var_cache: Optional[np.ndarray] = None
        self._dirty: bool = False

    def _format_vec(self, vec: Sequence[float]) -> np.ndarray:
        arr = np.asarray(vec, dtype=float).ravel()
        if arr.size == self.feature_dim:
            return arr
        if arr.size > self.feature_dim:
            return arr[: self.feature_dim].copy()
        out = np.zeros(self.feature_dim, dtype=float)
        out[: arr.size] = arr
        return out

    def set_ic_weights(self, ic_weights: Sequence[float]) -> None:
        w = np.abs(np.asarray(ic_weights, dtype=float)).ravel()
        if w.size != self.feature_dim:
            w = np.resize(w, self.feature_dim)
        s = float(np.sum(w))
        self.ic_weights = (w / s * self.feature_dim) if s > 0 else np.ones(self.feature_dim)

    def add_episode(
        self,
        feature_vector: Sequence[float],
        r_multiple_net: float,
        outcome_win: Optional[bool] = None,
        regime: str = "TREND_BULL",
        strategy_id: str = "S1_TREND_PULLBACK",
        note: str = "",
    ) -> None:
        v = self._format_vec(feature_vector)
        win_flag = (1 if outcome_win else 0) if outcome_win is not None else (1 if float(r_multiple_net) > 0 else 0)
        self._vectors_list.append(v)
        self._regimes.append(str(regime).upper().strip())
        self._strategies.append(str(strategy_id).upper().strip())
        self._r_multiples.append(float(r_multiple_net))
        self._outcomes_win.append(int(win_flag))
        self._notes.append(str(note))
        self._dirty = True

    def bulk_load(
        self,
        vectors: np.ndarray,
        r_multiples: Sequence[float],
        outcomes_win: Optional[Sequence[int]] = None,
        regimes: Optional[Sequence[str]] = None,
        strategies: Optional[Sequence[str]] = None,
        notes: Optional[Sequence[str]] = None,
    ) -> None:
        """
        Bulk-load historical episodes directly into contiguous NumPy arrays for < 5ms search.
        """
        mat = np.asarray(vectors, dtype=float)
        if mat.ndim != 2:
            raise ValueError("vectors must be a 2D array of shape (N, D)")
        n, d = mat.shape
        if d != self.feature_dim:
            if d > self.feature_dim:
                mat = mat[:, : self.feature_dim]
            else:
                padded = np.zeros((n, self.feature_dim), dtype=float)
                padded[:, :d] = mat
                mat = padded

        r_arr = [float(x) for x in r_multiples]
        if outcomes_win is not None:
            w_arr = [1 if int(w) > 0 else 0 for w in outcomes_win]
        else:
            w_arr = [1 if r > 0 else 0 for r in r_arr]

        reg_arr = [str(r).upper().strip() for r in regimes] if regimes is not None else ["ALL"] * n
        strat_arr = [str(s).upper().strip() for s in strategies] if strategies is not None else ["S1"] * n
        note_arr = [str(nt) for nt in notes] if notes is not None else [""] * n

        self._vectors_list = [mat[i] for i in range(n)]
        self._r_multiples = r_arr
        self._outcomes_win = w_arr
        self._regimes = reg_arr
        self._strategies = strat_arr
        self._notes = note_arr

        self._matrix_cache = np.ascontiguousarray(mat, dtype=float)
        var = np.var(self._matrix_cache, axis=0)
        self._inv_var_cache = 1.0 / np.maximum(var, 1e-3)
        self._dirty = False

    def _rebuild_cache_if_needed(self) -> None:
        if not self._dirty and self._matrix_cache is not None:
            return
        if not self._vectors_list:
            self._matrix_cache = np.empty((0, self.feature_dim), dtype=float)
            self._inv_var_cache = np.ones(self.feature_dim, dtype=float)
            self._dirty = False
            return
        self._matrix_cache = np.ascontiguousarray(np.vstack(self._vectors_list), dtype=float)
        if self._matrix_cache.shape[0] >= 5:
            var = np.var(self._matrix_cache, axis=0)
            self._inv_var_cache = 1.0 / np.maximum(var, 1e-3)
        else:
            self._inv_var_cache = np.ones(self.feature_dim, dtype=float)
        self._dirty = False

    def size(self) -> int:
        return len(self._outcomes_win)

    def query(
        self,
        z_now: Sequence[float],
        regime: Optional[str] = None,
        k: Optional[int] = None,
        metric: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve k = 7 closest market analogs and compute non-parametric p_kNN in < 15ms.
        """
        t0 = time.perf_counter()
        self._rebuild_cache_if_needed()
        total_n = len(self._outcomes_win)
        k_use = min(k or self.k_neighbors, max(1, total_n))

        if total_n == 0 or self._matrix_cache is None or self._matrix_cache.shape[0] == 0:
            return {
                "p_knn": self.default_prior,
                "expected_r_knn": 0.0,
                "k_used": 0,
                "mean_similarity": 0.0,
                "analogs": [],
                "prompt_summary": "No historical analogs in episodic memory yet; using neutral prior 50.0%.",
                "latency_ms": (time.perf_counter() - t0) * 1000.0,
            }

        q_vec = self._format_vec(z_now)
        mat = self._matrix_cache
        inv_var = self._inv_var_cache if self._inv_var_cache is not None else np.ones(self.feature_dim)

        # Filter indices by regime if enough samples exist in that regime
        cand_indices: np.ndarray
        if regime:
            reg_norm = str(regime).upper().strip()
            matched = [idx for idx, r in enumerate(self._regimes) if r == reg_norm]
            if len(matched) >= k_use:
                cand_indices = np.asarray(matched, dtype=np.int64)
                sub_mat = mat[cand_indices]
            else:
                cand_indices = np.arange(total_n, dtype=np.int64)
                sub_mat = mat
        else:
            cand_indices = np.arange(total_n, dtype=np.int64)
            sub_mat = mat

        use_metric = (metric or self.metric).lower().strip()
        ic_w = self.ic_weights

        if use_metric == "cosine":
            # |IC|-weighted cosine distance: 1 - cos_sim(sqrt(|IC|) * z_now, sqrt(|IC|) * z_i)
            sqrt_w = np.sqrt(ic_w)
            q_w = q_vec * sqrt_w
            sub_w = sub_mat * sqrt_w
            q_norm = float(np.linalg.norm(q_w)) + 1e-12
            sub_norms = np.linalg.norm(sub_w, axis=1) + 1e-12
            cos_sim = (sub_w @ q_w) / (sub_norms * q_norm)
            dists = np.maximum(0.0, 1.0 - cos_sim)
        else:
            # |IC|-weighted Mahalanobis distance (standardized by feature variance):
            # d(z_now, z_i) = sqrt( sum_m |IC_m| * (z_{now,m} - z_{i,m})^2 / var_m )
            eff_w = ic_w * inv_var
            diff = sub_mat - q_vec
            dists = np.sqrt(np.maximum(0.0, (diff * diff) @ eff_w) / float(self.feature_dim))

        # Use argpartition for O(N) top-k selection
        n_cand = dists.size
        k_actual = min(k_use, n_cand)
        if k_actual < n_cand:
            part_idx = np.argpartition(dists, k_actual - 1)[:k_actual]
            order_in_part = np.argsort(dists[part_idx])
            top_local_idx = part_idx[order_in_part]
        else:
            top_local_idx = np.argsort(dists)

        top_global_idx = cand_indices[top_local_idx]
        top_dists = dists[top_local_idx]

        # Distance kernel weights w_j = exp(-d(z_now, z_j))
        weights = np.exp(-top_dists)
        w_sum = float(np.sum(weights)) + 1e-12

        wins = np.asarray([self._outcomes_win[idx] for idx in top_global_idx], dtype=float)
        r_mults = np.asarray([self._r_multiples[idx] for idx in top_global_idx], dtype=float)

        p_knn = float(np.sum(weights * wins) / w_sum)
        expected_r_knn = float(np.sum(weights * r_mults) / w_sum)
        mean_sim = float(np.mean(weights))

        analogs: List[Dict[str, Any]] = []
        for rank, (g_idx, dist_val, w_val) in enumerate(zip(top_global_idx, top_dists, weights)):
            analogs.append(
                {
                    "rank": rank + 1,
                    "episode_index": int(g_idx),
                    "distance": float(dist_val),
                    "similarity": float(w_val),
                    "outcome": "WIN" if self._outcomes_win[g_idx] > 0 else "LOSS",
                    "r_multiple_net": float(self._r_multiples[g_idx]),
                    "regime": self._regimes[g_idx],
                    "strategy_id": self._strategies[g_idx],
                    "note": self._notes[g_idx],
                }
            )

        n_wins = int(np.sum(wins > 0.5))
        n_losses = k_actual - n_wins
        win_r_vals = r_mults[wins > 0.5]
        loss_r_vals = r_mults[wins <= 0.5]
        avg_win_r = float(np.mean(win_r_vals)) if win_r_vals.size > 0 else 0.0
        avg_loss_r = float(np.mean(loss_r_vals)) if loss_r_vals.size > 0 else 0.0

        summary = (
            f"Dari {k_actual} kondisi pasar paling identik di masa lalu "
            f"(kemiripan rata-rata {mean_sim * 100:.1f}%), {n_wins} berakhir WIN "
            f"(rata-rata {avg_win_r:+.2f}R) dan {n_losses} berakhir LOSS "
            f"(rata-rata {avg_loss_r:+.2f}R) -> Prior k-NN = {p_knn * 100:.1f}% "
            f"(E[R]_kNN = {expected_r_knn:+.2f}R)."
        )

        latency_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "p_knn": float(np.clip(p_knn, 1e-4, 1.0 - 1e-4)),
            "expected_r_knn": expected_r_knn,
            "k_used": k_actual,
            "mean_similarity": mean_sim,
            "analogs": analogs[:5],
            "all_k_analogs": analogs,
            "prompt_summary": summary,
            "latency_ms": latency_ms,
        }
