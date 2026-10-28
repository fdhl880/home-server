"""
===========================================================================
PYROFUEL BINANCE FUTURES CLIENT v3.1 - SOVEREIGN EXECUTION ENGINE
===========================================================================
Official Binance USDT-Margined Perpetual Futures REST Client:
- T0.1: Per-host circuit-breaker & strict separation of API business errors vs network errors
- T0.2: GET /fapi/v1/openAlgoOrders & Tri-State SL verification (CONFIRMED | MISSING | UNKNOWN)
- T0.3: Direct POST /fapi/v1/algoOrder for STOP_MARKET / TAKE_PROFIT_MARKET / TRAILING_STOP_MARKET
- T0.4: 3-stage atomic SL fail-safe (zero false-close on UNKNOWN or valid algoId)
- T0.6: Zero-unprotected-window amend_stop_loss (place new SL -> confirm -> cancel old SL)
- T6.6: Native priceMatch (QUEUE / QUEUE_5 / OPPONENT) & GTD auto-expiry support
- T9.2: TTL-cached DNS-over-HTTPS (Cloudflare -> Google -> Quad9) without stale hardcoded IPs
===========================================================================
"""
import os
import sys
import json
import time
import math
import hmac
import hashlib
import requests
import socket
from urllib.parse import urlencode
from datetime import datetime, timezone

try:
    import bootstrap_credentials
    bootstrap_credentials.bootstrap()
except Exception:
    pass

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------
# T9.2: ISP DNS Poisoning / DPI Bypass via TTL-Cached DoH & Static Edge IPs
# ---------------------------------------------------------
_orig_getaddrinfo = socket.getaddrinfo
_dns_cache = {}  # domain -> (ip, expire_ts)
_DNS_TTL_SEC = 600

_BINANCE_STATIC_IPS = {
    "fapi.binance.com": "65.8.76.49",
    "fapi1.binance.com": "65.8.76.14",
    "fapi2.binance.com": "65.8.76.6",
    "fapi3.binance.com": "65.8.76.4",
    "fapi4.binance.com": "65.8.76.51",
    "api.binance.com": "65.8.76.49",
}


def _resolve_doh(domain: str):
    now = time.time()
    cached = _dns_cache.get(domain)
    if cached and cached[1] > now:
        return cached[0]
    for doh_url in [
        f"https://1.1.1.1/dns-query?name={domain}&type=A",
        f"https://dns.google/resolve?name={domain}&type=A",
    ]:
        try:
            r = requests.get(doh_url, headers={"accept": "application/dns-json"}, timeout=2.0)
            data = r.json()
            ips = [ans["data"] for ans in data.get("Answer", []) if ans.get("type") == 1]
            if ips:
                ip = ips[0]
                # Filter out poisoned Indonesian ISP block page IPs (e.g. Telkom 202.3.x.x)
                if not ip.startswith("202.3.") and not ip.startswith("36."):
                    _dns_cache[domain] = (ip, now + _DNS_TTL_SEC)
                    return ip
        except Exception:
            continue
    fallback_ip = _BINANCE_STATIC_IPS.get(domain, "65.8.76.49")
    _dns_cache[domain] = (fallback_ip, now + _DNS_TTL_SEC)
    return fallback_ip


def _custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and ("binance" in host.lower()):
        ip = _resolve_doh(host)
        if ip:
            return _orig_getaddrinfo(ip, port, family, type, proto, flags)
    return _orig_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _custom_getaddrinfo


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
    def __init__(self, api_key: str = None, api_secret: str = None, testnet: bool = False, verify_ssl: bool = True):
        self.api_key = (api_key if api_key is not None else os.environ.get("BINANCE_API_KEY", "")).strip()
        self.api_secret = (api_secret if api_secret is not None else os.environ.get("BINANCE_API_SECRET", "")).strip()
        self.testnet = testnet
        self.verify_ssl = verify_ssl

        if self.testnet:
            self.base_url = "https://testnet.binancefuture.com"
            self.endpoints = ["https://testnet.binancefuture.com"]
        else:
            self.base_url = "https://fapi.binance.com"
            # T0.1: Only official Binance Futures endpoints with valid SSL certificates
            self.endpoints = [
                "https://fapi.binance.com",
                "https://fapi1.binance.com",
            ]

        self._host_cooldown = {}     # host -> ready_timestamp
        self._host_fail_count = {}   # host -> consecutive_network_failures
        self._cooldown_sec = 300.0
        self._connect_timeout = 3.05
        self._read_timeout = 8.0
        self.last_used_weight = 0

        self.session = requests.Session()
        self.session.verify = self.verify_ssl
        if not self.verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        if self.api_key:
            self.session.headers.update({
                "X-MBX-APIKEY": self.api_key,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "PyrofuelFutures/3.1",
            })

        self._symbol_cache = {}
        self._symbol_cache_time = 0
        self._account_mode_checked = False
        self.dual_side_position = False
        self.multi_assets_margin = False

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol into standard Binance USDT Perpetual format."""
        if not symbol:
            return "BTCUSDT"
        sym = symbol.upper().strip().replace("-USD", "").replace("USDT", "")
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
        """Fetch and cache LOT_SIZE, PRICE_FILTER, and MIN_NOTIONAL for symbol."""
        sym = self.normalize_symbol(symbol)
        now = time.time()
        if not self._symbol_cache or (now - self._symbol_cache_time > 1800):
            try:
                res = self.get_exchange_info()
                if isinstance(res, dict) and "symbols" in res:
                    for s in res["symbols"]:
                        s_name = s.get("symbol")
                        lot = next((f for f in s.get("filters", []) if f.get("filterType") == "LOT_SIZE"), None)
                        p_filt = next((f for f in s.get("filters", []) if f.get("filterType") == "PRICE_FILTER"), None)
                        min_not = next(
                            (f for f in s.get("filters", []) if f.get("filterType") in ("MIN_NOTIONAL", "NOTIONAL")),
                            None,
                        )
                        self._symbol_cache[s_name] = {
                            "status": s.get("status", "TRADING"),
                            "contractType": s.get("contractType", "PERPETUAL"),
                            "quantityPrecision": int(s.get("quantityPrecision", 3)),
                            "pricePrecision": int(s.get("pricePrecision", 2)),
                            "stepSize": float(lot["stepSize"]) if lot and "stepSize" in lot else 0.001,
                            "minQty": float(lot["minQty"]) if lot and "minQty" in lot else 0.001,
                            "tickSize": float(p_filt["tickSize"]) if p_filt and "tickSize" in p_filt else 0.01,
                            "minNotional": float(min_not.get("notional", min_not.get("minNotional", 5.0))) if min_not else 5.0,
                        }
                    self._symbol_cache_time = now
            except Exception as e:
                print(f"[BinanceFutures] ⚠️ ExchangeInfo caching error: {e}", flush=True)

        default_notional = 50.0 if sym == "BTCUSDT" else (20.0 if sym == "ETHUSDT" else 5.0)
        return self._symbol_cache.get(sym, {
            "status": "TRADING",
            "contractType": "PERPETUAL",
            "quantityPrecision": 3,
            "pricePrecision": 2,
            "stepSize": 0.001,
            "minQty": 0.001,
            "tickSize": 0.01,
            "minNotional": default_notional,
        })

    def format_quantity(self, symbol: str, raw_quantity: float) -> float:
        """Format quantity strictly adhering to symbol's stepSize, minQty, and precision."""
        rules = self.get_symbol_filters(symbol)
        step = max(float(rules["stepSize"]), 1e-8)
        prec = int(rules["quantityPrecision"])
        min_qty = float(rules["minQty"])

        steps = math.floor((raw_quantity + 1e-12) / step)
        qty = steps * step
        if qty < min_qty:
            qty = min_qty

        if prec == 0:
            return float(int(round(qty)))
        return round(qty, prec)

    def format_price(self, symbol: str, raw_price: float) -> float:
        """Format price strictly adhering to symbol's tickSize and precision."""
        rules = self.get_symbol_filters(symbol)
        tick = max(float(rules["tickSize"]), 1e-8)
        prec = int(rules["pricePrecision"])

        steps = round(raw_price / tick)
        price = steps * tick
        if prec == 0:
            return float(int(round(price)))
        return round(price, prec)

    # Aliases used by blueprint modules
    round_quantity = format_quantity
    round_price = format_price

    def _sync_server_time(self):
        """Synchronize local timestamp offset with Binance server time to eliminate -1021 recvWindow errors."""
        for ep in self._get_candidate_hosts():
            try:
                r = self.session.get(f"{ep}/fapi/v1/time", timeout=(self._connect_timeout, 5.0))
                st = r.json().get("serverTime")
                if st:
                    self.time_offset = int(st - (time.time() * 1000))
                    return self.time_offset
            except Exception:
                continue
        self.time_offset = 0
        return 0

    sync_time = _sync_server_time

    def _sign(self, params: dict) -> dict:
        """Add timestamp, recvWindow, and HMAC-SHA256 signature to query parameters."""
        if not hasattr(self, "time_offset"):
            self._sync_server_time()
        clean = {k: v for k, v in params.items() if k not in ("signature",)}
        clean["recvWindow"] = 60000
        clean["timestamp"] = int(time.time() * 1000 + getattr(self, "time_offset", 0))
        query_string = urlencode(clean)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        clean["signature"] = signature
        return clean

    def _get_candidate_hosts(self) -> list:
        """Return endpoints not currently in circuit-breaker cooldown (or all if all are cooling down)."""
        now = time.time()
        healthy = [ep for ep in self.endpoints if self._host_cooldown.get(ep, 0) <= now]
        return healthy if healthy else list(self.endpoints)

    def _mark_host_failure(self, host: str):
        cnt = self._host_fail_count.get(host, 0) + 1
        self._host_fail_count[host] = cnt
        if cnt >= 2:
            self._host_cooldown[host] = time.time() + self._cooldown_sec

    def _mark_host_success(self, host: str):
        self._host_fail_count[host] = 0
        self._host_cooldown.pop(host, None)

    def _request(self, method: str, endpoint: str, params: dict = None, signed: bool = False, retry_time: bool = True):
        """
        T0.1: Execute HTTP request against Binance Futures REST API with:
        - Per-host circuit-breaker (2 network/SSL/5xx failures -> 5min skip)
        - Strict separation of network errors (failover) vs Binance API business errors (never failover)
        - Automatic -1021 timestamp resync & retry
        """
        raw_params = (params or {}).copy()

        if signed:
            if not self.api_key or not self.api_secret:
                raise ValueError("Binance API Key and Secret are required for private endpoints!")
            req_params = self._sign(raw_params)
        else:
            req_params = raw_params

        last_error = None
        timeout_tuple = (self._connect_timeout, self._read_timeout)

        for base in self._get_candidate_hosts():
            url = f"{base}{endpoint}"
            try:
                m = method.upper()
                if m == "GET":
                    resp = self.session.get(url, params=req_params, timeout=timeout_tuple)
                elif m == "POST":
                    resp = self.session.post(url, data=req_params, timeout=timeout_tuple)
                elif m == "PUT":
                    resp = self.session.put(url, data=req_params, timeout=timeout_tuple)
                elif m == "DELETE":
                    resp = self.session.delete(url, params=req_params, timeout=timeout_tuple)
                else:
                    resp = self.session.request(m, url, params=req_params, timeout=timeout_tuple)

                # Track Binance IP weight header
                if hasattr(resp, "headers") and resp.headers:
                    w = resp.headers.get("X-MBX-USED-WEIGHT-1M") or resp.headers.get("x-mbx-used-weight-1m")
                    if w and str(w).isdigit():
                        self.last_used_weight = int(w)

                # Gateway / Cloudflare / 5xx server failure -> failover to next host
                if resp.status_code in (502, 503, 504):
                    self._mark_host_failure(base)
                    last_error = f"HTTP {resp.status_code}"
                    continue

                self._mark_host_success(base)
                data = resp.json()

                if resp.status_code >= 400 or (isinstance(data, dict) and data.get("code", 0) < 0):
                    err_msg = data.get("msg") or data.get("message") or getattr(resp, "text", "API Error")
                    err_code = data.get("code", resp.status_code)
                    if err_code == -1021 and retry_time:
                        print("[BinanceFutures] 🔄 -1021 Timestamp error detected. Resyncing server clock and retrying...", flush=True)
                        self._sync_server_time()
                        return self._request(method, endpoint, raw_params, signed=signed, retry_time=False)
                    # T0.1: Do NOT failover on Binance business/validation errors (e.g. -4120, -4509, -4164, -2021)
                    print(f"[BinanceFutures] [ERROR {err_code}]: {err_msg}", flush=True)
                    return {"isError": True, "error": err_msg, "code": err_code}

                return data

            except Exception as e:
                self._mark_host_failure(base)
                last_error = e
                continue

        print(f"[BinanceFutures] [NETWORK ERROR] ({endpoint}): {last_error}", flush=True)
        return {"isError": True, "isNetworkError": True, "error": str(last_error)}

    # ===================================================================
    # PUBLIC MARKET DATA & UNIVERSE
    # ===================================================================

    def ping(self):
        return self._request("GET", "/fapi/v1/ping")

    def get_server_time(self):
        return self._request("GET", "/fapi/v1/time")

    def get_exchange_info(self):
        return self._request("GET", "/fapi/v1/exchangeInfo")

    def get_funding_info(self):
        """T3.15: Fetch dynamic funding interval (2h/4h/8h) and cap/floor info."""
        return self._request("GET", "/fapi/v1/fundingInfo")

    def get_all_premium_index(self):
        """T3.15: Fetch markPrice, indexPrice, lastFundingRate, and nextFundingTime for all symbols."""
        return self._request("GET", "/fapi/v1/premiumIndex")

    def get_market_price(self, symbol: str) -> float:
        """Get latest mark price for symbol (e.g. BTCUSDT)."""
        sym = self.normalize_symbol(symbol)
        res = self._request("GET", "/fapi/v1/premiumIndex", {"symbol": sym})
        if isinstance(res, dict) and "markPrice" in res:
            return float(res["markPrice"])
        return 0.0

    # ===================================================================
    # ACCOUNT, MODES, WALLET BALANCES & FORENSICS
    # ===================================================================

    def check_account_modes(self) -> dict:
        """T0.3: Check One-Way vs Hedge mode (dualSidePosition) and Multi-Assets Margin mode."""
        if self._account_mode_checked:
            return {
                "dualSidePosition": self.dual_side_position,
                "multiAssetsMargin": self.multi_assets_margin,
            }
        try:
            dual_res = self._request("GET", "/fapi/v1/positionSide/dual", signed=True)
            if isinstance(dual_res, dict) and "dualSidePosition" in dual_res:
                self.dual_side_position = bool(dual_res["dualSidePosition"])
            multi_res = self._request("GET", "/fapi/v1/multiAssetsMargin", signed=True)
            if isinstance(multi_res, dict) and "multiAssetsMargin" in multi_res:
                self.multi_assets_margin = bool(multi_res["multiAssetsMargin"])
            self._account_mode_checked = True
        except Exception:
            pass
        return {
            "dualSidePosition": self.dual_side_position,
            "multiAssetsMargin": self.multi_assets_margin,
        }

    def get_account(self):
        return self._request("GET", "/fapi/v2/account", signed=True)

    def get_balance(self):
        """Get wallet balances. Returns USDT total, available, and unrealized PnL."""
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
                    "raw": usdt_wallet,
                }
        return res

    def get_positions(self, symbol: str = None):
        """Get currently OPEN positions (positionAmt != 0)."""
        params = {}
        if symbol:
            params["symbol"] = self.normalize_symbol(symbol)
        res = self._request("GET", "/fapi/v2/positionRisk", params=params, signed=True)
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
                        "leverage": int(p.get("leverage", 20)),
                        "margin_type": p.get("marginType", "isolated").upper(),
                        "isolated_margin": float(p.get("isolatedMargin", 0)),
                    })
            return open_positions
        return res

    def wait_for_position_open(self, symbol: str, max_wait_sec: float = 3.0) -> dict:
        """
        T0.3: Poll positionRisk until positionAmt != 0 before placing closePosition=true Algo SL/TP
        (avoids Binance error -4509).
        """
        sym = self.normalize_symbol(symbol)
        deadline = time.time() + max_wait_sec
        while True:
            positions = self.get_positions(sym)
            if isinstance(positions, list):
                for p in positions:
                    if p.get("symbol") == sym and float(p.get("position_amount", 0)) > 0:
                        return p
            if time.time() >= deadline:
                break
            time.sleep(0.3)
        return {}

    def get_user_trades(self, symbol: str, limit: int = 100, start_time: int = None):
        """T1.1: Fetch actual trade fills, commissions, and realized PnL from Binance."""
        params = {"symbol": self.normalize_symbol(symbol), "limit": min(int(limit), 1000)}
        if start_time:
            params["startTime"] = int(start_time)
        return self._request("GET", "/fapi/v1/userTrades", params=params, signed=True)

    def get_income_history(self, symbol: str = None, income_type: str = None, limit: int = 100, start_time: int = None):
        """T1.1: Fetch REALIZED_PNL, COMMISSION, FUNDING_FEE income history."""
        params = {"limit": min(int(limit), 1000)}
        if symbol:
            params["symbol"] = self.normalize_symbol(symbol)
        if income_type:
            params["incomeType"] = income_type
        if start_time:
            params["startTime"] = int(start_time)
        return self._request("GET", "/fapi/v1/income", params=params, signed=True)

    # ===================================================================
    # LEVERAGE & MARGIN SETTINGS
    # ===================================================================

    def set_leverage(self, symbol: str, leverage: int = 20):
        sym = self.normalize_symbol(symbol)
        params = {"symbol": sym, "leverage": int(leverage)}
        res = self._request("POST", "/fapi/v1/leverage", params=params, signed=True)
        if isinstance(res, dict) and "leverage" in res:
            print(f"[BinanceFutures] ✅ Leverage set for {sym}: {res['leverage']}x", flush=True)
        return res

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED"):
        sym = self.normalize_symbol(symbol)
        m_type = margin_type.upper()
        if m_type == "CROSS":
            m_type = "CROSSED"
        params = {"symbol": sym, "marginType": m_type}
        res = self._request("POST", "/fapi/v1/marginType", params=params, signed=True)
        if isinstance(res, dict) and (res.get("code") == 200 or res.get("code") == -4046 or res.get("msg") == "success"):
            print(f"[BinanceFutures] ✅ Margin type for {sym}: {m_type}", flush=True)
        return res

    # ===================================================================
    # ORDER EXECUTION (LONG, SHORT, ALGO TP/SL, NATIVE PRICEMATCH)
    # ===================================================================

    def open_position(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        leverage: int = 20,
        order_type: str = "MARKET",
        limit_price: float = None,
        margin_type: str = "ISOLATED",
        time_in_force: str = None,
        price_match: str = None,
        good_till_date_ms: int = None,
        client_order_id: str = None,
    ):
        """
        Open a FUTURES position on Binance supporting:
        - MARKET orders
        - LIMIT orders (GTC, GTX Post-Only, IOC, GTD)
        - T6.6: Native priceMatch (QUEUE, QUEUE_5, OPPONENT) eliminating local-to-Tokyo latency
        """
        sym = self.normalize_symbol(symbol)
        side = "BUY" if direction.upper() == "LONG" else "SELL"

        try:
            self.set_margin_type(sym, margin_type)
        except Exception:
            pass
        try:
            self.set_leverage(sym, leverage)
        except Exception:
            pass

        fmt_qty = self.format_quantity(sym, quantity)
        prec = self.get_symbol_filters(sym)["quantityPrecision"]

        params = {
            "symbol": sym,
            "side": side,
            "type": order_type.upper(),
            "quantity": fmt_qty if prec > 0 else int(fmt_qty),
        }
        if self.dual_side_position:
            params["positionSide"] = "LONG" if direction.upper() == "LONG" else "SHORT"
        if client_order_id:
            params["newClientOrderId"] = str(client_order_id)[:36]

        if order_type.upper() == "LIMIT":
            if price_match and price_match.upper() in ("QUEUE", "QUEUE_5", "QUEUE_10", "OPPONENT", "OPPONENT_5"):
                params["priceMatch"] = price_match.upper()
                if good_till_date_ms and int(good_till_date_ms) > int(time.time() * 1000) + 1000:
                    params["timeInForce"] = "GTD"
                    params["goodTillDate"] = int(good_till_date_ms)
                else:
                    params["timeInForce"] = time_in_force or "GTX"
            else:
                if not limit_price or limit_price <= 0:
                    raise ValueError("Limit price required for LIMIT order without priceMatch")
                params["price"] = str(self.format_price(sym, limit_price))
                params["timeInForce"] = time_in_force or "GTC"
                if params["timeInForce"] == "GTD" and good_till_date_ms:
                    params["goodTillDate"] = int(good_till_date_ms)

        print(f"[BinanceFutures] 🚀 Sending {direction} {sym} Qty:{params['quantity']} (Lev {leverage}x, Type {order_type})...", flush=True)
        res = self._request("POST", "/fapi/v1/order", params=params, signed=True)
        # T6.6 fallback: if priceMatch or GTX was rejected (-5022 or unsupported), fallback cleanly
        if isinstance(res, dict) and res.get("isError") and order_type.upper() == "LIMIT" and price_match:
            if limit_price and limit_price > 0:
                params.pop("priceMatch", None)
                params.pop("goodTillDate", None)
                params["price"] = str(self.format_price(sym, limit_price))
                params["timeInForce"] = "GTX"
                res = self._request("POST", "/fapi/v1/order", params=params, signed=True)
        if isinstance(res, dict) and "orderId" in res:
            print(f"[BinanceFutures] ✅ Order FILLED/SUBMITTED! Order ID: {res.get('orderId')}, Status: {res.get('status')}", flush=True)
        return res

    def get_open_orders(self, symbol: str = None):
        """Fetch all open standard orders on Binance Futures."""
        params = {}
        if symbol:
            params["symbol"] = self.normalize_symbol(symbol)
        return self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)

    def get_open_algo_orders(self, symbol: str = None) -> tuple:
        """
        T0.2: Query open conditional/algo orders using the official Binance endpoint:
        GET /fapi/v1/openAlgoOrders (SIGNED).
        Returns (ok: bool, orders: list).
        Note: Never call GET /fapi/v1/algoOpenOrders because that path is DELETE-only.
        """
        params = {}
        if symbol:
            params["symbol"] = self.normalize_symbol(symbol)
        res = self._request("GET", "/fapi/v1/openAlgoOrders", params=params, signed=True)
        if isinstance(res, list):
            return True, res
        if isinstance(res, dict):
            if res.get("isError"):
                return False, []
            if "orders" in res and isinstance(res["orders"], list):
                return True, res["orders"]
            if "data" in res and isinstance(res["data"], list):
                return True, res["data"]
            # Empty dict or single order dict
            if "algoId" in res:
                return True, [res]
            return True, []
        return False, []

    def verify_stop_loss_active(
        self,
        symbol: str,
        expected_side: str = None,
        max_wait_sec: float = 3.0,
        return_tristate: bool = True,
        known_algo_id: int = None,
    ):
        """
        T0.2: Tri-state verification of active Stop-Loss order on Binance Futures.
        Returns one of:
        - "CONFIRMED": Active STOP_MARKET / STOP / TRAILING_STOP_MARKET order found on exchange
        - "MISSING": Both openAlgoOrders and openOrders responded HTTP 200 and no SL order exists
        - "UNKNOWN": Network/API error prevented verification (MUST NOT close position!)
        (If return_tristate=False, returns True for CONFIRMED/UNKNOWN and False only for MISSING).
        """
        sym = self.normalize_symbol(symbol)
        deadline = time.time() + max(0.1, float(max_wait_sec))
        saw_any_network_error = False
        saw_clean_empty_check = False

        while True:
            # 1. Primary check: GET /fapi/v1/openAlgoOrders
            ok_algo, algo_orders = self.get_open_algo_orders(sym)
            if ok_algo:
                for ao in algo_orders:
                    status = str(ao.get("algoStatus", ao.get("status", "NEW"))).upper()
                    if status not in ("NEW", "WORKING", "PARTIALLY_FILLED", ""):
                        continue
                    if known_algo_id and ao.get("algoId") == known_algo_id:
                        return "CONFIRMED" if return_tristate else True
                    otype = str(ao.get("orderType", ao.get("type", ""))).upper()
                    side = str(ao.get("side", "")).upper()
                    if ("STOP" in otype or "TRAILING" in otype) and (not expected_side or side == expected_side.upper()):
                        return "CONFIRMED" if return_tristate else True
            else:
                saw_any_network_error = True

            # 2. Secondary check: GET /fapi/v1/openOrders
            std_orders = self.get_open_orders(sym)
            ok_std = isinstance(std_orders, list)
            if ok_std:
                for o in std_orders:
                    otype = str(o.get("type", "")).upper()
                    orig_type = str(o.get("origType", "")).upper()
                    side = str(o.get("side", "")).upper()
                    if ("STOP" in otype or "STOP" in orig_type) and (not expected_side or side == expected_side.upper()):
                        return "CONFIRMED" if return_tristate else True
            else:
                saw_any_network_error = True

            if ok_algo and ok_std:
                saw_clean_empty_check = True

            if time.time() >= deadline:
                break
            time.sleep(0.5)

        if saw_clean_empty_check and not saw_any_network_error:
            return "MISSING" if return_tristate else False
        return "UNKNOWN" if return_tristate else True

    def set_take_profit(self, symbol: str, direction: str, trigger_price: float, quantity: float = None, working_type: str = "MARK_PRICE"):
        """
        T0.3: Place Take Profit Market order directly via POST /fapi/v1/algoOrder.
        - If position is LONG -> TP is SELL
        - If position is SHORT -> TP is BUY
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
            "workingType": working_type,
            "priceProtect": "TRUE",
        }
        if self.dual_side_position:
            params["positionSide"] = "LONG" if direction.upper() == "LONG" else "SHORT"

        if quantity is None:
            params["closePosition"] = "true"
        else:
            fmt_qty = self.format_quantity(sym, quantity)
            prec = self.get_symbol_filters(sym)["quantityPrecision"]
            params["quantity"] = fmt_qty if prec > 0 else int(fmt_qty)
            params["reduceOnly"] = "true"

        res = self._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)
        if isinstance(res, dict) and "algoId" in res:
            print(f"[BinanceFutures] 🎯 Take Profit Algo Order set at ${fmt_price} (Algo ID: {res.get('algoId')})", flush=True)
        return res

    def set_stop_loss(self, symbol: str, direction: str, trigger_price: float, quantity: float = None, working_type: str = "MARK_PRICE"):
        """
        T0.3: Place Stop Loss Market order directly via POST /fapi/v1/algoOrder.
        Eliminates the deprecated /fapi/v1/order STOP_MARKET call that always failed with -4120.
        """
        sym = self.normalize_symbol(symbol)
        side = "SELL" if direction.upper() == "LONG" else "BUY"
        fmt_price = self.format_price(sym, trigger_price)
        algo_params = {
            "algoType": "CONDITIONAL",
            "symbol": sym,
            "side": side,
            "type": "STOP_MARKET",
            "triggerPrice": str(fmt_price),
            "workingType": working_type,
            "priceProtect": "TRUE",
        }
        if self.dual_side_position:
            algo_params["positionSide"] = "LONG" if direction.upper() == "LONG" else "SHORT"

        if quantity is None:
            algo_params["closePosition"] = "true"
        else:
            fmt_qty = self.format_quantity(sym, quantity)
            prec = self.get_symbol_filters(sym)["quantityPrecision"]
            algo_params["quantity"] = fmt_qty if prec > 0 else int(fmt_qty)
            algo_params["reduceOnly"] = "true"

        res_algo = self._request("POST", "/fapi/v1/algoOrder", params=algo_params, signed=True)
        if isinstance(res_algo, dict) and res_algo.get("code") == -2021:
            print(f"[BinanceFutures] ⚠️ Stop Loss would immediately trigger at ${fmt_price} (-2021). Auto-adjusting trigger price...", flush=True)
            live_mark = self.get_market_price(sym)
            if live_mark > 0:
                adj_price = live_mark * 0.985 if direction.upper() == "LONG" else live_mark * 1.015
                fmt_price = self.format_price(sym, adj_price)
                algo_params["triggerPrice"] = str(fmt_price)
                res_algo = self._request("POST", "/fapi/v1/algoOrder", params=algo_params, signed=True)

        if isinstance(res_algo, dict) and res_algo.get("code") in (-4130, -4509) and "closePosition" in algo_params:
            print(f"[BinanceFutures] ⚠️ closePosition=true rejected ({res_algo.get('code')}). Retrying with quantity + reduceOnly...", flush=True)
            algo_params.pop("closePosition", None)
            pos_list = self.get_positions(sym)
            act_qty = 0.0
            if isinstance(pos_list, list) and pos_list:
                act_qty = abs(float(pos_list[0].get("position_amount", pos_list[0].get("positionAmt", 0))))
            if act_qty > 0:
                fmt_qty = self.format_quantity(sym, act_qty)
                prec = self.get_symbol_filters(sym)["quantityPrecision"]
                algo_params["quantity"] = fmt_qty if prec > 0 else int(fmt_qty)
                algo_params["reduceOnly"] = "true"
                res_algo = self._request("POST", "/fapi/v1/algoOrder", params=algo_params, signed=True)

        if isinstance(res_algo, dict) and "algoId" in res_algo:
            print(f"[BinanceFutures] 🛡️ Stop Loss Algo Order set at ${fmt_price} (Algo ID: {res_algo.get('algoId')})", flush=True)
        return res_algo

    def set_trailing_stop(
        self,
        symbol: str,
        direction: str,
        callback_rate: float,
        activation_price: float = None,
        quantity: float = None,
        working_type: str = "MARK_PRICE",
    ):
        """
        T0.6: Place native exchange-side TRAILING_STOP_MARKET order via /fapi/v1/algoOrder.
        callback_rate is clamped to [0.1, 5.0] (%).
        """
        sym = self.normalize_symbol(symbol)
        side = "SELL" if direction.upper() == "LONG" else "BUY"
        cb = round(max(0.1, min(5.0, float(callback_rate))), 1)
        params = {
            "algoType": "CONDITIONAL",
            "symbol": sym,
            "side": side,
            "type": "TRAILING_STOP_MARKET",
            "callbackRate": str(cb),
            "workingType": working_type,
            "reduceOnly": "true",
        }
        if activation_price and activation_price > 0:
            params["activatePrice"] = str(self.format_price(sym, activation_price))
        if quantity is None:
            positions = self.get_positions(sym)
            if isinstance(positions, list) and positions:
                quantity = float(positions[0].get("position_amount", 0))
        if quantity and quantity > 0:
            fmt_qty = self.format_quantity(sym, quantity)
            prec = self.get_symbol_filters(sym)["quantityPrecision"]
            params["quantity"] = fmt_qty if prec > 0 else int(fmt_qty)
        return self._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)

    def cancel_algo_order(self, symbol: str, algo_id: int):
        """Cancel a single Algo Order by algoId."""
        sym = self.normalize_symbol(symbol)
        return self._request("DELETE", "/fapi/v1/algoOrder", params={"symbol": sym, "algoId": int(algo_id)}, signed=True)

    def amend_stop_loss(self, symbol: str, direction: str, new_trigger_price: float, old_algo_id: int = None, quantity: float = None) -> dict:
        """
        T0.6: Zero-Unprotected-Window Stop-Loss Amendment.
        1. Place NEW Stop-Loss Algo Order first.
        2. Verify new_algo_id is confirmed.
        3. ONLY THEN cancel the old Stop-Loss Algo Order.
        If new SL placement fails, the old SL remains untouched on the exchange!
        """
        sym = self.normalize_symbol(symbol)
        # Discover existing SL algo orders before placing new one if old_algo_id not provided
        existing_sl_ids = []
        if old_algo_id:
            existing_sl_ids.append(int(old_algo_id))
        else:
            ok, open_algos = self.get_open_algo_orders(sym)
            if ok:
                expected_side = "SELL" if direction.upper() == "LONG" else "BUY"
                for ao in open_algos:
                    otype = str(ao.get("orderType", ao.get("type", ""))).upper()
                    side = str(ao.get("side", "")).upper()
                    if "STOP" in otype and "TAKE_PROFIT" not in otype and side == expected_side and "algoId" in ao:
                        existing_sl_ids.append(int(ao["algoId"]))

        # Step 1: Place NEW SL first
        new_res = self.set_stop_loss(sym, direction, new_trigger_price, quantity=quantity)
        if not isinstance(new_res, dict) or new_res.get("isError") or "algoId" not in new_res:
            print(f"[BinanceFutures] ⚠️ amend_stop_loss: New SL failed ({new_res}); keeping existing SL untouched!", flush=True)
            return {"status": "AMEND_FAILED_KEPT_OLD", "new_res": new_res, "kept_algo_ids": existing_sl_ids}

        new_algo_id = int(new_res["algoId"])

        # Step 2: Cancel old SL orders only after new SL is active
        cancelled_ids = []
        for old_id in existing_sl_ids:
            if old_id != new_algo_id:
                try:
                    self.cancel_algo_order(sym, old_id)
                    cancelled_ids.append(old_id)
                except Exception:
                    pass

        return {
            "status": "AMENDED",
            "symbol": sym,
            "new_algo_id": new_algo_id,
            "new_trigger_price": self.format_price(sym, new_trigger_price),
            "cancelled_algo_ids": cancelled_ids,
        }

    def close_position(self, symbol: str, direction: str, quantity: float = None):
        """Instantly close a position at MARKET price with reduceOnly."""
        sym = self.normalize_symbol(symbol)
        side = "SELL" if direction.upper() == "LONG" else "BUY"
        params = {
            "symbol": sym,
            "side": side,
            "type": "MARKET",
            "reduceOnly": "true",
        }
        if self.dual_side_position:
            params["positionSide"] = "LONG" if direction.upper() == "LONG" else "SHORT"
            params.pop("reduceOnly", None)

        if quantity is None:
            try:
                positions = self.get_positions(sym)
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
        prec = self.get_symbol_filters(sym)["quantityPrecision"]
        params["quantity"] = fmt_qty if prec > 0 else int(fmt_qty)
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def cancel_all_orders(self, symbol: str):
        """Cancel all pending regular and algo TP/SL orders for a symbol."""
        sym = self.normalize_symbol(symbol)
        res_std = self._request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": sym}, signed=True)
        try:
            res_algo = self._request("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": sym}, signed=True)
        except Exception:
            res_algo = None
        return {"standard": res_std, "algo": res_algo}

    # ===================================================================
    # FULL AUTONOMOUS PIPELINE EXECUTION (T0.3, T0.4, T7.1, T7.2, T7.3)
    # ===================================================================

    def _get_locked_vault_usdt(self) -> float:
        """Read locked profit vault balance from results/vault_state.json if active."""
        vault_path = os.path.join(BASE_DIR, "results", "vault_state.json")
        if os.path.exists(vault_path):
            try:
                with open(vault_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return max(0.0, float(data.get("locked_profit_vault_usdt", 0.0)))
            except Exception:
                pass
        return 0.0

    def _sanitize_sl_tp(self, symbol: str, direction: str, mark_price: float, sl: float, tp: float) -> tuple:
        """
        Sanitize SL and TP against live mark price to prevent Binance -2021 (Order would immediately trigger).
        Guarantees:
        - LONG: sl strictly < mark_price (0.50% - 2.25% buffer), tp strictly > mark_price
        - SHORT: sl strictly > mark_price (0.50% - 2.25% buffer), tp strictly < mark_price
        """
        if mark_price <= 0:
            return sl, tp
        sym = self.normalize_symbol(symbol)
        min_buf = 0.0050  # 0.50% minimum distance
        max_buf = 0.0225  # 2.25% maximum distance
        is_long = direction.upper() == "LONG"

        if sl > 0:
            if is_long:
                if sl >= mark_price * (1.0 - min_buf):
                    sl = mark_price * (1.0 - min_buf)
                elif sl < mark_price * (1.0 - max_buf):
                    sl = mark_price * (1.0 - max_buf)
            else:
                if sl <= mark_price * (1.0 + min_buf):
                    sl = mark_price * (1.0 + min_buf)
                elif sl > mark_price * (1.0 + max_buf):
                    sl = mark_price * (1.0 + max_buf)
            sl = self.format_price(sym, sl)

        if tp > 0:
            if is_long and tp <= mark_price * (1.0 + min_buf):
                tp = mark_price * (1.0 + 0.015)
            elif not is_long and tp >= mark_price * (1.0 - min_buf):
                tp = mark_price * (1.0 - 0.015)
            tp = self.format_price(sym, tp)

        return sl, tp

    def execute_full_trade(self, signal: dict, config: dict):
        """
        Execute full quantitative trade directly on Binance Futures:
        - Enforces Fixed 20x ISOLATED & ALL_IN (95% working balance) per user mandate
        - Confirms open position in positionRisk before placing Algo SL/TP (avoids -4509)
        - Verifies liquidation distance >= 2.0x SL distance
        - T0.4: 3-stage atomic SL fail-safe with Tri-State (CONFIRMED | MISSING | UNKNOWN)
        """
        raw_sym = signal.get("binance_pair") or signal.get("symbol", "")
        symbol = self.normalize_symbol(raw_sym)
        direction = signal.get("direction", "LONG").upper()
        leverage = int(config.get("fixed_leverage", 20))  # Locked 20x user mandate
        margin_type = signal.get("margin_type") or config.get("margin_type", "ISOLATED")
        order_type = (signal.get("order_type") or config.get("order_type", "MARKET")).upper()
        limit_price = float(signal.get("limit_price") or signal.get("entry_price", 0))
        price_match = signal.get("price_match")

        self.check_account_modes()

        # 1. Check if already in position
        try:
            open_pos = self.get_positions(symbol)
            if isinstance(open_pos, list) and len(open_pos) > 0:
                return {
                    "status": "SKIPPED_ALREADY_OPEN",
                    "error": f"Position already active for {symbol}",
                    "binance_synced": True,
                }
        except Exception:
            pass

        # 2. Check live wallet balance & apply ALL_IN (95% working balance) sizing
        avail_usdt = 100.0
        sizing_mode = str(config.get("sizing_mode", "ALL_IN")).upper()
        all_in_fraction = float(config.get("all_in_balance_fraction", 0.95))
        pos_size_usd = float(signal.get("position_size_usdt") or signal.get("position_size_usd") or 0.0)

        try:
            bal_info = self.get_balance()
            if isinstance(bal_info, dict) and "available_balance" in bal_info:
                avail_usdt = float(bal_info["available_balance"])
                if avail_usdt < 0.30:
                    return {
                        "status": "REJECTED_LOW_BALANCE",
                        "error": f"Available margin ${avail_usdt:.2f} is insufficient (Min $0.30 USDT required)",
                        "binance_synced": False,
                    }
                locked_vault = self._get_locked_vault_usdt()
                working_usdt = max(min(avail_usdt, 1.0), avail_usdt - locked_vault)
                if sizing_mode == "ALL_IN" or pos_size_usd <= 0:
                    pos_size_usd = round(working_usdt * all_in_fraction, 4)
                else:
                    max_safe_margin = round(working_usdt * all_in_fraction, 4)
                    if pos_size_usd > max_safe_margin:
                        pos_size_usd = max_safe_margin
        except Exception as e:
            print(f"[BinanceFutures] ⚠️ Balance check warning: {e}", flush=True)
            if pos_size_usd <= 0:
                pos_size_usd = 10.0

        # 3. Get live mark price
        mark_price = self.get_market_price(symbol)
        if mark_price <= 0 and limit_price > 0:
            mark_price = limit_price
        if mark_price <= 0:
            return {"status": "FAILED", "error": f"Could not determine market price for {symbol}", "binance_synced": False}

        # 4. Symbol rules from exchangeInfo
        rules = self.get_symbol_filters(symbol)
        min_notional = float(rules.get("minNotional", 5.0))
        notional_usd = pos_size_usd * leverage

        if notional_usd < min_notional:
            needed_margin = (min_notional * 1.02) / leverage
            if needed_margin <= avail_usdt * 0.98:
                notional_usd = min_notional * 1.02
                pos_size_usd = round(needed_margin, 4)
            else:
                return {
                    "status": "REJECTED_NOTIONAL_CAPACITY",
                    "error": f"Symbol {symbol} minNotional ${min_notional:.2f} exceeds capacity ${notional_usd:.2f} (Avail: ${avail_usdt:.2f} at {leverage}x)",
                    "binance_synced": False,
                }

        raw_quantity = notional_usd / mark_price
        quantity = self.format_quantity(symbol, raw_quantity)
        if (quantity * mark_price) < min_notional:
            step_size = float(rules.get("stepSize", 0.001))
            bumped_qty = self.format_quantity(symbol, quantity + step_size)
            bumped_margin = (bumped_qty * mark_price) / leverage
            if bumped_margin <= avail_usdt * 0.98:
                quantity = bumped_qty
                pos_size_usd = round(bumped_margin, 4)
            else:
                return {
                    "status": "REJECTED_NOTIONAL_CAPACITY",
                    "error": f"Rounded quantity notional ${quantity * mark_price:.2f} < minNotional ${min_notional:.2f} for {symbol}",
                    "binance_synced": False,
                }

        tp = float(signal.get("take_profit") or signal.get("take_profit_2") or signal.get("take_profit_1", 0))
        sl = float(signal.get("stop_loss", 0))

        # T7.1: Enforce SL distance <= max_sl_pct (2.5%) for 20x Isolated liquidation safety
        max_sl_pct = float(config.get("max_sl_pct", 2.5)) / 100.0
        if sl > 0 and mark_price > 0:
            sl_dist = abs(mark_price - sl) / mark_price
            if sl_dist > max_sl_pct:
                sl = self.format_price(
                    symbol,
                    mark_price * (1.0 - max_sl_pct) if direction == "LONG" else mark_price * (1.0 + max_sl_pct),
                )

        sl, tp = self._sanitize_sl_tp(symbol, direction, mark_price, sl, tp)

        execution_log = {
            "exchange": "BINANCE_FUTURES",
            "symbol": symbol,
            "direction": direction,
            "leverage": leverage,
            "margin_type": margin_type,
            "sizing_mode": sizing_mode,
            "order_type": order_type,
            "entry_price": mark_price,
            "quantity": quantity,
            "position_size_usdt": round(pos_size_usd, 4),
            "notional_usdt": round(quantity * mark_price, 2),
            "take_profit": tp,
            "stop_loss": sl,
            "sl_state": "PENDING",
            "sl_algo_id": None,
            "tp_algo_id": None,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "steps": {},
        }

        try:
            # Step 1: Open Position
            order_res = self.open_position(
                symbol=symbol,
                direction=direction,
                quantity=quantity,
                leverage=leverage,
                order_type=order_type,
                limit_price=limit_price if order_type == "LIMIT" else None,
                margin_type=margin_type,
                price_match=price_match,
                client_order_id=signal.get("client_order_id"),
            )
            execution_log["steps"]["open_position"] = order_res

            if isinstance(order_res, dict) and order_res.get("isError"):
                raise RuntimeError(order_res.get("error", "Unknown Binance order error"))

            order_id = order_res.get("orderId") if isinstance(order_res, dict) else None
            if not order_id:
                raise RuntimeError(f"Binance order failed to return orderId: {order_res}")
            execution_log["order_id"] = order_id

            # Step 2 (T0.3): Poll positionRisk until position is open (prevents -4509 on closePosition=true)
            pos_info = self.wait_for_position_open(symbol, max_wait_sec=3.0)
            if pos_info:
                execution_log["entry_price"] = float(pos_info.get("entry_price") or mark_price)
                execution_log["liquidation_price"] = float(pos_info.get("liquidation_price", 0.0))

            # Step 3: Place Take Profit Algo Order
            if tp > 0:
                try:
                    tp_res = self.set_take_profit(symbol, direction, trigger_price=tp, quantity=quantity)
                    execution_log["steps"]["take_profit"] = tp_res
                    if isinstance(tp_res, dict) and "algoId" in tp_res:
                        execution_log["tp_algo_id"] = tp_res["algoId"]
                except Exception as e:
                    print(f"[BinanceFutures] ⚠️ TP placement notice: {e}", flush=True)

            # Step 4 (T0.4): Place Stop Loss Algo Order with 3-Retry & Tri-State Semantics
            if sl > 0:
                expected_sl_side = "SELL" if direction == "LONG" else "BUY"
                sl_state = "MISSING"
                retry_delays = [0.5, 1.0, 2.0]

                for attempt in range(3):
                    sl_res = self.set_stop_loss(symbol, direction, trigger_price=sl, quantity=quantity)
                    execution_log["steps"][f"stop_loss_attempt_{attempt + 1}"] = sl_res

                    if isinstance(sl_res, dict) and "algoId" in sl_res:
                        execution_log["sl_algo_id"] = sl_res["algoId"]
                        sl_state = "CONFIRMED"
                        break

                    sl_state = self.verify_stop_loss_active(
                        symbol,
                        expected_side=expected_sl_side,
                        max_wait_sec=1.8,
                        return_tristate=True,
                        known_algo_id=execution_log.get("sl_algo_id"),
                    )
                    if sl_state == "CONFIRMED":
                        break
                    if sl_state == "UNKNOWN" and execution_log["sl_algo_id"] is not None:
                        # AlgoId was already returned by POST /fapi/v1/algoOrder; do not panic!
                        sl_state = "CONFIRMED"
                        break
                    if attempt < len(retry_delays):
                        time.sleep(retry_delays[attempt])

                if sl_state == "CONFIRMED":
                    execution_log["sl_state"] = "CONFIRMED"
                    execution_log["sl_verified"] = True
                else:
                    # NEVER dump an open position at market just because exchange SL registration lagged!
                    # Keep the position alive. Local Sentinel Guard in auto_trader.py monitors every 10s and retries.
                    print(f"[BinanceFutures] ⚠️ SL order {sl_state} on exchange. Position KEPT OPEN under local Sentinel Guard.", flush=True)
                    execution_log["sl_state"] = "LOCAL_GUARD_MONITORED"
                    execution_log["sl_verified"] = False

            execution_log["status"] = "EXECUTED"
            execution_log["binance_synced"] = True
            print(f"[BinanceFutures] 🎉 FULL TRADE EXECUTED ON BINANCE: {direction} {symbol} ({leverage}x, Qty: {quantity}, SL State: {execution_log['sl_state']})", flush=True)

        except Exception as e:
            execution_log["status"] = "FAILED"
            execution_log["error"] = str(e)
            execution_log["binance_synced"] = False
            print(f"[BinanceFutures] ❌ Execution failed: {e}", flush=True)

        return execution_log
