"""
===========================================================================
PYROFUEL BINANCE FUTURES CLIENT v1.0 - FULL NATIVE EXECUTION ENGINE
===========================================================================
Official Binance USDT-Margined Perpetual Futures REST Client:
- HMAC-SHA256 authenticated (pure standard library + requests)
- Full account wallet balance & margin monitoring
- Live position tracker & floating PnL
- Dynamic leverage configuration (1x-125x)
- Margin type configuration (ISOLATED / CROSSED)
- Market & Limit order execution for both LONG and SHORT
- Native Take Profit & Stop Loss order placement (reduceOnly)
- Position close / emergency flat
- Dual-mode support (Live Trading vs Testnet)
===========================================================================
"""
import os
import time
import hmac
import hashlib
import requests
import socket
from urllib.parse import urlencode
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------
# ISP DNS Poisoning / DPI Bypass via DNS-over-HTTPS
# ---------------------------------------------------------
_orig_getaddrinfo = socket.getaddrinfo
_dns_cache = {
    "fapi.binance.com": "65.8.76.49",
    "fapi1.binance.com": "65.8.76.14",
    "fapi2.binance.com": "65.8.76.6",
    "fapi3.binance.com": "65.8.76.4",
}

def _resolve_doh(domain: str):
    if domain in _dns_cache:
        return _dns_cache[domain]
    for doh_url in [
        f"https://1.1.1.1/dns-query?name={domain}&type=A",
        f"https://dns.google/resolve?name={domain}&type=A"
    ]:
        try:
            r = requests.get(doh_url, headers={"accept": "application/dns-json"}, timeout=3)
            data = r.json()
            ips = [ans["data"] for ans in data.get("Answer", []) if ans.get("type") == 1]
            if ips:
                _dns_cache[domain] = ips[0]
                return ips[0]
        except Exception:
            continue
    return None

def _custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and ("binance" in host.lower()):
        ip = _resolve_doh(host)
        if ip:
            return _orig_getaddrinfo(ip, port, family, type, proto, flags)
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _custom_getaddrinfo

# Auto-load .env without third-party dependencies
def _load_env_fallback():
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_load_env_fallback()



class BinanceFuturesClient:
    def __init__(self, api_key: str = None, api_secret: str = None, testnet: bool = False, verify_ssl: bool = False):
        self.api_key = api_key or os.environ.get("BINANCE_API_KEY", "").strip()
        self.api_secret = api_secret or os.environ.get("BINANCE_API_SECRET", "").strip()
        self.testnet = testnet
        self.verify_ssl = verify_ssl
        
        if self.testnet:
            self.base_url = "https://testnet.binancefuture.com"
            self.endpoints = ["https://testnet.binancefuture.com"]
        else:
            self.base_url = "https://fapi.binance.com"
            self.endpoints = [
                "https://fapi.binance.com",
                "https://fapi1.binance.com",
                "https://fapi2.binance.com",
                "https://fapi3.binance.com"
            ]
            
        self.session = requests.Session()
        self.session.verify = self.verify_ssl
        if not self.verify_ssl:
            import urllib3
        if self.api_key:
            self.session.headers.update({
                "X-MBX-APIKEY": self.api_key,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "PyrofuelFutures/1.0"
            })
            
        self._symbol_cache = {}
        self._symbol_cache_time = 0

    def normalize_symbol(self, symbol: str) -> str:
        """
        Normalize symbol into standard Binance USDT Perpetual format.
        Handles aliases like PEPE -> 1000PEPEUSDT, BONK -> 1000BONKUSDT, etc.
        """
        if not symbol:
            return "BTCUSDT"
        sym = symbol.upper().strip().replace("-USD", "").replace("USDT", "")
        # Well known 1000x futures contracts on Binance
        k1000_coins = {
            "PEPE": "1000PEPEUSDT",
            "SHIB": "1000SHIBUSDT",
            "BONK": "1000BONKUSDT",
            "FLOKI": "1000FLOKIUSDT",
            "LUNC": "1000LUNCUSDT",
            "SATS": "1000SATSUSDT",
            "RATS": "1000RATSUSDT",
            "CAT": "1000CATUSDT",
            "MOG": "1000000MOGUSDT",
            "CHEEMS": "1000000CHEEMSUSDT",
        }
        if sym in k1000_coins:
            return k1000_coins[sym]
        if sym.startswith("1000") and sym[4:] in k1000_coins:
            return sym + "USDT"
        return sym + "USDT"

    def get_symbol_filters(self, symbol: str) -> dict:
        """Fetch and cache LOT_SIZE, PRICE_FILTER, and MIN_NOTIONAL for symbol"""
        sym = self.normalize_symbol(symbol)
        now = time.time()
        if not self._symbol_cache or (now - self._symbol_cache_time > 1800):
            try:
                res = self.get_exchange_info()
                if isinstance(res, dict) and "symbols" in res:
                    for s in res["symbols"]:
                        s_name = s.get("symbol")
                        lot = next((f for f in s.get("filters", []) if f["filterType"] == "LOT_SIZE"), None)
                        p_filt = next((f for f in s.get("filters", []) if f["filterType"] == "PRICE_FILTER"), None)
                        min_not = next((f for f in s.get("filters", []) if f["filterType"] == "MIN_NOTIONAL"), None)
                        self._symbol_cache[s_name] = {
                            "quantityPrecision": s.get("quantityPrecision", 3),
                            "pricePrecision": s.get("pricePrecision", 2),
                            "stepSize": float(lot["stepSize"]) if lot else 0.001,
                            "minQty": float(lot["minQty"]) if lot else 0.001,
                            "tickSize": float(p_filt["tickSize"]) if p_filt else 0.01,
                            "minNotional": float(min_not.get("notional", 5.0)) if min_not else 5.0
                        }
                    self._symbol_cache_time = now
            except Exception as e:
                print(f"[BinanceFutures] ⚠️ ExchangeInfo caching error: {e}", flush=True)

        return self._symbol_cache.get(sym, {
            "quantityPrecision": 3,
            "pricePrecision": 2,
            "stepSize": 0.001,
            "minQty": 0.001,
            "tickSize": 0.01,
            "minNotional": 5.0
        })

    def format_quantity(self, symbol: str, raw_quantity: float) -> float:
        """Format quantity strictly adhering to symbol's stepSize, minQty, and precision"""
        rules = self.get_symbol_filters(symbol)
        step = rules["stepSize"]
        prec = rules["quantityPrecision"]
        min_qty = rules["minQty"]
        
        # Round down to nearest step
        import math
        steps = math.floor(raw_quantity / step)
        qty = steps * step
        if qty < min_qty:
            qty = min_qty
            
        if prec == 0:
            return float(int(round(qty)))
        return round(qty, prec)

    def format_price(self, symbol: str, raw_price: float) -> float:
        """Format price strictly adhering to symbol's tickSize and precision"""
        rules = self.get_symbol_filters(symbol)
        tick = rules["tickSize"]
        prec = rules["pricePrecision"]
        
        steps = round(raw_price / tick)
        price = steps * tick
        if prec == 0:
            return float(int(round(price)))
        return round(price, prec)

    def _sync_server_time(self):
        """Synchronize local timestamp offset with Binance server time to eliminate -1021 recvWindow errors"""
        for ep in self.endpoints:
            try:
                r = self.session.get(f"{ep}/fapi/v1/time", timeout=5)
                st = r.json().get("serverTime")
                if st:
                    self.time_offset = int(st - (time.time() * 1000))
                    return self.time_offset
            except Exception:
                continue
        self.time_offset = 0
        return 0

    def _sign(self, params: dict) -> dict:
        """Add timestamp, recvWindow, and HMAC-SHA256 signature to query parameters with auto time synchronization"""
        if not hasattr(self, "time_offset"):
            self._sync_server_time()
        params["recvWindow"] = 60000
        params["timestamp"] = int(time.time() * 1000 + getattr(self, "time_offset", 0))
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _request(self, method: str, endpoint: str, params: dict = None, signed: bool = False, retry_time: bool = True):
        """Execute HTTP request against Binance Futures REST API with multi-endpoint failover and clock skew retry"""
        params = params or {}
        
        if signed:
            if not self.api_key or not self.api_secret:
                raise ValueError("Binance API Key and Secret are required for private endpoints!")
            params = self._sign(params.copy())

        last_error = None
        for base in self.endpoints:
            url = f"{base}{endpoint}"
            try:
                if method.upper() == "GET":
                    resp = self.session.get(url, params=params, timeout=10)
                elif method.upper() == "POST":
                    resp = self.session.post(url, data=params, timeout=10)
                elif method.upper() == "DELETE":
                    resp = self.session.delete(url, params=params, timeout=10)
                else:
                    resp = self.session.request(method, url, params=params, timeout=10)
                    
                data = resp.json()
                if resp.status_code >= 400:
                    err_msg = data.get("msg") or data.get("message") or resp.text
                    err_code = data.get("code", resp.status_code)
                    if err_code == -1021 and retry_time:
                        print("[BinanceFutures] 🔄 -1021 Timestamp error detected. Resyncing server clock and retrying...", flush=True)
                        self._sync_server_time()
                        return self._request(method, endpoint, params, signed=signed, retry_time=False)
                    print(f"[BinanceFutures] [ERROR {err_code}]: {err_msg}", flush=True)
                    return {"isError": True, "error": err_msg, "code": err_code}
                    
                return data
            except Exception as e:
                last_error = e
                continue

        print(f"[BinanceFutures] [NETWORK ERROR] ({endpoint}): {last_error}", flush=True)
        return {"isError": True, "error": str(last_error)}

    # ===================================================================
    # PUBLIC MARKET DATA & UNIVERSE
    # ===================================================================

    def ping(self):
        """Test connectivity to Binance Futures"""
        return self._request("GET", "/fapi/v1/ping")

    def get_server_time(self):
        """Check server time synchronization"""
        return self._request("GET", "/fapi/v1/time")

    def get_exchange_info(self):
        """Fetch all tradable USDT Perpetual Futures pairs and specifications"""
        return self._request("GET", "/fapi/v1/exchangeInfo")

    def get_market_price(self, symbol: str):
        """Get latest mark price for symbol (e.g. BTCUSDT)"""
        sym = self.normalize_symbol(symbol)
        res = self._request("GET", "/fapi/v1/premiumIndex", {"symbol": sym})
        if isinstance(res, dict) and "markPrice" in res:
            return float(res["markPrice"])
        return 0.0

    # ===================================================================
    # ACCOUNT & WALLET BALANCES
    # ===================================================================

    def get_account(self):
        """Get full account status, risk limits, and positions"""
        return self._request("GET", "/fapi/v2/account", signed=True)

    def get_balance(self):
        """
        Get wallet balances. Returns USDT total, available, and unrealized PnL.
        """
        res = self._request("GET", "/fapi/v2/balance", signed=True)
        if isinstance(res, list):
            usdt_wallet = next((b for b in res if b.get("asset") == "USDT"), None)
            if usdt_wallet:
                return {
                    "asset": "USDT",
                    "total_wallet_balance": float(usdt_wallet.get("balance", 0)),
                    "available_balance": float(usdt_wallet.get("availableBalance", 0)),
                    "cross_unrealized_pnl": float(usdt_wallet.get("crossUnPnl", 0)),
                    "max_withdraw_amount": float(usdt_wallet.get("maxWithdrawAmount", 0)),
                    "raw": usdt_wallet
                }
        return res

    def get_positions(self):
        """
        Get all currently OPEN positions (positionAmt != 0).
        """
        res = self._request("GET", "/fapi/v2/positionRisk", signed=True)
        if isinstance(res, list):
            open_positions = []
            for p in res:
                amt = float(p.get("positionAmt", 0))
                if amt != 0:
                    open_positions.append({
                        "symbol": p.get("symbol"),
                        "direction": "LONG" if amt > 0 else "SHORT",
                        "position_amount": abs(amt),
                        "entry_price": float(p.get("entryPrice", 0)),
                        "mark_price": float(p.get("markPrice", 0)),
                        "unrealized_pnl": float(p.get("unRealizedProfit", 0)),
                        "liquidation_price": float(p.get("liquidationPrice", 0)),
                        "leverage": int(p.get("leverage", 1)),
                        "margin_type": p.get("marginType", "isolated").upper(),
                        "isolated_margin": float(p.get("isolatedMargin", 0))
                    })
            return open_positions
        return res

    # ===================================================================
    # LEVERAGE & MARGIN SETTINGS
    # ===================================================================

    def set_leverage(self, symbol: str, leverage: int):
        """
        Set leverage for a futures pair (1x to 125x depending on symbol limits).
        """
        sym = self.normalize_symbol(symbol)
        params = {"symbol": sym, "leverage": int(leverage)}
        res = self._request("POST", "/fapi/v1/leverage", params=params, signed=True)
        if isinstance(res, dict) and "leverage" in res:
            print(f"[BinanceFutures] ✅ Leverage set for {sym}: {res['leverage']}x", flush=True)
        return res

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED"):
        """
        Set margin type: ISOLATED or CROSSED.
        """
        sym = self.normalize_symbol(symbol)
        m_type = margin_type.upper()
        if m_type == "CROSS":
            m_type = "CROSSED"
        params = {"symbol": sym, "marginType": m_type}
        res = self._request("POST", "/fapi/v1/marginType", params=params, signed=True)
        # Note: Code -4046 means 'No need to change margin type' which is normal
        if isinstance(res, dict) and (res.get("code") == 200 or res.get("code") == -4046 or res.get("msg") == "success"):
            print(f"[BinanceFutures] ✅ Margin type for {sym}: {m_type}", flush=True)
        return res

    # ===================================================================
    # ORDER EXECUTION (LONG, SHORT, TP, SL)
    # ===================================================================

    def open_position(self, symbol: str, direction: str, quantity: float,
                      leverage: int = 5, order_type: str = "MARKET",
                      limit_price: float = None, margin_type: str = "ISOLATED"):
        """
        Open a real FUTURES position on Binance:
        - LONG  → BUY order
        - SHORT → SELL order
        """
        sym = self.normalize_symbol(symbol)
        side = "BUY" if direction.upper() == "LONG" else "SELL"
        
        # 1. Pre-configure margin & leverage
        try:
            self.set_margin_type(sym, margin_type)
        except Exception:
            pass
        try:
            self.set_leverage(sym, leverage)
        except Exception:
            pass

        # 2. Format quantity strictly adhering to LOT_SIZE filter
        fmt_qty = self.format_quantity(sym, quantity)

        # 3. Build order
        params = {
            "symbol": sym,
            "side": side,
            "type": order_type.upper(),
            "quantity": fmt_qty if self.get_symbol_filters(sym)["quantityPrecision"] > 0 else int(fmt_qty)
        }
        
        if order_type.upper() == "LIMIT":
            if not limit_price or limit_price <= 0:
                raise ValueError("Limit price required for LIMIT order")
            params["price"] = str(self.format_price(sym, limit_price))
            params["timeInForce"] = "GTC"
            
        print(f"[BinanceFutures] 🚀 Sending {direction} {sym} Qty:{params['quantity']} (Lev {leverage}x, Type {order_type})...", flush=True)
        res = self._request("POST", "/fapi/v1/order", params=params, signed=True)
        if isinstance(res, dict) and "orderId" in res:
            print(f"[BinanceFutures] ✅ Order FILLED/SUBMITTED! Order ID: {res.get('orderId')}, Status: {res.get('status')}", flush=True)
        return res

    def set_take_profit(self, symbol: str, direction: str, trigger_price: float, quantity: float = None):
        """
        Place Take Profit Market order via Binance Algo Order API (/fapi/v1/algoOrder).
        - If position was LONG → TP is a SELL
        - If position was SHORT → TP is a BUY
        """
        sym = self.normalize_symbol(symbol)
        side = "SELL" if direction.upper() == "LONG" else "BUY"
        fmt_price = self.format_price(sym, trigger_price)
        params = {
            "algoType": "CONDITIONAL",
            "symbol": sym,
            "side": side,
            "type": "TAKE_PROFIT_MARKET",
            "triggerPrice": str(fmt_price),
            "closePosition": "true" if quantity is None else "false"
        }
        if quantity is not None:
            fmt_qty = self.format_quantity(sym, quantity)
            params["quantity"] = fmt_qty if self.get_symbol_filters(sym)["quantityPrecision"] > 0 else int(fmt_qty)
            params["reduceOnly"] = "true"
            params.pop("closePosition", None)
            
        res = self._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)
        if isinstance(res, dict) and "algoId" in res:
            print(f"[BinanceFutures] 🎯 Take Profit Algo Order set at ${fmt_price} (Algo ID: {res.get('algoId')})", flush=True)
        return res

    def set_stop_loss(self, symbol: str, direction: str, trigger_price: float, quantity: float = None):
        """
        Place Stop Loss Market order via Binance Algo Order API (/fapi/v1/algoOrder).
        - If position was LONG → SL is a SELL
        - If position was SHORT → SL is a BUY
        """
        sym = self.normalize_symbol(symbol)
        side = "SELL" if direction.upper() == "LONG" else "BUY"
        fmt_price = self.format_price(sym, trigger_price)
        params = {
            "algoType": "CONDITIONAL",
            "symbol": sym,
            "side": side,
            "type": "STOP_MARKET",
            "triggerPrice": str(fmt_price),
            "closePosition": "true" if quantity is None else "false"
        }
        if quantity is not None:
            fmt_qty = self.format_quantity(sym, quantity)
            params["quantity"] = fmt_qty if self.get_symbol_filters(sym)["quantityPrecision"] > 0 else int(fmt_qty)
            params["reduceOnly"] = "true"
            params.pop("closePosition", None)
            
        res = self._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)
        if isinstance(res, dict) and "algoId" in res:
            print(f"[BinanceFutures] 🛡️ Stop Loss Algo Order set at ${fmt_price} (Algo ID: {res.get('algoId')})", flush=True)
        return res

    def close_position(self, symbol: str, direction: str, quantity: float = None):
        """
        Instantly close a position at MARKET price with reduceOnly.
        """
        sym = self.normalize_symbol(symbol)
        side = "SELL" if direction.upper() == "LONG" else "BUY"
        params = {
            "symbol": sym,
            "side": side,
            "type": "MARKET",
            "reduceOnly": "true"
        }
        if quantity is None:
            try:
                positions = self.get_positions()
                if isinstance(positions, list):
                    for p in positions:
                        if p.get("symbol") == sym:
                            quantity = abs(float(p.get("position_amount", 0)))
                            break
            except Exception:
                pass
        if quantity is None or quantity <= 0:
            return {"isError": True, "error": f"No active position found on Binance to close for {sym}"}
        fmt_qty = self.format_quantity(sym, quantity)
        params["quantity"] = fmt_qty if self.get_symbol_filters(sym)["quantityPrecision"] > 0 else int(fmt_qty)
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def cancel_all_orders(self, symbol: str):
        """Cancel all pending regular and algo TP/SL orders for a symbol"""
        sym = self.normalize_symbol(symbol)
        # 1. Cancel standard orders
        res_std = self._request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": sym}, signed=True)
        # 2. Cancel algo / conditional orders
        try:
            res_algo = self._request("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": sym}, signed=True)
        except Exception:
            res_algo = None
        return {"standard": res_std, "algo": res_algo}

    # ===================================================================
    # FULL AUTONOMOUS PIPELINE EXECUTION
    # ===================================================================

    def execute_full_trade(self, signal: dict, config: dict):
        """
        Execute full quantitative trade directly on Binance Futures:
        1. Set Margin Type (ISOLATED)
        2. Set Leverage (AI decided, e.g. 5x-20x)
        3. Dynamically adjust Position Size based on live wallet balance
        4. Calculate exact compliant quantity with stepSize & precision
        5. Place Market / Limit Order
        6. Place Native TP and SL orders on Binance
        """
        raw_sym = signal.get("binance_pair") or signal.get("symbol", "")
        symbol = self.normalize_symbol(raw_sym)
        direction = signal.get("direction", "LONG").upper()
        leverage = int(signal.get("leverage") or config.get("max_leverage", 5))
        margin_type = signal.get("margin_type") or config.get("margin_type", "ISOLATED")
        order_type = (signal.get("order_type") or config.get("order_type", "MARKET")).upper()
        limit_price = float(signal.get("limit_price") or signal.get("entry_price", 0))
        
        # Position size in USDT (e.g. $10, $50, etc.)
        pos_size_usd = float(signal.get("position_size_usdt") or signal.get("position_size_usd") or 10.0)
        
        # 1. Check if already in position for this symbol
        try:
            acc = self.get_account()
            for p in acc.get("positions", []):
                if p.get("symbol") == symbol and abs(float(p.get("positionAmt", 0))) > 0:
                    print(f"[BinanceFutures] ℹ️ Skipping trade: Position already active for {symbol} (Amt: {p.get('positionAmt')})", flush=True)
                    return {
                        "status": "SKIPPED_ALREADY_OPEN",
                        "error": f"Position already active for {symbol} (Amt: {p.get('positionAmt')})",
                        "binance_synced": True
                    }
        except Exception:
            pass

        # 2. Check live wallet balance for safe sizing
        avail_usdt = 100.0
        try:
            bal_info = self.get_balance()
            if isinstance(bal_info, dict) and "available_balance" in bal_info:
                avail_usdt = float(bal_info["available_balance"])
                if avail_usdt < 1.0:
                    print(f"[BinanceFutures] ℹ️ Insufficient available margin (${avail_usdt:.2f} USDT). Skipping new entry until funds are freed.", flush=True)
                    return {
                        "status": "REJECTED_LOW_BALANCE",
                        "error": f"Available margin ${avail_usdt:.2f} is insufficient to open new positions safely (Min $1.00 USDT required)",
                        "binance_synced": False
                    }
                # Keep safety buffer for fees and maintenance margin
                max_safe_margin = max(1.0, round(avail_usdt * 0.90, 2))
                if pos_size_usd > max_safe_margin:
                    print(f"[BinanceFutures] ℹ️ Auto-sizing margin from ${pos_size_usd:.2f} to ${max_safe_margin:.2f} USDT (Avail: ${avail_usdt:.2f})", flush=True)
                    pos_size_usd = max_safe_margin
        except Exception as e:
            print(f"[BinanceFutures] ⚠️ Balance check warning: {e}", flush=True)

        # 3. Get live mark price
        mark_price = self.get_market_price(symbol)
        if mark_price <= 0 and limit_price > 0:
            mark_price = limit_price
            
        if mark_price <= 0:
            return {"status": "FAILED", "error": f"Could not determine market price for {symbol}", "binance_synced": False}

        # 4. Symbol rules from exchangeInfo
        rules = self.get_symbol_filters(symbol)
        min_notional = rules.get("minNotional", 5.0)

        # Total notional = margin * leverage
        notional_usd = pos_size_usd * leverage
        
        # Ensure notional meets Binance minimum requirement (e.g. $5)
        if notional_usd < min_notional:
            needed_margin = (min_notional * 1.05) / leverage
            if needed_margin <= avail_usdt:
                notional_usd = min_notional * 1.05
                pos_size_usd = round(needed_margin, 2)
            else:
                print(f"[BinanceFutures] ℹ️ Required notional (${min_notional}) exceeds available margin capacity. Skipping.", flush=True)
                return {
                    "status": "REJECTED_NOTIONAL_CAPACITY",
                    "error": f"Required margin ${needed_margin:.2f} exceeds available margin ${avail_usdt:.2f}",
                    "binance_synced": False
                }
            
        raw_quantity = notional_usd / mark_price
        quantity = self.format_quantity(symbol, raw_quantity)
        
        # Re-check notional after rounding
        if (quantity * mark_price) < min_notional:
            quantity = self.format_quantity(symbol, (min_notional * 1.05) / mark_price)
            
        tp = float(signal.get("take_profit") or signal.get("take_profit_2") or signal.get("take_profit_1", 0))
        sl = float(signal.get("stop_loss", 0))

        execution_log = {
            "exchange": "BINANCE_FUTURES",
            "symbol": symbol,
            "direction": direction,
            "leverage": leverage,
            "margin_type": margin_type,
            "order_type": order_type,
            "entry_price": mark_price,
            "quantity": quantity,
            "position_size_usdt": pos_size_usd,
            "notional_usdt": round(quantity * mark_price, 2),
            "take_profit": tp,
            "stop_loss": sl,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "steps": {}
        }

        try:
            # 1. Open Position
            order_res = self.open_position(
                symbol=symbol,
                direction=direction,
                quantity=quantity,
                leverage=leverage,
                order_type=order_type,
                limit_price=limit_price if order_type == "LIMIT" else None,
                margin_type=margin_type
            )
            execution_log["steps"]["open_position"] = order_res
            
            if order_res.get("isError"):
                raise Exception(order_res.get("error", "Unknown Binance error"))
                
            order_id = order_res.get("orderId")
            if not order_id:
                raise Exception(f"Binance order rejected or failed to return orderId: {order_res}")
            execution_log["order_id"] = order_id

            # 2. Set TP Order
            if tp > 0:
                try:
                    tp_res = self.set_take_profit(symbol, direction, trigger_price=tp)
                    execution_log["steps"]["take_profit"] = tp_res
                except Exception as e:
                    print(f"[BinanceFutures] ⚠️ TP placement notice: {e}")

            # 3. Set SL Order
            if sl > 0:
                try:
                    sl_res = self.set_stop_loss(symbol, direction, trigger_price=sl)
                    execution_log["steps"]["stop_loss"] = sl_res
                except Exception as e:
                    print(f"[BinanceFutures] ⚠️ SL placement notice: {e}")

            execution_log["status"] = "EXECUTED"
            execution_log["binance_synced"] = True
            print(f"[BinanceFutures] 🎉 FULL TRADE EXECUTED ON BINANCE: {direction} {symbol} ({leverage}x, Qty: {quantity}, Notional: ${execution_log['notional_usdt']})", flush=True)

        except Exception as e:
            execution_log["status"] = "FAILED"
            execution_log["error"] = str(e)
            execution_log["binance_synced"] = False
            print(f"[BinanceFutures] ❌ Execution failed: {e}", flush=True)

        return execution_log
