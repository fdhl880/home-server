"""
Pilar 28 (T3.15) — Dynamic `fundingInfo` Interval Tracker (2h/4h/8h), Bulk `premiumIndex`
`nextFundingTime` Guard, & US Macro (CPI/NFP/FOMC) / Sunday CME Open Shock Shield.

Implements Section 13.4:
  1. Dynamic Funding Schedule:
     - Tracks per-symbol `fundingIntervalHours` in {2, 4, 8} from `/fapi/v1/fundingInfo`.
     - Reads bulk `/fapi/v1/premiumIndex` (weight 10 for all symbols) to get exact per-symbol
       `nextFundingTime` (ms), `lastFundingRate`, `markPrice`, and `indexPrice`.
     - Funding Boundary Guard: Blocks entry when `minutes_to_funding <= 10.0` and the position
       direction would pay >= 0.05% (`0.0005` funding rate = 1.0% ROE on 20x leverage).
  2. Macro Shock & Sunday CME Open Shield:
     - Blocks new entries from 15 minutes BEFORE until 10 minutes AFTER (`[-15m, +10m]`):
       * Scheduled US Macro releases (`CPI`, `NFP`, `PPI`, `FOMC`)
       * First-Friday Monthly US NFP release (`12:30 UTC` DST / `13:30 UTC` Standard)
       * Sunday CME Bitcoin Futures Open (`Sunday 22:00 UTC` DST / `23:00 UTC` Standard)
     - Signals `tighten_existing_sl_to_be = True` during shield windows.
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

logger = logging.getLogger(__name__)

DEFAULT_FAPI_HOSTS: List[str] = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi4.binance.com",
]


def _is_us_dst(dt_utc: datetime.datetime) -> bool:
    """
    Determine whether US Eastern Time is in Daylight Saving Time (EDT = UTC-4)
    or Standard Time (EST = UTC-5) for a given UTC datetime:
      - Starts 2nd Sunday in March at 07:00 UTC
      - Ends 1st Sunday in November at 06:00 UTC
    """
    year = dt_utc.year
    # 2nd Sunday in March
    march_1 = datetime.datetime(year, 3, 1, tzinfo=datetime.timezone.utc)
    first_sun_march = 1 + ((6 - march_1.weekday()) % 7)
    second_sun_march = first_sun_march + 7
    dst_start = datetime.datetime(year, 3, second_sun_march, 7, 0, tzinfo=datetime.timezone.utc)

    # 1st Sunday in November
    nov_1 = datetime.datetime(year, 11, 1, tzinfo=datetime.timezone.utc)
    first_sun_nov = 1 + ((6 - nov_1.weekday()) % 7)
    dst_end = datetime.datetime(year, 11, first_sun_nov, 6, 0, tzinfo=datetime.timezone.utc)

    return dst_start <= dt_utc < dst_end


def compute_next_dynamic_funding_ms(
    now_ms: int,
    interval_hours: int = 8,
    explicit_next_funding_ms: Optional[int] = None,
) -> int:
    """
    Compute the exact next funding timestamp in milliseconds.
    Priority:
      1. `explicit_next_funding_ms` from `/fapi/v1/premiumIndex` if > `now_ms`.
      2. Dynamic schedule aligned to UTC `00:00` every `interval_hours` in `{1, 2, 4, 8}`.
    """
    if explicit_next_funding_ms is not None and int(explicit_next_funding_ms) >= int(now_ms):
        return int(explicit_next_funding_ms)

    iv_h = int(interval_hours) if int(interval_hours) in (1, 2, 4, 8) else 8
    period_ms = iv_h * 3_600_000
    next_slot_ms = ((int(now_ms) // period_ms) + 1) * period_ms
    return int(next_slot_ms)


def check_macro_and_cme_shield(
    now_ms: int,
    scheduled_events: Optional[Iterable[Dict[str, Any]]] = None,
    pre_event_block_min: float = 15.0,
    post_event_block_min: float = 10.0,
) -> Dict[str, Any]:
    """
    Check if `now_ms` falls within `[-pre_event_block_min, +post_event_block_min]`
    (default `[-15m, +10m]`) of:
      1. Any explicit macro event in `scheduled_events` (e.g. `{"name": "US_CPI", "ts_ms": ...}`).
      2. Automatic First-Friday US Non-Farm Payrolls (NFP) at `08:30 ET` (`12:30 UTC` EDT / `13:30 UTC` EST).
      3. Sunday CME Bitcoin Futures Open (`22:00 UTC` EDT / `23:00 UTC` EST, and checks both 22:00 and 23:00 UTC
         on Sundays so CME open is always shielded regardless of seasonal clock transitions).
    """
    pre_ms = int(float(pre_event_block_min) * 60_000)
    post_ms = int(float(post_event_block_min) * 60_000)
    curr_ms = int(now_ms)

    candidates: List[Tuple[str, int]] = []

    if scheduled_events:
        for ev in scheduled_events:
            if isinstance(ev, dict):
                ev_name = str(ev.get("name", ev.get("event", "US_MACRO_EVENT")))
                ev_ts = int(ev.get("ts_ms", ev.get("timestamp_ms", 0)))
                if ev_ts > 0:
                    candidates.append((ev_name, ev_ts))
            elif isinstance(ev, (int, float)):
                candidates.append(("US_MACRO_EVENT", int(ev)))

    dt_utc = datetime.datetime.fromtimestamp(curr_ms / 1000.0, tz=datetime.timezone.utc)
    is_dst = _is_us_dst(dt_utc)

    # Check Sunday CME Open (weekday() == 6 is Sunday)
    if dt_utc.weekday() == 6:
        for cme_hour in (22, 23):
            cme_dt = datetime.datetime(
                dt_utc.year, dt_utc.month, dt_utc.day, cme_hour, 0, 0, tzinfo=datetime.timezone.utc
            )
            candidates.append(("SUNDAY_CME_FUTURES_OPEN", int(cme_dt.timestamp() * 1000)))

    # Check First-Friday of the month NFP release (weekday() == 4 and 1 <= day <= 7)
    if dt_utc.weekday() == 4 and 1 <= dt_utc.day <= 7:
        nfp_hour = 12 if is_dst else 13
        nfp_dt = datetime.datetime(
            dt_utc.year, dt_utc.month, dt_utc.day, nfp_hour, 30, 0, tzinfo=datetime.timezone.utc
        )
        candidates.append(("US_NFP_RELEASE", int(nfp_dt.timestamp() * 1000)))

    for ev_name, ev_ts_ms in candidates:
        diff_ms = ev_ts_ms - curr_ms  # positive if event is in the future, negative if in the past
        if -post_ms <= diff_ms <= pre_ms:
            minutes_to_event = diff_ms / 60_000.0
            return {
                "shield_active": True,
                "block_new_entries": True,
                "tighten_existing_sl_to_be": True,
                "active_event": ev_name,
                "event_ts_ms": int(ev_ts_ms),
                "minutes_to_event": float(minutes_to_event),
            }

    return {
        "shield_active": False,
        "block_new_entries": False,
        "tighten_existing_sl_to_be": False,
        "active_event": "NONE",
        "event_ts_ms": 0,
        "minutes_to_event": 999.0,
    }


class DynamicFundingAndMacroShield:
    """
    Tracks dynamic per-symbol funding intervals (`2h`, `4h`, `8h` from `/fapi/v1/fundingInfo`),
    bulk `premiumIndex` `nextFundingTime` & `lastFundingRate`, and US Macro / CME Open shock windows.
    """

    def __init__(
        self,
        rest_hosts: Optional[List[str]] = None,
        funding_guard_window_min: float = 10.0,
        funding_rate_threshold: float = 0.0005,
        pre_macro_block_min: float = 15.0,
        post_macro_block_min: float = 10.0,
    ) -> None:
        self.rest_hosts = list(rest_hosts or DEFAULT_FAPI_HOSTS)
        self.funding_guard_window_min = float(funding_guard_window_min)
        self.funding_rate_threshold = float(funding_rate_threshold)
        self.pre_macro_block_min = float(pre_macro_block_min)
        self.post_macro_block_min = float(post_macro_block_min)

        # Symbol -> fundingIntervalHours (2, 4, or 8)
        self.funding_intervals: Dict[str, int] = {}
        # Symbol -> {"markPrice": float, "indexPrice": float, "lastFundingRate": float, "nextFundingTime": int}
        self.premium_index_map: Dict[str, Dict[str, Any]] = {}
        # Scheduled macro events list: [{"name": "US_CPI", "ts_ms": ...}, ...]
        self.scheduled_macro_events: List[Dict[str, Any]] = []
        self.last_funding_info_sync_ms: int = 0
        self.last_premium_sync_ms: int = 0

    def ingest_funding_info(self, funding_info_list: Iterable[Dict[str, Any]]) -> Dict[str, int]:
        """
        Parse response from `GET /fapi/v1/fundingInfo`:
            `[{"symbol": "SOLUSDT", "fundingIntervalHours": 4, ...}, ...]`
        """
        for item in funding_info_list:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol", "")).upper()
            if not sym:
                continue
            iv_hours = int(item.get("fundingIntervalHours", 8) or 8)
            self.funding_intervals[sym] = iv_hours
        return dict(self.funding_intervals)

    def ingest_bulk_premium_index(
        self,
        premium_index_payload: Any,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Parse response from bulk `GET /fapi/v1/premiumIndex` (either a list of all symbols
        or a single symbol dict).
        """
        items = premium_index_payload if isinstance(premium_index_payload, list) else [premium_index_payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol", "")).upper()
            if not sym:
                continue
            self.premium_index_map[sym] = {
                "symbol": sym,
                "mark_price": float(item.get("markPrice", item.get("mark_price", 0.0)) or 0.0),
                "index_price": float(item.get("indexPrice", item.get("index_price", 0.0)) or 0.0),
                "last_funding_rate": float(item.get("lastFundingRate", item.get("funding_rate", 0.0)) or 0.0),
                "next_funding_time": int(item.get("nextFundingTime", item.get("next_funding_time", 0)) or 0),
            }
        return dict(self.premium_index_map)

    def register_macro_event(self, name: str, ts_ms: int) -> None:
        self.scheduled_macro_events.append({"name": str(name), "ts_ms": int(ts_ms)})

    def sync_from_rest(self, timeout: float = 3.0) -> bool:
        """
        Fetch `/fapi/v1/fundingInfo` and bulk `/fapi/v1/premiumIndex` from Binance Futures REST.
        Safe offline fallback if unreachable.
        """
        headers = {"User-Agent": "PyrofuelQuantBot/3.0"}
        now_ms = int(time.time() * 1000)
        ok = False

        for host in self.rest_hosts:
            try:
                if (now_ms - self.last_funding_info_sync_ms) > 3_600_000 or not self.funding_intervals:
                    r_info = requests.get(f"{host}/fapi/v1/fundingInfo", headers=headers, timeout=timeout)
                    if r_info.status_code == 200 and isinstance(r_info.json(), list):
                        self.ingest_funding_info(r_info.json())
                        self.last_funding_info_sync_ms = now_ms

                r_prem = requests.get(f"{host}/fapi/v1/premiumIndex", headers=headers, timeout=timeout)
                if r_prem.status_code == 200:
                    self.ingest_bulk_premium_index(r_prem.json())
                    self.last_premium_sync_ms = now_ms
                    ok = True
                    break
            except Exception as exc:
                logger.debug("MacroFundingShield REST sync fallback on %s: %s", host, exc)
                continue
        return ok

    def evaluate_symbol_shield(
        self,
        symbol: str,
        now_ms: int,
        direction: Optional[str] = None,
        override_funding_rate: Optional[float] = None,
        override_next_funding_ms: Optional[int] = None,
        extra_macro_events: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate both the Dynamic Funding Boundary Guard (2h/4h/8h) and the US Macro / CME Open
        Shock Shield for `symbol` at `now_ms`.
        """
        sym_u = symbol.upper()
        interval_hours = self.funding_intervals.get(sym_u, 8)
        prem = self.premium_index_map.get(sym_u, {})

        funding_rate = (
            float(override_funding_rate)
            if override_funding_rate is not None
            else float(prem.get("last_funding_rate", 0.0))
        )
        raw_next_ms = (
            int(override_next_funding_ms)
            if override_next_funding_ms is not None
            else int(prem.get("next_funding_time", 0))
        )
        next_funding_ms = compute_next_dynamic_funding_ms(
            now_ms=int(now_ms),
            interval_hours=interval_hours,
            explicit_next_funding_ms=raw_next_ms if raw_next_ms > 0 else None,
        )

        minutes_to_funding = max(0.0, (float(next_funding_ms) - float(now_ms)) / 60_000.0)
        in_funding_window = 0.0 <= minutes_to_funding <= self.funding_guard_window_min

        dir_u = (direction or "").upper()
        if dir_u == "LONG":
            pays_high_funding = funding_rate >= self.funding_rate_threshold
        elif dir_u == "SHORT":
            pays_high_funding = funding_rate <= -self.funding_rate_threshold
        else:
            pays_high_funding = abs(funding_rate) >= self.funding_rate_threshold

        funding_boundary_block = bool(in_funding_window and pays_high_funding)

        all_events = list(self.scheduled_macro_events)
        if extra_macro_events:
            all_events.extend(extra_macro_events)

        macro_res = check_macro_and_cme_shield(
            now_ms=int(now_ms),
            scheduled_events=all_events,
            pre_event_block_min=self.pre_macro_block_min,
            post_event_block_min=self.post_macro_block_min,
        )

        block_new_entry = bool(funding_boundary_block or macro_res["block_new_entries"])
        if macro_res["block_new_entries"]:
            block_reason = f"MACRO_SHIELD_{macro_res['active_event']}"
        elif funding_boundary_block:
            block_reason = f"FUNDING_BOUNDARY_{interval_hours}H_GUARD"
        else:
            block_reason = "NONE"

        return {
            "symbol": sym_u,
            "funding_interval_hours": int(interval_hours),
            "funding_rate": float(funding_rate),
            "next_funding_time_ms": int(next_funding_ms),
            "minutes_to_funding": float(minutes_to_funding),
            "funding_boundary_block": funding_boundary_block,
            "macro_shield_active": bool(macro_res["shield_active"]),
            "active_macro_event": macro_res["active_event"],
            "minutes_to_macro_event": float(macro_res["minutes_to_event"]),
            "tighten_existing_sl_to_be": bool(macro_res["tighten_existing_sl_to_be"]),
            "block_new_entries": block_new_entry,
            "block_reason": block_reason,
        }
