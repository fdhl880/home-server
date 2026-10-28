"""
PYROFUEL BOT - STRATEGY S4: EXTREME FUNDING & BAND REVERSION (Task T4.2)
Aktif pada rezim `MEAN_REVERT` saat terjadi kepadatan posisi ekstrem (|Z_funding| >= 2.0
atau ekstensi harga menembus pita luar Bollinger/Keltner > 2.2 sigma) disertai
CVD Absorption Divergence dan kegagalan mencetak titik ekstrem baru.
"""
from typing import Any, Dict, List, Optional, Sequence
import numpy as np
from strategies.base import (
    SetupCandidate,
    extract_arrays,
    compute_ema,
    compute_atr,
    infer_micro_state,
    build_sniper_candidate,
)

STRATEGY_ID = "S4_EXTREME_FUNDING_REVERSION"
ALLOWED_REGIMES = {"MEAN_REVERT"}


def evaluate(
    klines: Sequence[Any],
    regime_state: Dict[str, Any],
    micro_state: Optional[Dict[str, Any]] = None,
    symbol: str = "",
) -> Optional[SetupCandidate]:
    """
    Evaluate S4_EXTREME_FUNDING_REVERSION on closed klines (strictly no-lookahead).
    """
    regime = str((regime_state or {}).get("regime", "UNKNOWN"))
    if regime not in ALLOWED_REGIMES:
        return None

    arr = extract_arrays(klines)
    closes = arr["close"]
    opens = arr["open"]
    highs = arr["high"]
    lows = arr["low"]
    n = len(closes)
    if n < 30:
        return None

    ema50 = compute_ema(closes, 50)
    atr14 = compute_atr(highs, lows, closes, 14)

    curr_close = float(closes[-1])
    curr_open = float(opens[-1])
    curr_high = float(highs[-1])
    curr_low = float(lows[-1])
    curr_ema50 = float(ema50[-1])
    curr_atr = float(atr14[-1])
    if curr_close <= 0 or curr_atr <= 0:
        return None

    # Bollinger / Keltner 2.2-sigma bands over 20 bars
    win = closes[-20:]
    bb_mid = float(np.mean(win))
    bb_std = max(float(np.std(win)), curr_atr * 0.5)
    upper_22 = bb_mid + 2.2 * bb_std
    lower_22 = bb_mid - 2.2 * bb_std

    ms = infer_micro_state(arr, micro_state)
    funding_z = float(ms.get("funding_zscore", 0.0) or 0.0)
    tfi_5m = float(ms.get("tfi_5m", 0.0) or 0.0)
    bull_abs = bool(ms.get("bullish_absorption", False))
    bear_abs = bool(ms.get("bearish_absorption", False))

    # Candidate SHORT: Extreme Long Crowding (Z_funding >= +2.0) or Outer Upper Band (> 2.2 sigma)
    touched_upper = (curr_high >= upper_22 or float(highs[-2]) >= upper_22)
    crowded_long = (funding_z >= 2.0) or touched_upper
    failed_new_high = (curr_close < curr_open) or (curr_close < float(highs[-1]) - 0.40 * (curr_high - curr_low))

    if crowded_long and touched_upper and failed_new_high and (bear_abs or tfi_5m <= -0.05):
        extreme_high = max(curr_high, float(highs[-2]))
        raw_sl = extreme_high + 0.40 * curr_atr
        sl_dist = abs(raw_sl - curr_close)
        target_mean = min(curr_ema50, bb_mid)
        raw_tp2 = min(target_mean, curr_close - 1.75 * max(sl_dist, curr_close * 0.0055))
        tags: List[str] = ["MEAN_REVERT_UPPER_2.2SIGMA", "CVD_BEARISH_ABSORPTION"]
        if funding_z >= 2.0:
            tags.append(f"EXTREME_POSITIVE_FUNDING_Z_{funding_z:.1f}")

        return build_sniper_candidate(
            strategy_id=STRATEGY_ID,
            direction="SHORT",
            entry_price=curr_close,
            raw_sl_price=raw_sl,
            raw_tp2_price=raw_tp2,
            vertical_barrier_bars=24,
            structural_anchor_desc=f"Bearish funding/band reversion from >2.2sigma ({upper_22:.4f}, Z_fund={funding_z:+.2f}) to EMA50 ({curr_ema50:.4f})",
            confluence_tags=tags,
            entry_type="MAKER_FIRST_GTX",
            min_sl_pct=0.45,
            max_sl_pct=1.80,
            min_tp2_r=1.70,
            regime=regime,
            symbol=symbol,
        )

    # Candidate LONG: Extreme Short Crowding (Z_funding <= -2.0) or Outer Lower Band (< -2.2 sigma)
    touched_lower = (curr_low <= lower_22 or float(lows[-2]) <= lower_22)
    crowded_short = (funding_z <= -2.0) or touched_lower
    failed_new_low = (curr_close > curr_open) or (curr_close > float(lows[-1]) + 0.40 * (curr_high - curr_low))

    if crowded_short and touched_lower and failed_new_low and (bull_abs or tfi_5m >= 0.05):
        extreme_low = min(curr_low, float(lows[-2]))
        raw_sl = extreme_low - 0.40 * curr_atr
        sl_dist = abs(curr_close - raw_sl)
        target_mean = max(curr_ema50, bb_mid)
        raw_tp2 = max(target_mean, curr_close + 1.75 * max(sl_dist, curr_close * 0.0055))
        tags = ["MEAN_REVERT_LOWER_2.2SIGMA", "CVD_BULLISH_ABSORPTION"]
        if funding_z <= -2.0:
            tags.append(f"EXTREME_NEGATIVE_FUNDING_Z_{funding_z:.1f}")

        return build_sniper_candidate(
            strategy_id=STRATEGY_ID,
            direction="LONG",
            entry_price=curr_close,
            raw_sl_price=raw_sl,
            raw_tp2_price=raw_tp2,
            vertical_barrier_bars=24,
            structural_anchor_desc=f"Bullish funding/band reversion from <-2.2sigma ({lower_22:.4f}, Z_fund={funding_z:+.2f}) to EMA50 ({curr_ema50:.4f})",
            confluence_tags=tags,
            entry_type="MAKER_FIRST_GTX",
            min_sl_pct=0.45,
            max_sl_pct=1.80,
            min_tp2_r=1.70,
            regime=regime,
            symbol=symbol,
        )

    return None


generate_signal = evaluate
