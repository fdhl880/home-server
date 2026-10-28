"""
Pilar 15 (T3.9) — Synthetic Liquidation Heatmap & Leverage Magnet Profiler (10x/20x/25x/50x/100x).

Constructs a Synthetic Liquidation Density Histogram directly from public
`(Price, High, Low, OpenInterestDelta, TakerImbalance)` data without paid APIs.

Formulas (Section 11.2):
  1. Leverage tiers L in {10, 20, 25, 50, 100} with prior weights w_L = {0.15, 0.25, 0.25, 0.25, 0.10}
     and Maintenance Margin Rate MMR = 0.004:
         P_{liq, long}(t, L)  = P_bar_t * (1 - 1/L + 0.004)
         P_{liq, short}(t, L) = P_bar_t * (1 + 1/L - 0.004)
  2. Price bins B_k (bin width = 0.10% of price) with exponential time decay exp(-eta * (T - t)).
  3. Swept-Bin Zeroing Rule:
     - Whenever `low_t` drops to or below bin B_k (B_k >= low_t), Long liquidation density at B_k is set to 0.
     - Whenever `high_t` rises to or above bin B_k (B_k <= high_t), Short liquidation density at B_k is set to 0.
  4. Tactical Outputs:
     - `nearest_long_liq_magnet`: highest-density unswept Long liquidation cluster below current price.
     - `nearest_short_liq_magnet`: highest-density unswept Short liquidation cluster above current price.
     - `is_sl_in_stop_hunt_zone`: checks if a proposed Stop-Loss sits inside or in front of an unswept
       25x/50x/100x liquidation cluster and recommends a shielded SL behind the cluster.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

LEVERAGE_TIERS: Tuple[int, ...] = (10, 20, 25, 50, 100)
LEVERAGE_WEIGHTS: Dict[int, float] = {
    10: 0.15,
    20: 0.25,
    25: 0.25,
    50: 0.25,
    100: 0.10,
}
DEFAULT_MMR: float = 0.004


def compute_tier_liquidation_prices(
    entry_price: float,
    mmr: float = DEFAULT_MMR,
    tiers: Sequence[int] = LEVERAGE_TIERS,
) -> Dict[int, Dict[str, float]]:
    """
    Compute theoretical isolated liquidation prices for Long and Short positions
    across leverage tiers L in {10, 20, 25, 50, 100}.
    """
    p_bar = float(entry_price)
    out: Dict[int, Dict[str, float]] = {}
    for lev in tiers:
        inv_l = 1.0 / float(lev)
        p_long = p_bar * (1.0 - inv_l + float(mmr))
        p_short = p_bar * (1.0 + inv_l - float(mmr))
        out[int(lev)] = {
            "long_liq_price": float(p_long),
            "short_liq_price": float(p_short),
        }
    return out


def _quantize_bin_price(price: float, ref_price: float, bin_width_pct: float = 0.0010) -> float:
    """
    Quantize a price level to the nearest discrete bin center of width `bin_width_pct * ref_price`.
    """
    step = max(ref_price * float(bin_width_pct), 1e-8)
    idx = round(float(price) / step)
    return round(float(idx * step), 8)


def is_sl_in_stop_hunt_zone(
    proposed_sl: float,
    current_price: float,
    direction: str,
    heatmap: Dict[str, Any],
    tolerance_pct: float = 0.0030,
    shield_buffer_pct: float = 0.0018,
) -> Dict[str, Any]:
    """
    Check whether a proposed Stop-Loss (`proposed_sl`) sits inside or just in front of
    a dense unswept liquidation cluster (where stop-hunt wicks are magnetically drawn).

    For LONG (`proposed_sl < current_price`):
      - Checks unswept `long_liq_bins` near `proposed_sl` (or between `current_price` and `proposed_sl * (1 - tolerance_pct)`).
      - If a high-density cluster sits right around `proposed_sl` (within `tolerance_pct` of `proposed_sl`),
        flags `in_stop_hunt_zone = True` and recommends placing SL safely below the cluster:
        `recommended_safe_sl = cluster_price * (1 - shield_buffer_pct)`.
    For SHORT (`proposed_sl > current_price`):
      - Checks unswept `short_liq_bins` near `proposed_sl`.
      - If a high-density cluster sits within `tolerance_pct`, recommends `cluster_price * (1 + shield_buffer_pct)`.
    """
    sl_px = float(proposed_sl)
    curr_px = float(current_price)
    dir_u = (direction or "LONG").upper()

    long_bins: Dict[float, float] = heatmap.get("long_liq_bins", {})
    short_bins: Dict[float, float] = heatmap.get("short_liq_bins", {})

    if dir_u == "LONG":
        relevant_bins = {float(bp): float(dens) for bp, dens in long_bins.items() if float(dens) > 0 and float(bp) < curr_px}
    else:
        relevant_bins = {float(bp): float(dens) for bp, dens in short_bins.items() if float(dens) > 0 and float(bp) > curr_px}

    if not relevant_bins:
        return {
            "in_stop_hunt_zone": False,
            "recommended_safe_sl": sl_px,
            "cluster_price": None,
            "cluster_density": 0.0,
        }

    all_densities = list(relevant_bins.values())
    # Dense cluster threshold: >= median/mean of active bins
    density_thresh = max(float(np.mean(all_densities)) * 0.5, 1e-9)

    nearby_clusters: List[Tuple[float, float]] = []
    for bp, dens in relevant_bins.items():
        if dens < density_thresh:
            continue
        rel_dist = abs(bp - sl_px) / max(curr_px, 1e-12)
        if rel_dist <= float(tolerance_pct):
            nearby_clusters.append((dens, bp))

    if not nearby_clusters:
        return {
            "in_stop_hunt_zone": False,
            "recommended_safe_sl": sl_px,
            "cluster_price": None,
            "cluster_density": 0.0,
        }

    nearby_clusters.sort(key=lambda item: item[0], reverse=True)
    top_dens, top_bp = nearby_clusters[0]

    if dir_u == "LONG":
        # Place SL safely below the lowest nearby stop-hunt cluster
        lowest_cluster_bp = min(bp for _d, bp in nearby_clusters)
        safe_sl = min(sl_px, lowest_cluster_bp * (1.0 - float(shield_buffer_pct)))
    else:
        highest_cluster_bp = max(bp for _d, bp in nearby_clusters)
        safe_sl = max(sl_px, highest_cluster_bp * (1.0 + float(shield_buffer_pct)))

    return {
        "in_stop_hunt_zone": True,
        "recommended_safe_sl": float(safe_sl),
        "cluster_price": float(top_bp),
        "cluster_density": float(top_dens),
    }


def build_liquidation_heatmap(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    oi_series: Sequence[float],
    tfi_series: Optional[Sequence[float]] = None,
    vwap_series: Optional[Sequence[float]] = None,
    bin_width_pct: float = 0.0010,
    decay_eta: float = 0.015,
    mmr: float = DEFAULT_MMR,
    proposed_sl: Optional[float] = None,
    direction: str = "LONG",
) -> Dict[str, Any]:
    """
    Build the Synthetic Liquidation Density Histogram across bars t = 0..T-1 and apply
    the exact Swept-Bin Zeroing Rule at every bar:
      - When `lows[t] <= B_k`, Long liquidation bin `B_k` is swept -> set to 0.0.
      - When `highs[t] >= B_k`, Short liquidation bin `B_k` is swept -> set to 0.0.

    Returns:
      - `nearest_long_liq_magnet`: Price of the strongest unswept Long liquidation cluster below current price.
      - `nearest_short_liq_magnet`: Price of the strongest unswept Short liquidation cluster above current price.
      - `long_liq_bins`: `{bin_price: density}` for unswept Long liquidations.
      - `short_liq_bins`: `{bin_price: density}` for unswept Short liquidations.
      - `swept_long_bins_count` & `swept_short_bins_count`.
      - `is_sl_in_stop_hunt_zone`: boolean if `proposed_sl` was supplied (plus `sl_shield_info`).
    """
    c_arr = np.asarray(closes, dtype=float)
    h_arr = np.asarray(highs, dtype=float)
    l_arr = np.asarray(lows, dtype=float)
    oi_arr = np.asarray(oi_series, dtype=float)
    n = min(len(c_arr), len(h_arr), len(l_arr), len(oi_arr))

    if n == 0:
        return {
            "nearest_long_liq_magnet": None,
            "nearest_short_liq_magnet": None,
            "long_liq_bins": {},
            "short_liq_bins": {},
            "swept_long_bins_count": 0,
            "swept_short_bins_count": 0,
            "is_sl_in_stop_hunt_zone": False,
            "sl_shield_info": {},
        }

    c_arr = c_arr[:n]
    h_arr = h_arr[:n]
    l_arr = l_arr[:n]
    oi_arr = oi_arr[:n]

    if tfi_series is not None and len(tfi_series) >= n:
        tfi_arr = np.asarray(tfi_series[:n], dtype=float)
    else:
        # Infer TFI proxy from bar Close Location Value
        rng = np.maximum(h_arr - l_arr, 1e-8 * c_arr)
        tfi_arr = np.clip((2.0 * c_arr - h_arr - l_arr) / rng, -1.0, 1.0)

    if vwap_series is not None and len(vwap_series) >= n:
        p_bar_arr = np.asarray(vwap_series[:n], dtype=float)
    else:
        p_bar_arr = (h_arr + l_arr + c_arr) / 3.0

    ref_price = float(c_arr[-1]) if c_arr[-1] > 0 else 100.0
    decay_factor = math.exp(-max(0.0, float(decay_eta)))

    long_bins: Dict[float, float] = {}
    short_bins: Dict[float, float] = {}
    swept_long_count = 0
    swept_short_count = 0

    for t in range(n):
        # 1. Apply exponential time decay to existing bins
        if decay_factor < 1.0:
            for k in list(long_bins.keys()):
                long_bins[k] *= decay_factor
            for k in list(short_bins.keys()):
                short_bins[k] *= decay_factor

        # 2. Swept-Bin Zeroing Rule for existing positions hit by bar t's [low_t, high_t]
        low_t = float(l_arr[t])
        high_t = float(h_arr[t])

        for bp in list(long_bins.keys()):
            if bp >= low_t and long_bins[bp] > 0.0:
                long_bins[bp] = 0.0
                swept_long_count += 1

        for bp in list(short_bins.keys()):
            if bp <= high_t and short_bins[bp] > 0.0:
                short_bins[bp] = 0.0
                swept_short_count += 1

        # 3. Accumulate newly opened Open Interest at bar t (when Delta OI_t > 0)
        if t == 0:
            delta_oi = max(0.0, float(oi_arr[0]) * 0.02)
        else:
            delta_oi = max(0.0, float(oi_arr[t] - oi_arr[t - 1]))

        if delta_oi > 0.0:
            p_bar = float(p_bar_arr[t])
            tfi_t = float(np.clip(tfi_arr[t], -1.0, 1.0))
            long_share = float(np.clip(0.5 + 0.35 * tfi_t, 0.15, 0.85))
            short_share = 1.0 - long_share

            tier_prices = compute_tier_liquidation_prices(p_bar, mmr=mmr)
            for lev, w_l in LEVERAGE_WEIGHTS.items():
                p_liq_long = tier_prices[lev]["long_liq_price"]
                p_liq_short = tier_prices[lev]["short_liq_price"]

                bin_long = _quantize_bin_price(p_liq_long, ref_price=ref_price, bin_width_pct=bin_width_pct)
                bin_short = _quantize_bin_price(p_liq_short, ref_price=ref_price, bin_width_pct=bin_width_pct)

                # Only accumulate if the bin wasn't immediately swept within the same bar
                if bin_long < low_t:
                    long_bins[bin_long] = long_bins.get(bin_long, 0.0) + delta_oi * w_l * long_share
                else:
                    long_bins.setdefault(bin_long, 0.0)

                if bin_short > high_t:
                    short_bins[bin_short] = short_bins.get(bin_short, 0.0) + delta_oi * w_l * short_share
                else:
                    short_bins.setdefault(bin_short, 0.0)

    curr_price = float(c_arr[-1])

    # Identify highest-density unswept Long liquidation magnet below current price (within 6% range)
    active_long_candidates = [
        (dens, abs(curr_price - bp) / max(curr_price, 1e-12), bp)
        for bp, dens in long_bins.items()
        if dens > 1e-9 and bp < curr_price and (curr_price - bp) / max(curr_price, 1e-12) <= 0.06
    ]
    if not active_long_candidates:
        active_long_candidates = [
            (dens, abs(curr_price - bp) / max(curr_price, 1e-12), bp)
            for bp, dens in long_bins.items()
            if dens > 1e-9 and bp < curr_price
        ]

    if active_long_candidates:
        # Rank by density weighted by proximity: dens / (dist_pct + 0.005)
        active_long_candidates.sort(key=lambda item: item[0] / (item[1] + 0.005), reverse=True)
        nearest_long_magnet: Optional[float] = float(active_long_candidates[0][2])
    else:
        nearest_long_magnet = None

    # Identify highest-density unswept Short liquidation magnet above current price (within 6% range)
    active_short_candidates = [
        (dens, abs(bp - curr_price) / max(curr_price, 1e-12), bp)
        for bp, dens in short_bins.items()
        if dens > 1e-9 and bp > curr_price and (bp - curr_price) / max(curr_price, 1e-12) <= 0.06
    ]
    if not active_short_candidates:
        active_short_candidates = [
            (dens, abs(bp - curr_price) / max(curr_price, 1e-12), bp)
            for bp, dens in short_bins.items()
            if dens > 1e-9 and bp > curr_price
        ]

    if active_short_candidates:
        active_short_candidates.sort(key=lambda item: item[0] / (item[1] + 0.005), reverse=True)
        nearest_short_magnet: Optional[float] = float(active_short_candidates[0][2])
    else:
        nearest_short_magnet = None

    base_result: Dict[str, Any] = {
        "current_price": curr_price,
        "nearest_long_liq_magnet": nearest_long_magnet,
        "nearest_short_liq_magnet": nearest_short_magnet,
        "long_liq_bins": long_bins,
        "short_liq_bins": short_bins,
        "swept_long_bins_count": swept_long_count,
        "swept_short_bins_count": swept_short_count,
    }

    if proposed_sl is not None:
        sl_check = is_sl_in_stop_hunt_zone(
            proposed_sl=float(proposed_sl),
            current_price=curr_price,
            direction=direction,
            heatmap=base_result,
        )
        base_result["is_sl_in_stop_hunt_zone"] = bool(sl_check["in_stop_hunt_zone"])
        base_result["recommended_safe_sl"] = sl_check["recommended_safe_sl"]
        base_result["sl_shield_info"] = sl_check
    else:
        base_result["is_sl_in_stop_hunt_zone"] = False
        base_result["recommended_safe_sl"] = None
        base_result["sl_shield_info"] = {}

    return base_result
