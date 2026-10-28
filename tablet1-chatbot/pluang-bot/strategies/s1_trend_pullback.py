"""
PYROFUEL BOT - STRATEGY S1: TREND PULLBACK TO STRUCTURAL ANCHOR (Task T4.2)
Aktif hanya pada rezim `TREND_BULL` atau `TREND_BEAR`.
Menangkap kelanjutan tren saat harga melakukan pullback ke zona EMA21 / Fair Value Gap (FVG) /
Order Block disertai konfirmasi pembalikan positif Trade Flow Imbalance (TFI) & OFI.
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

STRATEGY_ID = "S1_TREND_PULLBACK"
ALLOWED_REGIMES = {"TREND_BULL", "TREND_BEAR"}


def evaluate(
    klines: Sequence[Any],
    regime_state: Dict[str, Any],
    micro_state: Optional[Dict[str, Any]] = None,
    symbol: str = "",
) -> Optional[SetupCandidate]:
    """
    Evaluate S1_TREND_PULLBACK on closed klines (strictly no-lookahead).
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

    ema21 = compute_ema(closes, 21)
    ema50 = compute_ema(closes, 50)
    atr14 = compute_atr(highs, lows, closes, 14)

    curr_close = float(closes[-1])
    curr_open = float(opens[-1])
    curr_high = float(highs[-1])
    curr_low = float(lows[-1])
    curr_ema21 = float(ema21[-1])
    curr_ema50 = float(ema50[-1])
    curr_atr = float(atr14[-1])

    if curr_close <= 0 or curr_atr <= 0:
        return None

    ms = infer_micro_state(arr, micro_state)
    tfi_5m = float(ms.get("tfi_5m", 0.0) or 0.0)
    tfi_15m = float(ms.get("tfi_15m", 0.0) or 0.0)
    ofi_z = float(ms.get("ofi_z", 0.0) or 0.0)
    oi_quadrant = str(ms.get("oi_quadrant", "NEUTRAL"))

    # Check Bullish FVG / Order Block in recent 8 bars
    bull_fvg = False
    bear_fvg = False
    for k in range(max(2, n - 8), n - 1):
        if lows[k] > highs[k - 2]:
            bull_fvg = True
        if highs[k] < lows[k - 2]:
            bear_fvg = True

    if regime == "TREND_BULL":
        # Structural alignment: EMA21 >= EMA50 * 0.999 and pullback touched EMA21 / OB zone
        if curr_ema21 < curr_ema50 * 0.998:
            return None

        touched_zone = (
            curr_low <= curr_ema21 * 1.004
            or float(lows[-2]) <= float(ema21[-2]) * 1.004
        )
        reclaimed_ema21 = curr_close >= curr_ema21 * 0.9995 and curr_close > curr_open
        flow_ok = (tfi_5m >= 0.12 or tfi_15m >= 0.10 or ofi_z >= 0.40)
        oi_ok = oi_quadrant != "Q4_LONG_LIQ_FLUSH"

        if not (touched_zone and reclaimed_ema21 and flow_ok and oi_ok):
            return None

        swing_low = float(np.min(lows[-4:]))
        raw_sl = swing_low - 0.35 * curr_atr
        prior_swing_high = float(np.max(highs[-16:]))
        raw_tp2 = max(prior_swing_high, curr_close + 2.2 * abs(curr_close - raw_sl))

        tags: List[str] = ["TREND_BULL_ANCHOR", "EMA21_PULLBACK_RECLAIM"]
        if bull_fvg:
            tags.append("BULLISH_FVG_SUPPORT")
        if oi_quadrant == "Q1_NEW_LONGS":
            tags.append("OI_Q1_NEW_LONGS")
        if tfi_5m >= 0.15:
            tags.append("POSITIVE_TFI_REVERSAL")

        return build_sniper_candidate(
            strategy_id=STRATEGY_ID,
            direction="LONG",
            entry_price=curr_close,
            raw_sl_price=raw_sl,
            raw_tp2_price=raw_tp2,
            vertical_barrier_bars=16,
            structural_anchor_desc=f"Bullish pullback to EMA21 ({curr_ema21:.4f}) & swing low {swing_low:.4f} with TFI={tfi_5m:+.2f}",
            confluence_tags=tags,
            entry_type="MAKER_FIRST_GTX",
            min_sl_pct=0.50,
            max_sl_pct=1.65,
            min_tp2_r=1.80,
            regime=regime,
            symbol=symbol,
        )

    elif regime == "TREND_BEAR":
        if curr_ema21 > curr_ema50 * 1.002:
            return None

        touched_zone = (
            curr_high >= curr_ema21 * 0.996
            or float(highs[-2]) >= float(ema21[-2]) * 0.996
        )
        rejected_ema21 = curr_close <= curr_ema21 * 1.0005 and curr_close < curr_open
        flow_ok = (tfi_5m <= -0.12 or tfi_15m <= -0.10 or ofi_z <= -0.40)
        oi_ok = oi_quadrant != "Q2_SHORT_COVERING"

        if not (touched_zone and rejected_ema21 and flow_ok and oi_ok):
            return None

        swing_high = float(np.max(highs[-4:]))
        raw_sl = swing_high + 0.35 * curr_atr
        prior_swing_low = float(np.min(lows[-16:]))
        raw_tp2 = min(prior_swing_low, curr_close - 2.2 * abs(raw_sl - curr_close))

        tags = ["TREND_BEAR_ANCHOR", "EMA21_PULLBACK_REJECT"]
        if bear_fvg:
            tags.append("BEARISH_FVG_RESISTANCE")
        if oi_quadrant == "Q3_NEW_SHORTS":
            tags.append("OI_Q3_NEW_SHORTS")
        if tfi_5m <= -0.15:
            tags.append("NEGATIVE_TFI_REVERSAL")

        return build_sniper_candidate(
            strategy_id=STRATEGY_ID,
            direction="SHORT",
            entry_price=curr_close,
            raw_sl_price=raw_sl,
            raw_tp2_price=raw_tp2,
            vertical_barrier_bars=16,
            structural_anchor_desc=f"Bearish pullback to EMA21 ({curr_ema21:.4f}) & swing high {swing_high:.4f} with TFI={tfi_5m:+.2f}",
            confluence_tags=tags,
            entry_type="MAKER_FIRST_GTX",
            min_sl_pct=0.50,
            max_sl_pct=1.65,
            min_tp2_r=1.80,
            regime=regime,
            symbol=symbol,
        )

    return None


generate_signal = evaluate
