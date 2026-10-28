"""
Pilar 2 (T3.2) — Institutional Microstructure & Derivatives Alpha Engine.

Pure, deterministic, zero-lookahead functions implementing Section 5.2 of Blueprint v2:
  1. `compute_multilevel_ofi`: Cont-Kukanov-Stoikov Multi-Level OFI with exponential depth
     decay w_k = exp(-0.25 * (k - 1)), 20-level OBI, Micro-Price, & Micro-Price Divergence.
  2. `compute_tfi_and_cvd`: Trade Flow Imbalance (5m, 15m, 1h) & Cumulative Volume Delta (CVD)
     supporting both live `@aggTrade` streams and historical/REST kline `taker_buy_quote` columns,
     plus Bullish/Bearish CVD Absorption detection.
  3. `classify_oi_price_quadrant`: Open Interest x Price 4-Quadrant classifier
     (`Q1_NEW_LONGS | Q2_SHORT_COVERING | Q3_NEW_SHORTS | Q4_LONG_LIQ_FLUSH`).
  4. `compute_liquidation_cascade`: `@forceOrder` 1m/5m rolling USD totals, 24h z-score,
     and Cascade Exhaustion detector.
  5. `compute_funding_and_basis`: Mark-Index Basis (bps), 30d Funding Rate Z-Score,
     Crowding detector, and 10-minute Funding Boundary Guard.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


def _extract_book_side(book: Optional[Dict[str, Any]], keys: Tuple[str, ...]) -> List[Tuple[float, float]]:
    if not book or not isinstance(book, dict):
        return []
    for key in keys:
        if key in book and book[key] is not None:
            raw = book[key]
            out: List[Tuple[float, float]] = []
            for item in raw:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    p, q = float(item[0]), float(item[1])
                    if p > 0 and q >= 0:
                        out.append((p, q))
                elif isinstance(item, dict):
                    p = float(item.get("price", item.get("p", 0.0)))
                    q = float(item.get("qty", item.get("q", 0.0)))
                    if p > 0 and q >= 0:
                        out.append((p, q))
            return out
    return []


def compute_multilevel_ofi(
    prev_book: Optional[Dict[str, Any]],
    curr_book: Optional[Dict[str, Any]],
    decay_lambda: float = 0.25,
    max_levels: int = 20,
) -> Dict[str, Any]:
    """
    Cont-Kukanov-Stoikov Multi-Level Order Flow Imbalance (OFI), 20-Level Weighted
    Order Book Imbalance (OBI), Micro-Price, and Micro-Price Divergence.

    Formulas (Section 5.2.A):
      Delta B_{k,t} = I(P^B_{k,t} >= P^B_{k,t-1}) Q^B_{k,t} - I(P^B_{k,t} <= P^B_{k,t-1}) Q^B_{k,t-1}
      Delta A_{k,t} = I(P^A_{k,t} <= P^A_{k,t-1}) Q^A_{k,t} - I(P^A_{k,t} >= P^A_{k,t-1}) Q^A_{k,t-1}
      w_k = exp(-decay_lambda * (k - 1)),  k = 1..20
      OFI_t = sum_{k=1}^{20} w_k * (Delta B_{k,t} - Delta A_{k,t})
      OBI_t = (sum w_k Q^B_{k,t} - sum w_k Q^A_{k,t}) / (sum w_k Q^B_{k,t} + sum w_k Q^A_{k,t})
      MicroPrice = (Q^B_1 * P^A_1 + Q^A_1 * P^B_1) / (Q^B_1 + Q^A_1)
      MicroDiv   = (MicroPrice - P_mid) / (P^A_1 - P^B_1)
    """
    curr_bids = _extract_book_side(curr_book, ("bids", "b"))
    curr_asks = _extract_book_side(curr_book, ("asks", "a"))
    prev_bids = _extract_book_side(prev_book, ("bids", "b"))
    prev_asks = _extract_book_side(prev_book, ("asks", "a"))

    if not curr_bids or not curr_asks:
        return {
            "ofi_raw": 0.0,
            "obi_weighted_20": 0.0,
            "obi_20": 0.0,
            "micro_price": 0.0,
            "mid_price": 0.0,
            "micro_divergence": 0.0,
            "spread_bps": 0.0,
            "level_ofis": [],
        }

    levels_curr = min(max_levels, len(curr_bids), len(curr_asks))
    levels_prev = min(levels_curr, len(prev_bids), len(prev_asks))

    weighted_bid_sum = 0.0
    weighted_ask_sum = 0.0
    ofi_raw = 0.0
    level_ofis: List[float] = []

    for idx in range(levels_curr):
        # k = idx + 1, so k - 1 == idx
        w_k = math.exp(-float(decay_lambda) * idx)
        pb_t, qb_t = curr_bids[idx]
        pa_t, qa_t = curr_asks[idx]

        weighted_bid_sum += w_k * qb_t
        weighted_ask_sum += w_k * qa_t

        if idx < levels_prev:
            pb_prev, qb_prev = prev_bids[idx]
            pa_prev, qa_prev = prev_asks[idx]

            delta_b = (qb_t if pb_t >= pb_prev else 0.0) - (qb_prev if pb_t <= pb_prev else 0.0)
            delta_a = (qa_t if pa_t <= pa_prev else 0.0) - (qa_prev if pa_t >= pa_prev else 0.0)
            ofi_k = w_k * (delta_b - delta_a)
        else:
            ofi_k = 0.0

        ofi_raw += ofi_k
        level_ofis.append(float(ofi_k))

    denom_obi = weighted_bid_sum + weighted_ask_sum
    obi_weighted_20 = (weighted_bid_sum - weighted_ask_sum) / denom_obi if denom_obi > 1e-12 else 0.0
    obi_weighted_20 = float( max(-1.0, min(1.0, obi_weighted_20)) )

    pb_1, qb_1 = curr_bids[0]
    pa_1, qa_1 = curr_asks[0]
    mid_price = 0.5 * (pb_1 + pa_1)
    spread = max(0.0, pa_1 - pb_1)
    spread_bps = (spread / mid_price * 1e4) if mid_price > 1e-12 else 0.0

    top_qty_sum = qb_1 + qa_1
    if top_qty_sum > 1e-12:
        micro_price = (qb_1 * pa_1 + qa_1 * pb_1) / top_qty_sum
    else:
        micro_price = mid_price

    if spread > 1e-12:
        micro_divergence = (micro_price - mid_price) / spread
    else:
        micro_divergence = 0.0
    micro_divergence = float(max(-0.5, min(0.5, micro_divergence)))

    return {
        "ofi_raw": float(ofi_raw),
        "obi_weighted_20": float(obi_weighted_20),
        "obi_20": float(obi_weighted_20),
        "micro_price": float(micro_price),
        "mid_price": float(mid_price),
        "micro_divergence": float(micro_divergence),
        "spread_bps": float(spread_bps),
        "level_ofis": level_ofis,
    }


def _standardized_linear_slope(values: Sequence[float]) -> float:
    """
    Compute the standardized OLS slope (t-stat / correlation-scaled slope) of `values`
    against time index `0, 1, ..., L-1`.
    """
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    if n < 2:
        return 0.0
    y_std = float(np.std(arr))
    if y_std < 1e-12:
        return 0.0
    x = np.arange(n, dtype=float)
    x_centered = x - np.mean(x)
    y_centered = (arr - np.mean(arr)) / y_std
    denom = float(np.sum(x_centered ** 2))
    if denom < 1e-12:
        return 0.0
    # Slope in units of standard deviations across the window
    slope_per_bar = float(np.sum(x_centered * y_centered) / denom)
    return slope_per_bar * float(n - 1)


def compute_tfi_and_cvd(
    klines_or_trades: Iterable[Any],
    window: int = 12,
    now_sec: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute Trade Flow Imbalance (TFI_5m, TFI_15m, TFI_1h) and Cumulative Volume Delta (CVD)
    Divergence / Absorption.

    Supports 3 input formats transparently:
      1. Raw `@aggTrade` dicts: `{"p": price, "q": qty, "m": is_buyer_maker, "T": ts_ms}`
         (`m == False` -> Taker Buy `+1`; `m == True` -> Taker Sell `-1`).
      2. 1-second aggTrade bucket dicts: `{"ts_sec": ..., "buy_dollar_vol": ..., "sell_dollar_vol": ..., "last_price": ...}`.
      3. Historical / REST klines (list of 11+ elements or dict with `close`, `quote_volume`, `taker_buy_quote`):
         `TakerBuyQuote_t = kline[10]`, `DeltaQuote_t = 2 * TakerBuyQuote_t - QuoteVolume_t`.
    """
    items = list(klines_or_trades)
    if not items:
        return {
            "tfi_5m": 0.0,
            "tfi_15m": 0.0,
            "tfi_1h": 0.0,
            "cvd_slope_z": 0.0,
            "price_slope_z": 0.0,
            "bullish_absorption": False,
            "bearish_absorption": False,
            "cvd_series": [],
            "delta_cvd": 0.0,
            "delta_price_pct": 0.0,
        }

    first = items[0]
    prices: List[float] = []
    signed_vols: List[float] = []
    total_vols: List[float] = []
    timestamps_sec: List[float] = []
    is_kline_mode = False
    bar_interval_sec = 900.0  # default 15m kline

    if isinstance(first, (list, tuple)) and len(first) >= 7:
        # REST Kline row format
        is_kline_mode = True
        if len(items) >= 2:
            dt_ms = float(items[-1][0]) - float(items[-2][0])
            if dt_ms > 0:
                bar_interval_sec = dt_ms / 1000.0
        for row in items:
            close_px = float(row[4])
            vol_base = float(row[5])
            quote_vol = float(row[7]) if len(row) > 7 and float(row[7]) > 0 else vol_base * close_px
            if len(row) > 10 and row[10] is not None:
                taker_buy_quote = float(row[10])
            elif len(row) > 9 and row[9] is not None:
                taker_buy_quote = float(row[9]) * close_px
            else:
                # Fallback CLV approximation if taker column unavailable
                h, l, o = float(row[2]), float(row[3]), float(row[1])
                clv = ((close_px - l) / (h - l)) if (h - l) > 1e-12 else (0.5 if close_px == o else (0.7 if close_px > o else 0.3))
                taker_buy_quote = quote_vol * clv
            delta_q = 2.0 * taker_buy_quote - quote_vol
            prices.append(close_px)
            signed_vols.append(delta_q)
            total_vols.append(max(quote_vol, abs(delta_q)))
            timestamps_sec.append(float(row[0]) / 1000.0)

    elif isinstance(first, dict) and ("buy_dollar_vol" in first or "sell_dollar_vol" in first):
        # 1-second aggTrade bucket format from BinanceFuturesStreamManager
        for b in items:
            buy_v = float(b.get("buy_dollar_vol", 0.0))
            sell_v = float(b.get("sell_dollar_vol", 0.0))
            px = float(b.get("last_price", b.get("vwap", 0.0)))
            ts = float(b.get("ts_sec", len(timestamps_sec)))
            prices.append(px)
            signed_vols.append(buy_v - sell_v)
            total_vols.append(buy_v + sell_v)
            timestamps_sec.append(ts)

    elif isinstance(first, dict) and ("m" in first or ("p" in first and "q" in first)):
        # Raw `@aggTrade` list
        for tr in items:
            px = float(tr.get("p", tr.get("price", 0.0)))
            qty = float(tr.get("q", tr.get("qty", 0.0)))
            is_buyer_maker = bool(tr.get("m", False))
            ts_ms = float(tr.get("T", tr.get("E", len(timestamps_sec) * 1000.0)))
            d_vol = px * qty
            sign = -1.0 if is_buyer_maker else 1.0
            prices.append(px)
            signed_vols.append(sign * d_vol)
            total_vols.append(d_vol)
            timestamps_sec.append(ts_ms / 1000.0)

    elif isinstance(first, dict):
        # Normalized kline dict format
        is_kline_mode = True
        if len(items) >= 2 and "open_time" in items[-1] and "open_time" in items[-2]:
            dt_ms = float(items[-1]["open_time"]) - float(items[-2]["open_time"])
            if dt_ms > 0:
                bar_interval_sec = dt_ms / 1000.0
        for kd in items:
            close_px = float(kd.get("close", kd.get("c", 0.0)))
            vol_base = float(kd.get("volume", kd.get("v", 0.0)))
            quote_vol = float(kd.get("quote_volume", kd.get("q", vol_base * close_px)))
            if "taker_buy_quote" in kd and kd["taker_buy_quote"] is not None:
                taker_buy_quote = float(kd["taker_buy_quote"])
            elif "Q" in kd and kd["Q"] is not None:
                taker_buy_quote = float(kd["Q"])
            elif "taker_buy_base" in kd and kd["taker_buy_base"] is not None:
                taker_buy_quote = float(kd["taker_buy_base"]) * close_px
            else:
                h = float(kd.get("high", kd.get("h", close_px)))
                l = float(kd.get("low", kd.get("l", close_px)))
                clv = ((close_px - l) / (h - l)) if (h - l) > 1e-12 else 0.5
                taker_buy_quote = quote_vol * clv
            delta_q = 2.0 * taker_buy_quote - quote_vol
            prices.append(close_px)
            signed_vols.append(delta_q)
            total_vols.append(max(quote_vol, abs(delta_q)))
            timestamps_sec.append(float(kd.get("open_time", kd.get("t", len(timestamps_sec) * bar_interval_sec * 1000.0))) / 1000.0)

    signed_arr = np.asarray(signed_vols, dtype=float)
    total_arr = np.asarray(total_vols, dtype=float)
    price_arr = np.asarray(prices, dtype=float)
    ts_arr = np.asarray(timestamps_sec, dtype=float)
    cvd_arr = np.cumsum(signed_arr)

    def _tfi_over_horizon(horizon_sec: float, fallback_bars: int) -> float:
        if len(signed_arr) == 0:
            return 0.0
        if not is_kline_mode and len(ts_arr) > 1 and (ts_arr[-1] - ts_arr[0]) > 10.0:
            ref_t = float(now_sec) if now_sec is not None else float(ts_arr[-1])
            mask = ts_arr >= (ref_t - horizon_sec)
            if np.any(mask):
                s_sum = float(np.sum(signed_arr[mask]))
                t_sum = float(np.sum(total_arr[mask]))
                return float(np.clip(s_sum / t_sum, -1.0, 1.0)) if t_sum > 1e-12 else 0.0
        n_take = max(1, min(len(signed_arr), fallback_bars))
        s_sum = float(np.sum(signed_arr[-n_take:]))
        t_sum = float(np.sum(total_arr[-n_take:]))
        return float(np.clip(s_sum / t_sum, -1.0, 1.0)) if t_sum > 1e-12 else 0.0

    if is_kline_mode:
        bars_5m = max(1, int(round(300.0 / max(60.0, bar_interval_sec))))
        bars_15m = max(1, int(round(900.0 / max(60.0, bar_interval_sec))))
        bars_1h = max(1, int(round(3600.0 / max(60.0, bar_interval_sec))))
    else:
        bars_5m, bars_15m, bars_1h = 5, 15, 60

    tfi_5m = _tfi_over_horizon(300.0, bars_5m)
    tfi_15m = _tfi_over_horizon(900.0, bars_15m)
    tfi_1h = _tfi_over_horizon(3600.0, bars_1h)

    win = max(2, min(int(window), len(price_arr)))
    p_win = price_arr[-win:]
    cvd_win = cvd_arr[-win:]

    price_slope_z = _standardized_linear_slope(p_win)
    cvd_slope_z = _standardized_linear_slope(cvd_win)

    delta_p = float(p_win[-1] - p_win[0])
    delta_price_pct = (delta_p / p_win[0] * 100.0) if p_win[0] > 1e-12 else 0.0
    # Note: ΔCVD across the window `win` includes the net signed flow during those `win` bars:
    delta_cvd = float(np.sum(signed_arr[-win:]))

    # Bullish Absorption: Price makes Lower Low / drops (delta_p < 0 or price_slope_z < -0.25)
    # while CVD rises (delta_cvd > 0 and cvd_slope_z > 0.15)
    bullish_absorption = bool(
        (delta_p < 0.0 or price_slope_z < -0.25)
        and (delta_cvd > 0.0 and cvd_slope_z > 0.15)
    )
    # Bearish Absorption: Price makes Higher High / rises (delta_p > 0 or price_slope_z > +0.25)
    # while CVD falls (delta_cvd < 0 and cvd_slope_z < -0.15)
    bearish_absorption = bool(
        (delta_p > 0.0 or price_slope_z > 0.25)
        and (delta_cvd < 0.0 and cvd_slope_z < -0.15)
    )

    return {
        "tfi_5m": float(tfi_5m),
        "tfi_15m": float(tfi_15m),
        "tfi_1h": float(tfi_1h),
        "cvd_slope_z": float(cvd_slope_z),
        "price_slope_z": float(price_slope_z),
        "bullish_absorption": bullish_absorption,
        "bearish_absorption": bearish_absorption,
        "cvd_series": [float(x) for x in cvd_arr],
        "delta_cvd": float(delta_cvd),
        "delta_price_pct": float(delta_price_pct),
    }


def classify_oi_price_quadrant(
    prices: Sequence[float],
    oi_series: Sequence[float],
    lookback: int = 4,
) -> Dict[str, Any]:
    """
    Open Interest x Price 4-Quadrant Mechanics (Section 5.2.C):
      - Q1_NEW_LONGS:       Delta P > 0, Delta OI > 0
      - Q2_SHORT_COVERING:  Delta P > 0, Delta OI < 0
      - Q3_NEW_SHORTS:      Delta P < 0, Delta OI > 0
      - Q4_LONG_LIQ_FLUSH:  Delta P < 0, Delta OI < 0
    """
    p_arr = np.asarray(prices, dtype=float)
    oi_arr = np.asarray(oi_series, dtype=float)
    n = min(len(p_arr), len(oi_arr))
    if n < 2:
        return {
            "quadrant": "Q1_NEW_LONGS",
            "delta_p_pct": 0.0,
            "delta_oi_pct": 0.0,
            "oi_zscore": 0.0,
            "price_zscore": 0.0,
        }

    p_arr = p_arr[-n:]
    oi_arr = oi_arr[-n:]
    tau = max(1, min(int(lookback), n - 1))

    p_prev = float(p_arr[-1 - tau])
    p_curr = float(p_arr[-1])
    oi_prev = float(oi_arr[-1 - tau])
    oi_curr = float(oi_arr[-1])

    delta_p_pct = ((p_curr - p_prev) / p_prev * 100.0) if abs(p_prev) > 1e-12 else 0.0
    delta_oi_pct = ((oi_curr - oi_prev) / oi_prev * 100.0) if abs(oi_prev) > 1e-12 else 0.0

    # Compute rolling percentage changes over lag=tau (or 1-step if n is short) for z-scores
    if n >= tau + 4:
        oi_diffs = (oi_arr[tau:] - oi_arr[:-tau]) / np.maximum(np.abs(oi_arr[:-tau]), 1e-12) * 100.0
        p_diffs = (p_arr[tau:] - p_arr[:-tau]) / np.maximum(np.abs(p_arr[:-tau]), 1e-12) * 100.0
    else:
        oi_diffs = np.diff(oi_arr) / np.maximum(np.abs(oi_arr[:-1]), 1e-12) * 100.0
        p_diffs = np.diff(p_arr) / np.maximum(np.abs(p_arr[:-1]), 1e-12) * 100.0

    oi_std = float(np.std(oi_diffs))
    oi_mean = float(np.mean(oi_diffs))
    oi_zscore = ((oi_diffs[-1] - oi_mean) / oi_std) if oi_std > 1e-12 else (delta_oi_pct / 0.5)

    p_std = float(np.std(p_diffs))
    p_mean = float(np.mean(p_diffs))
    price_zscore = ((p_diffs[-1] - p_mean) / p_std) if p_std > 1e-12 else (delta_p_pct / 0.5)

    if delta_p_pct >= 0.0 and delta_oi_pct >= 0.0:
        quadrant = "Q1_NEW_LONGS"
    elif delta_p_pct >= 0.0 and delta_oi_pct < 0.0:
        quadrant = "Q2_SHORT_COVERING"
    elif delta_p_pct < 0.0 and delta_oi_pct >= 0.0:
        quadrant = "Q3_NEW_SHORTS"
    else:
        quadrant = "Q4_LONG_LIQ_FLUSH"

    return {
        "quadrant": quadrant,
        "delta_p_pct": float(delta_p_pct),
        "delta_oi_pct": float(delta_oi_pct),
        "oi_zscore": float(oi_zscore),
        "price_zscore": float(price_zscore),
    }


def compute_liquidation_cascade(
    force_orders: Iterable[Dict[str, Any]],
    lookback_sec: int = 300,
    now_ms: Optional[int] = None,
    delta_oi_15m_pct: Optional[float] = None,
    recent_1m_lows: Optional[Sequence[float]] = None,
    ofi_current: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Real-Time Liquidation Cascade & Exhaustion Detector (`@forceOrder`, Section 5.2.D):
      - `S == "SELL"` -> Long position liquidated (`long_liq`).
      - `S == "BUY"`  -> Short position liquidated (`short_liq`).
      - Computes 1m and 5m USD liquidation sums and 24-hour rolling 5m bucket Z-Score.
      - Flags `cascade_exhaustion_trigger` when `liq_zscore >= 3.0` and cascade conditions align.
    """
    orders = list(force_orders)
    if not orders:
        return {
            "long_liq_usd_1m": 0.0,
            "short_liq_usd_1m": 0.0,
            "long_liq_usd_5m": 0.0,
            "short_liq_usd_5m": 0.0,
            "long_liq_zscore": 0.0,
            "short_liq_zscore": 0.0,
            "liq_zscore": 0.0,
            "dominant_liq_side": "NONE",
            "cascade_exhaustion_trigger": False,
        }

    parsed: List[Tuple[int, str, float]] = []
    for item in orders:
        obj = item.get("o", item) if isinstance(item, dict) else {}
        side = str(obj.get("S", obj.get("side", "SELL"))).upper()
        ts = int(obj.get("T", item.get("ts_ms", item.get("E", 0))))
        if "notional_usd" in obj and obj["notional_usd"] is not None:
            usd = float(obj["notional_usd"])
        elif "notional_usd" in item and item["notional_usd"] is not None:
            usd = float(item["notional_usd"])
        else:
            px = float(obj.get("ap", obj.get("p", obj.get("price", 0.0))))
            if px <= 0.0:
                px = float(obj.get("p", 0.0))
            qty = float(obj.get("z", obj.get("q", obj.get("qty", 0.0))))
            if qty <= 0.0:
                qty = float(obj.get("q", 0.0))
            usd = px * qty
        parsed.append((ts, side, max(0.0, usd)))

    ref_ms = int(now_ms if now_ms is not None else max(p[0] for p in parsed))
    win_5m_ms = int(lookback_sec * 1000)
    win_1m_ms = 60_000
    win_24h_ms = 86_400_000

    long_liq_1m = 0.0
    short_liq_1m = 0.0
    long_liq_5m = 0.0
    short_liq_5m = 0.0

    # Build 5-minute buckets over the last 24h (up to 288 buckets)
    n_buckets = max(12, int(win_24h_ms // max(1, win_5m_ms)))
    long_buckets = np.zeros(n_buckets, dtype=float)
    short_buckets = np.zeros(n_buckets, dtype=float)

    for ts, side, usd in parsed:
        age_ms = ref_ms - ts
        if age_ms < 0 or age_ms > win_24h_ms:
            continue
        is_long_liq = side == "SELL" or side == "LONG_LIQ"
        if age_ms <= win_1m_ms:
            if is_long_liq:
                long_liq_1m += usd
            else:
                short_liq_1m += usd
        if age_ms < win_5m_ms:
            if is_long_liq:
                long_liq_5m += usd
            else:
                short_liq_5m += usd

        b_idx = int(age_ms // max(1, win_5m_ms))
        if 0 <= b_idx < n_buckets:
            if is_long_liq:
                long_buckets[b_idx] += usd
            else:
                short_buckets[b_idx] += usd

    # Compute z-score of current 5m bucket (b_idx == 0) against historical 24h buckets
    # If most of the 288 buckets are empty because test data only passed active buckets,
    # adaptively use occupied span or full 288 span if span covers multiple hours
    min_ts = min(p[0] for p in parsed)
    span_buckets = max(12, min(n_buckets, int((ref_ms - min_ts) // max(1, win_5m_ms)) + 1))

    hist_long = long_buckets[:span_buckets]
    hist_short = short_buckets[:span_buckets]

    def _calc_z(curr_val: float, buckets_arr: np.ndarray) -> float:
        if curr_val <= 0.0:
            return 0.0
        # Exclude current bucket from baseline mean/std if baseline has variance
        baseline = buckets_arr[1:] if len(buckets_arr) > 1 else buckets_arr
        mu = float(np.mean(baseline))
        sigma = float(np.std(baseline))
        if sigma > 1e-6:
            return (curr_val - mu) / sigma
        # When baseline is all zeros or constant, compare against full array std
        full_std = float(np.std(buckets_arr))
        full_mu = float(np.mean(buckets_arr))
        return ((curr_val - full_mu) / full_std) if full_std > 1e-6 else 0.0

    long_z = _calc_z(long_liq_5m, hist_long)
    short_z = _calc_z(short_liq_5m, hist_short)
    liq_zscore = max(long_z, short_z)

    if long_liq_5m > short_liq_5m and long_liq_5m > 0:
        dominant_side = "LONG_LIQ"
    elif short_liq_5m > long_liq_5m and short_liq_5m > 0:
        dominant_side = "SHORT_LIQ"
    else:
        dominant_side = "NONE"

    # Evaluate Cascade Exhaustion Trigger (Section 5.2.D)
    cascade_exhaustion = bool(liq_zscore >= 3.0)
    if cascade_exhaustion and delta_oi_15m_pct is not None:
        cascade_exhaustion = cascade_exhaustion and (float(delta_oi_15m_pct) < -1.5)
    if cascade_exhaustion and recent_1m_lows is not None and len(recent_1m_lows) >= 2:
        # Failed to make a new lower low in the latest 1m bars
        cascade_exhaustion = cascade_exhaustion and (float(recent_1m_lows[-1]) >= float(min(recent_1m_lows[:-1])))
    if cascade_exhaustion and ofi_current is not None:
        cascade_exhaustion = cascade_exhaustion and (float(ofi_current) > 0.0)

    return {
        "long_liq_usd_1m": float(long_liq_1m),
        "short_liq_usd_1m": float(short_liq_1m),
        "long_liq_usd_5m": float(long_liq_5m),
        "short_liq_usd_5m": float(short_liq_5m),
        "long_liq_zscore": float(long_z),
        "short_liq_zscore": float(short_z),
        "liq_zscore": float(liq_zscore),
        "dominant_liq_side": dominant_side,
        "cascade_exhaustion_trigger": bool(cascade_exhaustion),
    }


def compute_funding_and_basis(
    mark_price: float,
    index_price: float,
    funding_history: Sequence[float],
    next_funding_ms: int,
    now_ms: int,
    direction: Optional[str] = None,
    current_funding_rate: Optional[float] = None,
    top_trader_ls_ratio: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Funding Rate & Mark-Index Basis Z-Score + Funding Boundary Guard (Section 5.2.E):
      - Basis_t = (P_mark - P_index) / P_index (in bps = * 10^4)
      - Z_funding = (F_t - mu_{F,30d}) / sigma_{F,30d}
      - Extreme Long Crowding: Z_funding > +2.5 (and top_trader_ls_ratio > 2.0 if provided)
      - Funding Boundary Guard: If 0 <= minutes_to_funding <= 10.0 and position direction
        must PAY funding >= 0.05% (0.0005), block/delay entry until after funding timestamp.
    """
    mp = float(mark_price)
    ip = float(index_price)
    basis_bps = ((mp - ip) / ip * 1e4) if ip > 1e-12 else 0.0

    hist_arr = np.asarray(list(funding_history), dtype=float) if funding_history else np.array([], dtype=float)
    if current_funding_rate is not None:
        latest_funding = float(current_funding_rate)
    elif len(hist_arr) > 0:
        latest_funding = float(hist_arr[-1])
    else:
        latest_funding = 0.0

    if len(hist_arr) >= 3:
        mu_f = float(np.mean(hist_arr))
        sigma_f = float(np.std(hist_arr))
        funding_zscore = ((latest_funding - mu_f) / sigma_f) if sigma_f > 1e-12 else 0.0
    else:
        # Standard baseline: normal funding ~0.01% (0.0001) with std ~0.015% (0.00015)
        funding_zscore = (latest_funding - 0.0001) / 0.00015 if abs(latest_funding) > 1e-9 else 0.0

    minutes_to_funding = max(0.0, (float(next_funding_ms) - float(now_ms)) / 60_000.0) if next_funding_ms > 0 else 999.0

    # Funding Boundary Guard: <= 10 minutes to funding and paying >= 0.05% (0.0005)
    in_boundary_window = (0.0 <= minutes_to_funding <= 10.0) and (next_funding_ms >= now_ms)
    dir_upper = (direction or "").upper()
    if dir_upper == "LONG":
        pays_high_funding = latest_funding >= 0.0005
    elif dir_upper == "SHORT":
        pays_high_funding = latest_funding <= -0.0005
    else:
        pays_high_funding = abs(latest_funding) >= 0.0005

    funding_boundary_block = bool(in_boundary_window and pays_high_funding)

    ls_long_crowded = True if top_trader_ls_ratio is None else (float(top_trader_ls_ratio) > 2.0)
    ls_short_crowded = True if top_trader_ls_ratio is None else (float(top_trader_ls_ratio) < 0.5)

    extreme_long_crowding = bool(funding_zscore > 2.5 and ls_long_crowded)
    extreme_short_crowding = bool(funding_zscore < -2.5 and ls_short_crowded)

    return {
        "basis_bps": float(basis_bps),
        "funding_rate": float(latest_funding),
        "funding_zscore": float(funding_zscore),
        "minutes_to_funding": float(minutes_to_funding),
        "funding_boundary_block": funding_boundary_block,
        "extreme_long_crowding": extreme_long_crowding,
        "extreme_short_crowding": extreme_short_crowding,
    }
