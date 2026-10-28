"""
===========================================================================
PYROFUEL WEBSOCKET USER DATA STREAM MANAGER v3.0 (T6.1)
===========================================================================
Real-time Binance USDⓈ-M Futures User Data Stream handler:
1. Lifecycle Management:
   - Opens `listenKey` via `POST /fapi/v1/listenKey`
   - Automatic keepalive via `PUT /fapi/v1/listenKey` every 25 minutes (1500s)
   - Clean teardown via `DELETE /fapi/v1/listenKey`
2. Real-Time Event Processing (`< 50ms`):
   - `ORDER_TRADE_UPDATE`: Extracts exact average fill price (`ap`), cumulative
     filled quantity (`z`), commission (`n`), and realized profit (`rp`).
     Closes/updates in-memory position state, computes net R-multiple
     (`r_multiple_net`), writes to journal callback, and fires
     `CRITICAL_POSITION_INTERRUPT` on `PriorityEventBus`.
   - `ALGO_UPDATE`: Instantly updates `sl_state` (`CONFIRMED | MISSING | TRIGGERED`)
     and `sl_algo_id` / `tp_algo_id`.
   - `ACCOUNT_UPDATE`: Updates USDT wallet balance and open positions in memory
     without burning REST API rate limits.
===========================================================================
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from exec.event_bus import EventPriority, PriorityEventBus


class UserDataStreamManager:
    """
    Manages Binance USDⓈ-M Futures User Data Stream (`listenKey` & real-time events) (T6.1).
    """

    KEEPALIVE_INTERVAL_SEC = 25 * 60  # 25 minutes (1500s)

    def __init__(
        self,
        client: Optional[Any] = None,
        event_bus: Optional[PriorityEventBus] = None,
        journal_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.client = client
        self.event_bus = event_bus
        self.journal_callback = journal_callback

        self._lock = threading.RLock()
        self.listen_key: Optional[str] = None
        self.last_keepalive_ts: float = 0.0

        # In-memory state synchronized from user stream
        self.wallet_balance_usdt: float = 0.0
        self.cross_wallet_balance_usdt: float = 0.0
        self.active_positions: Dict[str, Dict[str, Any]] = {}
        self.closed_trades_log: List[Dict[str, Any]] = []

    def create_listen_key(self) -> Optional[str]:
        if self.client is None:
            return None
        res = self.client._request("POST", "/fapi/v1/listenKey", signed=True)
        if isinstance(res, dict) and "listenKey" in res:
            with self._lock:
                self.listen_key = str(res["listenKey"])
                self.last_keepalive_ts = time.time()
            return self.listen_key
        return None

    def keepalive_listen_key(self) -> bool:
        if self.client is None or not self.listen_key:
            return False
        res = self.client._request("PUT", "/fapi/v1/listenKey", signed=True)
        if isinstance(res, dict) and not res.get("isError"):
            with self._lock:
                self.last_keepalive_ts = time.time()
            return True
        return False

    def close_listen_key(self) -> bool:
        if self.client is None or not self.listen_key:
            return False
        res = self.client._request("DELETE", "/fapi/v1/listenKey", signed=True)
        with self._lock:
            self.listen_key = None
        return isinstance(res, dict) and not res.get("isError")

    def get_ws_url(self, testnet: bool = False) -> str:
        base = "wss://stream.binancefuture.com/ws" if testnet else "wss://fstream.binance.com/ws"
        return f"{base}/{self.listen_key or ''}"

    def register_tracked_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        quantity: float,
        margin_usdt: float = 0.0,
        decision_id: str = "",
        sl_state: str = "CONFIRMED",
        sl_algo_id: Optional[str] = None,
    ) -> None:
        sym = str(symbol).upper().strip()
        with self._lock:
            self.active_positions[sym] = {
                "symbol": sym,
                "direction": str(direction).upper().strip(),
                "entry_price": float(entry_price),
                "sl_price": float(sl_price),
                "tp_price": float(tp_price),
                "quantity": float(quantity),
                "margin_usdt": float(margin_usdt),
                "decision_id": decision_id,
                "sl_state": sl_state,
                "sl_algo_id": sl_algo_id,
                "entry_fee_usdt": 0.0,
                "opened_at_ms": int(time.time() * 1000),
            }

    def handle_event(self, raw_event: str | Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a raw WebSocket User Data Stream JSON message in < 10ms.
        Supports:
          - `ORDER_TRADE_UPDATE`
          - `ALGO_UPDATE`
          - `ACCOUNT_UPDATE`
        """
        t0 = time.perf_counter()
        if isinstance(raw_event, str):
            msg = json.loads(raw_event)
        else:
            msg = dict(raw_event)

        event_type = str(msg.get("e", "")).upper().strip()
        if event_type == "ORDER_TRADE_UPDATE":
            res = self._handle_order_trade_update(msg)
        elif event_type in ("ALGO_UPDATE", "CONDITIONAL_ORDER_TRIGGER_REJECT"):
            res = self._handle_algo_update(msg)
        elif event_type == "ACCOUNT_UPDATE":
            res = self._handle_account_update(msg)
        else:
            res = {"handled": False, "event_type": event_type}

        res["processing_ms"] = (time.perf_counter() - t0) * 1000.0
        return res

    def _handle_order_trade_update(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        o = msg.get("o", {})
        symbol = str(o.get("s", "")).upper().strip()
        side = str(o.get("S", "")).upper().strip()
        order_type = str(o.get("o", "")).upper().strip()
        orig_type = str(o.get("ot", order_type)).upper().strip()
        status = str(o.get("X", "")).upper().strip()
        client_order_id = str(o.get("c", ""))
        avg_price = float(o.get("ap", 0.0) or 0.0)
        filled_qty = float(o.get("z", 0.0) or 0.0)
        commission = float(o.get("n", 0.0) or 0.0)
        realized_profit = float(o.get("rp", 0.0) or 0.0)
        reduce_only = bool(o.get("R", False))
        close_position = bool(o.get("cp", False))

        with self._lock:
            pos = self.active_positions.get(symbol)
            is_exit_order = (
                reduce_only
                or close_position
                or any(k in orig_type for k in ("STOP", "TAKE_PROFIT", "TRAILING"))
                or any(k in order_type for k in ("STOP", "TAKE_PROFIT", "TRAILING"))
            )
            if pos and not is_exit_order:
                pos_dir = pos["direction"]
                if (pos_dir == "LONG" and side == "SELL") or (pos_dir == "SHORT" and side == "BUY"):
                    is_exit_order = True

            # Case 1: Entry order fill update
            if not is_exit_order and status in ("FILLED", "PARTIALLY_FILLED"):
                if pos:
                    if avg_price > 0:
                        pos["entry_price"] = avg_price
                    if filled_qty > 0:
                        pos["quantity"] = filled_qty
                    pos["entry_fee_usdt"] = float(pos.get("entry_fee_usdt", 0.0)) + commission
                return {
                    "handled": True,
                    "event_type": "ORDER_TRADE_UPDATE",
                    "sub_type": "ENTRY_FILL",
                    "symbol": symbol,
                    "avg_price": avg_price,
                    "filled_qty": filled_qty,
                    "commission": commission,
                }

            # Case 2: Exit / SL / TP fill update
            if is_exit_order and status == "FILLED":
                close_reason = "TP_EXCHANGE"
                if "TRAILING" in orig_type or "TRAILING" in order_type:
                    close_reason = "TRAIL_EXCHANGE"
                elif "STOP" in orig_type or "STOP" in order_type:
                    close_reason = "SL_EXCHANGE"
                elif realized_profit < 0:
                    close_reason = "SL_EXCHANGE"

                entry_px = float(pos["entry_price"]) if pos else avg_price
                sl_px = float(pos["sl_price"]) if pos else entry_px * 0.99
                qty = filled_qty if filled_qty > 0 else (float(pos["quantity"]) if pos else 0.0)
                entry_fee = float(pos.get("entry_fee_usdt", 0.0)) if pos else 0.0
                total_fee = entry_fee + commission
                net_pnl_usdt = realized_profit - total_fee

                # Compute r_multiple_net relative to initial 1R dollar risk |entry - sl| * qty
                risk_per_unit = max(1e-8, abs(entry_px - sl_px))
                initial_risk_usdt = max(1e-8, risk_per_unit * max(1e-8, qty))
                if realized_profit != 0.0 or total_fee != 0.0:
                    r_multiple_net = net_pnl_usdt / initial_risk_usdt
                else:
                    dir_sign = 1.0 if (pos and pos["direction"] == "LONG") else -1.0
                    gross_r = dir_sign * (avg_price - entry_px) / risk_per_unit
                    r_multiple_net = gross_r - (total_fee / initial_risk_usdt)

                trade_record = {
                    "symbol": symbol,
                    "direction": pos["direction"] if pos else ("LONG" if side == "SELL" else "SHORT"),
                    "decision_id": pos.get("decision_id", "") if pos else "",
                    "client_order_id": client_order_id,
                    "entry_fill": entry_px,
                    "exit_fill": avg_price,
                    "qty": qty,
                    "fee_usdt": total_fee,
                    "realized_pnl_gross": realized_profit,
                    "net_pnl_usdt": net_pnl_usdt,
                    "r_multiple_net": float(r_multiple_net),
                    "close_reason": close_reason,
                    "closed_at_ms": int(msg.get("E", int(time.time() * 1000))),
                }

                # Check if partial TP1 fill or full position close
                remaining_qty = (float(pos["quantity"]) - filled_qty) if pos else 0.0
                is_partial_tp1 = (not close_position) and (remaining_qty > 1e-8)

                if is_partial_tp1 and pos:
                    pos["quantity"] = remaining_qty
                    pos["tp1_filled"] = True
                    trade_record["sub_type"] = "PARTIAL_TP1_FILL"
                else:
                    self.active_positions.pop(symbol, None)
                    self.closed_trades_log.append(trade_record)
                    trade_record["sub_type"] = "POSITION_CLOSED"

        if self.journal_callback is not None:
            self.journal_callback(trade_record)

        if self.event_bus is not None:
            self.event_bus.publish(
                "CRITICAL_POSITION_INTERRUPT",
                payload=trade_record,
                priority=int(EventPriority.CRITICAL_POSITION_INTERRUPT),
            )

        return {
            "handled": True,
            "event_type": "ORDER_TRADE_UPDATE",
            **trade_record,
        }

    def _handle_algo_update(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        o = msg.get("o", msg)
        symbol = str(o.get("s") or o.get("symbol") or "").upper().strip()
        algo_id = str(o.get("aid") or o.get("algoId") or "")
        status = str(o.get("X") or o.get("algoStatus") or "").upper().strip()
        order_type = str(o.get("o") or o.get("orderType") or "STOP_MARKET").upper().strip()
        trigger_px = float(o.get("tp") or o.get("triggerPrice") or 0.0)

        new_sl_state = "UNKNOWN"
        if status in ("NEW", "WORKING"):
            new_sl_state = "CONFIRMED"
        elif status in ("CANCELED", "EXPIRED", "REJECTED"):
            new_sl_state = "MISSING"
        elif status in ("TRIGGERED", "FINISHED", "FILLED"):
            new_sl_state = "TRIGGERED"

        with self._lock:
            pos = self.active_positions.get(symbol)
            if pos and "STOP" in order_type:
                pos["sl_state"] = new_sl_state
                if algo_id:
                    pos["sl_algo_id"] = algo_id
                if trigger_px > 0:
                    pos["sl_price"] = trigger_px

        if new_sl_state == "MISSING" and self.event_bus is not None:
            self.event_bus.publish(
                "CRITICAL_POSITION_INTERRUPT",
                payload={"symbol": symbol, "sl_state": "MISSING", "algo_id": algo_id},
                priority=int(EventPriority.CRITICAL_POSITION_INTERRUPT),
            )

        return {
            "handled": True,
            "event_type": "ALGO_UPDATE",
            "symbol": symbol,
            "algo_id": algo_id,
            "algo_status": status,
            "sl_state": new_sl_state,
            "trigger_price": trigger_px,
        }

    def _handle_account_update(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        a = msg.get("a", {})
        balances = a.get("B", [])
        positions = a.get("P", [])

        with self._lock:
            for b in balances:
                if str(b.get("a", "")).upper() == "USDT":
                    self.wallet_balance_usdt = float(b.get("wb", self.wallet_balance_usdt))
                    self.cross_wallet_balance_usdt = float(b.get("cw", self.cross_wallet_balance_usdt))

            for p in positions:
                sym = str(p.get("s", "")).upper().strip()
                amt = float(p.get("pa", 0.0))
                ep = float(p.get("ep", 0.0))
                if amt == 0.0:
                    self.active_positions.pop(sym, None)
                else:
                    existing = self.active_positions.get(sym, {})
                    existing.update(
                        {
                            "symbol": sym,
                            "direction": "LONG" if amt > 0 else "SHORT",
                            "quantity": abs(amt),
                            "entry_price": ep if ep > 0 else existing.get("entry_price", 0.0),
                            "unrealized_pnl": float(p.get("up", 0.0)),
                            "margin_type": str(p.get("mt", "isolated")).upper(),
                        }
                    )
                    self.active_positions[sym] = existing

        return {
            "handled": True,
            "event_type": "ACCOUNT_UPDATE",
            "wallet_balance_usdt": self.wallet_balance_usdt,
            "active_symbols": list(self.active_positions.keys()),
        }
