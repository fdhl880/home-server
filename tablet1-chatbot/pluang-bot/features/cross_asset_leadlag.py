"""
Pilar 14 (T3.8) — Cross-Asset Lead-Lag Propagation (BTC/ETH -> $5 minNotional Altcoins).

Exploits the 5–45 second price-discovery propagation lag from BTC Spot/Perp into liquid
`$5 minNotional` altcoin perpetuals (`SOLUSDT`, `XRPUSDT`, `DOGEUSDT`, `SUIUSDT`, `ADAUSDT`),
turning small-account `BTCUSDT minNotional = $50` exclusion into a structural alpha advantage.

Formulas (Section 11.1):
  1. Leader Impulse I_{BTC, t} from BTC OFI_z, TFI, Hawkes intensity ratio, and return impulse.
  2. Dynamic Beta: beta_{i, t} = Cov(r_i, r_BTC) / Var(r_BTC).
  3. Expected Catch-Up Gap:
         Gap_{i, Delta t} = beta_{i, t} * r_{BTC, Delta t} - r_{i, Delta t}
  4. Leader-Follower Divergence Trigger: |I_{BTC, t}| > 2.5 sigma, |Gap_{i, 60s}| significant,
     and altcoin order-book imbalance OBI_{i, 20} aligned with BTC impulse direction.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

DEFAULT_SMALL_ACCOUNT_ALTCOINS: Tuple[str, ...] = (
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "SUIUSDT",
    "ADAUSDT",
)


def compute_leader_impulse(
    btc_ofi_z: float = 0.0,
    btc_tfi: float = 0.0,
    btc_hawkes_ratio: float = 1.0,
    btc_return_z: float = 0.0,
    eth_return_z: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Compute the composite BTC/ETH Leader Impulse I_{BTC, t} in standard deviation (sigma) units.
    """
    # Convert TFI in [-1, 1] to approximate z-score (~ 2.5 * TFI)
    tfi_z = 2.5 * float(np.clip(btc_tfi, -1.0, 1.0))
    ofi_z = float(btc_ofi_z)
    ret_z = float(btc_return_z)
    if eth_return_z is not None:
        ret_z = 0.70 * ret_z + 0.30 * float(eth_return_z)

    # Hawkes excitation amplifier (>= 1.0 when cascade/sweep is active)
    hawkes_excess = max(0.0, float(btc_hawkes_ratio) - 1.0)
    flow_sign = 1.0 if (ofi_z + tfi_z + ret_z) >= 0.0 else -1.0
    hawkes_contrib = flow_sign * min(2.5, 0.35 * hawkes_excess)

    # Weighted composite impulse in sigma units
    impulse_sigma = 0.35 * ret_z + 0.30 * ofi_z + 0.25 * tfi_z + 0.10 * hawkes_contrib
    # Also allow strong direct return + flow combination to reflect full magnitude
    if abs(ret_z) > 2.0 and (ret_z * (ofi_z + tfi_z)) > 0:
        impulse_sigma = flow_sign * max(abs(impulse_sigma), 0.55 * abs(ret_z) + 0.30 * abs(ofi_z) + 0.25 * abs(tfi_z))

    impulse_active = bool(abs(impulse_sigma) > 2.5)
    if impulse_sigma > 2.5:
        direction = "LONG"
    elif impulse_sigma < -2.5:
        direction = "SHORT"
    else:
        direction = "NONE"

    return {
        "leader_impulse_sigma": float(impulse_sigma),
        "impulse_active": impulse_active,
        "impulse_direction": direction,
        "components": {
            "ret_z": float(ret_z),
            "ofi_z": float(ofi_z),
            "tfi_z": float(tfi_z),
            "hawkes_contrib": float(hawkes_contrib),
        },
    }


def estimate_dynamic_beta(
    alt_returns: Sequence[float],
    btc_returns: Sequence[float],
    window: int = 60,
    min_beta: float = 0.20,
    max_beta: float = 3.50,
) -> float:
    """
    Estimate dynamic rolling beta_{i, t} = Cov(r_i, r_BTC) / Var(r_BTC).
    """
    r_alt = np.asarray(alt_returns, dtype=float)
    r_btc = np.asarray(btc_returns, dtype=float)
    n = min(len(r_alt), len(r_btc))
    if n < 3:
        return 1.0

    win = min(n, max(3, int(window)))
    a_seg = r_alt[-win:]
    b_seg = r_btc[-win:]

    var_btc = float(np.var(b_seg))
    if var_btc < 1e-12:
        return 1.0
    cov = float(np.mean((a_seg - np.mean(a_seg)) * (b_seg - np.mean(b_seg))))
    beta = cov / var_btc
    return float(np.clip(beta, min_beta, max_beta))


def _prices_to_returns(prices_or_returns: Sequence[float], is_returns: bool = False) -> np.ndarray:
    arr = np.asarray(prices_or_returns, dtype=float)
    if len(arr) == 0:
        return np.array([], dtype=float)
    if is_returns:
        return arr
    # Check if values look like positive price levels (> 0 and mean > 0.01 with small relative step)
    if np.all(arr > 0.0):
        if len(arr) < 2:
            return np.zeros(1, dtype=float)
        return np.diff(arr) / np.maximum(arr[:-1], 1e-12)
    return arr


def compute_catchup_gap(
    btc_series: Sequence[float],
    alt_series: Sequence[float],
    beta: Optional[float] = None,
    window: int = 60,
    is_returns: bool = False,
    alt_obi_20: float = 0.0,
    leader_impulse_sigma: float = 0.0,
) -> Dict[str, Any]:
    """
    Compute the Expected Catch-Up Gap for a single altcoin i relative to BTC across
    short-term propagation horizons (15s / 60s / 5m):
        Gap_{i, Delta t} = beta_{i, t} * r_{BTC, Delta t} - r_{i, Delta t}
    """
    r_btc = _prices_to_returns(btc_series, is_returns=is_returns)
    r_alt = _prices_to_returns(alt_series, is_returns=is_returns)
    n = min(len(r_btc), len(r_alt))
    if n < 2:
        return {
            "beta": float(beta if beta is not None else 1.0),
            "gap_15s": 0.0,
            "gap_60s": 0.0,
            "gap_5m": 0.0,
            "residual_vol": 1e-4,
            "signal_to_noise": 0.0,
            "obi_aligned": False,
            "trigger_active": False,
            "direction": "NONE",
            "catchup_score": 0.0,
        }

    r_btc = r_btc[-n:]
    r_alt = r_alt[-n:]

    # Estimate dynamic beta on prior history (excluding the latest impulse bar(s) so an unpropagated
    # lag at t doesn't artificially depress beta)
    if beta is not None:
        beta_val = float(beta)
    elif n >= 6:
        beta_val = estimate_dynamic_beta(r_alt[:-2], r_btc[:-2], window=window)
    else:
        beta_val = estimate_dynamic_beta(r_alt, r_btc, window=window)

    def _cum_ret(ret_arr: np.ndarray, k_bars: int) -> float:
        k = max(1, min(len(ret_arr), int(k_bars)))
        return float(np.sum(ret_arr[-k:]))

    # 1-step (~15s), 4-step (~60s), and 20-step (~5m) cumulative returns
    r_btc_15s = _cum_ret(r_btc, 1)
    r_alt_15s = _cum_ret(r_alt, 1)
    gap_15s = beta_val * r_btc_15s - r_alt_15s

    k_60s = min(4, max(1, n // 5))
    r_btc_60s = _cum_ret(r_btc, k_60s)
    r_alt_60s = _cum_ret(r_alt, k_60s)
    gap_60s = beta_val * r_btc_60s - r_alt_60s

    k_5m = min(20, max(1, n // 2))
    r_btc_5m = _cum_ret(r_btc, k_5m)
    r_alt_5m = _cum_ret(r_alt, k_5m)
    gap_5m = beta_val * r_btc_5m - r_alt_5m

    # Historical residual volatility sigma_{resid, i}
    hist_slice = slice(0, max(2, n - k_60s))
    residuals = beta_val * r_btc[hist_slice] - r_alt[hist_slice]
    resid_vol = max(float(np.std(residuals)), 1e-5)

    # Use the stronger of 15s or 60s gap for instantaneous lead-lag capture
    primary_gap = gap_15s if abs(gap_15s) >= abs(gap_60s) else gap_60s
    snr = float(primary_gap / resid_vol)

    # Check OBI alignment with BTC impulse / gap direction
    obi = float(alt_obi_20)
    if primary_gap > 0:
        obi_aligned = obi >= 0.05
        direction = "LONG"
    elif primary_gap < 0:
        obi_aligned = obi <= -0.05
        direction = "SHORT"
    else:
        obi_aligned = False
        direction = "NONE"

    impulse_ok = abs(float(leader_impulse_sigma)) > 2.5 or abs(snr) > 2.5
    same_sign = (float(leader_impulse_sigma) * primary_gap >= 0.0) if abs(leader_impulse_sigma) > 0.1 else True
    trigger_active = bool(impulse_ok and same_sign and abs(snr) >= 1.5 and obi_aligned)

    obi_bonus = 1.0 + 0.5 * abs(obi) if obi_aligned else 0.5
    catchup_score = float(abs(snr) * obi_bonus) if same_sign else 0.0

    return {
        "beta": float(beta_val),
        "gap_15s": float(gap_15s),
        "gap_60s": float(gap_60s),
        "gap_5m": float(gap_5m),
        "primary_gap": float(primary_gap),
        "residual_vol": float(resid_vol),
        "signal_to_noise": float(snr),
        "obi_aligned": bool(obi_aligned),
        "trigger_active": trigger_active,
        "direction": direction if trigger_active else ("LONG" if primary_gap > 0 else ("SHORT" if primary_gap < 0 else "NONE")),
        "catchup_score": float(catchup_score),
    }


def compute_cross_asset_leadlag(
    btc_prices: Sequence[float],
    alt_prices_dict: Dict[str, Sequence[float]],
    btc_micro: Optional[Dict[str, Any]] = None,
    alt_micro_dict: Optional[Dict[str, Dict[str, Any]]] = None,
    is_returns: bool = False,
    window: int = 60,
) -> Dict[str, Any]:
    """
    Evaluate BTC/ETH Leader Impulse and rank all `$5 minNotional` altcoins (`SOLUSDT`, `XRPUSDT`,
    `DOGEUSDT`, `SUIUSDT`, `ADAUSDT`, etc.) by Expected Catch-Up Gap & Signal-to-Noise Ratio.
    """
    r_btc = _prices_to_returns(btc_prices, is_returns=is_returns)
    if len(r_btc) >= 3:
        prior_std = max(float(np.std(r_btc[:-1])), 1e-5)
        btc_ret_z = float((r_btc[-1] - float(np.mean(r_btc[:-1]))) / prior_std)
    else:
        btc_ret_z = 0.0

    b_micro = btc_micro or {}
    impulse_info = compute_leader_impulse(
        btc_ofi_z=float(b_micro.get("ofi_z", b_micro.get("obi_20", 0.0) * 3.0)),
        btc_tfi=float(b_micro.get("tfi_5m", b_micro.get("tfi", 0.0))),
        btc_hawkes_ratio=float(b_micro.get("hawkes_ratio", 1.0)),
        btc_return_z=float(b_micro.get("btc_return_z", btc_ret_z)),
        eth_return_z=b_micro.get("eth_return_z"),
    )
    leader_sigma = impulse_info["leader_impulse_sigma"]

    a_micro_map = alt_micro_dict or {}
    alt_metrics: Dict[str, Dict[str, Any]] = {}
    ranked: List[Tuple[float, str]] = []

    for sym, series in alt_prices_dict.items():
        sym_u = sym.upper()
        a_m = a_micro_map.get(sym_u, a_micro_map.get(sym, {}))
        obi_20 = float(a_m.get("obi_weighted_20", a_m.get("obi_20", 0.15 if leader_sigma > 0 else (-0.15 if leader_sigma < 0 else 0.0))))
        gap_res = compute_catchup_gap(
            btc_series=btc_prices,
            alt_series=series,
            window=window,
            is_returns=is_returns,
            alt_obi_20=obi_20,
            leader_impulse_sigma=leader_sigma,
        )
        alt_metrics[sym_u] = gap_res
        ranked.append((gap_res["catchup_score"], sym_u))

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_sym = ranked[0][1] if ranked else None
    best_info = alt_metrics[best_sym] if best_sym else None

    return {
        "leader_impulse_sigma": float(leader_sigma),
        "impulse_active": bool(impulse_info["impulse_active"]),
        "impulse_direction": impulse_info["impulse_direction"],
        "best_catchup_altcoin": best_sym,
        "best_catchup_metrics": best_info,
        "ranked_altcoins": [sym for _score, sym in ranked],
        "altcoin_gaps": alt_metrics,
    }
