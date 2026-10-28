"""
===========================================================================
PYROFUEL BINANCE NATIVE PRICEMATCH & GTD ROUTER v3.0 (T6.6)
===========================================================================
Eliminates the ~150ms non-colocated network latency (Indonesia -> Tokyo AWS)
on passive Maker orders by leveraging Binance USDⓈ-M Matching-Engine native
parameters:
1. `priceMatch`:
   - `"QUEUE"`: Matching engine sets order price at best_bid (BUY) / best_ask (SELL)
     at the exact microsecond the packet arrives in Tokyo.
   - `"QUEUE_5"`: Places passive order 5 ticks deeper into the book to capture
     micro-wicks.
   - `"OPPONENT"` / `"OPPONENT_5"`: Aggressive limit matching against opposite book.
   * CRITICAL BINANCE API RULE: When `priceMatch` is sent, the `price` parameter
     MUST NOT be sent in the payload!
2. `timeInForce="GTD"` + `goodTillDate = now_ms + 4500`:
   - Matching engine automatically expires unfilled passive limit orders at
     `now_ms + 4500` server-side without requiring a second REST DELETE call.
3. Automatic Clean Fallback to `LIMIT` + `timeInForce="GTX"` (Post-Only) with
   explicit formatted `price` if the symbol or endpoint rejects `priceMatch`/`GTD`.
===========================================================================
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

VALID_PRICEMATCH_MODES = (
    "QUEUE",
    "QUEUE_5",
    "QUEUE_10",
    "QUEUE_20",
    "OPPONENT",
    "OPPONENT_5",
    "OPPONENT_10",
    "OPPONENT_20",
)


def build_native_pricematch_params(
    symbol: str,
    side: str,
    quantity: float | int | str,
    price_match: str = "QUEUE",
    tif: str = "GTD",
    now_ms: Optional[int] = None,
    gtd_offset_ms: int = 4500,
    client_order_id: Optional[str] = None,
    reduce_only: bool = False,
) -> Dict[str, Any]:
    """
    Construct Binance USDⓈ-M `/fapi/v1/order` parameters for native `priceMatch`
    and `GTD` auto-expiry (`goodTillDate = now_ms + 4500`).
    Strictly omits `price` as required by the Binance matching engine when `priceMatch` is active.
    """
    pm = str(price_match).upper().strip()
    if pm not in VALID_PRICEMATCH_MODES:
        raise ValueError(f"Unsupported priceMatch mode '{pm}'. Must be one of {VALID_PRICEMATCH_MODES}")

    side_norm = str(side).upper().strip()
    if side_norm in ("LONG", "BUY"):
        side_norm = "BUY"
    elif side_norm in ("SHORT", "SELL"):
        side_norm = "SELL"
    else:
        raise ValueError(f"Invalid order side '{side}'")

    tif_norm = str(tif).upper().strip()
    current_ms = int(now_ms) if now_ms is not None else int(time.time() * 1000)

    params: Dict[str, Any] = {
        "symbol": str(symbol).upper().strip(),
        "side": side_norm,
        "type": "LIMIT",
        "quantity": quantity,
        "priceMatch": pm,
        "timeInForce": tif_norm,
    }
    if tif_norm == "GTD":
        params["goodTillDate"] = int(current_ms + int(gtd_offset_ms))

    if client_order_id:
        params["newClientOrderId"] = str(client_order_id)[:36]
    if reduce_only:
        params["reduceOnly"] = "true"

    # Guarantee 'price' is never present when priceMatch is set
    params.pop("price", None)
    return params


def build_fallback_gtx_params(
    symbol: str,
    side: str,
    quantity: float | int | str,
    price: float | str,
    client_order_id: Optional[str] = None,
    reduce_only: bool = False,
) -> Dict[str, Any]:
    """
    Construct standard Post-Only Maker (`LIMIT` with `timeInForce="GTX"`) payload
    used when native `priceMatch` or `GTD` is rejected for a symbol.
    """
    side_norm = str(side).upper().strip()
    if side_norm in ("LONG", "BUY"):
        side_norm = "BUY"
    elif side_norm in ("SHORT", "SELL"):
        side_norm = "SELL"
    else:
        raise ValueError(f"Invalid order side '{side}'")

    params: Dict[str, Any] = {
        "symbol": str(symbol).upper().strip(),
        "side": side_norm,
        "type": "LIMIT",
        "quantity": quantity,
        "price": str(price),
        "timeInForce": "GTX",
    }
    if client_order_id:
        params["newClientOrderId"] = str(client_order_id)[:36]
    if reduce_only:
        params["reduceOnly"] = "true"
    return params


class NativePriceMatchRouter:
    """
    Executes passive Maker orders via native `priceMatch="QUEUE"` / `"QUEUE_5"` + `GTD`
    (`goodTillDate = now_ms + 4500`) with automatic fallback to `LIMIT GTX`.
    """

    def __init__(self, gtd_offset_ms: int = 4500) -> None:
        self.gtd_offset_ms = int(gtd_offset_ms)

    def place_passive_maker_order(
        self,
        client: Any,
        symbol: str,
        direction: str,
        quantity: float,
        fallback_price: float,
        price_match: str = "QUEUE",
        client_order_id: Optional[str] = None,
        now_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Attempt native `priceMatch` + `GTD` on `/fapi/v1/order`.
        If rejected by exchange (e.g. symbol doesn't support `priceMatch` or `GTD`
        interval rule), transparently falls back to `LIMIT` with `timeInForce="GTX"`.
        """
        sym = client.normalize_symbol(symbol) if hasattr(client, "normalize_symbol") else str(symbol).upper()
        fmt_qty = client.format_quantity(sym, quantity) if hasattr(client, "format_quantity") else quantity
        fmt_px = client.format_price(sym, fallback_price) if hasattr(client, "format_price") else fallback_price

        native_params = build_native_pricematch_params(
            symbol=sym,
            side=direction,
            quantity=fmt_qty,
            price_match=price_match,
            tif="GTD",
            now_ms=now_ms,
            gtd_offset_ms=self.gtd_offset_ms,
            client_order_id=client_order_id,
        )
        res = client._request("POST", "/fapi/v1/order", params=native_params, signed=True)
        if isinstance(res, dict) and not res.get("isError") and "orderId" in res:
            out = dict(res)
            out["routing_mode"] = f"NATIVE_PRICEMATCH_{price_match}_GTD"
            out["submitted_params"] = native_params
            return out

        # Fallback to LIMIT GTX (Post-Only)
        fb_cid = f"{client_order_id}_gtx"[:36] if client_order_id else None
        gtx_params = build_fallback_gtx_params(
            symbol=sym,
            side=direction,
            quantity=fmt_qty,
            price=fmt_px,
            client_order_id=fb_cid,
        )
        res_gtx = client._request("POST", "/fapi/v1/order", params=gtx_params, signed=True)
        out_gtx = dict(res_gtx) if isinstance(res_gtx, dict) else {"raw": res_gtx}
        out_gtx["routing_mode"] = "FALLBACK_LIMIT_GTX"
        out_gtx["native_rejection"] = res
        out_gtx["submitted_params"] = gtx_params
        return out_gtx
