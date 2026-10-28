"""
PYROFUEL BOT - STRATEGY S3: LIQUIDATION CASCADE EXHAUSTION FADE (Task T4.2 / T3.5)
Aktif pada rezim `CASCADE_EXHAUSTION` atau `MEAN_REVERT`.
Menangkap titik infleksi akhir kaskade likuidasi (Liquidity Sweep + Hawkes Inflection +
CVD Absorption) dengan Sniper SL super presisi (0.50% <= d_SL <= 0.85%) di balik ekor sapuan.
"""
from typing import Any, Dict, List, Optional, Sequence
import numpy as np
from strategies.base import (
    SetupCandidate,
    extract_arrays,
    compute_atr,
    infer_micro_state,
    build_sniper_candidate,
)

STRATEGY_ID = "S3_LIQ_CASCADE_FADE"
ALLOWED_REGIMES = {"CASCADE_EXHAUSTION", "MEAN_REVERT"}


def evaluate(
    klines: Sequence[Any],
    regime_state: Dict[str, Any],
    micro_state: Optional[Dict[str, Any]] = None,
    symbol: str = "",
) -> Optional[SetupCandidate]:
    """
    Evaluate S3_LIQ_CASCADE_FADE on closed klines (strictly no-lookahead).
    """
    regime = str((regime_state or {}).get("regime", "UNKNOWN"))
    ms_raw = micro_state or {}
    hawkes_state = str(ms_raw.get("hawkes_state", ""))

    # Block catching a falling knife when Hawkes intensity is still accelerating
    if hawkes_state == "CASCADE_ACCELERATING":
        return None

    if regime not in ALLOWED_REGIMES and hawkes_state != "CASCADE_EXHAUSTED_INFLECTION":
        return None

    arr = extract_arrays(klines)
    closes = arr["close"]
    opens = arr["open"]
    highs = arr["high"]
    lows = arr["low"]
    vols = arr["volume"]
    n = len(closes)
    if n < 20:
        return None

    atr14 = compute_atr(highs, lows, closes, 14)
    curr_close = float(closes[-1])
    curr_open = float(opens[-1])
    curr_high = float(highs[-1])
    curr_low = float(lows[-1])
    curr_atr = float(atr14[-1])
    if curr_close <= 0 or curr_atr <= 0:
        return None

    ms = infer_micro_state(arr, micro_state)
    liq_z = float(ms.get("liq_zscore", 0.0) or 0.0)
    oi_quadrant = str(ms.get("oi_quadrant", "NEUTRAL"))
    tfi_5m = float(ms.get("tfi_5m", 0.0) or 0.0)
    bull_abs = bool(ms.get("bullish_absorption", False))
    bear_abs = bool(ms.get("bearish_absorption", False))

    # 24-bar rolling VWAP
    vwap_win = min(24, n)
    typ_px = (highs[-vwap_win:] + lows[-vwap_win:] + closes[-vwap_win:]) / 3.0
    vol_win = np.maximum(vols[-vwap_win:], 1e-12)
    vwap_24 = float(np.sum(typ_px * vol_win) / np.sum(vol_win))

    look = min(14, n - 2)
    prior_swing_low = float(np.min(lows[-(look + 1):-1]))
    prior_swing_high = float(np.max(highs[-(look + 1):-1]))

    # Check Bullish Liquidity Sweep & Reclaim
    swept_low = (curr_low <= prior_swing_low * 1.001) or (
        n >= 3 and float(lows[-2]) <= float(np.min(lows[-(look + 2):-2])) * 1.001
    )
    reclaimed_low = curr_close > min(prior_swing_low, curr_low + 0.45 * (curr_high - curr_low)) and curr_close >= curr_open
    liq_flush_ok = (
        liq_z >= 2.0
        or oi_quadrant == "Q4_LONG_LIQ_FLUSH"
        or hawkes_state == "CASCADE_EXHAUSTED_INFLECTION"
        or bull_abs
    )

    if swept_low and reclaimed_low and liq_flush_ok and (tfi_5m >= 0.10 or bull_abs):
        extreme_wick = min(curr_low, float(lows[-2]))
        raw_sl = extreme_wick - 0.30 * curr_atr
        sl_dist = abs(curr_close - raw_sl)
        raw_tp2 = max(vwap_24, curr_close + 1.85 * max(sl_dist, curr_close * 0.0055))
        tags: List[str] = ["LIQ_SWEEP_LOW_RECLAIM", "CVD_BULLISH_ABSORPTION"]
        if hawkes_state == "CASCADE_EXHAUSTED_INFLECTION":
            tags.append("HAWKES_EXHAUSTED_INFLECTION")
        if oi_quadrant == "Q4_LONG_LIQ_FLUSH":
            tags.append("OI_Q4_LONG_LIQ_FLUSH")

        return build_sniper_candidate(
            strategy_id=STRATEGY_ID,
            direction="LONG",
            entry_price=curr_close,
            raw_sl_price=raw_sl,
            raw_tp2_price=raw_tp2,
            vertical_barrier_bars=12,
            structural_anchor_desc=f"Bullish liquidity sweep below {prior_swing_low:.4f} (wick {extreme_wick:.4f}) + CVD absorption",
            confluence_tags=tags,
            entry_type="MAKER_FIRST_GTX",
            min_sl_pct=0.50,
            max_sl_pct=0.85,
            min_tp2_r=1.80,
            regime=regime,
            symbol=symbol,
        )

    # Check Bearish Liquidity Sweep (Short Squeeze Exhaustion) & Reject
    swept_high = (curr_high >= prior_swing_high * 0.999) or (
        n >= 3 and float(highs[-2]) >= float(np.max(highs[-(look + 2):-2])) * 0.999
    )
    rejected_high = curr_close < max(prior_swing_high, curr_high - 0.45 * (curr_high - curr_low)) and curr_close <= curr_open
    short_squeeze_ok = (
        liq_z >= 2.0
        or oi_quadrant == "Q2_SHORT_COVERING"
        or hawkes_state == "CASCADE_EXHAUSTED_INFLECTION"
        or bear_abs
    )

    if swept_high and rejected_high and short_squeeze_ok and (tfi_5m <= -0.10 or bear_abs):
        extreme_wick = max(curr_high, float(highs[-2]))
        raw_sl = extreme_wick + 0.30 * curr_atr
        sl_dist = abs(raw_sl - curr_close)
        raw_tp2 = min(vwap_24, curr_close - 1.85 * max(sl_dist, curr_close * 0.0055))
        tags = ["LIQ_SWEEP_HIGH_REJECT", "CVD_BEARISH_ABSORPTION"]
        if hawkes_state == "CASCADE_EXHAUSTED_INFLECTION":
            tags.append("HAWKES_EXHAUSTED_INFLECTION")

        return build_sniper_candidate(
            strategy_id=STRATEGY_ID,
            direction="SHORT",
            entry_price=curr_close,
            raw_sl_price=raw_sl,
            raw_tp2_price=raw_tp2,
            vertical_barrier_bars=12,
            structural_anchor_desc=f"Bearish liquidity sweep above {prior_swing_high:.4f} (wick {extreme_wick:.4f}) + CVD absorption",
            confluence_tags=tags,
            entry_type="MAKER_FIRST_GTX",
            min_sl_pct=0.50,
            max_sl_pct=0.85,
            min_tp2_r=1.80,
            regime=regime,
            symbol=symbol,
        )

    return None


generate_signal = evaluate
