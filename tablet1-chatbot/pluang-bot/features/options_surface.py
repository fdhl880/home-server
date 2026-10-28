"""
Pilar 16 (T3.10) — Options Surface Intelligence: Implied Volatility (DVOL), Variance Risk Premium (VRP),
25-Delta Risk-Reversal Skew, & Dealer Gamma Regime.

Formulas (Section 11.3):
  1. Variance Risk Premium:
         VRP_t = DVOL_t - sigma_{YZ, 24h}
     When VRP_t percentile > 90%, options smart money is pricing an imminent volatility expansion.
  2. 25-Delta Risk-Reversal Skew:
         Skew_{25Delta} = IV_{Call, 25Delta} - IV_{Put, 25Delta}
     If Skew_{25Delta} < -5.0% (institutions bidding up Put protection), blocks aggressive Longs.
  3. Graceful Offline Fallback:
     Queries Deribit public API (`https://www.deribit.com/api/v2/public/...`) and Binance Options
     (`https://eapi.binance.com/eapi/v1/mark`) with safe non-blocking fallback if offline.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Sequence

import numpy as np
import requests

logger = logging.getLogger(__name__)

DERIBIT_PUBLIC_BASE = "https://www.deribit.com/api/v2/public"
BINANCE_EAPI_MARK = "https://eapi.binance.com/eapi/v1/mark"


def compute_options_surface_metrics(
    dvol: Optional[float],
    realized_vol_yz_24h: float,
    call_25d_iv: Optional[float] = None,
    put_25d_iv: Optional[float] = None,
    vrp_history: Optional[Sequence[float]] = None,
    net_gex: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Pure deterministic calculation of Options Surface metrics:
      - `vrp`: DVOL_t - sigma_{YZ, 24h}
      - `vrp_percentile`: percentile rank in [0, 100]
      - `skew_25d`: IV_{Call, 25Delta} - IV_{Put, 25Delta}
      - `vol_expansion_alert`: True when `vrp_percentile > 90.0` (or `vrp >= 12.0` without history)
      - `veto_aggressive_long` / `put_skew_bearish_veto`: True when `skew_25d < -5.0`
      - `dealer_gamma_regime`: `NEGATIVE_GAMMA_TREND_ACCELERATION | POSITIVE_GAMMA_PINNING | NEUTRAL`
    """
    yz_vol = float(realized_vol_yz_24h)
    if dvol is None or not np.isfinite(dvol) or float(dvol) <= 0.0:
        return {
            "status": "OFFLINE_FALLBACK",
            "dvol": float(yz_vol),
            "realized_vol_yz_24h": float(yz_vol),
            "vrp": 0.0,
            "vrp_percentile": 50.0,
            "skew_25d": 0.0,
            "vol_expansion_alert": False,
            "put_skew_bearish_veto": False,
            "veto_aggressive_long": False,
            "veto_aggressive_short": False,
            "dealer_gamma_regime": "NEUTRAL",
        }

    dvol_val = float(dvol)
    vrp = dvol_val - yz_vol

    if vrp_history is not None and len(vrp_history) >= 5:
        hist_arr = np.asarray(list(vrp_history), dtype=float)
        vrp_pct = float(np.mean(hist_arr <= vrp) * 100.0)
    else:
        # Calibrated empirical mapping: normal crypto VRP ~ [-5, +10], > +12 is > 90th percentile
        vrp_pct = float(np.clip(50.0 + 3.5 * vrp, 0.0, 100.0))

    if call_25d_iv is not None and put_25d_iv is not None:
        skew_25d = float(call_25d_iv) - float(put_25d_iv)
    else:
        skew_25d = 0.0

    vol_expansion_alert = bool(vrp_pct > 90.0 or vrp >= 12.0)
    put_skew_bearish_veto = bool(skew_25d < -5.0)
    call_skew_bullish_veto_short = bool(skew_25d > 5.0)

    if net_gex is not None:
        gex_val = float(net_gex)
        if gex_val < -1e6:
            gamma_regime = "NEGATIVE_GAMMA_TREND_ACCELERATION"
        elif gex_val > 1e6:
            gamma_regime = "POSITIVE_GAMMA_PINNING"
        else:
            gamma_regime = "NEUTRAL"
    else:
        if vol_expansion_alert and abs(skew_25d) >= 4.0:
            gamma_regime = "NEGATIVE_GAMMA_TREND_ACCELERATION"
        elif vrp < -3.0 and abs(skew_25d) < 2.5:
            gamma_regime = "POSITIVE_GAMMA_PINNING"
        else:
            gamma_regime = "NEUTRAL"

    return {
        "status": "OK",
        "dvol": float(dvol_val),
        "realized_vol_yz_24h": float(yz_vol),
        "vrp": float(vrp),
        "vrp_percentile": float(vrp_pct),
        "skew_25d": float(skew_25d),
        "vol_expansion_alert": vol_expansion_alert,
        "put_skew_bearish_veto": put_skew_bearish_veto,
        "veto_aggressive_long": put_skew_bearish_veto,
        "veto_aggressive_short": call_skew_bullish_veto_short,
        "dealer_gamma_regime": gamma_regime,
    }


def fetch_options_surface(
    currency: str = "BTC",
    realized_vol_yz_24h: float = 45.0,
    vrp_history: Optional[Sequence[float]] = None,
    timeout: float = 2.5,
) -> Dict[str, Any]:
    """
    Fetch live DVOL and 25-Delta Call/Put IV skew from Deribit / Binance Options public endpoints.
    Never raises on network failure — returns safe `OFFLINE_FALLBACK` metrics.
    """
    curr = "ETH" if "ETH" in currency.upper() else "BTC"
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 3600_000 * 4

    dvol_val: Optional[float] = None
    call_iv: Optional[float] = None
    put_iv: Optional[float] = None

    try:
        resp = requests.get(
            f"{DERIBIT_PUBLIC_BASE}/get_volatility_index_data",
            params={
                "currency": curr,
                "start_timestamp": start_ms,
                "end_timestamp": now_ms,
                "resolution": "3600",
            },
            headers={"User-Agent": "PyrofuelQuantBot/3.0"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            payload = resp.json()
            rows = payload.get("result", {}).get("data", [])
            if rows and len(rows[-1]) >= 5:
                # [timestamp, open, high, low, close]
                dvol_val = float(rows[-1][4])
    except Exception as exc:
        logger.debug("Deribit DVOL fetch fallback for %s: %s", curr, exc)

    # Attempt to sample OTM Call vs OTM Put mark IVs from Binance eapi or Deribit book summary
    if dvol_val is None:
        try:
            resp_eapi = requests.get(
                BINANCE_EAPI_MARK,
                headers={"User-Agent": "PyrofuelQuantBot/3.0"},
                timeout=timeout,
            )
            if resp_eapi.status_code == 200:
                marks = resp_eapi.json()
                if isinstance(marks, list):
                    c_ivs = []
                    p_ivs = []
                    for item in marks:
                        sym = str(item.get("symbol", ""))
                        if not sym.startswith(f"{curr}-"):
                            continue
                        iv = float(item.get("markIV", 0.0)) * 100.0
                        delta = abs(float(item.get("delta", 0.0)))
                        if 0.18 <= delta <= 0.32 and iv > 0:
                            if sym.endswith("-C"):
                                c_ivs.append(iv)
                            elif sym.endswith("-P"):
                                p_ivs.append(iv)
                    if c_ivs and p_ivs:
                        call_iv = float(np.median(c_ivs))
                        put_iv = float(np.median(p_ivs))
                        dvol_val = 0.5 * (call_iv + put_iv)
        except Exception as exc:
            logger.debug("Binance eapi mark fallback for %s: %s", curr, exc)

    return compute_options_surface_metrics(
        dvol=dvol_val,
        realized_vol_yz_24h=realized_vol_yz_24h,
        call_25d_iv=call_iv,
        put_25d_iv=put_iv,
        vrp_history=vrp_history,
    )
