"""
PYROFUEL BOT - STRATEGY S2: OI + VOLATILITY SQUEEZE BREAKOUT (Task T4.2)
Menangkap transisi kompresi volatilitas (Bollinger Bandwidth squeeze) menuju impuls tren baru
yang dikonfirmasi oleh penutupan bar di luar kotak struktur, lonjakan volume >= 1.8x-2.0x SMA20,
serta Kuadran Open Interest `Q1_NEW_LONGS` (Long) atau `Q3_NEW_SHORTS` (Short).
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

STRATEGY_ID = "S2_OI_VOL_BREAKOUT"
ALLOWED_REGIMES = {"TREND_BULL", "TREND_BEAR", "MEAN_REVERT"}


def _bollinger_bw_percentile(closes: np.ndarray, window: int = 20, lookback: int = 80) -> float:
    n = len(closes)
    if n < window + 5:
        return 20.0
    bws = []
    start = max(window, n - lookback)
    for idx in range(start, n):
        sl = closes[idx - window:idx]
        mean_v = float(np.mean(sl))
        std_v = float(np.std(sl))
        bw = (4.0 * std_v) / max(mean_v, 1e-12)
        bws.append(bw)
    if len(bws) < 3:
        return 20.0
    # Evaluate prior bar squeeze (before the breakout bar itself)
    prior_bw = bws[-2] if len(bws) >= 2 else bws[-1]
    arr_bw = np.asarray(bws[:-1] if len(bws) > 2 else bws, dtype=np.float64)
    pct = float(np.sum(arr_bw <= prior_bw)) / len(arr_bw) * 100.0
    return pct


def evaluate(
    klines: Sequence[Any],
    regime_state: Dict[str, Any],
    micro_state: Optional[Dict[str, Any]] = None,
    symbol: str = "",
) -> Optional[SetupCandidate]:
    """
    Evaluate S2_OI_VOL_BREAKOUT on closed klines (strictly no-lookahead).
    """
    regime = str((regime_state or {}).get("regime", "UNKNOWN"))
    if regime not in ALLOWED_REGIMES:
        return None

    arr = extract_arrays(klines)
    closes = arr["close"]
    opens = arr["open"]
    highs = arr["high"]
    lows = arr["low"]
    vols = arr["volume"]
    n = len(closes)
    if n < 25:
        return None

    atr14 = compute_atr(highs, lows, closes, 14)
    curr_close = float(closes[-1])
    curr_open = float(opens[-1])
    curr_vol = float(vols[-1])
    curr_atr = float(atr14[-1])
    if curr_close <= 0 or curr_atr <= 0:
        return None

    box_window = min(14, n - 2)
    box_high = float(np.max(highs[-(box_window + 1):-1]))
    box_low = float(np.min(lows[-(box_window + 1):-1]))
    box_mid = 0.5 * (box_high + box_low)
    box_width_pct = (box_high - box_low) / max(box_mid, 1e-12) * 100.0

    bw_pct = _bollinger_bw_percentile(closes, window=20, lookback=80)
    is_squeeze = (bw_pct <= 35.0) or (box_width_pct <= 3.2)

    vol_sma20 = float(np.mean(vols[-21:-1])) if n >= 21 else float(np.mean(vols[:-1]))
    vol_ratio = curr_vol / max(vol_sma20, 1e-12)

    ms = infer_micro_state(arr, micro_state)
    oi_quadrant = str(ms.get("oi_quadrant", "NEUTRAL"))
    delta_oi_pct = float(ms.get("delta_oi_pct", 0.0) or 0.0)
    ofi_z = float(ms.get("ofi_z", 0.0) or 0.0)
    obi_20 = float(ms.get("obi_20", 0.0) or 0.0)

    if not is_squeeze or vol_ratio < 1.80:
        return None

    # Bullish Breakout
    if (
        curr_close > box_high
        and curr_close > curr_open
        and oi_quadrant == "Q1_NEW_LONGS"
        and delta_oi_pct >= 0.80
        and (ofi_z >= 0.0 or obi_20 >= 0.0)
    ):
        raw_sl = max(box_mid, curr_close - 1.2 * curr_atr)
        sl_dist = abs(curr_close - raw_sl)
        raw_tp2 = curr_close + 2.5 * max(sl_dist, curr_close * 0.006)
        tags: List[str] = [
            "VOL_SQUEEZE_BREAKOUT",
            "OI_Q1_NEW_LONGS",
            f"VOL_SPIKE_{vol_ratio:.1f}X",
        ]
        return build_sniper_candidate(
            strategy_id=STRATEGY_ID,
            direction="LONG",
            entry_price=curr_close,
            raw_sl_price=raw_sl,
            raw_tp2_price=raw_tp2,
            vertical_barrier_bars=16,
            structural_anchor_desc=f"Bullish squeeze breakout above box {box_high:.4f} (Vol {vol_ratio:.1f}x, OI +{delta_oi_pct:.2f}%)",
            confluence_tags=tags,
            entry_type="IMMEDIATE_IOC",
            min_sl_pct=0.50,
            max_sl_pct=1.80,
            min_tp2_r=2.20,
            regime=regime,
            symbol=symbol,
        )

    # Bearish Breakdown
    if (
        curr_close < box_low
        and curr_close < curr_open
        and oi_quadrant == "Q3_NEW_SHORTS"
        and delta_oi_pct >= 0.80
        and (ofi_z <= 0.0 or obi_20 <= 0.0)
    ):
        raw_sl = min(box_mid, curr_close + 1.2 * curr_atr)
        sl_dist = abs(raw_sl - curr_close)
        raw_tp2 = curr_close - 2.5 * max(sl_dist, curr_close * 0.006)
        tags = [
            "VOL_SQUEEZE_BREAKDOWN",
            "OI_Q3_NEW_SHORTS",
            f"VOL_SPIKE_{vol_ratio:.1f}X",
        ]
        return build_sniper_candidate(
            strategy_id=STRATEGY_ID,
            direction="SHORT",
            entry_price=curr_close,
            raw_sl_price=raw_sl,
            raw_tp2_price=raw_tp2,
            vertical_barrier_bars=16,
            structural_anchor_desc=f"Bearish squeeze breakdown below box {box_low:.4f} (Vol {vol_ratio:.1f}x, OI +{delta_oi_pct:.2f}%)",
            confluence_tags=tags,
            entry_type="IMMEDIATE_IOC",
            min_sl_pct=0.50,
            max_sl_pct=1.80,
            min_tp2_r=2.20,
            regime=regime,
            symbol=symbol,
        )

    return None


generate_signal = evaluate
