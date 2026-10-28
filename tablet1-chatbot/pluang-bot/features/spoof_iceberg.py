"""
Pilar 20 (T3.11) — Anti-Spoofing Order Book Persistence Filter & Hidden Iceberg Replenishment Detector.

Formulas (Section 12.1):
  1. Order Persistence Weighting:
         w_{k, t}^{clean} = exp(-lambda * (k - 1)) * (1 - exp(-tau_{k, t} / tau_0)),  tau_0 = 2.5s
     where tau_{k, t} is the age in seconds of resting liquidity at price level P_k.
     Newly flashed spoof walls (tau < 0.5s) receive near-zero weight in `obi_clean`.
  2. Cancel-to-Fill Ratio (CFR_t):
         CFR_t = sum max(0, -Delta Q_{book, t} - V_{traded, t}) / (sum V_{traded, t} + eps)
  3. Hidden Iceberg Replenishment Detector:
     If aggressive sell volume V_sell > 0.8 * Q^B_{1, t-1} while best_bid holds (P^B_{1, t} >= P^B_{1, t-1}):
         Q^B_{iceberg, t} = max(0, V_sell - max(0, Q^B_{1, t-1} - Q^B_{1, t}))
     Symmetric formula for Q^A_{iceberg, t} when V_buy > 0.8 * Q^A_{1, t-1} and P^A_{1, t} <= P^A_{1, t-1}.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


def compute_clean_persistence_weight(
    level_k_1based: int,
    age_sec: float,
    decay_lambda: float = 0.25,
    tau_0: float = 2.5,
) -> float:
    """
    Compute the anti-spoofing persistence weight for level k in {1..20}:
        w_{k, t}^{clean} = exp(-lambda * (k - 1)) * (1 - exp(-tau_{k, t} / tau_0))
    """
    k_idx = max(0, int(level_k_1based) - 1)
    tau = max(0.0, float(age_sec))
    tau_ref = max(1e-6, float(tau_0))
    depth_weight = math.exp(-float(decay_lambda) * k_idx)
    persistence_factor = 1.0 - math.exp(-tau / tau_ref)
    return float(depth_weight * persistence_factor)


def compute_cancel_to_fill_ratio(
    prev_book: Dict[str, Any],
    curr_book: Dict[str, Any],
    traded_buy_vol: float = 0.0,
    traded_sell_vol: float = 0.0,
    eps: float = 1e-6,
) -> Dict[str, Any]:
    """
    Compute the Cancel-to-Fill Ratio (CFR_t):
        CFR_t = sum max(0, -Delta Q_{book, t} - V_{traded, t}) / (sum V_{traded, t} + eps)
    """
    prev_bids = {float(p): float(q) for p, q in prev_book.get("bids", prev_book.get("b", []))}
    curr_bids = {float(p): float(q) for p, q in curr_book.get("bids", curr_book.get("b", []))}
    prev_asks = {float(p): float(q) for p, q in prev_book.get("asks", prev_book.get("a", []))}
    curr_asks = {float(p): float(q) for p, q in curr_book.get("asks", curr_book.get("a", []))}

    bid_qty_drop = 0.0
    for p, q_prev in prev_bids.items():
        q_curr = curr_bids.get(p, 0.0)
        if q_curr < q_prev:
            bid_qty_drop += (q_prev - q_curr)

    ask_qty_drop = 0.0
    for p, q_prev in prev_asks.items():
        q_curr = curr_asks.get(p, 0.0)
        if q_curr < q_prev:
            ask_qty_drop += (q_prev - q_curr)

    v_sell = max(0.0, float(traded_sell_vol))
    v_buy = max(0.0, float(traded_buy_vol))

    canceled_bid = max(0.0, bid_qty_drop - v_sell)
    canceled_ask = max(0.0, ask_qty_drop - v_buy)
    total_canceled = canceled_bid + canceled_ask
    total_traded = v_sell + v_buy

    cfr = total_canceled / (total_traded + float(eps))
    return {
        "cfr": float(cfr),
        "canceled_bid_vol": float(canceled_bid),
        "canceled_ask_vol": float(canceled_ask),
        "total_canceled_vol": float(total_canceled),
        "total_traded_vol": float(total_traded),
    }


def detect_hidden_iceberg(
    prev_book: Dict[str, Any],
    curr_book: Dict[str, Any],
    aggressive_sell_vol: float = 0.0,
    aggressive_buy_vol: float = 0.0,
) -> Dict[str, Any]:
    """
    Detect Hidden Iceberg Order replenishment at top-of-book (`best_bid` / `best_ask`):
      - Bid Iceberg: When V_sell > 0.8 * Q^B_{1, t-1} and P^B_{1, t} >= P^B_{1, t-1}:
            Q^B_{iceberg, t} = max(0, V_sell - max(0, Q^B_{1, t-1} - Q^B_{1, t}))
      - Ask Iceberg: When V_buy > 0.8 * Q^A_{1, t-1} and P^A_{1, t} <= P^A_{1, t-1}:
            Q^A_{iceberg, t} = max(0, V_buy - max(0, Q^A_{1, t-1} - Q^A_{1, t}))
    """
    p_bids = prev_book.get("bids", prev_book.get("b", []))
    c_bids = curr_book.get("bids", curr_book.get("b", []))
    p_asks = prev_book.get("asks", prev_book.get("a", []))
    c_asks = curr_book.get("asks", curr_book.get("a", []))

    q_iceberg_bid = 0.0
    q_iceberg_ask = 0.0

    v_sell = max(0.0, float(aggressive_sell_vol))
    v_buy = max(0.0, float(aggressive_buy_vol))

    if p_bids and c_bids:
        pb_prev, qb_prev = float(p_bids[0][0]), float(p_bids[0][1])
        pb_curr, qb_curr = float(c_bids[0][0]), float(c_bids[0][1])
        if qb_prev > 1e-12 and v_sell > 0.8 * qb_prev and pb_curr >= pb_prev - 1e-12:
            visible_depletion = max(0.0, qb_prev - qb_curr)
            q_iceberg_bid = max(0.0, v_sell - visible_depletion)

    if p_asks and c_asks:
        pa_prev, qa_prev = float(p_asks[0][0]), float(p_asks[0][1])
        pa_curr, qa_curr = float(c_asks[0][0]), float(c_asks[0][1])
        if qa_prev > 1e-12 and v_buy > 0.8 * qa_prev and pa_curr <= pa_prev + 1e-12:
            visible_depletion = max(0.0, qa_prev - qa_curr)
            q_iceberg_ask = max(0.0, v_buy - visible_depletion)

    iceberg_bid_detected = bool(q_iceberg_bid > 1e-9)
    iceberg_ask_detected = bool(q_iceberg_ask > 1e-9)

    if iceberg_bid_detected and q_iceberg_bid >= q_iceberg_ask:
        tag = "ICEBERG_ABSORPTION"
        side = "BID"
    elif iceberg_ask_detected:
        tag = "ICEBERG_ABSORPTION"
        side = "ASK"
    else:
        tag = "NONE"
        side = "NONE"

    return {
        "q_iceberg_bid": float(q_iceberg_bid),
        "q_iceberg_ask": float(q_iceberg_ask),
        "iceberg_bid_detected": iceberg_bid_detected,
        "iceberg_ask_detected": iceberg_ask_detected,
        "iceberg_tag": tag,
        "iceberg_side": side,
    }


class OrderBookPersistenceTracker:
    """
    Stateful tracker for 20-level order book persistence lifetimes tau_{k, t},
    Cancel-to-Fill Ratio (CFR), Spoof Wall detection, and Hidden Iceberg absorption.
    """

    def __init__(
        self,
        decay_lambda: float = 0.25,
        tau_0: float = 2.5,
        spoof_max_age_sec: float = 1.0,
        spoof_min_size_mult: float = 2.5,
    ) -> None:
        self.decay_lambda = float(decay_lambda)
        self.tau_0 = float(tau_0)
        self.spoof_max_age_sec = float(spoof_max_age_sec)
        self.spoof_min_size_mult = float(spoof_min_size_mult)

        # Map price -> {"first_seen_sec": float, "qty": float, "peak_qty": float}
        self._bid_levels: Dict[float, Dict[str, float]] = {}
        self._ask_levels: Dict[float, Dict[str, float]] = {}
        self._prev_book: Optional[Dict[str, Any]] = None
        self._cumulative_iceberg_bid: float = 0.0
        self._cumulative_iceberg_ask: float = 0.0

    def update(
        self,
        curr_book: Dict[str, Any],
        t_sec: Optional[float] = None,
        aggressive_sell_vol: float = 0.0,
        aggressive_buy_vol: float = 0.0,
        level_ages_override: Optional[Dict[str, Sequence[float]]] = None,
    ) -> Dict[str, Any]:
        """
        Process a new 20-level order book snapshot at `t_sec` (seconds).
        Returns `obi_raw`, `obi_clean`, `cfr`, `spoof_wall_detected`, `q_iceberg_bid`, `q_iceberg_ask`, etc.
        """
        if t_sec is None:
            ts_ms = curr_book.get("ts_ms", curr_book.get("E", curr_book.get("T", 0)))
            t_sec = float(ts_ms) / 1000.0 if ts_ms else 0.0
        now_s = float(t_sec)

        raw_bids = curr_book.get("bids", curr_book.get("b", []))[:20]
        raw_asks = curr_book.get("asks", curr_book.get("a", []))[:20]

        bids: List[Tuple[float, float]] = [(float(p), float(q)) for p, q in raw_bids]
        asks: List[Tuple[float, float]] = [(float(p), float(q)) for p, q in raw_asks]

        # Check if any short-lived large wall from `_prev_book` vanished without trade fills
        spoof_wall_detected = False
        spoof_side = "NONE"

        curr_bid_map = {p: q for p, q in bids}
        curr_ask_map = {p: q for p, q in asks}

        avg_bid_qty = (sum(q for _p, q in bids) / len(bids)) if bids else 1.0
        avg_ask_qty = (sum(q for _p, q in asks) / len(asks)) if asks else 1.0

        for p, info in list(self._bid_levels.items()):
            wall_age = max(0.0, now_s - info.get("surge_seen_sec", info["first_seen_sec"]))
            new_q = curr_bid_map.get(p, 0.0)
            dropped = info["qty"] - new_q
            if (
                dropped > max(avg_bid_qty * self.spoof_min_size_mult, 1e-6)
                and wall_age <= self.spoof_max_age_sec
                and aggressive_sell_vol < 0.25 * dropped
            ):
                spoof_wall_detected = True
                spoof_side = "BID"
            if new_q <= 1e-12:
                del self._bid_levels[p]

        for p, info in list(self._ask_levels.items()):
            wall_age = max(0.0, now_s - info.get("surge_seen_sec", info["first_seen_sec"]))
            new_q = curr_ask_map.get(p, 0.0)
            dropped = info["qty"] - new_q
            if (
                dropped > max(avg_ask_qty * self.spoof_min_size_mult, 1e-6)
                and wall_age <= self.spoof_max_age_sec
                and aggressive_buy_vol < 0.25 * dropped
            ):
                spoof_wall_detected = True
                spoof_side = "ASK"
            if new_q <= 1e-12:
                del self._ask_levels[p]

        # Update resting lifetimes for current levels.
        # If size at an existing price level suddenly jumps above its prior resting size,
        # only the pre-existing resting portion has `old_age`, while the newly flashed addition has age = 0.0s!
        bid_clean_weighted_qtys: List[float] = []
        for idx, (p, q) in enumerate(bids):
            k_1based = idx + 1
            if level_ages_override and "bids" in level_ages_override and idx < len(level_ages_override["bids"]):
                age_val = float(level_ages_override["bids"][idx])
                self._bid_levels[p] = {"first_seen_sec": now_s - age_val, "surge_seen_sec": now_s - age_val, "qty": q, "base_qty": q}
                w_c = compute_clean_persistence_weight(k_1based, age_val, decay_lambda=self.decay_lambda, tau_0=self.tau_0)
                bid_clean_weighted_qtys.append(w_c * q)
                continue

            if p in self._bid_levels:
                info = self._bid_levels[p]
                old_age = max(0.0, now_s - info["first_seen_sec"])
                base_q = min(q, info.get("base_qty", info["qty"]))
                added_q = max(0.0, q - base_q)
                if added_q > base_q:
                    # Newly flashed wall on top of resting level: flashed portion has age = 0.02s
                    if q > info["qty"] * 1.5:
                        info["surge_seen_sec"] = now_s
                    surge_age = max(0.02, now_s - info.get("surge_seen_sec", now_s))
                    w_base = compute_clean_persistence_weight(k_1based, old_age, decay_lambda=self.decay_lambda, tau_0=self.tau_0)
                    w_add = compute_clean_persistence_weight(k_1based, surge_age, decay_lambda=self.decay_lambda, tau_0=self.tau_0)
                    bid_clean_weighted_qtys.append(w_base * base_q + w_add * added_q)
                    info["qty"] = q
                else:
                    info["qty"] = q
                    info["base_qty"] = q
                    info["surge_seen_sec"] = info["first_seen_sec"]
                    w_c = compute_clean_persistence_weight(k_1based, old_age, decay_lambda=self.decay_lambda, tau_0=self.tau_0)
                    bid_clean_weighted_qtys.append(w_c * q)
            else:
                # Newly appeared level starts with small initial age (0.02s)
                self._bid_levels[p] = {"first_seen_sec": now_s, "surge_seen_sec": now_s, "qty": q, "base_qty": q}
                w_c = compute_clean_persistence_weight(k_1based, 0.02, decay_lambda=self.decay_lambda, tau_0=self.tau_0)
                bid_clean_weighted_qtys.append(w_c * q)

        ask_clean_weighted_qtys: List[float] = []
        for idx, (p, q) in enumerate(asks):
            k_1based = idx + 1
            if level_ages_override and "asks" in level_ages_override and idx < len(level_ages_override["asks"]):
                age_val = float(level_ages_override["asks"][idx])
                self._ask_levels[p] = {"first_seen_sec": now_s - age_val, "surge_seen_sec": now_s - age_val, "qty": q, "base_qty": q}
                w_c = compute_clean_persistence_weight(k_1based, age_val, decay_lambda=self.decay_lambda, tau_0=self.tau_0)
                ask_clean_weighted_qtys.append(w_c * q)
                continue

            if p in self._ask_levels:
                info = self._ask_levels[p]
                old_age = max(0.0, now_s - info["first_seen_sec"])
                base_q = min(q, info.get("base_qty", info["qty"]))
                added_q = max(0.0, q - base_q)
                if added_q > base_q:
                    if q > info["qty"] * 1.5:
                        info["surge_seen_sec"] = now_s
                    surge_age = max(0.02, now_s - info.get("surge_seen_sec", now_s))
                    w_base = compute_clean_persistence_weight(k_1based, old_age, decay_lambda=self.decay_lambda, tau_0=self.tau_0)
                    w_add = compute_clean_persistence_weight(k_1based, surge_age, decay_lambda=self.decay_lambda, tau_0=self.tau_0)
                    ask_clean_weighted_qtys.append(w_base * base_q + w_add * added_q)
                    info["qty"] = q
                else:
                    info["qty"] = q
                    info["base_qty"] = q
                    info["surge_seen_sec"] = info["first_seen_sec"]
                    w_c = compute_clean_persistence_weight(k_1based, old_age, decay_lambda=self.decay_lambda, tau_0=self.tau_0)
                    ask_clean_weighted_qtys.append(w_c * q)
            else:
                self._ask_levels[p] = {"first_seen_sec": now_s, "surge_seen_sec": now_s, "qty": q, "base_qty": q}
                w_c = compute_clean_persistence_weight(k_1based, 0.02, decay_lambda=self.decay_lambda, tau_0=self.tau_0)
                ask_clean_weighted_qtys.append(w_c * q)

        # Compute raw OBI vs persistence-weighted `obi_clean`
        raw_bid_sum = 0.0
        raw_ask_sum = 0.0
        clean_bid_sum = 0.0
        clean_ask_sum = 0.0

        levels = min(20, len(bids), len(asks))
        for idx in range(levels):
            w_raw = math.exp(-self.decay_lambda * idx)
            qb = bids[idx][1]
            qa = asks[idx][1]
            raw_bid_sum += w_raw * qb
            raw_ask_sum += w_raw * qa
            clean_bid_sum += bid_clean_weighted_qtys[idx]
            clean_ask_sum += ask_clean_weighted_qtys[idx]

        raw_denom = raw_bid_sum + raw_ask_sum
        clean_denom = clean_bid_sum + clean_ask_sum
        obi_raw = ((raw_bid_sum - raw_ask_sum) / raw_denom) if raw_denom > 1e-12 else 0.0
        obi_clean = ((clean_bid_sum - clean_ask_sum) / clean_denom) if clean_denom > 1e-12 else 0.0

        if self._prev_book is not None:
            cfr_info = compute_cancel_to_fill_ratio(
                self._prev_book,
                curr_book,
                traded_buy_vol=aggressive_buy_vol,
                traded_sell_vol=aggressive_sell_vol,
            )
            iceberg_info = detect_hidden_iceberg(
                self._prev_book,
                curr_book,
                aggressive_sell_vol=aggressive_sell_vol,
                aggressive_buy_vol=aggressive_buy_vol,
            )
        else:
            cfr_info = {"cfr": 0.0, "total_canceled_vol": 0.0, "total_traded_vol": 0.0}
            iceberg_info = {
                "q_iceberg_bid": 0.0,
                "q_iceberg_ask": 0.0,
                "iceberg_bid_detected": False,
                "iceberg_ask_detected": False,
                "iceberg_tag": "NONE",
                "iceberg_side": "NONE",
            }

        self._cumulative_iceberg_bid += iceberg_info["q_iceberg_bid"]
        self._cumulative_iceberg_ask += iceberg_info["q_iceberg_ask"]
        self._prev_book = {"bids": bids, "asks": asks, "ts_ms": int(now_s * 1000)}

        if spoof_wall_detected:
            anomaly_tag = "SPOOF_WALL"
        elif iceberg_info["iceberg_tag"] == "ICEBERG_ABSORPTION":
            anomaly_tag = "ICEBERG_ABSORPTION"
        else:
            anomaly_tag = "CLEAN"

        return {
            "obi_raw": float(obi_raw),
            "obi_clean": float(obi_clean),
            "cfr": float(cfr_info["cfr"]),
            "spoof_wall_detected": bool(spoof_wall_detected),
            "spoof_side": spoof_side,
            "q_iceberg_bid": float(iceberg_info["q_iceberg_bid"]),
            "q_iceberg_ask": float(iceberg_info["q_iceberg_ask"]),
            "cumulative_iceberg_bid": float(self._cumulative_iceberg_bid),
            "cumulative_iceberg_ask": float(self._cumulative_iceberg_ask),
            "iceberg_bid_detected": bool(iceberg_info["iceberg_bid_detected"]),
            "iceberg_ask_detected": bool(iceberg_info["iceberg_ask_detected"]),
            "anomaly_tag": anomaly_tag,
        }
