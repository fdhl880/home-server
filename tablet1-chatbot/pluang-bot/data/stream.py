"""
Pilar 1 (T3.1) — Real-Time Binance Futures Multiplexed WebSocket Streamer & Closed-Bar Integrity.

Key Invariants:
1. Strict Separation of Closed Candles vs. Live Forming Tick:
   - Historical array `closed_klines` ONLY contains bars where `is_closed == True`
     (`k['x'] == True` on WebSocket or `close_time <= server_time_ms` on REST).
   - Unclosed forming candle is stored separately in `forming_bar` with time-normalized
     volume pace: V_hat_pace = V_forming / max(elapsed_ratio, 0.05).
2. Multiplexed Combined WebSocket (`wss://fstream.binance.com/stream?streams=...`):
   - Subscribes to `<symbol>@kline_1m`, `<symbol>@kline_15m`, `<symbol>@kline_1h`,
     `<symbol>@aggTrade`, `<symbol>@depth20@100ms`, `<symbol>@forceOrder`,
     and `<symbol>@markPrice@1s`.
3. Lock-Free / Thread-Safe Ring Buffers (`collections.deque`):
   - `closed_klines`: `1m`, `15m`, `1h` closed bars only.
   - `agg_trades_window`: 1-second aggregated buckets `(ts_sec, buy_dollar_vol, sell_dollar_vol, trade_count)`
     for the last 60 minutes (`maxlen=3600`, < 20 MB RAM).
   - `depth20_snapshot`: latest 20-level bid/ask book + per-second OFI history (`maxlen=3600`).
   - `force_orders_window`: real-time liquidation events over the last 24 hours.
   - `mark_price_state`: `mark_price`, `index_price`, `funding_rate`, `next_funding_time`.
4. Auto-Reconnect with Exponential Backoff & Graceful Offline REST Fallback.
"""

from __future__ import annotations

import collections
import json
import logging
import math
import random
import threading
import time
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

INTERVAL_DURATION_MS: Dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

DEFAULT_FAPI_REST_HOSTS: List[str] = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi4.binance.com",
]

DEFAULT_WS_BASE_URLS: List[str] = [
    "wss://fstream.binance.com/stream",
    "wss://fstream1.binance.com/stream",
]


def compute_forming_volume_pace(
    forming_volume: float,
    open_time_ms: int,
    now_ms: int,
    bar_duration_ms: int = 900_000,
) -> Tuple[float, float]:
    """
    Compute elapsed bar ratio and time-normalized volume pace for an unclosed candle:
        elapsed_ratio = clamp((now_ms - open_time_ms) / bar_duration_ms, 0.0, 1.0)
        V_hat_pace = V_forming / max(elapsed_ratio, 0.05)

    Returns (elapsed_ratio, paced_volume).
    """
    if bar_duration_ms <= 0:
        bar_duration_ms = 900_000
    raw_ratio = (float(now_ms) - float(open_time_ms)) / float(bar_duration_ms)
    elapsed_ratio = max(0.0, min(1.0, raw_ratio))
    eff_ratio = max(elapsed_ratio, 0.05)
    paced_vol = max(0.0, float(forming_volume)) / eff_ratio
    return elapsed_ratio, paced_vol


def _normalize_kline_item(
    raw: Any,
    server_time_ms: int,
    bar_duration_ms: int = 900_000,
) -> Dict[str, Any]:
    """
    Convert either a Binance REST kline list `[open_time, open, high, low, close, vol, close_time, ...]`
    or a WebSocket `k` dict into a standardized kline dictionary with `is_closed`.
    """
    if isinstance(raw, dict):
        # Could be WebSocket kline payload `{"t": ..., "T": ..., "o": ..., "x": ...}`
        # or already normalized dict
        if "t" in raw and "T" in raw and ("o" in raw or "open" in raw):
            open_time = int(raw.get("t", 0))
            close_time = int(raw.get("T", open_time + bar_duration_ms - 1))
            open_px = float(raw.get("o", raw.get("open", 0.0)))
            high_px = float(raw.get("h", raw.get("high", 0.0)))
            low_px = float(raw.get("l", raw.get("low", 0.0)))
            close_px = float(raw.get("c", raw.get("close", 0.0)))
            vol = float(raw.get("v", raw.get("volume", 0.0)))
            quote_vol = float(raw.get("q", raw.get("quote_volume", vol * close_px)))
            trades = int(raw.get("n", raw.get("trades", 0)))
            taker_buy_base = float(raw.get("V", raw.get("taker_buy_base", vol * 0.5)))
            taker_buy_quote = float(raw.get("Q", raw.get("taker_buy_quote", quote_vol * 0.5)))
            if "x" in raw:
                is_closed = bool(raw["x"])
            else:
                is_closed = bool(close_time <= server_time_ms)
        else:
            open_time = int(raw.get("open_time", 0))
            close_time = int(raw.get("close_time", open_time + bar_duration_ms - 1))
            open_px = float(raw.get("open", 0.0))
            high_px = float(raw.get("high", 0.0))
            low_px = float(raw.get("low", 0.0))
            close_px = float(raw.get("close", 0.0))
            vol = float(raw.get("volume", 0.0))
            quote_vol = float(raw.get("quote_volume", vol * close_px))
            trades = int(raw.get("trades", 0))
            taker_buy_base = float(raw.get("taker_buy_base", vol * 0.5))
            taker_buy_quote = float(raw.get("taker_buy_quote", quote_vol * 0.5))
            if "is_closed" in raw:
                is_closed = bool(raw["is_closed"])
            elif "x" in raw:
                is_closed = bool(raw["x"])
            else:
                is_closed = bool(close_time <= server_time_ms)
    elif isinstance(raw, (list, tuple)) and len(raw) >= 7:
        open_time = int(raw[0])
        open_px = float(raw[1])
        high_px = float(raw[2])
        low_px = float(raw[3])
        close_px = float(raw[4])
        vol = float(raw[5])
        close_time = int(raw[6])
        quote_vol = float(raw[7]) if len(raw) > 7 else vol * close_px
        trades = int(raw[8]) if len(raw) > 8 else 0
        taker_buy_base = float(raw[9]) if len(raw) > 9 else vol * 0.5
        taker_buy_quote = float(raw[10]) if len(raw) > 10 else quote_vol * 0.5
        is_closed = bool(close_time <= server_time_ms)
    else:
        raise ValueError(f"Unsupported kline format: {type(raw)}")

    return {
        "open_time": open_time,
        "open": open_px,
        "high": high_px,
        "low": low_px,
        "close": close_px,
        "volume": vol,
        "close_time": close_time,
        "quote_volume": quote_vol,
        "trades": trades,
        "taker_buy_base": taker_buy_base,
        "taker_buy_quote": taker_buy_quote,
        "is_closed": is_closed,
    }


def separate_closed_and_forming_klines(
    raw_klines: Iterable[Any],
    server_time_ms: Optional[int] = None,
    interval: str = "15m",
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Strictly separate a sequence of klines into:
      1. `closed_klines`: ONLY bars where `close_time <= server_time_ms` (or `is_closed == True`).
      2. `forming_bar`: The unclosed live bar (if present), enriched with `elapsed_ratio`
         and `paced_volume = V_forming / max(elapsed_ratio, 0.05)`.

    Guarantees 0% intra-bar lookahead contamination from `data[-1]`.
    """
    if server_time_ms is None:
        server_time_ms = int(time.time() * 1000)
    bar_duration_ms = INTERVAL_DURATION_MS.get(interval, 900_000)

    closed_klines: List[Dict[str, Any]] = []
    forming_bar: Optional[Dict[str, Any]] = None

    for item in raw_klines:
        norm = _normalize_kline_item(item, server_time_ms=server_time_ms, bar_duration_ms=bar_duration_ms)
        if norm["is_closed"]:
            closed_klines.append(norm)
        else:
            elapsed_ratio, paced_vol = compute_forming_volume_pace(
                forming_volume=norm["volume"],
                open_time_ms=norm["open_time"],
                now_ms=server_time_ms,
                bar_duration_ms=bar_duration_ms,
            )
            _, paced_quote_vol = compute_forming_volume_pace(
                forming_volume=norm["quote_volume"],
                open_time_ms=norm["open_time"],
                now_ms=server_time_ms,
                bar_duration_ms=bar_duration_ms,
            )
            forming_bar = {
                **norm,
                "last_price": norm["close"],
                "intrabar_high": norm["high"],
                "intrabar_low": norm["low"],
                "elapsed_ratio": elapsed_ratio,
                "paced_volume": paced_vol,
                "paced_quote_volume": paced_quote_vol,
            }

    return closed_klines, forming_bar


def _quick_multilevel_ofi(
    prev_bids: List[List[float]],
    prev_asks: List[List[float]],
    curr_bids: List[List[float]],
    curr_asks: List[List[float]],
    decay_lambda: float = 0.25,
) -> Tuple[float, float]:
    """
    Fast helper for stream-level OFI and OBI on 20-level depth snapshots.
    """
    levels = min(20, len(curr_bids), len(curr_asks))
    if levels == 0:
        return 0.0, 0.0

    ofi_total = 0.0
    weighted_bid = 0.0
    weighted_ask = 0.0

    has_prev = len(prev_bids) >= levels and len(prev_asks) >= levels
    for k in range(levels):
        w_k = math.exp(-decay_lambda * k)
        pb_curr, qb_curr = float(curr_bids[k][0]), float(curr_bids[k][1])
        pa_curr, qa_curr = float(curr_asks[k][0]), float(curr_asks[k][1])
        weighted_bid += w_k * qb_curr
        weighted_ask += w_k * qa_curr

        if has_prev:
            pb_prev, qb_prev = float(prev_bids[k][0]), float(prev_bids[k][1])
            pa_prev, qa_prev = float(prev_asks[k][0]), float(prev_asks[k][1])

            delta_b = (qb_curr if pb_curr >= pb_prev else 0.0) - (qb_prev if pb_curr <= pb_prev else 0.0)
            delta_a = (qa_curr if pa_curr <= pa_prev else 0.0) - (qa_prev if pa_curr >= pa_prev else 0.0)
            ofi_total += w_k * (delta_b - delta_a)

    denom = weighted_bid + weighted_ask
    obi = (weighted_bid - weighted_ask) / denom if denom > 1e-12 else 0.0
    return ofi_total, obi


class SymbolStreamBuffer:
    """
    Per-symbol lock-free deque buffers for closed klines, forming bars,
    1-second aggTrade buckets, depth20 + OFI history, 24h forceOrder events,
    and real-time markPrice state.
    """

    def __init__(
        self,
        symbol: str,
        kline_maxlen: int = 500,
        agg_trade_seconds: int = 3600,
        ofi_history_seconds: int = 3600,
        force_order_maxlen: int = 5000,
    ) -> None:
        self.symbol = symbol.upper()
        self.closed_klines: Dict[str, Deque[Dict[str, Any]]] = {
            "1m": collections.deque(maxlen=kline_maxlen),
            "15m": collections.deque(maxlen=kline_maxlen),
            "1h": collections.deque(maxlen=kline_maxlen),
        }
        self.forming_bar: Dict[str, Optional[Dict[str, Any]]] = {
            "1m": None,
            "15m": None,
            "1h": None,
        }
        # 1-second buckets: (ts_sec, buy_dollar_vol, sell_dollar_vol, trade_count)
        self.agg_trades_window: Deque[Dict[str, Any]] = collections.deque(maxlen=agg_trade_seconds)
        self.depth20_snapshot: Dict[str, Any] = {
            "ts_ms": 0,
            "bids": [],
            "asks": [],
            "obi_20": 0.0,
            "ofi_last": 0.0,
        }
        self.prev_depth20_snapshot: Dict[str, Any] = {
            "ts_ms": 0,
            "bids": [],
            "asks": [],
        }
        self.ofi_history: Deque[Dict[str, Any]] = collections.deque(maxlen=ofi_history_seconds)
        self.force_orders_window: Deque[Dict[str, Any]] = collections.deque(maxlen=force_order_maxlen)
        self.mark_price_state: Dict[str, Any] = {
            "mark_price": 0.0,
            "index_price": 0.0,
            "funding_rate": 0.0,
            "next_funding_time": 0,
            "ts_ms": 0,
        }
        self.last_update_ms: int = 0


class BinanceFuturesStreamManager:
    """
    Multiplexed WebSocket Stream Manager for Binance USD-M Perpetual Futures (`T3.1`).

    Streams per symbol:
      - `<symbol>@kline_1m`, `<symbol>@kline_15m`, `<symbol>@kline_1h`
      - `<symbol>@aggTrade`
      - `<symbol>@depth20@100ms`
      - `<symbol>@forceOrder`
      - `<symbol>@markPrice@1s`

    Features:
      - Stores ONLY closed bars (`k['x'] == True`) in `closed_klines` deque.
      - Maintains `forming_bar` separately with time-paced volume normalization.
      - Maintains 1-second `aggTrade` ring buffer for 60 minutes (< 20 MB RAM).
      - Maintains 20-level depth snapshot + per-second OFI ring buffer.
      - Maintains 24-hour `@forceOrder` liquidation ring buffer.
      - Maintains real-time `@markPrice@1s` state.
      - Automatic exponential backoff reconnect (`1s -> 2s -> 4s -> ... -> 30s`)
        with graceful fallback to REST polling when offline.
    """

    MAX_ELIGIBLE_SYMBOLS = 12

    def __init__(
        self,
        symbols: Optional[Iterable[str]] = None,
        intervals: Tuple[str, ...] = ("1m", "15m", "1h"),
        rest_hosts: Optional[List[str]] = None,
        ws_base_urls: Optional[List[str]] = None,
        kline_maxlen: int = 500,
        agg_trade_seconds: int = 3600,
        force_order_retention_sec: int = 86_400,
    ) -> None:
        self._lock = threading.RLock()
        self.intervals = tuple(intervals)
        self.rest_hosts = list(rest_hosts or DEFAULT_FAPI_REST_HOSTS)
        self.ws_base_urls = list(ws_base_urls or DEFAULT_WS_BASE_URLS)
        self.kline_maxlen = kline_maxlen
        self.agg_trade_seconds = agg_trade_seconds
        self.force_order_retention_ms = int(force_order_retention_sec * 1000)

        self._buffers: Dict[str, SymbolStreamBuffer] = {}
        self._symbols: List[str] = []
        if symbols:
            self.set_symbols(symbols)

        self._callbacks: Dict[str, List[Callable[[str, Dict[str, Any]], None]]] = collections.defaultdict(list)
        self._running = False
        self._connected = False
        self._offline_fallback_mode = False
        self._reconnect_attempts = 0
        self._last_msg_ts_ms = 0
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_app: Any = None
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "PyrofuelQuantBot/3.0"})

    # ------------------------------------------------------------------
    # Symbol & Buffer Management
    # ------------------------------------------------------------------
    def _ensure_buffer(self, symbol: str) -> SymbolStreamBuffer:
        sym = symbol.upper()
        with self._lock:
            buf = self._buffers.get(sym)
            if buf is None:
                buf = SymbolStreamBuffer(
                    symbol=sym,
                    kline_maxlen=self.kline_maxlen,
                    agg_trade_seconds=self.agg_trade_seconds,
                    ofi_history_seconds=self.agg_trade_seconds,
                )
                self._buffers[sym] = buf
            return buf

    def set_symbols(self, symbols: Iterable[str], active_position_symbols: Iterable[str] = ()) -> List[str]:
        """
        Configure up to 10 top eligible symbols + any active position symbols.
        """
        active_upper = [s.upper() for s in active_position_symbols if s]
        eligible_upper = [s.upper() for s in symbols if s and s.upper() not in active_upper]
        combined = active_upper + eligible_upper[: max(0, self.MAX_ELIGIBLE_SYMBOLS - len(active_upper))]
        with self._lock:
            self._symbols = combined
            for sym in combined:
                self._ensure_buffer(sym)
        return list(self._symbols)

    def build_combined_stream_url(self, base_url: Optional[str] = None) -> str:
        """
        Construct the Binance Futures multiplexed WebSocket URL:
            wss://fstream.binance.com/stream?streams=<s1>@kline_1m/<s1>@kline_15m/...
        """
        root = (base_url or self.ws_base_urls[0]).rstrip("/")
        stream_names: List[str] = []
        with self._lock:
            syms = list(self._symbols)
        for sym in syms:
            lower = sym.lower()
            for iv in self.intervals:
                stream_names.append(f"{lower}@kline_{iv}")
            stream_names.append(f"{lower}@aggTrade")
            stream_names.append(f"{lower}@depth20@100ms")
            stream_names.append(f"{lower}@forceOrder")
            stream_names.append(f"{lower}@markPrice@1s")
        query = "/".join(stream_names)
        return f"{root}?streams={query}" if query else root

    def register_callback(self, event_type: str, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        Register an event listener for `kline_closed`, `force_order`, `depth_update`,
        `agg_trade`, or `mark_price`.
        """
        self._callbacks[event_type].append(callback)

    def _emit(self, event_type: str, symbol: str, payload: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.get(event_type, ())):
            try:
                cb(symbol, payload)
            except Exception as exc:
                logger.debug("Stream callback error (%s, %s): %s", event_type, symbol, exc)

    # ------------------------------------------------------------------
    # Event Ingestion (WebSocket & Unit-Testable Deterministic Entrypoints)
    # ------------------------------------------------------------------
    def process_ws_message(self, raw_msg: Any, server_time_ms: Optional[int] = None) -> Optional[str]:
        """
        Parse and route a raw WebSocket JSON message (both combined `{"stream": ..., "data": ...}`
        and direct payload formats).
        Returns the handled event type (`"kline"`, `"aggTrade"`, `"depthUpdate"`, `"forceOrder"`, `"markPriceUpdate"`).
        """
        if isinstance(raw_msg, (bytes, bytearray)):
            raw_msg = raw_msg.decode("utf-8", errors="replace")
        if isinstance(raw_msg, str):
            try:
                msg = json.loads(raw_msg)
            except json.JSONDecodeError:
                return None
        elif isinstance(raw_msg, dict):
            msg = raw_msg
        else:
            return None

        stream_name = str(msg.get("stream", ""))
        data = msg.get("data", msg)
        if not isinstance(data, dict):
            return None

        now_ms = int(server_time_ms if server_time_ms is not None else data.get("E", int(time.time() * 1000)))
        self._last_msg_ts_ms = max(self._last_msg_ts_ms, now_ms)

        event_type = str(data.get("e", ""))
        symbol = str(data.get("s", "")).upper()
        if not symbol and "@" in stream_name:
            symbol = stream_name.split("@", 1)[0].upper()

        if event_type == "kline" or "k" in data:
            k_obj = data.get("k", data)
            interval = str(k_obj.get("i", "15m"))
            sym = str(k_obj.get("s", symbol)).upper()
            self.ingest_kline_event(sym, interval, k_obj, server_time_ms=now_ms)
            return "kline"

        if event_type == "aggTrade" or "@aggTrade" in stream_name:
            self.ingest_agg_trade(symbol, data)
            return "aggTrade"

        if event_type == "depthUpdate" or "@depth" in stream_name or ("b" in data and "a" in data) or ("bids" in data and "asks" in data):
            self.ingest_depth20(symbol, data, now_ms=now_ms)
            return "depthUpdate"

        if event_type == "forceOrder" or "@forceOrder" in stream_name or "o" in data:
            order_obj = data.get("o", data)
            sym = str(order_obj.get("s", symbol)).upper()
            self.ingest_force_order(sym, data, now_ms=now_ms)
            return "forceOrder"

        if event_type == "markPriceUpdate" or "@markPrice" in stream_name:
            self.ingest_mark_price(symbol, data, now_ms=now_ms)
            return "markPriceUpdate"

        return None

    def ingest_kline_event(
        self,
        symbol: str,
        interval: str,
        k_dict: Dict[str, Any],
        server_time_ms: Optional[int] = None,
    ) -> bool:
        """
        Process a WebSocket `kline` event.
        CRITICAL RULE (T3.1):
          - If `k['x'] == True` (closed bar): append to `closed_klines[interval]` (deduplicating
            by `open_time`) and clear `forming_bar[interval]`.
          - If `k['x'] == False` (forming bar): update ONLY `forming_bar[interval]` and NEVER
            append to `closed_klines[interval]`.
        Returns True if the bar was closed and added to `closed_klines`, False if forming.
        """
        if server_time_ms is None:
            server_time_ms = int(time.time() * 1000)
        bar_duration_ms = INTERVAL_DURATION_MS.get(interval, 900_000)
        norm = _normalize_kline_item(k_dict, server_time_ms=server_time_ms, bar_duration_ms=bar_duration_ms)

        buf = self._ensure_buffer(symbol)
        if interval not in buf.closed_klines:
            buf.closed_klines[interval] = collections.deque(maxlen=self.kline_maxlen)
            buf.forming_bar[interval] = None

        buf.last_update_ms = max(buf.last_update_ms, server_time_ms)

        if norm["is_closed"]:
            dq = buf.closed_klines[interval]
            if dq and dq[-1]["open_time"] == norm["open_time"]:
                dq[-1] = norm
            elif not dq or norm["open_time"] > dq[-1]["open_time"]:
                dq.append(norm)
            buf.forming_bar[interval] = None
            self._emit("kline_closed", buf.symbol, {"interval": interval, "kline": norm})
            return True
        else:
            elapsed_ratio, paced_vol = compute_forming_volume_pace(
                forming_volume=norm["volume"],
                open_time_ms=norm["open_time"],
                now_ms=server_time_ms,
                bar_duration_ms=bar_duration_ms,
            )
            _, paced_quote_vol = compute_forming_volume_pace(
                forming_volume=norm["quote_volume"],
                open_time_ms=norm["open_time"],
                now_ms=server_time_ms,
                bar_duration_ms=bar_duration_ms,
            )
            buf.forming_bar[interval] = {
                **norm,
                "last_price": norm["close"],
                "intrabar_high": norm["high"],
                "intrabar_low": norm["low"],
                "elapsed_ratio": elapsed_ratio,
                "paced_volume": paced_vol,
                "paced_quote_volume": paced_quote_vol,
            }
            return False

    def ingest_agg_trade(self, symbol: str, trade_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggregate `@aggTrade` events into 1-second ring buffer buckets:
            (ts_sec, buy_dollar_vol, sell_dollar_vol, trade_count)
        Note: `m = isBuyerMaker`:
            - `m == False` -> Taker BUY (`buy_dollar_vol += p * q`)
            - `m == True`  -> Taker SELL (`sell_dollar_vol += p * q`)
        """
        buf = self._ensure_buffer(symbol)
        price = float(trade_dict.get("p", trade_dict.get("price", 0.0)))
        qty = float(trade_dict.get("q", trade_dict.get("qty", 0.0)))
        ts_ms = int(trade_dict.get("T", trade_dict.get("E", int(time.time() * 1000))))
        is_buyer_maker = bool(trade_dict.get("m", False))
        dollar_vol = price * qty
        ts_sec = ts_ms // 1000

        dq = buf.agg_trades_window
        if dq and dq[-1]["ts_sec"] == ts_sec:
            bucket = dq[-1]
            if is_buyer_maker:
                bucket["sell_dollar_vol"] += dollar_vol
                bucket["sell_base_vol"] += qty
            else:
                bucket["buy_dollar_vol"] += dollar_vol
                bucket["buy_base_vol"] += qty
            bucket["trade_count"] += 1
            bucket["last_price"] = price
            total_base = bucket["buy_base_vol"] + bucket["sell_base_vol"]
            total_dollar = bucket["buy_dollar_vol"] + bucket["sell_dollar_vol"]
            bucket["vwap"] = total_dollar / total_base if total_base > 1e-12 else price
        else:
            bucket = {
                "ts_sec": ts_sec,
                "buy_dollar_vol": 0.0 if is_buyer_maker else dollar_vol,
                "sell_dollar_vol": dollar_vol if is_buyer_maker else 0.0,
                "buy_base_vol": 0.0 if is_buyer_maker else qty,
                "sell_base_vol": qty if is_buyer_maker else 0.0,
                "trade_count": 1,
                "last_price": price,
                "vwap": price,
            }
            dq.append(bucket)

        buf.last_update_ms = max(buf.last_update_ms, ts_ms)
        self._emit("agg_trade", buf.symbol, bucket)
        return bucket

    def ingest_depth20(
        self,
        symbol: str,
        depth_dict: Dict[str, Any],
        now_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Update 20-level order book snapshot (`@depth20@100ms`) and maintain
        per-second Order Flow Imbalance (`ofi_history`) ring buffer.
        """
        buf = self._ensure_buffer(symbol)
        raw_bids = depth_dict.get("b", depth_dict.get("bids", []))
        raw_asks = depth_dict.get("a", depth_dict.get("asks", []))
        ts_ms = int(now_ms if now_ms is not None else depth_dict.get("E", depth_dict.get("T", int(time.time() * 1000))))

        bids = [[float(level[0]), float(level[1])] for level in raw_bids[:20]]
        asks = [[float(level[0]), float(level[1])] for level in raw_asks[:20]]

        prev_bids = buf.depth20_snapshot.get("bids", [])
        prev_asks = buf.depth20_snapshot.get("asks", [])

        ofi_step, obi_20 = _quick_multilevel_ofi(prev_bids, prev_asks, bids, asks)

        buf.prev_depth20_snapshot = {
            "ts_ms": buf.depth20_snapshot.get("ts_ms", 0),
            "bids": prev_bids,
            "asks": prev_asks,
        }
        buf.depth20_snapshot = {
            "ts_ms": ts_ms,
            "bids": bids,
            "asks": asks,
            "obi_20": obi_20,
            "ofi_last": ofi_step,
        }

        ts_sec = ts_ms // 1000
        ofi_dq = buf.ofi_history
        if ofi_dq and ofi_dq[-1]["ts_sec"] == ts_sec:
            ofi_dq[-1]["ofi"] += ofi_step
            ofi_dq[-1]["obi_20"] = obi_20
            ofi_dq[-1]["updates"] += 1
        else:
            ofi_dq.append(
                {
                    "ts_sec": ts_sec,
                    "ofi": ofi_step,
                    "obi_20": obi_20,
                    "updates": 1,
                }
            )

        buf.last_update_ms = max(buf.last_update_ms, ts_ms)
        self._emit("depth_update", buf.symbol, buf.depth20_snapshot)
        return buf.depth20_snapshot

    def ingest_force_order(
        self,
        symbol: str,
        force_dict: Dict[str, Any],
        now_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Store real-time `@forceOrder` liquidation events and prune events older than 24 hours.
        Note:
          - `S == "SELL"` -> Long position was force-liquidated (`liq_side = "LONG_LIQ"`).
          - `S == "BUY"`  -> Short position was force-liquidated (`liq_side = "SHORT_LIQ"`).
        """
        buf = self._ensure_buffer(symbol)
        order_obj = force_dict.get("o", force_dict)
        side = str(order_obj.get("S", order_obj.get("side", "SELL"))).upper()
        price = float(order_obj.get("ap", order_obj.get("p", order_obj.get("price", 0.0))))
        if price <= 0.0:
            price = float(order_obj.get("p", 0.0))
        qty = float(order_obj.get("z", order_obj.get("q", order_obj.get("qty", 0.0))))
        if qty <= 0.0:
            qty = float(order_obj.get("q", 0.0))
        ts_ms = int(
            now_ms
            if now_ms is not None
            else order_obj.get("T", force_dict.get("E", int(time.time() * 1000)))
        )
        notional_usd = price * qty

        record = {
            "ts_ms": ts_ms,
            "symbol": buf.symbol,
            "side": side,
            "liq_type": "LONG_LIQ" if side == "SELL" else "SHORT_LIQ",
            "price": price,
            "qty": qty,
            "notional_usd": notional_usd,
        }
        dq = buf.force_orders_window
        dq.append(record)

        # Prune older than 24 hours
        cutoff_ms = ts_ms - self.force_order_retention_ms
        while dq and dq[0]["ts_ms"] < cutoff_ms:
            dq.popleft()

        buf.last_update_ms = max(buf.last_update_ms, ts_ms)
        self._emit("force_order", buf.symbol, record)
        return record

    def ingest_mark_price(
        self,
        symbol: str,
        mark_dict: Dict[str, Any],
        now_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Update real-time `@markPrice@1s` state:
          `mark_price`, `index_price`, `funding_rate`, `next_funding_time`.
        """
        buf = self._ensure_buffer(symbol)
        ts_ms = int(now_ms if now_ms is not None else mark_dict.get("E", int(time.time() * 1000)))
        state = {
            "mark_price": float(mark_dict.get("p", mark_dict.get("markPrice", 0.0))),
            "index_price": float(mark_dict.get("i", mark_dict.get("indexPrice", 0.0))),
            "funding_rate": float(mark_dict.get("r", mark_dict.get("lastFundingRate", 0.0))),
            "next_funding_time": int(mark_dict.get("T", mark_dict.get("nextFundingTime", 0))),
            "ts_ms": ts_ms,
        }
        buf.mark_price_state = state
        buf.last_update_ms = max(buf.last_update_ms, ts_ms)
        self._emit("mark_price", buf.symbol, state)
        return state

    # ------------------------------------------------------------------
    # Query & Snapshot Accessors
    # ------------------------------------------------------------------
    def get_closed_klines(self, symbol: str, interval: str = "15m") -> List[Dict[str, Any]]:
        """
        Return a copy of the closed-only klines list for `(symbol, interval)`.
        Guaranteed to NEVER include an unclosed forming bar.
        """
        buf = self._ensure_buffer(symbol)
        dq = buf.closed_klines.get(interval)
        if not dq:
            return []
        return list(dq)

    def get_closed_arrays(
        self,
        symbol: str,
        interval: str = "15m",
    ) -> Dict[str, List[float]]:
        """
        Return `opens, highs, lows, closes, volumes, quote_volumes, taker_buy_quotes`
        extracted strictly from `closed_klines`.
        """
        klines = self.get_closed_klines(symbol, interval=interval)
        return {
            "open_times": [k["open_time"] for k in klines],
            "opens": [k["open"] for k in klines],
            "highs": [k["high"] for k in klines],
            "lows": [k["low"] for k in klines],
            "closes": [k["close"] for k in klines],
            "volumes": [k["volume"] for k in klines],
            "quote_volumes": [k["quote_volume"] for k in klines],
            "taker_buy_quotes": [k["taker_buy_quote"] for k in klines],
        }

    def get_forming_bar(self, symbol: str, interval: str = "15m") -> Optional[Dict[str, Any]]:
        """
        Return the current live forming bar (if any), kept strictly separate from `closed_klines`.
        """
        buf = self._ensure_buffer(symbol)
        bar = buf.forming_bar.get(interval)
        return dict(bar) if bar is not None else None

    def get_agg_trade_buckets(self, symbol: str, lookback_sec: int = 3600, now_sec: Optional[int] = None) -> List[Dict[str, Any]]:
        buf = self._ensure_buffer(symbol)
        dq = buf.agg_trades_window
        if not dq:
            return []
        ref_sec = int(now_sec if now_sec is not None else dq[-1]["ts_sec"])
        cutoff = ref_sec - lookback_sec
        return [b for b in dq if b["ts_sec"] >= cutoff]

    def get_depth20_snapshot(self, symbol: str) -> Dict[str, Any]:
        buf = self._ensure_buffer(symbol)
        return dict(buf.depth20_snapshot)

    def get_force_orders(self, symbol: str, lookback_sec: int = 86_400, now_ms: Optional[int] = None) -> List[Dict[str, Any]]:
        buf = self._ensure_buffer(symbol)
        dq = buf.force_orders_window
        if not dq:
            return []
        ref_ms = int(now_ms if now_ms is not None else dq[-1]["ts_ms"])
        cutoff_ms = ref_ms - int(lookback_sec * 1000)
        return [e for e in dq if e["ts_ms"] >= cutoff_ms]

    def get_mark_price_state(self, symbol: str) -> Dict[str, Any]:
        buf = self._ensure_buffer(symbol)
        return dict(buf.mark_price_state)

    # ------------------------------------------------------------------
    # REST Seed & Offline Graceful Fallback
    # ------------------------------------------------------------------
    def ingest_rest_klines(
        self,
        symbol: str,
        interval: str,
        raw_klines: Iterable[Any],
        server_time_ms: Optional[int] = None,
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
        """
        Ingest a batch of REST `/fapi/v1/klines` into the symbol buffer, strictly
        separating closed bars from the trailing unclosed forming bar.
        Returns `(num_closed_ingested, forming_bar)`.
        """
        closed, forming = separate_closed_and_forming_klines(
            raw_klines=raw_klines,
            server_time_ms=server_time_ms,
            interval=interval,
        )
        buf = self._ensure_buffer(symbol)
        if interval not in buf.closed_klines:
            buf.closed_klines[interval] = collections.deque(maxlen=self.kline_maxlen)
        dq = buf.closed_klines[interval]
        dq.clear()
        for bar in closed:
            dq.append(bar)
        buf.forming_bar[interval] = forming
        return len(closed), forming

    def poll_rest_fallback(
        self,
        symbol: str,
        intervals: Tuple[str, ...] = ("15m", "1h"),
        limit: int = 200,
        timeout: Tuple[float, float] = (3.05, 6.0),
    ) -> bool:
        """
        Graceful fallback to REST polling when WebSocket is offline or reconnecting.
        """
        sym = symbol.upper()
        success = False
        for host in self.rest_hosts:
            try:
                # 1. Fetch server time or use local clock
                now_ms = int(time.time() * 1000)
                for iv in intervals:
                    resp = self._session.get(
                        f"{host}/fapi/v1/klines",
                        params={"symbol": sym, "interval": iv, "limit": limit},
                        timeout=timeout,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list):
                            self.ingest_rest_klines(sym, iv, data, server_time_ms=now_ms)
                            success = True

                # 2. Fetch depth20 snapshot
                resp_depth = self._session.get(
                    f"{host}/fapi/v1/depth",
                    params={"symbol": sym, "limit": 20},
                    timeout=timeout,
                )
                if resp_depth.status_code == 200:
                    d_json = resp_depth.json()
                    if isinstance(d_json, dict) and "bids" in d_json:
                        self.ingest_depth20(sym, d_json, now_ms=now_ms)

                # 3. Fetch premiumIndex (markPrice, indexPrice, fundingRate, nextFundingTime)
                resp_mark = self._session.get(
                    f"{host}/fapi/v1/premiumIndex",
                    params={"symbol": sym},
                    timeout=timeout,
                )
                if resp_mark.status_code == 200:
                    m_json = resp_mark.json()
                    if isinstance(m_json, dict) and "markPrice" in m_json:
                        self.ingest_mark_price(sym, m_json, now_ms=now_ms)

                if success:
                    break
            except Exception as exc:
                logger.debug("REST fallback host %s failed for %s: %s", host, sym, exc)
                continue
        return success

    # ------------------------------------------------------------------
    # Background WebSocket Lifecycle with Exponential Backoff
    # ------------------------------------------------------------------
    @staticmethod
    def compute_backoff_seconds(attempt: int, base: float = 1.0, cap: float = 30.0, jitter: bool = True) -> float:
        """
        Compute exponential backoff delay: `min(cap, base * 2^attempt)` with optional jitter.
        """
        raw = min(cap, base * (2.0 ** max(0, min(attempt, 10))))
        if not jitter:
            return raw
        return raw * (0.85 + 0.30 * random.random())

    def start(self, daemon: bool = True) -> None:
        """
        Start the background WebSocket streaming thread with auto-reconnect and REST fallback.
        """
        with self._lock:
            if self._running:
                return
            self._running = True
            self._ws_thread = threading.Thread(
                target=self._run_loop,
                name="BinanceFuturesStreamManager",
                daemon=daemon,
            )
            self._ws_thread.start()

    def stop(self) -> None:
        """
        Stop the background WebSocket streaming loop cleanly.
        """
        with self._lock:
            self._running = False
            self._connected = False
            ws_app = self._ws_app
        if ws_app is not None:
            try:
                ws_app.close()
            except Exception:
                pass

    def _run_loop(self) -> None:
        try:
            import websocket  # type: ignore
            has_ws_lib = True
        except ImportError:
            has_ws_lib = False
            self._offline_fallback_mode = True
            logger.info("websocket-client not installed; running StreamManager in REST fallback mode.")

        while self._running:
            if not has_ws_lib:
                with self._lock:
                    syms = list(self._symbols)
                for sym in syms:
                    if not self._running:
                        break
                    self.poll_rest_fallback(sym)
                time.sleep(5.0)
                continue

            url_idx = self._reconnect_attempts % len(self.ws_base_urls)
            ws_url = self.build_combined_stream_url(self.ws_base_urls[url_idx])

            def _on_open(_ws: Any) -> None:
                self._connected = True
                self._offline_fallback_mode = False
                self._reconnect_attempts = 0
                logger.info("Connected to Binance Futures multiplexed stream: %s", ws_url)

            def _on_message(_ws: Any, message: str) -> None:
                self.process_ws_message(message)

            def _on_error(_ws: Any, error: Any) -> None:
                logger.debug("Binance WS error: %s", error)

            def _on_close(_ws: Any, _code: Any, _msg: Any) -> None:
                self._connected = False

            try:
                self._ws_app = websocket.WebSocketApp(
                    ws_url,
                    on_open=_on_open,
                    on_message=_on_message,
                    on_error=_on_error,
                    on_close=_on_close,
                )
                self._ws_app.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as exc:
                logger.debug("WebSocket run_forever exception: %s", exc)
            finally:
                self._connected = False

            if not self._running:
                break

            # Graceful fallback to REST while disconnected
            self._offline_fallback_mode = True
            with self._lock:
                syms = list(self._symbols)
            for sym in syms[:3]:
                self.poll_rest_fallback(sym)

            delay = self.compute_backoff_seconds(self._reconnect_attempts)
            self._reconnect_attempts += 1
            time.sleep(delay)

    def get_health_status(self, now_ms: Optional[int] = None) -> Dict[str, Any]:
        """
        Diagnostic status for `/health` Telegram command (`T9.3`).
        """
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        last_age_ms = (now_ms - self._last_msg_ts_ms) if self._last_msg_ts_ms > 0 else -1
        return {
            "status": "CONNECTED" if self._connected else ("REST_FALLBACK" if self._offline_fallback_mode else "IDLE"),
            "connected": self._connected,
            "offline_fallback_mode": self._offline_fallback_mode,
            "reconnect_attempts": self._reconnect_attempts,
            "last_message_age_ms": last_age_ms,
            "tracked_symbols": list(self._symbols),
        }
