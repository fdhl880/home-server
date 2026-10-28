"""
PYROFUEL BOT - STATISTICAL REGIME CLASSIFIER (Pilar 3 / Task T4.1)
Mengklasifikasikan rezim pasar secara kuantitatif menggunakan:
1. Hurst Exponent (H) via Variogram / Rescaled Range
2. Lo-MacKinlay Heteroskedastic Variance Ratio VR(q) & z*-stat
3. Yang-Zhang Realized Volatility Estimator & Rolling 30d Percentile
4. Wilder's ADX(14) & Directional Movement (+DI / -DI)
States: TREND_BULL | TREND_BEAR | MEAN_REVERT | CASCADE_EXHAUSTION | CHOP_NO_TRADE
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


def _extract_ohlcv(klines: Any) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Extract (opens, highs, lows, closes, volumes) numpy float64 arrays from:
    - list of dicts [{'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}]
    - list of lists/tuples [[open_time, open, high, low, close, volume, ...]]
    - dict of arrays / DataFrame-like mapping {'open': ..., 'high': ..., 'low': ..., 'close': ...}
    """
    if klines is None:
        empty = np.array([], dtype=np.float64)
        return empty, empty, empty, empty, empty

    if hasattr(klines, "to_dict") or isinstance(klines, dict):
        d = klines
        closes = np.asarray(d["close"], dtype=np.float64)
        opens = np.asarray(d.get("open", closes), dtype=np.float64)
        highs = np.asarray(d.get("high", closes), dtype=np.float64)
        lows = np.asarray(d.get("low", closes), dtype=np.float64)
        vols = np.asarray(d.get("volume", np.ones_like(closes)), dtype=np.float64)
        return opens, highs, lows, closes, vols

    if isinstance(klines, (list, tuple, np.ndarray)):
        if len(klines) == 0:
            empty = np.array([], dtype=np.float64)
            return empty, empty, empty, empty, empty
        first = klines[0]
        if isinstance(first, dict):
            opens = np.array([float(k.get("open", k.get("close", 0.0))) for k in klines], dtype=np.float64)
            highs = np.array([float(k.get("high", k.get("close", 0.0))) for k in klines], dtype=np.float64)
            lows = np.array([float(k.get("low", k.get("close", 0.0))) for k in klines], dtype=np.float64)
            closes = np.array([float(k.get("close", 0.0)) for k in klines], dtype=np.float64)
            vols = np.array([float(k.get("volume", 0.0)) for k in klines], dtype=np.float64)
            return opens, highs, lows, closes, vols
        elif isinstance(first, (list, tuple, np.ndarray)) and len(first) >= 5:
            opens = np.array([float(k[1]) for k in klines], dtype=np.float64)
            highs = np.array([float(k[2]) for k in klines], dtype=np.float64)
            lows = np.array([float(k[3]) for k in klines], dtype=np.float64)
            closes = np.array([float(k[4]) for k in klines], dtype=np.float64)
            vols = np.array([float(k[5]) if len(k) > 5 else 0.0 for k in klines], dtype=np.float64)
            return opens, highs, lows, closes, vols
        else:
            closes = np.asarray(klines, dtype=np.float64)
            return closes.copy(), closes.copy(), closes.copy(), closes, np.ones_like(closes)

    empty = np.array([], dtype=np.float64)
    return empty, empty, empty, empty, empty


def hurst_exponent(close_series: Sequence[float], max_lag: int = 20) -> float:
    """
    Calculate Hurst Exponent H via log-price variogram scaling:
        Var(tau) = <|log(P_{t+tau}) - log(P_t)|^2> ~ tau^(2H)
    - H > 0.55: Persistent / Trending
    - H < 0.45: Anti-Persistent / Mean-Reverting
    - 0.45 <= H <= 0.55: Geometric Brownian Walk / Noise
    """
    closes = np.asarray(close_series, dtype=np.float64)
    closes = closes[np.isfinite(closes) & (closes > 0)]
    n = len(closes)
    if n < 20:
        return 0.50

    log_p = np.log(closes[-min(n, 150):])
    upper_lag = min(max_lag, len(log_p) // 3)
    if upper_lag < 4:
        return 0.50

    lags = np.arange(1, upper_lag + 1, dtype=np.float64)
    tau_stds = []
    valid_lags = []

    # Check if series has statistically significant directional drift (|t-stat| > 2.2)
    r1 = np.diff(log_p)
    r1_std = float(np.std(r1))
    drift_tstat = abs(float(np.mean(r1))) * np.sqrt(len(r1)) / max(r1_std, 1e-12)
    drift_weight = 1.0 if drift_tstat >= 2.2 else 0.0

    for lag in lags:
        k = int(lag)
        diffs = log_p[k:] - log_p[:-k]
        centered_var = float(np.var(diffs))
        mean_diff = float(np.mean(diffs))
        rms = float(np.sqrt(centered_var + drift_weight * (mean_diff ** 2)))
        if rms > 1e-12:
            tau_stds.append(rms)
            valid_lags.append(float(k))

    if len(valid_lags) < 3:
        return 0.50

    lx = np.log(np.asarray(valid_lags, dtype=np.float64))
    ly = np.log(np.asarray(tau_stds, dtype=np.float64))
    lx_m = lx - np.mean(lx)
    denom = float(np.dot(lx_m, lx_m))
    h = float(np.dot(lx_m, ly - np.mean(ly)) / denom) if denom > 1e-12 else 0.50
    return round(float(np.clip(h, 0.05, 0.95)), 4)


def variance_ratio(close_series: Sequence[float], lag: int = 4) -> Tuple[float, float]:
    """
    Lo-MacKinlay (1988) Variance Ratio VR(q) and heteroskedasticity-consistent z*-statistic.
    Returns (vr_q, z_stat).
    - VR(q) > 1.12: Positive autocorrelation (Trending)
    - VR(q) < 0.88: Negative autocorrelation (Mean-Reverting)
    """
    closes = np.asarray(close_series, dtype=np.float64)
    closes = closes[np.isfinite(closes) & (closes > 0)]
    q = max(2, int(lag))
    if len(closes) < max(20, q * 3 + 2):
        return (1.0, 0.0)

    x = np.log(closes[-min(len(closes), 200):])
    n = len(x) - 1
    if n <= q:
        return (1.0, 0.0)

    mu = (x[-1] - x[0]) / n
    r1 = np.diff(x) - mu
    denom_sum = float(np.sum(r1 ** 2))
    if denom_sum <= 1e-18:
        return (1.0, 0.0)

    sigma_a2 = denom_sum / (n - 1)
    rq = (x[q:] - x[:-q]) - q * mu
    m = q * (n - q + 1) * (1.0 - q / n)
    if m <= 0 or sigma_a2 <= 1e-18:
        return (1.0, 0.0)

    sigma_c2 = float(np.sum(rq ** 2)) / m
    vr = sigma_c2 / sigma_a2

    # Heteroskedasticity-consistent asymptotic variance theta(q)
    r1_sq = r1 ** 2
    theta = 0.0
    for j in range(1, q):
        num = float(np.sum(r1_sq[j:] * r1_sq[:-j]))
        delta_j = num / (denom_sum ** 2)
        weight = (2.0 * (q - j) / q) ** 2
        theta += weight * delta_j

    z_stat = (vr - 1.0) / np.sqrt(theta) if theta > 1e-18 else 0.0
    return (round(float(vr), 4), round(float(z_stat), 4))


def yang_zhang_volatility(
    open_s: Sequence[float],
    high_s: Sequence[float],
    low_s: Sequence[float],
    close_s: Sequence[float],
    window: int = 20,
    return_percentile: bool = False,
    lookback: int = 120,
) -> Union[float, Tuple[float, float]]:
    """
    Yang-Zhang (2000) Realized Volatility Estimator combining overnight jumps,
    open-to-close volatility, and Rogers-Satchell range volatility:
        sigma_YZ^2 = sigma_o^2 + k * sigma_c^2 + (1 - k) * sigma_RS^2
        k = 0.34 / (1.34 + (N + 1) / (N - 1))
    If `return_percentile=True`, returns `(sigma_yz, vol_percentile_0_to_100)`.
    """
    opens = np.asarray(open_s, dtype=np.float64)
    highs = np.asarray(high_s, dtype=np.float64)
    lows = np.asarray(low_s, dtype=np.float64)
    closes = np.asarray(close_s, dtype=np.float64)

    n_total = min(len(opens), len(highs), len(lows), len(closes))
    if n_total < 3:
        return (0.01, 50.0) if return_percentile else 0.01

    opens = np.maximum(opens[-n_total:], 1e-12)
    highs = np.maximum(highs[-n_total:], opens)
    lows = np.minimum(np.maximum(lows[-n_total:], 1e-12), opens)
    closes = np.maximum(closes[-n_total:], 1e-12)

    log_o = np.log(opens[1:] / closes[:-1])
    log_c = np.log(closes[1:] / opens[1:])
    log_u = np.log(highs[1:] / opens[1:])
    log_d = np.log(lows[1:] / opens[1:])
    rs_all = log_u * (log_u - log_c) + log_d * (log_d - log_c)

    m_total = len(log_o)
    w = min(max(2, int(window)), m_total)
    k = 0.34 / (1.34 + (w + 1.0) / max(1.0, w - 1.0))

    def _yz_at(end_pos: int) -> float:
        s_o = log_o[end_pos - w:end_pos]
        s_c = log_c[end_pos - w:end_pos]
        s_rs = rs_all[end_pos - w:end_pos]
        var_o = float(np.var(s_o, ddof=1)) if len(s_o) > 1 else 0.0
        var_c = float(np.var(s_c, ddof=1)) if len(s_c) > 1 else 0.0
        var_rs = float(np.mean(s_rs))
        return float(np.sqrt(max(0.0, var_o + k * var_c + (1.0 - k) * var_rs)))

    current_yz = _yz_at(m_total)
    if not return_percentile:
        return round(current_yz, 6)

    # Fast vectorized rolling Yang-Zhang distribution over `lookback` bars (step=2 for speed)
    start_pos = max(w, m_total - int(lookback))
    hist_vals = [_yz_at(pos) for pos in range(start_pos, m_total + 1, 2)]
    if not hist_vals or hist_vals[-1] != current_yz:
        hist_vals.append(current_yz)

    if len(hist_vals) < 3:
        pct = 50.0
    else:
        arr_h = np.asarray(hist_vals, dtype=np.float64)
        span = float(np.max(arr_h) - np.min(arr_h))
        if span <= 1e-12:
            pct = 50.0
        else:
            rank_le = float(np.sum(arr_h <= current_yz))
            pct = float(np.clip((rank_le / len(arr_h)) * 100.0, 1.0, 99.0))

    return (round(current_yz, 6), round(pct, 2))


def yang_zhang_vol_percentile(
    open_s: Sequence[float],
    high_s: Sequence[float],
    low_s: Sequence[float],
    close_s: Sequence[float],
    window: int = 20,
    lookback: int = 120,
) -> Tuple[float, float]:
    """Convenience wrapper returning `(sigma_yz, vol_percentile)`."""
    res = yang_zhang_volatility(
        open_s, high_s, low_s, close_s,
        window=window, return_percentile=True, lookback=lookback
    )
    assert isinstance(res, tuple)
    return res


def compute_adx_di(
    high_s: Sequence[float],
    low_s: Sequence[float],
    close_s: Sequence[float],
    period: int = 14,
) -> Tuple[float, float, float]:
    """
    Wilder's ADX(14) along with +DI and -DI.
    Returns `(adx, plus_di, minus_di)`.
    """
    highs = np.asarray(high_s, dtype=np.float64)
    lows = np.asarray(low_s, dtype=np.float64)
    closes = np.asarray(close_s, dtype=np.float64)
    n = min(len(highs), len(lows), len(closes))
    if n < period + 2:
        return (15.0, 20.0, 20.0)

    highs = highs[-n:]
    lows = lows[-n:]
    closes = closes[-n:]

    up_move = highs[1:] - highs[:-1]
    down_move = lows[:-1] - lows[1:]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = highs[1:] - lows[1:]
    tr2 = np.abs(highs[1:] - closes[:-1])
    tr3 = np.abs(lows[1:] - closes[:-1])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))

    m = len(tr)
    p = min(period, m)
    atr_s = np.zeros(m, dtype=np.float64)
    pdm_s = np.zeros(m, dtype=np.float64)
    mdm_s = np.zeros(m, dtype=np.float64)

    atr_s[p - 1] = np.mean(tr[:p])
    pdm_s[p - 1] = np.mean(plus_dm[:p])
    mdm_s[p - 1] = np.mean(minus_dm[:p])

    for i in range(p, m):
        atr_s[i] = (atr_s[i - 1] * (p - 1) + tr[i]) / p
        pdm_s[i] = (pdm_s[i - 1] * (p - 1) + plus_dm[i]) / p
        mdm_s[i] = (mdm_s[i - 1] * (p - 1) + minus_dm[i]) / p

    safe_atr = np.maximum(atr_s, 1e-12)
    plus_di_arr = np.where(atr_s > 1e-12, 100.0 * (pdm_s / safe_atr), 0.0)
    minus_di_arr = np.where(atr_s > 1e-12, 100.0 * (mdm_s / safe_atr), 0.0)
    di_sum = plus_di_arr + minus_di_arr
    safe_di_sum = np.maximum(di_sum, 1e-12)
    dx = np.where(di_sum > 1e-12, 100.0 * np.abs(plus_di_arr - minus_di_arr) / safe_di_sum, 0.0)

    if m < 2 * p:
        adx_val = float(np.mean(dx[p - 1:]))
    else:
        adx_val = float(np.mean(dx[p - 1:2 * p - 1]))
        for i in range(2 * p - 1, m):
            adx_val = (adx_val * (p - 1) + float(dx[i])) / p

    return (
        round(float(adx_val), 2),
        round(float(plus_di_arr[-1]), 2),
        round(float(minus_di_arr[-1]), 2),
    )


def adx_14(
    high_s: Sequence[float],
    low_s: Sequence[float],
    close_s: Sequence[float],
    period: int = 14,
) -> float:
    """Return Wilder's ADX(14) scalar value."""
    adx_val, _, _ = compute_adx_di(high_s, low_s, close_s, period=period)
    return adx_val


def _classify_single_series(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    micro_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if len(closes) < 20:
        return {
            "regime": "CHOP_NO_TRADE",
            "hurst": 0.50,
            "vr4": 1.0,
            "vr4_zstat": 0.0,
            "adx14": 15.0,
            "plus_di": 20.0,
            "minus_di": 20.0,
            "yz_vol": 0.01,
            "yz_vol_pct": 50.0,
            "trend_direction": "NEUTRAL",
        }

    h = hurst_exponent(closes, max_lag=20)
    vr4, vr4_z = variance_ratio(closes, lag=4)
    yz_vol, yz_pct = yang_zhang_vol_percentile(opens, highs, lows, closes, window=20, lookback=120)
    adx_val, plus_di, minus_di = compute_adx_di(highs, lows, closes, period=14)

    # EMA20 & EMA50 for directional anchor
    k20 = 2.0 / 21.0
    k50 = 2.0 / 51.0
    ema20 = float(closes[0])
    ema50 = float(closes[0])
    for px in closes[1:]:
        fpx = float(px)
        ema20 = fpx * k20 + ema20 * (1.0 - k20)
        ema50 = fpx * k50 + ema50 * (1.0 - k50)

    bull_bias = (closes[-1] >= ema20 >= ema50) or (plus_di >= minus_di and closes[-1] > ema50)
    trend_dir = "BULL" if bull_bias else "BEAR"

    ms = micro_state or {}
    liq_z = abs(float(ms.get("liq_zscore", 0.0) or 0.0))
    delta_oi = float(ms.get("delta_oi_pct", 0.0) or 0.0)
    cascade_flag = bool(ms.get("cascade_exhaustion_trigger", False))
    hawkes_state = str(ms.get("hawkes_state", ""))

    # 1. Check CASCADE_EXHAUSTION
    # Triggered by microstructure liquidation spike / Hawkes inflection OR extreme realized vol wick
    recent_range = (highs[-1] - lows[-1]) / max(closes[-1], 1e-12)
    avg_range = float(np.mean((highs[-20:] - lows[-20:]) / np.maximum(closes[-20:], 1e-12)))
    wick_exhaustion = (yz_pct >= 85.0 and recent_range >= 2.2 * max(avg_range, 1e-6))

    if (
        cascade_flag
        or hawkes_state == "CASCADE_EXHAUSTED_INFLECTION"
        or (liq_z >= 2.5 and (delta_oi <= -1.0 or yz_pct >= 80.0))
        or (wick_exhaustion and liq_z >= 1.8)
    ):
        regime = "CASCADE_EXHAUSTION"
    # 2. Check TREND_BULL / TREND_BEAR
    elif ((h > 0.54 or vr4 > 1.12) and adx_val >= 24.0 and 20.0 <= yz_pct <= 95.0) or (
        h >= 0.58 and vr4 >= 1.15 and adx_val >= 18.0
    ):
        regime = "TREND_BULL" if bull_bias else "TREND_BEAR"
    # 3. Check MEAN_REVERT
    elif ((h < 0.46 or vr4 < 0.88) and adx_val < 22.0 and yz_pct < 80.0) or (
        h <= 0.42 and vr4 <= 0.85
    ):
        regime = "MEAN_REVERT"
    # 4. Check CHOP_NO_TRADE
    elif (0.46 <= h <= 0.54 and adx_val < 20.0) or yz_pct < 18.0:
        regime = "CHOP_NO_TRADE"
    else:
        # Borderline cases: if ADX is strong (>= 26) and VR4 >= 1.02, classify as trend;
        # if ADX < 18 and VR4 < 0.96, classify as MEAN_REVERT; otherwise CHOP_NO_TRADE
        if adx_val >= 26.0 and (h >= 0.52 or vr4 >= 1.05):
            regime = "TREND_BULL" if bull_bias else "TREND_BEAR"
        elif adx_val < 18.0 and (h <= 0.48 or vr4 <= 0.94):
            regime = "MEAN_REVERT"
        else:
            regime = "CHOP_NO_TRADE"

    return {
        "regime": regime,
        "hurst": h,
        "vr4": vr4,
        "vr4_zstat": vr4_z,
        "adx14": adx_val,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "yz_vol": yz_vol,
        "yz_vol_pct": yz_pct,
        "ema20": round(ema20, 6),
        "ema50": round(ema50, 6),
        "trend_direction": trend_dir,
    }


def detect_market_regime(
    btc_klines: Any,
    symbol_klines: Any = None,
    micro_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Detect statistical market regime combining symbol price action, BTC market anchor,
    and optional real-time microstructure state.
    Returns dict with `regime` in:
        {"TREND_BULL", "TREND_BEAR", "MEAN_REVERT", "CASCADE_EXHAUSTION", "CHOP_NO_TRADE"}
    plus `hurst`, `vr4`, `vr4_zstat`, `adx14`, `yz_vol_pct`, and `btc_anchor_regime`.
    """
    if symbol_klines is None or (isinstance(symbol_klines, (list, tuple)) and len(symbol_klines) == 0):
        symbol_klines = btc_klines

    b_open, b_high, b_low, b_close, _ = _extract_ohlcv(btc_klines)
    s_open, s_high, s_low, s_close, _ = _extract_ohlcv(symbol_klines)

    if len(b_close) == 0 and len(s_close) > 0:
        b_open, b_high, b_low, b_close = s_open, s_high, s_low, s_close

    btc_res = _classify_single_series(b_open, b_high, b_low, b_close, micro_state=None)
    sym_res = _classify_single_series(s_open, s_high, s_low, s_close, micro_state=micro_state)

    final_regime = sym_res["regime"]
    btc_regime = btc_res["regime"]

    return {
        "regime": final_regime,
        "hurst": sym_res["hurst"],
        "vr4": sym_res["vr4"],
        "vr4_zstat": sym_res["vr4_zstat"],
        "adx14": sym_res["adx14"],
        "plus_di": sym_res["plus_di"],
        "minus_di": sym_res["minus_di"],
        "yz_vol": sym_res["yz_vol"],
        "yz_vol_pct": sym_res["yz_vol_pct"],
        "trend_direction": sym_res["trend_direction"],
        "btc_anchor_regime": btc_regime,
        "btc_hurst": btc_res["hurst"],
        "btc_vr4": btc_res["vr4"],
        "is_tradable": final_regime != "CHOP_NO_TRADE",
    }
