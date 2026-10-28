"""
===========================================================================
PYROFUEL AVELLANEDA-STOIKOV OPTIMAL MICRO-ENTRY ROUTER v3.0 (T6.4)
===========================================================================
Implements:
1. Micro-Price (P_tilde_t) from Level-1 Bid/Ask Queue Imbalance:
     P_tilde_t = (Q_1^B * P_1^A + Q_1^A * P_1^B) / (Q_1^B + Q_1^A)
2. Avellaneda-Stoikov / Guéant-Lehalle Optimal Limit Offset (delta*):
     delta* = (1 / kappa) * ln(1 + kappa / gamma_risk)
              - mu_flow / (gamma_risk * sigma_1m^2)
   Places passive Limit GTX / QUEUE orders at P_entry* = P_tilde_t -/+ delta*
   when VPIN < 0.70, tightening SL distance by delta* and saving 0.03% taker fee
   (+0.6% ROE at 20x leverage).
3. Pre-Trade Order-Book Depth VWAP Impact Guard:
     Impact_bps = (|P_VWAP(Qty) - P_mid| / P_mid) * 10^4 <= 8.0 bps
   Aborts trade execution if order-book impact exceeds 8.0 bps (0.08%).
===========================================================================
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


class AvellanedaStoikovRouter:
    """
    Avellaneda-Stoikov / Guéant-Lehalle optimal micro-entry offset & VWAP depth impact router (T6.4).
    """

    def __init__(
        self,
        gamma_risk: float = 0.5,
        default_kappa: float = 1500.0,
        max_impact_bps: float = 8.0,
        vpin_maker_cutoff: float = 0.70,
        vpin_cdf_hard_cutoff: float = 0.90,
        min_offset_bps: float = 0.5,
        max_offset_bps: float = 15.0,
    ):
        self.gamma_risk = max(1e-4, float(gamma_risk))
        self.default_kappa = max(1.0, float(default_kappa))
        self.max_impact_bps = float(max_impact_bps)
        self.vpin_maker_cutoff = float(vpin_maker_cutoff)
        self.vpin_cdf_hard_cutoff = float(vpin_cdf_hard_cutoff)
        self.min_offset_bps = float(min_offset_bps)
        self.max_offset_bps = float(max_offset_bps)

    @staticmethod
    def compute_micro_price(
        best_bid_price: float,
        best_bid_qty: float,
        best_ask_price: float,
        best_ask_qty: float,
    ) -> Dict[str, float]:
        """
        Compute micro-price P_tilde_t and micro-price divergence.
        """
        pb = float(best_bid_price)
        qb = max(0.0, float(best_bid_qty))
        pa = float(best_ask_price)
        qa = max(0.0, float(best_ask_qty))
        mid = 0.5 * (pb + pa)
        spread = max(1e-12, pa - pb)

        denom = qb + qa
        if denom <= 1e-12:
            micro = mid
        else:
            micro = (qb * pa + qa * pb) / denom

        micro_div = (micro - mid) / spread
        return {
            "mid_price": mid,
            "micro_price": micro,
            "spread": spread,
            "spread_bps": (spread / max(1e-12, mid)) * 1e4,
            "micro_divergence": micro_div,
        }

    def compute_optimal_offset(
        self,
        direction: str,
        best_bid_price: float,
        best_bid_qty: float,
        best_ask_price: float,
        best_ask_qty: float,
        ofi_20: float = 0.0,
        tfi_1m: float = 0.0,
        sigma_1m: float = 0.0015,
        kappa: Optional[float] = None,
        vpin: float = 0.35,
        vpin_cdf: float = 0.50,
        tick_size: float = 0.01,
    ) -> Dict[str, Any]:
        """
        Compute Avellaneda-Stoikov / Guéant-Lehalle optimal micro-entry offset delta*
        and optimal passive limit price P_entry*.
        """
        dir_norm = str(direction).upper().strip()
        sign = 1.0 if dir_norm == "LONG" else -1.0

        mp = self.compute_micro_price(
            best_bid_price=best_bid_price,
            best_bid_qty=best_bid_qty,
            best_ask_price=best_ask_price,
            best_ask_qty=best_ask_qty,
        )
        p_tilde = mp["micro_price"]
        mid = mp["mid_price"]

        # Directional order-flow drift mu_flow (positive when flow supports our trade direction)
        mu_raw = 0.6 * float(ofi_20) + 0.4 * float(tfi_1m)
        mu_flow = sign * mu_raw

        # Adverse-selection toxicity check (T3.4 & T6.4)
        adverse_flow = mu_flow < -0.15
        if float(vpin_cdf) >= self.vpin_cdf_hard_cutoff and adverse_flow:
            return {
                "allowed_passive_maker": False,
                "block_reason": "ADVERSE_SELECTION_VPIN_CDF_BLOCK",
                "recommended_price_match": "NONE",
                "micro_price": p_tilde,
                "mid_price": mid,
                "delta_star_frac": 0.0,
                "delta_star_price": 0.0,
                "optimal_limit_price": float(best_bid_price if dir_norm == "LONG" else best_ask_price),
            }

        k_val = max(1.0, float(kappa) if kappa is not None else self.default_kappa)
        sig = max(1e-4, float(sigma_1m))
        gamma = self.gamma_risk

        # Avellaneda-Stoikov / Guéant-Lehalle formula:
        # delta* = (1 / kappa) * ln(1 + kappa / gamma) - mu_flow / (gamma * sigma^2)
        base_term = (1.0 / k_val) * math.log(1.0 + k_val / gamma)
        # Scale drift term to fractional price units
        drift_term = (mu_flow * 1e-6) / (gamma * (sig ** 2))
        delta_star_raw = base_term - drift_term

        min_frac = self.min_offset_bps * 1e-4
        max_frac = self.max_offset_bps * 1e-4
        delta_star_frac = float(max(min_frac, min(max_frac, delta_star_raw)))
        delta_star_px = p_tilde * delta_star_frac

        tick = max(1e-8, float(tick_size))
        if dir_norm == "LONG":
            # Place passive limit at min(best_bid, P_tilde - delta*)
            raw_limit = min(float(best_bid_price), p_tilde - delta_star_px)
            opt_limit = math.floor(raw_limit / tick + 1e-9) * tick
        else:
            # Place passive limit at max(best_ask, P_tilde + delta*)
            raw_limit = max(float(best_ask_price), p_tilde + delta_star_px)
            opt_limit = math.ceil(raw_limit / tick - 1e-9) * tick

        allow_maker = float(vpin) < self.vpin_maker_cutoff and float(vpin_cdf) < self.vpin_cdf_hard_cutoff
        ticks_deep = abs(opt_limit - (best_bid_price if dir_norm == "LONG" else best_ask_price)) / tick
        rec_price_match = "QUEUE_5" if ticks_deep >= 3.0 else "QUEUE"

        return {
            "allowed_passive_maker": allow_maker,
            "block_reason": None if allow_maker else "VPIN_HIGH_TOXICITY",
            "recommended_price_match": rec_price_match,
            "micro_price": p_tilde,
            "mid_price": mid,
            "mu_flow": mu_flow,
            "delta_star_raw": delta_star_raw,
            "delta_star_frac": delta_star_frac,
            "delta_star_bps": delta_star_frac * 1e4,
            "delta_star_price": delta_star_px,
            "optimal_limit_price": round(opt_limit, 8),
        }

    def compute_vwap_impact_bps(
        self,
        depth_book: Dict[str, Sequence[Sequence[float | str]]],
        direction: str,
        quantity: float,
    ) -> Dict[str, Any]:
        """
        Walk `@depth20` order book to compute VWAP fill price for `quantity` and verify:
          Impact_bps = (|P_VWAP(Qty) - P_mid| / P_mid) * 10^4 <= 8.0 bps
        """
        bids_raw = depth_book.get("bids", [])
        asks_raw = depth_book.get("asks", [])
        if not bids_raw or not asks_raw:
            return {
                "passed": False,
                "reason": "EMPTY_ORDER_BOOK",
                "impact_bps": 999.0,
                "vwap_price": 0.0,
                "mid_price": 0.0,
                "filled_ratio": 0.0,
            }

        best_bid = float(bids_raw[0][0])
        best_ask = float(asks_raw[0][0])
        mid_price = 0.5 * (best_bid + best_ask)
        if mid_price <= 0:
            return {
                "passed": False,
                "reason": "INVALID_MID_PRICE",
                "impact_bps": 999.0,
                "vwap_price": 0.0,
                "mid_price": 0.0,
                "filled_ratio": 0.0,
            }

        dir_norm = str(direction).upper().strip()
        levels = asks_raw if dir_norm in ("LONG", "BUY") else bids_raw

        target_qty = max(1e-12, float(quantity))
        rem_qty = target_qty
        cost_accum = 0.0
        qty_accum = 0.0

        for lvl in levels:
            px = float(lvl[0])
            avail = float(lvl[1])
            if avail <= 0:
                continue
            take = min(rem_qty, avail)
            cost_accum += take * px
            qty_accum += take
            rem_qty -= take
            if rem_qty <= 1e-12:
                break

        filled_ratio = qty_accum / target_qty
        if qty_accum <= 0 or filled_ratio < 0.999:
            return {
                "passed": False,
                "reason": f"INSUFFICIENT_BOOK_DEPTH (filled {filled_ratio * 100:.1f}%)",
                "impact_bps": 999.0,
                "vwap_price": cost_accum / max(1e-12, qty_accum),
                "mid_price": mid_price,
                "filled_ratio": filled_ratio,
            }

        vwap_price = cost_accum / qty_accum
        impact_bps = abs(vwap_price - mid_price) / mid_price * 1e4
        passed = impact_bps <= self.max_impact_bps + 1e-9

        return {
            "passed": passed,
            "reason": "OK" if passed else f"IMPACT_EXCEEDS_MAX ({impact_bps:.2f} > {self.max_impact_bps:.1f} bps)",
            "impact_bps": float(impact_bps),
            "vwap_price": float(vwap_price),
            "mid_price": float(mid_price),
            "filled_ratio": float(filled_ratio),
        }
