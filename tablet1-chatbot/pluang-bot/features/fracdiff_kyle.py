"""
Pilar 11 (T3.7) — Fixed-Width Window Fractional Differentiation (FFD) & Kyle's Lambda Book Fragility.

Implements:
  1. `get_ffd_weights(d=0.35, thres=1e-4)` & `frac_diff_ffd(series, d=0.35, thres=1e-4)`:
     López de Prado Fixed-Width Window Fractional Differentiation with binomial weights:
         omega_0 = 1,  omega_k = -omega_{k-1} * (d - k + 1) / k
     truncated at |omega_k| < thres. Preserves > 0.80 correlation (long memory) with the
     underlying structural trend while achieving stationarity.
  2. `compute_kyles_lambda(prices, signed_volumes, window=20)`:
     Kyle's Lambda price-impact / order-book fragility estimator:
         lambda_{Kyle, t} = Cov_20(Delta P_i, SignedVol_i) / Var_20(SignedVol_i)
     along with rolling `fragility_zscore` and `is_book_fragile` flag (Z > +2.0).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

import numpy as np


def get_ffd_weights(d: float = 0.35, thres: float = 1e-4, max_len: int = 2000) -> np.ndarray:
    """
    Compute Fixed-Width Window Fractional Differentiation (FFD) weights:
        omega_0 = 1.0
        omega_k = -omega_{k-1} * (d - k + 1) / k
    stopping when |omega_k| < `thres` or len reaches `max_len`.
    """
    d_val = float(d)
    thres_val = max(float(thres), 1e-10)
    weights = [1.0]
    k = 1
    while k < max_len:
        w_k = -weights[-1] * (d_val - float(k) + 1.0) / float(k)
        if abs(w_k) < thres_val:
            break
        weights.append(w_k)
        k += 1
    return np.asarray(weights, dtype=float)


def frac_diff_ffd(
    series: Sequence[float],
    d: float = 0.35,
    thres: float = 1e-4,
    log_transform: bool = False,
) -> np.ndarray:
    """
    Apply Fixed-Width Window Fractional Differentiation (FFD) causally (zero lookahead)
    to `series` (or `log(series)` if `log_transform=True`).

    At each index t, uses only `series[max(0, t - K + 1) : t + 1]` anchored against `series[0]`
    so that:
      - Zero lookahead holds strictly at every index t (`frac_diff_ffd(x[:t+1])[-1] == frac_diff_ffd(x)[t]`).
      - No NaNs or artificial truncation boundary jumps occur on finite windows.
      - High structural memory correlation (> 0.80) and stationarity are simultaneously achieved.
    """
    arr = np.asarray(series, dtype=float)
    n = len(arr)
    if n == 0:
        return np.array([], dtype=float)
    if log_transform:
        arr = np.log(np.maximum(arr, 1e-12))

    weights = get_ffd_weights(d=d, thres=thres, max_len=max(n + 1, 2000))
    k_max = len(weights)

    # Anchor at initial value x_0 so expanding causal prefix up to k_max has zero level drift
    anchored = arr - arr[0]
    out = np.zeros(n, dtype=float)
    for t in range(n):
        w_len = min(t + 1, k_max)
        # weights[0] multiplies anchored[t], weights[1] multiplies anchored[t-1], ...
        seg = anchored[t - w_len + 1 : t + 1][::-1]
        out[t] = float(np.dot(weights[:w_len], seg))

    return out


def compute_fracdiff_features(
    prices: Sequence[float],
    oi_series: Optional[Sequence[float]] = None,
    d: float = 0.35,
    thres: float = 1e-4,
    z_window: int = 40,
) -> Dict[str, Any]:
    """
    Compute FFD-differentiated log-price (and optional log-OI) series, rolling z-score,
    and correlation with the original log-price series.
    """
    p_arr = np.asarray(prices, dtype=float)
    if len(p_arr) < 3:
        return {
            "d": float(d),
            "ffd_price": 0.0,
            "ffd_price_zscore": 0.0,
            "corr_with_log_price": 1.0,
            "ffd_oi": 0.0,
            "ffd_oi_zscore": 0.0,
            "ffd_series": [],
        }

    log_p = np.log(np.maximum(p_arr, 1e-12))
    ffd_p = frac_diff_ffd(log_p, d=d, thres=thres, log_transform=False)

    win = min(len(ffd_p), max(3, int(z_window)))
    seg = ffd_p[-win:]
    sd = float(np.std(seg))
    ffd_p_z = ((ffd_p[-1] - float(np.mean(seg))) / sd) if sd > 1e-12 else 0.0

    # Correlation between ffd_p and log_p
    lp_sd = float(np.std(log_p))
    fp_sd = float(np.std(ffd_p))
    if lp_sd > 1e-12 and fp_sd > 1e-12:
        corr = float(
            np.mean((log_p - np.mean(log_p)) * (ffd_p - np.mean(ffd_p))) / (lp_sd * fp_sd)
        )
    else:
        corr = 1.0

    ffd_oi_val = 0.0
    ffd_oi_z = 0.0
    if oi_series is not None and len(oi_series) >= 3:
        oi_arr = np.asarray(oi_series, dtype=float)
        log_oi = np.log(np.maximum(oi_arr, 1e-12))
        ffd_oi_arr = frac_diff_ffd(log_oi, d=d, thres=thres, log_transform=False)
        ffd_oi_val = float(ffd_oi_arr[-1])
        seg_oi = ffd_oi_arr[-min(len(ffd_oi_arr), win) :]
        sd_oi = float(np.std(seg_oi))
        ffd_oi_z = ((ffd_oi_val - float(np.mean(seg_oi))) / sd_oi) if sd_oi > 1e-12 else 0.0

    return {
        "d": float(d),
        "ffd_price": float(ffd_p[-1]),
        "ffd_price_zscore": float(ffd_p_z),
        "corr_with_log_price": float(np.clip(corr, -1.0, 1.0)),
        "ffd_oi": float(ffd_oi_val),
        "ffd_oi_zscore": float(ffd_oi_z),
        "ffd_series": [float(x) for x in ffd_p],
    }


def compute_kyles_lambda(
    prices: Sequence[float],
    signed_volumes: Sequence[float],
    window: int = 20,
    z_window: int = 60,
) -> Dict[str, Any]:
    """
    Compute Kyle's Lambda (Order Book Fragility & Price Impact Coefficient, Section 10.2 #4):
        lambda_{Kyle, t} = Cov_20(Delta P_i, SignedVol_i) / Var_20(SignedVol_i)

    Also computes rolling `fragility_zscore` (`kyle_lambda_zscore`).
    When `fragility_zscore > +2.0`, the order book is fragile (`is_book_fragile = True`),
    warning of high slippage and flash-wick risk.
    """
    p_arr = np.asarray(prices, dtype=float)
    sv_arr = np.asarray(signed_volumes, dtype=float)
    n = min(len(p_arr), len(sv_arr))
    if n < 3:
        return {
            "kyle_lambda": 0.0,
            "fragility_zscore": 0.0,
            "kyle_lambda_zscore": 0.0,
            "is_book_fragile": False,
            "kyle_lambda_series": [],
        }

    p_arr = p_arr[:n]
    sv_arr = sv_arr[:n]
    delta_p = np.concatenate(([0.0], np.diff(p_arr)))

    win = max(2, int(window))
    lambdas = np.zeros(n, dtype=float)

    for t in range(2, n):
        start = max(1, t - win + 1)
        dp_seg = delta_p[start : t + 1]
        sv_seg = sv_arr[start : t + 1]
        var_sv = float(np.var(sv_seg))
        if var_sv > 1e-12:
            cov = float(np.mean((dp_seg - np.mean(dp_seg)) * (sv_seg - np.mean(sv_seg))))
            lambdas[t] = cov / var_sv
        else:
            lambdas[t] = 0.0

    curr_lambda = float(lambdas[-1])
    valid_lambdas = lambdas[2:]
    z_seg = valid_lambdas[-min(len(valid_lambdas), max(5, int(z_window))) :]

    if len(z_seg) >= 3:
        # Compute z-score relative to prior readings if prior readings have variance
        prior = z_seg[:-1]
        mu_p = float(np.mean(prior))
        sd_p = float(np.std(prior))
        if sd_p > 1e-12:
            z_val = (curr_lambda - mu_p) / sd_p
        else:
            sd_all = float(np.std(z_seg))
            z_val = ((curr_lambda - float(np.mean(z_seg))) / sd_all) if sd_all > 1e-12 else 0.0
    else:
        z_val = 0.0

    is_fragile = bool(z_val > 2.0)

    return {
        "kyle_lambda": float(curr_lambda),
        "fragility_zscore": float(z_val),
        "kyle_lambda_zscore": float(z_val),
        "is_book_fragile": is_fragile,
        "kyle_lambda_series": [float(x) for x in lambdas],
    }
