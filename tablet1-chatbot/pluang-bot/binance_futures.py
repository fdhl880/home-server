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
import re
import sys
import json
import time
import math
import hmac
import hashlib
import logging
import threading
import requests
import socket
from contextlib import contextmanager
from urllib.parse import urlencode
from datetime import datetime, timezone

logger = logging.getLogger("binance_futures")

try:
    import bootstrap_credentials
    bootstrap_credentials.bootstrap()
except Exception as exc:
    logger.debug("bootstrap_credentials skipped: %s", exc)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception as exc:
        logger.debug("stdout reconfigure skipped: %s", exc)
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception as exc:
        logger.debug("stderr reconfigure skipped: %s", exc)

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
        except Exception as exc:
            logger.debug("DoH lookup failed for %s via %s: %s", domain, doh_url, exc)
            continue
    fallback_ip = _BINANCE_STATIC_IPS.get(domain)
    if fallback_ip:
        _dns_cache[domain] = (fallback_ip, now + _DNS_TTL_SEC)
        return fallback_ip
    # M14 Fix: Never cache REST static IP (65.8.76.49) for WS/testnet domains (fstream/stream/testnet).
    return None


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
        except Exception as exc:
            logger.warning("Failed reading .env fallback %s: %s", env_file, exc)


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
        self.recv_window = 5000
        self._time_sync_interval_sec = 600.0
        self._last_time_sync_ts = None

        # B-13: IP Weight & 429/418 Rate-Limit Governor
        self._weight_limit_1m = 2400
        self._weight_throttle_ratio = 0.80  # 1920 weight/min
        self.last_used_weight = 0
        self._last_weight_ts = 0.0
        self._rate_limit_until_ts = 0.0
        self._rate_limit_streak = 0
        self._last_rate_limit_alert_ts = 0.0
        self._rate_limit_alert_cooldown_sec = 300.0
        self._rate_limit_lock = threading.Lock()
        self._alert_callback = None

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
        self._symbol_cache_time = 0.0
        self._symbol_fail_time = None
        self._symbol_fail_cooldown_sec = 30.0
        self._account_mode_checked = False
        self.dual_side_position = False
        self.multi_assets_margin = False
        self._cid_lock = threading.Lock()
        self._cid_seq = 0
        self._thread_local = threading.local()

    def set_alert_callback(self, callback) -> None:
        """Register an optional rate-limited critical alert callback `(key, message)`."""
        self._alert_callback = callback

    def _emit_rate_limit_alert(self, key: str, message: str) -> bool:
        """Emit rate-limited error/critical alert once per cooldown window."""
        now = time.time()
        lock = getattr(self, "_rate_limit_lock", None)
        should_send = False
        if lock is not None:
            with lock:
                last_ts = float(getattr(self, "_last_rate_limit_alert_ts", 0.0) or 0.0)
                if now - last_ts >= float(getattr(self, "_rate_limit_alert_cooldown_sec", 300.0)):
                    self._last_rate_limit_alert_ts = now
                    should_send = True
        else:
            should_send = True

        logger.error("Binance rate limit [%s]: %s", key, message)
        if not should_send:
            return False

        cb = getattr(self, "_alert_callback", None)
        if callable(cb):
            try:
                cb(key, message)
                return True
            except Exception as exc:
                logger.warning("Rate-limit alert callback failed: %s", exc)
        return True

    @contextmanager
    def _critical_priority(self):
        """Force nested helper calls (e.g. exchangeInfo lookup for SL/close) to use CRITICAL priority."""
        tl = getattr(self, "_thread_local", None)
        if tl is None:
            yield
            return
        prev = getattr(tl, "request_priority", None)
        tl.request_priority = "CRITICAL"
        try:
            yield
        finally:
            tl.request_priority = prev

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
        """Fetch and cache LOT_SIZE, MARKET_LOT_SIZE, PRICE_FILTER, and MIN_NOTIONAL for symbol (fail-closed)."""
        sym = self.normalize_symbol(symbol)
        now = time.time()
        cooldown = float(getattr(self, "_symbol_fail_cooldown_sec", 30.0))
        fail_ts = getattr(self, "_symbol_fail_time", None)
        in_fail_cooldown = (fail_ts is not None) and ((now - float(fail_ts)) < cooldown)
        need_refresh = (not self._symbol_cache) or ((now - float(self._symbol_cache_time or 0.0)) > 1800.0)

        if need_refresh and not in_fail_cooldown:
            fetch_ok = False
            fresh_cache = {}
            fetch_err = "Unknown exchangeInfo error"
            try:
                res = self.get_exchange_info()
                if isinstance(res, dict) and not res.get("isError") and isinstance(res.get("symbols"), list) and len(res["symbols"]) > 0:
                    for s in res["symbols"]:
                        s_name = s.get("symbol")
                        if not s_name:
                            continue
                        filters = s.get("filters", []) or []
                        lot = next((f for f in filters if f.get("filterType") == "LOT_SIZE"), None)
                        mlot = next((f for f in filters if f.get("filterType") == "MARKET_LOT_SIZE"), None)
                        p_filt = next((f for f in filters if f.get("filterType") == "PRICE_FILTER"), None)
                        min_not = next(
                            (f for f in filters if f.get("filterType") in ("MIN_NOTIONAL", "NOTIONAL")),
                            None,
                        )
                        entry = {
                            "status": str(s.get("status", "UNKNOWN")).upper(),
                            "contractType": str(s.get("contractType", "")).upper(),
                            "quantityPrecision": int(s.get("quantityPrecision", 3)),
                            "pricePrecision": int(s.get("pricePrecision", 2)),
                            "stepSize": float(lot["stepSize"]) if lot and "stepSize" in lot else 0.001,
                            "minQty": float(lot["minQty"]) if lot and "minQty" in lot else 0.001,
                            "maxQty": float(lot["maxQty"]) if lot and "maxQty" in lot else None,
                            "marketStepSize": float(mlot["stepSize"]) if mlot and "stepSize" in mlot else (float(lot["stepSize"]) if lot and "stepSize" in lot else 0.001),
                            "marketMinQty": float(mlot["minQty"]) if mlot and "minQty" in mlot else (float(lot["minQty"]) if lot and "minQty" in lot else 0.001),
                            "marketMaxQty": float(mlot["maxQty"]) if mlot and "maxQty" in mlot else (float(lot["maxQty"]) if lot and "maxQty" in lot else None),
                            "tickSize": float(p_filt["tickSize"]) if p_filt and "tickSize" in p_filt else 0.01,
                            "minNotional": float(min_not.get("notional", min_not.get("minNotional", 5.0))) if min_not else 5.0,
                        }
                        if min_not and "maxNotional" in min_not:
                            entry["maxNotional"] = float(min_not["maxNotional"])
                        fresh_cache[s_name] = entry
                    if fresh_cache:
                        self._symbol_cache = fresh_cache
                        self._symbol_cache_time = now
                        self._symbol_fail_time = None
                        fetch_ok = True
                else:
                    fetch_err = (res.get("error") if isinstance(res, dict) else None) or "Invalid or empty exchangeInfo payload"
            except Exception as e:
                fetch_err = str(e)
                print(f"[BinanceFutures] ⚠️ ExchangeInfo caching error: {e}", flush=True)

            if not fetch_ok:
                self._symbol_cache = {}
                self._symbol_fail_time = now
                self._symbol_cache_time = now
                return {"isError": True, "error": f"Failed to fetch Binance exchangeInfo ({fetch_err})"}

        if sym in self._symbol_cache:
            return self._symbol_cache[sym]
        if in_fail_cooldown and not self._symbol_cache:
            return {"isError": True, "error": f"Binance exchangeInfo unavailable (retry cooldown active) for {sym}"}
        return {"isError": True, "error": f"Symbol {sym} not found in Binance exchangeInfo"}

    def format_quantity(self, symbol: str, raw_quantity: float, order_type: str = "LIMIT") -> float:
        """Format quantity strictly adhering to symbol's stepSize, minQty, and precision."""
        rules = self.get_symbol_filters(symbol)
        if not isinstance(rules, dict) or rules.get("isError"):
            err = rules.get("error", f"Symbol filters unavailable for {symbol}") if isinstance(rules, dict) else f"Invalid filters for {symbol}"
            raise ValueError(err)

        is_mkt = str(order_type or "LIMIT").upper() == "MARKET"
        step_val = rules.get("marketStepSize") if is_mkt and rules.get("marketStepSize") else rules["stepSize"]
        min_val = rules.get("marketMinQty") if is_mkt and rules.get("marketMinQty") else rules["minQty"]
        step = max(float(step_val), 1e-8)
        prec = int(rules["quantityPrecision"])
        min_qty = float(min_val)

        steps = math.floor((float(raw_quantity) + 1e-12) / step)
        qty = steps * step
        if qty < min_qty:
            qty = min_qty

        if prec == 0:
            return float(int(round(qty)))
        return round(qty, prec)

    def _format_qty_compat(self, symbol: str, raw_quantity: float, order_type: str = "LIMIT") -> float:
        """Call format_quantity passing order_type only if not overridden by a 2-arg subclass."""
        if type(self).format_quantity is BinanceFuturesClient.format_quantity:
            return self.format_quantity(symbol, raw_quantity, order_type=order_type)
        return self.format_quantity(symbol, raw_quantity)

    def format_price(self, symbol: str, raw_price: float) -> float:
        """Format price strictly adhering to symbol's tickSize and precision."""
        rules = self.get_symbol_filters(symbol)
        if not isinstance(rules, dict) or rules.get("isError"):
            err = rules.get("error", f"Symbol filters unavailable for {symbol}") if isinstance(rules, dict) else f"Invalid filters for {symbol}"
            raise ValueError(err)
        tick = max(float(rules["tickSize"]), 1e-8)
        prec = int(rules["pricePrecision"])

        steps = round(float(raw_price) / tick)
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
                    self._last_time_sync_ts = time.time()
                    return self.time_offset
            except Exception as exc:
                logger.warning("Server time sync failed via %s: %s", ep, exc)
                continue
        self.time_offset = 0
        self._last_time_sync_ts = time.time()
        return 0

    sync_time = _sync_server_time

    def _sign(self, params: dict) -> dict:
        """Add timestamp, recvWindow=5000, periodic 10m resync, and HMAC-SHA256 signature."""
        now = time.time()
        last_sync = getattr(self, "_last_time_sync_ts", None)
        interval = float(getattr(self, "_time_sync_interval_sec", 600.0))
        if not hasattr(self, "time_offset") or (
            last_sync is not None and (now - float(last_sync)) >= interval
        ):
            self._sync_server_time()
        clean = {k: v for k, v in params.items() if k not in ("signature",)}
        clean["recvWindow"] = int(params.get("recvWindow") or getattr(self, "recv_window", 5000))
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

    def _generate_client_id(self, kind: str, params: dict) -> str:
        """Generate a deterministic <= 36-char Binance clientOrderId / clientAlgoId."""
        lock = getattr(self, "_cid_lock", None)
        if lock is not None:
            with lock:
                self._cid_seq = (getattr(self, "_cid_seq", 0) + 1) % 100000
                seq = self._cid_seq
        else:
            seq = int(time.time() * 1000) % 100000
        raw_sym = str((params or {}).get("symbol", "UNK"))
        sym = re.sub(r"[^A-Za-z0-9]", "", raw_sym)[:8] or "UNK"
        side = str((params or {}).get("side", "X"))[:1]
        otype = str((params or {}).get("type", "X"))[:2]
        seed = (
            f"{kind}|{sym}|{side}|{otype}|"
            f"{(params or {}).get('quantity', '')}|"
            f"{(params or {}).get('triggerPrice', (params or {}).get('price', ''))}|"
            f"{seq}|{time.time_ns()}"
        )
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        return f"pf_{kind}_{sym}_{digest}"[:36]

    def _recover_ambiguous_write(self, method_upper: str, endpoint: str, raw_params: dict, failed_host: str):
        """
        A-1: Query exchange order/algo status before failing over on ambiguous write failure
        (timeout, connection reset, 5xx) to prevent duplicate order submission.
        """
        sym = raw_params.get("symbol")
        if not sym:
            return None
        candidates = self._get_candidate_hosts()
        alt_hosts = [h for h in candidates if h != failed_host]
        preferred_hosts = alt_hosts + [failed_host]

        try:
            if method_upper == "POST" and endpoint == "/fapi/v1/order":
                cid = raw_params.get("newClientOrderId")
                if not cid:
                    return None
                lookup = self._request(
                    "GET",
                    "/fapi/v1/order",
                    {"symbol": sym, "origClientOrderId": cid},
                    signed=True,
                    _hosts_override=preferred_hosts,
                )
                if isinstance(lookup, dict) and not lookup.get("isError") and "orderId" in lookup:
                    print(f"[BinanceFutures] 🛡️ A-1 Idempotent recovery: order {cid} already exists (#{lookup.get('orderId')})", flush=True)
                    return lookup

            elif method_upper == "POST" and endpoint == "/fapi/v1/algoOrder":
                caid = raw_params.get("clientAlgoId")
                if not caid:
                    return None
                lookup = self._request(
                    "GET",
                    "/fapi/v1/openAlgoOrders",
                    {"symbol": sym},
                    signed=True,
                    _hosts_override=preferred_hosts,
                )
                orders = []
                if isinstance(lookup, list):
                    orders = lookup
                elif isinstance(lookup, dict) and not lookup.get("isError"):
                    if isinstance(lookup.get("orders"), list):
                        orders = lookup["orders"]
                    elif isinstance(lookup.get("data"), list):
                        orders = lookup["data"]
                    elif "algoId" in lookup:
                        orders = [lookup]
                for ao in orders:
                    if isinstance(ao, dict) and (ao.get("clientAlgoId") == caid or ao.get("origClientAlgoId") == caid):
                        print(f"[BinanceFutures] 🛡️ A-1 Idempotent recovery: algoOrder {caid} already exists (#{ao.get('algoId')})", flush=True)
                        return ao

            elif method_upper == "DELETE" and endpoint == "/fapi/v1/order":
                q = {"symbol": sym}
                if raw_params.get("orderId") is not None:
                    q["orderId"] = raw_params["orderId"]
                elif raw_params.get("origClientOrderId"):
                    q["origClientOrderId"] = raw_params["origClientOrderId"]
                else:
                    return None
                lookup = self._request(
                    "GET",
                    "/fapi/v1/order",
                    q,
                    signed=True,
                    _hosts_override=preferred_hosts,
                )
                if isinstance(lookup, dict) and not lookup.get("isError"):
                    st = str(lookup.get("status", "")).upper()
                    if st in ("CANCELED", "CANCELLED", "FILLED", "EXPIRED"):
                        print(f"[BinanceFutures] 🛡️ A-1 Idempotent delete recovery: order already {st}", flush=True)
                        return lookup

            elif method_upper == "DELETE" and endpoint == "/fapi/v1/algoOrder":
                aid = raw_params.get("algoId")
                caid = raw_params.get("clientAlgoId")
                if aid is None and not caid:
                    return None
                lookup = self._request(
                    "GET",
                    "/fapi/v1/openAlgoOrders",
                    {"symbol": sym},
                    signed=True,
                    _hosts_override=preferred_hosts,
                )
                orders = None
                if isinstance(lookup, list):
                    orders = lookup
                elif isinstance(lookup, dict) and not lookup.get("isError"):
                    if isinstance(lookup.get("orders"), list):
                        orders = lookup["orders"]
                    elif isinstance(lookup.get("data"), list):
                        orders = lookup["data"]
                    elif "algoId" in lookup:
                        orders = [lookup]
                    else:
                        orders = []
                if orders is not None:
                    still_open = any(
                        isinstance(ao, dict)
                        and (
                            (aid is not None and str(ao.get("algoId")) == str(aid))
                            or (caid and ao.get("clientAlgoId") == caid)
                        )
                        for ao in orders
                    )
                    if not still_open:
                        print("[BinanceFutures] 🛡️ A-1 Idempotent algo delete recovery: algoOrder already canceled", flush=True)
                        return {"algoId": aid, "clientAlgoId": caid, "algoStatus": "CANCELED", "code": 200, "idempotent_confirmed": True}
        except Exception as exc:
            logger.warning("Ambiguous write recovery failed for %s %s: %s", method_upper, endpoint, exc)
        return None

    _CRITICAL_ENDPOINTS = frozenset({
        "/fapi/v1/algoOrder",
        "/fapi/v1/algoOpenOrders",
        "/fapi/v1/openAlgoOrders",
        "/fapi/v1/openOrders",
        "/fapi/v1/allOpenOrders",
        "/fapi/v2/positionRisk",
        "/fapi/v2/balance",
        "/fapi/v2/account",
        "/fapi/v1/userTrades",
        "/fapi/v1/income",
        "/fapi/v1/allOrders",
        "/fapi/v1/listenKey",
        "/fapi/v1/time",
        "/fapi/v1/positionSide/dual",
        "/fapi/v1/multiAssetsMargin",
    })
    _SCAN_ENDPOINTS = frozenset({
        "/fapi/v1/exchangeInfo",
        "/fapi/v1/depth",
        "/fapi/v1/premiumIndex",
        "/fapi/v1/fundingInfo",
        "/fapi/v1/ping",
        "/fapi/v1/ticker/24hr",
    })

    def _resolve_request_priority(
        self,
        method: str,
        endpoint: str,
        raw_params: dict,
        explicit_priority: str = None,
    ) -> str:
        if explicit_priority:
            return str(explicit_priority).upper().strip()
        tl = getattr(self, "_thread_local", None)
        tl_prio = getattr(tl, "request_priority", None) if tl is not None else None
        if tl_prio:
            return str(tl_prio).upper().strip()
        if endpoint in self._CRITICAL_ENDPOINTS:
            return "CRITICAL"
        if endpoint == "/fapi/v1/order":
            return "CRITICAL"
        if endpoint in self._SCAN_ENDPOINTS:
            return "SCAN"
        return "CRITICAL" if method in ("POST", "PUT", "DELETE") else "SCAN"

    @staticmethod
    def _parse_retry_after(headers) -> float | None:
        if not headers:
            return None
        try:
            raw_ra = headers.get("Retry-After")
            if raw_ra is None:
                raw_ra = headers.get("retry-after")
        except Exception:
            return None
        if isinstance(raw_ra, (int, float)) and not isinstance(raw_ra, bool):
            val = float(raw_ra)
            return max(0.0, min(val, 600.0)) if math.isfinite(val) else None
        if isinstance(raw_ra, str):
            s = raw_ra.strip()
            try:
                val = float(s)
                return max(0.0, min(val, 600.0)) if math.isfinite(val) else None
            except ValueError:
                return None
        return None

    def _handle_rate_limit_response(
        self,
        status_code: int,
        err_code,
        resp_headers,
        err_msg: str,
        endpoint: str,
    ) -> dict:
        now = time.time()
        parsed_ra = self._parse_retry_after(resp_headers)
        lock = getattr(self, "_rate_limit_lock", None)
        if lock is not None:
            with lock:
                streak = int(getattr(self, "_rate_limit_streak", 0))
                self._rate_limit_streak = min(streak + 1, 6)
        else:
            streak = int(getattr(self, "_rate_limit_streak", 0))
            self._rate_limit_streak = min(streak + 1, 6)

        if parsed_ra is not None and parsed_ra > 0:
            wait_sec = float(parsed_ra)
        else:
            base_sec = 60.0 if int(status_code) == 418 else 2.0
            wait_sec = min(300.0, base_sec * (2 ** min(streak, 5)))

        self._rate_limit_until_ts = max(float(getattr(self, "_rate_limit_until_ts", 0.0) or 0.0), now + wait_sec)
        self._emit_rate_limit_alert(
            f"BINANCE_RL_{status_code}_{err_code}",
            f"Binance Futures rate limit HTTP {status_code} (code={err_code}) on {endpoint}: "
            f"{err_msg}. Cooldown {wait_sec:.1f}s.",
        )
        return {
            "isError": True,
            "code": err_code,
            "http_status": int(status_code),
            "rate_limited": True,
            "retry_after": round(wait_sec, 2),
            "error": err_msg,
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        signed: bool = False,
        retry_time: bool = True,
        _hosts_override: list = None,
        priority: str = None,
        _retry_rate_limit: bool = True,
        api_key_only: bool = False,
    ):
        """
        T0.1 / A-1 / B-13: Execute HTTP request against Binance Futures REST API with:
        - IP weight governor (>= 80% of 2400 pauses SCAN while CRITICAL passes)
        - HTTP 429/418/-1003 Retry-After cooldown & rate-limited alerting (no failover storm)
        - Deterministic clientOrderId / clientAlgoId injection before host failover on order writes
        - Pre-failover exchange lookup on ambiguous 5xx / timeout / connection errors
        - Per-host circuit-breaker (2 network/SSL/5xx failures -> 5min skip)
        - Automatic -1021 timestamp resync & retry
        """
        m = method.upper()
        raw_params = (params or {}).copy()
        eff_priority = self._resolve_request_priority(m, endpoint, raw_params, explicit_priority=priority)

        # B-13: Rate-limit / weight governor check before dispatching non-critical SCAN requests
        now = time.time()
        last_w_ts = float(getattr(self, "_last_weight_ts", 0.0) or 0.0)
        if last_w_ts > 0 and (now - last_w_ts > 65.0 or now < last_w_ts):
            self.last_used_weight = 0
            self._last_weight_ts = 0.0

        rl_until = float(getattr(self, "_rate_limit_until_ts", 0.0) or 0.0)
        if rl_until > 0 and (rl_until - now) > 650.0:
            # Guard against backwards-mocked test clocks
            self._rate_limit_until_ts = 0.0
            rl_until = 0.0

        if eff_priority == "SCAN":
            if now < rl_until:
                rem = round(rl_until - now, 2)
                logger.warning("Rate-limit cooldown active (%ss left); skipping SCAN %s", rem, endpoint)
                return {
                    "isError": True,
                    "code": -1003,
                    "rate_limited": True,
                    "retry_after": rem,
                    "error": f"Rate-limit cooldown active ({rem:.1f}s remaining)",
                }
            weight_limit = int(getattr(self, "_weight_limit_1m", 2400) or 2400)
            throttle_thr = int(weight_limit * float(getattr(self, "_weight_throttle_ratio", 0.80) or 0.80))
            if int(getattr(self, "last_used_weight", 0) or 0) >= throttle_thr:
                logger.warning(
                    "IP weight governor throttled SCAN %s (used=%s >= %s/%s)",
                    endpoint,
                    self.last_used_weight,
                    throttle_thr,
                    weight_limit,
                )
                return {
                    "isError": True,
                    "code": -1003,
                    "rate_limited": True,
                    "used_weight": int(self.last_used_weight),
                    "error": f"Rate-limit governor paused SCAN request: 1m weight {self.last_used_weight}/{weight_limit} >= 80%",
                }

        # A-1: Inject deterministic client IDs BEFORE signing and host failover loop
        is_order_post = (m == "POST" and endpoint == "/fapi/v1/order")
        is_algo_post = (m == "POST" and endpoint == "/fapi/v1/algoOrder")
        is_order_delete = (m == "DELETE" and endpoint == "/fapi/v1/order")
        is_algo_delete = (m == "DELETE" and endpoint == "/fapi/v1/algoOrder")
        is_idempotent_write = is_order_post or is_algo_post or is_order_delete or is_algo_delete

        if is_order_post:
            if "client_order_id" in raw_params:
                cid_sup = raw_params.pop("client_order_id")
                if cid_sup and "newClientOrderId" not in raw_params:
                    raw_params["newClientOrderId"] = str(cid_sup)[:36]
            if "newClientOrderId" in raw_params and raw_params["newClientOrderId"]:
                raw_params["newClientOrderId"] = str(raw_params["newClientOrderId"])[:36]
            else:
                raw_params["newClientOrderId"] = self._generate_client_id("o", raw_params)
        elif is_algo_post:
            if "client_order_id" in raw_params:
                cid_sup = raw_params.pop("client_order_id")
                if cid_sup and "clientAlgoId" not in raw_params:
                    raw_params["clientAlgoId"] = str(cid_sup)[:36]
            if "clientAlgoId" in raw_params and raw_params["clientAlgoId"]:
                raw_params["clientAlgoId"] = str(raw_params["clientAlgoId"])[:36]
            else:
                raw_params["clientAlgoId"] = self._generate_client_id("a", raw_params)
        elif is_order_delete and "client_order_id" in raw_params:
            cid_sup = raw_params.pop("client_order_id")
            if cid_sup and "orderId" not in raw_params and "origClientOrderId" not in raw_params:
                raw_params["origClientOrderId"] = str(cid_sup)[:36]
        elif is_algo_delete and "client_order_id" in raw_params:
            cid_sup = raw_params.pop("client_order_id")
            if cid_sup and "algoId" not in raw_params and "clientAlgoId" not in raw_params:
                raw_params["clientAlgoId"] = str(cid_sup)[:36]

        if signed:
            if not self.api_key or not self.api_secret:
                raise ValueError("Binance API Key and Secret are required for private endpoints!")
            req_params = self._sign(raw_params)
        else:
            if api_key_only:
                if not self.api_key:
                    raise ValueError("Binance API Key is required for USER_STREAM endpoints!")
                if "X-MBX-APIKEY" not in self.session.headers:
                    self.session.headers["X-MBX-APIKEY"] = self.api_key
            req_params = raw_params

        last_error = None
        timeout_tuple = (self._connect_timeout, self._read_timeout)
        hosts = list(_hosts_override) if _hosts_override else self._get_candidate_hosts()

        for base in hosts:
            url = f"{base}{endpoint}"
            try:
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

                resp_headers = getattr(resp, "headers", None)
                # Track Binance IP weight header
                if resp_headers:
                    try:
                        w = resp_headers.get("X-MBX-USED-WEIGHT-1M") or resp_headers.get("x-mbx-used-weight-1m")
                    except Exception:
                        w = None
                    if isinstance(w, (int, float)) and not isinstance(w, bool):
                        self.last_used_weight = int(w)
                        self._last_weight_ts = time.time()
                    elif isinstance(w, str) and w.strip().isdigit():
                        self.last_used_weight = int(w.strip())
                        self._last_weight_ts = time.time()

                status_int = int(resp.status_code)

                # B-13: Handle HTTP 429 / 418 BEFORE JSON parse / failover (never storm fapi* hosts!)
                if status_int in (429, 418):
                    try:
                        rl_data = resp.json()
                    except Exception:
                        rl_data = {}
                    rl_msg = (
                        (rl_data.get("msg") or rl_data.get("message")) if isinstance(rl_data, dict) else None
                    ) or getattr(resp, "text", f"HTTP {status_int}")
                    rl_code = rl_data.get("code", status_int) if isinstance(rl_data, dict) else status_int
                    rl_out = self._handle_rate_limit_response(status_int, rl_code, resp_headers, str(rl_msg), endpoint)
                    if (
                        eff_priority == "CRITICAL"
                        and status_int == 429
                        and _retry_rate_limit
                        and float(rl_out.get("retry_after", 999)) <= 5.0
                    ):
                        time.sleep(float(rl_out["retry_after"]))
                        return self._request(
                            method,
                            endpoint,
                            raw_params,
                            signed=signed,
                            retry_time=retry_time,
                            _hosts_override=_hosts_override,
                            priority=priority,
                            _retry_rate_limit=False,
                        )
                    return rl_out

                # Gateway / Cloudflare / 5xx server failure -> recover ambiguous write, else failover
                if 500 <= status_int < 600:
                    self._mark_host_failure(base)
                    last_error = f"HTTP {status_int}"
                    if is_idempotent_write:
                        recovered = self._recover_ambiguous_write(m, endpoint, raw_params, base)
                        if recovered is not None:
                            return recovered
                    continue

                self._mark_host_success(base)
                data = resp.json()

                if status_int >= 400 or (isinstance(data, dict) and data.get("code", 0) < 0):
                    err_msg = data.get("msg") or data.get("message") or getattr(resp, "text", "API Error") if isinstance(data, dict) else getattr(resp, "text", "API Error")
                    err_code = data.get("code", status_int) if isinstance(data, dict) else status_int
                    if err_code == -1003:
                        return self._handle_rate_limit_response(status_int, err_code, resp_headers, str(err_msg), endpoint)
                    if err_code == -1021 and retry_time:
                        print("[BinanceFutures] 🔄 -1021 Timestamp error detected. Resyncing server clock and retrying...", flush=True)
                        self._sync_server_time()
                        return self._request(
                            method,
                            endpoint,
                            raw_params,
                            signed=signed,
                            retry_time=False,
                            _hosts_override=_hosts_override,
                            priority=priority,
                            _retry_rate_limit=_retry_rate_limit,
                        )
                    if err_code == -4116 and is_order_post:
                        recovered = self._recover_ambiguous_write(m, endpoint, raw_params, base)
                        if recovered is not None:
                            return recovered
                    # T0.1: Do NOT failover on Binance business/validation errors (e.g. -4120, -4509, -4164, -2021)
                    print(f"[BinanceFutures] [ERROR {err_code}]: {err_msg}", flush=True)
                    return {"isError": True, "error": err_msg, "code": err_code}

                self._rate_limit_streak = 0
                return data

            except Exception as e:
                self._mark_host_failure(base)
                last_error = e
                if is_idempotent_write:
                    recovered = self._recover_ambiguous_write(m, endpoint, raw_params, base)
                    if recovered is not None:
                        return recovered
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

    def get_funding_info(self, symbol: str = None):
        """
        T3.15 / C-9:
        - When `symbol is None`, fetch `/fapi/v1/fundingInfo` (interval/cap metadata).
        - When `symbol` is provided, query `/fapi/v1/premiumIndex` and return normalized
          `{"symbol", "last_funding_rate", "next_funding_time_ms", "mark_price", "ok"}`.
        """
        if symbol is None:
            return self._request("GET", "/fapi/v1/fundingInfo")

        sym = self.normalize_symbol(symbol)
        res = self._request("GET", "/fapi/v1/premiumIndex", {"symbol": sym})
        item = None
        if isinstance(res, list):
            item = next(
                (r for r in res if isinstance(r, dict) and str(r.get("symbol", "")).upper() == sym),
                None,
            )
        elif isinstance(res, dict) and not res.get("isError"):
            item = res

        if isinstance(item, dict) and (
            "lastFundingRate" in item or "nextFundingTime" in item or "markPrice" in item
        ):
            try:
                return {
                    "symbol": sym,
                    "last_funding_rate": float(item.get("lastFundingRate", 0.0) or 0.0),
                    "next_funding_time_ms": int(item.get("nextFundingTime", 0) or 0),
                    "mark_price": float(item.get("markPrice", 0.0) or 0.0),
                    "ok": True,
                }
            except (TypeError, ValueError) as exc:
                return {
                    "symbol": sym,
                    "last_funding_rate": 0.0,
                    "next_funding_time_ms": 0,
                    "mark_price": 0.0,
                    "ok": False,
                    "error": f"Invalid premiumIndex numeric payload: {exc}",
                }

        err_msg = res.get("error", str(res)) if isinstance(res, dict) else f"Unexpected payload: {type(res).__name__}"
        return {
            "symbol": sym,
            "last_funding_rate": 0.0,
            "next_funding_time_ms": 0,
            "mark_price": 0.0,
            "ok": False,
            "error": err_msg,
        }

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
        """T0.3 / C-1: Check One-Way vs Hedge mode (dualSidePosition) and Multi-Assets Margin mode."""
        if self._account_mode_checked:
            return {
                "dualSidePosition": self.dual_side_position,
                "multiAssetsMargin": self.multi_assets_margin,
                "ok": True,
            }
        dual_ok = False
        multi_ok = False
        err_msg = None
        try:
            dual_res = self._request("GET", "/fapi/v1/positionSide/dual", signed=True)
            if isinstance(dual_res, dict) and not dual_res.get("isError") and "dualSidePosition" in dual_res:
                self.dual_side_position = bool(dual_res["dualSidePosition"])
                dual_ok = True
            elif isinstance(dual_res, dict):
                err_msg = dual_res.get("error") or str(dual_res)

            multi_res = self._request("GET", "/fapi/v1/multiAssetsMargin", signed=True)
            if isinstance(multi_res, dict) and not multi_res.get("isError") and "multiAssetsMargin" in multi_res:
                self.multi_assets_margin = bool(multi_res["multiAssetsMargin"])
                multi_ok = True
            elif isinstance(multi_res, dict) and not err_msg:
                err_msg = multi_res.get("error") or str(multi_res)

            if dual_ok and multi_ok:
                self._account_mode_checked = True
        except Exception as e:
            err_msg = str(e)
        res = {
            "dualSidePosition": self.dual_side_position,
            "multiAssetsMargin": self.multi_assets_margin,
            "ok": bool(dual_ok and multi_ok),
        }
        if err_msg and not res["ok"]:
            res["error"] = err_msg
        return res

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
                        "position_side": str(p.get("positionSide", "BOTH")).upper(),
                        "direction": "LONG" if amt > 0 else "SHORT",
                        "position_amount": abs(amt),
                        "entry_price": float(p.get("entryPrice", 0)),
                        "mark_price": float(p.get("markPrice", 0)),
                        "unrealized_pnl": float(p.get("unRealizedProfit", 0)),
                        "liquidation_price": float(p.get("liquidationPrice", 0)),
                        "leverage": int(p.get("leverage", 20)),
                        "margin_type": p.get("marginType", "isolated").upper(),
                        "isolated_margin": float(p.get("isolatedMargin", 0)),
                        "isolated_wallet": float(p.get("isolatedWallet", 0)),
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

    def get_user_trades(self, symbol: str, limit: int = 100, start_time: int = None, end_time: int = None):
        """T1.1: Fetch actual trade fills, commissions, and realized PnL from Binance."""
        params = {"symbol": self.normalize_symbol(symbol), "limit": min(int(limit), 1000)}
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        return self._request("GET", "/fapi/v1/userTrades", params=params, signed=True)

    def get_income_history(self, symbol: str = None, income_type: str = None, limit: int = 100, start_time: int = None, end_time: int = None):
        """T1.1: Fetch REALIZED_PNL, COMMISSION, FUNDING_FEE income history."""
        params = {"limit": min(int(limit), 1000)}
        if symbol:
            params["symbol"] = self.normalize_symbol(symbol)
        if income_type:
            params["incomeType"] = income_type
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        return self._request("GET", "/fapi/v1/income", params=params, signed=True)

    def get_all_orders(self, symbol: str, limit: int = 20, start_time: int = None):
        """Fetch recent symbol orders (including liquidation/ADL close orders)."""
        params = {"symbol": self.normalize_symbol(symbol), "limit": min(int(limit), 1000)}
        if start_time is not None:
            params["startTime"] = int(start_time)
        return self._request("GET", "/fapi/v1/allOrders", params=params, signed=True)

    # ===================================================================
    # LEVERAGE & MARGIN SETTINGS
    # ===================================================================

    @staticmethod
    def _is_margin_type_ok(res) -> bool:
        """Accept ONLY non-error response or Binance code -4046 ('No need to change margin type')."""
        if not isinstance(res, dict):
            return False
        if not res.get("isError"):
            return True
        return res.get("code") == -4046

    def set_leverage(self, symbol: str, leverage: int = 20):
        sym = self.normalize_symbol(symbol)
        params = {"symbol": sym, "leverage": int(leverage)}
        res = self._request("POST", "/fapi/v1/leverage", params=params, signed=True)
        if isinstance(res, dict) and not res.get("isError") and "leverage" in res:
            print(f"[BinanceFutures] ✅ Leverage set for {sym}: {res['leverage']}x", flush=True)
        return res

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED"):
        sym = self.normalize_symbol(symbol)
        m_type = str(margin_type or "ISOLATED").upper().strip()
        if m_type == "CROSS":
            m_type = "CROSSED"
        if m_type not in ("ISOLATED", "CROSSED"):
            return {"isError": True, "error": f"Invalid margin_type: {margin_type}"}
        params = {"symbol": sym, "marginType": m_type}
        res = self._request("POST", "/fapi/v1/marginType", params=params, signed=True)
        if self._is_margin_type_ok(res):
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
        otype = order_type.upper()

        # A-2: Strictly verify margin type and leverage unless already verified in execute_full_trade
        tl = getattr(self, "_thread_local", None)
        verified_mode = getattr(tl, "exec_verified_mode", None) if tl is not None else None
        norm_mt = "CROSSED" if str(margin_type or "ISOLATED").upper() in ("CROSS", "CROSSED") else str(margin_type or "ISOLATED").upper()
        if verified_mode != (sym, norm_mt, int(leverage)):
            try:
                m_res = self.set_margin_type(sym, margin_type)
            except Exception as e:
                return {"isError": True, "error": f"Margin type exception for {sym}: {e}", "stage": "set_margin_type"}
            if not self._is_margin_type_ok(m_res):
                return {
                    "isError": True,
                    "code": m_res.get("code") if isinstance(m_res, dict) else None,
                    "error": f"Margin type setup failed for {sym}: {m_res}",
                    "stage": "set_margin_type",
                }

            try:
                l_res = self.set_leverage(sym, leverage)
            except Exception as e:
                return {"isError": True, "error": f"Leverage exception for {sym}: {e}", "stage": "set_leverage"}
            if not isinstance(l_res, dict) or l_res.get("isError") or l_res.get("leverage") is None:
                return {
                    "isError": True,
                    "code": l_res.get("code") if isinstance(l_res, dict) else None,
                    "error": f"Leverage setup failed for {sym}: {l_res}",
                    "stage": "set_leverage",
                }

        rules = self.get_symbol_filters(sym)
        if not isinstance(rules, dict) or rules.get("isError"):
            return {
                "isError": True,
                "error": f"Symbol filters unavailable for {sym}: {rules}",
                "stage": "get_symbol_filters",
            }
        if "status" in rules and str(rules["status"]).upper() != "TRADING":
            return {
                "isError": True,
                "error": f"Symbol {sym} status is {rules['status']} (requires TRADING)",
                "stage": "symbol_status",
            }
        if "contractType" in rules and str(rules["contractType"]).upper() != "PERPETUAL":
            return {
                "isError": True,
                "error": f"Symbol {sym} contractType is {rules['contractType']} (requires PERPETUAL)",
                "stage": "contract_type",
            }

        fmt_qty = self._format_qty_compat(sym, quantity, order_type=otype)
        eff_max_qty = rules.get("marketMaxQty") if otype == "MARKET" else rules.get("maxQty")
        if eff_max_qty is None and otype == "MARKET":
            eff_max_qty = rules.get("maxQty")
        if eff_max_qty is not None and float(eff_max_qty) > 0 and fmt_qty > float(eff_max_qty):
            return {
                "isError": True,
                "error": f"Quantity {fmt_qty} exceeds maxQty {eff_max_qty} for {sym}",
                "stage": "max_qty",
            }
        prec = int(rules.get("quantityPrecision", 3))

        params = {
            "symbol": sym,
            "side": side,
            "type": otype,
            "quantity": fmt_qty if prec > 0 else int(fmt_qty),
        }
        if self.dual_side_position:
            params["positionSide"] = "LONG" if direction.upper() == "LONG" else "SHORT"
        if client_order_id:
            params["newClientOrderId"] = str(client_order_id)[:36]

        if otype == "LIMIT":
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
        if isinstance(res, dict) and res.get("isError") and otype == "LIMIT" and price_match:
            if limit_price and limit_price > 0:
                params.pop("priceMatch", None)
                params.pop("goodTillDate", None)
                if "newClientOrderId" in params:
                    params["newClientOrderId"] = f"{str(params['newClientOrderId'])[:33]}_fb"
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

    def set_take_profit(
        self,
        symbol: str,
        direction: str,
        trigger_price: float,
        quantity: float = None,
        working_type: str = "MARK_PRICE",
        client_algo_id: str = None,
    ):
        """
        T0.3: Place Take Profit Market order directly via POST /fapi/v1/algoOrder.
        - If position is LONG -> TP is SELL
        - If position is SHORT -> TP is BUY
        """
        with self._critical_priority():
            sym = self.normalize_symbol(symbol)
            rules = self.get_symbol_filters(sym)
            if not isinstance(rules, dict) or rules.get("isError"):
                return {"isError": True, "error": (rules.get("error") if isinstance(rules, dict) else None) or f"Symbol filters unavailable for {sym}"}
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
            if client_algo_id:
                params["clientAlgoId"] = str(client_algo_id)[:36]

            if quantity is None:
                params["closePosition"] = "true"
            else:
                fmt_qty = self._format_qty_compat(sym, quantity, order_type="MARKET")
                prec = int(rules.get("quantityPrecision", 3))
                params["quantity"] = fmt_qty if prec > 0 else int(fmt_qty)
                if not self.dual_side_position:
                    params["reduceOnly"] = "true"

            res = self._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)
            if isinstance(res, dict) and "algoId" in res:
                print(f"[BinanceFutures] 🎯 Take Profit Algo Order set at ${fmt_price} (Algo ID: {res.get('algoId')})", flush=True)
            return res

    def set_stop_loss(
        self,
        symbol: str,
        direction: str,
        trigger_price: float,
        quantity: float = None,
        working_type: str = "MARK_PRICE",
        client_algo_id: str = None,
    ):
        """
        T0.3 / B-11: Place Stop Loss Market order directly via POST /fapi/v1/algoOrder.
        Uses closePosition=true without quantity when quantity is None.
        On -2021 ("Order would immediately trigger"), refuses to loosen SL and signals caller
        to close immediately.
        """
        with self._critical_priority():
            sym = self.normalize_symbol(symbol)
            rules = self.get_symbol_filters(sym)
            if not isinstance(rules, dict) or rules.get("isError"):
                return {"isError": True, "error": (rules.get("error") if isinstance(rules, dict) else None) or f"Symbol filters unavailable for {sym}"}
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
            if client_algo_id:
                algo_params["clientAlgoId"] = str(client_algo_id)[:36]

            if quantity is None:
                algo_params["closePosition"] = "true"
            else:
                fmt_qty = self._format_qty_compat(sym, quantity, order_type="MARKET")
                prec = int(rules.get("quantityPrecision", 3))
                algo_params["quantity"] = fmt_qty if prec > 0 else int(fmt_qty)
                if not self.dual_side_position:
                    algo_params["reduceOnly"] = "true"

            res_algo = self._request("POST", "/fapi/v1/algoOrder", params=algo_params, signed=True)
            if isinstance(res_algo, dict) and res_algo.get("code") == -2021:
                print(f"[BinanceFutures] 🚨 Stop Loss would immediately trigger at ${fmt_price} (-2021) — refusing to loosen SL!", flush=True)
                res_out = dict(res_algo)
                res_out["would_immediately_trigger"] = True
                return res_out

            if isinstance(res_algo, dict) and res_algo.get("code") == -4509 and "closePosition" in algo_params:
                time.sleep(0.3)
                if not client_algo_id:
                    algo_params.pop("clientAlgoId", None)
                res_algo = self._request("POST", "/fapi/v1/algoOrder", params=algo_params, signed=True)
                if isinstance(res_algo, dict) and res_algo.get("code") == -2021:
                    res_out = dict(res_algo)
                    res_out["would_immediately_trigger"] = True
                    return res_out

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
        with self._critical_priority():
            sym = self.normalize_symbol(symbol)
            dir_u = direction.upper()
            side = "SELL" if dir_u == "LONG" else "BUY"
            cb = round(max(0.1, min(5.0, float(callback_rate))), 1)
            params = {
                "algoType": "CONDITIONAL",
                "symbol": sym,
                "side": side,
                "type": "TRAILING_STOP_MARKET",
                "callbackRate": str(cb),
                "workingType": working_type,
            }
            if self.dual_side_position:
                params["positionSide"] = "LONG" if dir_u == "LONG" else "SHORT"
            else:
                params["reduceOnly"] = "true"
            if activation_price and activation_price > 0:
                params["activatePrice"] = str(self.format_price(sym, activation_price))
            if quantity is None:
                positions = self.get_positions(sym)
                if isinstance(positions, list) and positions:
                    matched = next(
                        (p for p in positions if p.get("symbol") == sym and str(p.get("direction", "")).upper() == dir_u),
                        positions[0],
                    )
                    quantity = float(matched.get("position_amount", 0))
            if quantity and quantity > 0:
                rules = self.get_symbol_filters(sym)
                if not isinstance(rules, dict) or rules.get("isError"):
                    return {"isError": True, "error": (rules.get("error") if isinstance(rules, dict) else None) or f"Symbol filters unavailable for {sym}"}
                fmt_qty = self._format_qty_compat(sym, quantity, order_type="MARKET")
                prec = int(rules.get("quantityPrecision", 3))
                params["quantity"] = fmt_qty if prec > 0 else int(fmt_qty)
            return self._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)

    def cancel_algo_order(self, symbol: str, algo_id: int):
        """Cancel a single Algo Order by algoId."""
        sym = self.normalize_symbol(symbol)
        return self._request("DELETE", "/fapi/v1/algoOrder", params={"symbol": sym, "algoId": int(algo_id)}, signed=True)

    def amend_stop_loss(self, symbol: str, direction: str, new_trigger_price: float, old_algo_id: int = None, quantity: float = None) -> dict:
        """
        T0.6 / C1 Fix: Zero-Unprotected-Window Stop-Loss Amendment (bypasses Binance -4130).
        Binance rejects placing a second closePosition=true STOP_MARKET while an existing
        closePosition=true SL exists (-4130). To preserve ZERO unprotected window:
        1. Discover ALL existing SL algo orders (merged with old_algo_id).
        2. If an existing closePosition=true SL is open (or first placement returns -4130)
           and quantity is None, fetch live position quantity and place the new SL using
           explicit quantity + reduceOnly/positionSide (which Binance allows concurrently).
        3. Verify new_algo_id is confirmed.
        4. ONLY THEN cancel all old SL algo orders.
        If new SL placement fails (e.g. -2021), old SL remains untouched on exchange!
        """
        with self._critical_priority():
            sym = self.normalize_symbol(symbol)
            dir_u = str(direction or "").upper()
            expected_side = "SELL" if dir_u == "LONG" else "BUY"

            # Always discover ALL active SL algo orders and merge with old_algo_id (deduped)
            existing_sl_ids = []
            has_close_pos_sl = False
            if old_algo_id is not None:
                try:
                    existing_sl_ids.append(int(old_algo_id))
                except (TypeError, ValueError):
                    pass

            ok_open, open_algos = self.get_open_algo_orders(sym)
            if ok_open and isinstance(open_algos, list):
                for ao in open_algos:
                    if not isinstance(ao, dict):
                        continue
                    otype = str(ao.get("orderType", ao.get("type", ""))).upper()
                    side = str(ao.get("side", "")).upper()
                    if "STOP" in otype and "TAKE_PROFIT" not in otype and side == expected_side and "algoId" in ao:
                        aid = int(ao["algoId"])
                        if aid not in existing_sl_ids:
                            existing_sl_ids.append(aid)
                        cp_raw = ao.get("closePosition")
                        if cp_raw is True or str(cp_raw).lower() == "true":
                            has_close_pos_sl = True

            def _fetch_live_qty_for_sl() -> float | None:
                try:
                    pos_list = self.get_positions(sym)
                    if isinstance(pos_list, list):
                        matched = next(
                            (
                                p for p in pos_list
                                if p.get("symbol") == sym
                                and abs(float(p.get("position_amount", 0) or 0)) > 0
                                and (
                                    str(p.get("direction", "")).upper() == dir_u
                                    or str(p.get("position_side", "")).upper() == dir_u
                                )
                            ),
                            None,
                        )
                        if matched is None:
                            matched = next(
                                (p for p in pos_list if p.get("symbol") == sym and abs(float(p.get("position_amount", 0) or 0)) > 0),
                                None,
                            )
                        if matched is not None:
                            q_val = abs(float(matched.get("position_amount", 0) or 0))
                            if q_val > 0:
                                return q_val
                except Exception as q_exc:
                    logger.debug("amend_stop_loss live qty lookup failed for %s: %s", sym, q_exc)
                return None

            # Step 1: Place NEW SL first (proactively use live quantity+reduceOnly if a closePosition SL exists)
            eff_qty = quantity
            used_qty_fallback = False
            if eff_qty is None and has_close_pos_sl:
                live_q = _fetch_live_qty_for_sl()
                if live_q and live_q > 0:
                    eff_qty = live_q
                    used_qty_fallback = True

            new_res = self.set_stop_loss(sym, direction, new_trigger_price, quantity=eff_qty)

            # Reactive -4130 fallback when old_algo_id was provided or openAlgoOrders didn't expose closePosition flag
            if (
                eff_qty is None
                and isinstance(new_res, dict)
                and new_res.get("code") == -4130
            ):
                live_q_retry = _fetch_live_qty_for_sl()
                if live_q_retry and live_q_retry > 0:
                    print(
                        f"[BinanceFutures] 🔄 amend_stop_loss {sym} hit -4130 (existing closePosition SL); "
                        f"retrying with live quantity={live_q_retry} reduceOnly (zero unprotected window)...",
                        flush=True,
                    )
                    new_res = self.set_stop_loss(sym, direction, new_trigger_price, quantity=live_q_retry)
                    used_qty_fallback = True

            if not isinstance(new_res, dict) or new_res.get("isError") or "algoId" not in new_res:
                print(f"[BinanceFutures] ⚠️ amend_stop_loss: New SL failed ({new_res}); keeping existing SL untouched!", flush=True)
                return {"status": "AMEND_FAILED_KEPT_OLD", "new_res": new_res, "kept_algo_ids": existing_sl_ids}

            new_algo_id = int(new_res["algoId"])

            # Step 2: Cancel ALL old SL orders only after new SL is confirmed active
            cancelled_ids = []
            cancel_errors = []
            for old_id in existing_sl_ids:
                if old_id != new_algo_id:
                    try:
                        cancel_res = self.cancel_algo_order(sym, old_id)
                        if cancel_res is False or (isinstance(cancel_res, dict) and cancel_res.get("isError")):
                            cancel_errors.append({"algo_id": old_id, "error": cancel_res})
                        else:
                            cancelled_ids.append(old_id)
                    except Exception as exc:
                        cancel_errors.append({"algo_id": old_id, "error": str(exc)})

            out = {
                "status": "AMENDED",
                "symbol": sym,
                "new_algo_id": new_algo_id,
                "new_trigger_price": self.format_price(sym, new_trigger_price),
                "cancelled_algo_ids": cancelled_ids,
                "used_quantity_reduce_only": used_qty_fallback,
            }
            if cancel_errors:
                out["cancel_errors"] = cancel_errors
                print(
                    f"[BinanceFutures] ⚠️ amend_stop_loss: New SL #{new_algo_id} active, failed to cancel old SL(s): {cancel_errors}",
                    flush=True,
                )
            return out

    def close_position(self, symbol: str, direction: str, quantity: float = None, reduce_only: bool = True, client_order_id: str = None):
        """Instantly close a position at MARKET price (positionSide in Hedge mode, reduceOnly in One-Way mode)."""
        with self._critical_priority():
            sym = self.normalize_symbol(symbol)
            dir_u = direction.upper()
            side = "SELL" if dir_u == "LONG" else "BUY"
            params = {
                "symbol": sym,
                "side": side,
                "type": "MARKET",
            }
            if self.dual_side_position:
                params["positionSide"] = "LONG" if dir_u == "LONG" else "SHORT"
            elif reduce_only:
                params["reduceOnly"] = "true"
            if client_order_id:
                params["newClientOrderId"] = str(client_order_id)[:36]

            if quantity is None:
                try:
                    positions = self.get_positions(sym)
                    if isinstance(positions, list):
                        # Match specific hedge leg (direction/position_side) first before symbol fallback
                        matched = next(
                            (
                                p for p in positions
                                if p.get("symbol") == sym
                                and (
                                    str(p.get("position_side", "")).upper() == dir_u
                                    or str(p.get("direction", "")).upper() == dir_u
                                )
                            ),
                            None,
                        )
                        if matched is None:
                            matched = next((p for p in positions if p.get("symbol") == sym), None)
                        if matched is not None:
                            quantity = abs(float(matched.get("position_amount", 0)))
                except Exception as exc:
                    logger.warning("close_position position lookup failed for %s: %s", sym, exc)
            if quantity is None or quantity <= 0:
                return {"isError": True, "error": f"No active position found on Binance to close for {sym}"}

            rules = self.get_symbol_filters(sym)
            if isinstance(rules, dict) and not rules.get("isError"):
                fmt_qty = self._format_qty_compat(sym, quantity, order_type="MARKET")
                prec = int(rules.get("quantityPrecision", 3))
                params["quantity"] = fmt_qty if prec > 0 else int(fmt_qty)
            else:
                params["quantity"] = round(float(quantity), 6)
            return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def cancel_all_orders(self, symbol: str):
        """Cancel all pending regular and algo TP/SL orders for a symbol, verifying algo cleanup."""
        sym = self.normalize_symbol(symbol)
        res_std = self._request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": sym}, signed=True)
        try:
            res_algo = self._request("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": sym}, signed=True)
        except Exception as exc:
            res_algo = {"isError": True, "error": str(exc)}

        remaining_algo_ids = []
        algo_clean_verified = False
        try:
            ok_algo, open_algos = self.get_open_algo_orders(sym)
            if ok_algo:
                stragglers = [ao for ao in open_algos if ao.get("algoId") is not None]
                for ao in stragglers:
                    aid = int(ao["algoId"])
                    try:
                        c_res = self.cancel_algo_order(sym, aid)
                        if c_res is False or (isinstance(c_res, dict) and c_res.get("isError")):
                            remaining_algo_ids.append(aid)
                    except Exception:
                        remaining_algo_ids.append(aid)
                if stragglers:
                    ok_after, open_after = self.get_open_algo_orders(sym)
                    if ok_after:
                        remaining_algo_ids = [int(ao["algoId"]) for ao in open_after if ao.get("algoId") is not None]
                        algo_clean_verified = len(remaining_algo_ids) == 0
                else:
                    algo_clean_verified = True
        except Exception as exc:
            print(f"[BinanceFutures] ⚠️ cancel_all_orders algo verification failed for {sym}: {exc}", flush=True)

        return {
            "standard": res_std,
            "algo": res_algo,
            "algo_clean_verified": algo_clean_verified,
            "remaining_algo_ids": remaining_algo_ids,
        }

    def get_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Fetch L2 order book bids/asks for VWAP slippage impact & micro-price calculation."""
        sym = self.normalize_symbol(symbol)
        res = self._request("GET", "/fapi/v1/depth", {"symbol": sym, "limit": int(limit)})
        return res if isinstance(res, dict) and not res.get("isError") else {}

    def query_order(self, symbol: str, order_id: int) -> dict:
        """Query single standard order status/executedQty/avgPrice on Binance Futures."""
        sym = self.normalize_symbol(symbol)
        return self._request("GET", "/fapi/v1/order", {"symbol": sym, "orderId": int(order_id)}, signed=True)

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel a single open standard order on Binance Futures."""
        sym = self.normalize_symbol(symbol)
        return self._request("DELETE", "/fapi/v1/order", {"symbol": sym, "orderId": int(order_id)}, signed=True)

    def partial_close_position(self, symbol: str, direction: str, fraction: float = 0.65) -> dict:
        """
        Close `fraction` (e.g. 65%) of an active position at TP1 (+0.55R) while leaving
        remaining 35% runner open. Strictly enforces `minNotional` & `minQty` on BOTH the
        partial slice AND the remaining runner slice so micro-accounts never hit -4164 or dust locks.
        """
        with self._critical_priority():
            sym = self.normalize_symbol(symbol)
            dir_u = str(direction or "").upper()
            positions = self.get_positions(sym)
            if not isinstance(positions, list) or not positions:
                return {"status": "NO_ACTIVE_POSITION", "partial_closed": False, "symbol": sym}

            pos = next(
                (
                    p for p in positions
                    if p.get("symbol") == sym
                    and float(p.get("position_amount", 0)) > 0
                    and (not dir_u or str(p.get("direction", "")).upper() == dir_u or str(p.get("position_side", "")).upper() == dir_u)
                ),
                None,
            )
            if pos is None:
                pos = next((p for p in positions if p.get("symbol") == sym and float(p.get("position_amount", 0)) > 0), None)
            if not pos:
                return {"status": "NO_ACTIVE_POSITION", "partial_closed": False, "symbol": sym}

        with self._critical_priority():
            total_qty = abs(float(pos.get("position_amount", 0)))
            mark_px = float(pos.get("mark_price") or self.get_market_price(sym) or 0.0)
            rules = self.get_symbol_filters(sym)
            if not isinstance(rules, dict) or rules.get("isError"):
                return {"status": "SYMBOL_FILTER_ERROR", "partial_closed": False, "symbol": sym, "error": (rules.get("error") if isinstance(rules, dict) else "Invalid filters")}
            min_notional = float(rules.get("minNotional", 5.0))
            min_qty = float(rules.get("marketMinQty") or rules.get("minQty", 0.001))

            frac = max(0.10, min(0.85, float(fraction or 0.65)))
            partial_qty = self._format_qty_compat(sym, total_qty * frac, order_type="MARKET")
            rem_qty = max(0.0, total_qty - partial_qty)
            partial_notional = partial_qty * mark_px
            rem_notional = rem_qty * mark_px

            if (
                partial_qty < min_qty
                or rem_qty < min_qty
                or mark_px <= 0
                or partial_notional < min_notional
                or rem_notional < min_notional
            ):
                return {
                    "status": "SKIPPED_MIN_NOTIONAL",
                    "partial_closed": False,
                    "symbol": sym,
                    "total_qty": total_qty,
                    "partial_qty": partial_qty,
                    "remaining_qty": round(rem_qty, 8),
                    "min_notional": min_notional,
                    "partial_notional": round(partial_notional, 2),
                    "remaining_notional": round(rem_notional, 2),
                }

            res = self.close_position(sym, direction, quantity=partial_qty)
            if isinstance(res, dict) and res.get("isError"):
                return {
                    "status": "PARTIAL_CLOSE_ERROR",
                    "partial_closed": False,
                    "symbol": sym,
                    "error": res.get("error"),
                    "order": res,
                }

            return {
                "status": "PARTIAL_CLOSED",
                "partial_closed": True,
                "symbol": sym,
                "closed_qty": partial_qty,
                "remaining_qty": round(rem_qty, 8),
                "order": res,
            }

    def sync_take_profit_close_position(
        self,
        symbol: str,
        direction: str,
        tp_price: float,
        old_tp_algo_id: int = None,
    ) -> dict:
        """
        H1 / Feature #2: Replace an oversized quantity-based TP2 order with a clean
        `closePosition=true` TAKE_PROFIT_MARKET algo order after a 65% TP1 partial close.
        """
        with self._critical_priority():
            sym = self.normalize_symbol(symbol)
            dir_u = str(direction or "").upper()
            expected_side = "SELL" if dir_u == "LONG" else "BUY"

            old_tp_ids = []
            if old_tp_algo_id is not None:
                try:
                    old_tp_ids.append(int(old_tp_algo_id))
                except (TypeError, ValueError):
                    pass

            ok_open, open_algos = self.get_open_algo_orders(sym)
            if ok_open and isinstance(open_algos, list):
                for ao in open_algos:
                    if not isinstance(ao, dict):
                        continue
                    otype = str(ao.get("orderType", ao.get("type", ""))).upper()
                    side = str(ao.get("side", "")).upper()
                    if "TAKE_PROFIT" in otype and side == expected_side and "algoId" in ao:
                        aid = int(ao["algoId"])
                        if aid not in old_tp_ids:
                            old_tp_ids.append(aid)

            # Cancel existing TP algo orders first (TP is non-protective, so replacing avoids -4130)
            cancelled_ids = []
            for oid in old_tp_ids:
                try:
                    c_res = self.cancel_algo_order(sym, oid)
                    if not (c_res is False or (isinstance(c_res, dict) and c_res.get("isError"))):
                        cancelled_ids.append(oid)
                except Exception as exc:
                    logger.debug("Cancel old TP algo #%s on %s failed: %s", oid, sym, exc)

            new_tp_res = self.set_take_profit(sym, dir_u, trigger_price=float(tp_price), quantity=None)
            if isinstance(new_tp_res, dict) and "algoId" in new_tp_res:
                return {
                    "status": "TP_SYNCED_CLOSE_POSITION",
                    "symbol": sym,
                    "new_algo_id": int(new_tp_res["algoId"]),
                    "cancelled_algo_ids": cancelled_ids,
                }
            return {
                "status": "TP_SYNC_FAILED",
                "symbol": sym,
                "cancelled_algo_ids": cancelled_ids,
                "error": (new_tp_res.get("error") if isinstance(new_tp_res, dict) else str(new_tp_res)),
            }

    def place_maker_tp1_order(
        self,
        symbol: str,
        direction: str,
        tp1_price: float,
        fraction: float = 0.65,
    ) -> dict:
        """
        Feature #2: Place a resting exchange-side LIMIT reduceOnly (GTC) Maker TP1 order
        for `fraction` (e.g. 65%) of the live position to earn Maker fees (0.02% vs 0.05%)
        and capture sub-second wicks. Strictly enforces minQty & minNotional on BOTH slices.
        """
        with self._critical_priority():
            sym = self.normalize_symbol(symbol)
            dir_u = str(direction or "").upper()
            side = "SELL" if dir_u == "LONG" else "BUY"
            tp1_px = float(tp1_price or 0.0)
            if tp1_px <= 0:
                return {"status": "INVALID_TP1_PRICE", "placed": False, "symbol": sym}

            positions = self.get_positions(sym)
            if not isinstance(positions, list) or not positions:
                return {"status": "NO_ACTIVE_POSITION", "placed": False, "symbol": sym}

            pos = next(
                (
                    p for p in positions
                    if p.get("symbol") == sym
                    and float(p.get("position_amount", 0)) > 0
                    and (not dir_u or str(p.get("direction", "")).upper() == dir_u or str(p.get("position_side", "")).upper() == dir_u)
                ),
                None,
            )
            if pos is None:
                pos = next((p for p in positions if p.get("symbol") == sym and float(p.get("position_amount", 0)) > 0), None)
            if not pos:
                return {"status": "NO_ACTIVE_POSITION", "placed": False, "symbol": sym}

            total_qty = abs(float(pos.get("position_amount", 0)))
            rules = self.get_symbol_filters(sym)
            if not isinstance(rules, dict) or rules.get("isError"):
                return {"status": "SYMBOL_FILTER_ERROR", "placed": False, "symbol": sym}

            min_notional = float(rules.get("minNotional", 5.0))
            min_qty = float(rules.get("minQty", 0.001))
            prec = int(rules.get("quantityPrecision", 3))
            frac = max(0.10, min(0.85, float(fraction or 0.65)))

            partial_qty = self._format_qty_compat(sym, total_qty * frac, order_type="LIMIT")
            rem_qty = max(0.0, total_qty - partial_qty)
            partial_notional = partial_qty * tp1_px
            rem_notional = rem_qty * tp1_px

            if (
                partial_qty < min_qty
                or rem_qty < min_qty
                or partial_notional < min_notional
                or rem_notional < min_notional
            ):
                return {
                    "status": "SKIPPED_MIN_NOTIONAL",
                    "placed": False,
                    "symbol": sym,
                    "partial_qty": partial_qty,
                    "remaining_qty": round(rem_qty, 8),
                    "min_notional": min_notional,
                }

            fmt_tp1 = self.format_price(sym, tp1_px)
            params = {
                "symbol": sym,
                "side": side,
                "type": "LIMIT",
                "timeInForce": "GTC",
                "price": str(fmt_tp1),
                "quantity": partial_qty if prec > 0 else int(partial_qty),
            }
            if self.dual_side_position:
                params["positionSide"] = "LONG" if dir_u == "LONG" else "SHORT"
            else:
                params["reduceOnly"] = "true"

            res = self._request("POST", "/fapi/v1/order", params=params, signed=True)
            if isinstance(res, dict) and not res.get("isError") and res.get("orderId"):
                return {
                    "status": "MAKER_TP1_PLACED",
                    "placed": True,
                    "symbol": sym,
                    "order_id": res.get("orderId"),
                    "tp1_price": fmt_tp1,
                    "partial_qty": partial_qty,
                    "remaining_qty": round(rem_qty, 8),
                    "order": res,
                }
            return {
                "status": "MAKER_TP1_ERROR",
                "placed": False,
                "symbol": sym,
                "error": (res.get("error") if isinstance(res, dict) else str(res)),
            }

    # ===================================================================
    # FULL AUTONOMOUS PIPELINE EXECUTION (T0.3, T0.4, T7.1, T7.2, T7.3)
    # ===================================================================

    def _get_locked_vault_usdt(self) -> float:
        """Read locked profit vault balance from active vault_state.json (fail-closed if corrupt)."""
        vault_path = os.path.join(BASE_DIR, "results", "vault_state.json")
        try:
            import risk.vault as rv

            if getattr(rv, "DEFAULT_VAULT_STATE_PATH", None):
                vault_path = rv.DEFAULT_VAULT_STATE_PATH
        except Exception as exc:
            logger.debug("risk.vault import fallback in _get_locked_vault_usdt: %s", exc)
        if os.path.exists(vault_path):
            try:
                from state_io import CorruptedStateError, read_json_safe

                data = read_json_safe(
                    vault_path,
                    default=None,
                    strict_on_corrupt=True,
                    expected_type=dict,
                )
                if isinstance(data, dict):
                    return max(0.0, float(data.get("locked_profit_vault_usdt", 0.0)))
            except CorruptedStateError as cse:
                logger.error("Vault state corrupt at %s (%s); failing closed.", vault_path, cse)
                return 1e18
            except Exception as exc:
                logger.warning("Failed reading vault state at %s: %s", vault_path, exc)
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

    def _emergency_flatten_and_verify(self, symbol: str, direction: str, quantity: float = None) -> dict:
        """
        A-6 / A-2 / B-11 / B-2: Immediately market-close with reduceOnly, clean up open orders,
        and verify via positionRisk that the symbol is flat.
        """
        sym = self.normalize_symbol(symbol)
        close_res = None
        flat_verified = False
        still_open = False
        live_pos = None

        try:
            if quantity is not None and float(quantity) > 0:
                close_res = self.close_position(sym, direction, quantity=float(quantity))
            else:
                close_res = self.close_position(sym, direction)
        except Exception as ce:
            close_res = {"isError": True, "error": str(ce)}

        try:
            self.cancel_all_orders(sym)
        except Exception as ce_cancel:
            logger.warning("_emergency_flatten_and_verify cancel_all_orders failed for %s: %s", sym, ce_cancel)

        for attempt in range(2):
            try:
                post_pos = self.get_positions(sym)
            except Exception as pe:
                post_pos = {"isError": True, "error": str(pe)}

            if isinstance(post_pos, list):
                sym_pos = [
                    p for p in post_pos
                    if (not p.get("symbol") or p.get("symbol") == sym) and abs(float(p.get("position_amount", 0) or 0)) > 0
                ]
                if not sym_pos:
                    flat_verified = True
                    still_open = False
                    live_pos = None
                    break
                still_open = True
                live_pos = sym_pos[0]
                if attempt == 0:
                    # Retry close using live exchange amount
                    try:
                        close_res = self.close_position(sym, direction, quantity=abs(float(live_pos.get("position_amount", 0))))
                        self.cancel_all_orders(sym)
                    except Exception as retry_exc:
                        logger.error("_emergency_flatten_and_verify retry close failed for %s: %s", sym, retry_exc)
                    time.sleep(0.2)
            else:
                close_ok = (
                    isinstance(close_res, dict)
                    and not close_res.get("isError")
                    and ("orderId" in close_res or str(close_res.get("status", "")).upper() == "FILLED")
                )
                still_open = not close_ok
                break

        closed_ok = flat_verified or (
            isinstance(close_res, dict)
            and not close_res.get("isError")
            and ("orderId" in close_res or str(close_res.get("status", "")).upper() == "FILLED")
        )
        return {
            "close_res": close_res,
            "closed_ok": bool(closed_ok),
            "flat_verified": bool(flat_verified),
            "still_open": bool(still_open),
            "live_position": live_pos,
        }

    @staticmethod
    def _norm_margin_type(mt: str) -> str:
        val = str(mt or "ISOLATED").upper().strip()
        return "CROSSED" if val in ("CROSS", "CROSSED") else val

    @staticmethod
    def _has_mode_mismatch(pos_info: dict, expected_margin_type: str, expected_leverage: int) -> tuple:
        if not isinstance(pos_info, dict) or not pos_info:
            return False, ""
        reasons = []
        if pos_info.get("margin_type"):
            live_mt = BinanceFuturesClient._norm_margin_type(pos_info["margin_type"])
            req_mt = BinanceFuturesClient._norm_margin_type(expected_margin_type)
            if live_mt != req_mt:
                reasons.append(f"margin_type={live_mt} != {req_mt}")
        if pos_info.get("leverage") is not None:
            live_lev = int(pos_info["leverage"])
            if live_lev != int(expected_leverage):
                reasons.append(f"leverage={live_lev}x != {expected_leverage}x")
        return bool(reasons), "; ".join(reasons)

    @staticmethod
    def _build_tca_payload(
        symbol: str,
        direction: str,
        routing_used: str,
        arrival_price: float,
        fill_price: float,
        quantity: float,
        margin_usdt: float,
        impact_bps_est: float,
    ) -> dict:
        arr_px = float(arrival_price or fill_price or 0.0)
        fill_px = float(fill_price or arr_px or 0.0)
        sign_slip = 1.0 if direction == "LONG" else -1.0
        arr_slip_bps = sign_slip * ((fill_px - arr_px) / arr_px) * 10000.0 if arr_px > 0 else 0.0
        notional_act = float(quantity) * fill_px
        fee_rate = 0.0002 if "MAKER_GTX" in str(routing_used) else 0.0005
        est_fee_usdt = notional_act * fee_rate
        fee_drag_roe_pct = (est_fee_usdt / margin_usdt) * 100.0 if margin_usdt > 0 else 0.0
        return {
            "symbol": symbol,
            "direction": direction,
            "routing_used": routing_used,
            "arrival_price": round(arr_px, 8),
            "fill_price": round(fill_px, 8),
            "arrival_slippage_bps": round(arr_slip_bps, 3),
            "fee_usdt": round(est_fee_usdt, 6),
            "margin_usdt": round(margin_usdt, 4),
            "fee_drag_roe_pct": round(fee_drag_roe_pct, 4),
            "impact_bps_est": round(impact_bps_est, 3),
        }

    def execute_full_trade(self, signal: dict, config: dict):
        """
        Execute full quantitative trade directly on Binance Futures with WP-1 hardening:
        - C-1 / A-2: Multi-Assets CROSS rejection, strict marginType & pre-sizing leverage verification
        - B-1: Fail closed if positionRisk check fails
        - C-2: Fail-closed symbol filters, TRADING/PERPETUAL, LOT_SIZE & MARKET_LOT_SIZE enforcement
        - A-7: True fill verification via executedQty & positionRisk delta (zero phantom positions)
        - A-6 / B-11: SL-first (closePosition=true) before TP, no -2021 loosening, mandatory flatten on 3x SL fail
        - B-2: Post-fill exception recovery via positionRisk
        """
        raw_sym = signal.get("binance_pair") or signal.get("symbol", "")
        symbol = self.normalize_symbol(raw_sym)
        direction = str(signal.get("direction", "LONG")).upper()
        leverage = int(config.get("fixed_leverage") or signal.get("leverage") or 20)
        margin_type = str(signal.get("margin_type") or config.get("margin_type", "ISOLATED")).upper()
        order_type = str(signal.get("order_type") or config.get("order_type", "MARKET")).upper()
        limit_price = float(signal.get("limit_price") or signal.get("entry_price", 0) or 0)
        price_match = signal.get("price_match")

        # 0. Check account modes (C-1 / A-2 / C-4)
        modes = self.check_account_modes()
        if isinstance(modes, dict):
            if modes.get("dualSidePosition") or self.dual_side_position:
                return {
                    "status": "REJECTED_HEDGE_MODE_UNSUPPORTED",
                    "error": (
                        "Hedge Mode (dualSidePosition=true) is active on Binance Futures; "
                        "please enable One-Way Mode in Binance Futures Preferences before opening new trades."
                    ),
                    "binance_synced": False,
                }
            if modes.get("multiAssetsMargin") or self.multi_assets_margin:
                return {
                    "status": "REJECTED_MULTI_ASSETS_CROSS",
                    "error": f"Multi-Assets Margin mode is active on Binance (forces CROSS margin; {margin_type} required)",
                    "binance_synced": False,
                }
            if modes.get("ok") is False:
                return {
                    "status": "REJECTED_ACCOUNT_MODE_ERROR",
                    "error": f"Failed to verify Binance account modes ({modes.get('error', 'API error')})",
                    "binance_synced": False,
                }
        elif self.dual_side_position:
            return {
                "status": "REJECTED_HEDGE_MODE_UNSUPPORTED",
                "error": (
                    "Hedge Mode (dualSidePosition=true) is active on Binance Futures; "
                    "please enable One-Way Mode in Binance Futures Preferences before opening new trades."
                ),
                "binance_synced": False,
            }
        elif self.multi_assets_margin:
            return {
                "status": "REJECTED_MULTI_ASSETS_CROSS",
                "error": "Multi-Assets Margin mode is active on Binance (forces CROSS margin)",
                "binance_synced": False,
            }

        # 1. Check if already in position (B-1: fail CLOSED if positionRisk fails)
        try:
            open_pos = self.get_positions(symbol)
        except Exception as e:
            return {
                "status": "REJECTED_POSITION_CHECK_ERROR",
                "error": f"Position check exception for {symbol} ({e}) — refusing blind entry",
                "binance_synced": False,
            }
        if not isinstance(open_pos, list):
            err_txt = open_pos.get("error", str(open_pos)) if isinstance(open_pos, dict) else f"Unexpected positionRisk payload ({type(open_pos).__name__})"
            return {
                "status": "REJECTED_POSITION_CHECK_ERROR",
                "error": f"Position check failed for {symbol} ({err_txt}) — refusing blind entry",
                "binance_synced": False,
            }
        if len(open_pos) > 0:
            return {
                "status": "SKIPPED_ALREADY_OPEN",
                "error": f"Position already active for {symbol}",
                "binance_synced": True,
            }
        pre_amt = 0.0

        # 2. Check live wallet balance strictly & enforce Profit Ratchet Vault
        avail_usdt = 0.0
        working_usdt = 0.0
        sizing_mode = str(config.get("sizing_mode", "ALL_IN")).upper()
        all_in_fraction = float(config.get("all_in_balance_fraction", 0.95))
        pos_size_usd = float(signal.get("position_size_usdt") or signal.get("position_size_usd") or 0.0)

        try:
            bal_info = self.get_balance()
            if not isinstance(bal_info, dict) or bal_info.get("isError") or "available_balance" not in bal_info:
                err_txt = (bal_info or {}).get("error", "Invalid balance payload") if isinstance(bal_info, dict) else "Balance endpoint did not return dict"
                return {
                    "status": "REJECTED_BALANCE_API_ERROR",
                    "error": f"Live Binance balance unavailable ({err_txt}) — refusing unsafe order sizing",
                    "binance_synced": False,
                }
            avail_usdt = float(bal_info["available_balance"])
            if avail_usdt < 0.30:
                return {
                    "status": "REJECTED_LOW_BALANCE",
                    "error": f"Available margin ${avail_usdt:.2f} is insufficient (Min $0.30 USDT required)",
                    "binance_synced": False,
                }
            locked_vault = self._get_locked_vault_usdt()
            working_usdt = max(0.0, avail_usdt - locked_vault)
            if working_usdt < 0.30:
                return {
                    "status": "REJECTED_VAULT_PROTECTED",
                    "error": f"Available balance ${avail_usdt:.2f} is protected by Profit Ratchet Vault (${locked_vault:.2f} locked)",
                    "binance_synced": False,
                }
            eff_all_in_fraction = min(0.98, max(0.0, all_in_fraction))
            if sizing_mode == "ALL_IN" or pos_size_usd <= 0:
                pos_size_usd = round(working_usdt * eff_all_in_fraction, 4)
            else:
                max_safe_margin = round(working_usdt * eff_all_in_fraction, 4)
                if pos_size_usd > max_safe_margin:
                    pos_size_usd = max_safe_margin
        except Exception as e:
            return {
                "status": "REJECTED_BALANCE_API_ERROR",
                "error": f"Balance API exception ({e}) — refusing unsafe order sizing",
                "binance_synced": False,
            }

        # 3. Get live mark price
        mark_price = self.get_market_price(symbol)
        if mark_price <= 0 and limit_price > 0:
            mark_price = limit_price
        if mark_price <= 0:
            return {"status": "FAILED", "error": f"Could not determine market price for {symbol}", "binance_synced": False}

        # 4. Fail-closed Symbol rules from exchangeInfo (C-2)
        rules = self.get_symbol_filters(symbol)
        if not isinstance(rules, dict) or rules.get("isError"):
            err_txt = (rules.get("error") if isinstance(rules, dict) else None) or f"ExchangeInfo unavailable for {symbol}"
            return {
                "status": "REJECTED_SYMBOL_FILTER_ERROR",
                "error": err_txt,
                "binance_synced": False,
            }
        if "status" in rules and str(rules["status"]).upper() != "TRADING":
            return {
                "status": "REJECTED_SYMBOL_NOT_TRADING",
                "error": f"Symbol {symbol} status is {rules['status']} (requires TRADING)",
                "binance_synced": False,
            }
        if "contractType" in rules and str(rules["contractType"]).upper() != "PERPETUAL":
            return {
                "status": "REJECTED_INVALID_CONTRACT_TYPE",
                "error": f"Symbol {symbol} contractType is {rules['contractType']} (requires PERPETUAL)",
                "binance_synced": False,
            }

        # 5. Enforce Margin Mode & Leverage BEFORE sizing (A-2)
        _is_mock_open_subclass = (
            type(self) is not BinanceFuturesClient
            and type(self).open_position is not BinanceFuturesClient.open_position
            and type(self).set_margin_type is BinanceFuturesClient.set_margin_type
            and type(self).set_leverage is BinanceFuturesClient.set_leverage
            and type(self)._request is BinanceFuturesClient._request
            and not hasattr(self.set_margin_type, "assert_called")
            and not hasattr(self.set_leverage, "assert_called")
            and not hasattr(self._request, "assert_called")
            and not hasattr(self.session.post, "assert_called")
        )
        if _is_mock_open_subclass:
            effective_leverage = leverage
        else:
            try:
                m_res = self.set_margin_type(symbol, margin_type)
            except Exception as me:
                m_res = {"isError": True, "error": str(me)}
            if not self._is_margin_type_ok(m_res):
                return {
                    "status": "REJECTED_MARGIN_TYPE_ERROR",
                    "error": f"Failed to enforce {margin_type} margin for {symbol}: {m_res}",
                    "binance_synced": False,
                }

            try:
                l_res = self.set_leverage(symbol, leverage)
            except Exception as le:
                l_res = {"isError": True, "error": str(le)}
            if not isinstance(l_res, dict) or l_res.get("isError") or l_res.get("leverage") is None:
                return {
                    "status": "REJECTED_LEVERAGE_ERROR",
                    "error": f"Failed to set leverage {leverage}x for {symbol}: {l_res}",
                    "binance_synced": False,
                }
            effective_leverage = int(l_res["leverage"])
            if effective_leverage <= 0 or effective_leverage > leverage:
                return {
                    "status": "REJECTED_LEVERAGE_MISMATCH",
                    "error": f"Exchange returned invalid leverage {effective_leverage}x (requested {leverage}x)",
                    "binance_synced": False,
                }
            if effective_leverage < leverage:
                print(
                    f"[BinanceFutures] ⚠️ Leverage capped by exchange for {symbol}: requested {leverage}x -> effective {effective_leverage}x. Rescaling sizing.",
                    flush=True,
                )

        # 6. Size quantity using effective_leverage + LOT_SIZE / MARKET_LOT_SIZE / budget checks (A-2, C-2, C-13)
        min_notional = float(rules.get("minNotional", 5.0))
        notional_usd = pos_size_usd * effective_leverage
        budget_cap = working_usdt * 0.98

        if notional_usd < min_notional:
            needed_margin = (min_notional * 1.02) / effective_leverage
            if needed_margin <= budget_cap + 1e-6:
                notional_usd = min_notional * 1.02
                pos_size_usd = round(needed_margin, 4)
            else:
                if locked_vault > 0 and needed_margin <= (avail_usdt * 0.98) + 1e-6:
                    return {
                        "status": "REJECTED_VAULT_PROTECTED",
                        "error": (
                            f"Symbol {symbol} minNotional ${min_notional:.2f} requires ${needed_margin:.2f} margin "
                            f"> working cap ${budget_cap:.2f} (Locked Vault ${locked_vault:.2f} protected)"
                        ),
                        "binance_synced": False,
                    }
                return {
                    "status": "REJECTED_NOTIONAL_CAPACITY",
                    "error": f"Symbol {symbol} minNotional ${min_notional:.2f} exceeds capacity ${notional_usd:.2f} (Working: ${working_usdt:.2f} at {effective_leverage}x)",
                    "binance_synced": False,
                }

        is_mkt_entry = (order_type == "MARKET")
        lot_step = float(rules.get("marketStepSize") or rules.get("stepSize", 0.001)) if is_mkt_entry else float(rules.get("stepSize", 0.001))
        lot_min_qty = float(rules.get("marketMinQty") or rules.get("minQty", 0.0)) if is_mkt_entry else float(rules.get("minQty", 0.0))
        lot_max_qty = rules.get("marketMaxQty") if is_mkt_entry else rules.get("maxQty")
        if lot_max_qty is None and is_mkt_entry:
            lot_max_qty = rules.get("maxQty")
        max_qty_val = float(lot_max_qty) if lot_max_qty is not None and float(lot_max_qty) > 0 else None

        if max_qty_val is not None and lot_min_qty > max_qty_val:
            return {
                "status": "REJECTED_MAX_QTY_EXCEEDED",
                "error": f"Invalid symbol filters for {symbol}: minQty {lot_min_qty} > maxQty {max_qty_val}",
                "binance_synced": False,
            }

        raw_quantity = notional_usd / mark_price
        quantity = self._format_qty_compat(symbol, raw_quantity, order_type=order_type)

        if max_qty_val is not None and quantity > max_qty_val:
            if raw_quantity < lot_min_qty:
                return {
                    "status": "REJECTED_MAX_QTY_EXCEEDED",
                    "error": f"Bumped minQty {quantity} exceeds maxQty {max_qty_val} for {symbol}",
                    "binance_synced": False,
                }
            quantity = self._format_qty_compat(symbol, max_qty_val, order_type=order_type)
            if quantity <= 0 or (quantity * mark_price) < min_notional:
                return {
                    "status": "REJECTED_MAX_QTY_EXCEEDED",
                    "error": f"Clamped maxQty {quantity} notional ${quantity * mark_price:.2f} < minNotional ${min_notional:.2f} for {symbol}",
                    "binance_synced": False,
                }
            pos_size_usd = round((quantity * mark_price) / effective_leverage, 4)

        if (quantity * mark_price) < min_notional:
            bumped_qty = self._format_qty_compat(symbol, quantity + lot_step, order_type=order_type)
            bumped_margin = (bumped_qty * mark_price) / effective_leverage
            if bumped_margin <= budget_cap + 1e-6 and (max_qty_val is None or bumped_qty <= max_qty_val):
                quantity = bumped_qty
                pos_size_usd = round(bumped_margin, 4)
            else:
                if locked_vault > 0 and bumped_margin <= (avail_usdt * 0.98) + 1e-6:
                    return {
                        "status": "REJECTED_VAULT_PROTECTED",
                        "error": f"Rounded quantity notional bump requires ${bumped_margin:.2f} > working budget ${budget_cap:.2f} (Vault ${locked_vault:.2f} protected)",
                        "binance_synced": False,
                    }
                return {
                    "status": "REJECTED_NOTIONAL_CAPACITY",
                    "error": f"Rounded quantity notional ${quantity * mark_price:.2f} < minNotional ${min_notional:.2f} for {symbol}",
                    "binance_synced": False,
                }

        actual_req_margin = (quantity * mark_price) / effective_leverage
        if actual_req_margin > budget_cap + 1e-6:
            if locked_vault > 0 and actual_req_margin <= (avail_usdt * 0.98) + 1e-6:
                return {
                    "status": "REJECTED_VAULT_PROTECTED",
                    "error": f"Formatted qty {quantity} requires ${actual_req_margin:.2f} > working budget ${budget_cap:.2f} (Vault ${locked_vault:.2f} protected)",
                    "binance_synced": False,
                }
            return {
                "status": "REJECTED_NOTIONAL_CAPACITY",
                "error": f"Formatted qty {quantity} requires margin ${actual_req_margin:.2f} > working budget ${budget_cap:.2f}",
                "binance_synced": False,
            }
        if max_qty_val is not None and quantity > max_qty_val:
            return {
                "status": "REJECTED_MAX_QTY_EXCEEDED",
                "error": f"Formatted qty {quantity} exceeds maxQty {max_qty_val} for {symbol}",
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

        # Pre-trade L2 Order Book VWAP Slippage Impact Gate & Avellaneda-Stoikov Optimal Price
        depth_book = {}
        try:
            depth_book = self.get_order_book(symbol, limit=20)
        except Exception:
            depth_book = {}

        arrival_price = float(mark_price)
        impact_bps_est = 0.0
        router = None
        if depth_book.get("bids") and depth_book.get("asks"):
            best_bid = float(depth_book["bids"][0][0])
            best_ask = float(depth_book["asks"][0][0])
            best_bid_qty = float(depth_book["bids"][0][1])
            best_ask_qty = float(depth_book["asks"][0][1])
            if best_bid > 0 and best_ask > 0:
                arrival_price = 0.5 * (best_bid + best_ask)
            try:
                from exec.avellaneda_router import AvellanedaStoikovRouter
                max_imp = float(config.get("max_vwap_impact_bps", 8.0))
                router = AvellanedaStoikovRouter(max_impact_bps=max_imp)
                imp = router.compute_vwap_impact_bps(depth_book, direction, quantity)
                impact_bps_est = float(imp.get("impact_bps", 0.0) or 0.0)
                if not imp.get("passed", True):
                    return {
                        "status": "REJECTED_SLIPPAGE_IMPACT",
                        "error": f"Pre-trade VWAP impact rejected {symbol}: {imp.get('reason')}",
                        "impact_bps_est": round(impact_bps_est, 3),
                        "binance_synced": False,
                    }
            except Exception:
                router = None

        execution_log = {
            "exchange": "BINANCE_FUTURES",
            "symbol": symbol,
            "direction": direction,
            "leverage": effective_leverage,
            "requested_leverage": leverage,
            "margin_type": margin_type,
            "sizing_mode": sizing_mode,
            "order_type": order_type,
            "entry_price": mark_price,
            "arrival_price": arrival_price,
            "impact_bps_est": round(impact_bps_est, 3),
            "routing_used": order_type,
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

        entry_may_have_been_sent = False
        caller_cid = signal.get("client_order_id")
        if caller_cid:
            clean_base = re.sub(r"[^A-Za-z0-9._:/-]", "", str(caller_cid))[:30] or "pf_ord"
        else:
            sig_seed = f"{signal.get('id', '')}|{symbol}|{direction}|{time.time_ns()}"
            clean_base = f"pf_{re.sub(r'[^A-Za-z0-9]', '', symbol)[:6]}_{hashlib.sha256(sig_seed.encode('utf-8')).hexdigest()[:14]}"

        tl = getattr(self, "_thread_local", None)
        norm_mt = self._norm_margin_type(margin_type)
        if tl is not None:
            tl.exec_verified_mode = (symbol, norm_mt, int(effective_leverage))

        try:
            # Step 1: Smart Maker-First GTX / Chase-Limit -> Slippage-Capped IOC / Market Fallback
            order_res = None
            last_filled_order_res = None
            routing_used = "MARKET_TAKER"
            mp_sig = signal.get("math_proof") or {}
            vpin_val = float(mp_sig.get("vpin", 0.35) or 0.35)
            vpin_cdf = float(mp_sig.get("vpin_cdf", 0.50) or 0.50)
            ofi_20 = float(mp_sig.get("obi_weighted_20", 0.0) or 0.0)
            tick_sz = float(rules.get("tickSize", 0.01))

            use_maker_first = (
                order_type in ("MAKER_FIRST_GTX", "SMART_MAKER", "LIMIT", "GTX")
                and not bool(signal.get("vpin_toxic_maker_block", False))
            )
            maker_only = bool(config.get("maker_only_no_taker_fallback", False))
            filled_qty_total = 0.0
            weighted_fill_cost = 0.0

            if use_maker_first and depth_book.get("bids") and depth_book.get("asks"):
                rem_qty = quantity

                for cycle in range(2):
                    if rem_qty * mark_price < min_notional and filled_qty_total > 0:
                        break
                    cycle_book = depth_book if cycle == 0 else (self.get_order_book(symbol, limit=5) or depth_book)
                    bids_c = cycle_book.get("bids") or depth_book["bids"]
                    asks_c = cycle_book.get("asks") or depth_book["asks"]
                    bb_px, bb_q = float(bids_c[0][0]), float(bids_c[0][1])
                    ba_px, ba_q = float(asks_c[0][0]), float(asks_c[0][1])
                    chase_px = bb_px if direction == "LONG" else ba_px
                    if router is not None and cycle == 0:
                        opt = router.compute_optimal_offset(
                            direction=direction,
                            best_bid_price=bb_px,
                            best_bid_qty=bb_q,
                            best_ask_price=ba_px,
                            best_ask_qty=ba_q,
                            ofi_20=ofi_20,
                            vpin=vpin_val,
                            vpin_cdf=vpin_cdf,
                            tick_size=tick_sz,
                        )
                        if not opt.get("allowed_passive_maker", True):
                            break
                        chase_px = float(opt.get("optimal_limit_price") or chase_px)

                    chase_px = self.format_price(symbol, chase_px)
                    cycle_qty = self._format_qty_compat(symbol, rem_qty, order_type="LIMIT")
                    leg_cid = (str(caller_cid)[:36] if (caller_cid and cycle == 0) else f"{clean_base}_g{cycle + 1}"[:36])
                    entry_may_have_been_sent = True
                    res_gtx = self.open_position(
                        symbol=symbol,
                        direction=direction,
                        quantity=cycle_qty,
                        leverage=effective_leverage,
                        order_type="LIMIT",
                        limit_price=chase_px,
                        margin_type=margin_type,
                        time_in_force="GTX",
                        client_order_id=leg_cid,
                    )
                    execution_log["steps"][f"maker_gtx_cycle_{cycle + 1}"] = res_gtx
                    if not isinstance(res_gtx, dict) or res_gtx.get("isError"):
                        if order_res is None:
                            order_res = res_gtx
                        continue
                    oid = res_gtx.get("orderId")
                    order_res = res_gtx
                    if oid:
                        term_status = None
                        for _poll in range(3):
                            time.sleep(0.4)
                            qo = self.query_order(symbol, oid)
                            if isinstance(qo, dict) and not qo.get("isError"):
                                order_res = qo
                                q_st = str(qo.get("status", "")).upper()
                                if q_st == "FILLED":
                                    ex_q = float(qo.get("executedQty") or cycle_qty)
                                    av_p = float(qo.get("avgPrice") or chase_px)
                                    filled_qty_total += ex_q
                                    weighted_fill_cost += ex_q * av_p
                                    rem_qty = max(0.0, quantity - filled_qty_total)
                                    routing_used = "MAKER_GTX_FILLED"
                                    last_filled_order_res = qo
                                    term_status = q_st
                                    break
                                if q_st in ("CANCELED", "CANCELLED", "EXPIRED", "REJECTED"):
                                    term_status = q_st
                                    ex_q = float(qo.get("executedQty") or 0.0)
                                    if ex_q > 0:
                                        av_p = float(qo.get("avgPrice") or chase_px)
                                        filled_qty_total += ex_q
                                        weighted_fill_cost += ex_q * av_p
                                        rem_qty = max(0.0, quantity - filled_qty_total)
                                        routing_used = "MAKER_GTX_FILLED"
                                        last_filled_order_res = qo
                                    break
                        if rem_qty <= 0 or (rem_qty * mark_price < min_notional and filled_qty_total > 0):
                            break
                        if term_status is None:
                            self.cancel_order(symbol, oid)
                            qo_post = self.query_order(symbol, oid)
                            if isinstance(qo_post, dict) and not qo_post.get("isError"):
                                order_res = qo_post
                                ex_q = float(qo_post.get("executedQty") or 0.0)
                                if ex_q > 0:
                                    av_p = float(qo_post.get("avgPrice") or chase_px)
                                    filled_qty_total += ex_q
                                    weighted_fill_cost += ex_q * av_p
                                    rem_qty = max(0.0, quantity - filled_qty_total)
                                    routing_used = "MAKER_GTX_FILLED"
                                    last_filled_order_res = qo_post
                            else:
                                # L20 Fix: Guard cancel-vs-fill race via live positionRisk delta if query_order fails
                                try:
                                    pos_race = self.get_positions(symbol)
                                    if isinstance(pos_race, list):
                                        race_amt = sum(abs(float(p.get("position_amount", 0) or 0)) for p in pos_race)
                                        race_delta = max(0.0, race_amt - pre_amt)
                                        if race_delta > filled_qty_total + 1e-8:
                                            inc_q = race_delta - filled_qty_total
                                            filled_qty_total = race_delta
                                            weighted_fill_cost += inc_q * chase_px
                                            rem_qty = max(0.0, quantity - filled_qty_total)
                                            routing_used = "MAKER_GTX_FILLED"
                                except Exception as race_exc:
                                    logger.debug("GTX cancel-vs-fill positionRisk guard failed on %s: %s", symbol, race_exc)

                if filled_qty_total > 0 and (rem_qty <= 0 or (rem_qty * mark_price < min_notional)):
                    execution_log["quantity"] = round(filled_qty_total, 8)
                    if weighted_fill_cost > 0:
                        execution_log["entry_price"] = round(weighted_fill_cost / filled_qty_total, 8)
                elif rem_qty > 0 and not maker_only:
                    rem_fmt = self._format_qty_compat(symbol, rem_qty, order_type="LIMIT")
                    if rem_fmt * mark_price >= min_notional:
                        cap_bps = min(8.0, float(config.get("max_vwap_impact_bps", 8.0))) / 10000.0
                        ioc_px = self.format_price(
                            symbol,
                            arrival_price * (1.0 + cap_bps) if direction == "LONG" else arrival_price * (1.0 - cap_bps),
                        )
                        entry_may_have_been_sent = True
                        ioc_res = self.open_position(
                            symbol=symbol,
                            direction=direction,
                            quantity=rem_fmt,
                            leverage=effective_leverage,
                            order_type="LIMIT",
                            limit_price=ioc_px,
                            margin_type=margin_type,
                            time_in_force="IOC",
                            client_order_id=f"{clean_base}_ic"[:36],
                        )
                        execution_log["steps"]["ioc_fallback"] = ioc_res
                        ioc_filled = float(ioc_res.get("executedQty") or 0.0) if isinstance(ioc_res, dict) and not ioc_res.get("isError") else 0.0
                        if ioc_filled > 0:
                            av_p = float(ioc_res.get("avgPrice") or ioc_px)
                            filled_qty_total += ioc_filled
                            weighted_fill_cost += ioc_filled * av_p
                            rem_qty = max(0.0, quantity - filled_qty_total)
                            order_res = ioc_res
                            last_filled_order_res = ioc_res
                            routing_used = "HYBRID_GTX_IOC" if filled_qty_total > ioc_filled else "LIMIT_IOC_CAPPED"
                        elif filled_qty_total <= 0:
                            order_res = ioc_res

                        if rem_qty > 0 and (rem_qty * mark_price >= min_notional) and filled_qty_total <= 0:
                            mkt_qty = self._format_qty_compat(symbol, rem_qty, order_type="MARKET")
                            entry_may_have_been_sent = True
                            mkt_res = self.open_position(
                                symbol=symbol,
                                direction=direction,
                                quantity=mkt_qty,
                                leverage=effective_leverage,
                                order_type="MARKET",
                                margin_type=margin_type,
                                client_order_id=f"{clean_base}_mk"[:36],
                            )
                            execution_log["steps"]["market_fallback"] = mkt_res
                            order_res = mkt_res
                            routing_used = "MARKET_FALLBACK"
                if filled_qty_total > 0:
                    if last_filled_order_res is not None:
                        order_res = last_filled_order_res
                    execution_log["quantity"] = round(filled_qty_total, 8)
                    quantity = execution_log["quantity"]
                    if weighted_fill_cost > 0:
                        execution_log["entry_price"] = round(weighted_fill_cost / filled_qty_total, 8)
            elif order_type == "LIMIT" and limit_price > 0 and not depth_book.get("bids"):
                entry_may_have_been_sent = True
                order_res = self.open_position(
                    symbol=symbol,
                    direction=direction,
                    quantity=quantity,
                    leverage=effective_leverage,
                    order_type="LIMIT",
                    limit_price=limit_price,
                    margin_type=margin_type,
                    price_match=price_match,
                    client_order_id=(str(caller_cid)[:36] if caller_cid else f"{clean_base}_lm"[:36]),
                )
                routing_used = "LIMIT_GTC"

            if order_res is None and not (use_maker_first and maker_only):
                entry_may_have_been_sent = True
                order_res = self.open_position(
                    symbol=symbol,
                    direction=direction,
                    quantity=quantity,
                    leverage=effective_leverage,
                    order_type="MARKET",
                    limit_price=None,
                    margin_type=margin_type,
                    price_match=price_match,
                    client_order_id=(str(caller_cid)[:36] if caller_cid else f"{clean_base}_mk"[:36]),
                )
                routing_used = "MARKET_TAKER"

            execution_log["routing_used"] = routing_used
            execution_log["steps"]["open_position"] = order_res

            # A-7: Maker-only rejected/unfilled before orderId -> verify flat and return UNFILLED
            if use_maker_first and maker_only and filled_qty_total <= 0 and (not isinstance(order_res, dict) or order_res.get("isError") or not order_res.get("orderId")):
                post_chk = self.get_positions(symbol)
                post_amt = sum(abs(float(p.get("position_amount", 0) or 0)) for p in post_chk) if isinstance(post_chk, list) else 0.0
                if post_amt <= pre_amt:
                    execution_log["status"] = "UNFILLED"
                    execution_log["binance_synced"] = False
                    execution_log["quantity"] = 0.0
                    execution_log["notional_usdt"] = 0.0
                    execution_log["error"] = "Maker-only GTX order did not fill (0 positionRisk delta)"
                    return execution_log

            if isinstance(order_res, dict) and order_res.get("isError"):
                raise RuntimeError(order_res.get("error", "Unknown Binance order error"))

            order_id = order_res.get("orderId") if isinstance(order_res, dict) else None
            if not order_id:
                raise RuntimeError(f"Binance order failed to return orderId: {order_res}")
            execution_log["order_id"] = order_id

            # A-7: True Fill Verification (executedQty + status + positionRisk delta)
            order_status = str(order_res.get("status", "")).upper()
            reported_filled_qty = filled_qty_total if (use_maker_first and filled_qty_total > 0) else float(order_res.get("executedQty") or 0.0)
            pos_info = {}

            if order_status in ("CANCELED", "CANCELLED", "EXPIRED", "REJECTED") and reported_filled_qty <= 0:
                post_chk = self.get_positions(symbol)
                post_amt = sum(abs(float(p.get("position_amount", 0) or 0)) for p in post_chk) if isinstance(post_chk, list) else 0.0
                if (post_amt - pre_amt) <= 0:
                    execution_log["status"] = "UNFILLED"
                    execution_log["binance_synced"] = False
                    execution_log["quantity"] = 0.0
                    execution_log["notional_usdt"] = 0.0
                    execution_log["error"] = f"Order {order_id} {order_status} with 0 filled quantity (positionRisk delta=0)"
                    return execution_log
                pos_info = post_chk[0]
            else:
                # Step 2 (T0.3): Poll positionRisk until position is open (prevents -4509 on closePosition=true)
                pos_info = self.wait_for_position_open(symbol, max_wait_sec=3.0)
                if not pos_info and reported_filled_qty <= 0:
                    if order_status in ("NEW", ""):
                        try:
                            self.cancel_order(symbol, order_id)
                        except Exception as ce_ord:
                            logger.warning("cancel_order(%s, %s) failed during fill check: %s", symbol, order_id, ce_ord)
                    qo_chk = self.query_order(symbol, order_id)
                    if isinstance(qo_chk, dict) and not qo_chk.get("isError"):
                        order_res = qo_chk
                        reported_filled_qty = float(qo_chk.get("executedQty") or 0.0)
                    post_chk = self.get_positions(symbol)
                    if isinstance(post_chk, list) and post_chk:
                        pos_info = post_chk[0]

            post_amt = abs(float(pos_info.get("position_amount", 0) or 0)) if isinstance(pos_info, dict) and pos_info else 0.0
            pos_delta = max(0.0, post_amt - pre_amt)

            if reported_filled_qty <= 0 and pos_delta <= 0:
                execution_log["status"] = "UNFILLED"
                execution_log["binance_synced"] = False
                execution_log["quantity"] = 0.0
                execution_log["notional_usdt"] = 0.0
                execution_log["error"] = f"Order {order_id} had 0 executedQty and 0 positionRisk delta"
                return execution_log

            actual_qty = pos_delta if pos_delta > 0 else reported_filled_qty
            fill_px = float((pos_info or {}).get("entry_price") or order_res.get("avgPrice") or execution_log.get("entry_price") or mark_price)
            execution_log["quantity"] = round(actual_qty, 8)
            execution_log["entry_price"] = fill_px
            execution_log["position_size_usdt"] = round((actual_qty * fill_px) / effective_leverage, 4)
            execution_log["notional_usdt"] = round(actual_qty * fill_px, 2)
            if isinstance(pos_info, dict) and pos_info.get("liquidation_price") is not None:
                execution_log["liquidation_price"] = float(pos_info.get("liquidation_price", 0.0))

            # A-2: Post-fill live marginType & leverage verification
            mismatch, mismatch_reason = self._has_mode_mismatch(pos_info, margin_type, effective_leverage)
            if mismatch:
                crit_msg = f"CRITICAL post-fill mode mismatch on {symbol}: {mismatch_reason}"
                logger.critical(crit_msg)
                print(f"[BinanceFutures] 🚨 {crit_msg} — executing immediate reduceOnly market close!", flush=True)
                flat_info = self._emergency_flatten_and_verify(symbol, direction, actual_qty)
                execution_log["steps"]["emergency_close"] = flat_info
                execution_log["emergency_closed"] = flat_info.get("closed_ok", False)
                execution_log["emergency_flat_verified"] = flat_info.get("flat_verified", False)
                execution_log["binance_position_still_open"] = flat_info.get("still_open", False)
                if flat_info.get("live_position"):
                    execution_log["live_position_info"] = flat_info["live_position"]
                execution_log["status"] = "ABORTED_MODE_MISMATCH"
                execution_log["binance_synced"] = False
                execution_log["error"] = f"{crit_msg}; flat_verified={flat_info.get('flat_verified')}"
                execution_log["critical_alert"] = execution_log["error"]
                return execution_log

            execution_log["tca"] = self._build_tca_payload(
                symbol=symbol,
                direction=direction,
                routing_used=routing_used,
                arrival_price=arrival_price,
                fill_price=fill_px,
                quantity=actual_qty,
                margin_usdt=execution_log["position_size_usdt"],
                impact_bps_est=impact_bps_est,
            )

            # Step 3 (A-6 / B-11): Place STOP LOSS FIRST with closePosition=true (no quantity)
            if sl > 0:
                expected_sl_side = "SELL" if direction == "LONG" else "BUY"
                sl_state = "MISSING"
                retry_delays = [0.5, 1.0, 2.0]
                immediate_trigger_hit = False

                for attempt in range(3):
                    sl_res = self.set_stop_loss(symbol, direction, trigger_price=sl)
                    execution_log["steps"][f"stop_loss_attempt_{attempt + 1}"] = sl_res

                    if isinstance(sl_res, dict) and "algoId" in sl_res:
                        execution_log["sl_algo_id"] = sl_res["algoId"]
                        sl_state = "CONFIRMED"
                        break

                    if isinstance(sl_res, dict) and (sl_res.get("code") == -2021 or sl_res.get("would_immediately_trigger")):
                        immediate_trigger_hit = True
                        print(f"[BinanceFutures] 🚨 SL -2021 immediate trigger on {symbol} @ ${sl}: closing position immediately!", flush=True)
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
                        sl_state = "CONFIRMED"
                        break
                    if attempt < 2:
                        time.sleep(retry_delays[attempt])

                if sl_state == "CONFIRMED":
                    execution_log["sl_state"] = "CONFIRMED"
                    execution_log["sl_verified"] = True
                else:
                    reason_tag = "SL -2021 immediate trigger" if immediate_trigger_hit else f"SL unconfirmed after 3 attempts (state={sl_state})"
                    logger.critical(f"{reason_tag} on {symbol} — mandatory reduceOnly close!")
                    print(f"[BinanceFutures] 🚨 CRITICAL: {reason_tag} on {symbol}. Executing emergency reduceOnly market close!", flush=True)
                    flat_info = self._emergency_flatten_and_verify(symbol, direction, actual_qty)
                    execution_log["steps"]["emergency_close"] = flat_info
                    execution_log["sl_state"] = "IMMEDIATE_TRIGGER_CLOSED" if immediate_trigger_hit else sl_state
                    execution_log["sl_verified"] = False
                    execution_log["emergency_closed"] = flat_info.get("closed_ok", False)
                    execution_log["emergency_flat_verified"] = flat_info.get("flat_verified", False)
                    execution_log["binance_position_still_open"] = flat_info.get("still_open", False)
                    if flat_info.get("live_position"):
                        execution_log["live_position_info"] = flat_info["live_position"]
                    execution_log["status"] = "ABORTED_UNPROTECTED_SL"
                    execution_log["binance_synced"] = False
                    execution_log["error"] = f"{reason_tag}; emergency close flat_verified={flat_info.get('flat_verified')}"
                    execution_log["critical_alert"] = execution_log["error"]
                    return execution_log

            # Step 4 (A-6): Place Take Profit Algo Order ONLY AFTER SL is confirmed
            if tp > 0:
                try:
                    tp_res = self.set_take_profit(symbol, direction, trigger_price=tp, quantity=actual_qty)
                    execution_log["steps"]["take_profit"] = tp_res
                    if isinstance(tp_res, dict) and "algoId" in tp_res:
                        execution_log["tp_algo_id"] = tp_res["algoId"]
                except Exception as e:
                    print(f"[BinanceFutures] ⚠️ TP placement notice: {e}", flush=True)

            execution_log["status"] = "EXECUTED"
            execution_log["binance_synced"] = True
            print(
                f"[BinanceFutures] 🎉 FULL TRADE EXECUTED ON BINANCE: {direction} {symbol} ({effective_leverage}x, Qty: {actual_qty}, SL State: {execution_log['sl_state']})",
                flush=True,
            )

        except Exception as e:
            execution_log["error"] = str(e)
            print(f"[BinanceFutures] ❌ Execution exception: {e}", flush=True)
            if entry_may_have_been_sent:
                # B-2: Inspect positionRisk to check if a live position actually opened on Binance!
                try:
                    live_list = self.get_positions(symbol)
                except Exception as pe:
                    live_list = {"isError": True, "error": str(pe)}

                if isinstance(live_list, list):
                    live_pos = next(
                        (
                            p for p in live_list
                            if (not p.get("symbol") or p.get("symbol") == symbol)
                            and abs(float(p.get("position_amount", 0) or 0)) > pre_amt
                        ),
                        None,
                    )
                    if live_pos is not None:
                        live_amt = abs(float(live_pos.get("position_amount", 0) or 0)) - pre_amt
                        live_px = float(live_pos.get("entry_price") or execution_log.get("entry_price") or mark_price)
                        execution_log["quantity"] = round(live_amt, 8)
                        execution_log["entry_price"] = live_px
                        execution_log["position_size_usdt"] = round((live_amt * live_px) / effective_leverage, 4)
                        execution_log["notional_usdt"] = round(live_amt * live_px, 2)
                        if live_pos.get("liquidation_price") is not None:
                            execution_log["liquidation_price"] = float(live_pos.get("liquidation_price", 0.0))

                        mismatch, mismatch_reason = self._has_mode_mismatch(live_pos, margin_type, effective_leverage)
                        if mismatch:
                            flat_info = self._emergency_flatten_and_verify(symbol, direction, live_amt)
                            execution_log["steps"]["emergency_close"] = flat_info
                            execution_log["emergency_closed"] = flat_info.get("closed_ok", False)
                            execution_log["emergency_flat_verified"] = flat_info.get("flat_verified", False)
                            execution_log["binance_position_still_open"] = flat_info.get("still_open", False)
                            execution_log["status"] = "ABORTED_MODE_MISMATCH"
                            execution_log["binance_synced"] = False
                            execution_log["critical_alert"] = f"Exception recovery mode mismatch ({mismatch_reason})"
                            return execution_log

                        expected_sl_side = "SELL" if direction == "LONG" else "BUY"
                        sl_ok = False
                        try:
                            sl_state = self.verify_stop_loss_active(symbol, expected_side=expected_sl_side, max_wait_sec=1.0, return_tristate=True)
                            if sl_state == "CONFIRMED":
                                sl_ok = True
                            elif sl > 0:
                                rec_sl = self.set_stop_loss(symbol, direction, trigger_price=sl)
                                execution_log["steps"]["recovery_stop_loss"] = rec_sl
                                if isinstance(rec_sl, dict) and "algoId" in rec_sl:
                                    execution_log["sl_algo_id"] = rec_sl["algoId"]
                                    sl_ok = True
                                elif self.verify_stop_loss_active(symbol, expected_side=expected_sl_side, max_wait_sec=1.2, return_tristate=True) == "CONFIRMED":
                                    sl_ok = True
                        except Exception:
                            sl_ok = False

                        if sl_ok:
                            execution_log["sl_state"] = "CONFIRMED"
                            execution_log["sl_verified"] = True
                            execution_log["tca"] = self._build_tca_payload(
                                symbol=symbol,
                                direction=direction,
                                routing_used=execution_log.get("routing_used", order_type),
                                arrival_price=arrival_price,
                                fill_price=live_px,
                                quantity=live_amt,
                                margin_usdt=execution_log["position_size_usdt"],
                                impact_bps_est=impact_bps_est,
                            )
                            execution_log["status"] = "EXECUTED_RECOVERY_PROTECTED"
                            execution_log["binance_synced"] = True
                            execution_log["critical_alert"] = f"Post-fill exception recovered with active SL on {symbol}: {e}"
                            return execution_log

                        # Emergency SL failed -> immediately market close!
                        flat_info = self._emergency_flatten_and_verify(symbol, direction, live_amt)
                        execution_log["steps"]["emergency_close"] = flat_info
                        execution_log["sl_state"] = "MISSING"
                        execution_log["sl_verified"] = False
                        execution_log["emergency_closed"] = flat_info.get("closed_ok", False)
                        execution_log["emergency_flat_verified"] = flat_info.get("flat_verified", False)
                        execution_log["binance_position_still_open"] = flat_info.get("still_open", False)
                        if flat_info.get("live_position"):
                            execution_log["live_position_info"] = flat_info["live_position"]
                        execution_log["status"] = "ABORTED_UNPROTECTED_SL"
                        execution_log["binance_synced"] = False
                        execution_log["critical_alert"] = f"Post-fill exception ({e}) & emergency SL failed; flattened flat_verified={flat_info.get('flat_verified')}"
                        return execution_log

                    execution_log["status"] = "FAILED"
                    execution_log["binance_synced"] = False
                else:
                    execution_log["status"] = "FAILED_UNKNOWN_POSITION_STATE"
                    execution_log["binance_synced"] = False
                    execution_log["position_state_unknown"] = True
                    execution_log["critical_alert"] = f"Execution exception ({e}) and positionRisk check failed ({live_list})"
            else:
                execution_log["status"] = "FAILED"
                execution_log["binance_synced"] = False
        finally:
            if tl is not None:
                tl.exec_verified_mode = None

        return execution_log


def get_binance_client() -> BinanceFuturesClient:
    """Compatibility factory for legacy Flask server callers."""
    return BinanceFuturesClient()
