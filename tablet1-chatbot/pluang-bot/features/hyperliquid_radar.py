"""
Pilar 26 (T3.13) — Hyperliquid On-Chain HLP Vault (`0xdfc24b077bc1425ad1dea75bcb6f8158e10df303`)
& Whale Liquidation Spillover Radar.

Mechanism (Section 13.2):
  1. Queries `POST https://api.hyperliquid.xyz/info` with
     `{"type": "clearinghouseState", "user": "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"}`.
  2. Tracks 30-second changes in HLP Vault Net Notional Position Delta Pos_{HLP, c} across
     c in {BTC, ETH, SOL, XRP, DOGE, SUI, ADA}.
  3. Signal Rules:
     - When Delta Pos_{HLP, c} spikes strongly positive (Z_{Delta HLP} > +3.0), HLP just absorbed
       a massive whale Long liquidation and is hedging/selling delta on Binance -> wait for spillover.
     - Once Delta Pos_{HLP, c} begins reverting back toward neutral (< 0 after a Z > +3.0 absorption
       within the last 1-3 minutes), hedging pressure is finished -> triggers
       `sniper_bottom_confirmed = True` for `S3_LIQ_CASCADE_FADE` Long!
"""

from __future__ import annotations

import collections
import logging
import time
from typing import Any, Deque, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import requests

logger = logging.getLogger(__name__)

HLP_VAULT_ADDRESS: str = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
HYPERLIQUID_INFO_URL: str = "https://api.hyperliquid.xyz/info"


def _normalize_coin_name(symbol_or_coin: str) -> str:
    s = str(symbol_or_coin).upper().strip()
    if s.endswith("USDT"):
        return s[:-4]
    if s.endswith("-USD") or s.endswith("-PERP"):
        return s.split("-", 1)[0]
    return s


def parse_hlp_clearinghouse_state(raw_payload: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """
    Parse Hyperliquid `clearinghouseState` JSON into a per-coin dictionary:
        {
          "BTC": {
            "szi": float,             # signed base size (+ for long, - for short)
            "entry_px": float,
            "abs_notional_usd": float,
            "signed_notional_usd": float,
            "unrealized_pnl": float,
          }, ...
        }
    """
    if not raw_payload or not isinstance(raw_payload, dict):
        return {}

    asset_positions = raw_payload.get("assetPositions", [])
    if not isinstance(asset_positions, list):
        return {}

    out: Dict[str, Dict[str, float]] = {}
    for item in asset_positions:
        if not isinstance(item, dict):
            continue
        pos = item.get("position", item)
        if not isinstance(pos, dict):
            continue
        coin = _normalize_coin_name(pos.get("coin", ""))
        if not coin:
            continue
        szi = float(pos.get("szi", 0.0))
        entry_px = float(pos.get("entryPx", 0.0) or 0.0)
        pos_val = abs(float(pos.get("positionValue", abs(szi) * entry_px) or 0.0))
        sign = 1.0 if szi > 0 else (-1.0 if szi < 0 else 0.0)
        signed_notional = sign * pos_val
        upnl = float(pos.get("unrealizedPnl", 0.0) or 0.0)

        out[coin] = {
            "szi": float(szi),
            "entry_px": float(entry_px),
            "abs_notional_usd": float(pos_val),
            "signed_notional_usd": float(signed_notional),
            "unrealized_pnl": float(upnl),
        }
    return out


def evaluate_hlp_spillover_series(
    signed_notional_series: Sequence[float],
    coin: str = "BTC",
    recent_spike_bars: int = 6,
) -> Dict[str, Any]:
    """
    Evaluate a time series of 30-second HLP Vault signed notional positions `Pos_{HLP, c}(t)`
    for a target coin `c`.

    Detects:
      1. `HLP_ABSORBING_LONG_LIQ_HEDGING_ACTIVE`: Current step Delta Pos_{HLP} has Z > +3.0
         (HLP just took over liquidated whale Longs and is actively selling on Binance to hedge).
      2. `HLP_SPILLOVER_EXHAUSTED_BOTTOM_CONFIRMED`: Within the last 1-3 minutes (`recent_spike_bars`),
         Z_{Delta HLP} spiked > +3.0, and now Delta Pos_{HLP} < 0 (inventory reverting toward neutral).
      3. Symmetric states for Short whale liquidation absorption (Z < -3.0).
    """
    c_name = _normalize_coin_name(coin)
    arr = np.asarray(signed_notional_series, dtype=float)
    n = len(arr)
    if n < 3:
        curr_pos = float(arr[-1]) if n > 0 else 0.0
        return {
            "status": "INSUFFICIENT_HISTORY",
            "coin": c_name,
            "current_signed_notional_usd": curr_pos,
            "delta_pos_usd": 0.0,
            "z_delta_hlp": 0.0,
            "max_z_recent": 0.0,
            "min_z_recent": 0.0,
            "state": "NEUTRAL",
            "spillover_selling_active": False,
            "spillover_buying_active": False,
            "sniper_bottom_confirmed": False,
            "sniper_top_confirmed": False,
        }

    deltas = np.diff(arr)
    curr_delta = float(deltas[-1])
    curr_pos = float(arr[-1])

    # Compute z-score of each delta step against baseline volatility of deltas
    # Use robust median/MAD + std of non-extreme steps so a single massive whale liquidation spike
    # isn't diluted by its own variance in short test windows.
    med = float(np.median(deltas))
    mad = float(np.median(np.abs(deltas - med)))
    robust_sigma = 1.4826 * mad
    if robust_sigma < 1e-6:
        # Fallback to standard deviation of deltas excluding the largest spike
        if len(deltas) >= 4:
            sorted_abs = np.sort(np.abs(deltas - med))
            base_std = float(np.std(sorted_abs[:-1]))
        else:
            base_std = float(np.std(deltas))
        sigma = max(base_std, 1e-6)
    else:
        sigma = robust_sigma

    z_series = (deltas - med) / sigma
    curr_z = float(z_series[-1])

    lookback = max(2, min(len(z_series), int(recent_spike_bars)))
    recent_z = z_series[-lookback:]
    prior_recent_z = recent_z[:-1] if len(recent_z) > 1 else recent_z

    max_z_recent = float(np.max(recent_z))
    min_z_recent = float(np.min(recent_z))
    max_z_prior = float(np.max(prior_recent_z))
    min_z_prior = float(np.min(prior_recent_z))
    prev_pos = float(arr[-2])

    # Bottom confirmation: prior 1-3m had a massive long-liquidation absorption spike (Z > +3.0),
    # and now HLP is unwinding that positive long inventory back toward neutral (curr_delta < 0 while prev_pos > 0)
    sniper_bottom_confirmed = bool(
        max_z_prior > 3.0
        and curr_delta < 0.0
        and prev_pos > 0.0
        and curr_pos >= 0.0
    )

    # Top confirmation: prior 1-3m had a massive short-liquidation absorption spike (Z < -3.0),
    # and now HLP is unwinding that negative short inventory back toward neutral (curr_delta > 0 while prev_pos < 0)
    sniper_top_confirmed = bool(
        min_z_prior < -3.0
        and curr_delta > 0.0
        and prev_pos < 0.0
        and curr_pos <= 0.0
    )

    # Active spillover hedging right now (only when not unwinding a prior opposing absorption spike)
    spillover_selling_active = bool(curr_z > 3.0 and not sniper_top_confirmed)
    spillover_buying_active = bool(curr_z < -3.0 and not sniper_bottom_confirmed)

    if sniper_bottom_confirmed:
        state = "HLP_SPILLOVER_EXHAUSTED_BOTTOM_CONFIRMED"
    elif sniper_top_confirmed:
        state = "HLP_SPILLOVER_EXHAUSTED_TOP_CONFIRMED"
    elif spillover_selling_active:
        state = "HLP_ABSORBING_LONG_LIQ_HEDGING_ACTIVE"
    elif spillover_buying_active:
        state = "HLP_ABSORBING_SHORT_LIQ_HEDGING_ACTIVE"
    else:
        state = "NEUTRAL"

    return {
        "status": "OK",
        "coin": c_name,
        "current_signed_notional_usd": float(curr_pos),
        "delta_pos_usd": float(curr_delta),
        "z_delta_hlp": float(curr_z),
        "max_z_recent": float(max_z_recent),
        "min_z_recent": float(min_z_recent),
        "state": state,
        "spillover_selling_active": spillover_selling_active,
        "spillover_buying_active": spillover_buying_active,
        "sniper_bottom_confirmed": sniper_bottom_confirmed,
        "sniper_top_confirmed": sniper_top_confirmed,
    }


class HLPSpilloverTracker:
    """
    Stateful tracker polling or receiving Hyperliquid HLP Vault `clearinghouseState`
    snapshots every 30 seconds across major coins (`BTC`, `ETH`, `SOL`, `XRP`, `DOGE`, `SUI`).
    """

    def __init__(self, vault_address: str = HLP_VAULT_ADDRESS, history_len: int = 120) -> None:
        self.vault_address = vault_address
        self.history_len = max(10, int(history_len))
        self._notional_history: Dict[str, Deque[float]] = collections.defaultdict(
            lambda: collections.deque(maxlen=self.history_len)
        )
        self._latest_parsed: Dict[str, Dict[str, float]] = {}
        self.last_update_ms: int = 0

    def ingest_clearinghouse_state(
        self,
        raw_payload: Dict[str, Any],
        now_ms: Optional[int] = None,
    ) -> Dict[str, Dict[str, float]]:
        parsed = parse_hlp_clearinghouse_state(raw_payload)
        self._latest_parsed = parsed
        for coin, info in parsed.items():
            self._notional_history[coin].append(float(info["signed_notional_usd"]))
        self.last_update_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        return parsed

    def get_coin_signal(self, symbol_or_coin: str) -> Dict[str, Any]:
        coin = _normalize_coin_name(symbol_or_coin)
        hist = list(self._notional_history.get(coin, ()))
        if not hist:
            return {
                "status": "OFFLINE_FALLBACK",
                "coin": coin,
                "current_signed_notional_usd": 0.0,
                "delta_pos_usd": 0.0,
                "z_delta_hlp": 0.0,
                "max_z_recent": 0.0,
                "min_z_recent": 0.0,
                "state": "NEUTRAL_OFFLINE",
                "spillover_selling_active": False,
                "spillover_buying_active": False,
                "sniper_bottom_confirmed": False,
                "sniper_top_confirmed": False,
            }
        return evaluate_hlp_spillover_series(hist, coin=coin)


def fetch_hlp_vault_state(
    vault_address: str = HLP_VAULT_ADDRESS,
    timeout: float = 2.5,
) -> Dict[str, Any]:
    """
    Query Hyperliquid On-Chain Info API (`POST https://api.hyperliquid.xyz/info`) for HLP Vault
    `clearinghouseState`. Never raises on network failure — returns safe offline fallback.
    """
    try:
        resp = requests.post(
            HYPERLIQUID_INFO_URL,
            json={"type": "clearinghouseState", "user": vault_address},
            headers={"Content-Type": "application/json", "User-Agent": "PyrofuelQuantBot/3.0"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            raw = resp.json()
            positions = parse_hlp_clearinghouse_state(raw)
            return {
                "status": "OK",
                "vault_address": vault_address,
                "positions": positions,
                "raw": raw,
            }
    except Exception as exc:
        logger.debug("Hyperliquid HLP Vault fetch fallback: %s", exc)

    return {
        "status": "OFFLINE_FALLBACK",
        "vault_address": vault_address,
        "positions": {},
        "raw": None,
    }
