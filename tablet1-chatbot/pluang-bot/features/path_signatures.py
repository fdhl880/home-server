"""
Pilar 27 (T3.14) — Rough Path Theory: 2nd-Order Iterated Integrals & Lévy Area (A_{ij})
in Vectorized NumPy for Order-Flow Lead-Lag Causality Detection.

Formulas (Section 13.3 — Terry Lyons Rough Path Theory):
  For normalized multidimensional path X_t = (P_t, CVD_t, OI_t, OFI_t) in R^d on t in {0, ..., N}:
    - 1st-Order Signature:
          Delta X^i = X_N^i - X_0^i
    - 2nd-Order Iterated Integral Matrix (Trapezoidal Stratonovich / Discrete Rough Path):
          S^{(2)}_{ij} = sum_{k=1}^N (0.5 * (X_{k-1}^i + X_k^i) - X_0^i) * (X_k^j - X_{k-1}^j)
    - Anti-Symmetric Lévy Area (A_{ij} = 0.5 * (S^{(2)}_{ij} - S^{(2)}_{ji})):
          A_{ij} = 0.5 * sum_{k=1}^N [ (X_{k-1}^i - X_0^i)(X_k^j - X_{k-1}^j)
                                     - (X_{k-1}^j - X_0^j)(X_k^i - X_{k-1}^i) ]

Physical Interpretation:
  - `A_{CVD, P} > 0` (Counterclockwise in (CVD, P) plane):
    CVD rises *ahead of* price P, and price P follows -> Genuine Institutional Accumulation.
  - `A_{CVD, P} < 0` (Clockwise in (CVD, P) plane):
    Price P jumps first on a thin book, while CVD only chases later at the top -> Retail FOMO / Exhaustion Trap.
  - `A_{OI, P}`: Captures continuous leverage build-up vs. deleveraging flush rotation.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Union

import numpy as np


def _normalize_path_1d(arr: np.ndarray, normalize: bool = True) -> np.ndarray:
    x = np.asarray(arr, dtype=float)
    if len(x) == 0:
        return x
    shifted = x - x[0]
    if not normalize:
        return shifted
    scale = float(np.std(x))
    if scale < 1e-12:
        span = float(np.max(x) - np.min(x))
        scale = span if span > 1e-12 else 1.0
    return shifted / scale


def compute_levy_area(
    x_series: Sequence[float],
    y_series: Sequence[float],
    normalize: bool = True,
) -> float:
    """
    Compute the exact 2nd-order anti-symmetric Lévy Area A_{x, y} in O(N) vectorized numpy:
        A_{x, y} = 0.5 * sum_{k=1}^N [ (x_{k-1} - x_0)(y_k - y_{k-1}) - (y_{k-1} - y_0)(x_k - x_{k-1}) ]

    When path `x` leads path `y` (e.g. x(t) = sin(t), y(t) = sin(t - pi/2), so x rises first
    and y follows counterclockwise in the (x, y) plane), A_{x, y} > 0.
    When path `x` lags path `y` (clockwise traversal), A_{x, y} < 0.
    """
    x_raw = np.asarray(x_series, dtype=float)
    y_raw = np.asarray(y_series, dtype=float)
    n = min(len(x_raw), len(y_raw))
    if n < 2:
        return 0.0

    x = _normalize_path_1d(x_raw[-n:], normalize=normalize)
    y = _normalize_path_1d(y_raw[-n:], normalize=normalize)

    dx = np.diff(x)
    dy = np.diff(y)
    # Since x[0] == 0 and y[0] == 0 after origin-shifting:
    area = 0.5 * float(np.sum(x[:-1] * dy - y[:-1] * dx))
    return area


def compute_path_signatures(
    paths_matrix: Union[np.ndarray, Sequence[Sequence[float]]],
    normalize: bool = True,
) -> Dict[str, Any]:
    """
    Compute 1st-order increments Delta X, 2nd-order iterated integral matrix S^{(2)},
    and anti-symmetric Lévy Area matrix A for a multidimensional path X in R^{N x d}
    using vectorized NumPy matrix operations.
    """
    mat = np.asarray(paths_matrix, dtype=float)
    if mat.ndim == 1:
        mat = mat[:, None]
    n_steps, d_dim = mat.shape
    if n_steps < 2 or d_dim == 0:
        return {
            "sig1": np.zeros(d_dim, dtype=float),
            "sig2": np.zeros((d_dim, d_dim), dtype=float),
            "levy_area_matrix": np.zeros((d_dim, d_dim), dtype=float),
        }

    # Shift to origin X_0 = 0 and optionally normalize each coordinate by its std
    shifted = mat - mat[0:1, :]
    if normalize:
        stds = np.std(mat, axis=0, keepdims=True)
        spans = np.max(mat, axis=0, keepdims=True) - np.min(mat, axis=0, keepdims=True)
        scales = np.where(stds > 1e-12, stds, np.where(spans > 1e-12, spans, 1.0))
        path = shifted / scales
    else:
        path = shifted

    sig1 = path[-1, :].copy()
    d_path = np.diff(path, axis=0)          # shape (N-1, d)
    path_prev = path[:-1, :]                # shape (N-1, d)
    path_mid = 0.5 * (path[:-1, :] + path[1:, :])

    # Trapezoidal 2nd-order iterated integral matrix S^{(2)}_{ij}
    sig2 = path_mid.T @ d_path              # shape (d, d)

    # Exact discrete Lévy Area matrix A_{ij} = 0.5 * sum_k (X_{k-1}^i dX_k^j - X_{k-1}^j dX_k^i)
    cross = path_prev.T @ d_path
    levy_mat = 0.5 * (cross - cross.T)

    return {
        "sig1": sig1,
        "sig2": sig2,
        "levy_area_matrix": levy_mat,
    }


def compute_orderflow_levy_signatures(
    prices: Sequence[float],
    cvd_series: Sequence[float],
    oi_series: Optional[Sequence[float]] = None,
    ofi_series: Optional[Sequence[float]] = None,
    window: int = 24,
    normalize: bool = True,
) -> Dict[str, Any]:
    """
    Compute the key Rough Path Lévy Area signatures for order-flow & leverage causality (Section 13.3):
      1. `levy_area_cvd_price` (A_{CVD, P}):
         - > 0: CVD moved ahead of Price P -> Flow-Led Genuine Institutional Accumulation / Distribution.
         - < 0: Price P moved ahead of CVD -> Price-Led Retail FOMO / Exhaustion Trap.
      2. `levy_area_oi_price` (A_{OI, P}):
         - Measures leverage cycle rotation (whether OI expansion led price or lagged price).
      3. `levy_area_ofi_price` (A_{OFI, P}):
         - Measures passive/aggressive book flow lead-lag over price.
    """
    p_arr = np.asarray(prices, dtype=float)
    c_arr = np.asarray(cvd_series, dtype=float)
    n = min(len(p_arr), len(c_arr))
    if oi_series is not None:
        n = min(n, len(oi_series))
    if ofi_series is not None:
        n = min(n, len(ofi_series))

    if n < 3:
        return {
            "levy_area_cvd_price": 0.0,
            "levy_area_oi_price": 0.0,
            "levy_area_ofi_price": 0.0,
            "delta_p_norm": 0.0,
            "delta_cvd_norm": 0.0,
            "flow_led_move": False,
            "exhaustion_trap": False,
            "causality_regime": "NEUTRAL",
        }

    win = max(3, min(n, int(window)))
    p_seg = p_arr[-win:]
    c_seg = c_arr[-win:]
    oi_seg = np.asarray(oi_series[-win:], dtype=float) if oi_series is not None else np.zeros(win, dtype=float)
    ofi_seg = np.asarray(ofi_series[-win:], dtype=float) if ofi_series is not None else np.zeros(win, dtype=float)

    # Multidimensional path X_t = (P_t, CVD_t, OI_t, OFI_t)
    paths_mat = np.column_stack([p_seg, c_seg, oi_seg, ofi_seg])
    sig_res = compute_path_signatures(paths_mat, normalize=normalize)
    levy_mat = sig_res["levy_area_matrix"]
    sig1 = sig_res["sig1"]

    # Index 0 = P, Index 1 = CVD, Index 2 = OI, Index 3 = OFI
    # A_{CVD, P} is levy_mat[1, 0]
    a_cvd_p = float(levy_mat[1, 0])
    a_oi_p = float(levy_mat[2, 0]) if oi_series is not None else 0.0
    a_ofi_p = float(levy_mat[3, 0]) if ofi_series is not None else 0.0

    dp_norm = float(sig1[0])
    dcvd_norm = float(sig1[1])

    # Classify causal trajectory:
    # A_{CVD, P} > 0: CVD leads Price (counterclockwise in (CVD, P) plane) -> Flow-Led
    # A_{CVD, P} < 0: Price leads CVD (clockwise in (CVD, P) plane) -> Price-Led / Exhaustion Trap
    flow_led_move = bool(a_cvd_p > 0.05)
    exhaustion_trap = bool(a_cvd_p < -0.05)

    if a_cvd_p > 0.05 and dp_norm >= 0.0:
        regime = "FLOW_LED_GENUINE_ACCUMULATION"
    elif a_cvd_p > 0.05 and dp_norm < 0.0:
        regime = "FLOW_LED_BULLISH_ABSORPTION_REVERSAL"
    elif a_cvd_p < -0.05 and dp_norm >= 0.0:
        regime = "PRICE_LED_EXHAUSTION_TRAP"
    elif a_cvd_p < -0.05 and dp_norm < 0.0:
        regime = "PRICE_LED_PANIC_FLUSH_TRAP"
    else:
        regime = "NEUTRAL"

    return {
        "levy_area_cvd_price": float(a_cvd_p),
        "levy_area_oi_price": float(a_oi_p),
        "levy_area_ofi_price": float(a_ofi_p),
        "delta_p_norm": float(dp_norm),
        "delta_cvd_norm": float(dcvd_norm),
        "flow_led_move": flow_led_move,
        "exhaustion_trap": exhaustion_trap,
        "causality_regime": regime,
        "sig1": sig1.tolist(),
        "levy_area_matrix": levy_mat.tolist(),
    }
