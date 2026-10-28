"""
PYROFUEL BOT - LOPEZ DE PRADO TRIPLE-BARRIER SIMULATOR (Task T1.3 & T7.4)
Mensimulasikan kotak Triple-Barrier [SL, TP1/TP2, T_max] tanpa lookahead dengan:
1. Resolusi intrabar konservatif (jika SL dan TP tersentuh pada bar yang sama -> SL menang dulu)
2. Mode Asimetris 2-Tahap (`HIGH_PRECISION_SNIPER_MODE`: TP1 = +0.55R mengunci SL di +0.38R + Runner TP2)
3. Pengecekan Harga Likuidasi 20x Isolated (MMR = 0.4%)
4. Biaya Transaksi Riil: Maker/Taker Fee + Dynamic Slippage + Pembayaran Funding Rate (8h/4h UTC)
"""
from typing import Any, Dict, List, Optional, Sequence, Union
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


def _counts_funding_boundary(open_time_ms: int, close_time_ms: int, interval_hours: int = 8) -> int:
    """Count how many funding timestamps (00:00, 08:00, 16:00 UTC or 4h) fall inside (open_time, close_time]."""
    if open_time_ms <= 0 or close_time_ms <= open_time_ms:
        return 0
    step_ms = max(1, int(interval_hours)) * 3600 * 1000
    first_boundary = ((open_time_ms // step_ms) + 1) * step_ms
    count = 0
    t = first_boundary
    while t <= close_time_ms:
        count += 1
        t += step_ms
    return count


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
) -> Dict[str, Any]:
    """
    Simulate a single trade over `future_candles` (which MUST start strictly at index t+1).
    Returns detailed execution outcome including `outcome`, `r_multiple_net`, `r_multiple_gross`,
    `net_return_pct`, `margin_pnl_pct`, `bars_held`, `exit_index_offset`, `mae_pct`, `mfe_pct`.
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
    liq_px = compute_liquidation_price(entry_px, direction, leverage=leverage, mmr=mmr)

    horizon = min(max(1, max_bars), len(future_candles))
    if horizon == 0:
        return {
            "outcome": "NO_FUTURE_DATA",
            "exit_price": entry_px,
            "r_multiple_gross": 0.0,
            "r_multiple_net": 0.0,
            "gross_return_pct": 0.0,
            "cost_pct": 0.0,
            "net_return_pct": 0.0,
            "margin_pnl_pct": 0.0,
            "bars_held": 0,
            "exit_index_offset": 0,
            "tp1_hit": False,
            "liquidated": False,
            "mae_pct": 0.0,
            "mfe_pct": 0.0,
        }

    tp1_hit = False
    active_sl = sl_px
    outcome = "TIME_BARRIER"
    exit_px = entry_px
    bars_held = horizon
    liquidated = False
    mae_pct = 0.0
    mfe_pct = 0.0
    funding_events = 0

    for idx in range(horizon):
        fc = future_candles[idx]
        hi = float(fc["high"])
        lo = float(fc["low"])
        cl = float(fc["close"])
        op = float(fc.get("open", cl))
        ot = int(fc.get("open_time", 0) or 0)
        ct = int(fc.get("close_time", ot + 3600_000 if ot > 0 else 0) or 0)
        funding_events += _counts_funding_boundary(ot, ct, interval_hours=funding_interval_hours)

        if direction == "LONG":
            adv = max(0.0, (entry_px - lo) / entry_px * 100.0)
            fav = max(0.0, (hi - entry_px) / entry_px * 100.0)
            mae_pct = max(mae_pct, adv)
            mfe_pct = max(mfe_pct, fav)

            # 1. Check Liquidation first if SL was somehow below liq_px
            if lo <= liq_px and liq_px >= active_sl:
                outcome = "LIQUIDATED"
                exit_px = liq_px
                bars_held = idx + 1
                liquidated = True
                break

            if not tp1_hit:
                # Conservative Intrabar SL-First rule: if lo <= active_sl, SL wins even if hi >= tp1/tp2
                if lo <= active_sl:
                    outcome = "SL"
                    exit_px = active_sl
                    bars_held = idx + 1
                    break

                if sniper_mode:
                    if hi >= tp2_px:
                        tp1_hit = True
                        outcome = "TP2"
                        exit_px = tp2_px
                        bars_held = idx + 1
                        break
                    elif hi >= tp1_px:
                        tp1_hit = True
                        active_sl = locked_sl_px
                        # If close dropped back below locked_sl_px within the same bar after hitting tp1
                        if cl <= active_sl and op > active_sl:
                            outcome = "TP1_LOCK_WIN"
                            exit_px = active_sl
                            bars_held = idx + 1
                            break
                else:
                    if hi >= tp2_px:
                        outcome = "TP"
                        exit_px = tp2_px
                        bars_held = idx + 1
                        break
            else:
                # Already hit TP1 on an earlier bar -> active_sl is locked at +0.38R
                # Conservative tie-break: check locked SL first
                if lo <= active_sl:
                    outcome = "TP1_LOCK_WIN"
                    exit_px = active_sl
                    bars_held = idx + 1
                    break
                elif hi >= tp2_px:
                    outcome = "TP2"
                    exit_px = tp2_px
                    bars_held = idx + 1
                    break

        else:  # SHORT
            adv = max(0.0, (hi - entry_px) / entry_px * 100.0)
            fav = max(0.0, (entry_px - lo) / entry_px * 100.0)
            mae_pct = max(mae_pct, adv)
            mfe_pct = max(mfe_pct, fav)

            if hi >= liq_px and liq_px <= active_sl:
                outcome = "LIQUIDATED"
                exit_px = liq_px
                bars_held = idx + 1
                liquidated = True
                break

            if not tp1_hit:
                if hi >= active_sl:
                    outcome = "SL"
                    exit_px = active_sl
                    bars_held = idx + 1
                    break

                if sniper_mode:
                    if lo <= tp2_px:
                        tp1_hit = True
                        outcome = "TP2"
                        exit_px = tp2_px
                        bars_held = idx + 1
                        break
                    elif lo <= tp1_px:
                        tp1_hit = True
                        active_sl = locked_sl_px
                        if cl >= active_sl and op < active_sl:
                            outcome = "TP1_LOCK_WIN"
                            exit_px = active_sl
                            bars_held = idx + 1
                            break
                else:
                    if lo <= tp2_px:
                        outcome = "TP"
                        exit_px = tp2_px
                        bars_held = idx + 1
                        break
            else:
                if hi >= active_sl:
                    outcome = "TP1_LOCK_WIN"
                    exit_px = active_sl
                    bars_held = idx + 1
                    break
                elif lo <= tp2_px:
                    outcome = "TP2"
                    exit_px = tp2_px
                    bars_held = idx + 1
                    break

    if outcome == "TIME_BARRIER":
        exit_px = float(future_candles[horizon - 1]["close"])

    # Compute gross return % and gross R-multiple
    if liquidated:
        gross_ret_pct = -(100.0 / max(1.0, float(leverage)))
        cost_pct = taker_fee_pct * 2.0 + base_slippage_pct * 2.0
        net_ret_pct = gross_ret_pct
        r_gross = -1.0 / max(sl_dist_pct * float(leverage) / 100.0, 0.01)
        r_net = r_gross
        margin_pnl_pct = -100.0
    else:
        runner_ret_pct = (
            ((exit_px - entry_px) / entry_px * 100.0)
            if direction == "LONG"
            else ((entry_px - exit_px) / entry_px * 100.0)
        )
        tp1_ret_pct = tp1_r * sl_dist_pct

        if sniper_mode and tp1_hit:
            # Blended return: 65% partial locked at TP1 (+0.55R) + 35% runner at exit_px
            w1 = float(np.clip(tp1_partial_weight, 0.0, 1.0))
            gross_ret_pct = w1 * tp1_ret_pct + (1.0 - w1) * runner_ret_pct
        else:
            gross_ret_pct = runner_ret_pct

        entry_fee = maker_fee_pct if entry_type == "MAKER_FIRST_GTX" else taker_fee_pct
        exit_fee = maker_fee_pct if outcome in ("TP", "TP2") else taker_fee_pct
        slip_pct = base_slippage_pct * (0.5 if entry_type == "MAKER_FIRST_GTX" else 1.0)
        funding_cost_pct = funding_events * float(funding_rate_pct)

        cost_pct = entry_fee + exit_fee + slip_pct + funding_cost_pct
        net_ret_pct = gross_ret_pct - cost_pct

        r_gross = gross_ret_pct / max(sl_dist_pct, 1e-9)
        r_net = net_ret_pct / max(sl_dist_pct, 1e-9)
        margin_pnl_pct = net_ret_pct * float(leverage)

    return {
        "outcome": outcome,
        "exit_price": round(exit_px, 8),
        "r_multiple_gross": round(float(r_gross), 4),
        "r_multiple_net": round(float(r_net), 4),
        "gross_return_pct": round(float(gross_ret_pct), 4),
        "cost_pct": round(float(cost_pct), 4),
        "net_return_pct": round(float(net_ret_pct), 4),
        "margin_pnl_pct": round(float(margin_pnl_pct), 3),
        "bars_held": int(bars_held),
        "exit_index_offset": int(bars_held),
        "tp1_hit": bool(tp1_hit),
        "liquidated": bool(liquidated),
        "mae_pct": round(float(mae_pct), 4),
        "mfe_pct": round(float(mfe_pct), 4),
    }
