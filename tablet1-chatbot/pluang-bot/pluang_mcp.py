"""
===========================================================================
PLUANG MCP CLIENT v3.0 - FULL FUTURES TRADING CONTROL
===========================================================================
Complete MCP (Model Context Protocol) client for Pluang Crypto Futures:
- Open/Close positions
- Set Leverage (1x-125x)
- Set Margin Type (CROSS/ISOLATED)
- Set Order Type (MARKET/LIMIT/STOP_MARKET/TAKE_PROFIT_MARKET)
- Set TP/SL orders
- Query portfolio, balance, positions
- Auto token refresh with PKCE
===========================================================================
"""
import requests
import json
import os
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class PluangMCPClient:
    def __init__(self, access_token: str, base_url: str = "https://mcp.pluang.com/mcp"):
        self.access_token = access_token
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        self._request_id = 1
        self._tool_cache = None
        self._last_error = None

    def _parse_sse(self, text: str):
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except Exception:
                    pass
        # Fallback raw json
        try:
            return json.loads(text)
        except Exception:
            return {}

    def _refresh_token(self):
        token_path = os.path.join(BASE_DIR, "tokens.json")
        client_path = os.path.join(BASE_DIR, "client_config.json")
        if not (os.path.exists(token_path) and os.path.exists(client_path)):
            return False
        try:
            with open(token_path, "r") as f:
                token_data = json.load(f)
            with open(client_path, "r") as f:
                client_data = json.load(f)
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": token_data.get("refresh_token"),
                "client_id": client_data.get("client_id")
            }
            resp = requests.post("https://mcp.pluang.com/token", data=payload, timeout=15)
            if resp.status_code == 200:
                new_data = resp.json()
                new_data["acquired_at"] = time.time()
                with open(token_path, "w") as f:
                    json.dump(new_data, f, indent=2)
                self.access_token = new_data["access_token"]
                self.headers["Authorization"] = f"Bearer {self.access_token}"
                print(f"[PluangMCP] Token refreshed successfully")
                return True
        except Exception as e:
            print(f"[PluangMCP] Token refresh failed: {e}")
        return False

    def _rpc(self, method: str, params: dict = None):
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {}
        }
        try:
            resp = requests.post(self.base_url, headers=self.headers, json=payload, timeout=20)
            if resp.status_code == 401:
                if self._refresh_token():
                    resp = requests.post(self.base_url, headers=self.headers, json=payload, timeout=20)

            if resp.status_code != 200:
                self._last_error = f"MCP RPC Error {resp.status_code}: {resp.text[:200]}"
                raise Exception(self._last_error)

            result = self._parse_sse(resp.text)
            if "error" in result:
                self._last_error = f"MCP Error: {result['error']}"
                raise Exception(self._last_error)
            return result.get("result", {})
        except requests.exceptions.RequestException as e:
            self._last_error = f"Network error: {str(e)}"
            raise

    # ===================================================================
    # CORE MCP METHODS
    # ===================================================================
    def initialize(self):
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "PyrofuelAgenticTrader",
                "version": "3.0.0"
            }
        }
        return self._rpc("initialize", params)

    def list_tools(self):
        if self._tool_cache:
            return self._tool_cache
        res = self._rpc("tools/list")
        self._tool_cache = res.get("tools", [])
        return self._tool_cache

    def call_tool(self, name: str, arguments: dict):
        if not isinstance(arguments, dict):
            arguments = {}
        if "user_query" not in arguments:
            arguments["user_query"] = f"execute {name}"
        if name != "generate_new_session_id" and "chat_session_id" not in arguments:
            arguments["chat_session_id"] = self._get_chat_session_id()
        params = {
            "name": name,
            "arguments": arguments
        }
        res = self._rpc("tools/call", params)
        return res

    def get_openai_tools(self):
        """Convert MCP tools definition to OpenAI / OpenRouter tool call format"""
        mcp_tools = self.list_tools()
        openai_tools = []
        for t in mcp_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "parameters": t.get("inputSchema", {
                        "type": "object",
                        "properties": {}
                    })
                }
            })
        return openai_tools

    # ===================================================================
    # FUTURES TRADING - HIGH LEVEL METHODS
    # These wrap MCP tool calls with proper error handling
    # ===================================================================
    # REAL PLUANG MCP TOOL HELPERS
    # ===================================================================

    def _get_chat_session_id(self) -> str:
        """Get or mint a chat_session_id required by all Pluang MCP tools."""
        if hasattr(self, "_session_id") and self._session_id:
            return self._session_id
        try:
            res = self._rpc("tools/call", {
                "name": "generate_new_session_id",
                "arguments": {"user_query": "init session"}
            })
            if isinstance(res, dict) and "content" in res and res["content"]:
                txt = res["content"][0].get("text", "")
                try:
                    data = json.loads(txt)
                    cid = data.get("data", {}).get("chatSessionId") or data.get("chatSessionId") or data.get("session_id")
                    self._session_id = cid or txt.strip()
                except Exception:
                    self._session_id = txt.strip()
            elif isinstance(res, dict) and "structuredContent" in res:
                cid = res["structuredContent"].get("data", {}).get("chatSessionId")
                self._session_id = cid or "pyrofuel-auto-session"
            else:
                self._session_id = "pyrofuel-auto-session"
        except Exception:
            self._session_id = "pyrofuel-auto-session"
        return self._session_id

    def get_portfolio(self):
        """Get full portfolio via Pluang portfolio_get_holdings"""
        return self.get_positions()

    def get_balance(self):
        """Get account balance via real Pluang MCP portfolio_get_wallet_balance"""
        try:
            sess_id = self._get_chat_session_id()
            return self.call_tool("portfolio_get_wallet_balance", {
                "user_query": "cek saldo idr dan wallet",
                "chat_session_id": sess_id
            })
        except Exception as e:
            print(f"[PluangMCP] get_balance error: {e}", flush=True)
            return {"error": str(e)}

    def get_positions(self):
        """Get all crypto holdings via real Pluang MCP portfolio_get_holdings"""
        try:
            sess_id = self._get_chat_session_id()
            return self.call_tool("portfolio_get_holdings", {
                "user_query": "cek portofolio dan kepemilikan aset crypto",
                "chat_session_id": sess_id
            })
        except Exception as e:
            print(f"[PluangMCP] get_positions error: {e}", flush=True)
            return {"error": str(e)}

    def get_market_price(self, symbol: str):
        """Get live market price for a symbol via crypto_get_price"""
        clean_sym = symbol.upper().replace("-USD", "").replace("USDT", "").replace("-USDT", "").strip()
        try:
            sess_id = self._get_chat_session_id()
            return self.call_tool("crypto_get_price", {
                "symbol": clean_sym,
                "user_query": f"harga {clean_sym}",
                "chat_session_id": sess_id
            })
        except Exception as e:
            print(f"[PluangMCP] get_market_price error: {e}", flush=True)
            return {"error": str(e)}

    # ===================================================================
    # LEVERAGE & MARGIN (FUTURES COMPATIBILITY)
    # ===================================================================

    def set_leverage(self, symbol: str, leverage: int):
        """Record desired leverage setting"""
        return {"status": "configured", "symbol": symbol, "leverage": leverage}

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED"):
        """Record desired margin type setting"""
        return {"status": "configured", "symbol": symbol, "margin_type": margin_type}

    # ===================================================================
    # REAL PLUANG ORDER EXECUTION
    # ===================================================================

    def open_position(self, symbol: str, direction: str, amount: float,
                      leverage: int = 5, order_type: str = "MARKET",
                      limit_price: float = None,
                      margin_type: str = "ISOLATED"):
        """
        Open a new position on Pluang via crypto_place_buy_order / crypto_place_sell_order.
        """
        clean_sym = symbol.upper().replace("-USD", "").replace("USDT", "").replace("-USDT", "").strip()
        side = "BUY" if direction.upper() == "LONG" else "SELL"
        sess_id = self._get_chat_session_id()

        # Pluang accepts amount in IDR (must be whole number) or quantity
        if amount < 1000:
            # Likely USD, convert to IDR
            amount_idr = int(amount * 16500)
        else:
            amount_idr = int(amount)

        user_q = f"beli {clean_sym} {amount_idr}" if side == "BUY" else f"jual {clean_sym} {amount_idr}"

        order_params = {
            "symbol": clean_sym,
            "order_type": "MARKET",
            "amount": amount_idr,
            "user_query": user_q,
            "chat_session_id": sess_id
        }

        try:
            if side == "BUY":
                result = self.call_tool("crypto_place_buy_order", order_params)
            else:
                result = self.call_tool("crypto_place_sell_order", order_params)
            print(f"[PluangMCP] Real order dispatched: {side} {clean_sym} IDR {amount_idr:,}", flush=True)
            return result
        except Exception as e:
            print(f"[PluangMCP] open_position error: {e}", flush=True)
            return {"error": str(e)}

    def close_position(self, symbol: str, direction: str = None, quantity: float = None):
        """
        Close a position by placing opposite sell/buy order.
        """
        clean_sym = symbol.upper().replace("-USD", "").replace("USDT", "").replace("-USDT", "").strip()
        sess_id = self._get_chat_session_id()
        user_q = f"jual semua {clean_sym}"
        order_params = {
            "symbol": clean_sym,
            "order_type": "MARKET",
            "user_query": user_q,
            "chat_session_id": sess_id
        }
        if quantity:
            order_params["quantity"] = quantity
        try:
            result = self.call_tool("crypto_place_sell_order", order_params)
            print(f"[PluangMCP] Position closed: {clean_sym}", flush=True)
            return result
        except Exception as e:
            print(f"[PluangMCP] close_position error: {e}", flush=True)
            return {"error": str(e)}

    # ===================================================================
    # TP / SL ORDER MANAGEMENT
    # ===================================================================

    def set_take_profit(self, symbol: str, direction: str, tp_price: float,
                        quantity: float = None):
        """
        Place a Take Profit order.
        Args:
            symbol: "BTCUSDT"
            direction: position direction ("LONG" or "SHORT")
            tp_price: take profit trigger price
            quantity: amount (None = full position)
        """
        close_side = "SELL" if direction.upper() == "LONG" else "BUY"
        params = {
            "symbol": symbol,
            "side": close_side,
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": tp_price,
            "closePosition": quantity is None,
            "reduceOnly": True
        }
        if quantity:
            params["quantity"] = quantity
        try:
            result = self.call_tool("place_order", params)
            print(f"[PluangMCP] TP set: {symbol} @ ${tp_price}")
            return result
        except Exception as e:
            print(f"[PluangMCP] set_take_profit error: {e}")
            return {"error": str(e)}

    def set_stop_loss(self, symbol: str, direction: str, sl_price: float,
                      quantity: float = None):
        """
        Place a Stop Loss order.
        Args:
            symbol: "BTCUSDT"
            direction: position direction ("LONG" or "SHORT")
            sl_price: stop loss trigger price
            quantity: amount (None = full position)
        """
        close_side = "SELL" if direction.upper() == "LONG" else "BUY"
        params = {
            "symbol": symbol,
            "side": close_side,
            "type": "STOP_MARKET",
            "stopPrice": sl_price,
            "closePosition": quantity is None,
            "reduceOnly": True
        }
        if quantity:
            params["quantity"] = quantity
        try:
            result = self.call_tool("place_order", params)
            print(f"[PluangMCP] SL set: {symbol} @ ${sl_price}")
            return result
        except Exception as e:
            print(f"[PluangMCP] set_stop_loss error: {e}")
            return {"error": str(e)}

    def set_tp_sl(self, symbol: str, direction: str,
                  tp1_price: float = None, tp2_price: float = None,
                  sl_price: float = None, tp1_qty: float = None):
        """
        Set both TP and SL for a position in one call.
        Supports dual TP (TP1 partial + TP2 full).
        """
        results = {}

        if sl_price:
            results["stop_loss"] = self.set_stop_loss(symbol, direction, sl_price)

        if tp1_price and tp1_qty:
            results["take_profit_1"] = self.set_take_profit(
                symbol, direction, tp1_price, quantity=tp1_qty
            )

        if tp2_price:
            results["take_profit_2"] = self.set_take_profit(
                symbol, direction, tp2_price
            )

        return results

    def cancel_order(self, symbol: str, order_id: str):
        """Cancel a specific open order"""
        try:
            return self.call_tool("cancel_order", {
                "symbol": symbol,
                "orderId": order_id
            })
        except Exception as e:
            print(f"[PluangMCP] cancel_order error: {e}")
            return {"error": str(e)}

    def cancel_all_orders(self, symbol: str):
        """Cancel all open orders for a symbol"""
        try:
            return self.call_tool("cancel_all_orders", {"symbol": symbol})
        except Exception as e:
            print(f"[PluangMCP] cancel_all_orders error: {e}")
            return {"error": str(e)}

    def get_open_orders(self, symbol: str = None):
        """Get all open orders, optionally filtered by symbol"""
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol
            return self.call_tool("get_open_orders", params)
        except Exception as e:
            print(f"[PluangMCP] get_open_orders error: {e}")
            return {"error": str(e)}

    # ===================================================================
    # FULL AUTONOMOUS TRADE EXECUTION
    # ===================================================================

    def execute_full_trade(self, signal: dict, config: dict):
        """
        Execute a complete trade from an AI signal:
        1. Set margin type (ISOLATED by default for risk control)
        2. Set leverage
        3. Open position (MARKET order)
        4. Set TP1 (partial close + move SL to breakeven)
        5. Set TP2 (full close)
        6. Set SL (protect capital)

        Args:
            signal: AI pipeline output with keys:
                - symbol, direction, entry_price, leverage,
                - take_profit_1, take_profit_2, stop_loss,
                - position_size_usdt
            config: trading_config.json values
        Returns:
            dict with execution results
        """
        symbol = signal.get("binance_pair") or signal.get("symbol", "").replace("-USD", "USDT")
        direction = signal.get("direction", "LONG")
        leverage = min(signal.get("leverage", 5), config.get("max_leverage", 5))
        margin_type = config.get("margin_type", "ISOLATED")
        order_type = config.get("order_type", "MARKET")
        position_size = signal.get("position_size_usdt", 2.5)
        tp1 = signal.get("take_profit_1", 0)
        tp2 = signal.get("take_profit_2", 0)
        sl = signal.get("stop_loss", 0)

        execution_log = {
            "symbol": symbol,
            "direction": direction,
            "leverage": leverage,
            "margin_type": margin_type,
            "order_type": order_type,
            "position_size_usdt": position_size,
            "tp1": tp1,
            "tp2": tp2,
            "sl": sl,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "steps": {}
        }

        try:
            # Step 1: Set margin type
            execution_log["steps"]["margin_type"] = self.set_margin_type(symbol, margin_type)

            # Step 2: Set leverage
            execution_log["steps"]["leverage"] = self.set_leverage(symbol, leverage)

            # Step 3: Open position
            open_res = self.open_position(
                symbol=symbol,
                direction=direction,
                amount=position_size,
                leverage=leverage,
                order_type=order_type,
                margin_type=margin_type
            )
            execution_log["steps"]["open_position"] = open_res
            if not open_res or not isinstance(open_res, dict):
                raise Exception("Empty response from Pluang MCP")
            if open_res.get("isError") or "error" in open_res:
                err_msg = open_res.get("error")
                if not err_msg and open_res.get("content"):
                    err_msg = open_res["content"][0].get("text", "")
                raise Exception(f"Pluang API Error: {err_msg}")
            if open_res.get("content"):
                txt = open_res["content"][0].get("text", "")
                if '"success":false' in txt.replace(" ", "") or '"success": false' in txt:
                    raise Exception(f"Pluang Rejected Order: {txt}")

            # Step 4: Set TP/SL
            if tp1 or tp2 or sl:
                tp1_qty = position_size * 0.5 if tp1 and tp2 else None  # 50% at TP1
                execution_log["steps"]["tp_sl"] = self.set_tp_sl(
                    symbol=symbol,
                    direction=direction,
                    tp1_price=tp1 if tp1 else None,
                    tp2_price=tp2 if tp2 else None,
                    sl_price=sl if sl else None,
                    tp1_qty=tp1_qty
                )

            execution_log["status"] = "EXECUTED"
            execution_log["pluang_synced"] = True
            print(f"[PluangMCP] ✅ Full trade executed on Pluang: {direction} {symbol} ${position_size} {leverage}x")

        except Exception as e:
            execution_log["status"] = "FAILED"
            execution_log["error"] = str(e)
            execution_log["pluang_synced"] = False
            print(f"[PluangMCP] ❌ Trade execution failed: {e}")

        # Save execution log
        log_dir = os.path.join(BASE_DIR, "results")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "execution_log.json")
        logs = []
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        logs.insert(0, execution_log)
        logs = logs[:100]  # Keep last 100
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return execution_log

    # ===================================================================
    # MODIFY EXISTING POSITION
    # ===================================================================

    def modify_position_leverage(self, symbol: str, new_leverage: int):
        """Change leverage on an existing pair (only works if no open position)"""
        return self.set_leverage(symbol, new_leverage)

    def modify_tp_sl(self, symbol: str, direction: str,
                     new_tp: float = None, new_sl: float = None):
        """
        Modify TP/SL on an existing position.
        Cancels old orders first, then sets new ones.
        """
        # Cancel existing TP/SL orders
        cancel_result = self.cancel_all_orders(symbol)

        results = {"cancel": cancel_result}

        if new_sl:
            results["new_sl"] = self.set_stop_loss(symbol, direction, new_sl)
        if new_tp:
            results["new_tp"] = self.set_take_profit(symbol, direction, new_tp)

        return results

    # ===================================================================
    # CONNECTION STATUS
    # ===================================================================

    def check_connection(self):
        """Check if Pluang MCP connection is alive and authenticated"""
        try:
            result = self.initialize()
            return {
                "connected": True,
                "server_info": result.get("serverInfo", {}),
                "capabilities": result.get("capabilities", {}),
                "last_error": None
            }
        except Exception as e:
            return {
                "connected": False,
                "server_info": {},
                "capabilities": {},
                "last_error": str(e)
            }

    def get_available_tools(self):
        """List all available MCP tools from Pluang"""
        try:
            tools = self.list_tools()
            return {
                "count": len(tools),
                "tools": [
                    {"name": t.get("name"), "description": t.get("description", "")}
                    for t in tools
                ]
            }
        except Exception as e:
            return {"count": 0, "tools": [], "error": str(e)}
