"""
===========================================================================
PYROFUEL SUB-SECOND PRIORITY INTERRUPT EVENT BUS v3.0 (T6.5)
===========================================================================
Replaces blind `time.sleep()` loops with a < 50ms wake-up priority queue
built on `threading.Condition` + `heapq`:
- Priority 0: `CRITICAL_POSITION_INTERRUPT`
  Triggered by `exec/userstream.py` (TP1/SL fill) or `exec/thesis_monitor.py`
  (P_survive < 0.18) or intrabar price alarm hitting TP1 (+0.55R) to amend SL
  to +0.38R in < 200ms.
- Priority 1: `MICROSTRUCTURE_SNIPER_TRIGGER`
  Triggered by `features/hawkes.py` (`CASCADE_EXHAUSTED_INFLECTION`) or
  `features/cross_asset_leadlag.py` (`BTC -> Altcoin impulse`).
- Priority 2: `CLOSED_CANDLE_BOUNDARY_SCAN`
  Triggered 50ms after 15m/1h candle close (`k['x'] == True`).
===========================================================================
"""
from __future__ import annotations

import heapq
import itertools
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple


class EventPriority(IntEnum):
    CRITICAL_POSITION_INTERRUPT = 0
    MICROSTRUCTURE_SNIPER_TRIGGER = 1
    CLOSED_CANDLE_BOUNDARY_SCAN = 2
    ROUTINE_HEARTBEAT = 3


CRITICAL_POSITION_INTERRUPT = EventPriority.CRITICAL_POSITION_INTERRUPT
MICROSTRUCTURE_SNIPER_TRIGGER = EventPriority.MICROSTRUCTURE_SNIPER_TRIGGER
CLOSED_CANDLE_BOUNDARY_SCAN = EventPriority.CLOSED_CANDLE_BOUNDARY_SCAN


@dataclass(order=True)
class BusEvent:
    priority: int
    seq: int
    created_ts: float = field(compare=False)
    event_type: str = field(compare=False)
    payload: Dict[str, Any] = field(compare=False, default_factory=dict)


class PriorityEventBus:
    """
    Sub-second event-driven priority interrupt bus (< 50ms wake-up SLA).
    """

    DEFAULT_PRIORITY_MAP = {
        "CRITICAL_POSITION_INTERRUPT": int(EventPriority.CRITICAL_POSITION_INTERRUPT),
        "TP1_REACHED_ALARM": int(EventPriority.CRITICAL_POSITION_INTERRUPT),
        "THESIS_INVALIDATED_ALARM": int(EventPriority.CRITICAL_POSITION_INTERRUPT),
        "ORDER_FILL_INTERRUPT": int(EventPriority.CRITICAL_POSITION_INTERRUPT),
        "MICROSTRUCTURE_SNIPER_TRIGGER": int(EventPriority.MICROSTRUCTURE_SNIPER_TRIGGER),
        "CLOSED_CANDLE_BOUNDARY_SCAN": int(EventPriority.CLOSED_CANDLE_BOUNDARY_SCAN),
    }

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._heap: List[BusEvent] = []
        self._counter = itertools.count()
        self._subscribers: Dict[str, List[Callable[[BusEvent], None]]] = {}
        self._price_alarms: List[Dict[str, Any]] = []
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

    def subscribe(self, event_type: str, handler: Callable[[BusEvent], None]) -> None:
        with self._cond:
            self._subscribers.setdefault(event_type, []).append(handler)

    def publish(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: Optional[int] = None,
    ) -> BusEvent:
        """
        Publish an event and immediately wake any waiting consumer thread (< 1ms).
        """
        prio = (
            int(priority)
            if priority is not None
            else self.DEFAULT_PRIORITY_MAP.get(event_type, int(EventPriority.CLOSED_CANDLE_BOUNDARY_SCAN))
        )
        evt = BusEvent(
            priority=prio,
            seq=next(self._counter),
            created_ts=time.perf_counter(),
            event_type=str(event_type),
            payload=dict(payload or {}),
        )
        with self._cond:
            heapq.heappush(self._heap, evt)
            self._cond.notify_all()
        return evt

    def wait_next(self, timeout_sec: float = 1.0) -> Optional[BusEvent]:
        """
        Replace `time.sleep(timeout_sec)`: waits up to `timeout_sec`, waking up
        within < 50ms as soon as a priority event is published.
        """
        deadline = time.perf_counter() + max(0.0, float(timeout_sec))
        with self._cond:
            while not self._heap:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    return None
                self._cond.wait(timeout=remaining)
            return heapq.heappop(self._heap)

    def dispatch_next(self, timeout_sec: float = 0.05) -> Optional[Tuple[BusEvent, float]]:
        """
        Wait for the next event, invoke all registered subscribers for its `event_type`
        (plus wildcard `"*"`), and return `(event, wakeup_latency_ms)`.
        """
        evt = self.wait_next(timeout_sec=timeout_sec)
        if evt is None:
            return None
        latency_ms = (time.perf_counter() - evt.created_ts) * 1000.0
        with self._cond:
            handlers = list(self._subscribers.get(evt.event_type, [])) + list(
                self._subscribers.get("*", [])
            )
        for h in handlers:
            h(evt)
        return evt, latency_ms

    def dispatch_all(self) -> List[Tuple[BusEvent, float]]:
        """
        Dispatch all currently queued priority events in strict priority order.
        """
        dispatched: List[Tuple[BusEvent, float]] = []
        while self.pending_count() > 0:
            res = self.dispatch_next(timeout_sec=0.01)
            if res is None:
                break
            dispatched.append(res)
        return dispatched

    def register_price_alarm(
        self,
        symbol: str,
        direction: str,
        trigger_price: float,
        event_type: str = "CRITICAL_POSITION_INTERRUPT",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register an intrabar price alarm (e.g. TP1 at +0.55R) that fires a
        `CRITICAL_POSITION_INTERRUPT` immediately when `on_price_tick` crosses `trigger_price`.
        """
        with self._cond:
            self._price_alarms.append(
                {
                    "symbol": str(symbol).upper().strip(),
                    "direction": str(direction).upper().strip(),
                    "trigger_price": float(trigger_price),
                    "event_type": event_type,
                    "payload": dict(payload or {}),
                    "triggered": False,
                }
            )

    def on_price_tick(self, symbol: str, mark_price: float) -> List[BusEvent]:
        """
        Check registered price alarms for `symbol` and publish `CRITICAL_POSITION_INTERRUPT`
        if `mark_price` reaches or crosses `trigger_price`.
        """
        sym = str(symbol).upper().strip()
        px = float(mark_price)
        fired: List[BusEvent] = []
        to_fire: List[Dict[str, Any]] = []

        with self._cond:
            remaining: List[Dict[str, Any]] = []
            for alarm in self._price_alarms:
                if alarm["symbol"] != sym or alarm["triggered"]:
                    remaining.append(alarm)
                    continue
                hit = (
                    (px >= alarm["trigger_price"])
                    if alarm["direction"] == "LONG"
                    else (px <= alarm["trigger_price"])
                )
                if hit:
                    alarm["triggered"] = True
                    to_fire.append(alarm)
                else:
                    remaining.append(alarm)
            self._price_alarms = remaining

        for alarm in to_fire:
            pl = dict(alarm["payload"])
            pl.update(
                {
                    "symbol": sym,
                    "direction": alarm["direction"],
                    "trigger_price": alarm["trigger_price"],
                    "mark_price": px,
                }
            )
            evt = self.publish(
                alarm["event_type"],
                payload=pl,
                priority=int(EventPriority.CRITICAL_POSITION_INTERRUPT),
            )
            fired.append(evt)
        return fired

    def pending_count(self) -> int:
        with self._cond:
            return len(self._heap)
