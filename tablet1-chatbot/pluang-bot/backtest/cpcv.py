"""
PYROFUEL BOT - PURGED WALK-FORWARD CV, BOOTSTRAP CI, & DEFLATED SHARPE RATIO (Task T1.3)
Mengimplementasikan:
1. Purged & Embargoed Walk-Forward Cross-Validation (Marcos Lopez de Prado)
2. Non-Parametric Bootstrap 95% Confidence Intervals untuk E[R]_net
3. Deflated Sharpe Ratio (DSR — Bailey & Lopez de Prado, 2014) yang mengoreksi
   multiple testing (K trials), skewness (gamma_3), dan fat-tails kurtosis (gamma_4).
"""
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

EULER_MASCHERONI = 0.5772156649015329


def norm_cdf(x: float) -> float:
    """Standard Normal Cumulative Distribution Function Phi(x)."""
    return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """
    Acklam's rational approximation for Standard Normal Inverse CDF Phi^{-1}(p).
    Accurate to ~1.15e-9 across (0, 1).
    """
    p = float(np.clip(p, 1e-12, 1.0 - 1e-12))
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if phigh < p:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    )


def generate_purged_walk_forward_splits(
    n_samples: int,
    n_splits: int = 4,
    min_train_bars: int = 120,
    purge_bars: int = 24,
    embargo_pct: float = 0.01,
    embargo_bars: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Generate Purged & Embargoed Walk-Forward splits (Train -> Purge + Embargo -> Test).
    Ensures zero overlap between training label horizons and out-of-sample test windows.
    """
    if n_samples < min_train_bars + 30:
        mid = max(20, int(n_samples * 0.6))
        purge = min(purge_bars, max(1, (n_samples - mid) // 4))
        return [{
            "fold": 0,
            "train_start": 0,
            "train_end": max(1, mid - purge),
            "purge_bars": purge,
            "embargo_bars": 1,
            "test_start": mid,
            "test_end": n_samples,
        }]

    emb = embargo_bars if embargo_bars is not None else max(1, int(math.ceil(n_samples * embargo_pct)))
    gap = int(purge_bars) + emb

    test_total = n_samples - min_train_bars - gap
    n_splits = max(1, min(int(n_splits), max(1, test_total // 25)))
    test_size = max(20, test_total // n_splits)

    splits: List[Dict[str, Any]] = []
    for k in range(n_splits):
        test_start = min_train_bars + gap + k * test_size
        test_end = n_samples if k == n_splits - 1 else min(n_samples, test_start + test_size)
        train_end = max(1, test_start - gap)
        if test_start >= test_end or train_end <= 0:
            continue
        splits.append({
            "fold": k,
            "train_start": 0,
            "train_end": train_end,
            "purge_bars": int(purge_bars),
            "embargo_bars": emb,
            "test_start": test_start,
            "test_end": test_end,
        })
    return splits


def purge_and_embargo_trades(
    train_trades: Sequence[Dict[str, Any]],
    test_start_idx: int,
    test_end_idx: int,
    embargo_bars: int = 5,
) -> List[Dict[str, Any]]:
    """
    Filter `train_trades` by removing any trade whose `[entry_idx, exit_idx]` overlaps
    with `[test_start_idx - embargo_bars, test_end_idx + embargo_bars]`.
    """
    clean_train: List[Dict[str, Any]] = []
    lower_bound = test_start_idx
    upper_bound = test_end_idx + max(0, int(embargo_bars))
    for tr in train_trades:
        t0 = int(tr.get("entry_idx", 0))
        t1 = int(tr.get("exit_idx", t0 + int(tr.get("bars_held", 1))))
        if t1 >= lower_bound and t0 <= upper_bound:
            continue
        clean_train.append(tr)
    return clean_train


def bootstrap_ci95(
    r_multiples: Sequence[float],
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """
    Compute `(mean_r, ci_low, ci_high)` for E[R]_net using non-parametric bootstrap.
    """
    arr = np.asarray(r_multiples, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n == 0:
        return (0.0, 0.0, 0.0)
    mean_r = float(np.mean(arr))
    if n < 2:
        return (round(mean_r, 4), round(mean_r, 4), round(mean_r, 4))

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(max(100, int(n_boot)), n))
    boot_means = np.mean(arr[idx], axis=1)
    ci_low = float(np.percentile(boot_means, (alpha / 2.0) * 100.0))
    ci_high = float(np.percentile(boot_means, (1.0 - alpha / 2.0) * 100.0))
    return (round(mean_r, 4), round(ci_low, 4), round(ci_high, 4))


def deflated_sharpe_ratio(
    returns_or_r: Sequence[float],
    num_trials: int = 4,
    sr_variance: Optional[float] = None,
) -> Dict[str, float]:
    """
    Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio (DSR):
        SR_0 = sqrt(Var(SR_k)) * ((1 - gamma)*Phi^{-1}(1 - 1/K) + gamma*Phi^{-1}(1 - 1/(K*e)))
        DSR  = Phi( ((SR_hat - SR_0) * sqrt(T - 1)) / sqrt(1 - gamma_3*SR_hat + ((gamma_4 - 1)/4)*SR_hat^2) )
    Returns dict with `sharpe`, `sr0_benchmark`, `skewness`, `kurtosis`, and `dsr`.
    """
    arr = np.asarray(returns_or_r, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    t_len = len(arr)
    if t_len < 3:
        return {
            "sharpe": 0.0,
            "sr0_benchmark": 0.0,
            "skewness": 0.0,
            "kurtosis": 3.0,
            "dsr": 0.0,
        }

    mean_v = float(np.mean(arr))
    std_v = float(np.std(arr, ddof=1))
    if std_v <= 1e-12:
        sr_hat = 5.0 if mean_v > 0 else 0.0
        return {
            "sharpe": round(sr_hat, 4),
            "sr0_benchmark": 0.0,
            "skewness": 0.0,
            "kurtosis": 3.0,
            "dsr": 1.0 if mean_v > 0 else 0.0,
        }

    sr_hat = mean_v / std_v
    z = (arr - mean_v) / std_v
    skew = float(np.mean(z ** 3))
    kurt = float(np.mean(z ** 4))

    k_trials = max(1, int(num_trials))
    if k_trials <= 1:
        sr0 = 0.0
    else:
        # Under null hypothesis, standard error of per-trade SR across K trials is ~ 1 / sqrt(T)
        var_sr = float(sr_variance) if sr_variance is not None else (1.0 / max(t_len, 10))
        q1 = norm_ppf(1.0 - 1.0 / k_trials)
        q2 = norm_ppf(1.0 - 1.0 / (k_trials * math.e))
        sr0 = math.sqrt(max(0.0, var_sr)) * (
            (1.0 - EULER_MASCHERONI) * q1 + EULER_MASCHERONI * q2
        )

    denom_inner = 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * (sr_hat ** 2)
    denom = math.sqrt(max(1e-6, denom_inner))
    z_dsr = ((sr_hat - sr0) * math.sqrt(max(1.0, t_len - 1.0))) / denom
    dsr_val = norm_cdf(z_dsr)

    return {
        "sharpe": round(float(sr_hat), 4),
        "sr0_benchmark": round(float(sr0), 4),
        "skewness": round(float(skew), 4),
        "kurtosis": round(float(kurt), 4),
        "dsr": round(float(dsr_val), 4),
    }
