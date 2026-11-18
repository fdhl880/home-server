"""
PYROFUEL BOT - LOPEZ DE PRADO TRIPLE-BARRIER SIMULATOR (Task T1.3 / T7.4 / WP-6)
Mensimulasikan kotak Triple-Barrier [SL, TP1/TP2, T_max] tanpa lookahead dengan:
1. Resolusi intrabar konservatif (jika SL dan TP tersentuh pada bar yang sama -> SL menang dulu)
2. Mode Asimetris 2-Tahap (`HIGH_PRECISION_SNIPER_MODE`: TP1 = +0.55R mengunci SL di +0.38R + Runner TP2)
3. Pengecekan Harga Likuidasi 20x Isolated (MMR = 0.4%)
4. Realisme Biaya & Eksekusi (WP-6):
   - Historical funding lookup per 8h/4h UTC boundary (`funding_series` / CSV map, directional LONG vs SHORT)
   - Volatility & size-scaled dynamic slippage (`bar_range_pct / atr_pct` & `notional_usdt`)
   - Wick & gap stop slippage bounded cleanly by candle adverse excursion
   - Maker-first GTX fill realism (runaway non-fill / taker fallback fee & slippage)
"""
import bisect
import csv
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


def compute_liquidation_price(
    entry_price: float,
    direction: str,
    leverage: int = 20,
    mmr: float = 0.004,
) -> float:
    """
    Compute 20x Isolated Margin liquidation price:
        Long:  Entry * (1 - 1/leverage + MMR)  (~ -4.6% at 20x)
        Short: Entry * (1 + 1/leverage - MMR)  (~ +4.6% at 20x)
    """
    lev = max(1.0, float(leverage))
    if direction.upper() == "LONG":
        return float(entry_price) * (1.0 - (1.0 / lev) + float(mmr))
    return float(entry_price) * (1.0 + (1.0 / lev) - float(mmr))


def _funding_boundaries(open_time_ms: int, close_time_ms: int, interval_hours: int = 8) -> List[int]:
    """Return all funding boundary timestamps (00:00, 08:00, 16:00 UTC or interval_hours) in (open_time, close_time]."""
    if open_time_ms <= 0 or close_time_ms <= open_time_ms:
        return []
    step_ms = max(1, int(interval_hours)) * 3600 * 1000
    first_boundary = ((open_time_ms // step_ms) + 1) * step_ms
    boundaries: List[int] = []
    t = first_boundary
    while t <= close_time_ms:
        boundaries.append(int(t))
        t += step_ms
    return boundaries


def _counts_funding_boundary(open_time_ms: int, close_time_ms: int, interval_hours: int = 8) -> int:
    """Count how many funding timestamps fall inside (open_time, close_time]."""
    return len(_funding_boundaries(open_time_ms, close_time_ms, interval_hours=interval_hours))


def parse_funding_series(funding_series: Any) -> Optional[Tuple[List[int], List[float]]]:
    """
    Normalize a funding series into sorted `(timestamps_ms, rates_pct)` lists where
    `rates_pct` is expressed in percentage points (`0.01` = `0.01%` = `0.0001` decimal).
    Accepts `None`, path to `_funding.csv`, `{ts_ms: decimal_rate}` dict, or sequence of dicts/tuples.
    """
    if not funding_series:
        return None

    pairs: List[Tuple[int, float]] = []
    if isinstance(funding_series, str):
        try:
            with open(funding_series, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = int(float(row.get("funding_time") or row.get("fundingTime") or 0))
                    rate_dec = float(row.get("funding_rate") or row.get("fundingRate") or 0.0)
                    if ts > 0:
                        pairs.append((ts, rate_dec * 100.0))
        except Exception:
            return None
    elif isinstance(funding_series, dict):
        for k, v in funding_series.items():
            try:
                ts = int(float(k))
                rate_dec = float(v)
                if ts > 0:
                    pairs.append((ts, rate_dec * 100.0))
            except (TypeError, ValueError):
                continue
    elif isinstance(funding_series, (list, tuple)):
        for item in funding_series:
            try:
                if isinstance(item, dict):
                    ts = int(float(
                        item.get("funding_time")
                        or item.get("fundingTime")
                        or item.get("ts_ms")
                        or item.get("timestamp")
                        or 0
                    ))
                    if "funding_rate_pct" in item and item["funding_rate_pct"] is not None:
                        rate_pct = float(item["funding_rate_pct"])
                    else:
                        rate_dec = float(item.get("funding_rate", item.get("fundingRate", 0.0)) or 0.0)
                        rate_pct = rate_dec * 100.0
                    if ts > 0:
                        pairs.append((ts, rate_pct))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    ts = int(float(item[0]))
                    rate_pct = float(item[1]) * 100.0
                    if ts > 0:
                        pairs.append((ts, rate_pct))
            except (TypeError, ValueError):
                continue

    if not pairs:
        return None
    dedup = dict(pairs)
    sorted_ts = sorted(dedup.keys())
    return (sorted_ts, [dedup[t] for t in sorted_ts])


def lookup_funding_rate_pct(
    boundary_ts_ms: int,
    parsed_ts: Sequence[int],
    parsed_rates_pct: Sequence[float],
    default_rate_pct: float = 0.01,
    interval_hours: int = 8,
) -> float:
    """Look up historical funding rate (%) at `boundary_ts_ms` with small ms-jitter tolerance."""
    if not parsed_ts:
        return float(default_rate_pct)

    pos = bisect.bisect_left(parsed_ts, boundary_ts_ms)
    tolerance_ms = 120_000  # 2m tolerance for Binance boundary timestamp jitter
    best_idx: Optional[int] = None
    best_dist = tolerance_ms + 1

    for cand_idx in (pos - 1, pos):
        if 0 <= cand_idx < len(parsed_ts):
            dist = abs(int(parsed_ts[cand_idx]) - int(boundary_ts_ms))
            if dist <= tolerance_ms and dist < best_dist:
                best_dist = dist
                best_idx = cand_idx

    if best_idx is not None:
        return float(parsed_rates_pct[best_idx])

    # Fallback to most recent prior record within one funding interval
    prior_idx = pos - 1
    max_stale_ms = max(1, int(interval_hours)) * 3600 * 1000
    if 0 <= prior_idx < len(parsed_ts) and 0 <= (boundary_ts_ms - parsed_ts[prior_idx]) <= max_stale_ms:
        return float(parsed_rates_pct[prior_idx])

    return float(default_rate_pct)


def compute_funding_cost_pct(
    open_time_ms: int,
    close_time_ms: int,
    direction: str,
    interval_hours: int = 8,
    default_rate_pct: float = 0.01,
    parsed_funding: Optional[Tuple[List[int], List[float]]] = None,
) -> Tuple[float, int]:
    """
    Compute cumulative funding cost (%) across all funding boundaries in `(open_time_ms, close_time_ms]`.
    When `parsed_funding` is supplied, LONG pays positive funding (`+rate`) and receives negative (`-abs`);
    SHORT receives positive funding (`-rate`) and pays negative (`+abs`).
    When `parsed_funding` is None, preserves flat `funding_events * default_rate_pct`.
    """
    boundaries = _funding_boundaries(open_time_ms, close_time_ms, interval_hours=interval_hours)
    if not boundaries:
        return (0.0, 0)
    if parsed_funding is None:
        return (len(boundaries) * float(default_rate_pct), len(boundaries))

    ts_list, rates_list = parsed_funding
    sign = 1.0 if str(direction).upper() == "LONG" else -1.0
    total_pct = 0.0
    for b_ts in boundaries:
        rate_pct = lookup_funding_rate_pct(
            b_ts,
            ts_list,
            rates_list,
            default_rate_pct=default_rate_pct,
            interval_hours=interval_hours,
        )
        total_pct += sign * rate_pct
    return (float(total_pct), len(boundaries))


def compute_dynamic_slippage_pct(
    bar_high: float,
    bar_low: float,
    bar_close: float,
    atr_pct: Optional[float] = None,
    sl_dist_pct: float = 1.0,
    base_slippage_pct: float = 0.015,
    notional_usdt: float = 0.0,
    is_maker: bool = False,
) -> float:
    """
    Scale slippage (%) dynamically using `(high - low) / close` vs `atr_pct`,
    baseline volatility regime, and notional order size.
    """
    ref_px = max(float(bar_close or 0.0), 1e-12)
    bar_range_pct = max(0.0, (float(bar_high) - float(bar_low)) / ref_px * 100.0)
    ref_atr = (
        float(atr_pct)
        if (atr_pct is not None and float(atr_pct) > 0.0)
        else max(0.30, min(2.0, float(sl_dist_pct) * 0.85))
    )

    if bar_range_pct > 0.0:
        range_atr_ratio = bar_range_pct / max(ref_atr, 0.10)
        atr_scale = ref_atr / 0.60
        vol_scale = float(np.clip(0.55 * range_atr_ratio + 0.45 * atr_scale, 0.5, 6.0))
    else:
        vol_scale = float(np.clip(ref_atr / 0.60, 0.5, 4.0))

    size_scale = 1.0 + min(2.0, max(0.0, float(notional_usdt or 0.0)) / 25_000.0)
    maker_mult = 0.25 if is_maker else 1.0
    return float(base_slippage_pct) * vol_scale * size_scale * maker_mult


def apply_stop_slippage(
    bar_open: float,
    bar_high: float,
    bar_low: float,
    stop_price: float,
    direction: str,
    stop_slip_fraction: float = 0.06,
) -> float:
    """
    Model realistic wick/gap stop slippage past `stop_price` bounded cleanly by
    the candle's adverse excursion `[low, high]`.
    """
    op = float(bar_open)
    hi = float(bar_high)
    lo = float(bar_low)
    sp = float(stop_price)
    frac = float(np.clip(stop_slip_fraction, 0.0, 1.0))

    if str(direction).upper() == "LONG":
        if op < sp:
            # Gap open below SL: trigger begins at gap open and slides bounded by candle low
            overshoot = max(0.0, op - lo)
            slipped = op - frac * overshoot
            return max(lo, min(op, slipped))
        overshoot = max(0.0, sp - lo)
        slipped = sp - frac * overshoot
        return max(lo, min(sp, slipped))

    # SHORT
    if op > sp:
        overshoot = max(0.0, hi - op)
        slipped = op + frac * overshoot
        return min(hi, max(op, slipped))
    overshoot = max(0.0, hi - sp)
    slipped = sp + frac * overshoot
    return min(hi, max(sp, slipped))


def compute_barrier_costs(
    *,
    direction: str,
    outcome: str,
    entry_is_maker: bool,
    entry_bar: Optional[Dict[str, Any]],
    exit_bar: Optional[Dict[str, Any]],
    open_time_ms: int,
    close_time_ms: int,
    sl_dist_pct: float,
    atr_pct: Optional[float] = None,
    notional_usdt: float = 0.0,
    maker_fee_pct: float = 0.02,
    taker_fee_pct: float = 0.05,
    base_slippage_pct: float = 0.015,
    funding_rate_pct: float = 0.01,
    funding_interval_hours: int = 8,
    parsed_funding: Optional[Tuple[List[int], List[float]]] = None,
) -> Dict[str, Any]:
    """
    Canonical transaction cost model shared by `simulate_triple_barrier` and `ShadowEngine`:
    exact maker/taker fees, volatility & size-scaled entry/exit slippage, and historical/8h funding.
    """
    exit_is_maker = str(outcome).upper() in ("TP", "TP2")
    entry_fee = float(maker_fee_pct) if entry_is_maker else float(taker_fee_pct)
    exit_fee = float(maker_fee_pct) if exit_is_maker else float(taker_fee_pct)

    eb = entry_bar or {}
    xb = exit_bar or eb
    e_cl = float(eb.get("close", 1.0) or 1.0)
    e_hi = float(eb.get("high", e_cl) or e_cl)
    e_lo = float(eb.get("low", e_cl) or e_cl)

    x_cl = float(xb.get("close", e_cl) or e_cl)
    x_hi = float(xb.get("high", x_cl) or x_cl)
    x_lo = float(xb.get("low", x_cl) or x_cl)

    entry_slip = compute_dynamic_slippage_pct(
        e_hi, e_lo, e_cl,
        atr_pct=atr_pct,
        sl_dist_pct=sl_dist_pct,
        base_slippage_pct=base_slippage_pct,
        notional_usdt=notional_usdt,
        is_maker=entry_is_maker,
    )
    exit_slip = compute_dynamic_slippage_pct(
        x_hi, x_lo, x_cl,
        atr_pct=atr_pct,
        sl_dist_pct=sl_dist_pct,
        base_slippage_pct=base_slippage_pct,
        notional_usdt=notional_usdt,
        is_maker=exit_is_maker,
    )
    slip_pct = entry_slip + exit_slip

    funding_cost_pct, funding_events = compute_funding_cost_pct(
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        direction=direction,
        interval_hours=funding_interval_hours,
        default_rate_pct=funding_rate_pct,
        parsed_funding=parsed_funding,
    )

    total_cost_pct = entry_fee + exit_fee + slip_pct + funding_cost_pct
    return {
        "entry_fee_pct": round(entry_fee, 5),
        "exit_fee_pct": round(exit_fee, 5),
        "entry_slippage_pct": round(entry_slip, 5),
        "exit_slippage_pct": round(exit_slip, 5),
        "slippage_pct": round(slip_pct, 5),
        "funding_cost_pct": round(funding_cost_pct, 5),
        "funding_events": int(funding_events),
        "cost_pct": round(total_cost_pct, 5),
    }


def _evaluate_gtx_entry_fill(
    direction: str,
    entry_px: float,
    sl_dist_pct: float,
    first_bar: Dict[str, Any],
    *,
    maker_fallback_to_taker: bool = True,
    maker_touch_buffer_bps: float = 2.0,
    maker_non_fill_prob: float = 0.0,
    maker_seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Evaluate realistic passive GTX maker limit fill on `future_candles[0]`.
    Models runaway non-fill, weak-touch queue misses, and optional taker fallback chase.
    """
    op0 = float(first_bar.get("open", first_bar.get("close", entry_px)))
    hi0 = float(first_bar.get("high", op0))
    lo0 = float(first_bar.get("low", op0))
    cl0 = float(first_bar.get("close", op0))
    touch_buf = entry_px * (float(maker_touch_buffer_bps) / 10_000.0)

    if direction == "LONG":
        ran_away = lo0 > entry_px
        weak_touch = (not ran_away) and (lo0 > entry_px - touch_buf) and (cl0 > entry_px + touch_buf)
        gap_away_pct = max(0.0, (lo0 - entry_px) / max(entry_px, 1e-12) * 100.0)
        chase_px = max(entry_px, op0) if ran_away else (entry_px + touch_buf)
    else:
        ran_away = hi0 < entry_px
        weak_touch = (not ran_away) and (hi0 < entry_px + touch_buf) and (cl0 < entry_px - touch_buf)
        gap_away_pct = max(0.0, (entry_px - hi0) / max(entry_px, 1e-12) * 100.0)
        chase_px = min(entry_px, op0) if ran_away else (entry_px - touch_buf)

    prob_missed = False
    if float(maker_non_fill_prob or 0.0) > 0.0 and not (ran_away or weak_touch):
        seed_val = int(maker_seed if maker_seed is not None else (int(first_bar.get("open_time", 0) or 0) % (2 ** 31)))
        rng = np.random.default_rng(seed_val)
        prob_missed = bool(rng.random() < float(maker_non_fill_prob))

    if ran_away or weak_touch or prob_missed:
        max_chase_pct = max(0.25, 0.50 * float(sl_dist_pct))
        if maker_fallback_to_taker and gap_away_pct <= max_chase_pct:
            return {
                "filled": True,
                "entry_fill_mode": "TAKER_FALLBACK",
                "entry_is_maker": False,
                "actual_entry_price": float(chase_px),
            }
        return {
            "filled": False,
            "entry_fill_mode": "NO_FILL",
            "entry_is_maker": False,
            "actual_entry_price": float(entry_px),
        }

    return {
        "filled": True,
        "entry_fill_mode": "MAKER_FILLED",
        "entry_is_maker": True,
        "actual_entry_price": float(entry_px),
    }


def simulate_triple_barrier(
    candidate_or_params: Union[Any, Dict[str, Any]],
    future_candles: Sequence[Dict[str, Any]],
    sniper_mode: Optional[bool] = None,
    leverage: int = 20,
    mmr: float = 0.004,
    maker_fee_pct: float = 0.02,
    taker_fee_pct: float = 0.05,
    base_slippage_pct: float = 0.015,
    funding_rate_pct: float = 0.01,
    funding_interval_hours: int = 8,
    tp1_partial_weight: float = 0.35,
    funding_series: Optional[Any] = None,
    atr_pct: Optional[float] = None,
    notional_usdt: float = 0.0,
    stop_slip_fraction: float = 0.06,
    maker_fallback_to_taker: bool = True,
    maker_touch_buffer_bps: float = 2.0,
    maker_non_fill_prob: float = 0.0,
    maker_seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Simulate a single trade over `future_candles` (which MUST start strictly at index t+1).
    Returns detailed execution outcome including `outcome`, `r_multiple_net`, `r_multiple_gross`,
    `net_return_pct`, `margin_pnl_pct`, `bars_held`, `exit_index_offset`, `mae_pct`, `mfe_pct`,
    and granular realism telemetry (`entry_fill_mode`, `slippage_pct`, `funding_cost_pct`).
    """
    c = candidate_or_params
    direction = str(c["direction"] if isinstance(c, dict) else c.direction).upper()
    entry_px = float(c["entry_price"] if isinstance(c, dict) else c.entry_price)
    sl_px = float(c["sl_price"] if isinstance(c, dict) else c.sl_price)
    tp2_px = float(
        (c.get("tp2_price") or c.get("tp_price"))
        if isinstance(c, dict)
        else getattr(c, "tp2_price", getattr(c, "tp_price", 0.0))
    )
    tp1_px = float(
        c.get("tp1_price", 0.0)
        if isinstance(c, dict)
        else getattr(c, "tp1_price", 0.0)
    )
    max_bars = int(
        c.get("vertical_barrier_bars", 16)
        if isinstance(c, dict)
        else getattr(c, "vertical_barrier_bars", 16)
    )
    entry_type = str(
        c.get("entry_type", "MAKER_FIRST_GTX")
        if isinstance(c, dict)
        else getattr(c, "entry_type", "MAKER_FIRST_GTX")
    )
    tp1_r = float(c.get("tp1_r", 0.55) if isinstance(c, dict) else getattr(c, "tp1_r", 0.55))
    sl_lock_r = float(
        c.get("sl_lock_after_tp1_r", 0.38)
        if isinstance(c, dict)
        else getattr(c, "sl_lock_after_tp1_r", 0.38)
    )
    if sniper_mode is None:
        sniper_mode = bool(
            c.get("sniper_mode", True) if isinstance(c, dict) else getattr(c, "sniper_mode", True)
        )
    if atr_pct is None:
        raw_atr_pct = c.get("atr_pct") if isinstance(c, dict) else getattr(c, "atr_pct", None)
        if raw_atr_pct is not None:
            atr_pct = float(raw_atr_pct)

    sl_dist = abs(entry_px - sl_px)
    sl_dist_pct = (sl_dist / max(entry_px, 1e-12)) * 100.0
    if tp1_px <= 0:
        tp1_px = (
            entry_px + tp1_r * sl_dist
            if direction == "LONG"
            else entry_px - tp1_r * sl_dist
        )

    locked_sl_px = (
        entry_px + sl_lock_r * sl_dist
        if direction == "LONG"
        else entry_px - sl_lock_r * sl_dist
    )

    horizon = min(max(1, max_bars), len(future_candles))
    if horizon == 0:
        return {
            "outcome": "NO_FUTURE_DATA",
            "exit_price": entry_px,
            "actual_entry_price": entry_px,
            "entry_fill_mode": "NONE",
            "r_multiple_gross": 0.0,
            "r_multiple_net": 0.0,
            "gross_return_pct": 0.0,
            "cost_pct": 0.0,
            "entry_fee_pct": 0.0,
            "exit_fee_pct": 0.0,
            "entry_slippage_pct": 0.0,
            "exit_slippage_pct": 0.0,
            "slippage_pct": 0.0,
            "funding_cost_pct": 0.0,
            "funding_events": 0,
            "net_return_pct": 0.0,
            "margin_pnl_pct": 0.0,
            "bars_held": 0,
            "exit_index_offset": 0,
            "tp1_hit": False,
            "liquidated": False,
            "mae_pct": 0.0,
            "mfe_pct": 0.0,
        }

    # Evaluate Maker-First GTX vs Immediate IOC entry fill on bar 0
    if entry_type == "MAKER_FIRST_GTX":
        fill_info = _evaluate_gtx_entry_fill(
            direction=direction,
            entry_px=entry_px,
            sl_dist_pct=sl_dist_pct,
            first_bar=future_candles[0],
            maker_fallback_to_taker=maker_fallback_to_taker,
            maker_touch_buffer_bps=maker_touch_buffer_bps,
            maker_non_fill_prob=maker_non_fill_prob,
            maker_seed=maker_seed,
        )
        if not fill_info["filled"]:
            return {
                "outcome": "MAKER_NO_FILL",
                "exit_price": entry_px,
                "actual_entry_price": entry_px,
                "entry_fill_mode": "NO_FILL",
                "r_multiple_gross": 0.0,
                "r_multiple_net": 0.0,
                "gross_return_pct": 0.0,
                "cost_pct": 0.0,
                "entry_fee_pct": 0.0,
                "exit_fee_pct": 0.0,
                "entry_slippage_pct": 0.0,
                "exit_slippage_pct": 0.0,
                "slippage_pct": 0.0,
                "funding_cost_pct": 0.0,
                "funding_events": 0,
                "net_return_pct": 0.0,
                "margin_pnl_pct": 0.0,
                "bars_held": 1,
                "exit_index_offset": 1,
                "tp1_hit": False,
                "liquidated": False,
                "mae_pct": 0.0,
                "mfe_pct": 0.0,
            }
        actual_entry_px = float(fill_info["actual_entry_price"])
        entry_is_maker = bool(fill_info["entry_is_maker"])
        entry_fill_mode = str(fill_info["entry_fill_mode"])
    else:
        actual_entry_px = entry_px
        entry_is_maker = False
        entry_fill_mode = "TAKER_IOC"

    liq_px = compute_liquidation_price(actual_entry_px, direction, leverage=leverage, mmr=mmr)
    parsed_funding = parse_funding_series(funding_series)

    tp1_hit = False
    active_sl = sl_px
    outcome = "TIME_BARRIER"
    exit_px = actual_entry_px
    bars_held = horizon
    exit_bar_idx = horizon - 1
    liquidated = False
    mae_pct = 0.0
    mfe_pct = 0.0

    first_ot = int(future_candles[0].get("open_time", 0) or 0)
    last_ct = int(future_candles[0].get("close_time", first_ot + 3600_000 if first_ot > 0 else 0) or 0)

    for idx in range(horizon):
        fc = future_candles[idx]
        hi = float(fc["high"])
        lo = float(fc["low"])
        cl = float(fc["close"])
        op = float(fc.get("open", cl))
        ot = int(fc.get("open_time", 0) or 0)
        ct = int(fc.get("close_time", ot + 3600_000 if ot > 0 else 0) or 0)
        if ct > 0:
            last_ct = ct

        if direction == "LONG":
            adv = max(0.0, (actual_entry_px - lo) / actual_entry_px * 100.0)
            fav = max(0.0, (hi - actual_entry_px) / actual_entry_px * 100.0)
            mae_pct = max(mae_pct, adv)
            mfe_pct = max(mfe_pct, fav)

            if (lo <= liq_px and liq_px >= active_sl) or op <= liq_px:
                outcome = "LIQUIDATED"
                exit_px = min(liq_px, op) if op <= liq_px else liq_px
                bars_held = idx + 1
                exit_bar_idx = idx
                liquidated = True
                break

            if not tp1_hit:
                if lo <= active_sl:
                    outcome = "SL"
                    exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                    bars_held = idx + 1
                    exit_bar_idx = idx
                    break

                if sniper_mode:
                    if hi >= tp2_px:
                        tp1_hit = True
                        outcome = "TP2"
                        exit_px = tp2_px
                        bars_held = idx + 1
                        exit_bar_idx = idx
                        break
                    elif hi >= tp1_px:
                        tp1_hit = True
                        active_sl = locked_sl_px
                        if cl <= active_sl and op > active_sl:
                            outcome = "TP1_LOCK_WIN"
                            exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                            bars_held = idx + 1
                            exit_bar_idx = idx
                            break
                else:
                    if hi >= tp2_px:
                        outcome = "TP"
                        exit_px = tp2_px
                        bars_held = idx + 1
                        exit_bar_idx = idx
                        break
            else:
                if lo <= active_sl:
                    outcome = "TP1_LOCK_WIN"
                    exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                    bars_held = idx + 1
                    exit_bar_idx = idx
                    break
                elif hi >= tp2_px:
                    outcome = "TP2"
                    exit_px = tp2_px
                    bars_held = idx + 1
                    exit_bar_idx = idx
                    break

        else:  # SHORT
            adv = max(0.0, (hi - actual_entry_px) / actual_entry_px * 100.0)
            fav = max(0.0, (actual_entry_px - lo) / actual_entry_px * 100.0)
            mae_pct = max(mae_pct, adv)
            mfe_pct = max(mfe_pct, fav)

            if (hi >= liq_px and liq_px <= active_sl) or op >= liq_px:
                outcome = "LIQUIDATED"
                exit_px = max(liq_px, op) if op >= liq_px else liq_px
                bars_held = idx + 1
                exit_bar_idx = idx
                liquidated = True
                break

            if not tp1_hit:
                if hi >= active_sl:
                    outcome = "SL"
                    exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                    bars_held = idx + 1
                    exit_bar_idx = idx
                    break

                if sniper_mode:
                    if lo <= tp2_px:
                        tp1_hit = True
                        outcome = "TP2"
                        exit_px = tp2_px
                        bars_held = idx + 1
                        exit_bar_idx = idx
                        break
                    elif lo <= tp1_px:
                        tp1_hit = True
                        active_sl = locked_sl_px
                        if cl >= active_sl and op < active_sl:
                            outcome = "TP1_LOCK_WIN"
                            exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                            bars_held = idx + 1
                            exit_bar_idx = idx
                            break
                else:
                    if lo <= tp2_px:
                        outcome = "TP"
                        exit_px = tp2_px
                        bars_held = idx + 1
                        exit_bar_idx = idx
                        break
            else:
                if hi >= active_sl:
                    outcome = "TP1_LOCK_WIN"
                    exit_px = apply_stop_slippage(op, hi, lo, active_sl, direction, stop_slip_fraction=stop_slip_fraction)
                    bars_held = idx + 1
                    exit_bar_idx = idx
                    break
                elif lo <= tp2_px:
                    outcome = "TP2"
                    exit_px = tp2_px
                    bars_held = idx + 1
                    exit_bar_idx = idx
                    break

    if outcome == "TIME_BARRIER":
        exit_bar_idx = horizon - 1
        exit_px = float(future_candles[exit_bar_idx]["close"])

    costs = compute_barrier_costs(
        direction=direction,
        outcome=outcome,
        entry_is_maker=entry_is_maker,
        entry_bar=future_candles[0],
        exit_bar=future_candles[exit_bar_idx],
        open_time_ms=first_ot,
        close_time_ms=last_ct,
        sl_dist_pct=sl_dist_pct,
        atr_pct=atr_pct,
        notional_usdt=notional_usdt,
        maker_fee_pct=maker_fee_pct,
        taker_fee_pct=taker_fee_pct,
        base_slippage_pct=base_slippage_pct,
        funding_rate_pct=funding_rate_pct,
        funding_interval_hours=funding_interval_hours,
        parsed_funding=parsed_funding,
    )

    if liquidated:
        gross_ret_pct = -(100.0 / max(1.0, float(leverage)))
        cost_pct = costs["cost_pct"]
        net_ret_pct = gross_ret_pct
        r_gross = -1.0 / max(sl_dist_pct * float(leverage) / 100.0, 0.01)
        r_net = r_gross
        margin_pnl_pct = -100.0
    else:
        if direction == "LONG":
            runner_ret_pct = (exit_px - actual_entry_px) / max(actual_entry_px, 1e-12) * 100.0
            tp1_ret_pct = (tp1_px - actual_entry_px) / max(actual_entry_px, 1e-12) * 100.0
        else:
            runner_ret_pct = (actual_entry_px - exit_px) / max(actual_entry_px, 1e-12) * 100.0
            tp1_ret_pct = (actual_entry_px - tp1_px) / max(actual_entry_px, 1e-12) * 100.0

        if sniper_mode and tp1_hit:
            w1 = float(np.clip(tp1_partial_weight, 0.0, 1.0))
            gross_ret_pct = w1 * tp1_ret_pct + (1.0 - w1) * runner_ret_pct
        else:
            gross_ret_pct = runner_ret_pct

        cost_pct = float(costs["cost_pct"])
        net_ret_pct = gross_ret_pct - cost_pct

        r_gross = gross_ret_pct / max(sl_dist_pct, 1e-9)
        r_net = net_ret_pct / max(sl_dist_pct, 1e-9)
        margin_pnl_pct = net_ret_pct * float(leverage)

    return {
        "outcome": outcome,
        "exit_price": round(exit_px, 8),
        "actual_entry_price": round(actual_entry_px, 8),
        "entry_fill_mode": entry_fill_mode,
        "r_multiple_gross": round(float(r_gross), 4),
        "r_multiple_net": round(float(r_net), 4),
        "gross_return_pct": round(float(gross_ret_pct), 4),
        "cost_pct": round(float(cost_pct), 4),
        "entry_fee_pct": round(float(costs["entry_fee_pct"]), 4),
        "exit_fee_pct": round(float(costs["exit_fee_pct"]), 4),
        "entry_slippage_pct": round(float(costs["entry_slippage_pct"]), 4),
        "exit_slippage_pct": round(float(costs["exit_slippage_pct"]), 4),
        "slippage_pct": round(float(costs["slippage_pct"]), 4),
        "funding_cost_pct": round(float(costs["funding_cost_pct"]), 4),
        "funding_events": int(costs["funding_events"]),
        "net_return_pct": round(float(net_ret_pct), 4),
        "margin_pnl_pct": round(float(margin_pnl_pct), 3),
        "bars_held": int(bars_held),
        "exit_index_offset": int(bars_held),
        "tp1_hit": bool(tp1_hit),
        "liquidated": bool(liquidated),
        "mae_pct": round(float(mae_pct), 4),
        "mfe_pct": round(float(mfe_pct), 4),
    }
