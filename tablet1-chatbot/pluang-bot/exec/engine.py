"""
===========================================================================
PYROFUEL ATOMIC EXECUTION ENGINE v3.0 (T6.2, T0.2–T0.6, & T7.4)
===========================================================================
Wraps `binance_futures.py` (`BinanceFuturesClient`) with institutional
execution safeguards:
1. Deterministic `newClientOrderId`:
     pf3_{symbol[:6]}_{strategy_id[:2]}_{ts_sec}
   Queries `/fapi/v1/order?origClientOrderId=...` before re-submitting to
   guarantee 0 duplicate entries on network retries.
2. Pre-Trade Order-Book Depth Impact Guard (`AvellanedaStoikovRouter`):
   Aborts entry if VWAP fill impact exceeds 8.0 bps (0.08%).
3. Smart Maker-First (`priceMatch="QUEUE"` / `GTD` / `GTX`) vs `IOC` Router:
   Routes passive orders via `NativePriceMatchRouter` and converts any unfilled
   remainder after `maker_wait_sec` to a slippage-capped `LIMIT IOC`
   (`Entry * (1 +/- 0.0005)`).
4. Tri-State Algo Stop-Loss Lifecycle (`CONFIRMED | MISSING | UNKNOWN`):
   - Places SL/TP exclusively via `POST /fapi/v1/algoOrder` (`workingType="MARK_PRICE"`).
   - Verifies via `GET /fapi/v1/openAlgoOrders`.
   - NEVER closes positions on `"UNKNOWN"` (transient network error).
   - Retries up to 3x on `"MISSING"`; only emergency-closes if rejected 3x.
5. Adaptive Partial `TP1 (+0.55R)` vs Small-Account Single Full TP + Immediate
   Zero-Unprotected-Window `amend_stop_loss` to `+0.38R` when `+0.55R` is hit.
===========================================================================
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

from exec.avellaneda_router import AvellanedaStoikovRouter
from exec.event_bus import EventPriority, PriorityEventBus
from exec.native_pricematch import NativePriceMatchRouter


def generate_client_order_id(symbol: str, strategy_id: str, ts_sec: int, suffix: str = "") -> str:
    """
    Generate deterministic Binance `newClientOrderId`:
      pf3_{symbol[:6]}_{strategy_id[:2]}_{ts_sec}
    """
    clean_sym = "".join(c for c in str(symbol).upper() if c.isalnum())[:6]
    clean_strat = "".join(c for c in str(strategy_id).upper() if c.isalnum())[:2] or "S1"
    base = f"pf3_{clean_sym}_{clean_strat}_{int(ts_sec)}"
    if suffix:
        return f"{base}_{suffix}"[:36]
    return base[:36]


class AtomicExecutionEngineV3:
    """
    Atomic Execution Engine v3 (T6.2 & T7.4).
    """

    def __init__(
        self,
        client: Any,
        event_bus: Optional[PriorityEventBus] = None,
        avellaneda_router: Optional[AvellanedaStoikovRouter] = None,
        pricematch_router: Optional[NativePriceMatchRouter] = None,
        tp1_trigger_r: float = 0.55,
        sl_lock_after_tp1_r: float = 0.38,
        tp1_partial_close_pct: float = 0.50,
        min_leg_notional_floor_usdt: float = 15.0,
        ioc_max_slippage_frac: float = 0.0005,
        maker_wait_sec: float = 0.0,
    ):
        self.client = client
        self.event_bus = event_bus or PriorityEventBus()
        self.avellaneda = avellaneda_router or AvellanedaStoikovRouter()
        self.pricematch = pricematch_router or NativePriceMatchRouter()

        self.tp1_trigger_r = float(tp1_trigger_r)
        self.sl_lock_after_tp1_r = float(sl_lock_after_tp1_r)
        self.tp1_partial_close_pct = float(tp1_partial_close_pct)
        self.min_leg_notional_floor_usdt = float(min_leg_notional_floor_usdt)
        self.ioc_max_slippage_frac = float(ioc_max_slippage_frac)
        self.maker_wait_sec = float(maker_wait_sec)

        # Registry of active positions & idempotency cache for clientOrderId
        self.active_positions: Dict[str, Dict[str, Any]] = {}
        self._idempotent_orders: Dict[str, Dict[str, Any]] = {}

        # Subscribe to CRITICAL_POSITION_INTERRUPT for automatic TP1 -> +0.38R SL lock
        self.event_bus.subscribe("CRITICAL_POSITION_INTERRUPT", self._on_critical_interrupt)

    def _norm_sym(self, symbol: str) -> str:
        if hasattr(self.client, "normalize_symbol"):
            return self.client.normalize_symbol(symbol)
        s = str(symbol).upper().strip()
        return s if s.endswith("USDT") else f"{s}USDT"

    def _fmt_qty(self, symbol: str, qty: float) -> float:
        if hasattr(self.client, "format_quantity"):
            return float(self.client.format_quantity(symbol, qty))
        return round(float(qty), 3)

    def _fmt_px(self, symbol: str, px: float) -> float:
        if hasattr(self.client, "format_price"):
            return float(self.client.format_price(symbol, px))
        return round(float(px), 4)

    def _get_filters(self, symbol: str) -> Dict[str, Any]:
        if hasattr(self.client, "get_symbol_filters"):
            return dict(self.client.get_symbol_filters(symbol))
        return {
            "quantityPrecision": 3,
            "pricePrecision": 4,
            "stepSize": 0.001,
            "minQty": 0.001,
            "tickSize": 0.0001,
            "minNotional": 5.0,
        }

    def query_existing_order(self, symbol: str, client_order_id: str) -> Optional[Dict[str, Any]]:
        """
        Check if `client_order_id` was already accepted on Binance or in local idempotency cache
        to prevent double-entry on network retries.
        """
        if client_order_id in self._idempotent_orders:
            return dict(self._idempotent_orders[client_order_id])

        sym = self._norm_sym(symbol)
        res = self.client._request(
            "GET",
            "/fapi/v1/order",
            params={"symbol": sym, "origClientOrderId": client_order_id},
            signed=True,
        )
        if isinstance(res, dict) and not res.get("isError") and "orderId" in res:
            self._idempotent_orders[client_order_id] = dict(res)
            return dict(res)
        return None

    def get_open_algo_orders(self, symbol: Optional[str] = None) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Call `GET /fapi/v1/openAlgoOrders` (SIGNED).
        Returns `(ok: bool, orders: list)`. On network/HTTP error, returns `(False, [])`.
        """
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = self._norm_sym(symbol)
        res = self.client._request("GET", "/fapi/v1/openAlgoOrders", params=params, signed=True)
        if isinstance(res, dict) and res.get("isError"):
            return False, []
        if isinstance(res, list):
            return True, res
        if isinstance(res, dict) and "orders" in res and isinstance(res["orders"], list):
            return True, res["orders"]
        if isinstance(res, dict):
            return True, []
        return False, []

    def verify_stop_loss_tristate(
        self,
        symbol: str,
        expected_side: Optional[str] = None,
        max_wait_sec: float = 1.8,
        poll_interval_sec: float = 0.0,
    ) -> str:
        """
        Verify SL active on exchange using Tri-State semantics (`"CONFIRMED" | "MISSING" | "UNKNOWN"`):
        - Queries `GET /fapi/v1/openAlgoOrders` and standard `GET /fapi/v1/openOrders`.
        - Returns `"CONFIRMED"` if an active STOP_MARKET / STOP / TRAILING_STOP_MARKET order exists.
        - Returns `"MISSING"` ONLY if HTTP 200 succeeded and no SL order exists.
        - Returns `"UNKNOWN"` if network/HTTP errors prevented confirmation.
        """
        sym = self._norm_sym(symbol)
        exp_side = str(expected_side).upper().strip() if expected_side else None
        deadline = time.time() + max(0.01, float(max_wait_sec))
        saw_network_error = False

        while True:
            ok_algo, algo_orders = self.get_open_algo_orders(sym)
            if ok_algo:
                for o in algo_orders:
                    status = str(o.get("algoStatus") or o.get("status") or "NEW").upper()
                    otype = str(o.get("orderType") or o.get("type") or "").upper()
                    oside = str(o.get("side") or "").upper()
                    if status in ("NEW", "WORKING") and any(
                        t in otype for t in ("STOP_MARKET", "STOP", "TRAILING_STOP_MARKET")
                    ):
                        if exp_side is None or oside == exp_side:
                            return "CONFIRMED"
            else:
                saw_network_error = True

            std_orders = self.client.get_open_orders(sym) if hasattr(self.client, "get_open_orders") else []
            ok_std = isinstance(std_orders, list)
            if ok_std:
                for o in std_orders:
                    otype = str(o.get("type") or o.get("origType") or "").upper()
                    oside = str(o.get("side") or "").upper()
                    if any(t in otype for t in ("STOP_MARKET", "STOP", "TRAILING_STOP_MARKET")):
                        if exp_side is None or oside == exp_side:
                            return "CONFIRMED"
            elif isinstance(std_orders, dict) and std_orders.get("isError"):
                saw_network_error = True

            if time.time() >= deadline or poll_interval_sec <= 0.0:
                break
            time.sleep(poll_interval_sec)

        if saw_network_error:
            return "UNKNOWN"
        return "MISSING"

    def place_algo_stop_loss(
        self,
        symbol: str,
        direction: str,
        trigger_price: float,
        quantity: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Place Stop-Loss directly via `POST /fapi/v1/algoOrder` with `workingType="MARK_PRICE"`
        and `priceProtect="TRUE"`.
        """
        sym = self._norm_sym(symbol)
        side = "SELL" if str(direction).upper() == "LONG" else "BUY"
        fmt_px = self._fmt_px(sym, trigger_price)
        params: Dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": sym,
            "side": side,
            "type": "STOP_MARKET",
            "triggerPrice": str(fmt_px),
            "workingType": "MARK_PRICE",
            "priceProtect": "TRUE",
        }
        if quantity is None:
            params["closePosition"] = "true"
        else:
            params["quantity"] = self._fmt_qty(sym, quantity)
            params["reduceOnly"] = "true"

        return self.client._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)

    def place_algo_take_profit(
        self,
        symbol: str,
        direction: str,
        trigger_price: float,
        quantity: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Place Take-Profit directly via `POST /fapi/v1/algoOrder` with `workingType="MARK_PRICE"`.
        """
        sym = self._norm_sym(symbol)
        side = "SELL" if str(direction).upper() == "LONG" else "BUY"
        fmt_px = self._fmt_px(sym, trigger_price)
        params: Dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": sym,
            "side": side,
            "type": "TAKE_PROFIT_MARKET",
            "triggerPrice": str(fmt_px),
            "workingType": "MARK_PRICE",
            "priceProtect": "TRUE",
        }
        if quantity is None:
            params["closePosition"] = "true"
        else:
            params["quantity"] = self._fmt_qty(sym, quantity)
            params["reduceOnly"] = "true"

        return self.client._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)

    def amend_stop_loss(
        self,
        symbol: str,
        direction: str,
        new_stop_price: float,
        old_algo_id: Optional[str | int] = None,
    ) -> Dict[str, Any]:
        """
        Zero-Unprotected-Window atomic Stop-Loss amendment (T0.6 & T6.2):
        1. Place NEW Stop-Loss Algo Order at `new_stop_price` first.
        2. Verify the new SL succeeded and returned a valid `algoId`.
        3. ONLY THEN cancel `old_algo_id` via `DELETE /fapi/v1/algoOrder`.
        If step 1 fails, `old_algo_id` is NEVER cancelled!
        """
        sym = self._norm_sym(symbol)
        new_res = self.place_algo_stop_loss(sym, direction, new_stop_price)
        if not isinstance(new_res, dict) or new_res.get("isError") or "algoId" not in new_res:
            return {
                "ok": False,
                "error": "NEW_SL_PLACEMENT_FAILED",
                "new_sl_response": new_res,
                "old_sl_preserved": True,
                "old_algo_id": old_algo_id,
            }

        new_algo_id = new_res["algoId"]
        cancel_res = None
        if old_algo_id is not None:
            cancel_res = self.client._request(
                "DELETE",
                "/fapi/v1/algoOrder",
                params={"symbol": sym, "algoId": old_algo_id},
                signed=True,
            )

        if sym in self.active_positions:
            self.active_positions[sym]["sl_price"] = self._fmt_px(sym, new_stop_price)
            self.active_positions[sym]["sl_algo_id"] = new_algo_id
            self.active_positions[sym]["sl_state"] = "CONFIRMED"

        return {
            "ok": True,
            "symbol": sym,
            "new_stop_price": self._fmt_px(sym, new_stop_price),
            "new_algo_id": new_algo_id,
            "old_algo_id_cancelled": old_algo_id,
            "cancel_response": cancel_res,
        }

    def select_tp_mode(
        self,
        symbol: str,
        total_quantity: float,
        entry_price: float,
    ) -> Dict[str, Any]:
        """
        Adaptive Partial TP1 + TP2 vs Small-Account Single Full TP (T6.2 & T7.4):
        Splits into Partial TP1 + Runner TP2 ONLY when both legs satisfy:
          leg_notional >= max(1.05 * minNotional, min_leg_notional_floor_usdt)
          AND leg_qty >= minQty.
        On small balances (e.g. $1.32 where notional ~$25.08), automatically
        selects `"SINGLE_FULL_TP"` so exchange never rejects fractional TP orders.
        On larger balances (e.g. $50+ where notional ~$950), automatically
        selects `"PARTIAL_TP1_TP2"`.
        """
        sym = self._norm_sym(symbol)
        filters = self._get_filters(sym)
        min_notional = float(filters.get("minNotional", 5.0))
        min_qty = float(filters.get("minQty", 0.001))
        step = float(filters.get("stepSize", 0.001))
        prec = int(filters.get("quantityPrecision", 3))

        split_frac = self.tp1_partial_close_pct
        raw_tp1_qty = float(total_quantity) * split_frac
        tp1_steps = math.floor(raw_tp1_qty / max(1e-12, step))
        qty_tp1 = round(tp1_steps * step, prec) if prec > 0 else float(int(tp1_steps * step))
        qty_tp2 = round(float(total_quantity) - qty_tp1, prec) if prec > 0 else float(int(round(float(total_quantity) - qty_tp1)))

        notional_tp1 = qty_tp1 * float(entry_price)
        notional_tp2 = qty_tp2 * float(entry_price)
        req_leg_notional = max(1.05 * min_notional, self.min_leg_notional_floor_usdt)

        can_split = (
            qty_tp1 >= min_qty
            and qty_tp2 >= min_qty
            and notional_tp1 >= req_leg_notional
            and notional_tp2 >= req_leg_notional
        )
        if can_split:
            return {
                "tp_mode": "PARTIAL_TP1_TP2",
                "qty_tp1": qty_tp1,
                "qty_tp2": qty_tp2,
                "notional_tp1": notional_tp1,
                "notional_tp2": notional_tp2,
            }
        return {
            "tp_mode": "SINGLE_FULL_TP",
            "qty_tp1": 0.0,
            "qty_tp2": float(total_quantity),
            "notional_tp1": 0.0,
            "notional_tp2": float(total_quantity) * float(entry_price),
        }

    def execute_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        quantity: float,
        strategy_id: str = "S1_TREND_PULLBACK",
        execution_style: str = "MAKER_FIRST_GTX",
        ts_sec: Optional[int] = None,
        depth_book: Optional[Dict[str, Any]] = None,
        leverage: int = 20,
        margin_type: str = "ISOLATED",
    ) -> Dict[str, Any]:
        """
        Execute full atomic trade lifecycle:
        1. Idempotent `newClientOrderId` check
        2. Pre-Trade Depth VWAP Impact check (<= 8.0 bps)
        3. Smart Maker-First (`priceMatch=QUEUE` / `GTX`) or `LIMIT IOC` entry
        4. Tri-State SL placement & verification (`CONFIRMED | MISSING | UNKNOWN`)
        5. Adaptive Partial `TP1 (+0.55R)` + `TP2` vs Small-Account Single TP +
           intrabar price alarm at `+0.55R` to lock SL at `+0.38R`.
        """
        sym = self._norm_sym(symbol)
        dir_norm = str(direction).upper().strip()
        side = "BUY" if dir_norm == "LONG" else "SELL"
        ts_val = int(ts_sec) if ts_sec is not None else int(time.time())
        cid = generate_client_order_id(sym, strategy_id, ts_val)

        # 1. Idempotency Guard: never submit duplicate entry for the same clientOrderId
        existing = self.query_existing_order(sym, cid)
        if existing is not None:
            return {
                "status": "IDEMPOTENT_EXISTING_ORDER",
                "symbol": sym,
                "client_order_id": cid,
                "existing_order": existing,
                "duplicate_prevented": True,
            }

        # 2. Pre-Trade Depth Impact Check (<= 8.0 bps)
        if depth_book is not None:
            impact = self.avellaneda.compute_vwap_impact_bps(depth_book, dir_norm, quantity)
            if not impact["passed"]:
                return {
                    "status": "ABORTED_DEPTH_IMPACT",
                    "symbol": sym,
                    "client_order_id": cid,
                    "impact_bps": impact["impact_bps"],
                    "reason": impact["reason"],
                }

        # Pre-configure 20x ISOLATED
        try:
            self.client.set_margin_type(sym, margin_type)
            self.client.set_leverage(sym, leverage)
        except Exception:
            pass

        fmt_qty = self._fmt_qty(sym, quantity)
        fmt_entry = self._fmt_px(sym, entry_price)

        # 3. Entry Routing: MAKER_FIRST_GTX vs IMMEDIATE_IOC
        style = str(execution_style).upper().strip()
        entry_res: Dict[str, Any] = {}
        routing_used = style

        if style == "MAKER_FIRST_GTX":
            opt_px = fmt_entry
            pm_mode = "QUEUE"
            if depth_book and depth_book.get("bids") and depth_book.get("asks"):
                b0 = depth_book["bids"][0]
                a0 = depth_book["asks"][0]
                filters = self._get_filters(sym)
                as_info = self.avellaneda.compute_optimal_offset(
                    direction=dir_norm,
                    best_bid_price=float(b0[0]),
                    best_bid_qty=float(b0[1]),
                    best_ask_price=float(a0[0]),
                    best_ask_qty=float(a0[1]),
                    tick_size=float(filters.get("tickSize", 0.01)),
                )
                opt_px = self._fmt_px(sym, as_info["optimal_limit_price"])
                pm_mode = as_info["recommended_price_match"]

            maker_res = self.pricematch.place_passive_maker_order(
                client=self.client,
                symbol=sym,
                direction=dir_norm,
                quantity=fmt_qty,
                fallback_price=opt_px,
                price_match=pm_mode,
                client_order_id=cid,
            )
            entry_res = maker_res
            routing_used = maker_res.get("routing_mode", "MAKER_FIRST_GTX")

            # If maker order was not immediately filled and we need IOC fallback
            maker_status = str(maker_res.get("status", "FILLED")).upper()
            if maker_status in ("NEW", "PARTIALLY_FILLED", "EXPIRED", "CANCELED") and maker_res.get("convert_to_ioc"):
                if self.maker_wait_sec > 0:
                    time.sleep(self.maker_wait_sec)
                ioc_bound = (
                    fmt_entry * (1.0 + self.ioc_max_slippage_frac)
                    if dir_norm == "LONG"
                    else fmt_entry * (1.0 - self.ioc_max_slippage_frac)
                )
                ioc_params = {
                    "symbol": sym,
                    "side": side,
                    "type": "LIMIT",
                    "timeInForce": "IOC",
                    "quantity": fmt_qty,
                    "price": str(self._fmt_px(sym, ioc_bound)),
                    "newClientOrderId": f"{cid}_ioc"[:36],
                }
                entry_res = self.client._request("POST", "/fapi/v1/order", params=ioc_params, signed=True)
                routing_used = "MAKER_TO_IOC_FALLBACK"
        else:
            ioc_bound = (
                fmt_entry * (1.0 + self.ioc_max_slippage_frac)
                if dir_norm == "LONG"
                else fmt_entry * (1.0 - self.ioc_max_slippage_frac)
            )
            ioc_params = {
                "symbol": sym,
                "side": side,
                "type": "LIMIT",
                "timeInForce": "IOC",
                "quantity": fmt_qty,
                "price": str(self._fmt_px(sym, ioc_bound)),
                "newClientOrderId": cid,
            }
            entry_res = self.client._request("POST", "/fapi/v1/order", params=ioc_params, signed=True)
            routing_used = "IMMEDIATE_IOC"

        if not isinstance(entry_res, dict) or entry_res.get("isError") or "orderId" not in entry_res:
            return {
                "status": "ENTRY_FAILED",
                "symbol": sym,
                "client_order_id": cid,
                "entry_response": entry_res,
            }

        self._idempotent_orders[cid] = dict(entry_res)

        # 4. Place Stop-Loss via Algo Order API + Tri-State Verification (with up to 3x retry on MISSING)
        exp_sl_side = "SELL" if dir_norm == "LONG" else "BUY"
        sl_algo_id = None
        sl_state = "UNKNOWN"

        for attempt in range(3):
            sl_res = self.place_algo_stop_loss(sym, dir_norm, sl_price)
            if isinstance(sl_res, dict) and not sl_res.get("isError") and "algoId" in sl_res:
                sl_algo_id = sl_res["algoId"]
            sl_state = self.verify_stop_loss_tristate(sym, expected_side=exp_sl_side, max_wait_sec=0.5)
            if sl_state == "CONFIRMED":
                break
            if sl_state == "UNKNOWN" and sl_algo_id is not None:
                # Network hiccup during read, but POST /fapi/v1/algoOrder returned a valid algoId!
                break

        if sl_state == "MISSING":
            # Confirmed missing after 3 attempts -> Emergency close position
            if hasattr(self.client, "close_position"):
                self.client.close_position(sym, dir_norm, quantity=fmt_qty)
            return {
                "status": "ABORTED_SL_REJECTED_3X",
                "close_reason": "SL_PLACEMENT_REJECTED_3X",
                "symbol": sym,
                "client_order_id": cid,
                "sl_state": "MISSING",
            }

        # 5. Compute Sniper TP1 (+0.55R) and SL Lock (+0.38R) levels
        risk_dist = abs(float(entry_price) - float(sl_price))
        if dir_norm == "LONG":
            tp1_price = self._fmt_px(sym, float(entry_price) + self.tp1_trigger_r * risk_dist)
            sl_lock_price = self._fmt_px(sym, float(entry_price) + self.sl_lock_after_tp1_r * risk_dist)
        else:
            tp1_price = self._fmt_px(sym, float(entry_price) - self.tp1_trigger_r * risk_dist)
            sl_lock_price = self._fmt_px(sym, float(entry_price) - self.sl_lock_after_tp1_r * risk_dist)

        tp_plan = self.select_tp_mode(sym, fmt_qty, float(entry_price))
        tp_mode = tp_plan["tp_mode"]
        tp_orders: List[Dict[str, Any]] = []

        if tp_mode == "PARTIAL_TP1_TP2":
            res_tp1 = self.place_algo_take_profit(
                sym, dir_norm, tp1_price, quantity=tp_plan["qty_tp1"]
            )
            res_tp2 = self.place_algo_take_profit(
                sym, dir_norm, tp_price, quantity=None
            )
            tp_orders.extend([res_tp1, res_tp2])
        else:
            res_tp_full = self.place_algo_take_profit(
                sym, dir_norm, tp_price, quantity=None
            )
            tp_orders.append(res_tp_full)

        pos_state = {
            "symbol": sym,
            "direction": dir_norm,
            "client_order_id": cid,
            "routing_used": routing_used,
            "entry_price": fmt_entry,
            "sl_price": self._fmt_px(sym, sl_price),
            "tp_price": self._fmt_px(sym, tp_price),
            "tp1_price": tp1_price,
            "sl_lock_after_tp1_price": sl_lock_price,
            "quantity": fmt_qty,
            "tp_mode": tp_mode,
            "sl_state": sl_state,
            "sl_algo_id": sl_algo_id,
            "tp_orders": tp_orders,
            "tp1_locked": False,
        }
        self.active_positions[sym] = pos_state

        # Register intrabar price alarm on PriorityEventBus at TP1 (+0.55R)
        self.event_bus.register_price_alarm(
            symbol=sym,
            direction=dir_norm,
            trigger_price=tp1_price,
            event_type="CRITICAL_POSITION_INTERRUPT",
            payload={
                "reason": "TP1_REACHED_LOCK_SL",
                "symbol": sym,
                "direction": dir_norm,
                "new_stop_price": sl_lock_price,
                "old_algo_id": sl_algo_id,
            },
        )

        return {
            "status": "EXECUTED",
            **pos_state,
        }

    def on_tp1_reached(self, symbol: str) -> Dict[str, Any]:
        """
        Immediately amend Stop-Loss on exchange to `+0.38R` (`sl_lock_after_tp1_price`)
        when price reaches `TP1 (+0.55R)`.
        """
        sym = self._norm_sym(symbol)
        pos = self.active_positions.get(sym)
        if not pos:
            return {"ok": False, "error": f"No active position tracked for {sym}"}
        if pos.get("tp1_locked"):
            return {"ok": True, "already_locked": True, "sl_price": pos["sl_price"]}

        amend_res = self.amend_stop_loss(
            symbol=sym,
            direction=pos["direction"],
            new_stop_price=pos["sl_lock_after_tp1_price"],
            old_algo_id=pos.get("sl_algo_id"),
        )
        if amend_res.get("ok"):
            pos["tp1_locked"] = True
        return amend_res

    def _on_critical_interrupt(self, evt: Any) -> None:
        payload = getattr(evt, "payload", {}) or {}
        if payload.get("reason") == "TP1_REACHED_LOCK_SL":
            sym = payload.get("symbol")
            if sym:
                self.on_tp1_reached(sym)
