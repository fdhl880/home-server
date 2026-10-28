"""
Pilar 21 (T3.12) — Global Cross-Exchange Liquidity Radar: Coinbase US Institutional Premium
Index + Bybit/OKX Global Aggregated Open Interest & Funding Dispersion.

Formulas (Section 12.2):
  1. Coinbase Institutional Spot Premium (bps):
         CB_Prem_{bps, t} = ((P_{Coinbase, USD} - P_{Binance, USDT}) / P_{Binance, USDT}) * 10^4
     Rolling z-score Z_CB:
       - Z_CB > +1.8 -> US institutional spot buying (confirms Longs)
       - Z_CB < -1.8 -> US institutional selling / Asia retail froth trap
  2. Global Aggregated Open Interest & Funding Dispersion:
         OI_{Global, t} = OI_{Binance, t} + OI_{Bybit, t} + OI_{OKX, t}
  3. Graceful Degradation:
     If any external venue is slow or offline, falls back cleanly to Binance data without blocking.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import requests

logger = logging.getLogger(__name__)


def compute_coinbase_premium(
    coinbase_usd_price: Optional[float],
    binance_usdt_price: Optional[float],
    premium_history_bps: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """
    Compute Coinbase US Institutional Spot Premium Index in basis points (`cb_prem_bps`)
    and its rolling z-score (`cb_prem_zscore`).
    """
    if (
        coinbase_usd_price is None
        or binance_usdt_price is None
        or float(coinbase_usd_price) <= 0.0
        or float(binance_usdt_price) <= 0.0
    ):
        return {
            "status": "OFFLINE_FALLBACK",
            "cb_prem_bps": 0.0,
            "cb_prem_zscore": 0.0,
            "us_institutional_buying": False,
            "asia_retail_trap": False,
            "signal": "NEUTRAL_OFFLINE",
        }

    cb_px = float(coinbase_usd_price)
    bn_px = float(binance_usdt_price)
    prem_bps = ((cb_px - bn_px) / bn_px) * 1e4

    if premium_history_bps is not None and len(premium_history_bps) >= 3:
        hist = np.asarray(list(premium_history_bps), dtype=float)
        mu = float(np.mean(hist))
        sd = float(np.std(hist))
        z_cb = ((prem_bps - mu) / sd) if sd > 1e-6 else (prem_bps / 5.0)
    else:
        # Typical baseline: normal Coinbase-Binance spread std ~ 4.0 bps
        z_cb = prem_bps / 4.0

    us_buying = bool(z_cb > 1.8)
    asia_trap = bool(z_cb < -1.8)

    if us_buying:
        sig = "US_INSTITUTIONAL_BUYING"
    elif asia_trap:
        sig = "US_INSTITUTIONAL_SELLING_ASIA_TRAP"
    else:
        sig = "NEUTRAL"

    return {
        "status": "OK",
        "cb_prem_bps": float(prem_bps),
        "cb_prem_zscore": float(z_cb),
        "us_institutional_buying": us_buying,
        "asia_retail_trap": asia_trap,
        "signal": sig,
    }


def compute_global_oi_and_funding(
    binance_oi: float,
    bybit_oi: Optional[float] = None,
    okx_oi: Optional[float] = None,
    binance_funding: float = 0.0,
    bybit_funding: Optional[float] = None,
    okx_funding: Optional[float] = None,
    global_oi_history: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """
    Aggregate global Open Interest across Binance, Bybit, and OKX:
        OI_{Global, t} = OI_{Binance, t} + OI_{Bybit, t} + OI_{OKX, t}
    and compute OI-weighted global funding rate + cross-exchange funding dispersion.
    """
    bn_oi = max(0.0, float(binance_oi))
    by_oi = max(0.0, float(bybit_oi)) if bybit_oi is not None and np.isfinite(bybit_oi) else 0.0
    ok_oi = max(0.0, float(okx_oi)) if okx_oi is not None and np.isfinite(okx_oi) else 0.0

    oi_global = bn_oi + by_oi + ok_oi
    venues_online = 1 + (1 if bybit_oi is not None else 0) + (1 if okx_oi is not None else 0)

    # Funding rates and weights
    fund_list: List[float] = [float(binance_funding)]
    weights: List[float] = [max(bn_oi, 1.0)]
    if bybit_funding is not None and np.isfinite(bybit_funding):
        fund_list.append(float(bybit_funding))
        weights.append(max(by_oi, 1.0))
    if okx_funding is not None and np.isfinite(okx_funding):
        fund_list.append(float(okx_funding))
        weights.append(max(ok_oi, 1.0))

    w_sum = sum(weights)
    weighted_funding = sum(f * w for f, w in zip(fund_list, weights)) / w_sum if w_sum > 0 else float(binance_funding)
    funding_dispersion_bps = (max(fund_list) - min(fund_list)) * 1e4 if len(fund_list) >= 2 else 0.0

    if global_oi_history is not None and len(global_oi_history) >= 3:
        hist = np.asarray(list(global_oi_history), dtype=float)
        prev_oi = float(hist[-1])
        delta_global_oi_pct = ((oi_global - prev_oi) / prev_oi * 100.0) if prev_oi > 1e-12 else 0.0
        mu = float(np.mean(hist))
        sd = float(np.std(hist))
        global_oi_z = ((oi_global - mu) / sd) if sd > 1e-6 else 0.0
    else:
        delta_global_oi_pct = 0.0
        global_oi_z = 0.0

    return {
        "oi_global": float(oi_global),
        "oi_binance": float(bn_oi),
        "oi_bybit": float(by_oi),
        "oi_okx": float(ok_oi),
        "venues_online": int(venues_online),
        "delta_global_oi_pct": float(delta_global_oi_pct),
        "global_oi_zscore": float(global_oi_z),
        "global_weighted_funding": float(weighted_funding),
        "funding_dispersion_bps": float(funding_dispersion_bps),
    }


def fetch_global_liquidity_radar(
    symbol: str = "BTCUSDT",
    binance_spot_price: Optional[float] = None,
    binance_oi: float = 0.0,
    binance_funding: float = 0.0,
    premium_history_bps: Optional[Sequence[float]] = None,
    global_oi_history: Optional[Sequence[float]] = None,
    timeout: float = 2.0,
) -> Dict[str, Any]:
    """
    Query Coinbase Spot (`BTC-USD` / `ETH-USD` / `SOL-USD`), Bybit Linear Tickers,
    and OKX Swap Open Interest with full graceful degradation if offline.
    """
    sym_u = symbol.upper()
    base_coin = sym_u[:-4] if sym_u.endswith("USDT") else sym_u

    cb_price: Optional[float] = None
    bybit_oi: Optional[float] = None
    bybit_funding: Optional[float] = None
    okx_oi: Optional[float] = None

    headers = {"User-Agent": "PyrofuelQuantBot/3.0"}

    # 1. Coinbase Spot Ticker
    try:
        resp_cb = requests.get(
            f"https://api.exchange.coinbase.com/products/{base_coin}-USD/ticker",
            headers=headers,
            timeout=timeout,
        )
        if resp_cb.status_code == 200:
            cb_data = resp_cb.json()
            if "price" in cb_data:
                cb_price = float(cb_data["price"])
    except Exception as exc:
        logger.debug("Coinbase ticker fallback for %s: %s", base_coin, exc)

    # 2. Bybit V5 Linear Ticker (contains both openInterestValue/openInterest and fundingRate)
    try:
        resp_by = requests.get(
            "https://api.bybit.com/v5/market/tickers",
            params={"category": "linear", "symbol": sym_u},
            headers=headers,
            timeout=timeout,
        )
        if resp_by.status_code == 200:
            by_list = resp_by.json().get("result", {}).get("list", [])
            if by_list:
                entry = by_list[0]
                if "openInterest" in entry:
                    bybit_oi = float(entry["openInterest"])
                if "fundingRate" in entry and entry["fundingRate"] != "":
                    bybit_funding = float(entry["fundingRate"])
    except Exception as exc:
        logger.debug("Bybit ticker fallback for %s: %s", sym_u, exc)

    # 3. OKX Swap Open Interest
    try:
        inst_id = f"{base_coin}-USDT-SWAP"
        resp_ok = requests.get(
            "https://www.okx.com/api/v5/public/open-interest",
            params={"instType": "SWAP", "instId": inst_id},
            headers=headers,
            timeout=timeout,
        )
        if resp_ok.status_code == 200:
            ok_list = resp_ok.json().get("data", [])
            if ok_list and "oiCcy" in ok_list[0]:
                okx_oi = float(ok_list[0]["oiCcy"])
    except Exception as exc:
        logger.debug("OKX OI fallback for %s: %s", base_coin, exc)

    cb_metrics = compute_coinbase_premium(
        coinbase_usd_price=cb_price,
        binance_usdt_price=binance_spot_price,
        premium_history_bps=premium_history_bps,
    )
    oi_metrics = compute_global_oi_and_funding(
        binance_oi=binance_oi,
        bybit_oi=bybit_oi,
        okx_oi=okx_oi,
        binance_funding=binance_funding,
        bybit_funding=bybit_funding,
        okx_funding=None,
        global_oi_history=global_oi_history,
    )

    return {
        **cb_metrics,
        **oi_metrics,
        "symbol": sym_u,
    }
