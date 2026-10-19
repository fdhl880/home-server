"""
=============================================================
CRYPTO FUTURES MARKET DATA ENGINE v2.0 - FULL UNIVERSE SCANNER
=============================================================
Advanced Technical Analysis: RSI, EMA, MACD, Bollinger Bands,
ATR, Volume Profile, Support/Resistance, Funding Rate

UPGRADE v2.0:
- Dynamically fetches ALL Binance USDT Perpetual Futures (~200+ pairs)
- Smart Prioritization: ranks by volume, volatility, and momentum
- Currency Conversion: USD <-> IDR real-time
- Faster parallel-ready data fetching
=============================================================
"""
import requests
import math
import json
import os
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    from quant_factors import evaluate_all_quant_factors
except ImportError:
    evaluate_all_quant_factors = None

# ===================================================================
# PLUANG-RESTRICTED CRYPTO FUTURES UNIVERSE (43 COINS)
# ===================================================================
# ONLY coins that exist on BOTH Pluang Spot AND Binance USDT Perpetuals
# This is the HARD GATE — no coin outside this list will ever be scanned.
# Last verified: 2026-10-19 from Pluang MCP search_assets + Binance fapi
# ===================================================================
PLUANG_FUTURES_UNIVERSE = [
    # --- TIER 1: MEGA CAPS (BTC, ETH) ---
    {"symbol": "BTC-USD", "name": "Bitcoin",    "pair": "BTCUSDT",   "pluang_symbol": "BTC",    "leverage_max": 20, "tier": "T1_MEGA"},
    {"symbol": "ETH-USD", "name": "Ethereum",   "pair": "ETHUSDT",   "pluang_symbol": "ETH",    "leverage_max": 20, "tier": "T1_MEGA"},
    # --- TIER 2: LARGE CAPS ---
    {"symbol": "SOL-USD",  "name": "Solana",     "pair": "SOLUSDT",   "pluang_symbol": "SOL",    "leverage_max": 15, "tier": "T2_LARGE"},
    {"symbol": "BNB-USD",  "name": "BNB",        "pair": "BNBUSDT",   "pluang_symbol": "BNB",    "leverage_max": 15, "tier": "T2_LARGE"},
    {"symbol": "XRP-USD",  "name": "Ripple",     "pair": "XRPUSDT",   "pluang_symbol": "XRP",    "leverage_max": 15, "tier": "T2_LARGE"},
    {"symbol": "ADA-USD",  "name": "Cardano",    "pair": "ADAUSDT",   "pluang_symbol": "ADA",    "leverage_max": 10, "tier": "T2_LARGE"},
    {"symbol": "DOGE-USD", "name": "Dogecoin",   "pair": "DOGEUSDT",  "pluang_symbol": "DOGE",   "leverage_max": 10, "tier": "T2_LARGE"},
    {"symbol": "TRX-USD",  "name": "TRON",       "pair": "TRXUSDT",   "pluang_symbol": "TRX",    "leverage_max": 10, "tier": "T2_LARGE"},
    {"symbol": "AVAX-USD", "name": "Avalanche",  "pair": "AVAXUSDT",  "pluang_symbol": "AVAX",   "leverage_max": 10, "tier": "T2_LARGE"},
    {"symbol": "LINK-USD", "name": "Chainlink",  "pair": "LINKUSDT",  "pluang_symbol": "LINK",   "leverage_max": 10, "tier": "T2_LARGE"},
    {"symbol": "DOT-USD",  "name": "Polkadot",   "pair": "DOTUSDT",   "pluang_symbol": "DOT",    "leverage_max": 10, "tier": "T2_LARGE"},
    {"symbol": "LTC-USD",  "name": "Litecoin",   "pair": "LTCUSDT",   "pluang_symbol": "LTC",    "leverage_max": 10, "tier": "T2_LARGE"},
    {"symbol": "BCH-USD",  "name": "Bitcoin Cash","pair": "BCHUSDT",   "pluang_symbol": "BCH",    "leverage_max": 10, "tier": "T2_LARGE"},
    {"symbol": "XLM-USD",  "name": "Stellar",    "pair": "XLMUSDT",   "pluang_symbol": "XLM",    "leverage_max": 10, "tier": "T2_LARGE"},
    {"symbol": "ICP-USD",  "name": "ICP",        "pair": "ICPUSDT",   "pluang_symbol": "ICP",    "leverage_max": 10, "tier": "T2_LARGE"},
    {"symbol": "UNI-USD",  "name": "Uniswap",    "pair": "UNIUSDT",   "pluang_symbol": "UNI",    "leverage_max": 10, "tier": "T2_LARGE"},
    {"symbol": "ATOM-USD", "name": "Cosmos",     "pair": "ATOMUSDT",  "pluang_symbol": "ATOM",   "leverage_max": 10, "tier": "T2_LARGE"},
    # --- TIER 3: MID CAPS (Pluang-listed, Binance Futures available) ---
    {"symbol": "SUI-USD",  "name": "Sui",        "pair": "SUIUSDT",   "pluang_symbol": "SUI",    "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "NEAR-USD", "name": "NEAR",       "pair": "NEARUSDT",  "pluang_symbol": "NEAR",   "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "APT-USD",  "name": "Aptos",      "pair": "APTUSDT",   "pluang_symbol": "APT",    "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "FIL-USD",  "name": "Filecoin",   "pair": "FILUSDT",   "pluang_symbol": "FIL",    "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "ARB-USD",  "name": "Arbitrum",   "pair": "ARBUSDT",   "pluang_symbol": "ARB",    "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "OP-USD",   "name": "Optimism",   "pair": "OPUSDT",    "pluang_symbol": "OP",     "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "IMX-USD",  "name": "Immutable",  "pair": "IMXUSDT",   "pluang_symbol": "IMX",    "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "INJ-USD",  "name": "Injective",  "pair": "INJUSDT",   "pluang_symbol": "INJ",    "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "AAVE-USD", "name": "Aave",       "pair": "AAVEUSDT",  "pluang_symbol": "AAVE",   "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "ALGO-USD", "name": "Algorand",   "pair": "ALGOUSDT",  "pluang_symbol": "ALGO",   "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "RENDER-USD","name": "Render",     "pair": "RENDERUSDT","pluang_symbol": "RENDER",  "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "FET-USD",  "name": "Fetch.ai",   "pair": "FETUSDT",   "pluang_symbol": "FET",    "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "STX-USD",  "name": "Stacks",     "pair": "STXUSDT",   "pluang_symbol": "STX",    "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "TIA-USD",  "name": "Celestia",   "pair": "TIAUSDT",   "pluang_symbol": "TIA",    "leverage_max": 10, "tier": "T3_MID"},
    {"symbol": "POL-USD",  "name": "Polygon",    "pair": "POLUSDT",   "pluang_symbol": "POL",    "leverage_max": 10, "tier": "T3_MID"},
    # --- TIER 4: SMALL/MEME CAPS (High vol, Pluang available) ---
    {"symbol": "PEPE-USD", "name": "Pepe",       "pair": "PEPEUSDT",  "pluang_symbol": "PEPE",   "leverage_max": 5,  "tier": "T4_MEME"},
    {"symbol": "SHIB-USD", "name": "Shiba Inu",  "pair": "SHIBUSDT",  "pluang_symbol": "SHIB",   "leverage_max": 5,  "tier": "T4_MEME"},
    {"symbol": "BONK-USD", "name": "Bonk",       "pair": "BONKUSDT",  "pluang_symbol": "BONK",   "leverage_max": 5,  "tier": "T4_MEME"},
    {"symbol": "FLOKI-USD","name": "Floki",      "pair": "FLOKIUSDT", "pluang_symbol": "FLOKI",  "leverage_max": 5,  "tier": "T4_MEME"},
    {"symbol": "WIF-USD",  "name": "dogwifhat",  "pair": "WIFUSDT",   "pluang_symbol": "WIF",    "leverage_max": 5,  "tier": "T4_MEME"},
    # --- TIER 5: AI & DEFI NARRATIVES ---
    {"symbol": "TAO-USD",  "name": "Bittensor",  "pair": "TAOUSDT",   "pluang_symbol": "TAO",    "leverage_max": 10, "tier": "T5_NARRATIVE"},
    {"symbol": "KAS-USD",  "name": "Kaspa",      "pair": "KASUSDT",   "pluang_symbol": "KAS",    "leverage_max": 10, "tier": "T5_NARRATIVE"},
]

# The locked universe set - for fast lookup
PLUANG_BINANCE_PAIRS = {c["pair"] for c in PLUANG_FUTURES_UNIVERSE}
PLUANG_PAIR_MAP = {c["symbol"]: c["pair"] for c in PLUANG_FUTURES_UNIVERSE}
PLUANG_SYMBOL_MAP = {c["pair"]: c["pluang_symbol"] for c in PLUANG_FUTURES_UNIVERSE}

# Backward-compatible alias
CRYPTO_FUTURES_WATCHLIST = PLUANG_FUTURES_UNIVERSE

# Cache for dynamic universe
_DYNAMIC_UNIVERSE_CACHE = {"data": [], "last_fetch": 0, "ttl": 300}  # 5 min cache
_FX_RATE_CACHE = {"usd_idr": 16000, "last_fetch": 0, "ttl": 600}   # 10 min cache

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ===================================================================
# CURRENCY CONVERSION ENGINE
# ===================================================================
def get_usd_idr_rate():
    """Get real-time USD/IDR exchange rate"""
    now = time.time()
    if now - _FX_RATE_CACHE["last_fetch"] < _FX_RATE_CACHE["ttl"]:
        return _FX_RATE_CACHE["usd_idr"]

    # Try multiple sources
    sources = [
        ("https://api.exchangerate-api.com/v4/latest/USD", lambda d: d["rates"]["IDR"]),
        ("https://open.er-api.com/v6/latest/USD", lambda d: d["rates"]["IDR"]),
    ]

    for url, extractor in sources:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                rate = extractor(r.json())
                _FX_RATE_CACHE["usd_idr"] = rate
                _FX_RATE_CACHE["last_fetch"] = now
                return rate
        except Exception:
            continue

    return _FX_RATE_CACHE["usd_idr"]  # Return cached/default


def convert_usd_to_idr(usd_amount):
    """Convert USD to IDR"""
    rate = get_usd_idr_rate()
    return round(usd_amount * rate, 2)


def convert_idr_to_usd(idr_amount):
    """Convert IDR to USD"""
    rate = get_usd_idr_rate()
    return round(idr_amount / rate, 6) if rate else 0


def get_fx_info():
    """Get full FX info"""
    rate = get_usd_idr_rate()
    return {
        "usd_idr": rate,
        "idr_usd": round(1 / rate, 8) if rate else 0,
        "example_50k_idr_in_usd": convert_idr_to_usd(50000),
        "example_1_usd_in_idr": rate,
        "source": "exchangerate-api",
        "cached": time.time() - _FX_RATE_CACHE["last_fetch"] < _FX_RATE_CACHE["ttl"]
    }


# ===================================================================
# DYNAMIC UNIVERSE: FETCH ALL BINANCE USDT PERPETUAL FUTURES
# ===================================================================
def fetch_all_binance_futures_pairs():
    """
    Fetch ONLY Pluang-listed coins from Binance USDT tickers.
    HARD GATE: Any pair NOT in PLUANG_BINANCE_PAIRS is rejected.
    """
    now = time.time()
    if now - _DYNAMIC_UNIVERSE_CACHE["last_fetch"] < _DYNAMIC_UNIVERSE_CACHE["ttl"] and _DYNAMIC_UNIVERSE_CACHE["data"]:
        return _DYNAMIC_UNIVERSE_CACHE["data"]

    endpoints = [
        "https://data-api.binance.vision/api/v3/ticker/24hr",
        "https://fapi.binance.com/fapi/v1/ticker/24hr",
    ]

    # Build lookup from our fixed Pluang universe
    pluang_lookup = {c["pair"]: c for c in PLUANG_FUTURES_UNIVERSE}

    for url in endpoints:
        try:
            resp = requests.get(url, timeout=8, verify=False)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if not isinstance(data, list):
                continue

            pairs = []
            for item in data:
                sym = item.get("symbol", "")
                # HARD GATE: must be in Pluang universe
                if sym not in PLUANG_BINANCE_PAIRS:
                    continue

                template = pluang_lookup[sym]
                quote_vol = float(item.get("quoteVolume", 0) or 0)

                pairs.append({
                    **template,
                    "quote_asset": "USDT",
                    "base_asset": sym[:-4],
                    "last_price": float(item.get("lastPrice", 0) or 0),
                    "price_change_24h_pct": float(item.get("priceChangePercent", 0) or 0),
                    "volume_24h_usd": quote_vol,
                    "high_24h": float(item.get("highPrice", 0) or 0),
                    "low_24h": float(item.get("lowPrice", 0) or 0),
                })

            if len(pairs) > 10:
                _DYNAMIC_UNIVERSE_CACHE["data"] = pairs
                _DYNAMIC_UNIVERSE_CACHE["last_fetch"] = now
                return pairs

        except Exception:
            continue

    return _DYNAMIC_UNIVERSE_CACHE["data"] or list(PLUANG_FUTURES_UNIVERSE)


def get_full_universe():
    """Get the PLUANG-RESTRICTED universe of tradeable crypto futures (43 coins max)"""
    return fetch_all_binance_futures_pairs()


# ===================================================================
# SMART PRIORITIZATION: RANK BY MOVERS
# ===================================================================
def get_binance_24h_tickers():
    """Get 24h ticker data for ALL Binance pairs at once (1 API call)"""
    endpoints = [
        "https://data-api.binance.vision/api/v3/ticker/24hr",
        "https://fapi.binance.com/fapi/v1/ticker/24hr",
    ]
    for url in endpoints:
        try:
            resp = requests.get(url, timeout=8, verify=False)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            continue
    return []


def rank_universe_by_opportunity():
    """
    Rank ALL crypto futures by trading opportunity score.
    Factors: volume spike, price change %, volatility.
    Returns sorted list with top movers first.
    """
    universe = get_full_universe()
    tickers = get_binance_24h_tickers()
    
    if not tickers:
        return universe  # Return unsorted if API fails

    # Build ticker lookup
    ticker_map = {}
    for t in tickers:
        if t.get("symbol", "").endswith("USDT"):
            ticker_map[t["symbol"]] = t

    ranked = []
    for coin in universe:
        t = ticker_map.get(coin["pair"], {})
        if not t:
            continue

        try:
            volume_usd = float(t.get("quoteVolume", 0))
            price_change_pct = abs(float(t.get("priceChangePercent", 0)))
            high_low_range = 0
            high = float(t.get("highPrice", 0))
            low = float(t.get("lowPrice", 0))
            last_price = float(t.get("lastPrice", 0))
            
            if low > 0:
                high_low_range = ((high - low) / low) * 100
            
            # Skip dust pairs with very low volume
            if volume_usd < 1_000_000:  # < $1M daily volume = skip
                continue

            # Opportunity score (higher = more interesting to scan first)
            # Weights: volume (40%), price change (35%), range (25%)
            vol_score = min(volume_usd / 1_000_000_000, 10)  # Cap at 10
            change_score = min(price_change_pct / 2, 10)  # 20% change = max
            range_score = min(high_low_range / 3, 10)  # 30% range = max
            
            opportunity_score = (vol_score * 0.4) + (change_score * 0.35) + (range_score * 0.25)
            
            # Core coins get a boost
            if coin["tier"] == "CORE":
                opportunity_score += 3.0

            coin_ranked = dict(coin)
            coin_ranked.update({
                "volume_24h_usd": volume_usd,
                "price_change_24h_pct": float(t.get("priceChangePercent", 0)),
                "last_price": last_price,
                "high_24h": high,
                "low_24h": low,
                "high_low_range_pct": round(high_low_range, 2),
                "opportunity_score": round(opportunity_score, 3),
                "volume_rank": "HIGH" if volume_usd > 100_000_000 else ("MEDIUM" if volume_usd > 10_000_000 else "LOW")
            })
            ranked.append(coin_ranked)
        except (ValueError, TypeError):
            continue

    # Sort by opportunity score descending
    ranked.sort(key=lambda x: x.get("opportunity_score", 0), reverse=True)
    return ranked


def get_top_movers(limit=50):
    """Get top N coins ranked by trading opportunity"""
    all_ranked = rank_universe_by_opportunity()
    return all_ranked[:limit]


def get_universe_summary():
    """Get a quick summary of the entire crypto futures universe"""
    all_ranked = rank_universe_by_opportunity()
    
    gainers = sorted([c for c in all_ranked if c.get("price_change_24h_pct", 0) > 0],
                     key=lambda x: x["price_change_24h_pct"], reverse=True)[:10]
    losers = sorted([c for c in all_ranked if c.get("price_change_24h_pct", 0) < 0],
                    key=lambda x: x["price_change_24h_pct"])[:10]
    
    total_vol = sum(c.get("volume_24h_usd", 0) for c in all_ranked)
    
    return {
        "total_pairs": len(all_ranked),
        "total_volume_24h_usd": total_vol,
        "total_volume_24h_idr": convert_usd_to_idr(total_vol),
        "top_10_gainers": [{"symbol": c["pair"], "change": c["price_change_24h_pct"]} for c in gainers],
        "top_10_losers": [{"symbol": c["pair"], "change": c["price_change_24h_pct"]} for c in losers],
        "top_by_volume": [{"symbol": c["pair"], "vol": c["volume_24h_usd"]} for c in all_ranked[:10]],
        "usd_idr_rate": get_usd_idr_rate(),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    }


# ===================================================================
# TECHNICAL ANALYSIS FUNCTIONS
# ===================================================================
def calculate_rsi(prices, period=14):
    """Wilder's Smoothed RSI"""
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def calculate_ema(prices, period):
    """Exponential Moving Average"""
    if len(prices) < period:
        return prices[-1] if prices else 0
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p - ema) * multiplier + ema
    return round(ema, 6)


def calculate_sma(prices, period):
    """Simple Moving Average"""
    if len(prices) < period:
        return sum(prices) / len(prices) if prices else 0
    return sum(prices[-period:]) / period


def calculate_macd(prices, fast=12, slow=26, signal=9):
    """MACD Line, Signal Line, Histogram"""
    if len(prices) < slow + signal:
        return {"macd_line": 0, "signal_line": 0, "histogram": 0, "trend": "NEUTRAL"}

    ema_fast_val = calculate_ema(prices, fast)
    ema_slow_val = calculate_ema(prices, slow)
    macd_line = ema_fast_val - ema_slow_val

    # Calculate MACD values for signal line
    macd_values = []
    for i in range(slow, len(prices)):
        subset = prices[:i + 1]
        ef = calculate_ema(subset, fast)
        es = calculate_ema(subset, slow)
        macd_values.append(ef - es)

    signal_line = calculate_ema(macd_values, signal) if len(macd_values) >= signal else macd_line
    histogram = macd_line - signal_line

    trend = "BULLISH" if histogram > 0 else "BEARISH"
    if abs(histogram) < abs(macd_line) * 0.1:
        trend = "CONVERGING"

    return {
        "macd_line": round(macd_line, 6),
        "signal_line": round(signal_line, 6),
        "histogram": round(histogram, 6),
        "trend": trend
    }


def calculate_bollinger_bands(prices, period=20, std_dev=2):
    """Bollinger Bands: Upper, Middle (SMA), Lower, Width, %B"""
    if len(prices) < period:
        p = prices[-1] if prices else 0
        return {"upper": p, "middle": p, "lower": p, "width": 0, "percent_b": 50, "squeeze": False}

    sma = calculate_sma(prices, period)
    recent = prices[-period:]
    variance = sum((x - sma) ** 2 for x in recent) / period
    std = math.sqrt(variance)

    upper = sma + std_dev * std
    lower = sma - std_dev * std
    width = ((upper - lower) / sma) * 100 if sma else 0
    current = prices[-1]
    percent_b = ((current - lower) / (upper - lower)) * 100 if (upper - lower) != 0 else 50

    # Bollinger Squeeze detection (low volatility = upcoming breakout)
    squeeze = width < 4.0  # Tight bands indicate compression

    return {
        "upper": round(upper, 2),
        "middle": round(sma, 2),
        "lower": round(lower, 2),
        "width_pct": round(width, 2),
        "percent_b": round(percent_b, 2),
        "squeeze": squeeze
    }


def calculate_atr(highs, lows, closes, period=14):
    """Average True Range (volatility measure)"""
    if len(closes) < 2 or len(highs) < 2 or len(lows) < 2:
        return 0

    tr_values = []
    for i in range(1, min(len(highs), len(lows), len(closes))):
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_values.append(tr)

    if len(tr_values) < period:
        return round(sum(tr_values) / len(tr_values), 2) if tr_values else 0

    atr = sum(tr_values[:period]) / period
    for i in range(period, len(tr_values)):
        atr = (atr * (period - 1) + tr_values[i]) / period

    return round(atr, 2)


def calculate_support_resistance(highs, lows, closes, window=24):
    """Detect key support and resistance levels from recent price action"""
    if len(closes) < window:
        c = closes[-1] if closes else 0
        return {"resistance_1": c * 1.02, "support_1": c * 0.98, "resistance_2": c * 1.05, "support_2": c * 0.95}

    recent_highs = highs[-window:]
    recent_lows = lows[-window:]

    # Pivot Points calculation
    pivot = (max(recent_highs) + min(recent_lows) + closes[-1]) / 3
    r1 = 2 * pivot - min(recent_lows)
    s1 = 2 * pivot - max(recent_highs)
    r2 = pivot + (max(recent_highs) - min(recent_lows))
    s2 = pivot - (max(recent_highs) - min(recent_lows))

    return {
        "pivot": round(pivot, 2),
        "resistance_1": round(r1, 2),
        "resistance_2": round(r2, 2),
        "support_1": round(s1, 2),
        "support_2": round(s2, 2)
    }


def calculate_volume_profile(volumes, closes):
    """Analyze volume distribution to detect accumulation/distribution"""
    if len(volumes) < 10 or len(closes) < 10:
        return {"volume_trend": "N/A", "avg_volume": 0, "volume_ratio": 1.0}

    avg_vol_20 = sum(volumes[-20:]) / min(len(volumes), 20)
    avg_vol_5 = sum(volumes[-5:]) / min(len(volumes[-5:]), 5)
    vol_ratio = avg_vol_5 / avg_vol_20 if avg_vol_20 > 0 else 1.0

    # Price-Volume Divergence
    price_up = closes[-1] > closes[-5] if len(closes) >= 5 else False
    vol_up = vol_ratio > 1.2

    if price_up and vol_up:
        trend = "STRONG_ACCUMULATION"
    elif price_up and not vol_up:
        trend = "WEAK_RALLY_LOW_VOLUME"
    elif not price_up and vol_up:
        trend = "DISTRIBUTION_SELLING"
    else:
        trend = "LOW_INTEREST"

    return {
        "volume_trend": trend,
        "avg_volume_20": round(avg_vol_20),
        "avg_volume_5": round(avg_vol_5),
        "volume_ratio": round(vol_ratio, 2),
        "is_high_volume": vol_ratio > 1.5
    }


# ===================================================================
# BINANCE FUTURES SPECIFIC DATA
# ===================================================================
def get_binance_funding_rate(pair="BTCUSDT"):
    """Get real-time funding rate from Binance Futures"""
    try:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={pair}&limit=3"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                latest = data[-1]
                rate = float(latest.get("fundingRate", 0))
                return {
                    "funding_rate": round(rate * 100, 4),
                    "funding_rate_raw": rate,
                    "sentiment": "BEARISH_LONGS_PAY" if rate > 0.01 else ("BULLISH_SHORTS_PAY" if rate < -0.01 else "NEUTRAL"),
                    "timestamp": latest.get("fundingTime")
                }
    except Exception:
        pass
    return {"funding_rate": 0, "sentiment": "UNAVAILABLE"}


def get_binance_open_interest(pair="BTCUSDT"):
    """Get open interest from Binance Futures"""
    try:
        url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={pair}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "open_interest": float(data.get("openInterest", 0)),
                "symbol": data.get("symbol", pair)
            }
    except Exception:
        pass
    return {"open_interest": 0}


def get_binance_long_short_ratio(pair="BTCUSDT"):
    """Get Long/Short Account Ratio from Binance Futures"""
    try:
        url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={pair}&period=1h&limit=5"
        resp = requests.get(url, timeout=5, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                latest = data[-1]
                ratio = float(latest.get("longShortRatio", 1.0))
                long_pct = float(latest.get("longAccount", 0.5)) * 100
                short_pct = float(latest.get("shortAccount", 0.5)) * 100
                return {
                    "long_short_ratio": round(ratio, 3),
                    "long_pct": round(long_pct, 1),
                    "short_pct": round(short_pct, 1),
                    "crowd_sentiment": "CROWD_LONG" if ratio > 1.5 else ("CROWD_SHORT" if ratio < 0.67 else "BALANCED")
                }
    except Exception:
        pass
    return {"long_short_ratio": 1.0, "crowd_sentiment": "UNAVAILABLE"}


# ===================================================================
# INSTITUTIONAL SMART MONEY CONCEPTS (SMC) & DERIVATIVES MATRIX
# ===================================================================
def detect_smc_features(highs, lows, closes, lookback=15):
    """
    Institutional Smart Money Concepts (SMC) Engine:
    1. Fair Value Gap (FVG) detection (3-candle price imbalance)
    2. Liquidity Sweep (External stop hunt / swing high/low grab)
    3. Market Structure Shift (MSS)
    """
    if len(closes) < 5:
        return {"fvg": "NONE", "liquidity_sweep": "NONE", "market_structure": "NEUTRAL"}
    
    # 1. Fair Value Gap (FVG) 3-candle imbalance
    fvg = "NONE"
    fvg_zone = None
    for i in range(len(closes) - 1, max(len(closes) - 8, 2), -1):
        if lows[i] > highs[i - 2]:
            fvg = "BULLISH_FVG"
            fvg_zone = {"bottom": round(highs[i - 2], 4), "top": round(lows[i], 4), "candle": i}
            break
        elif highs[i] < lows[i - 2]:
            fvg = "BEARISH_FVG"
            fvg_zone = {"bottom": round(highs[i], 4), "top": round(lows[i - 2], 4), "candle": i}
            break

    # 2. Liquidity Sweep
    recent_highs = highs[-lookback:-1]
    recent_lows = lows[-lookback:-1]
    swing_high = max(recent_highs) if recent_highs else highs[-1]
    swing_low = min(recent_lows) if recent_lows else lows[-1]

    last_high = highs[-1]
    last_low = lows[-1]
    last_close = closes[-1]

    liquidity_sweep = "NONE"
    if last_high > swing_high and last_close < swing_high:
        liquidity_sweep = "BEARISH_BUY_SIDE_LIQUIDITY_GRAB"
    elif last_low < swing_low and last_close > swing_low:
        liquidity_sweep = "BULLISH_SELL_SIDE_LIQUIDITY_SWEEP"

    # 3. Market Structure
    ema_20 = calculate_ema(closes, 20)
    mss = "BULLISH" if last_close > ema_20 and closes[-1] >= closes[-2] else "BEARISH"

    return {
        "fvg": fvg,
        "fvg_zone": fvg_zone,
        "liquidity_sweep": liquidity_sweep,
        "swing_high": round(swing_high, 4),
        "swing_low": round(swing_low, 4),
        "market_structure": mss
    }


def analyze_derivatives_confluence(price_change, funding_rate, open_interest=None):
    """
    Four-Quadrant Confluence Matrix:
    Maps Price Action + Funding Rate + Open Interest into Institutional Regimes:
    - Overleveraged Long Trap: Rising Price + Extreme Positive Funding (Long Squeeze Risk)
    - Short Squeeze Setup: Extreme Negative Funding (Pump Reversal Risk)
    - Healthy Trend Continuation: Price trend backed by moderate leverage
    """
    fr_val = funding_rate.get("current_rate", 0.0001) if isinstance(funding_rate, dict) else 0.0001
    
    if fr_val > 0.0005 and price_change > 3:
        regime = "OVERLEVERAGED_LONG_TRAP_FADE"
        bias = "SHORT"
    elif fr_val < -0.0003:
        regime = "SHORT_SQUEEZE_POTENTIAL"
        bias = "LONG"
    elif price_change > 0 and 0 <= fr_val <= 0.0003:
        regime = "HEALTHY_BULLISH_CONTINUATION"
        bias = "LONG"
    elif price_change < 0 and fr_val <= 0:
        regime = "HEALTHY_BEARISH_CONTINUATION"
        bias = "SHORT"
    else:
        regime = "NEUTRAL_CONSOLIDATION"
        bias = "NONE"

    return {
        "regime": regime,
        "institutional_bias": bias,
        "funding_rate": fr_val
    }


def get_crypto_fear_greed():
    """Get Fear & Greed Index (important macro context)"""
    try:
        url = "https://api.alternative.me/fng/?limit=1&format=json"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()["data"][0]
            val = int(data["value"])
            return {
                "value": val,
                "classification": data["value_classification"],
                "signal": "EXTREME_FEAR_BUY" if val <= 20 else ("EXTREME_GREED_SELL" if val >= 80 else "NEUTRAL")
            }
    except Exception:
        pass
    return {"value": 50, "classification": "Neutral", "signal": "UNAVAILABLE"}


# ===================================================================
# BINANCE KLINES (FASTER THAN YAHOO, BETTER FOR CRYPTO)
# ===================================================================
def get_binance_klines(pair="BTCUSDT", interval="1h", limit=120):
    """
    Fetch klines from Binance API with mirror fallback.
    Returns OHLCV data.
    """
    endpoints = [
        f"https://data-api.binance.vision/api/v3/klines?symbol={pair}&interval={interval}&limit={limit}",
        f"https://fapi.binance.com/fapi/v1/klines?symbol={pair}&interval={interval}&limit={limit}",
    ]
    for url in endpoints:
        try:
            resp = requests.get(url, timeout=8, verify=False)
            if resp.status_code != 200:
                continue
            
            data = resp.json()
            if not isinstance(data, list) or len(data) == 0:
                continue

            opens = [float(k[1]) for k in data]
            highs = [float(k[2]) for k in data]
            lows = [float(k[3]) for k in data]
            closes = [float(k[4]) for k in data]
            volumes = [float(k[5]) for k in data]
            
            return {
                "opens": opens,
                "highs": highs,
                "lows": lows,
                "closes": closes,
                "volumes": volumes,
                "count": len(data)
            }
        except Exception:
            continue
    return None


def get_market_indicators_fast(binance_pair="BTCUSDT", yahoo_symbol=None):
    """
    Get market indicators using Binance Futures API (faster for crypto).
    Falls back to Yahoo Finance if Binance fails.
    """
    klines = get_binance_klines(binance_pair, "1h", 120)
    
    if not klines or not klines["closes"]:
        # Fallback to Yahoo
        if yahoo_symbol:
            return get_market_indicators(yahoo_symbol)
        return {"symbol": binance_pair, "error": "No data available", "data_quality": "FAILED"}
    
    closes = klines["closes"]
    highs = klines["highs"]
    lows = klines["lows"]
    volumes = klines["volumes"]
    
    current_price = closes[-1]
    
    # === CORE INDICATORS ===
    rsi_14 = calculate_rsi(closes, 14)
    rsi_7 = calculate_rsi(closes, 7)
    ema_9 = calculate_ema(closes, 9)
    ema_20 = calculate_ema(closes, 20)
    ema_50 = calculate_ema(closes, 50)
    ema_200 = calculate_ema(closes, min(len(closes), 100))
    macd = calculate_macd(closes)
    bb = calculate_bollinger_bands(closes)
    atr = calculate_atr(highs, lows, closes)
    support_resistance = calculate_support_resistance(highs, lows, closes)
    vol_profile = calculate_volume_profile(volumes, closes)

    # === PRICE CHANGES ===
    last_24 = closes[-24:] if len(closes) >= 24 else closes
    change_24h = round(((current_price - last_24[0]) / last_24[0]) * 100, 2) if last_24[0] else 0
    last_4h = closes[-4:] if len(closes) >= 4 else closes
    change_4h = round(((current_price - last_4h[0]) / last_4h[0]) * 100, 2) if last_4h[0] else 0
    high_24h = max(highs[-24:]) if len(highs) >= 24 else max(highs) if highs else current_price
    low_24h = min(lows[-24:]) if len(lows) >= 24 else min(lows) if lows else current_price

    # === TREND ANALYSIS ===
    ema_trend = "STRONG_BULLISH" if ema_9 > ema_20 > ema_50 else (
        "STRONG_BEARISH" if ema_9 < ema_20 < ema_50 else (
            "BULLISH_CROSSOVER" if ema_9 > ema_20 else "BEARISH_CROSSOVER"
        )
    )

    # === ATR-BASED VOLATILITY ===
    atr_pct = (atr / current_price) * 100 if current_price else 0
    volatility_state = "HIGH" if atr_pct > 3 else ("MODERATE" if atr_pct > 1.5 else "LOW")

    # === DISTANCE FROM KEY LEVELS ===
    dist_to_r1 = round(((support_resistance["resistance_1"] - current_price) / current_price) * 100, 2) if current_price else 0
    dist_to_s1 = round(((current_price - support_resistance["support_1"]) / current_price) * 100, 2) if current_price else 0

    # === BINANCE FUTURES DATA ===
    funding = get_binance_funding_rate(binance_pair)
    open_interest = get_binance_open_interest(binance_pair)
    long_short = get_binance_long_short_ratio(binance_pair)
    fear_greed = get_crypto_fear_greed()

    # === PRICE IN IDR ===
    price_idr = convert_usd_to_idr(current_price)

    # === SMC & INSTITUTIONAL DERIVATIVES CONFLUENCE ===
    smc = detect_smc_features(highs, lows, closes)
    deriv_confluence = analyze_derivatives_confluence(change_24h, funding, open_interest)

    # === 500+ QUANTITATIVE FACTORS MULTI-PILLAR MATRIX ===
    quant_matrix = None
    if evaluate_all_quant_factors:
        try:
            quant_matrix = evaluate_all_quant_factors(
                closes, highs, lows, volumes,
                funding_data=funding,
                open_interest_data=open_interest,
                long_short_data=long_short
            )
        except Exception as e:
            quant_matrix = {"error": str(e), "total_factors_evaluated": 0}

    return {
        "symbol": yahoo_symbol or binance_pair,
        "binance_pair": binance_pair,
        "currency": "USD",
        "current_price": round(current_price, 6),
        "current_price_idr": price_idr,
        "change_4h_pct": change_4h,
        "change_24h_pct": change_24h,
        "high_24h": round(high_24h, 6),
        "low_24h": round(low_24h, 6),
        # Technical Indicators
        "rsi_14": rsi_14,
        "rsi_7": rsi_7,
        "ema_9": ema_9,
        "ema_20": ema_20,
        "ema_50": ema_50,
        "ema_200": ema_200,
        "ema_trend": ema_trend,
        # MACD
        "macd": macd,
        # Bollinger Bands
        "bollinger": bb,
        # ATR / Volatility
        "atr_14": atr,
        "atr_pct": round(atr_pct, 2),
        "volatility": volatility_state,
        # Support & Resistance
        "levels": support_resistance,
        "dist_to_resistance_1_pct": dist_to_r1,
        "dist_to_support_1_pct": dist_to_s1,
        # Volume Analysis
        "volume_profile": vol_profile,
        "volume_24h": sum(volumes[-24:]) if len(volumes) >= 24 else sum(volumes),
        # Futures-Specific Data
        "funding_rate": funding,
        "open_interest": open_interest,
        "long_short_ratio": long_short,
        # Institutional SMC & Derivatives Matrix
        "smart_money_concepts": smc,
        "derivatives_matrix": deriv_confluence,
        # 500+ Multi-Pillar Quantitative Factors
        "quant_factors": quant_matrix,
        # Macro Sentiment
        "fear_greed_index": fear_greed,
        # Currency
        "usd_idr_rate": get_usd_idr_rate(),
        # Meta
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "data_quality": "COMPLETE",
        "data_source": "BINANCE_FUTURES"
    }


def get_market_indicators(symbol="BTC-USD"):
    """
    Mengambil data market real-time & indikator teknikal komprehensif.
    KHUSUS CRYPTO - data dari Yahoo Finance + Binance Futures.
    """
    # Try to use fast Binance path first
    pair_map = {item["symbol"]: item["pair"] for item in CRYPTO_FUTURES_WATCHLIST}
    binance_pair = pair_map.get(symbol, symbol.replace("-USD", "USDT").replace("20947", ""))
    
    # Try Binance first (faster)
    result = get_market_indicators_fast(binance_pair, symbol)
    if result.get("data_quality") != "FAILED":
        return result

    # === Yahoo Finance 1H Data (5 day range) - FALLBACK ===
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1h&range=5d"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            raise Exception(f"HTTP Error {resp.status_code}")

        data = resp.json()["chart"]["result"][0]
        meta = data["meta"]
        quotes = data["indicators"]["quote"][0]

        # Filter None values
        valid_indices = [i for i, c in enumerate(quotes["close"]) if c is not None]
        closes = [quotes["close"][i] for i in valid_indices]
        highs = [quotes["high"][i] for i in valid_indices if quotes["high"][i] is not None]
        lows = [quotes["low"][i] for i in valid_indices if quotes["low"][i] is not None]
        volumes = [quotes["volume"][i] for i in valid_indices if quotes["volume"][i] is not None]

        if not closes:
            raise Exception("No valid price data")

        current_price = closes[-1]

        # === CORE INDICATORS ===
        rsi_14 = calculate_rsi(closes, 14)
        rsi_7 = calculate_rsi(closes, 7)
        ema_9 = calculate_ema(closes, 9)
        ema_20 = calculate_ema(closes, 20)
        ema_50 = calculate_ema(closes, 50)
        ema_200 = calculate_ema(closes, 200) if len(closes) >= 200 else calculate_ema(closes, min(len(closes), 100))
        macd = calculate_macd(closes)
        bb = calculate_bollinger_bands(closes)
        atr = calculate_atr(highs, lows, closes)
        support_resistance = calculate_support_resistance(highs, lows, closes)
        vol_profile = calculate_volume_profile(volumes, closes)

        # === PRICE CHANGES ===
        last_24 = closes[-24:] if len(closes) >= 24 else closes
        change_24h = round(((current_price - last_24[0]) / last_24[0]) * 100, 2)
        last_4h = closes[-4:] if len(closes) >= 4 else closes
        change_4h = round(((current_price - last_4h[0]) / last_4h[0]) * 100, 2)
        high_24h = max(highs[-24:]) if len(highs) >= 24 else max(highs) if highs else current_price
        low_24h = min(lows[-24:]) if len(lows) >= 24 else min(lows) if lows else current_price

        # === TREND ANALYSIS ===
        ema_trend = "STRONG_BULLISH" if ema_9 > ema_20 > ema_50 else (
            "STRONG_BEARISH" if ema_9 < ema_20 < ema_50 else (
                "BULLISH_CROSSOVER" if ema_9 > ema_20 else "BEARISH_CROSSOVER"
            )
        )

        # === ATR-BASED VOLATILITY ===
        atr_pct = (atr / current_price) * 100 if current_price else 0
        volatility_state = "HIGH" if atr_pct > 3 else ("MODERATE" if atr_pct > 1.5 else "LOW")

        # === DISTANCE FROM KEY LEVELS ===
        dist_to_r1 = round(((support_resistance["resistance_1"] - current_price) / current_price) * 100, 2)
        dist_to_s1 = round(((current_price - support_resistance["support_1"]) / current_price) * 100, 2)

        # === BINANCE FUTURES DATA ===
        funding = get_binance_funding_rate(binance_pair)
        open_interest = get_binance_open_interest(binance_pair)
        long_short = get_binance_long_short_ratio(binance_pair)
        fear_greed = get_crypto_fear_greed()

        return {
            "symbol": symbol,
            "currency": meta.get("currency", "USD"),
            "current_price": round(current_price, 2),
            "current_price_idr": convert_usd_to_idr(current_price),
            "change_4h_pct": change_4h,
            "change_24h_pct": change_24h,
            "high_24h": round(high_24h, 2),
            "low_24h": round(low_24h, 2),
            # Technical Indicators
            "rsi_14": rsi_14,
            "rsi_7": rsi_7,
            "ema_9": ema_9,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "ema_200": ema_200,
            "ema_trend": ema_trend,
            # MACD
            "macd": macd,
            # Bollinger Bands
            "bollinger": bb,
            # ATR / Volatility
            "atr_14": atr,
            "atr_pct": round(atr_pct, 2),
            "volatility": volatility_state,
            # Support & Resistance
            "levels": support_resistance,
            "dist_to_resistance_1_pct": dist_to_r1,
            "dist_to_support_1_pct": dist_to_s1,
            # Volume Analysis
            "volume_profile": vol_profile,
            "volume_24h": sum(volumes[-24:]) if len(volumes) >= 24 else sum(volumes),
            # Futures-Specific Data
            "funding_rate": funding,
            "open_interest": open_interest,
            "long_short_ratio": long_short,
            # Macro Sentiment
            "fear_greed_index": fear_greed,
            # Currency
            "usd_idr_rate": get_usd_idr_rate(),
            # Meta
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "data_quality": "COMPLETE",
            "data_source": "YAHOO_FINANCE"
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e), "data_quality": "FAILED"}


def get_multi_timeframe(symbol="BTC-USD"):
    """
    Get data for multiple timeframes for confluence analysis.
    Returns 1H and 1D indicators side by side.
    """
    result = {"symbol": symbol}

    # Determine Binance pair
    pair_map = {item["symbol"]: item["pair"] for item in CRYPTO_FUTURES_WATCHLIST}
    binance_pair = pair_map.get(symbol, symbol.replace("-USD", "USDT").replace("20947", ""))

    # 1H timeframe (using fast Binance path)
    result["tf_1h"] = get_market_indicators_fast(binance_pair, symbol)

    # 1D timeframe from Binance
    try:
        klines_d = get_binance_klines(binance_pair, "1d", 90)
        if klines_d and klines_d["closes"]:
            closes_d = klines_d["closes"]
            result["tf_1d"] = {
                "rsi_14": calculate_rsi(closes_d, 14),
                "ema_20": calculate_ema(closes_d, 20),
                "ema_50": calculate_ema(closes_d, 50),
                "macd": calculate_macd(closes_d),
                "trend": "BULLISH" if calculate_ema(closes_d, 20) > calculate_ema(closes_d, 50) else "BEARISH"
            }
        else:
            result["tf_1d"] = {"error": "No daily data"}
    except Exception as e:
        result["tf_1d"] = {"error": str(e)}

    return result


def get_multi_timeframe_fast(binance_pair="BTCUSDT"):
    """
    Fast multi-timeframe analysis using only Binance data.
    Used for bulk scanning of the full universe.
    """
    result = {"pair": binance_pair}

    # 1H timeframe
    result["tf_1h"] = get_market_indicators_fast(binance_pair)

    # 4H timeframe
    try:
        klines_4h = get_binance_klines(binance_pair, "4h", 60)
        if klines_4h and klines_4h["closes"]:
            c4 = klines_4h["closes"]
            result["tf_4h"] = {
                "rsi_14": calculate_rsi(c4, 14),
                "ema_20": calculate_ema(c4, 20),
                "trend": "BULLISH" if calculate_ema(c4, 9) > calculate_ema(c4, 20) else "BEARISH"
            }
    except Exception:
        result["tf_4h"] = {"error": "N/A"}

    # 1D timeframe
    try:
        klines_d = get_binance_klines(binance_pair, "1d", 90)
        if klines_d and klines_d["closes"]:
            cd = klines_d["closes"]
            result["tf_1d"] = {
                "rsi_14": calculate_rsi(cd, 14),
                "ema_20": calculate_ema(cd, 20),
                "ema_50": calculate_ema(cd, 50),
                "macd": calculate_macd(cd),
                "trend": "BULLISH" if calculate_ema(cd, 20) > calculate_ema(cd, 50) else "BEARISH"
            }
    except Exception:
        result["tf_1d"] = {"error": "N/A"}

    return result


# ===================================================================
# BATCH SCANNING (PARALLEL)
# ===================================================================
def batch_quick_scan(pairs_list, max_workers=5):
    """
    Scan multiple pairs in parallel for quick screening.
    Returns dict of pair -> indicators.
    """
    results = {}
    
    def scan_one(pair_info):
        bp = pair_info.get("pair", pair_info.get("symbol", "").replace("-USD", "USDT"))
        try:
            data = get_market_indicators_fast(bp, pair_info.get("symbol"))
            return bp, data
        except Exception as e:
            return bp, {"error": str(e), "data_quality": "FAILED"}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_one, p): p for p in pairs_list}
        for future in as_completed(futures):
            try:
                pair, data = future.result()
                results[pair] = data
            except Exception:
                pass
    
    return results


if __name__ == "__main__":
    print("=== CRYPTO FUTURES MARKET DATA ENGINE v2.0 ===")
    print(f"\n--- FX Rate ---")
    print(json.dumps(get_fx_info(), indent=2))
    
    print(f"\n--- Full Universe Count ---")
    universe = get_full_universe()
    print(f"Total tradeable pairs: {len(universe)}")
    
    print(f"\n--- Top 20 Movers ---")
    movers = get_top_movers(20)
    for i, m in enumerate(movers):
        print(f"  {i+1}. {m['pair']:12s} | Score: {m.get('opportunity_score', 0):6.3f} | "
              f"Change: {m.get('price_change_24h_pct', 0):+6.2f}% | "
              f"Vol: ${m.get('volume_24h_usd', 0)/1e6:,.1f}M | {m['tier']}")
    
    print(f"\n--- BTC Indicators (Fast) ---")
    data = get_market_indicators_fast("BTCUSDT", "BTC-USD")
    print(json.dumps({k: v for k, v in data.items() if k not in ["timestamp"]}, indent=2, ensure_ascii=False))
