"""
===========================================================================
PYROFUEL INTRABAR OPTIMAL STOPPING & THESIS INVALIDATION ENGINE v3.0 (T6.3)
===========================================================================
Continuously evaluates open positions every 5 seconds to scratch failing trades
around ~ -0.25R instead of waiting for full -1.0R Stop-Loss hits:
1. Order-Flow Drift (mu_t):
     mu_raw = c_1 * OFI_20 + c_2 * TFI_5m + c_3 * D_SP
     mu_t   = sign(direction) * mu_raw
2. Continuous First-Passage Survival Probability P_survive(t) of hitting TP
   before SL for drifted Brownian motion X_t in (SL, TP):
     - If |mu_t| < 1e-6:
         P_survive(t) = (X_t - SL) / (TP - SL)   (directional distance ratio)
     - If |mu_t| >= 1e-6:
         P_survive(t) = (1 - exp(-2 * mu_t * x / sigma_t^2))
                        / (1 - exp(-2 * mu_t * L / sigma_t^2))
       where x = |X_t - SL| is favorable distance from SL and L = |TP - SL|.
3. Early Thesis Invalidation Trigger (100% AI-Only Compliant):
   - Position open >= 180s (3 minutes) and has NOT reached +1.0R
   - P_survive(t) < 0.18 for 3 consecutive readings (15 seconds)
   - Hard microstructure reversal confirmed (e.g., for LONG: Spot-Perp CVD
     divergence <= -1.5, or VPIN sell >= 0.88, or OI quadrant == Q3_NEW_SHORTS)
   -> Emits `CRITICAL_POSITION_INTERRUPT` on `PriorityEventBus` and invokes
      `ai/decide.py` in `INTRABAR_EMERGENCY_REVIEW` mode.
   -> If AI returns `action == "ABORT_THESIS_SCRATCH"`, exits immediately with
      `close_reason = "AI_THESIS_INVALIDATED_EARLY"`.
===========================================================================
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from exec.event_bus import EventPriority, PriorityEventBus


class IntrabarThesisMonitor:
    """
    Intrabar First-Passage Survival Probability & Real-Time Thesis Invalidation Engine (T6.3).
    """

    def __init__(
        self,
        survival_threshold: float = 0.18,
        required_consecutive_breaches: int = 3,
        min_elapsed_sec: float = 180.0,
        c1_ofi: float = 0.40,
        c2_tfi: float = 0.35,
        c3_dsp: float = 0.25,
        event_bus: Optional[PriorityEventBus] = None,
    ):
        self.survival_threshold = float(survival_threshold)
        self.required_consecutive_breaches = max(1, int(required_consecutive_breaches))
        self.min_elapsed_sec = float(min_elapsed_sec)
        self.c1_ofi = float(c1_ofi)
        self.c2_tfi = float(c2_tfi)
        self.c3_dsp = float(c3_dsp)
        self.event_bus = event_bus

        # Per-symbol consecutive breach counter
        self._breach_counts: Dict[str, int] = {}

    def compute_orderflow_drift(
        self,
        direction: str,
        ofi_20: float,
        tfi_5m: float,
        spot_perp_div: float,
    ) -> float:
        """
        Compute directional order-flow drift mu_t:
          mu_t = sign(direction) * (c1 * OFI_20 + c2 * TFI_5m + c3 * D_SP)
        Positive mu_t means drift toward TP; negative mu_t means drift toward SL.
        """
        sign = 1.0 if str(direction).upper().strip() == "LONG" else -1.0
        mu_raw = (
            self.c1_ofi * float(ofi_20)
            + self.c2_tfi * float(tfi_5m)
            + self.c3_dsp * float(spot_perp_div)
        )
        return sign * mu_raw

    @staticmethod
    def compute_first_passage_survival_prob(
        current_price: float,
        sl_price: float,
        tp_price: float,
        direction: str = "LONG",
        mu_drift: float = 0.0,
        sigma: float = 0.25,
    ) -> float:
        """
        Compute First-Passage Probability P_survive(t) of hitting TP before SL
        starting from current_price X_t in (SL, TP).
        """
        dir_norm = str(direction).upper().strip()
        x_t = float(current_price)
        sl = float(sl_price)
        tp = float(tp_price)

        if dir_norm == "LONG":
            L = tp - sl
            x = x_t - sl
        else:
            L = sl - tp
            x = sl - x_t

        if L <= 1e-12:
            return 0.0
        if x <= 0.0:
            return 0.0
        if x >= L:
            return 1.0

        # Normalize x and L to unit barrier [0, 1] so drift/volatility scaling is invariant to asset price level
        u = x / L  # in (0, 1)
        mu = float(mu_drift)
        sig = max(1e-4, float(sigma))

        if abs(mu) < 1e-6:
            return float(max(0.0, min(1.0, u)))

        # Peclet / drift-diffusion exponent alpha = 2 * mu / sigma^2 on normalized barrier [0, 1]
        alpha = max(-40.0, min(40.0, (2.0 * mu) / (sig * sig)))
        if abs(alpha) < 1e-6:
            return float(max(0.0, min(1.0, u)))

        num = 1.0 - math.exp(-alpha * u)
        den = 1.0 - math.exp(-alpha * 1.0)
        if abs(den) < 1e-12:
            return float(max(0.0, min(1.0, u)))

        p_surv = num / den
        return float(max(0.0, min(1.0, p_surv)))

    @staticmethod
    def check_structural_reversal(
        direction: str, micro_state: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if hard microstructure reversal conditions hold against the open position.
        For LONG:
          - Spot-Perp CVD divergence <= -1.5, OR
          - VPIN toxic sell >= 0.88, OR
          - OI quadrant == "Q3_NEW_SHORTS"
        For SHORT:
          - Spot-Perp CVD divergence >= +1.5, OR
          - VPIN toxic buy >= 0.88, OR
          - OI quadrant == "Q1_NEW_LONGS"
        """
        dir_norm = str(direction).upper().strip()
        dsp = float(micro_state.get("spot_perp_div", 0.0))
        vpin = float(micro_state.get("vpin", 0.0))
        tfi_5m = float(micro_state.get("tfi_5m", 0.0))
        oi_quad = str(micro_state.get("oi_quadrant", "")).upper().strip()

        reasons = []
        if dir_norm == "LONG":
            if dsp <= -1.5:
                reasons.append(f"SPOT_PERP_DIV_BEARISH({dsp:.2f})")
            if vpin >= 0.88 and tfi_5m < 0:
                reasons.append(f"VPIN_SELL_TOXIC({vpin:.2f})")
            if oi_quad == "Q3_NEW_SHORTS":
                reasons.append("OI_QUAD_Q3_NEW_SHORTS")
        else:
            if dsp >= 1.5:
                reasons.append(f"SPOT_PERP_DIV_BULLISH({dsp:.2f})")
            if vpin >= 0.88 and tfi_5m > 0:
                reasons.append(f"VPIN_BUY_TOXIC({vpin:.2f})")
            if oi_quad == "Q1_NEW_LONGS":
                reasons.append("OI_QUAD_Q1_NEW_LONGS")

        is_reversed = len(reasons) >= 1
        return is_reversed, {
            "is_reversed": is_reversed,
            "reversal_triggers": reasons,
            "spot_perp_div": dsp,
            "vpin": vpin,
            "tfi_5m": tfi_5m,
            "oi_quadrant": oi_quad,
        }

    def evaluate_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        current_price: float,
        sl_price: float,
        tp_price: float,
        elapsed_sec: float,
        micro_state: Dict[str, Any],
        sigma: float = 0.35,
        max_r_reached: float = 0.0,
        decide_engine: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a live open position on a 5-second tick:
        Computes P_survive(t), updates consecutive breach count, and triggers
        `INTRABAR_EMERGENCY_REVIEW` when all invalidation conditions are met.
        """
        sym = str(symbol).upper().strip()
        dir_norm = str(direction).upper().strip()

        risk_dist = max(1e-8, abs(float(entry_price) - float(sl_price)))
        signed_move = (
            (float(current_price) - float(entry_price))
            if dir_norm == "LONG"
            else (float(entry_price) - float(current_price))
        )
        current_r = signed_move / risk_dist
        peak_r = max(float(max_r_reached), current_r)

        mu_t = self.compute_orderflow_drift(
            direction=dir_norm,
            ofi_20=float(micro_state.get("ofi_20", 0.0)),
            tfi_5m=float(micro_state.get("tfi_5m", 0.0)),
            spot_perp_div=float(micro_state.get("spot_perp_div", 0.0)),
        )
        p_survive = self.compute_first_passage_survival_prob(
            current_price=current_price,
            sl_price=sl_price,
            tp_price=tp_price,
            direction=dir_norm,
            mu_drift=mu_t,
            sigma=sigma,
        )

        # Update consecutive low-survival counter
        if p_survive < self.survival_threshold:
            self._breach_counts[sym] = self._breach_counts.get(sym, 0) + 1
        else:
            self._breach_counts[sym] = 0

        consec = self._breach_counts[sym]
        is_reversed, rev_details = self.check_structural_reversal(dir_norm, micro_state)

        eligible_time_and_r = (float(elapsed_sec) >= self.min_elapsed_sec) and (peak_r < 1.0)
        trigger_emergency = (
            eligible_time_and_r
            and (consec >= self.required_consecutive_breaches)
            and is_reversed
        )

        result: Dict[str, Any] = {
            "symbol": sym,
            "direction": dir_norm,
            "current_r": current_r,
            "mu_drift": mu_t,
            "p_survive": p_survive,
            "consecutive_breaches": consec,
            "structural_reversal": is_reversed,
            "reversal_details": rev_details,
            "trigger_emergency_review": trigger_emergency,
            "should_scratch": False,
            "close_reason": None,
            "ai_review": None,
        }

        if not trigger_emergency:
            return result

        # Publish high-priority interrupt to PriorityEventBus (< 50ms wake-up)
        if self.event_bus is not None:
            self.event_bus.publish(
                "CRITICAL_POSITION_INTERRUPT",
                payload={
                    "reason": "THESIS_INVALIDATION_CANDIDATE",
                    "symbol": sym,
                    "direction": dir_norm,
                    "p_survive": p_survive,
                    "current_r": current_r,
                },
                priority=int(EventPriority.CRITICAL_POSITION_INTERRUPT),
            )

        # Consult AI in INTRABAR_EMERGENCY_REVIEW mode (strictly obeying AI-Only mandate)
        if decide_engine is not None and hasattr(decide_engine, "review_open_position_emergency"):
            ai_rev = decide_engine.review_open_position_emergency(
                symbol=sym,
                direction=dir_norm,
                entry_price=entry_price,
                current_price=current_price,
                sl_price=sl_price,
                tp_price=tp_price,
                p_survive=p_survive,
                reversal_signals=rev_details,
                elapsed_sec=elapsed_sec,
            )
            result["ai_review"] = ai_rev
            if ai_rev.get("action") == "ABORT_THESIS_SCRATCH":
                result["should_scratch"] = True
                result["close_reason"] = "AI_THESIS_INVALIDATED_EARLY"

        return result

    def reset_symbol(self, symbol: str) -> None:
        self._breach_counts.pop(str(symbol).upper().strip(), None)
