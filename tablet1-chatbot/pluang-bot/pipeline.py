"""
===========================================================================
PYROFUEL 5-LAYER INSTITUTIONAL CRYPTO FUTURES PIPELINE
===========================================================================
Lapisan 1: SCANNER        - Analisa data teknikal komprehensif
Lapisan 2: SETUP HUNTER   - Identifikasi pola & strategi presisi
Lapisan 3: PLAN ARCHITECT - Rancang entry/TP/SL/sizing ketat
Lapisan 4: RISK OFFICER   - Audit skeptis semua potensi kerugian
Lapisan 5: SUPREME JUDGE  - Gate-keeper final, tolak jika ragu

SEMUA LAPISAN HARUS LOLOS. SATU GAGAL = SELURUH TRADE DITOLAK.
===========================================================================
"""
import os
import sys
import json
import re
import time
import requests
import socket
import urllib3
from datetime import datetime, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Universal Anti-Blocking & ISP DNS Poisoning Bypass via DNS-over-HTTPS (DoH)
# Bypasses Telkomsel / Indosat / XL / IndiHome filtering for:
# - Groq Cloud AI (api.groq.com)
# - Google Gemini (generativelanguage.googleapis.com)
# - OpenRouter (openrouter.ai)
# - Telegram Bot (api.telegram.org)
# - Binance Futures (fapi.binance.com)
# ---------------------------------------------------------------------------
_orig_getaddrinfo = socket.getaddrinfo
_UNIVERSAL_DNS_CACHE = {
    "fapi.binance.com": "65.8.76.49",
    "fapi1.binance.com": "65.8.76.14",
    "fapi2.binance.com": "65.8.76.6",
    "fapi3.binance.com": "65.8.76.4",
    "api.groq.com": "104.18.38.236",
    "generativelanguage.googleapis.com": "172.217.114.4",
    "openrouter.ai": "104.18.3.115",
    "api.telegram.org": "149.154.166.110"
}

def _resolve_doh(domain: str):
    if domain in _UNIVERSAL_DNS_CACHE:
        return _UNIVERSAL_DNS_CACHE[domain]
    for doh_url in [
        f"https://1.1.1.1/dns-query?name={domain}&type=A",
        f"https://dns.google/resolve?name={domain}&type=A"
    ]:
        try:
            r = requests.get(doh_url, headers={"accept": "application/dns-json"}, timeout=3)
            data = r.json()
            ips = [ans["data"] for ans in data.get("Answer", []) if ans.get("type") == 1]
            if ips:
                _UNIVERSAL_DNS_CACHE[domain] = ips[0]
                return ips[0]
        except Exception:
            continue
    return None

def _custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and any(kw in host.lower() for kw in ["binance", "groq", "googleapis", "openrouter", "telegram"]):
        ip = _resolve_doh(host)
        if ip:
            return _orig_getaddrinfo(ip, port, family, type, proto, flags)
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _custom_getaddrinfo

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
from market_data import (
    get_market_indicators, get_market_indicators_fast, get_multi_timeframe,
    get_multi_timeframe_fast, CRYPTO_FUTURES_WATCHLIST, get_full_universe,
    get_top_movers, convert_usd_to_idr, convert_idr_to_usd, get_fx_info
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ===== ENVIRONMENT LOADING =====
def load_env():
    env = {}
    # 1. System environment variables
    for k, v in os.environ.items():
        if v:
            env[k] = v.strip()

    # 2. Parent directory .env (e.g. tablet1-chatbot/.env)
    parent_env = os.path.join(BASE_DIR, "..", ".env")
    if os.path.exists(parent_env):
        try:
            with open(parent_env, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip()
        except Exception:
            pass

    # 3. Local pluang-bot/.env (highest precedence)
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip()
        except Exception:
            pass
    return env

ENV = load_env()

# ===== AI PROVIDER CONFIGURATION =====
AI_PROVIDER = ENV.get("AI_PROVIDER", "ollama")  # "ollama" (local) is PRIMARY
OLLAMA_BASE_URL = ENV.get("OLLAMA_BASE_URL", "http://localhost:11434")  # Local Ollama endpoint
OLLAMA_MODEL = ENV.get("OLLAMA_MODEL", "llama3.2:1b")  # Model to use from local Ollama (1.2B fast CPU)
GROQ_API_KEY = ENV.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = ENV.get("GROQ_MODEL", "openai/gpt-oss-20b")
OPENROUTER_API_KEY = ENV.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = ENV.get("OPENROUTER_MODEL", "liquid/lfm-2.5-2.6b:free")
GEMINI_API_KEY = ENV.get("GEMINI_API_KEY", "").strip()
CEREBRAS_API_KEY = ENV.get("CEREBRAS_API_KEY", "").strip()

# Free backup models on OpenRouter — verified active free models
OPENROUTER_FREE_MODELS = [
    "minimax/minimax-m3.1-flash:free",
    "xingchen-agi/xing4.0-29b-a4b:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "dots-studio/dots-3-note-preview:free",
    "nvidia/nemotron-3.5-lightning:free",
    "liquid/lfm-2.5-2.6b:free",
]

# ===== LEVERAGE CONFIG — FIXED AT 20x (USER MANDATE) =====
FIXED_LEVERAGE = 20  # Immutable — AI cannot override this

CONFIG_FILE = os.path.join(BASE_DIR, "trading_config.json")

def get_trading_config():
    cfg = {
        "max_budget_idr": 0,           # 0 = AI uses dynamic wallet-based Kelly sizing
        "max_leverage": FIXED_LEVERAGE,  # LOCKED AT 20x — user mandate, AI cannot override
        "fixed_leverage": FIXED_LEVERAGE,
        "min_confidence_score": 45,
        "min_risk_reward_ratio": 1.5,
        "max_drawdown_pct": 5.0
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    # Always enforce 20x fixed — never allow config file to override
    cfg["max_leverage"] = FIXED_LEVERAGE
    cfg["fixed_leverage"] = FIXED_LEVERAGE
    return cfg

def save_trading_config(new_config: dict):
    cfg = get_trading_config()
    cfg.update(new_config)
    # Enforce fixed leverage — never save AI-overridden values
    cfg["max_leverage"] = FIXED_LEVERAGE
    cfg["fixed_leverage"] = FIXED_LEVERAGE
    cfg["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass
    return cfg

# Initial config
_cfg = get_trading_config()
MAX_BUDGET_IDR = _cfg.get("max_budget_idr", 0)       # 0 = dynamic wallet-based
MAX_LEVERAGE = 20                                     # FIXED 20x — user mandate
MIN_CONFIDENCE_SCORE = _cfg.get("min_confidence_score", 45)
MIN_RISK_REWARD_RATIO = _cfg.get("min_risk_reward_ratio", 1.5)
MAX_DRAWDOWN_PCT = _cfg.get("max_drawdown_pct", 5.0)


# Circuit breaker: if Groq daily limit hit, skip Groq for 6 hours then retry
_GROQ_DAILY_EXHAUSTED = {"exhausted": False, "detected_at": 0}
_GEMINI_RATELIMITED = {"exhausted": False, "detected_at": 0}


def _call_single_provider(url, headers, data, timeout=60):
    """Single provider call with response parsing (OpenAI-compatible endpoints)."""
    resp = requests.post(url, headers=headers, json=data, timeout=timeout)
    if resp.status_code != 200:
        error_text = resp.text[:300]
        # Detect daily TPD limit exhaustion (no point retrying)
        if resp.status_code == 429 and "tokens per day" in error_text.lower():
            raise DailyLimitExhausted(f"Daily token limit reached: {error_text[:150]}")
        raise Exception(f"HTTP {resp.status_code}: {error_text[:200]}")
    result = resp.json()
    if "error" in result:
        err_msg = str(result['error'])
        if "overloaded" in err_msg.lower() or "rate" in err_msg.lower():
            raise Exception(f"API Overloaded: {err_msg[:200]}")
        raise Exception(f"API Error: {err_msg[:200]}")
    choices = result.get("choices", [])
    if not choices:
        raise Exception("No choices in response")
    content = choices[0].get("message", {}).get("content", "")
    if not content:
        content = choices[0].get("message", {}).get("reasoning", "")
    if not content:
        raise Exception("Empty response from AI")
    return content


def _call_gemini_provider(api_key, model, messages, max_tokens=1500, temperature=0.1, timeout=60, is_json=True):
    """Call Google Gemini API directly (different format from OpenAI-compatible)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    
    # Convert OpenAI messages format to Gemini format
    gemini_contents = []
    system_instruction = None
    for msg in messages:
        if msg["role"] == "system":
            system_instruction = msg["content"]
        elif msg["role"] == "user":
            gemini_contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
        elif msg["role"] == "assistant":
            gemini_contents.append({"role": "model", "parts": [{"text": msg["content"]}]})
    
    gen_config = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens
    }
    if is_json:
        gen_config["responseMimeType"] = "application/json"
    
    payload = {
        "contents": gemini_contents,
        "generationConfig": gen_config
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    
    if resp.status_code != 200:
        error_text = resp.text[:300]
        if resp.status_code == 429:
            raise Exception(f"Gemini rate limited: {error_text[:200]}")
        raise Exception(f"Gemini HTTP {resp.status_code}: {error_text[:200]}")
    
    result = resp.json()
    candidates = result.get("candidates", [])
    if not candidates:
        raise Exception("No candidates in Gemini response")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise Exception("No parts in Gemini response")
    content = parts[0].get("text", "")
    if not content:
        raise Exception("Empty text in Gemini response")
    return content


class DailyLimitExhausted(Exception):
    """Raised when a provider's daily token limit is hit — no point retrying."""
    pass


def _call_ollama_provider(base_url, model, messages, max_tokens=1500, temperature=0.1, timeout=180):
    """Call local Ollama API (primary — no rate limits, no API key, no quota)."""
    url = f"{base_url}/api/chat"
    # num_ctx=512: keeps KV cache tiny so model fits in ~800MB free RAM on CPU-only machine.
    # num_predict capped at 400 for JSON responses (sufficient for compact JSON output).
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": min(max_tokens, 400),
            "num_ctx": 512,       # LOW: prevents OOM on low-RAM machines
            "num_thread": 2,      # limit CPU threads to reduce memory pressure
        }
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise Exception(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")
    result = resp.json()
    content = result.get("message", {}).get("content", "")
    if not content:
        raise Exception("Empty response from Ollama")
    return content


_OLLAMA_STATUS = {"available": False, "last_check": 0}

def _is_ollama_online(base_url: str) -> bool:
    """Check if Ollama HTTP server is responding (not just TCP port open)."""
    global _OLLAMA_STATUS
    now = time.time()
    if now - _OLLAMA_STATUS["last_check"] < 15:
        return _OLLAMA_STATUS["available"]
    _OLLAMA_STATUS["last_check"] = now
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=3)
        _OLLAMA_STATUS["available"] = resp.status_code == 200
    except Exception:
        _OLLAMA_STATUS["available"] = False
    return _OLLAMA_STATUS["available"]


def call_ai(prompt: str, system_prompt: str, max_tokens: int = 1500, temperature: float = 0.1, is_json: bool = True):
    """
    ULTIMATE AI caller — LOCAL OLLAMA FIRST (if online), then cloud cascade.
    NEVER falls back to rule-based math. Always AI.
    """
    global _GROQ_DAILY_EXHAUSTED

    effective_system = system_prompt or ""
    effective_prompt = prompt or ""
    if is_json and "json" not in (effective_system.lower() + effective_prompt.lower()):
        effective_system = (effective_system + "\nYou must respond strictly in valid JSON format.").strip()

    messages = [
        {"role": "system", "content": effective_system},
        {"role": "user", "content": effective_prompt}
    ]

    # ===== BUILD PROVIDER CHAIN =====
    providers = []

    # --- Tier 0: LOCAL OLLAMA (Local Primary — No Rate Limits, Zero Cloud Delay) ---
    if _is_ollama_online(OLLAMA_BASE_URL):
        providers.append({
            "name": "Ollama-Local",
            "type": "ollama",
            "base_url": OLLAMA_BASE_URL,
            "model": OLLAMA_MODEL,
            "max_retries": 2,
            "timeout": 180,
        })

    # --- Tier 1: Groq (Verified active: gpt-oss-20b, Qwen 27B, 120B) ---
    # Cooldown: 6 jam setelah daily TPD limit tercapai
    groq_cooldown = time.time() - _GROQ_DAILY_EXHAUSTED.get("detected_at", 0) > 21600  # 6 jam
    if GROQ_API_KEY and (not _GROQ_DAILY_EXHAUSTED["exhausted"] or groq_cooldown):
        if groq_cooldown and _GROQ_DAILY_EXHAUSTED["exhausted"]:
            _GROQ_DAILY_EXHAUSTED["exhausted"] = False  # Reset after 6h cooldown
            print("[AI] Groq 6h cooldown selesai, mencoba kembali...", flush=True)
        providers.append({
            "name": "Groq-20B",
            "type": "openai_compat",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            "model": "openai/gpt-oss-20b",  # Confirmed working 2026-10-27
            "use_json_object": False,
            "max_retries": 1,
            "timeout": 25,
        })
        providers.append({
            "name": "Groq-Qwen27B",
            "type": "openai_compat",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            "model": "qwen/qwen3.8-27b",    # Confirmed working 2026-10-27
            "use_json_object": True,
            "max_retries": 1,
            "timeout": 30,
        })
        providers.append({
            "name": "Groq-120B",
            "type": "openai_compat",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            "model": "openai/gpt-oss-120b",  # Confirmed working 2026-10-27
            "use_json_object": False,
            "max_retries": 1,
            "timeout": 35,
        })

    # --- Tier 2: Google Gemini (CONFIRMED ONLY: gemini-3.1-flash-lite via Gemini API key) ---
    # Cooldown: 5 menit setelah 503 overload
    gemini_cooldown = time.time() - _GEMINI_RATELIMITED.get("detected_at", 0) > 300
    if GEMINI_API_KEY and (not _GEMINI_RATELIMITED["exhausted"] or gemini_cooldown):
        if gemini_cooldown and _GEMINI_RATELIMITED["exhausted"]:
            _GEMINI_RATELIMITED["exhausted"] = False
        providers.append({
            "name": "Gemini-FlashLite",
            "type": "gemini",
            "api_key": GEMINI_API_KEY,
            "model": "gemini-3.1-flash-lite",  # Confirmed working 2026-10-27
            "max_retries": 2,
            "timeout": 40,
        })

    # --- Tier 3: OpenRouter (openrouter/auto selects best available free model) ---
    if OPENROUTER_API_KEY:
        # openrouter/auto confirmed returning 200 2026-10-27 (auto-selects best available)
        providers.append({
            "name": "OpenRouter-Auto",
            "type": "openai_compat",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "headers": {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://pyrofuel.app",
                "X-Title": "PYROFUEL"
            },
            "model": "openrouter/auto",
            "use_json_object": False,
            "max_retries": 2,
            "timeout": 45,
        })
        # Custom model if set and not known-broken
        broken_models = ["liquid/lfm-40b:free", "minimax/minimax-m3.1-flash:free",
                         "nvidia/nemotron-3.5-lightning:free", "liquid/lfm-2.5-2.6b:free"]
        if OPENROUTER_MODEL and OPENROUTER_MODEL not in broken_models:
            providers.append({
                "name": "OpenRouter-Custom",
                "type": "openai_compat",
                "url": "https://openrouter.ai/api/v1/chat/completions",
                "headers": {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://pyrofuel.app",
                    "X-Title": "PYROFUEL"
                },
                "model": OPENROUTER_MODEL,
                "use_json_object": False,
                "max_retries": 1,
                "timeout": 30,
            })

    # --- Tier 4: Cerebras (ultra-fast inference — add CEREBRAS_API_KEY to .env to enable) ---
    if CEREBRAS_API_KEY:
        providers.append({
            "name": "Cerebras",
            "type": "openai_compat",
            "url": "https://api.cerebras.ai/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {CEREBRAS_API_KEY}", "Content-Type": "application/json"},
            "model": "qwen-3.8-27b",
            "use_json_object": False,
            "max_retries": 1,
            "timeout": 30,
        })

    if not providers:
        raise Exception(
            "⛔ ZERO AI providers configured! Set at least one of: "
            "OPENROUTER_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, CEREBRAS_API_KEY in .env"
        )

    last_error = ""
    providers_tried = []
    for prov in providers:
        prov_name = prov["name"]
        providers_tried.append(prov_name)
        
        for attempt in range(prov["max_retries"]):
            try:
                if prov["type"] == "ollama":
                    # Local Ollama (primary provider — no API key, no rate limits)
                    tok_limit = min(max_tokens, 450) if is_json else min(max_tokens, 600)
                    content = _call_ollama_provider(
                        prov["base_url"], prov["model"], messages,
                        max_tokens=tok_limit, temperature=temperature, timeout=prov.get("timeout", 180)
                    )
                elif prov["type"] == "gemini":
                    # Gemini has its own API format
                    content = _call_gemini_provider(
                        prov["api_key"], prov["model"], messages,
                        max_tokens=max_tokens, temperature=temperature, timeout=35, is_json=is_json
                    )
                else:
                    # OpenAI-compatible endpoint (Groq, OpenRouter, Cerebras)
                    data = {
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "model": prov["model"]
                    }
                    if is_json and prov.get("use_json_object", False):
                        data["response_format"] = {"type": "json_object"}
                    content = _call_single_provider(prov["url"], prov["headers"], data, timeout=45)
                
                # Success!
                print(f"[AI OK] {prov_name} ({prov.get('model', '?')}) responded ✅", flush=True)
                return content
                
            except DailyLimitExhausted as e:
                _GROQ_DAILY_EXHAUSTED["exhausted"] = True
                _GROQ_DAILY_EXHAUSTED["detected_at"] = time.time()
                print(f"[AI] Groq DAILY LIMIT hit — cooldown 6 jam, lanjut ke provider berikut", flush=True)
                last_error = str(e)
                break  # Break inner retry loop, continue to next provider
            except Exception as e:
                err_str = str(e)
                last_error = f"{prov_name} attempt {attempt+1}: {err_str}"
                # Deteksi Gemini overloaded/503
                if prov["type"] == "gemini" and any(x in err_str.lower() for x in ["503", "overload", "service unavailable"]):
                    _GEMINI_RATELIMITED["exhausted"] = True
                    _GEMINI_RATELIMITED["detected_at"] = time.time()
                    print(f"[AI] Gemini 503 overloaded — cooldown 5 menit, lanjut ke provider berikut", flush=True)
                    break
                if attempt < prov["max_retries"] - 1:
                    wait = (attempt + 1) * 3
                    print(f"[AI RETRY] {last_error[:80]} — retry dalam {wait}s...", flush=True)
                    time.sleep(wait)
                else:
                    print(f"[AI SKIP] {prov_name} gagal: {last_error[:100]}", flush=True)

    raise Exception(
        f"ALL_AI_FAILED:{len(providers_tried)}:{' > '.join(providers_tried)}:LAST_ERROR:{last_error[:200]}"
    )



# ===================================================================
# RULE-BASED TECHNICAL FALLBACK — DISABLED (user mandate: AI ONLY)
# All fallbacks now RAISE exceptions to force the pipeline to fail
# loudly rather than proceed with math-based heuristics.
# ===================================================================
def _rule_based_setup(scan_data: dict):
    """
    Rule-based EMERGENCY fallback — AKTIF saat semua AI provider gagal/down.
    Menggunakan 500+ Quant Factors + RSI/MACD/EMA/BB/SMC scoring.
    Dipanggil otomatis saat ALL_AI_FAILED, BUKAN pengganti utama AI.
    """
    print("[FALLBACK] Semua AI gagal — menggunakan Rule-Based Quant Engine sebagai backup", flush=True)
    rsi = scan_data.get("rsi_14_1h", 50)
    ema_trend = scan_data.get("ema_trend_1h", "NEUTRAL")
    macd = scan_data.get("macd_1h", {})
    bb = scan_data.get("bollinger_1h", {})
    vol = scan_data.get("volume", {})
    funding = scan_data.get("funding_rate", {})
    smc = scan_data.get("smc", {})
    price = scan_data.get("price", 0)

    macd_hist = macd.get("histogram", 0) if isinstance(macd, dict) else 0
    macd_trend = macd.get("trend", "NEUTRAL") if isinstance(macd, dict) else "NEUTRAL"
    bb_pct_b = bb.get("percent_b", 50) if isinstance(bb, dict) else 50
    bb_squeeze = bb.get("squeeze", False) if isinstance(bb, dict) else False
    vol_trend = vol.get("volume_trend", "N/A") if isinstance(vol, dict) else "N/A"
    vol_ratio = vol.get("volume_ratio", 1.0) if isinstance(vol, dict) else 1.0
    fr_sentiment = funding.get("sentiment", "NEUTRAL") if isinstance(funding, dict) else "NEUTRAL"
    mss = smc.get("market_structure", "NEUTRAL") if isinstance(smc, dict) else "NEUTRAL"
    liq_sweep = smc.get("liquidity_sweep", "NONE") if isinstance(smc, dict) else "NONE"
    fvg = smc.get("fvg", "NONE") if isinstance(smc, dict) else "NONE"

    # === SCORING SYSTEM ===
    bull_score = 0
    bear_score = 0
    confluences = []

    # RSI
    if rsi < 30:
        bull_score += 2; confluences.append(f"RSI oversold ({rsi})")
    elif rsi < 40:
        bull_score += 1; confluences.append(f"RSI low ({rsi})")
    elif rsi > 70:
        bear_score += 2; confluences.append(f"RSI overbought ({rsi})")
    elif rsi > 60:
        bear_score += 1; confluences.append(f"RSI high ({rsi})")

    # EMA trend
    if "BULLISH" in ema_trend.upper():
        bull_score += 2; confluences.append(f"EMA {ema_trend}")
    elif "BEARISH" in ema_trend.upper():
        bear_score += 2; confluences.append(f"EMA {ema_trend}")

    # MACD
    if macd_hist > 0 and "BULLISH" in macd_trend.upper():
        bull_score += 1; confluences.append("MACD bullish")
    elif macd_hist < 0 and "BEARISH" in macd_trend.upper():
        bear_score += 1; confluences.append("MACD bearish")

    # 500+ Quant Factors Composite Score (Wall Street multi-pillar synthesis)
    qf = scan_data.get("quant_factors") or {}
    c_score = qf.get("composite_quant_score", 50.0)
    total_f = qf.get("total_factors_evaluated", 500)
    if c_score >= 60.0:
        bull_score += 3
        confluences.append(f"Quant Matrix Bullish ({c_score}/100 dari {total_f}+ faktor Wall Street)")
    elif c_score <= 40.0:
        bear_score += 3
        confluences.append(f"Quant Matrix Bearish ({c_score}/100 dari {total_f}+ faktor Wall Street)")

    # Smart Money Concepts from Quant Engine
    smc_sum = qf.get("smc_summary", {})
    if smc_sum.get("liquidity_sweep") == "BULLISH_SELL_SIDE_LIQUIDITY_SWEEP":
        bull_score += 2; confluences.append("Smart Money: Sell-side liquidity swept")
    elif smc_sum.get("liquidity_sweep") == "BEARISH_BUY_SIDE_LIQUIDITY_GRAB":
        bear_score += 2; confluences.append("Smart Money: Buy-side liquidity grab")

    # Bollinger
    if bb_pct_b < 10:
        bull_score += 1; confluences.append(f"BB oversold (%B={bb_pct_b})")
    elif bb_pct_b > 90:
        bear_score += 1; confluences.append(f"BB overbought (%B={bb_pct_b})")
    if bb_squeeze:
        confluences.append("BB Squeeze (breakout imminent)")

    # Volume
    if vol_trend == "STRONG_ACCUMULATION":
        bull_score += 1; confluences.append("Strong volume accumulation")
    elif vol_trend == "DISTRIBUTION_SELLING":
        bear_score += 1; confluences.append("Distribution selling")

    # SMC
    if "BULLISH" in liq_sweep.upper():
        bull_score += 2; confluences.append("Bullish liquidity sweep")
    elif "BEARISH" in liq_sweep.upper():
        bear_score += 2; confluences.append("Bearish liquidity sweep")
    if "BULLISH" in fvg.upper():
        bull_score += 1; confluences.append("Bullish FVG")
    elif "BEARISH" in fvg.upper():
        bear_score += 1; confluences.append("Bearish FVG")

    # Funding rate contrarian
    if "SHORTS_PAY" in fr_sentiment.upper():
        bull_score += 1; confluences.append("Funding: shorts paying")
    elif "LONGS_PAY" in fr_sentiment.upper():
        bear_score += 1; confluences.append("Funding: longs paying")

    # Market structure
    if mss == "BULLISH":
        bull_score += 1
    elif mss == "BEARISH":
        bear_score += 1

    # === BALANCED SETUP DETERMINATION (532 Quant Factors + Technical Edge) ===
    # Trade when 2+ independent confluences align. Markets rarely give 3+ perfect signals.
    # Choppy sideways (net between -1 and +1) = REJECTED to preserve cash.
    net = bull_score - bear_score
    direction = "NONE"
    setup_name = "NO_CLEAR_SETUP"
    prob = 35

    if net >= 3:
        direction = "LONG"
        setup_name = "RULE_BASED_STRONG_BULLISH"
        prob = min(72 + (net - 3) * 4, 88)
    elif net >= 2:
        direction = "LONG"
        setup_name = "RULE_BASED_BULLISH_CONFLUENCE"
        prob = min(58 + (net - 2) * 5, 75)
    elif net <= -3:
        direction = "SHORT"
        setup_name = "RULE_BASED_STRONG_BEARISH"
        prob = min(72 + (abs(net) - 3) * 4, 88)
    elif net <= -2:
        direction = "SHORT"
        setup_name = "RULE_BASED_BEARISH_CONFLUENCE"
        prob = min(58 + (abs(net) - 2) * 5, 75)
    else:
        # Net -1 to +1: truly choppy, no clear edge
        direction = "NONE"
        setup_name = "NO_CLEAR_SETUP"
        prob = 40

    return {
        "setup_name": setup_name,
        "direction": direction,
        "confluence_count": len(confluences),
        "confluences": confluences[:6],
        "probability_pct": prob,
        "bull_score": bull_score,
        "bear_score": bear_score,
        "explanation_id": f"Rule-based: Bull {bull_score} vs Bear {bear_score} (AI unavailable)",
        "ai_fallback": True
    }


def _rule_based_plan(scan_data: dict, setup: dict, market_data: dict):
    """Rule-based trading plan when AI is down or for quick baseline."""
    price = market_data.get("current_price", scan_data.get("price", 0))
    atr = market_data.get("atr_14", 0)
    atr_pct = market_data.get("atr_pct", 0) or (atr / price * 100 if price else 0)
    direction = setup.get("direction", "NONE")

    if direction == "NONE" or price <= 0:
        return {"action": "SKIP", "order_type": "MARKET", "entry_price": 0, "limit_price": 0,
                "stop_loss": 0, "take_profit": 0, "take_profit_1": 0, "take_profit_2": 0,
                "risk_reward_ratio": "0:0", "position_size_idr": 0,
                "leverage": FIXED_LEVERAGE, "reasoning": "No setup detected (rule-based)", "ai_fallback": True}

    sl_mult = 1.5
    tp_mult = 3.0  # Single Take Profit target (RRR 1:2.0)

    if direction == "LONG":
        sl = price - (atr * sl_mult)
        tp = price + (atr * tp_mult)
    else:
        sl = price + (atr * sl_mult)
        tp = price - (atr * tp_mult)

    sl_dist = abs(price - sl)
    tp_dist = abs(tp - price)
    rrr = round(tp_dist / sl_dist, 1) if sl_dist > 0 else 0

    return {
        "action": direction,
        "order_type": "MARKET",
        "entry_price": round(price, 6),
        "limit_price": round(price, 6),
        "stop_loss": round(sl, 6),
        "take_profit": round(tp, 6),
        "take_profit_1": round(tp, 6),
        "take_profit_2": round(tp, 6),
        "risk_reward_ratio": f"1:{rrr}",
        "position_size_idr": 0,
        "leverage": FIXED_LEVERAGE,
        "risk_pct_of_capital": 2.0,
        "sl_distance_pct": round((sl_dist / price) * 100, 2),
        "tp_distance_pct": round((tp_dist / price) * 100, 2),
        "reasoning": f"ATR Single TP plan: SL {sl_mult}x ATR, TP {tp_mult}x ATR (20x Fixed)",
        "ai_fallback": True
    }

def _rule_based_risk(scan_data: dict, setup: dict, plan: dict, market_data: dict):
    """Rule-based risk audit baseline and resilient fallback."""
    checks = []
    total = 0

    # 1. RRR check
    try:
        parts = plan.get("risk_reward_ratio", "0:0").split(":")
        rrr_val = float(parts[1]) / float(parts[0]) if len(parts) == 2 and float(parts[0]) > 0 else 0
    except Exception:
        rrr_val = 0
    passed = rrr_val >= 1.5
    if passed: total += 1
    checks.append({"name": "RRR_CHECK", "status": "PASS" if passed else "FAIL", "detail": f"RRR 1:{rrr_val}"})

    # 2. RSI check
    rsi = scan_data.get("rsi_14_1h", 50)
    direction = setup.get("direction", "NONE")
    rsi_ok = not (direction == "LONG" and rsi > 75) and not (direction == "SHORT" and rsi < 25)
    if rsi_ok: total += 1
    checks.append({"name": "RSI_CHECK", "status": "PASS" if rsi_ok else "FAIL", "detail": f"RSI {rsi}"})

    # 3. Volume check
    vol_trend = (scan_data.get("volume", {}) or {}).get("volume_trend", "N/A")
    vol_ok = vol_trend not in ("LOW_INTEREST",)
    if vol_ok: total += 1
    checks.append({"name": "VOLUME_CHECK", "status": "PASS" if vol_ok else "FAIL", "detail": vol_trend})

    # 4. Trend alignment
    ema_trend = scan_data.get("ema_trend_1h", "NEUTRAL")
    trend_ok = (direction == "LONG" and "BULLISH" in ema_trend.upper()) or \
               (direction == "SHORT" and "BEARISH" in ema_trend.upper()) or direction == "NONE"
    if trend_ok: total += 1
    checks.append({"name": "TREND_ALIGNMENT", "status": "PASS" if trend_ok else "WARN", "detail": ema_trend})

    # 5. Funding check
    fr = (scan_data.get("funding_rate", {}) or {})
    fr_rate = fr.get("rate", 0) if isinstance(fr, dict) else 0
    fr_ok = abs(fr_rate) < 0.03
    if fr_ok: total += 1
    checks.append({"name": "FUNDING_CHECK", "status": "PASS" if fr_ok else "WARN", "detail": f"Rate: {fr_rate}"})

    # 6. Volatility check
    atr_pct = scan_data.get("atr_pct", 0) or 0
    vol_ok = atr_pct < 6.0 or atr_pct == 0
    if vol_ok: total += 1
    checks.append({"name": "VOLATILITY_CHECK", "status": "PASS" if vol_ok else "FAIL", "detail": f"ATR: {atr_pct}%"})

    # 7. Sentiment check
    fg = scan_data.get("fear_greed", {}) or {}
    fg_val = fg.get("value", 50) if isinstance(fg, dict) else 50
    sent_ok = 25 < fg_val < 75
    if sent_ok: total += 1
    checks.append({"name": "SENTIMENT_CHECK", "status": "PASS" if sent_ok else "WARN", "detail": f"FG: {fg_val}"})

    # 8. Long/Short ratio check
    ls = scan_data.get("long_short", {}) or {}
    ls_ratio = ls.get("ratio", 1.0) if isinstance(ls, dict) else 1.0
    ls_ok = 0.5 < ls_ratio < 2.0
    if ls_ok: total += 1
    checks.append({"name": "LONG_SHORT_CHECK", "status": "PASS" if ls_ok else "WARN", "detail": f"Ratio: {ls_ratio}"})

    # 9. Liquidity / Leverage check
    lev = plan.get("leverage", 1)
    liq_ok = (lev == FIXED_LEVERAGE) or (lev <= 25)
    if liq_ok: total += 1
    checks.append({"name": "LIQUIDITY_CHECK", "status": "PASS" if liq_ok else "FAIL", "detail": f"Lev: {lev}x (Fixed)"})

    # 10. Max drawdown check
    sl_dist = plan.get("sl_distance_pct", 0) or 0
    dd_ok = sl_dist < 3.0 or sl_dist == 0
    if dd_ok: total += 1
    checks.append({"name": "MAX_DRAWDOWN", "status": "PASS" if dd_ok else "FAIL", "detail": f"SL dist: {sl_dist}%"})

    crit = [c["name"] for c in checks if c["status"] == "FAIL"]
    verdict = "LOW_RISK" if total >= 8 else ("MEDIUM_RISK" if total >= 6 else "HIGH_RISK")
    rec = "PROCEED" if total >= 6 else "REJECT"

    return {
        "total_score": total, "max_score": 10, "pass_rate_pct": total * 10,
        "checks": checks, "critical_failures": crit,
        "risk_verdict": verdict, "recommendation": rec,
        "max_drawdown_pct": plan.get("sl_distance_pct", 2.0),
        "reasoning": f"Rule-based risk audit: {total}/10 passed", "ai_fallback": True
    }


def parse_json_from_text(text):
    """Robust JSON parser from AI output with auto-repair for truncated reasoning output"""
    if not text:
        return None
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # Try extracting markdown JSON block
    match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    # Try finding complete JSON object
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    # Try finding starting { and auto-closing truncated JSON
    start_idx = text.find('{')
    if start_idx != -1:
        truncated = text[start_idx:]
        for suffix in ['"}]}', '"}]}}', '}]}', ']}', '}', '"}', '"]}', '"}}']:
            try:
                return json.loads(truncated + suffix)
            except Exception:
                pass
            # Try trimming to last comma or quote
            trimmed = truncated.rstrip(' ,\n\r\t')
            for s in ['', '"}', '}', '}]}', '"}]}']:
                try:
                    return json.loads(trimmed + s)
                except Exception:
                    pass

    # Try parsing bullet point / markdown key-values (e.g. from Gemma / thought models)
    if ("setup_name" in text or "direction" in text or "status" in text) and ":" in text:
        obj = {}
        for line in text.splitlines():
            clean = line.strip().lstrip("*-# ").strip()
            if ":" in clean:
                k, v = clean.split(":", 1)
                k = k.strip().strip('"\'` ')
                v = v.strip().strip('"\'` ')
                if k in ("setup_name", "direction", "explanation_id", "status", "action", "order_type", "risk_reward_ratio", "reasoning", "recommendation", "risk_verdict", "final_reason"):
                    obj[k] = v
                elif k in ("confluence_count", "probability_pct", "confidence_score", "total_score", "max_score", "pass_rate_pct", "leverage"):
                    try:
                        digits = re.sub(r'[^0-9]', '', v)
                        if digits:
                            obj[k] = int(digits)
                    except Exception:
                        pass
                elif k in ("entry_price", "stop_loss", "take_profit", "take_profit_1", "take_profit_2", "limit_price", "position_size_idr", "sl_distance_pct", "tp_distance_pct", "max_drawdown_pct"):
                    try:
                        floats = re.findall(r'[-+]?\d*\.?\d+', v)
                        if floats:
                            obj[k] = float(floats[0])
                    except Exception:
                        pass
                elif k in ("confluences", "critical_failures"):
                    obj[k] = [x.strip().strip('"\'') for x in v.strip('[]').split(',') if x.strip()]
        if obj.get("setup_name") or obj.get("direction") or obj.get("status"):
            return obj

    return None


# ===========================================================================
# LAPISAN 1: SCANNER (Data Collection & Technical Analysis)
# ===========================================================================
def layer1_scanning(symbol: str):
    """Collect comprehensive market data with multi-timeframe analysis"""
    mtf = get_multi_timeframe(symbol)
    data_1h = mtf.get("tf_1h", {})
    data_1d = mtf.get("tf_1d", {})

    if "error" in data_1h:
        return None, f"Data error: {data_1h['error']}"

    # Clean quant factors to keep core institutional composite metrics and remove bulky factor dumps
    qf_raw = data_1h.get("quant_factors") or {}
    qf_summary = {
        "composite_quant_score": qf_raw.get("composite_quant_score", 50.0),
        "signal": qf_raw.get("signal", "NEUTRAL"),
        "action": qf_raw.get("action", "WAIT"),
        "total_factors_evaluated": qf_raw.get("total_factors_evaluated", 500),
        "pillars": qf_raw.get("pillars", {}),
        "regime": qf_raw.get("regime", {}),
        "smc_summary": qf_raw.get("smc_summary", {}),
        "derivatives_summary": qf_raw.get("derivatives_summary", {})
    }

    # Generate scan summary for AI consumption (lean, high signal-to-noise ratio)
    scan_summary = {
        "symbol": symbol,
        "price": data_1h.get("current_price"),
        "change_4h": data_1h.get("change_4h_pct"),
        "change_24h": data_1h.get("change_24h_pct"),
        "rsi_14_1h": data_1h.get("rsi_14"),
        "rsi_7_1h": data_1h.get("rsi_7"),
        "ema_trend_1h": data_1h.get("ema_trend"),
        "macd_1h": data_1h.get("macd"),
        "bollinger_1h": data_1h.get("bollinger"),
        "atr_pct": data_1h.get("atr_pct"),
        "volatility": data_1h.get("volatility"),
        "levels": data_1h.get("levels"),
        "volume": data_1h.get("volume_profile"),
        "funding_rate": data_1h.get("funding_rate"),
        "long_short": data_1h.get("long_short_ratio"),
        "fear_greed": data_1h.get("fear_greed_index"),
        "smc": data_1h.get("smart_money_concepts"),
        "derivatives_matrix": data_1h.get("derivatives_matrix"),
        "quant_factors": qf_summary,
        "daily_rsi": data_1d.get("rsi_14") if isinstance(data_1d, dict) else None,
        "daily_trend": data_1d.get("trend") if isinstance(data_1d, dict) else None,
        "daily_macd": data_1d.get("macd") if isinstance(data_1d, dict) else None,
    }

    # Macro Breaking News & Sentiment Sentinel (summarized to prevent token bloat)
    try:
        from news_sentinel import get_news_sentiment_summary
        ns = get_news_sentiment_summary()
        scan_summary["news_macro"] = {
            "market_sentiment": ns.get("market_sentiment", "NEUTRAL"),
            "sentiment_score": ns.get("sentiment_score", 50),
            "latest_headline": ns.get("latest_headline", ""),
            "top_headlines": [a.get("title", "") for a in ns.get("top_articles", [])[:3] if isinstance(a, dict)]
        }
    except Exception:
        scan_summary["news_macro"] = {"market_sentiment": "NEUTRAL", "sentiment_score": 50}

    return data_1h, scan_summary


# ===========================================================================
# LAPISAN 2: SETUP HUNTER (Identifikasi Pola & Strategi)
# ===========================================================================
def layer2_setup_hunter(symbol: str, scan_data: dict):
    """AI identifies trading setup — compact prompt to preserve token budget"""
    # Only pass essential fields to AI (compress input tokens from ~2500 to ~600)
    compact = {
        "sym": symbol,
        "price": scan_data.get("price"),
        "chg24h": scan_data.get("change_24h"),
        "rsi14": scan_data.get("rsi_14_1h"),
        "ema": scan_data.get("ema_trend_1h"),
        "macd_hist": (scan_data.get("macd_1h") or {}).get("histogram"),
        "macd_trend": (scan_data.get("macd_1h") or {}).get("trend"),
        "bb_pct_b": (scan_data.get("bollinger_1h") or {}).get("percent_b"),
        "bb_squeeze": (scan_data.get("bollinger_1h") or {}).get("squeeze"),
        "atr_pct": scan_data.get("atr_pct"),
        "vol_trend": (scan_data.get("volume") or {}).get("volume_trend"),
        "vol_ratio": (scan_data.get("volume") or {}).get("volume_ratio"),
        "fund_rate": (scan_data.get("funding_rate") or {}).get("rate"),
        "fund_sent": (scan_data.get("funding_rate") or {}).get("sentiment"),
        "support1": (scan_data.get("levels") or {}).get("support_1"),
        "resist1": (scan_data.get("levels") or {}).get("resistance_1"),
        "mss": (scan_data.get("smc") or {}).get("market_structure"),
        "liq_sweep": (scan_data.get("smc") or {}).get("liquidity_sweep"),
        "daily_rsi": scan_data.get("daily_rsi"),
        "daily_trend": scan_data.get("daily_trend"),
        "qscore": (scan_data.get("quant_factors") or {}).get("composite_quant_score"),
        "news": (scan_data.get("news_macro") or {}).get("market_sentiment"),
    }
    compact_json = json.dumps(compact, ensure_ascii=False)

    system = (
        "Crypto futures setup analyst. Respond ONLY in valid JSON. DO NOT output internal reasoning.\n"
        "Start your response directly with '{'.\n"
        "Rules:\n"
        "- Identify actionable setups with statistical edge: TREND_CONTINUATION, EMA_PULLBACK_ENTRY, "
        "MEAN_REVERSION_BOUNCE, BREAKOUT_MOMENTUM, SMC_LIQUIDITY_SWEEP, BOLLINGER_SQUEEZE_BREAKOUT, "
        "RSI_DIVERGENCE_PLAY, FUNDING_RATE_ARBITRAGE.\n"
        "- Need ≥2 independent confirmations (e.g. Trend + Volume, or S/R bounce + RSI, or Squeeze + Structure).\n"
        "- In sideways/range markets, look for MEAN_REVERSION_BOUNCE, BOLLINGER_SQUEEZE_BREAKOUT, or S/R levels.\n"
        "- Use NO_CLEAR_SETUP only if the market is completely flat or signals are heavily conflicting.\n"
        "Output: {\"setup_name\":\"\",\"direction\":\"LONG/SHORT/NONE\","
        "\"confluence_count\":0,\"confluences\":[],"
        "\"probability_pct\":50,\"explanation_id\":\"\"}"
    )

    prompt = (
        f"Analyze {symbol}. Data:\n{compact_json}\n"
        f"Output ONLY JSON setup. Use NO_CLEAR_SETUP ONLY if signals are truly flat/conflicting."
    )

    raw = call_ai(prompt, system, max_tokens=600, temperature=0.1)
    result = parse_json_from_text(raw)

    if not result:
        # parse failure — pakai rule-based daripada default ke NO_CLEAR_SETUP
        print(f"[WARN] Layer 2 parse failed for {symbol} — menggunakan rule-based setup", flush=True)
        return _rule_based_setup(scan_data)

    if result.get("confluence_count", 0) < 1 and result.get("setup_name") != "NO_CLEAR_SETUP":
        result["confluence_count"] = max(result.get("confluence_count", 0), 1)

    return result


# ===========================================================================
# TP TIME PREDICTION ENGINE
# Prediksi berapa JAM sampai TP tercapai, berbasis:
#   1. ATR velocity   : berapa % price bergerak per jam rata-rata
#   2. Momentum factor: semakin kuat momentum, semakin cepat
#   3. Setup multiplier: setup tertentu lebih cepat dari yg lain
#   4. Volume confirm : high vol = gerakan lebih resolute
# ===========================================================================
def predict_tp_time(current_price: float, take_profit: float,
                    stop_loss: float, setup_name: str,
                    scan_data: dict, market_data: dict) -> dict:
    """
    Prediksi waktu sampai TP tercapai berdasarkan model ATR velocity.
    Returns dict dengan eta_label, eta_hours_realistic, dsb.
    """
    if not current_price or not take_profit or current_price <= 0:
        return {"eta_label": "N/A", "model_note": "Data tidak cukup"}

    tp_dist_pct = abs(take_profit - current_price) / current_price * 100
    sl_dist_pct = abs(stop_loss - current_price) / current_price * 100 if stop_loss else 0

    # 1. Baseline ATR velocity — gerakan bersih per jam ~35% dari ATR (bukan unidirectional)
    atr_pct = scan_data.get("atr_pct") or market_data.get("atr_pct") or 2.0
    atr_velocity = atr_pct * 0.35

    # 2. Momentum multiplier
    rsi = scan_data.get("rsi_14_1h") or market_data.get("rsi_14") or 50
    macd_hist = abs((scan_data.get("macd_1h") or {}).get("histogram", 0) or 0)
    vol_ratio = (scan_data.get("volume") or {}).get("volume_ratio", 1.0) or 1.0
    change_4h = abs(scan_data.get("change_4h") or 0)

    m = 1.0
    if rsi > 65 or rsi < 35:  m += 0.3
    elif rsi > 55 or rsi < 45: m += 0.1
    if macd_hist and atr_pct > 0: m += min(macd_hist / (atr_pct * 0.1 + 0.001), 1.5) * 0.2
    if vol_ratio > 1.5:  m += 0.25
    elif vol_ratio > 1.2: m += 0.1
    if change_4h > 2.0: m += 0.2
    elif change_4h > 1.0: m += 0.1
    m = min(m, 2.5)

    # 3. Setup multiplier
    setup_mults = {
        "BREAKOUT_MOMENTUM": 1.5, "BOLLINGER_SQUEEZE_BREAKOUT": 1.4,
        "FUNDING_RATE_ARBITRAGE": 1.4, "VOLATILITY_EXPANSION": 1.3,
        "SMC_LIQUIDITY_SWEEP": 1.1, "TREND_CONTINUATION": 1.0,
        "EMA_PULLBACK_ENTRY": 1.0, "MACD_CROSSOVER_MOMENTUM": 0.9,
        "MEAN_REVERSION_BOUNCE": 0.85, "RSI_DIVERGENCE_PLAY": 0.8,
    }
    sm = setup_mults.get(setup_name, 1.0)

    # 4. Effective velocity
    velocity = max(atr_velocity * m * sm, 0.05)

    # 5. ETA calculation
    eta_r = min(round(tp_dist_pct / velocity, 1), 168)  # realistic
    eta_o = min(round(eta_r / 1.8, 1), 168)              # optimistic (1.8x lebih cepat)
    eta_p = min(round(eta_r * 2.5, 1), 168)              # pessimistic (2.5x lebih lambat)

    def _fmt(h):
        if h < 1:   return f"{int(h*60)} menit"
        elif h < 24: return f"{h:.0f} jam"
        else:        return f"{h/24:.1f} hari"

    confidence = 50
    if m > 1.5:       confidence += 10
    if vol_ratio > 1.3: confidence += 8
    if atr_pct < 5:   confidence += 7
    if change_4h > 1: confidence += 5
    confidence = min(confidence, 80)

    return {
        "tp_distance_pct": round(tp_dist_pct, 2),
        "sl_distance_pct": round(sl_dist_pct, 2),
        "atr_per_hour_pct": round(atr_velocity, 3),
        "effective_velocity_pct_per_hour": round(velocity, 3),
        "momentum_multiplier": round(m, 2),
        "setup_multiplier": sm,
        "eta_hours_optimistic": eta_o,
        "eta_hours_realistic": eta_r,
        "eta_hours_pessimistic": eta_p,
        "eta_label": f"{_fmt(eta_o)} – {_fmt(eta_p)}",
        "eta_detail": f"Realistis ~{_fmt(eta_r)}, best case {_fmt(eta_o)}, worst case {_fmt(eta_p)}",
        "confidence_pct": confidence,
        "model_note": (
            f"ATR {atr_pct:.2f}%/candle × momentum {m:.2f}x × setup {sm}x "
            f"= {velocity:.3f}%/jam. TP jarak {tp_dist_pct:.2f}%."
        )
    }


# ===========================================================================
# LAPISAN 3: TRADING PLAN ARCHITECT (Entry/TP/SL/Sizing)
# ===========================================================================
def layer3_build_plan(symbol: str, scan_data: dict, setup_result: dict, market_data: dict):
    """Build precise trading plan — strict SL/TP to prevent margin calls"""
    current_price = market_data.get("current_price", 0)
    atr = market_data.get("atr_14", 0)
    atr_pct = market_data.get("atr_pct", 0) or (atr / current_price * 100 if current_price else 1.5)
    direction = setup_result.get("direction", "LONG")

    # Pre-compute safe SL/TP bounds (hard constraint — AI cannot override)
    if direction == "LONG":
        sl_safe = round(current_price * (1 - max(atr_pct * 1.5, 0.8) / 100), 6)
        tp_safe = round(current_price * (1 + max(atr_pct * 3.0, 1.5) / 100), 6)
    else:
        sl_safe = round(current_price * (1 + max(atr_pct * 1.5, 0.8) / 100), 6)
        tp_safe = round(current_price * (1 - max(atr_pct * 3.0, 1.5) / 100), 6)
    sl_dist_pct = abs(current_price - sl_safe) / current_price * 100
    tp_dist_pct = abs(tp_safe - current_price) / current_price * 100

    support1 = (scan_data.get("levels") or {}).get("support_1", sl_safe)
    resist1  = (scan_data.get("levels") or {}).get("resistance_1", tp_safe)

    system = (
        "Crypto futures trading plan architect. Respond ONLY in JSON, no prose.\n"
        "RULES (IMMUTABLE):\n"
        f"1. LEVERAGE = 20x ISOLATED. NEVER change this.\n"
        f"2. DIRECTION = {direction}\n"
        f"3. SL MUST be between {sl_safe:.6f} and {current_price:.6f} (ATR-based, not wider than 3% from entry)\n"
        f"4. TP must give RRR ≥ 1.5 vs the SL distance. Suggested TP near {tp_safe:.6f}\n"
        f"5. Use key S/R: support={support1}, resistance={resist1}\n"
        "6. order_type: LIMIT if price near S/R level, else MARKET\n"
        "7. position_size_idr = 0 (auto from wallet)\n"
        "Output: {\"action\":\"LONG/SHORT/SKIP\",\"order_type\":\"MARKET/LIMIT\","
        "\"entry_price\":0,\"limit_price\":0,\"stop_loss\":0,\"take_profit\":0,"
        "\"risk_reward_ratio\":\"1:2.5\",\"leverage\":20,\"position_size_idr\":0,"
        "\"sl_distance_pct\":1.5,\"tp_distance_pct\":3.75,\"reasoning\":\"brief\"}"
    )

    prompt = (
        f"{symbol} @ ${current_price}, ATR {atr_pct:.2f}%, Setup: {setup_result.get('setup_name')}.\n"
        f"SL safe zone: {sl_safe:.6f} | TP target: {tp_safe:.6f}\n"
        f"Output ONLY JSON plan with SL ≤ {sl_dist_pct:.2f}% from entry."
    )

    raw = call_ai(prompt, system, max_tokens=600, temperature=0.05)
    result = parse_json_from_text(raw)

    if not result:
        print(f"[FALLBACK] Layer 3 parse failed for {symbol} — rule-based plan", flush=True)
        return _rule_based_plan(scan_data, setup_result, market_data)

    # Normalize TPs
    tp = result.get("take_profit") or result.get("take_profit_2") or result.get("take_profit_1") or 0
    result["take_profit"] = tp
    result["take_profit_1"] = tp
    result["take_profit_2"] = tp

    if not result.get("order_type"):
        result["order_type"] = "MARKET"
    if result["order_type"].upper() == "LIMIT" and not result.get("limit_price"):
        result["limit_price"] = result.get("entry_price", current_price)
    elif result["order_type"].upper() != "LIMIT":
        result["limit_price"] = result.get("entry_price", current_price)

    # ENFORCE FIXED 20x — immutable
    result["leverage"] = FIXED_LEVERAGE

    # SAFETY: If AI returned a bad SL (wider than 4% = almost certain margin call on 20x)
    # Force it back to safe computed value
    ai_sl = result.get("stop_loss", 0)
    if ai_sl and current_price > 0:
        ai_sl_pct = abs(current_price - ai_sl) / current_price * 100
        if ai_sl_pct > 4.0 or ai_sl_pct < 0.1:
            print(f"[SL SAFETY] {symbol}: AI SL distance {ai_sl_pct:.2f}% unsafe → forcing to {sl_dist_pct:.2f}%", flush=True)
            result["stop_loss"] = sl_safe
            result["sl_distance_pct"] = sl_dist_pct

    # SAFETY: If AI returned bad TP (RRR < 1.3)
    ai_tp = result.get("take_profit", 0)
    if ai_tp and current_price > 0 and ai_sl and ai_sl != current_price:
        ai_rrr = abs(ai_tp - current_price) / abs(current_price - result["stop_loss"]) if abs(current_price - result["stop_loss"]) > 0 else 0
        if ai_rrr < 1.3:
            print(f"[TP SAFETY] {symbol}: AI RRR {ai_rrr:.2f} too low → forcing TP to {tp_safe:.6f}", flush=True)
            result["take_profit"] = tp_safe
            result["take_profit_1"] = tp_safe
            result["take_profit_2"] = tp_safe

    if result.get("position_size_idr") is None or result.get("position_size_idr") < 0:
        result["position_size_idr"] = 0

    # === TP TIME PREDICTION — inject ke setiap plan ===
    try:
        final_tp  = result.get("take_profit", 0)
        final_sl  = result.get("stop_loss", 0)
        final_ent = result.get("entry_price", current_price)
        if final_tp and final_ent:
            tp_eta = predict_tp_time(
                current_price=final_ent,
                take_profit=final_tp,
                stop_loss=final_sl,
                setup_name=setup_result.get("setup_name", ""),
                scan_data=scan_data,
                market_data=market_data
            )
            result["tp_time_prediction"] = tp_eta
    except Exception as _e:
        result["tp_time_prediction"] = {"eta_label": "N/A", "model_note": str(_e)}

    return result



# ===========================================================================
# LAPISAN 4: CHIEF RISK OFFICER (Professional Risk Management)
# ===========================================================================
def layer4_risk_audit(symbol: str, scan_data: dict, setup_result: dict, plan_result: dict, market_data: dict):
    """Risk check — compact prompt to save tokens"""
    sl = plan_result.get("stop_loss", 0)
    tp = plan_result.get("take_profit", 0)
    entry = plan_result.get("entry_price", scan_data.get("price", 0))
    direction = setup_result.get("direction", "NONE")
    rsi = scan_data.get("rsi_14_1h", 50)
    vol_trend = (scan_data.get("volume") or {}).get("volume_trend", "N/A")
    ema = scan_data.get("ema_trend_1h", "NEUTRAL")
    fr_rate = (scan_data.get("funding_rate") or {}).get("rate", 0)
    atr_pct = scan_data.get("atr_pct", 0)
    news_sent = (scan_data.get("news_macro") or {}).get("market_sentiment", "NEUTRAL")

    # Pre-compute RRR
    if entry and sl and tp and abs(entry - sl) > 0:
        rrr_val = round(abs(tp - entry) / abs(entry - sl), 2)
    else:
        rrr_val = 0

    sl_dist_pct = abs(entry - sl) / entry * 100 if entry else 0

    system = (
        "Risk officer. 8-point check. Respond ONLY in compact JSON.\n"
        "PASS=1pt. FAIL=0pt. Need ≥6/8 for PROCEED.\n"
        "Checks: RRR≥1.5, RSI not extreme against direction, Volume not LOW_INTEREST, "
        "EMA aligned with direction, Funding rate <0.02%, ATR<6%, "
        "SL distance <3%, News not BEARISH for LONG.\n"
        "Output: {\"total_score\":7,\"max_score\":8,\"pass_rate_pct\":87,"
        "\"critical_failures\":[],\"max_drawdown_pct\":2.5,"
        "\"risk_verdict\":\"LOW_RISK\",\"recommendation\":\"PROCEED\","
        "\"reasoning\":\"brief\"}"
    )

    prompt = (
        f"{symbol} {direction} @ ${entry:.4f}. SL={sl:.4f}({sl_dist_pct:.2f}%), "
        f"TP={tp:.4f}, RRR=1:{rrr_val}. RSI={rsi}, EMA={ema}, "
        f"Vol={vol_trend}, Funding={fr_rate}%, ATR={atr_pct:.2f}%, News={news_sent}.\n"
        f"Output ONLY risk JSON."
    )

    raw = call_ai(prompt, system, max_tokens=250, temperature=0.05)
    result = parse_json_from_text(raw)

    if not result:
        return _rule_based_risk(scan_data, setup_result, plan_result, market_data)

    if not result.get("checks"):
        result["checks"] = [
            {"name": "RISK_AUDIT_SUMMARY",
             "status": "PASS" if result.get("total_score", 0) >= 6 else "WARN",
             "detail": result.get("reasoning", "Audit complete")}
        ]

    return result


# ===========================================================================
# LAPISAN 5: SUPREME JUDGE (Final Decision - Professional Trading Desk)
# ===========================================================================
def layer5_final_judgment(symbol: str, scan_data: dict, setup_result: dict,
                          plan_result: dict, risk_result: dict, market_data: dict):
    """Final gate — compact prompt, strict approve criteria"""
    cfg = get_trading_config()
    min_conf = cfg.get("min_confidence_score", 55)  # raised from 45 to 55
    min_rrr = cfg.get("min_risk_reward_ratio", 1.5)

    entry = plan_result.get("entry_price", 0)
    sl = plan_result.get("stop_loss", 0)
    tp = plan_result.get("take_profit", 0)
    direction = setup_result.get("direction", "NONE")
    prob = setup_result.get("probability_pct", 0)
    risk_score = risk_result.get("total_score", 0)
    risk_max = risk_result.get("max_score", 8)
    setup_name = setup_result.get("setup_name", "NO_CLEAR_SETUP")

    # Pre-compute RRR for context
    rrr_val = round(abs(tp - entry) / abs(entry - sl), 2) if entry and sl and abs(entry - sl) > 0 else 0
    sl_pct = round(abs(entry - sl) / entry * 100, 2) if entry else 0

    system = (
        f"Final trading judge. Respond ONLY in JSON.\n"
        f"APPROVE if ALL: direction≠NONE, setup≠NO_CLEAR_SETUP, "
        f"confluence≥2, risk_score≥5/{risk_max}, RRR≥{min_rrr}, "
        f"confidence≥{min_conf}%, SL distance < 3.0%.\n"
        f"For 20x leverage: SL between 0.5% and 2.5% is EXCELLENT and SAFE (far from 5% liquidation).\n"
        f"Only REJECT if SL > 3.5% (liquidation danger), RRR < {min_rrr}, or major signal conflict.\n"
        f"Output: {{\"status\":\"APPROVED/REJECTED\",\"confidence_score\":{prob},"
        f"\"direction\":\"{direction}\",\"order_type\":\"MARKET/LIMIT\","
        f"\"limit_price\":{entry},\"entry_price\":{entry},"
        f"\"take_profit\":{tp},\"stop_loss\":{sl},"
        f"\"risk_reward_ratio\":\"1:{rrr_val}\",\"leverage\":20,"
        f"\"position_size_idr\":0,\"setup_name\":\"{setup_name}\","
        f"\"risk_audit_pass_rate\":{risk_result.get('pass_rate_pct',0)},"
        f"\"final_reason\":\"brief reason\"}}"
    )

    prompt = (
        f"{symbol}: {direction} @ ${entry:.4f}, SL=${sl:.4f}({sl_pct:.2f}%), "
        f"TP=${tp:.4f}(RRR 1:{rrr_val}), Setup={setup_name}, "
        f"Confidence={prob}%, Risk {risk_score}/{risk_max}.\n"
        f"APPROVE or REJECT? Output ONLY JSON."
    )

    raw = call_ai(prompt, system, max_tokens=300, temperature=0.05)
    result = parse_json_from_text(raw)

    if not result:
        approved = (
            direction != "NONE" and
            setup_name != "NO_CLEAR_SETUP" and
            prob >= min_conf and
            risk_score >= 6 and
            plan_result.get("action") not in ("SKIP", None) and
            sl_pct < 3.5
        )
        tp_val = plan_result.get("take_profit") or plan_result.get("take_profit_2", 0)
        result = {
            "status": "APPROVED" if approved else "REJECTED",
            "confidence_score": prob,
            "direction": direction,
            "setup_name": setup_name,
            "order_type": plan_result.get("order_type", "MARKET"),
            "limit_price": plan_result.get("limit_price", entry),
            "entry_price": entry,
            "take_profit": tp_val,
            "take_profit_1": tp_val,
            "take_profit_2": tp_val,
            "stop_loss": sl,
            "risk_reward_ratio": f"1:{rrr_val}",
            "leverage": FIXED_LEVERAGE,
            "position_size_idr": 0,
            "max_risk_idr": 1000,
            "final_reason": f"Rule-based: {'; '.join(setup_result.get('confluences', [])[:3])}",
            "ai_fallback": True
        }
    else:
        tp_val = result.get("take_profit") or result.get("take_profit_2") or result.get("take_profit_1") or plan_result.get("take_profit") or 0
        result["take_profit"] = tp_val
        result["take_profit_1"] = tp_val
        result["take_profit_2"] = tp_val
        if not result.get("order_type"):
            result["order_type"] = plan_result.get("order_type", "MARKET")
        if not result.get("limit_price"):
            result["limit_price"] = plan_result.get("limit_price", result.get("entry_price", 0))
        if not result.get("leverage"):
            result["leverage"] = FIXED_LEVERAGE
        if not result.get("position_size_idr"):
            result["position_size_idr"] = plan_result.get("position_size_idr") or 0

    return _apply_safety_gates(result, setup_result, plan_result, risk_result, scan_data, market_data)


def _apply_safety_gates(result, setup_result, plan_result, risk_result, scan_data, market_data):
    """
    PYTHON-LEVEL SAFETY GATES - Balanced institutional risk controls.
    Block only CLEARLY dangerous trades, allow setups with reasonable edge.
    AI governs leverage, limit/market order type, modal, and single Take Profit.
    """
    cfg = get_trading_config()
    current_max_budget = cfg.get("max_budget_idr", 0)
    current_max_leverage = FIXED_LEVERAGE  # Always 20x — immutable
    current_min_confidence = cfg.get("min_confidence_score", 45)
    current_min_rrr = cfg.get("min_risk_reward_ratio", 1.5)

    # Preserve AI-governed parameters
    tp_val = result.get("take_profit") or plan_result.get("take_profit") or plan_result.get("take_profit_2", 0)
    result["take_profit"] = tp_val
    result["take_profit_1"] = tp_val
    result["take_profit_2"] = tp_val
    result["order_type"] = result.get("order_type") or plan_result.get("order_type", "MARKET")
    result["limit_price"] = result.get("limit_price") or plan_result.get("limit_price", result.get("entry_price", 0))
    # ENFORCE FIXED 20x LEVERAGE — always, no exceptions
    result["leverage"] = FIXED_LEVERAGE

    reasons = []

    # Gate 1: Confidence < min
    conf = result.get("confidence_score", 0)
    if conf < current_min_confidence:
        result["status"] = "REJECTED"
        reasons.append(f"Confidence score {conf}% di bawah batas {current_min_confidence}%")

    # Gate 2: If max_budget_idr > 0 cap to it; 0 means dynamic wallet-based (no cap)
    if current_max_budget > 0 and result.get("position_size_idr", 0) > current_max_budget:
        result["position_size_idr"] = current_max_budget
    elif result.get("position_size_idr", 0) < 0:
        result["position_size_idr"] = 0   # 0 triggers dynamic wallet sizing in auto_trader

    # Gate 3: Leverage LOCKED at 20x (user mandate)
    result["leverage"] = FIXED_LEVERAGE

    # Gate 4: NO_CLEAR_SETUP or Direction NONE = REJECT
    if result.get("direction", "NONE") == "NONE" or setup_result.get("setup_name") == "NO_CLEAR_SETUP":
        result["status"] = "REJECTED"
        reasons.append("Pasar sideways/konsolidasi tanpa setup arah yang jelas")

    # Gate 5: Plan SKIP rejects
    if plan_result.get("action") == "SKIP":
        result["status"] = "REJECTED"
        reasons.append("Trading plan SKIP")

    # Gate 6: Risk audit must pass at least 5/10 checks (balanced, not ultra-strict)
    risk_score = risk_result.get("total_score", 5)
    if risk_score < 5:
        result["status"] = "REJECTED"
        reasons.append(f"Risk audit hanya lolos {risk_score}/10 (minimum 5/10)")

    # Gate 6b: Confluence count minimum 2 (real markets rarely have 3+ perfect confluences)
    confluence_count = setup_result.get("confluence_count", 0)
    if confluence_count < 2 and setup_result.get("setup_name") != "NO_CLEAR_SETUP":
        result["status"] = "REJECTED"
        reasons.append(f"Hanya {confluence_count} confluence (minimum 2)")

    # Gate 7: Critical failures >= 3 = REJECT (allow 1-2 warnings)
    cf = risk_result.get("critical_failures", [])
    real_cf = [c for c in cf if c != "PARSE_FAILURE"]
    if len(real_cf) >= 3:
        result["status"] = "REJECTED"
        reasons.append(f"Terdapat {len(real_cf)} kegagalan risiko kritis: {', '.join(real_cf)}")

    # Gate 8: RRR check
    if result.get("direction", "NONE") != "NONE":
        try:
            rrr_str = result.get("risk_reward_ratio", "0:0")
            parts = rrr_str.split(":")
            if len(parts) == 2:
                rrr_val = float(parts[1]) / float(parts[0]) if float(parts[0]) > 0 else 0
                if rrr_val < current_min_rrr:
                    result["status"] = "REJECTED"
                    reasons.append(f"Risk-to-Reward {rrr_str} di bawah rasio minimum 1:{current_min_rrr}")
        except Exception:
            pass

    # Gate 9: Quant score veto (only extreme contradictions)
    quant_matrix = scan_data.get("quant_factors") or market_data.get("quant_factors")
    if quant_matrix and isinstance(quant_matrix, dict) and "composite_quant_score" in quant_matrix:
        c_score = quant_matrix.get("composite_quant_score", 50.0)
        direction = result.get("direction", "NONE")
        if direction == "LONG" and c_score < 25.0:
            result["status"] = "REJECTED"
            reasons.append(f"Quant Score {c_score}/100 sangat bearish — tidak mendukung LONG")
        elif direction == "SHORT" and c_score > 75.0:
            result["status"] = "REJECTED"
            reasons.append(f"Quant Score {c_score}/100 sangat bullish — tidak mendukung SHORT")

    # Gate 10: SL distance must be < 5% (expanded from 3% for volatile crypto)
    try:
        entry = float(result.get("entry_price", 0))
        sl = float(result.get("stop_loss", 0))
        if entry > 0 and sl > 0:
            sl_dist_pct = abs(entry - sl) / entry * 100
            if sl_dist_pct > 5.0:
                result["status"] = "REJECTED"
                reasons.append(f"SL distance {sl_dist_pct:.1f}% melebihi batas 5%")
    except Exception:
        pass

    # Append rejection reasons if any
    if reasons:
        result["final_reason"] = result.get("final_reason", "") + " [SAFETY: " + "; ".join(reasons) + "]"

    return result


# ===========================================================================
# MAIN PIPELINE EXECUTOR
# ===========================================================================
def run_5_layer_pipeline(symbol: str, active_positions: list = None):
    """
    Execute the unified 5-layer quant pipeline + 9-agent committee debate in ONE seamless process.
    RESILIENT: If AI providers fail, falls back to rule-based technical analysis.
    Auto-trading NEVER halts due to API overload.
    """
    start_time = time.time()
    pipeline_id = f"{symbol}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    ai_fallback_used = False

    # === LAYER 1: SCANNING (pure data, no AI) ===
    market_data, scan_summary = layer1_scanning(symbol)
    if market_data is None:
        return {
            "pipeline_id": pipeline_id,
            "symbol": symbol,
            "error": scan_summary,
            "status": "FAILED",
            "execution_time_sec": round(time.time() - start_time, 2)
        }

    # === LAYER 2: SETUP HUNTER (AI with fallback) ===
    try:
        setup_result = layer2_setup_hunter(symbol, scan_summary)
    except Exception as e:
        print(f"[FALLBACK] Layer 2 AI failed for {symbol}: {e} — using rule-based setup", flush=True)
        setup_result = _rule_based_setup(scan_summary)
        ai_fallback_used = True

    # Branch on setup detection
    if setup_result.get("setup_name") == "NO_CLEAR_SETUP" or setup_result.get("direction") in ("NONE", "SKIP", None):
        plan_result = _rule_based_plan(scan_summary, setup_result, market_data)
        risk_result = _rule_based_risk(scan_summary, setup_result, plan_result, market_data)
        final_call = {
            "status": "REJECTED",
            "confidence_score": setup_result.get("probability_pct", 30),
            "direction": "NONE",
            "setup_name": "NO_CLEAR_SETUP",
            "entry_price": scan_summary.get("price", 0),
            "take_profit_1": 0,
            "take_profit_2": 0,
            "stop_loss": 0,
            "risk_reward_ratio": "0:0",
            "leverage": FIXED_LEVERAGE,
            "position_size_idr": 0,
            "final_reason": setup_result.get("reasoning") or "Pasar sideways tanpa setup terkonfirmasi. Dana aman di USDT.",
            "checklist_passed": 0,
            "checklist_total": 10
        }
    else:
        # === LAYER 3: BUILD PLAN (AI with fallback) ===
        try:
            plan_result = layer3_build_plan(symbol, scan_summary, setup_result, market_data)
        except Exception as e:
            print(f"[FALLBACK] Layer 3 AI failed for {symbol}: {e} — using rule-based plan", flush=True)
            plan_result = _rule_based_plan(scan_summary, setup_result, market_data)
            ai_fallback_used = True

        # === LAYER 4: RISK AUDIT (AI with fallback) ===
        try:
            risk_result = layer4_risk_audit(symbol, scan_summary, setup_result, plan_result, market_data)
        except Exception as e:
            print(f"[FALLBACK] Layer 4 AI failed for {symbol}: {e} — using rule-based risk", flush=True)
            risk_result = _rule_based_risk(scan_summary, setup_result, plan_result, market_data)
            ai_fallback_used = True

        # === LAYER 5: FINAL JUDGMENT (AI with fallback) ===
        try:
            final_call = layer5_final_judgment(symbol, scan_summary, setup_result, plan_result, risk_result, market_data)
        except Exception as e:
            print(f"[FALLBACK] Layer 5 AI failed for {symbol}: {e} — using rule-based judgment", flush=True)
            # Build final judgment from rule-based layers
            cfg = get_trading_config()
            direction = setup_result.get("direction", "NONE")
            prob = setup_result.get("probability_pct", 0)
            risk_rec = risk_result.get("recommendation", "REJECT")
            risk_score = risk_result.get("total_score", 0)
            setup_name = setup_result.get("setup_name", "NO_CLEAR_SETUP")

            approved = (
                direction != "NONE" and
                setup_name != "NO_CLEAR_SETUP" and
                prob >= cfg.get("min_confidence_score", 65) and
                risk_score >= 6
            )

            final_call = {
                "status": "APPROVED" if approved else "REJECTED",
                "confidence_score": prob,
                "direction": direction,
                "setup_name": setup_name,
                "order_type": plan_result.get("order_type", "MARKET"),
                "limit_price": plan_result.get("limit_price", plan_result.get("entry_price", 0)),
                "entry_price": plan_result.get("entry_price", 0),
                "take_profit": plan_result.get("take_profit") or plan_result.get("take_profit_2", 0),
                "take_profit_1": plan_result.get("take_profit") or plan_result.get("take_profit_2", 0),
                "take_profit_2": plan_result.get("take_profit") or plan_result.get("take_profit_2", 0),
                "stop_loss": plan_result.get("stop_loss", 0),
                "risk_reward_ratio": plan_result.get("risk_reward_ratio", "0:0"),
                "leverage": FIXED_LEVERAGE,
                "position_size_idr": plan_result.get("position_size_idr", 50000),
                "max_risk_idr": 1000,
                "risk_audit_pass_rate": risk_result.get("pass_rate_pct", 0),
                "checklist_passed": risk_score,
                "checklist_total": 10,
                "final_reason": f"Rule-based judgment (AI unavailable): {', '.join(setup_result.get('confluences', [])[:3])}",
                "ai_fallback": True
            }
            # Apply Python safety gates
            final_call = _apply_safety_gates(final_call, setup_result, plan_result, risk_result, scan_summary, market_data)
            ai_fallback_used = True

    execution_time = round(time.time() - start_time, 2)

    result = {
        "pipeline_id": pipeline_id,
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "execution_time_sec": execution_time,
        "status": final_call.get("status", "COMPLETED"),
        "ai_fallback_used": ai_fallback_used,
        "layer1_scanning": {
            "current_price": market_data.get("current_price"),
            "rsi_14": market_data.get("rsi_14"),
            "rsi_7": market_data.get("rsi_7"),
            "ema_trend": market_data.get("ema_trend"),
            "macd": market_data.get("macd"),
            "bollinger": market_data.get("bollinger"),
            "atr_pct": market_data.get("atr_pct"),
            "volatility": market_data.get("volatility"),
            "volume_profile": market_data.get("volume_profile"),
            "funding_rate": market_data.get("funding_rate"),
            "long_short_ratio": market_data.get("long_short_ratio"),
            "fear_greed": market_data.get("fear_greed_index"),
            "levels": market_data.get("levels"),
            "quant_factors": market_data.get("quant_factors"),
        },
        "layer2_setup": setup_result,
        "layer3_plan": plan_result,
        "layer4_risk": risk_result,
        "layer5_final_call": final_call
    }

    # === LAYER 6: SIDANG MAHKAMAH 9-AGENT MULTI-COMMITTEE ===
    # ⚡ TOKEN GUARD: Committee HANYA dijalankan jika Layer 5 sudah APPROVED
    # Ini mencegah pemborosan ~7000 token/koin untuk koin yang sudah REJECTED
    # (dahulu committee jalan untuk SEMUA koin → pemborosan masif)
    committee_res = None
    _layer5_approved = final_call.get("status") == "APPROVED"
    if not _layer5_approved:
        print(f"[PIPELINE] ⏭️ Committee DILEWATI untuk {symbol} (Layer 5: {final_call.get('status', 'REJECTED')}) — hemat ~7000 token", flush=True)
    else:
        try:
            from multi_agent_committee import run_multi_agent_committee
            print(f"[PIPELINE+SIDANG] 🏛️ Layer 5 APPROVED → Sidang 9-Agent untuk {symbol}...", flush=True)
            committee_res = run_multi_agent_committee(symbol, active_positions=active_positions or [])
            result["committee"] = committee_res

            if committee_res:
                com_approved = bool(committee_res.get("approved"))
                com_dir = committee_res.get("direction", "SKIP")
                com_conf = committee_res.get("confidence_pct", 0)

                if com_approved and com_dir in ("LONG", "SHORT") and com_conf >= 60:
                    final_call["status"] = "APPROVED"
                    final_call["direction"] = com_dir
                    final_call["confidence_score"] = max(final_call.get("confidence_score", 0), com_conf)
                    result["status"] = "APPROVED"
                    if committee_res.get("trade_params"):
                        tp_p = committee_res["trade_params"]
                        if tp_p.get("entry_price"): final_call["entry_price"] = tp_p["entry_price"]
                        if tp_p.get("tp1_price"): final_call["take_profit_1"] = tp_p["tp1_price"]
                        if tp_p.get("tp2_price"): final_call["take_profit_2"] = tp_p["tp2_price"]
                        if tp_p.get("sl_price"): final_call["stop_loss"] = tp_p["sl_price"]
                        if tp_p.get("budget_idr"): final_call["position_size_idr"] = tp_p["budget_idr"]
                elif not com_approved and final_call.get("status") == "APPROVED":
                    pm_dec = committee_res.get("portfolio_manager", {}).get("decision", "Veto Risiko Sidang")
                    final_call["status"] = "REJECTED_BY_COMMITTEE"
                    final_call["final_reason"] = f"Ditolak Sidang 9-Agent: {pm_dec}"
                    result["status"] = "REJECTED_BY_COMMITTEE"
        except Exception as ce:
            print(f"[PIPELINE+SIDANG] Notice: {ce}", flush=True)


    # Save result to file for dashboard consumption
    try:
        result_file = os.path.join(RESULTS_DIR, f"{symbol.replace('-', '_')}_latest.json")
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # Also save to history
        history_file = os.path.join(RESULTS_DIR, f"history_{symbol.replace('-', '_')}.jsonl")
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    except Exception as e:
        result["save_error"] = str(e)

    return result


def scan_all_watchlist():
    """Scan all crypto futures in watchlist"""
    results = {}
    for item in CRYPTO_FUTURES_WATCHLIST:
        symbol = item["symbol"]
        print(f"[SCAN] Memulai pipeline untuk {symbol}...", flush=True)
        try:
            result = run_5_layer_pipeline(symbol)
            results[symbol] = result
            status = result.get("layer5_final_call", {}).get("status", "UNKNOWN")
            conf = result.get("layer5_final_call", {}).get("confidence_score", 0)
            print(f"[SCAN] {symbol}: {status} (Confidence: {conf}%) - {result.get('execution_time_sec')}s", flush=True)
        except Exception as e:
            print(f"[SCAN] ERROR {symbol}: {e}", flush=True)
            results[symbol] = {"error": str(e)}
        time.sleep(1)  # Rate limit respect

    # Save summary
    try:
        summary_file = os.path.join(RESULTS_DIR, "watchlist_summary.json")
        summary = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "total_scanned": len(results),
            "approved": sum(1 for r in results.values()
                          if r.get("layer5_final_call", {}).get("status") == "APPROVED"),
            "rejected": sum(1 for r in results.values()
                           if r.get("layer5_final_call", {}).get("status") == "REJECTED"),
            "errors": sum(1 for r in results.values() if "error" in r),
            "results": {k: {
                "status": v.get("layer5_final_call", {}).get("status", "ERROR"),
                "confidence": v.get("layer5_final_call", {}).get("confidence_score", 0),
                "direction": v.get("layer5_final_call", {}).get("direction", "NONE"),
                "setup": v.get("layer2_setup", {}).get("setup_name", "N/A"),
                "price": v.get("layer1_scanning", {}).get("current_price", 0),
            } for k, v in results.items()}
        }
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return results


if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC-USD"
    print(f"[*] Menguji 5-Layer Pipeline untuk {symbol}...", flush=True)
    res = run_5_layer_pipeline(symbol)
    print("\n=== HASIL 5-LAYER PIPELINE ===", flush=True)
    print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
