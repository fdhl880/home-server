"""
PYROFUEL BOT - TRIPLE-BARRIER STRATEGY BASE & SNIPER SCHEMA (Task T4.2 / T7.4)
Mendefinisikan skema standar `SetupCandidate` (dataclass + dict-compatible),
fungsi perhitungan indikator bebas-lookahead (closed-bar only), serta
pembentuk kotak Triple-Barrier dengan mode `HIGH_PRECISION_SNIPER_MODE`
(clamping 0.45% <= d_SL <= 1.80%, TP1 = +0.55R, SL Lock = +0.38R, TP2 >= +1.60R).
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np


@dataclass
class SetupCandidate:
    strategy_id: str
    direction: str  # "LONG" | "SHORT"
    entry_type: str  # "MAKER_FIRST_GTX" | "IMMEDIATE_IOC"
    entry_price: float
    sl_price: float
    tp1_price: float
    tp2_price: float
    sl_distance_pct: float  # percentage e.g. 0.65 means 0.65%
    rrr_gross: float
    rrr_net: float
    vertical_barrier_bars: int
    structural_anchor_desc: str
    confluence_tags: List[str] = field(default_factory=list)
    regime: str = "UNKNOWN"
    symbol: str = ""
    tp1_r: float = 0.55
    sl_lock_after_tp1_r: float = 0.38
    tp2_r: float = 1.80
    sniper_mode: bool = True
    bandit_score: float = 0.0
    bandit_theta: float = 0.5

    @property
    def tp_price(self) -> float:
        """Alias for primary runner target TP2."""
        return self.tp2_price

    @property
    def structural_Anchor_desc(self) -> str:
        """Case-insensitive alias matching blueprint field name."""
        return self.structural_anchor_desc

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tp_price"] = self.tp2_price
        d["structural_Anchor_desc"] = self.structural_anchor_desc
        return d

    # Dict-protocol compatibility so callers can use either `cand.entry_price` or `cand["entry_price"]`
    def __getitem__(self, key: str) -> Any:
        if key == "tp_price":
            return self.tp2_price
        if key == "structural_Anchor_desc":
            return self.structural_anchor_desc
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "tp_price":
            self.tp2_price = float(value)
        elif key == "structural_Anchor_desc":
            self.structural_anchor_desc = str(value)
        else:
            setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except AttributeError:
            return default

    def __contains__(self, key: str) -> bool:
        if key in ("tp_price", "structural_Anchor_desc"):
            return True
        return hasattr(self, key)

    def keys(self):
        return self.to_dict().keys()

    def items(self):
        return self.to_dict().items()

    def values(self):
        return self.to_dict().values()


def extract_arrays(klines: Sequence[Any]) -> Dict[str, np.ndarray]:
    """
    Extract numpy arrays for open, high, low, close, volume, taker_buy_vol from closed klines.
    Strictly operates on the provided sequence without mutating it.
    """
    if not klines:
        empty = np.array([], dtype=np.float64)
        return {
            "open": empty, "high": empty, "low": empty,
            "close": empty, "volume": empty, "taker_buy": empty,
        }

    first = klines[0]
    if isinstance(first, dict):
        opens = np.array([float(k.get("open", k.get("close", 0.0))) for k in klines], dtype=np.float64)
        highs = np.array([float(k.get("high", k.get("close", 0.0))) for k in klines], dtype=np.float64)
        lows = np.array([float(k.get("low", k.get("close", 0.0))) for k in klines], dtype=np.float64)
        closes = np.array([float(k.get("close", 0.0)) for k in klines], dtype=np.float64)
        vols = np.array([float(k.get("volume", 0.0)) for k in klines], dtype=np.float64)
        has_tb = "taker_buy_base" in first or "taker_buy_quote" in first
        if has_tb:
            tb = np.array([
                float(k.get("taker_buy_base", k.get("taker_buy_quote", 0.0)) or 0.0)
                for k in klines
            ], dtype=np.float64)
        else:
            # Close-Location-Value derived taker buy proxy when CSV lacks column 9/10
            rng = np.maximum(highs - lows, 1e-12)
            buy_ratio = np.clip((closes - lows) / rng, 0.05, 0.95)
            tb = vols * buy_ratio
    else:
        opens = np.array([float(k[1]) for k in klines], dtype=np.float64)
        highs = np.array([float(k[2]) for k in klines], dtype=np.float64)
        lows = np.array([float(k[3]) for k in klines], dtype=np.float64)
        closes = np.array([float(k[4]) for k in klines], dtype=np.float64)
        vols = np.array([float(k[5]) if len(k) > 5 else 0.0 for k in klines], dtype=np.float64)
        if len(first) > 9:
            tb = np.array([float(k[9]) for k in klines], dtype=np.float64)
        else:
            rng = np.maximum(highs - lows, 1e-12)
            buy_ratio = np.clip((closes - lows) / rng, 0.05, 0.95)
            tb = vols * buy_ratio

    return {
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": vols,
        "taker_buy": tb,
    }


def compute_ema(series: np.ndarray, period: int) -> np.ndarray:
    n = len(series)
    if n == 0:
        return np.array([], dtype=np.float64)
    out = np.zeros(n, dtype=np.float64)
    k = 2.0 / (period + 1.0)
    out[0] = series[0]
    for i in range(1, n):
        out[i] = series[i] * k + out[i - 1] * (1.0 - k)
    return out


def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(closes)
    if n == 0:
        return np.array([], dtype=np.float64)
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = max(highs[0] - lows[0], 1e-12)
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    atr = np.zeros(n, dtype=np.float64)
    p = min(period, n)
    atr[:p] = np.mean(tr[:p])
    for i in range(p, n):
        atr[i] = (atr[i - 1] * (p - 1) + tr[i]) / p
    return atr


def infer_micro_state(
    arr: Dict[str, np.ndarray],
    micro_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge explicit live `micro_state` with closed-bar derived order-flow & CVD proxies
    so strategies work identically in live streaming and historical walk-forward backtests.
    """
    ms = dict(micro_state or {})
    closes = arr["close"]
    opens = arr["open"]
    highs = arr["high"]
    lows = arr["low"]
    vols = arr["volume"]
    tb = arr["taker_buy"]
    n = len(closes)
    if n < 5:
        return ms

    signed_vol = 2.0 * tb - vols
    recent_vol_3 = float(np.sum(vols[-3:]))
    tfi_calc = float(np.sum(signed_vol[-3:]) / max(recent_vol_3, 1e-12))
    tfi_15m_calc = float(signed_vol[-1] / max(vols[-1], 1e-12))

    # CVD & Price slope divergence over last 10 bars (closed-form OLS slope)
    win = min(10, n)
    cvd = np.cumsum(signed_vol[-win:])
    px_win = closes[-win:]
    if win >= 3:
        x_idx = np.arange(win, dtype=np.float64) - 0.5 * (win - 1)
        x_var = float(np.dot(x_idx, x_idx))
        px_slope = float(np.dot(x_idx, px_win - np.mean(px_win)) / x_var)
        cvd_slope = float(np.dot(x_idx, cvd - np.mean(cvd)) / x_var)
    else:
        px_slope = 0.0
        cvd_slope = 0.0

    # Bullish absorption: price flat/down over window or sweeping low, while recent signed delta is positive
    bull_abs = bool(
        (px_slope <= 0 and cvd_slope > 0)
        or (closes[-1] > opens[-1] and ( min(opens[-1], closes[-1]) - lows[-1] ) > 0.45 * max(highs[-1] - lows[-1], 1e-12) and tfi_15m_calc > 0.05)
    )
    bear_abs = bool(
        (px_slope >= 0 and cvd_slope < 0)
        or (closes[-1] < opens[-1] and ( highs[-1] - max(opens[-1], closes[-1]) ) > 0.45 * max(highs[-1] - lows[-1], 1e-12) and tfi_15m_calc < -0.05)
    )

    # Volume Z-score
    v_look = vols[-min(24, n):]
    v_mean = float(np.mean(v_look[:-1])) if len(v_look) > 2 else float(np.mean(v_look))
    v_std = float(np.std(v_look[:-1])) if len(v_look) > 2 else 1.0
    vol_z = (float(vols[-1]) - v_mean) / max(v_std, 1e-9)

    # Default OI quadrant inference if not provided by live REST/WS
    dp_4 = (closes[-1] - closes[-min(4, n)]) / max(closes[-min(4, n)], 1e-12) * 100.0
    if "oi_quadrant" not in ms or not ms["oi_quadrant"]:
        if dp_4 > 0 and tfi_calc > 0.08 and vols[-1] > 1.15 * v_mean:
            ms["oi_quadrant"] = "Q1_NEW_LONGS"
            ms.setdefault("delta_oi_pct", 1.1)
        elif dp_4 < 0 and tfi_calc < -0.08 and vols[-1] > 1.15 * v_mean:
            ms["oi_quadrant"] = "Q3_NEW_SHORTS"
            ms.setdefault("delta_oi_pct", 1.1)
        elif dp_4 < -0.8 and bull_abs:
            ms["oi_quadrant"] = "Q4_LONG_LIQ_FLUSH"
            ms.setdefault("delta_oi_pct", -1.6)
        else:
            ms["oi_quadrant"] = "Q2_SHORT_COVERING" if dp_4 > 0 else "NEUTRAL"
            ms.setdefault("delta_oi_pct", 0.2)

    ms.setdefault("tfi_5m", round(tfi_15m_calc, 4))
    ms.setdefault("tfi_15m", round(tfi_calc, 4))
    ms.setdefault("ofi_z", round(tfi_15m_calc * 3.0, 3))
    ms.setdefault("obi_20", round(float(np.clip(tfi_15m_calc * 1.2, -0.95, 0.95)), 4))
    ms.setdefault("bullish_absorption", bull_abs)
    ms.setdefault("bearish_absorption", bear_abs)
    ms.setdefault("vol_zscore", round(vol_z, 3))
    ms.setdefault("liq_zscore", round(max(0.0, vol_z * 1.25) if (bull_abs or bear_abs) else 0.0, 3))
    ms.setdefault("funding_zscore", 0.0)
    return ms


def build_sniper_candidate(
    strategy_id: str,
    direction: str,
    entry_price: float,
    raw_sl_price: float,
    raw_tp2_price: float,
    vertical_barrier_bars: int,
    structural_anchor_desc: str,
    confluence_tags: List[str],
    entry_type: str = "MAKER_FIRST_GTX",
    min_sl_pct: float = 0.45,
    max_sl_pct: float = 1.80,
    min_tp2_r: float = 1.65,
    tp1_r: float = 0.55,
    sl_lock_r: float = 0.38,
    regime: str = "UNKNOWN",
    symbol: str = "",
) -> SetupCandidate:
    """
    Construct a validated `SetupCandidate` enforcing:
    1. Sniper SL clamping: `min_sl_pct <= d_SL <= max_sl_pct` (default 0.45% .. 1.80%),
       protecting 20x Isolated liquidation (liq distance ~4.6% >= 2.5x SL).
    2. Two-Stage Asymmetric Profit Lock:
       - `tp1_price` at `+0.55R` (locks SL to `+0.38R` upon touch)
       - `tp2_price` at `>= +1.65R` (ensuring net RRR >= 1.60 after fees)
    """
    direction = direction.upper()
    entry_px = float(entry_price)
    raw_dist_pct = abs(entry_px - float(raw_sl_price)) / max(entry_px, 1e-12) * 100.0
    clamped_sl_pct = float(np.clip(raw_dist_pct, min_sl_pct, max_sl_pct))
    sl_frac = clamped_sl_pct / 100.0

    # Round-trip fee + slippage fraction (Maker GTX entry 0.02% + Taker exit 0.05% + 0.01% slip = 0.08%)
    rt_cost_frac = 0.0008 if entry_type == "MAKER_FIRST_GTX" else 0.0012

    # Ensure TP2 satisfies both min_tp2_r and net RRR >= 1.60
    raw_tp2_dist_pct = abs(float(raw_tp2_price) - entry_px) / max(entry_px, 1e-12) * 100.0
    raw_r_gross = raw_tp2_dist_pct / max(clamped_sl_pct, 1e-9)

    required_tp2_frac = max(
        min_tp2_r * sl_frac,
        1.62 * (sl_frac + rt_cost_frac) + rt_cost_frac,
    )
    tp2_frac = max(raw_r_gross * sl_frac, required_tp2_frac)
    tp1_frac = tp1_r * sl_frac

    if direction == "LONG":
        sl_px = entry_px * (1.0 - sl_frac)
        tp1_px = entry_px * (1.0 + tp1_frac)
        tp2_px = entry_px * (1.0 + tp2_frac)
    else:
        sl_px = entry_px * (1.0 + sl_frac)
        tp1_px = entry_px * (1.0 - tp1_frac)
        tp2_px = entry_px * (1.0 - tp2_frac)

    rrr_gross = tp2_frac / max(sl_frac, 1e-12)
    rrr_net = (tp2_frac - rt_cost_frac) / max(sl_frac + rt_cost_frac, 1e-12)

    return SetupCandidate(
        strategy_id=strategy_id,
        direction=direction,
        entry_type=entry_type,
        entry_price=round(entry_px, 8),
        sl_price=round(sl_px, 8),
        tp1_price=round(tp1_px, 8),
        tp2_price=round(tp2_px, 8),
        sl_distance_pct=round(clamped_sl_pct, 4),
        rrr_gross=round(rrr_gross, 3),
        rrr_net=round(rrr_net, 3),
        vertical_barrier_bars=int(vertical_barrier_bars),
        structural_anchor_desc=structural_anchor_desc,
        confluence_tags=list(confluence_tags),
        regime=regime,
        symbol=symbol,
        tp1_r=tp1_r,
        sl_lock_after_tp1_r=sl_lock_r,
        tp2_r=round(rrr_gross, 3),
        sniper_mode=True,
    )
