"""
Pilar 9 (T3.5) — Self-Exciting Hawkes Point Process for Liquidation Cascade Inflection Detection.

Models aggressive sell/liquidation arrival intensity lambda_-(t) and aggressive buy/short-squeeze
intensity lambda_+(t) using an O(1) recursive exponential kernel:
    lambda_+/-(t) = mu_+/- + I_+/-(t)
    I_+/-(t) = I_+/-(t_{k-1}) * exp(-beta * (t - t_{k-1})) + sum_{t_k = t} alpha * ln(1 + Q_k / Q_scale)

with half-life tau_{1/2} = 15s (beta = ln(2) / 15) and branching ratio eta = alpha / beta < 1.

Classifies real-time cascade phase into:
  - `BASELINE`
  - `CASCADE_ACCELERATING` (falling knife / active cascade -> blocks opposing entry)
  - `CASCADE_EXHAUSTED_INFLECTION` (cascade fuel exhausted + reversal flow taking over -> Sniper Entry)
"""

from __future__ import annotations

import collections
import math
from typing import Any, Deque, Dict, Iterable, Optional, Tuple


class HawkesCascadeTracker:
    """
    O(1) Recursive Exponential Hawkes Point Process Tracker for real-time liquidation
    and aggressive sweep cascades.
    """

    def __init__(
        self,
        mu_minus: float = 0.10,
        mu_plus: float = 0.10,
        half_life_sec: float = 15.0,
        branching_ratio_eta: float = 0.70,
        q_scale: float = 10_000.0,
        peak_window_sec: float = 180.0,
    ) -> None:
        self.mu_minus = max(float(mu_minus), 1e-6)
        self.mu_plus = max(float(mu_plus), 1e-6)
        self.half_life_sec = max(float(half_life_sec), 0.5)
        self.beta = math.log(2.0) / self.half_life_sec
        # Enforce stationarity condition: branching ratio eta = alpha / beta < 1
        self.eta = max(0.05, min(0.98, float(branching_ratio_eta)))
        self.alpha = self.eta * self.beta
        self.q_scale = max(float(q_scale), 1e-6)
        self.peak_window_sec = max(10.0, float(peak_window_sec))

        self.i_minus: float = 0.0
        self.i_plus: float = 0.0
        self.last_t: Optional[float] = None
        self.prev_lambda_minus: float = self.mu_minus
        self.prev_lambda_plus: float = self.mu_plus
        self.d_lambda_minus: float = 0.0
        self.d_lambda_plus: float = 0.0

        # Rolling 3-minute history of (t_sec, lambda_minus, lambda_plus) for peak tracking
        self._peak_history: Deque[Tuple[float, float, float]] = collections.deque(maxlen=2000)

    @property
    def branching_ratio(self) -> float:
        return self.alpha / self.beta

    def _decay_to(self, t_sec: float) -> float:
        if self.last_t is None:
            self.last_t = float(t_sec)
            return 0.0
        dt = max(0.0, float(t_sec) - self.last_t)
        if dt > 0.0:
            decay_factor = math.exp(-self.beta * dt)
            self.i_minus *= decay_factor
            self.i_plus *= decay_factor
            self.last_t = float(t_sec)
        return dt

    def _prune_peaks(self, t_sec: float) -> None:
        cutoff = float(t_sec) - self.peak_window_sec
        while self._peak_history and self._peak_history[0][0] < cutoff:
            self._peak_history.popleft()

    def update_event(
        self,
        t_sec: float,
        side: str,
        quantity_usd: float,
    ) -> Tuple[float, float]:
        """
        Process an arrival event at time `t_sec` (in seconds):
          - `side in ("SELL", "LONG_LIQ", "MINUS", "-1")` -> excites `lambda_minus(t)`
            (aggressive sell sweep / Long position force-liquidated).
          - `side in ("BUY", "SHORT_LIQ", "PLUS", "+1")` -> excites `lambda_plus(t)`
            (aggressive buy sweep / Short position force-liquidated).
        Returns `(lambda_minus, lambda_plus)` immediately after the event jump.
        """
        old_l_minus = self.mu_minus + self.i_minus
        old_l_plus = self.mu_plus + self.i_plus

        self._decay_to(t_sec)
        jump = self.alpha * math.log(1.0 + max(0.0, float(quantity_usd)) / self.q_scale)

        side_upper = str(side).upper()
        if side_upper in ("SELL", "LONG_LIQ", "MINUS", "-1", "BEAR"):
            self.i_minus += jump
        else:
            self.i_plus += jump

        l_minus = self.mu_minus + self.i_minus
        l_plus = self.mu_plus + self.i_plus

        self.d_lambda_minus = l_minus - old_l_minus
        self.d_lambda_plus = l_plus - old_l_plus
        self.prev_lambda_minus = l_minus
        self.prev_lambda_plus = l_plus

        self._peak_history.append((float(t_sec), l_minus, l_plus))
        self._prune_peaks(t_sec)
        return l_minus, l_plus

    def evaluate(
        self,
        t_sec: Optional[float] = None,
        ofi_20: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate the Hawkes intensities at time `t_sec` (applying pure exponential decay
        since `last_t` if no new event occurred at `t_sec`) and classify the cascade state:
          - `BASELINE`
          - `CASCADE_ACCELERATING`
          - `CASCADE_EXHAUSTED_INFLECTION`
        """
        if t_sec is not None:
            old_l_minus = self.mu_minus + self.i_minus
            old_l_plus = self.mu_plus + self.i_plus
            dt = self._decay_to(float(t_sec))
            l_minus = self.mu_minus + self.i_minus
            l_plus = self.mu_plus + self.i_plus
            if dt > 0.0:
                self.d_lambda_minus = (l_minus - old_l_minus) / max(dt, 1e-3)
                self.d_lambda_plus = (l_plus - old_l_plus) / max(dt, 1e-3)
            self._prune_peaks(float(t_sec))
            self._peak_history.append((float(t_sec), l_minus, l_plus))
        else:
            l_minus = self.mu_minus + self.i_minus
            l_plus = self.mu_plus + self.i_plus

        ratio_minus = l_minus / self.mu_minus
        ratio_plus = l_plus / self.mu_plus

        if self._peak_history:
            max_l_minus = max(item[1] for item in self._peak_history)
            max_l_plus = max(item[2] for item in self._peak_history)
        else:
            max_l_minus = l_minus
            max_l_plus = l_plus

        max_ratio_minus = max_l_minus / self.mu_minus
        max_ratio_plus = max_l_plus / self.mu_plus

        # 1. Check for `CASCADE_EXHAUSTED_INFLECTION` (Sniper Reversal Entry):
        # Long Sniper (after sell/long-liq cascade):
        #   - Peak lambda_-(t) in last 3m exceeded 5.0 * mu_-
        #   - Current lambda_-(t) < 0.35 * max(lambda_-) and d_lambda_-/dt <= 0
        #   - Buying intensity lambda_+(t) > lambda_-(t)
        #   - If ofi_20 is provided, ofi_20 > +0.25
        ofi_long_ok = True if ofi_20 is None else (float(ofi_20) > 0.25)
        ofi_short_ok = True if ofi_20 is None else (float(ofi_20) < -0.25)

        long_inflection = (
            max_ratio_minus > 5.0
            and l_minus < 0.35 * max_l_minus
            and self.d_lambda_minus <= 0.0
            and l_plus > l_minus
            and ofi_long_ok
        )
        short_inflection = (
            max_ratio_plus > 5.0
            and l_plus < 0.35 * max_l_plus
            and self.d_lambda_plus <= 0.0
            and l_minus > l_plus
            and ofi_short_ok
        )

        # 2. Check for `CASCADE_ACCELERATING` (Danger / Falling Knife):
        sell_accelerating = ratio_minus > 4.0 and self.d_lambda_minus >= -1e-9
        buy_accelerating = ratio_plus > 4.0 and self.d_lambda_plus >= -1e-9

        if long_inflection:
            state = "CASCADE_EXHAUSTED_INFLECTION"
            sniper_dir = "LONG"
            block_long = False
            block_short = False
        elif short_inflection:
            state = "CASCADE_EXHAUSTED_INFLECTION"
            sniper_dir = "SHORT"
            block_long = False
            block_short = False
        elif sell_accelerating or buy_accelerating:
            state = "CASCADE_ACCELERATING"
            sniper_dir = "NONE"
            block_long = bool(sell_accelerating)
            block_short = bool(buy_accelerating)
        else:
            state = "BASELINE"
            sniper_dir = "NONE"
            block_long = False
            block_short = False

        return {
            "state": state,
            "lambda_minus": float(l_minus),
            "lambda_plus": float(l_plus),
            "mu_minus": float(self.mu_minus),
            "mu_plus": float(self.mu_plus),
            "ratio_minus": float(ratio_minus),
            "ratio_plus": float(ratio_plus),
            "d_lambda_minus": float(self.d_lambda_minus),
            "d_lambda_plus": float(self.d_lambda_plus),
            "max_lambda_minus_3m": float(max_l_minus),
            "max_lambda_plus_3m": float(max_l_plus),
            "branching_ratio_eta": float(self.branching_ratio),
            "alpha": float(self.alpha),
            "beta": float(self.beta),
            "block_long": block_long,
            "block_short": block_short,
            "sniper_reversal_direction": sniper_dir,
            "recommended_sniper_sl_pct": 0.55 if state == "CASCADE_EXHAUSTED_INFLECTION" else 1.20,
        }


def evaluate_hawkes_cascade(
    events: Iterable[Dict[str, Any]],
    eval_t_sec: Optional[float] = None,
    ofi_20: Optional[float] = None,
    mu_minus: float = 0.10,
    mu_plus: float = 0.10,
    half_life_sec: float = 15.0,
    branching_ratio_eta: float = 0.70,
    q_scale: float = 10_000.0,
) -> Dict[str, Any]:
    """
    Stateless convenience wrapper to replay a sequence of liquidation / aggressive trade
    events through `HawkesCascadeTracker` and evaluate at `eval_t_sec`.
    """
    tracker = HawkesCascadeTracker(
        mu_minus=mu_minus,
        mu_plus=mu_plus,
        half_life_sec=half_life_sec,
        branching_ratio_eta=branching_ratio_eta,
        q_scale=q_scale,
    )
    for ev in events:
        if "t_sec" in ev:
            t_s = float(ev["t_sec"])
        elif "ts_ms" in ev:
            t_s = float(ev["ts_ms"]) / 1000.0
        elif "T" in ev:
            t_s = float(ev["T"]) / 1000.0
        else:
            t_s = float(ev.get("t", 0.0))
        side = str(ev.get("side", ev.get("S", "SELL")))
        usd = float(ev.get("quantity_usd", ev.get("notional_usd", ev.get("q", 10_000.0))))
        tracker.update_event(t_s, side, usd)

    return tracker.evaluate(t_sec=eval_t_sec, ofi_20=ofi_20)
