"""
Pilar 10 (T3.6) — Cross-Market Binance Spot vs. Perpetual Futures CVD Divergence.

Distinguishes genuine cash-driven institutional accumulation on Binance Spot
(`https://api.binance.com/api/v3/klines`) from leveraged retail froth on Binance Futures
(`https://fapi.binance.com/fapi/v1/klines`).

Formulas (Section 10.2 #3):
  Delta CVD_{market, t} = 2 * V_{taker_buy_quote, t} - V_{quote_total, t}
  D_{SP, t} = Z_{48}(Delta CVD_{Spot, 15m}) - Z_{48}(Delta CVD_{Perp, 15m})
  R_{SP, t} = V_{Spot, 15m} / V_{Perp, 15m}

Regimes:
  - Stealth Institutional Accumulation: D_{SP, t} >= +1.5
  - Leveraged Retail Froth / Bull Trap: D_{SP, t} <= -1.5 and Delta P > 0 (and Delta OI > 0) -> Veto Longs
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import requests

logger = logging.getLogger(__name__)

SPOT_REST_HOSTS: List[str] = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]


def fetch_binance_spot_klines(
    symbol: str,
    interval: str = "15m",
    limit: int = 60,
    timeout: float = 3.0,
    server_time_ms: Optional[int] = None,
    closed_only: bool = True,
) -> List[List[Any]]:
    """
    Fetch klines from Binance Spot (`https://api.binance.com/api/v3/klines`).
    Note: `api.binance.com` rate-limit quota is completely separate from `fapi.binance.com`.
    Returns `[]` safely if offline or unreachable so the bot never crashes.
    """
    sym = symbol.upper()
    now_ms = int(server_time_ms if server_time_ms is not None else time.time() * 1000)

    for host in SPOT_REST_HOSTS:
        try:
            resp = requests.get(
                f"{host}/api/v3/klines",
                params={"symbol": sym, "interval": interval, "limit": int(limit)},
                headers={"User-Agent": "PyrofuelQuantBot/3.0"},
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    if closed_only and len(data) > 0:
                        # Drop trailing forming bar if close_time > now_ms
                        last_close_ms = int(data[-1][6])
                        if last_close_ms > now_ms:
                            return data[:-1]
                    return data
        except Exception as exc:
            logger.debug("Spot klines fetch failed on %s for %s: %s", host, sym, exc)
            continue
    return []


def _extract_kline_flow(items: Iterable[Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Extract `(closes, total_quote_vols, delta_cvd_quotes)` from klines or flow dicts.
    """
    closes: List[float] = []
    tot_vols: List[float] = []
    delta_cvds: List[float] = []

    for row in items:
        if isinstance(row, (list, tuple)) and len(row) >= 7:
            c = float(row[4])
            v_base = float(row[5])
            q_vol = float(row[7]) if len(row) > 7 and float(row[7]) > 0 else v_base * c
            if len(row) > 10 and row[10] is not None:
                tb_q = float(row[10])
            elif len(row) > 9 and row[9] is not None:
                tb_q = float(row[9]) * c
            else:
                tb_q = 0.5 * q_vol
            delta_q = 2.0 * tb_q - q_vol
            closes.append(c)
            tot_vols.append(max(q_vol, 0.0))
            delta_cvds.append(delta_q)
        elif isinstance(row, dict):
            c = float(row.get("close", row.get("c", 1.0)))
            v_base = float(row.get("volume", row.get("v", 0.0)))
            q_vol = float(row.get("quote_volume", row.get("q", v_base * c)))
            if "delta_cvd" in row and row["delta_cvd"] is not None:
                delta_q = float(row["delta_cvd"])
            elif "taker_buy_quote" in row and row["taker_buy_quote"] is not None:
                delta_q = 2.0 * float(row["taker_buy_quote"]) - q_vol
            elif "Q" in row and row["Q"] is not None:
                delta_q = 2.0 * float(row["Q"]) - q_vol
            elif "buy_dollar_vol" in row or "sell_dollar_vol" in row:
                b_v = float(row.get("buy_dollar_vol", 0.0))
                s_v = float(row.get("sell_dollar_vol", 0.0))
                q_vol = b_v + s_v
                delta_q = b_v - s_v
            else:
                delta_q = 0.0
            closes.append(c)
            tot_vols.append(max(q_vol, 0.0))
            delta_cvds.append(delta_q)
        else:
            # Scalar delta_cvd value
            val = float(row)
            closes.append(1.0)
            tot_vols.append(max(abs(val), 1.0))
            delta_cvds.append(val)

    return (
        np.asarray(closes, dtype=float),
        np.asarray(tot_vols, dtype=float),
        np.asarray(delta_cvds, dtype=float),
    )


def _latest_zscore(arr: np.ndarray, window: int = 48) -> float:
    if len(arr) < 2:
        return 0.0
    seg = arr[-min(len(arr), max(2, int(window))) :]
    mu = float(np.mean(seg))
    sd = float(np.std(seg))
    if sd < 1e-12:
        return 0.0
    return float((seg[-1] - mu) / sd)


def compute_spot_perp_divergence(
    spot_klines: Iterable[Any],
    perp_klines: Iterable[Any],
    z_window: int = 48,
    delta_oi_pct: Optional[float] = None,
    delta_price_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Compute Spot vs. Perpetual Futures CVD Divergence (D_{SP,t}) and Spot-Perp Volume Ratio (R_{SP,t}):
        D_{SP, t} = Z_{48}(Delta CVD_{Spot, 15m}) - Z_{48}(Delta CVD_{Perp, 15m})
        R_{SP, t} = V_{Spot, 15m} / V_{Perp, 15m}

    If `spot_klines` or `perp_klines` is empty (e.g. offline fallback), returns neutral defaults
    without blocking execution.
    """
    spot_closes, spot_vols, spot_dcvd = _extract_kline_flow(spot_klines)
    perp_closes, perp_vols, perp_dcvd = _extract_kline_flow(perp_klines)

    n = min(len(spot_dcvd), len(perp_dcvd))
    if n < 2:
        return {
            "status": "OFFLINE_FALLBACK",
            "d_sp": 0.0,
            "z_spot_cvd": 0.0,
            "z_perp_cvd": 0.0,
            "spot_perp_vol_ratio": 0.0,
            "r_sp": 0.0,
            "stealth_accumulation": False,
            "leveraged_bull_trap": False,
            "veto_long": False,
            "veto_short": False,
            "signal_regime": "NEUTRAL_OFFLINE",
        }

    spot_dcvd = spot_dcvd[-n:]
    perp_dcvd = perp_dcvd[-n:]
    spot_vols = spot_vols[-n:]
    perp_vols = perp_vols[-n:]
    perp_closes = perp_closes[-n:]

    z_spot = _latest_zscore(spot_dcvd, window=z_window)
    z_perp = _latest_zscore(perp_dcvd, window=z_window)
    d_sp = float(z_spot - z_perp)

    v_spot_last = float(spot_vols[-1])
    v_perp_last = float(perp_vols[-1])
    r_sp = (v_spot_last / v_perp_last) if v_perp_last > 1e-12 else 0.0

    if delta_price_pct is not None:
        dp = float(delta_price_pct)
    elif len(perp_closes) >= 2 and perp_closes[-2] > 1e-12:
        dp = float((perp_closes[-1] - perp_closes[-2]) / perp_closes[-2] * 100.0)
    else:
        dp = 0.0

    oi_expanding = True if delta_oi_pct is None else (float(delta_oi_pct) > 0.0)

    # 1. Stealth Institutional Accumulation: D_SP >= +1.5
    stealth_accumulation = bool(d_sp >= 1.5)

    # 2. Leveraged Retail Froth / Bull Trap: D_SP <= -1.5 and Delta P > 0 and Delta OI > 0
    leveraged_bull_trap = bool(d_sp <= -1.5 and dp > 0.0 and oi_expanding)

    # 3. Bear Trap / Spot Absorption on dip: D_SP >= +1.5 and Delta P < 0
    spot_dip_absorption = bool(d_sp >= 1.5 and dp < 0.0)

    veto_long = leveraged_bull_trap
    veto_short = spot_dip_absorption

    if leveraged_bull_trap:
        signal_regime = "LEVERAGED_RETAIL_FROTH_BULL_TRAP"
    elif stealth_accumulation:
        signal_regime = "STEALTH_INSTITUTIONAL_ACCUMULATION"
    elif d_sp <= -1.5:
        signal_regime = "SPOT_DISTRIBUTION_PRESSURE"
    else:
        signal_regime = "NEUTRAL"

    return {
        "status": "OK",
        "d_sp": float(d_sp),
        "z_spot_cvd": float(z_spot),
        "z_perp_cvd": float(z_perp),
        "spot_perp_vol_ratio": float(r_sp),
        "r_sp": float(r_sp),
        "delta_price_pct": float(dp),
        "stealth_accumulation": stealth_accumulation,
        "leveraged_bull_trap": leveraged_bull_trap,
        "veto_long": veto_long,
        "veto_short": veto_short,
        "signal_regime": signal_regime,
    }
