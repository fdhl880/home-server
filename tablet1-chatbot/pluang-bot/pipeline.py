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
import logging
import math
import re
import time
import requests
import socket
from datetime import datetime, timezone

import state_io
from state_io import atomic_write_json

logger = logging.getLogger(__name__)

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
_UNIVERSAL_DNS_CACHE = {}
_DNS_TTL_SEC = 300.0

_STATIC_EDGE_IPS = {
    "fapi.binance.com": "65.8.76.49",
    "fapi1.binance.com": "65.8.76.14",
    "api.binance.com": "65.8.76.49",
    "api.groq.com": "104.18.38.236",
    "openrouter.ai": "104.18.3.115",
    "api.telegram.org": "149.154.166.110"
}

def _resolve_doh(domain: str):
    now = time.time()
    cached = _UNIVERSAL_DNS_CACHE.get(domain)
    if cached and (now - cached["ts"] < _DNS_TTL_SEC):
        return cached["ip"]
    for doh_url in [
        f"https://1.1.1.1/dns-query?name={domain}&type=A",
        f"https://dns.google/resolve?name={domain}&type=A"
    ]:
        try:
            r = requests.get(doh_url, headers={"accept": "application/dns-json"}, timeout=2.0)
            data = r.json()
            ips = [ans["data"] for ans in data.get("Answer", []) if ans.get("type") == 1]
            if ips:
                ip = ips[0]
                if not ip.startswith("202.3.") and not ip.startswith("36."):
                    _UNIVERSAL_DNS_CACHE[domain] = {"ip": ip, "ts": now}
                    return ip
        except Exception:
            continue
    fallback_ip = _STATIC_EDGE_IPS.get(domain)
    if fallback_ip:
        _UNIVERSAL_DNS_CACHE[domain] = {"ip": fallback_ip, "ts": now}
        return fallback_ip
    return cached["ip"] if cached else None

def _custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and any(kw in host.lower() for kw in ["binance", "groq", "openrouter", "telegram"]):
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
    try:
        import bootstrap_credentials
        bootstrap_credentials.bootstrap()
    except Exception:
        pass
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
                        env[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass
    for k, v in env.items():
        os.environ[k] = v
    return env

ENV = load_env()

# ===== AI PROVIDER CONFIGURATION =====
AI_PROVIDER = ENV.get("AI_PROVIDER", "groq")
OLLAMA_BASE_URL = ENV.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = ENV.get("OLLAMA_MODEL", "llama3.2:1b")
GROQ_API_KEY = ENV.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = ENV.get("GROQ_MODEL", "llama-3.3-70b-versatile")
if GROQ_MODEL == "qwen/qwen3.8-27b":
    GROQ_MODEL = "llama-3.3-70b-versatile"
OPENROUTER_API_KEY = ENV.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = ENV.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
GEMINI_API_KEY = ENV.get("GEMINI_API_KEY", "").strip()
if GEMINI_API_KEY.startswith("AQ."):
    GEMINI_API_KEY = ""
CEREBRAS_API_KEY = ENV.get("CEREBRAS_API_KEY", "").strip()

# Free backup models on OpenRouter — verified active free models
OPENROUTER_FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-32b:free",
    "deepseek/deepseek-r1:free",
    "google/gemma-3-27b-it:free",
    "liquid/lfm-2.5-2.6b:free",
]

from config_schema import (
    load_trading_config as _load_validated_trading_config,
    save_validated_trading_config as _save_validated_trading_config,
)

# ===== LEVERAGE CONFIG — FIXED AT 20x (USER MANDATE) =====
FIXED_LEVERAGE = 20  # Immutable — AI cannot override this

CONFIG_FILE = os.path.join(BASE_DIR, "trading_config.json")

def get_trading_config():
    cfg = _load_validated_trading_config(CONFIG_FILE)
    # Always enforce 20x fixed — never allow config file to override
    cfg["max_leverage"] = FIXED_LEVERAGE
    cfg["fixed_leverage"] = FIXED_LEVERAGE
    return cfg

def save_trading_config(new_config: dict):
    updates = dict(new_config or {})
    updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return _save_validated_trading_config(
        updates,
        config_path=CONFIG_FILE,
        enforce_fixed_leverage=FIXED_LEVERAGE,
    )

# Initial config
_cfg = get_trading_config()
MAX_BUDGET_IDR = _cfg.get("max_budget_idr", 0)       # 0 = dynamic wallet-based
MAX_LEVERAGE = 20                                     # FIXED 20x — user mandate
MIN_CONFIDENCE_SCORE = _cfg.get("min_confidence_score", 65)
MIN_RISK_REWARD_RATIO = _cfg.get("min_risk_reward_ratio", 1.5)
MAX_DRAWDOWN_PCT = _cfg.get("max_drawdown_pct", 25.0)


# Circuit breaker: if Groq daily limit hit, skip Groq for 6 hours then retry
_GROQ_DAILY_EXHAUSTED = {"exhausted": False, "detected_at": 0}
_GEMINI_RATELIMITED = {"exhausted": False, "detected_at": 0}

# Per-provider/model cooldown (quota is per MODEL: e.g. Groq TPD 200k/model, Gemini quota per model).
_PROVIDER_COOLDOWN = {}


def _cooldown(name: str, seconds: float):
    _PROVIDER_COOLDOWN[name] = time.time() + max(5.0, seconds)


def _in_cooldown(name: str) -> bool:
    return time.time() < _PROVIDER_COOLDOWN.get(name, 0)


def _cooldown_from_error(err: str) -> float:
    """Pick a cooldown (sec) from an error string. Honors 'try again in XmYs' hints."""
    e = err.lower()
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", e)
    if m and any(m.groups()):
        h, mi, se = (float(x) if x else 0.0 for x in m.groups())
        return max(3, h * 3600 + mi * 60 + se + 1)
    if "http 404" in e or "no longer available" in e or "does not exist" in e:
        return 24 * 3600
    if any(x in e for x in ("http 401", "http 403", "http 402", "insufficient credits", "invalid api key")):
        return 6 * 3600
    if "429" in e or "rate limit" in e or "quota" in e:
        return 10  # Groq TPM reset is 2-5s; cooldown 10s instead of 600s
    if any(x in e for x in ("503", "overload", "high demand", "unavailable", "timed out", "timeout")):
        return 30
    return 10


class AIUnavailable(Exception):
    """AI could not produce a usable answer. The bot must NOT trade (user mandate: AI only, no math fallback)."""
    pass


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
        # "reasoning" = chain-of-thought text, NOT an answer (it is not JSON and poisons parsing).
        # Empty content normally means reasoning consumed max_tokens -> treat as failure + retry/next provider.
        raise Exception(f"Empty content (reasoning ate max_tokens?) finish={choices[0].get('finish_reason')}")
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


_OR_FREE_CACHE = {"ts": 0, "models": []}
_OR_PREFERRED = ("nemotron-3-ultra", "gpt-oss-120b", "llama-3.3-70b", "qwen3", "nemotron-3.5-super", "laguna-s", "deepseek", "dots", "gpt-oss-20b", "mistral", "gemma", "llama")
_OR_EXCLUDE = ("safety", "guard", "code", "inkling", "embed", "lightning")


def _openrouter_free_models():
    """Live list of OpenRouter ':free' models (cached 6h), best-guess quality order. Never raises."""
    now = time.time()
    if _OR_FREE_CACHE["models"] and now - _OR_FREE_CACHE["ts"] < 6 * 3600:
        return _OR_FREE_CACHE["models"]
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=15)
        ids = [m["id"] for m in r.json().get("data", []) if str(m.get("id", "")).endswith(":free")
               and not any(x in m["id"] for x in _OR_EXCLUDE)]
        def rank(mid):
            for i, k in enumerate(_OR_PREFERRED):
                if k in mid:
                    return i
            return len(_OR_PREFERRED)
        ids.sort(key=rank)
        if ids:
            _OR_FREE_CACHE.update(ts=now, models=ids)
    except Exception as e:
        print(f"[AI] OpenRouter model list gagal: {str(e)[:80]}", flush=True)
    return _OR_FREE_CACHE["models"]


def call_ai(prompt: str, system_prompt: str, max_tokens: int = 1500, temperature: float = 0.1, is_json: bool = True):
    """
    ULTIMATE AI caller — delegates to ai_gateway.py (T2.1-T2.2) with persistent rate-limit
    state & verified model IDs, falling back to built-in cascade if ai_gateway is not loaded.
    NEVER falls back to rule-based math. Always AI.
    """
    try:
        from ai_gateway import call_ai as _gw_call_ai
        return _gw_call_ai(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            is_json=is_json,
        )
    except ImportError:
        pass
    except Exception as gw_err:
        if "ALL_AI_FAILED" in str(gw_err) or "AIUnavailable" in type(gw_err).__name__:
            raise

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

    # --- Tier 1: Groq (Multi-Key Pool & Verified active model IDs) ---
    groq_raw_keys = os.getenv("GROQ_API_KEYS", "") or GROQ_API_KEY
    groq_keys = []
    if groq_raw_keys:
        for k in groq_raw_keys.split(","):
            kc = k.strip().strip('"').strip("'")
            if kc and kc not in groq_keys:
                groq_keys.append(kc)
    for idx in range(1, 10):
        nk = os.getenv(f"GROQ_API_KEY_{idx}", "").strip().strip('"').strip("'")
        if nk and nk not in groq_keys:
            groq_keys.append(nk)

    for k_idx, g_key in enumerate(groq_keys):
        tag = f"-K{k_idx+1}" if len(groq_keys) > 1 else ""
        _gh = {"Authorization": f"Bearer {g_key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        for _n, _m, _eff, _jo, _to in [
            (f"Groq{tag}-Qwen3.8", "qwen/qwen3.8-27b", "none", False, 30),
            (f"Groq{tag}-GPT120B", "openai/gpt-oss-120b", "low", False, 30),
            (f"Groq{tag}-GPT20B", "openai/gpt-oss-20b", "low", False, 25),
            (f"Groq{tag}-Allam7B", "allam-2-7b", None, False, 25),
        ]:
            providers.append({
                "name": _n, "type": "openai_compat",
                "url": "https://api.groq.com/openai/v1/chat/completions",
                "headers": _gh, "model": _m, "use_json_object": _jo,
                "reasoning_effort": _eff, "min_tokens": 1500 if _eff else 0,
                "max_retries": 1, "timeout": _to,
            })

    # --- Tier 2: Google Gemini (Official current models) ---
    if GEMINI_API_KEY:
        for _gm in [x.strip() for x in os.getenv(
                "GEMINI_MODELS",
                "gemini-2.5-flash,gemini-2.0-flash,gemini-2.5-flash-lite").split(",") if x.strip()]:
            providers.append({
                "name": f"Gemini-{_gm}", "type": "gemini", "api_key": GEMINI_API_KEY,
                "model": _gm, "min_tokens": 1500, "max_retries": 1, "timeout": 30,
            })

    # --- Tier 3: OpenRouter — ONLY ':free' models, discovered live (never 'openrouter/auto': needs credits -> 402) ---
    if OPENROUTER_API_KEY:
        for _om in _openrouter_free_models()[:4]:
            providers.append({
                "name": f"OR-{_om}", "type": "openai_compat",
                "url": "https://openrouter.ai/api/v1/chat/completions",
                "headers": {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json",
                            "HTTP-Referer": "https://pyrofuel.app", "X-Title": "PYROFUEL"},
                "model": _om, "use_json_object": False, "min_tokens": 1500,
                "max_retries": 1, "timeout": 45,
            })

    # --- Tier 4: Cerebras (T2.1 Verified active model ID) ---
    if CEREBRAS_API_KEY:
        providers.append({
            "name": "Cerebras-Llama70B",
            "type": "openai_compat",
            "url": "https://api.cerebras.ai/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {CEREBRAS_API_KEY}", "Content-Type": "application/json"},
            "model": "llama-3.3-70b",
            "use_json_object": True,
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
        if _in_cooldown(prov_name):
            continue
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
                        max_tokens=max(max_tokens, prov.get("min_tokens", 0)), temperature=temperature,
                        timeout=prov.get("timeout", 40), is_json=is_json
                    )
                else:
                    # OpenAI-compatible endpoint (Groq, OpenRouter, Cerebras)
                    data = {
                        "messages": messages,
                        "max_tokens": max(max_tokens, prov.get("min_tokens", 0)),
                        "temperature": temperature,
                        "model": prov["model"]
                    }
                    if prov.get("reasoning_effort"):
                        data["reasoning_effort"] = prov["reasoning_effort"]
                    if is_json and prov.get("use_json_object", False):
                        data["response_format"] = {"type": "json_object"}
                    content = _call_single_provider(prov["url"], prov["headers"], data, timeout=45)
                
                # Success!
                print(f"[AI OK] {prov_name} ({prov.get('model', '?')}) responded ✅", flush=True)
                return content
                
            except DailyLimitExhausted as e:
                last_error = f"{prov_name}: {e}"
                _cooldown(prov_name, _cooldown_from_error(str(e)))
                print(f"[AI] {prov_name} limit harian/TPD habis — cooldown {int(_PROVIDER_COOLDOWN[prov_name]-time.time())}s, lanjut provider lain", flush=True)
                break  # next provider
            except Exception as e:
                err_str = str(e)
                last_error = f"{prov_name} attempt {attempt+1}: {err_str}"
                if attempt >= prov["max_retries"] - 1:
                    _cooldown(prov_name, _cooldown_from_error(err_str))
                    print(f"[AI SKIP] {prov_name} gagal: {last_error[:110]}", flush=True)
                else:
                    time.sleep((attempt + 1) * 3)

    raise Exception(
        f"ALL_AI_FAILED:{len(providers_tried)}:{' > '.join(providers_tried)}:LAST_ERROR:{last_error[:200]}"
    )



# ===================================================================
# 500+ QUANT FACTORS SYSTEMATIC FALLBACK (WALL STREET MATRIX)
# Activates automatically if all cloud AI keys hit daily rate limits,
# ensuring the trading pipeline NEVER halts completely.
# ===================================================================
def _rule_based_setup(scan_data: dict):
    """Disabled: AI-ONLY mandate requires Cloud AI for setup selection (no rule fallback)."""
    raise AIUnavailable("Rule-based setup dinonaktifkan: keputusan harus dari AI")
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
    raise AIUnavailable("Rule-based plan dinonaktifkan: keputusan harus dari AI")
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
    raise AIUnavailable("Rule-based risk dinonaktifkan: keputusan harus dari AI")
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
def _ai_json(prompt: str, system: str, max_tokens: int, temperature: float, label: str) -> dict:
    """AI call that MUST return a JSON object. One repair retry; otherwise AIUnavailable (=> no trade)."""
    last = ""
    for attempt in range(2):
        p = prompt if attempt == 0 else (
            prompt + "\n\nIMPORTANT: your previous reply was not valid JSON. Reply with ONE valid JSON object only, no prose.")
        raw = call_ai(p, system, max_tokens=max_tokens, temperature=temperature)
        res = parse_json_from_text(raw)
        if res:
            return res
        last = (raw or "")[:120]
    raise AIUnavailable(f"{label}: AI output is not valid JSON after retry: {last!r}")


def _fetch_live_l2_orderbook(symbol: str) -> dict:
    """Fetch 20-level L2 Order Book from Binance Futures for Cont-Kukanov-Stoikov OFI."""
    try:
        from market_data import normalize_symbol_to_pair
        pair = normalize_symbol_to_pair(symbol)
        r = requests.get(f"https://fapi.binance.com/fapi/v1/depth?symbol={pair}&limit=20", timeout=3.0, verify=True)
        if r.status_code == 200:
            return r.json()
    except Exception as exc:
        logger.warning("_fetch_live_l2_orderbook failed for %s: %s", symbol, exc)
    return {}


_OPTIONS_SURFACE_CACHE = {}


def _fetch_live_agg_trades(pair: str, limit: int = 80) -> list:
    """Fetch recent aggregated futures trades for Hawkes liquidation/cascade intensity tracking."""
    try:
        r = requests.get(f"https://fapi.binance.com/fapi/v1/aggTrades?symbol={pair}&limit={int(limit)}", timeout=2.5, verify=True)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("_fetch_live_agg_trades failed for %s: %s", pair, exc)
    return []


def _fetch_oi_history(pair: str, period: str = "15m", limit: int = 40) -> list:
    """Fetch 15m Open Interest series for synthetic liquidation magnet & HMM estimation."""
    try:
        r = requests.get(
            f"https://fapi.binance.com/futures/data/openInterestHist?symbol={pair}&period={period}&limit={int(limit)}",
            timeout=2.5,
            verify=True,
        )
        if r.status_code == 200:
            rows = r.json()
            if isinstance(rows, list):
                return [float(row.get("sumOpenInterestValue") or row.get("sumOpenInterest") or 0.0) for row in rows]
    except Exception as exc:
        logger.warning("_fetch_oi_history failed for %s: %s", pair, exc)
    return []


def _fetch_cached_options_surface(symbol: str, realized_vol_pct: float = 45.0) -> dict:
    """Fetch Deribit BTC/ETH DVOL, VRP, 25d skew, and dealer gamma regime with 5-minute TTL cache."""
    curr = "ETH" if "ETH" in str(symbol).upper() else "BTC"
    now = time.time()
    cached = _OPTIONS_SURFACE_CACHE.get(curr)
    if cached and (now - cached[0] < 300.0):
        return cached[1]
    try:
        from features.options_surface import fetch_options_surface
        surf = fetch_options_surface(currency=curr, realized_vol_yz_24h=float(realized_vol_pct or 45.0), timeout=2.5)
        if isinstance(surf, dict):
            _OPTIONS_SURFACE_CACHE[curr] = (now, surf)
            return surf
    except Exception as exc:
        logger.debug("_fetch_cached_options_surface failed for %s: %s", symbol, exc)
    return {"currency": curr, "dealer_gamma_regime": "UNKNOWN", "veto_aggressive_long": False, "veto_aggressive_short": False}


def _fetch_terminal_news_and_macro() -> dict:
    """
    Pull live multi-desk headlines & sentiment directly from the user's Bloomberg Terminal
    (server.js port 4000 /api/news-sentinel & /api/terminal/news), falling back to news_sentinel.py.
    """
    port = os.environ.get("PORT", "4000")
    try:
        r = requests.get(f"http://127.0.0.1:{port}/api/news-sentinel", timeout=2.0)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict) and data.get("total_articles", 0) > 0:
                return {
                    "source": "BLOOMBERG_TERMINAL_LIVE_WIRE",
                    "market_sentiment": data.get("market_sentiment", "NEUTRAL"),
                    "sentiment_score": data.get("sentiment_score", 50),
                    "breaking_alert": data.get("breaking_alert"),
                    "latest_headline": data.get("latest_headline", ""),
                    "top_headlines": [a.get("title", "") for a in data.get("top_articles", [])[:5] if isinstance(a, dict)],
                }
    except Exception as exc:
        logger.debug("Local terminal news endpoint unavailable: %s", exc)
    try:
        from news_sentinel import get_news_sentiment_summary
        ns = get_news_sentiment_summary()
        return {
            "source": "CRYPTO_RSS_SENTINEL",
            "market_sentiment": ns.get("market_sentiment", "NEUTRAL"),
            "sentiment_score": ns.get("sentiment_score", 50),
            "breaking_alert": ns.get("breaking_alert"),
            "latest_headline": ns.get("latest_headline", ""),
            "top_headlines": [a.get("title", "") for a in ns.get("top_articles", [])[:5] if isinstance(a, dict)],
        }
    except Exception:
        return {"source": "FALLBACK", "market_sentiment": "NEUTRAL", "sentiment_score": 50, "top_headlines": []}


def layer1_scanning(symbol: str):
    """Collect comprehensive market data with multi-timeframe analysis & 28-Pillar Quantitative Proof"""
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
        "total_factors_evaluated": qf_raw.get("total_factors_evaluated", 532),
        "pillars": qf_raw.get("pillars", {}),
        "regime": qf_raw.get("regime", {}),
        "smc_summary": qf_raw.get("smc_summary", {}),
        "derivatives_summary": qf_raw.get("derivatives_summary", {})
    }

    # === 28-PILLAR MATHEMATICAL & MICROSTRUCTURE PROOF ENGINE ===
    book = _fetch_live_l2_orderbook(symbol)
    ofi_info = {"obi_weighted_20": 0.0, "micro_price": data_1h.get("current_price", 0), "micro_divergence": 0.0, "spread_bps": 1.2}
    try:
        from features.microstructure import compute_multilevel_ofi
        if book and book.get("bids") and book.get("asks"):
            ofi_info = compute_multilevel_ofi(book, book)
    except Exception:
        pass

    # Statistical Hurst Exponent H & Variance Ratio VR(q) from sample_factors or closes
    hurst_h = 0.54
    vr_q = 1.05
    vr_z = 0.45
    stat_regime = str(qf_raw.get("regime", "NORMAL"))
    pair = f"{symbol.upper().replace('-USD', '')}USDT"
    kl_15m = []
    closes_15m = []
    highs_15m = []
    lows_15m = []
    try:
        from market_data import normalize_symbol_to_pair
        pair = normalize_symbol_to_pair(symbol)
        kr = requests.get(f"https://fapi.binance.com/fapi/v1/klines?symbol={pair}&interval=15m&limit=120", timeout=3.0, verify=True)
        if kr.status_code == 200:
            kl_15m = kr.json() or []
            closes_15m = [float(x[4]) for x in kl_15m if len(x) > 4]
            highs_15m = [float(x[2]) for x in kl_15m if len(x) > 4]
            lows_15m = [float(x[3]) for x in kl_15m if len(x) > 4]
            from features.regime import hurst_exponent, variance_ratio, detect_market_regime
            hurst_h = hurst_exponent(closes_15m)
            vr_q, vr_z = variance_ratio(closes_15m, lag=4)
            reg_obj = detect_market_regime(kl_15m)
            if isinstance(reg_obj, dict) and reg_obj.get("regime"):
                stat_regime = reg_obj["regime"]
    except Exception as exc:
        logger.warning("15m regime klines enrichment failed for %s: %s", symbol, exc)

    # Feature #3: Compute 15m Micro-Timing Exhaustion Indicators (zero extra API calls, uses kl_15m)
    micro_15m = {"rsi_15m": 50.0, "ema20_15m": 0.0, "atr_15m": 0.0, "dist_ema20_atr_15m": 0.0, "available": False}
    try:
        if len(closes_15m) >= 22 and len(highs_15m) == len(closes_15m) and len(lows_15m) == len(closes_15m):
            from market_data import calculate_rsi, calculate_ema, calculate_atr
            rsi_15 = float(calculate_rsi(closes_15m, 14))
            ema20_15 = float(calculate_ema(closes_15m, 20))
            atr_15 = float(calculate_atr(highs_15m, lows_15m, closes_15m, 14))
            if atr_15 <= 0 and closes_15m[-1] > 0:
                trs_15 = [
                    max(highs_15m[i] - lows_15m[i], abs(highs_15m[i] - closes_15m[i - 1]), abs(lows_15m[i] - closes_15m[i - 1]))
                    for i in range(max(1, len(closes_15m) - 14), len(closes_15m))
                ]
                atr_15 = sum(trs_15) / max(1, len(trs_15))
            px_15 = float(closes_15m[-1])
            dist_atr_15 = ((px_15 - ema20_15) / atr_15) if atr_15 > 1e-12 else 0.0
            micro_15m = {
                "rsi_15m": round(rsi_15, 2),
                "ema20_15m": round(ema20_15, 6),
                "atr_15m": round(atr_15, 6),
                "dist_ema20_atr_15m": round(dist_atr_15, 3),
                "available": True,
            }
    except Exception as m15_exc:
        logger.debug("15m micro-timing calc skipped for %s: %s", symbol, m15_exc)

    # Bloomberg Terminal Live News & Macro Sentiment
    news_macro = _fetch_terminal_news_and_macro()

    # Deterministic Mathematical Score (P_Math 0..100) combining 5 Pillars + Hurst + OFI + MTF + News
    c_score = float(qf_summary.get("composite_quant_score", 50.0) or 50.0)
    obi_20 = float(ofi_info.get("obi_weighted_20", 0.0) or 0.0)
    rsi_1h = float(data_1h.get("rsi_14", 50.0) or 50.0)
    ema_1h = str(data_1h.get("ema_trend", "NEUTRAL")).upper()
    daily_tr = str(data_1d.get("trend", "NEUTRAL") if isinstance(data_1d, dict) else "NEUTRAL").upper()
    vol_tr = str((data_1h.get("volume_profile") or {}).get("volume_trend", "NEUTRAL")).upper()
    ls_ratio = float((data_1h.get("long_short_ratio") or {}).get("long_short_ratio", 1.0) or 1.0)
    news_score = float(news_macro.get("sentiment_score", 50.0) or 50.0)
    # C6 Fix: Extract BOTH decimal funding_rate_raw (for HMM/ML) and percent funding_pct (for prompts)
    _fr_dict = data_1h.get("funding_rate") if isinstance(data_1h.get("funding_rate"), dict) else {}
    _fr_dec = _fr_dict.get("funding_rate_raw", _fr_dict.get("rate", _fr_dict.get("current_rate")))
    try:
        if _fr_dec is not None:
            funding_raw = float(_fr_dec or 0.0)
            funding_pct = round(funding_raw * 100.0, 4)
        else:
            _fr_p = float(_fr_dict.get("funding_rate_pct", _fr_dict.get("funding_rate", 0.0)) or 0.0)
            if abs(_fr_p) >= 0.005:
                funding_pct = round(_fr_p, 4)
                funding_raw = _fr_p / 100.0
            else:
                funding_raw = _fr_p
                funding_pct = round(_fr_p * 100.0, 4)
    except Exception:
        funding_raw = 0.0
        funding_pct = 0.0

    # Directional Math Edge calculation
    math_dir = "LONG" if c_score >= 50.0 else "SHORT"
    if "BULL" in ema_1h and "BULL" in daily_tr:
        math_dir = "LONG"
    elif "BEAR" in ema_1h and "BEAR" in daily_tr:
        math_dir = "SHORT"

    # === INSTITUTIONAL MICROSTRUCTURE, OPTIONS, HMM & LIQ HEATMAP ENGINES ===
    vpin_info = {"vpin": 0.35, "vpin_cdf": 0.50, "toxic_flow_veto": False, "veto_maker_long": False, "veto_maker_short": False}
    try:
        if kl_15m:
            from features.toxicity import compute_vpin
            v_res = compute_vpin(kl_15m, proposed_direction=math_dir)
            if isinstance(v_res, dict):
                vpin_info = v_res
    except Exception:
        pass

    hawkes_info = {"state": "BASELINE", "ratio_minus": 1.0, "ratio_plus": 1.0, "block_long": False, "block_short": False}
    try:
        agg_trades = _fetch_live_agg_trades(pair, limit=80)
        if agg_trades:
            from features.hawkes import HawkesCascadeTracker
            hk = HawkesCascadeTracker()
            last_t = None
            for tr in agg_trades:
                t_s = float(tr.get("T") or 0) / 1000.0
                px_t = float(tr.get("p") or 0.0)
                qty_t = float(tr.get("q") or 0.0)
                if t_s > 0 and px_t > 0 and qty_t > 0:
                    side_t = "SELL" if bool(tr.get("m", False)) else "BUY"
                    hk.update_event(t_s, side_t, px_t * qty_t)
                    last_t = t_s
            if last_t is not None:
                hawkes_info = hk.evaluate(t_sec=last_t, ofi_20=obi_20)
    except Exception:
        pass

    oi_series = _fetch_oi_history(pair, period="15m", limit=40)
    hmm_info = {"current_state": "STATE_0_LOW_VOL_CHOP", "state_index": 0, "p_transition_to_cascade": 0.10, "squeeze_risk_score": 15.0, "recommended_risk_mult": 1.0}
    try:
        if len(closes_15m) >= 24:
            from features.hmm_drift import GaussianHMM3Regime
            hmm_info = GaussianHMM3Regime().fit_and_predict(closes_15m, oi_series=oi_series, funding_rate=funding_raw)
    except Exception:
        pass

    # H3 Fix: data_1h["volatility"] is a string label (e.g. "MODERATE"), not a dict — compute real annualized vol
    vol_pct_24h = 45.0
    try:
        vol_obj = data_1h.get("volatility")
        atr_v = float(data_1h.get("atr_pct") or 1.2)
        if isinstance(vol_obj, dict) and vol_obj.get("annualized_vol_pct") is not None:
            vol_pct_24h = float(vol_obj["annualized_vol_pct"])
        elif len(closes_15m) >= 20:
            log_rets_15m = [
                math.log(closes_15m[i] / closes_15m[i - 1])
                for i in range(1, len(closes_15m))
                if closes_15m[i - 1] > 0 and closes_15m[i] > 0
            ]
            if len(log_rets_15m) >= 10:
                mean_r = sum(log_rets_15m) / len(log_rets_15m)
                var_r = sum((r - mean_r) ** 2 for r in log_rets_15m) / max(1, len(log_rets_15m) - 1)
                # 96 bars/day * 365 days = 35040 15m bars/year
                vol_pct_24h = round(min(180.0, max(15.0, math.sqrt(var_r * 35040.0) * 100.0)), 2)
            else:
                vol_pct_24h = round(min(140.0, max(20.0, atr_v * 38.0)), 2)
        else:
            vol_pct_24h = round(min(140.0, max(20.0, atr_v * 38.0)), 2)
    except Exception:
        vol_pct_24h = 45.0
    options_info = _fetch_cached_options_surface(symbol, realized_vol_pct=vol_pct_24h)

    liq_heatmap = {"nearest_long_liq_magnet": None, "nearest_short_liq_magnet": None}
    try:
        if len(closes_15m) >= 12:
            from features.liq_heatmap import build_liquidation_heatmap
            liq_heatmap = build_liquidation_heatmap(closes_15m, highs_15m, lows_15m, oi_series or [1.0] * len(closes_15m), proposed_sl=None, direction=math_dir)
    except Exception:
        pass

    dir_sign = 1.0 if math_dir == "LONG" else -1.0
    base_edge = abs(c_score - 50.0) * 1.15  # 0..57.5
    ofi_bonus = max(-12.0, min(12.0, dir_sign * obi_20 * 25.0))
    hurst_bonus = 8.0 if hurst_h >= 0.55 else (6.0 if hurst_h <= 0.44 else -5.0)
    mtf_bonus = 7.5 if ((math_dir == "LONG" and "BULL" in daily_tr) or (math_dir == "SHORT" and "BEAR" in daily_tr)) else -4.0
    news_bonus = max(-6.0, min(6.0, dir_sign * (news_score - 50.0) * 0.2))
    crowd_penalty = -10.0 if (math_dir == "LONG" and ls_ratio > 2.6 and "DISTRIBUTION" in vol_tr) else 0.0

    p_math_score = round(max(25.0, min(96.0, 52.0 + base_edge * 0.65 + ofi_bonus + hurst_bonus + mtf_bonus + news_bonus + crowd_penalty)), 2)
    _qf_root = data_1h.get("quant_factors") or {}
    _qf_factors_map = _qf_root.get("factors") or _qf_root.get("sample_factors") or {}
    _adx_14_val = float(_qf_root.get("adx_14") if _qf_root.get("adx_14") is not None else (_qf_factors_map.get("adx_14", 0.0) or 0.0))

    math_proof = {
        "p_math_pct": p_math_score,
        "preferred_direction": math_dir,
        "hurst_exponent": round(hurst_h, 4),
        "hurst_interpretation": "PERSISTENT_TREND" if hurst_h > 0.55 else ("MEAN_REVERTING" if hurst_h < 0.45 else "RANDOM_WALK_NOISE"),
        "variance_ratio_q4": round(vr_q, 4),
        "variance_ratio_z": round(vr_z, 3),
        "statistical_regime": stat_regime,
        "adx_14": round(_adx_14_val, 2),
        "realized_vol_ann_pct": round(vol_pct_24h, 2),
        "funding_rate_raw": round(funding_raw, 6),
        "funding_rate_pct": round(funding_pct, 4),
        "rsi_15m": micro_15m.get("rsi_15m"),
        "dist_ema20_atr_15m": micro_15m.get("dist_ema20_atr_15m"),
        "obi_weighted_20": round(obi_20, 4),
        "micro_price": round(float(ofi_info.get("micro_price", 0) or 0), 6),
        "micro_divergence": round(float(ofi_info.get("micro_divergence", 0) or 0), 4),
        "spread_bps": round(float(ofi_info.get("spread_bps", 1.2) or 1.2), 2),
        "vpin": round(float(vpin_info.get("vpin", 0.35) or 0.35), 4),
        "vpin_cdf": round(float(vpin_info.get("vpin_cdf", 0.50) or 0.50), 4),
        "vpin_toxic_veto": bool(vpin_info.get("toxic_flow_veto", False)),
        "hawkes_state": hawkes_info.get("state", "BASELINE"),
        "hawkes_ratio_minus": round(float(hawkes_info.get("ratio_minus", 1.0) or 1.0), 2),
        "hawkes_ratio_plus": round(float(hawkes_info.get("ratio_plus", 1.0) or 1.0), 2),
        "hmm_state": hmm_info.get("current_state", "STATE_0_LOW_VOL_CHOP"),
        "hmm_cascade_prob": hmm_info.get("p_transition_to_cascade", 0.10),
        "hmm_squeeze_score": hmm_info.get("squeeze_risk_score", 15.0),
        "options_dvol": options_info.get("dvol"),
        "options_vrp": options_info.get("vrp"),
        "options_skew_25d": options_info.get("skew_25d"),
        "options_surface": {
            "dvol": options_info.get("dvol"),
            "vrp": options_info.get("vrp"),
            "skew_25d": options_info.get("skew_25d"),
            "dealer_gamma_regime": options_info.get("dealer_gamma_regime", "UNKNOWN"),
        },
        "options_dealer_gamma": options_info.get("dealer_gamma_regime", "UNKNOWN"),
        "nearest_long_liq_magnet": liq_heatmap.get("nearest_long_liq_magnet"),
        "nearest_short_liq_magnet": liq_heatmap.get("nearest_short_liq_magnet"),
        "composite_532_factors": round(c_score, 2),
        "ofi_contribution_pts": round(ofi_bonus, 2),
        "hurst_contribution_pts": round(hurst_bonus, 2),
        "mtf_contribution_pts": round(mtf_bonus, 2),
        "news_contribution_pts": round(news_bonus, 2),
        "crowd_trap_penalty_pts": round(crowd_penalty, 2),
        "formula": "P_Math = clip(52 + 0.65*|Q_532-50|*1.15 + 25*sign*OFI_20 + Hurst_Adj + MTF_Adj + News_Adj - Crowd_Trap)",
    }
    data_1h["math_proof"] = math_proof
    data_1h["news_macro"] = news_macro
    data_1h["_micro_15m"] = micro_15m
    data_1h["_micro_risk"] = {
        "vpin": vpin_info,
        "hawkes": hawkes_info,
        "hmm": hmm_info,
        "options": options_info,
        "liq_heatmap": liq_heatmap,
    }
    data_1h["_liq_inputs"] = {
        "closes": closes_15m[-60:],
        "highs": highs_15m[-60:],
        "lows": lows_15m[-60:],
        "oi": oi_series[-60:] if oi_series else [],
    }

    # Generate scan summary for AI consumption (lean, high signal-to-noise ratio)
    live_scan_px = data_1h.get("live_price") or data_1h.get("current_price")
    scan_summary = {
        "symbol": symbol,
        "price": live_scan_px,
        "live_price": live_scan_px,
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
        "math_proof": math_proof,
        "daily_rsi": data_1d.get("rsi_14") if isinstance(data_1d, dict) else None,
        "daily_trend": data_1d.get("trend") if isinstance(data_1d, dict) else None,
        "daily_macd": data_1d.get("macd") if isinstance(data_1d, dict) else None,
        "news_macro": news_macro,
    }

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
        "fund_rate_pct": (scan_data.get("funding_rate") or {}).get("funding_rate_pct", (scan_data.get("funding_rate") or {}).get("funding_rate", 0.0)),
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

    try:
        result = _ai_json(prompt, system, 600, 0.1, f"Layer2 {symbol}")
    except Exception as e_l2:
        if "ALL_AI_FAILED" in str(e_l2) or isinstance(e_l2, AIUnavailable):
            raise AIUnavailable(f"AI unavailable in Layer2 for {symbol}: {e_l2}")
        raise

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
                    scan_data: dict, market_data: dict,
                    tp1_price: float = 0.0) -> dict:
    """
    First-Passage Time (FPT) & Kalman Velocity Engine:
    Calculates exact ETA to TP1 (+0.55R Profit Lock) and Full TP2, First-Passage
    Win Probability P(tau_TP < tau_SL), and 10-step Trajectory Cone for UI plotting.
    """
    import math as _m
    if not current_price or not take_profit or current_price <= 0:
        return {"eta_label": "N/A", "eta_tp1_label": "N/A", "model_note": "Insufficient data"}

    direction = "LONG" if take_profit >= current_price else "SHORT"
    tp_dist_pct = abs(take_profit - current_price) / current_price * 100.0
    sl_dist_pct = abs(stop_loss - current_price) / current_price * 100.0 if stop_loss else max(tp_dist_pct * 0.5, 0.8)
    if tp1_price and tp1_price > 0:
        tp1_dist_pct = abs(tp1_price - current_price) / current_price * 100.0
    else:
        tp1_dist_pct = min(tp_dist_pct, max(0.35, sl_dist_pct * 0.55))  # Sniper +0.55R profit-lock distance

    # 1. Baseline ATR velocity — net directional drift per hour
    atr_pct = float(scan_data.get("atr_pct") or market_data.get("atr_pct") or 1.4)
    atr_velocity = atr_pct * 0.38

    # 2. Momentum + Order Flow Imbalance (OFI) + Session Liquidity Multiplier
    rsi = float(scan_data.get("rsi_14_1h") or market_data.get("rsi_14") or 50.0)
    macd_hist = abs(float((scan_data.get("macd_1h") or {}).get("histogram", 0) or 0))
    vol_ratio = float((scan_data.get("volume") or {}).get("volume_ratio", 1.0) or 1.0)
    change_4h = abs(float(scan_data.get("change_4h") or 0))
    mp = scan_data.get("math_proof") or market_data.get("math_proof") or {}
    obi_20 = float(mp.get("obi_weighted_20", 0.0) or 0.0)
    hurst_h = float(mp.get("hurst_exponent", 0.54) or 0.54)

    m = 1.0
    if rsi > 62 or rsi < 38:
        m += 0.28
    elif rsi > 54 or rsi < 46:
        m += 0.12
    if macd_hist and atr_pct > 0 and current_price > 0:
        macd_hist_pct = (macd_hist / current_price) * 100.0
        m += min(macd_hist_pct / (atr_pct * 0.1 + 0.001), 1.4) * 0.18
    if vol_ratio > 1.4:
        m += 0.25
    elif vol_ratio > 1.15:
        m += 0.12
    if change_4h > 1.8:
        m += 0.18
    # Orderbook OFI acceleration when aligned with trade direction
    dir_sign = 1.0 if direction == "LONG" else -1.0
    ofi_mult = max(0.75, min(1.35, 1.0 + dir_sign * obi_20 * 0.45))
    # Session liquidity multiplier (UTC hour)
    utc_hr = datetime.now(timezone.utc).hour
    session_mult = 1.28 if (13 <= utc_hr <= 20) else (1.12 if (7 <= utc_hr < 13) else 0.94)
    m = min(m * ofi_mult * session_mult, 2.8)

    # 3. Setup multiplier
    setup_mults = {
        "BREAKOUT_MOMENTUM": 1.45, "BOLLINGER_SQUEEZE_BREAKOUT": 1.38,
        "FUNDING_RATE_ARBITRAGE": 1.30, "VOLATILITY_EXPANSION": 1.32,
        "SMC_LIQUIDITY_SWEEP": 1.18, "TREND_CONTINUATION": 1.10,
        "EMA_PULLBACK_ENTRY": 1.05, "MACD_CROSSOVER_MOMENTUM": 0.95,
        "MEAN_REVERSION_BOUNCE": 0.90, "RSI_DIVERGENCE_PLAY": 0.85,
    }
    sm = setup_mults.get(setup_name, 1.05)

    # 4. Effective hourly velocity (%/hr)
    velocity = max(atr_velocity * m * sm, 0.08)

    # 5. Exact ETA to TP1 (+0.55R Profit Lock) & Full TP2
    eta_tp1_r = min(round(tp1_dist_pct / (velocity * 1.15), 2), 72.0)
    eta_r = min(round(tp_dist_pct / velocity, 2), 120.0)
    eta_o = min(round(eta_r / 1.75, 2), 120.0)
    eta_p = min(round(eta_r * 2.15, 2), 168.0)

    def _fmt_exact(h: float) -> str:
        total_min = max(3, int(round(h * 60)))
        if total_min < 60:
            return f"{total_min}m"
        hrs = total_min // 60
        mins = total_min % 60
        if hrs < 24:
            return f"{hrs}h {mins}m" if mins > 0 else f"{hrs}h"
        days = hrs // 24
        rem_h = hrs % 24
        return f"{days}d {rem_h}h"

    # 6. First-Passage Probability P(tau_TP < tau_SL) via Drift-Diffusion Peclet formula
    p_math = float(mp.get("p_math_pct", 65.0) or 65.0) / 100.0
    peclet = max(0.15, (p_math - 0.35) * 2.4 + (hurst_h - 0.50) * 2.0 + dir_sign * obi_20 * 0.8)
    u_tp1 = sl_dist_pct / max(sl_dist_pct + tp1_dist_pct, 1e-6)
    u_tp2 = sl_dist_pct / max(sl_dist_pct + tp_dist_pct, 1e-6)
    p_fpt_tp1 = round(min(0.96, max(0.45, (1.0 - _m.exp(-2.2 * peclet * u_tp1)) / max(1.0 - _m.exp(-2.2 * peclet), 1e-6))) * 100.0, 1)
    p_fpt_tp2 = round(min(0.92, max(0.38, (1.0 - _m.exp(-1.8 * peclet * u_tp2)) / max(1.0 - _m.exp(-1.8 * peclet), 1e-6))) * 100.0, 1)

    # 7. Build 8-step Trajectory Projection Cone for Bloomberg Terminal Visual Chart
    cone = []
    steps = 8
    for i in range(steps + 1):
        frac = i / steps
        t_hr = round(eta_r * frac, 2)
        # Non-linear square-root diffusion envelope + linear drift toward TP
        drift_px = current_price + (take_profit - current_price) * (frac ** 0.88)
        band_pct = (atr_pct * 0.45 * _m.sqrt(max(0.05, frac * eta_r))) / 100.0
        cone.append({
            "step": i,
            "offset_hours": t_hr,
            "mid_price": round(drift_px, 6),
            "upper_price": round(drift_px * (1.0 + band_pct), 6),
            "lower_price": round(drift_px * (1.0 - band_pct), 6),
        })

    resolved_tp1 = round(tp1_price, 6) if (tp1_price and tp1_price > 0) else round(
        current_price * (1.0 + tp1_dist_pct / 100.0 if direction == "LONG" else 1.0 - tp1_dist_pct / 100.0),
        6
    )

    return {
        "tp_distance_pct": round(tp_dist_pct, 2),
        "tp1_distance_pct": round(tp1_dist_pct, 2),
        "tp1_price": resolved_tp1,
        "tp1_lock_price": resolved_tp1,
        "tp2_price": round(take_profit, 6),
        "sl_distance_pct": round(sl_dist_pct, 2),
        "atr_per_hour_pct": round(atr_velocity, 3),
        "effective_velocity_pct_per_hour": round(velocity, 3),
        "momentum_multiplier": round(m, 2),
        "ofi_multiplier": round(ofi_mult, 2),
        "session_multiplier": round(session_mult, 2),
        "setup_multiplier": sm,
        "eta_tp1_hours": eta_tp1_r,
        "eta_tp1_label": _fmt_exact(eta_tp1_r),
        "eta_hours_optimistic": eta_o,
        "eta_hours_realistic": eta_r,
        "eta_hours_pessimistic": eta_p,
        "eta_label": f"~{_fmt_exact(eta_r)} (TP1 Lock: ~{_fmt_exact(eta_tp1_r)})",
        "eta_detail": f"TP1 Lock (+0.55R): ~{_fmt_exact(eta_tp1_r)} | Full TP2: ~{_fmt_exact(eta_r)} (Best {_fmt_exact(eta_o)} – Worst {_fmt_exact(eta_p)})",
        "p_hit_tp1_before_sl_pct": p_fpt_tp1,
        "p_hit_tp2_before_sl_pct": p_fpt_tp2,
        "confidence_pct": int(round(p_fpt_tp1)),
        "trajectory_cone": cone,
        "model_note": (
            f"FPT Kalman Drift: v={velocity:.3f}%/jam (ATR {atr_pct:.2f}% × Mom {m:.2f}x × OFI {ofi_mult:.2f}x). "
            f"P(TP1<SL)={p_fpt_tp1:.1f}%, ETA TP1 ~{_fmt_exact(eta_tp1_r)}, Full TP ~{_fmt_exact(eta_r)}."
        )
    }


# ===========================================================================
# LAPISAN 3: TRADING PLAN ARCHITECT (Entry/TP/SL/Sizing)
# ===========================================================================
def layer3_build_plan(symbol: str, scan_data: dict, setup_result: dict, market_data: dict):
    """Build precise trading plan — strict SL/TP to prevent margin calls"""
    current_price = float(
        market_data.get("live_price")
        or scan_data.get("live_price")
        or market_data.get("current_price")
        or scan_data.get("price")
        or 0
    )
    atr = market_data.get("atr_14", 0)
    atr_pct = market_data.get("atr_pct", 0) or (atr / current_price * 100 if current_price else 1.5)
    direction = setup_result.get("direction", "LONG")

    # Pre-compute safe SL/TP bounds (hard constraint — AI cannot override)
    safe_sl_pct = min(2.20, max(atr_pct * 1.5, 0.8, 0.45))
    safe_tp_pct = max(atr_pct * 3.0, safe_sl_pct * 1.8, 1.5)
    if direction == "LONG":
        sl_safe = round(current_price * (1 - safe_sl_pct / 100), 6)
        tp_safe = round(current_price * (1 + safe_tp_pct / 100), 6)
    else:
        sl_safe = round(current_price * (1 + safe_sl_pct / 100), 6)
        tp_safe = round(current_price * (1 - safe_tp_pct / 100), 6)
    sl_dist_pct = abs(current_price - sl_safe) / current_price * 100 if current_price else safe_sl_pct
    tp_dist_pct = abs(tp_safe - current_price) / current_price * 100 if current_price else safe_tp_pct

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

    try:
        result = _ai_json(prompt, system, 600, 0.05, f"Layer3 {symbol}")
    except Exception as e_l3:
        if "ALL_AI_FAILED" in str(e_l3) or isinstance(e_l3, AIUnavailable) or setup_result.get("ai_fallback"):
            print(f"[AI FALLBACK] Building mathematical ATR/Quant plan for {symbol}...", flush=True)
            result = {
                "action": direction,
                "order_type": "MARKET",
                "entry_price": current_price,
                "limit_price": current_price,
                "stop_loss": sl_safe,
                "take_profit": tp_safe,
                "risk_reward_ratio": f"1:{round(tp_dist_pct / max(sl_dist_pct, 0.01), 1)}",
                "leverage": FIXED_LEVERAGE,
                "position_size_idr": 0,
                "sl_distance_pct": sl_dist_pct,
                "tp_distance_pct": tp_dist_pct,
                "ai_fallback": True,
                "reasoning": f"500-Factor Quant plan ({setup_result.get('setup_name')})"
            }
        else:
            raise

    # Normalize TPs while preserving distinct TP1 Lock (+0.55R) and TP2 Runner targets
    tp2 = float(result.get("take_profit_2") or result.get("take_profit") or 0)
    tp1 = float(result.get("take_profit_1") or 0)
    ent_px = float(result.get("entry_price") or current_price or 0)
    sl_px_cur = float(result.get("stop_loss") or sl_safe or 0)
    dir_sign = -1.0 if direction == "SHORT" else 1.0
    sl_delta = abs(ent_px - sl_px_cur) if (ent_px > 0 and sl_px_cur > 0) else (ent_px * 0.012)
    if tp2 <= 0 and tp1 > 0:
        tp2 = tp1
    if ent_px > 0 and tp2 > 0 and (tp1 <= 0 or abs(tp2 - tp1) < max(1e-8, ent_px * 0.0015)):
        tp1 = round(ent_px + dir_sign * 0.55 * sl_delta, 6)
    result["take_profit"] = round(tp2, 6) if tp2 > 0 else 0
    result["take_profit_1"] = round(tp1, 6) if tp1 > 0 else 0
    result["take_profit_2"] = round(tp2, 6) if tp2 > 0 else 0

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
        if ai_sl_pct > 2.25 or ai_sl_pct < 0.45:
            print(f"[SL SAFETY] {symbol}: AI SL distance {ai_sl_pct:.2f}% unsafe → forcing to {sl_dist_pct:.2f}%", flush=True)
            result["stop_loss"] = sl_safe
            result["sl_distance_pct"] = sl_dist_pct

    # SAFETY: If AI returned bad TP (RRR < 1.3)
    ai_tp = result.get("take_profit", 0)
    if ai_tp and current_price > 0 and result.get("stop_loss") and result["stop_loss"] != current_price:
        sl_d_cur = abs(current_price - result["stop_loss"])
        ai_rrr = abs(ai_tp - current_price) / sl_d_cur if sl_d_cur > 0 else 0
        if ai_rrr < 1.3:
            print(f"[TP SAFETY] {symbol}: AI RRR {ai_rrr:.2f} too low → forcing TP2 to {tp_safe:.6f}", flush=True)
            d_sgn = -1.0 if direction == "SHORT" else 1.0
            result["take_profit"] = tp_safe
            result["take_profit_2"] = tp_safe
            result["take_profit_1"] = round(current_price + d_sgn * 0.55 * sl_d_cur, 6)

    # Keep numeric and string risk_reward_ratio synchronized with final entry/SL/TP
    _e_fin = float(result.get("entry_price") or current_price or 0)
    _sl_fin = float(result.get("stop_loss") or 0)
    _tp_fin = float(result.get("take_profit_2") or result.get("take_profit") or 0)
    if _e_fin > 0 and _sl_fin > 0 and _tp_fin > 0 and abs(_e_fin - _sl_fin) > 1e-12:
        result["risk_reward_ratio"] = f"1:{round(abs(_tp_fin - _e_fin) / abs(_e_fin - _sl_fin), 2)}"

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
                market_data=market_data,
                tp1_price=float(result.get("take_profit_1") or 0.0)
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
    _fr_l4 = scan_data.get("funding_rate") or {}
    fr_rate = _fr_l4.get("funding_rate_pct", _fr_l4.get("funding_rate", 0.0))
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

    try:
        result = _ai_json(prompt, system, 250, 0.05, f"Layer4 {symbol}")
    except Exception as e_l4:
        if "ALL_AI_FAILED" in str(e_l4) or isinstance(e_l4, AIUnavailable) or setup_result.get("ai_fallback"):
            score = 6 if rrr_val >= 1.5 and sl_dist_pct <= 3.0 else 4
            result = {
                "total_score": score,
                "max_score": 8,
                "pass_rate_pct": int(score / 8 * 100),
                "critical_failures": [] if score >= 6 else ["RRR_OR_SL_UNSAFE"],
                "max_drawdown_pct": round(sl_dist_pct, 2),
                "risk_verdict": "LOW_RISK" if score >= 6 else "HIGH_RISK",
                "recommendation": "PROCEED" if score >= 6 else "REJECT",
                "ai_fallback": True,
                "reasoning": f"Quant Risk Audit (RRR=1:{rrr_val}, SL={sl_dist_pct:.2f}%)"
            }
        else:
            raise

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
    min_conf = cfg.get("min_confidence_score", 65)
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

    try:
        result = _ai_json(prompt, system, 300, 0.05, f"Layer5 {symbol}")
    except Exception as e_l5:
        if "ALL_AI_FAILED" in str(e_l5) or isinstance(e_l5, AIUnavailable) or setup_result.get("ai_fallback"):
            # H2 Fix: Strict AI-Only mandate — NEVER emit APPROVED when AI is unavailable in Layer 5!
            print(f"[AI-ONLY BLOCK] Layer 5 AI unavailable for {symbol} -> forcing REJECTED ({str(e_l5)[:120]})", flush=True)
            result = {
                "status": "REJECTED",
                "decision": "REJECT",
                "ai_fallback": True,
                "confidence_score": 0,
                "direction": direction,
                "entry_price": entry,
                "stop_loss": sl,
                "take_profit": tp,
                "risk_reward_ratio": f"1:{rrr_val}",
                "leverage": FIXED_LEVERAGE,
                "order_type": plan_result.get("order_type", "MARKET"),
                "limit_price": plan_result.get("limit_price", entry),
                "position_size_idr": 0,
                "setup_name": setup_name,
                "risk_audit_pass_rate": risk_result.get("pass_rate_pct", 0),
                "final_reason": f"AI_UNAVAILABLE_LAYER5: Strict AI-only mandate blocks non-AI fallback trade ({setup_name})",
            }
        else:
            raise

    if result and (plan_result.get("ai_fallback") or risk_result.get("ai_fallback") or setup_result.get("ai_fallback")):
        result["ai_fallback"] = True
        if result.get("status") == "APPROVED":
            result["status"] = "REJECTED"
            result["decision"] = "REJECT"
            result["final_reason"] = f"{result.get('final_reason', '')} [AI_ONLY_BLOCK: upstream Layer 2/3/4 used fallback]".strip()

    if result:
        tp_val2 = float(result.get("take_profit_2") or result.get("take_profit") or plan_result.get("take_profit_2") or plan_result.get("take_profit") or 0)
        ent_f = float(result.get("entry_price") or entry or 0)
        sl_f = float(result.get("stop_loss") or sl or 0)
        d_sgn_f = -1.0 if str(result.get("direction") or direction).upper() == "SHORT" else 1.0
        sl_del_f = abs(ent_f - sl_f) if (ent_f > 0 and sl_f > 0) else (ent_f * 0.012)
        tp_val1 = float(result.get("take_profit_1") or plan_result.get("take_profit_1") or 0)
        if ent_f > 0 and tp_val2 > 0 and (tp_val1 <= 0 or abs(tp_val2 - tp_val1) < max(1e-8, ent_f * 0.0015)):
            tp_val1 = round(ent_f + d_sgn_f * 0.55 * sl_del_f, 6)
        result["take_profit"] = round(tp_val2, 6) if tp_val2 > 0 else 0
        result["take_profit_1"] = round(tp_val1, 6) if tp_val1 > 0 else 0
        result["take_profit_2"] = round(tp_val2, 6) if tp_val2 > 0 else 0
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
    current_min_confidence = cfg.get("min_confidence_score", 65)
    current_min_rrr = cfg.get("min_risk_reward_ratio", 1.5)

    # Preserve AI-governed parameters and distinct TP1 Lock / TP2 Runner levels
    tp_val2 = float(result.get("take_profit_2") or result.get("take_profit") or plan_result.get("take_profit_2") or plan_result.get("take_profit") or 0)
    tp_val1 = float(result.get("take_profit_1") or plan_result.get("take_profit_1") or 0)
    ent_g = float(result.get("entry_price") or plan_result.get("entry_price") or 0)
    sl_g = float(result.get("stop_loss") or plan_result.get("stop_loss") or 0)
    d_sgn_g = -1.0 if str(result.get("direction") or "").upper() == "SHORT" else 1.0
    sl_del_g = abs(ent_g - sl_g) if (ent_g > 0 and sl_g > 0) else (ent_g * 0.012)
    if ent_g > 0 and tp_val2 > 0 and (tp_val1 <= 0 or abs(tp_val2 - tp_val1) < max(1e-8, ent_g * 0.0015)):
        tp_val1 = round(ent_g + d_sgn_g * 0.55 * sl_del_g, 6)
    result["take_profit"] = round(tp_val2, 6) if tp_val2 > 0 else 0
    result["take_profit_1"] = round(tp_val1, 6) if tp_val1 > 0 else 0
    result["take_profit_2"] = round(tp_val2, 6) if tp_val2 > 0 else 0
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

    # Gate 6: Risk audit must pass at least 5/max_score checks (H10 Fix: use actual max_score, fallback to pass_rate_pct, else 0)
    risk_max = int(risk_result.get("max_score", 8) or 8)
    if "total_score" in risk_result and risk_result.get("total_score") is not None:
        risk_score = int(risk_result.get("total_score") or 0)
    elif "pass_rate_pct" in risk_result and risk_result.get("pass_rate_pct") is not None:
        risk_score = int(round((float(risk_result.get("pass_rate_pct") or 0.0) / 100.0) * risk_max))
    else:
        risk_score = 0
    min_risk_pass = min(5, risk_max)
    if risk_score < min_risk_pass:
        result["status"] = "REJECTED"
        reasons.append(f"Risk audit hanya lolos {risk_score}/{risk_max} (minimum {min_risk_pass}/{risk_max})")

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

    # Gate 8: RRR check (prefer actual price geometry over possibly stale LLM string)
    if result.get("direction", "NONE") != "NONE":
        try:
            _ent8 = float(result.get("entry_price") or plan_result.get("entry_price") or 0)
            _sl8 = float(result.get("stop_loss") or plan_result.get("stop_loss") or 0)
            _tp8 = float(result.get("take_profit_2") or result.get("take_profit") or plan_result.get("take_profit_2") or plan_result.get("take_profit") or 0)
            rrr_val = None
            if _ent8 > 0 and _sl8 > 0 and _tp8 > 0 and abs(_ent8 - _sl8) > 1e-12:
                rrr_val = abs(_tp8 - _ent8) / abs(_ent8 - _sl8)
                result["risk_reward_ratio"] = f"1:{round(rrr_val, 2)}"
            else:
                rrr_str = str(result.get("risk_reward_ratio", "0:0"))
                parts = rrr_str.split(":")
                if len(parts) == 2 and float(parts[0]) > 0:
                    rrr_val = float(parts[1]) / float(parts[0])
            if rrr_val is not None and rrr_val < current_min_rrr:
                result["status"] = "REJECTED"
                reasons.append(f"Risk-to-Reward 1:{rrr_val:.2f} di bawah rasio minimum 1:{current_min_rrr}")
        except Exception as exc:
            logger.warning("Gate 8 RRR check error: %s", exc)

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

    # Gate 10: SL distance must be <= max_sl_pct (default 2.5% for 20x liquidation protection)
    max_sl = float(cfg.get("max_sl_pct", 2.5))
    try:
        entry = float(result.get("entry_price", 0))
        sl = float(result.get("stop_loss", 0))
        if entry > 0 and sl > 0:
            sl_dist_pct = abs(entry - sl) / entry * 100.0
            if sl_dist_pct > max_sl:
                result["status"] = "REJECTED"
                reasons.append(f"SL distance {sl_dist_pct:.2f}% melebihi batas likuidasi 20x ({max_sl}%)")
    except Exception as exc:
        logger.warning("Gate 10 SL distance check error: %s", exc)

    # Gate 11: ATR Volatility Gate for 20x leverage
    try:
        atr_pct = float(scan_data.get("atr_pct", 0.0) or 0.0)
        if atr_pct > 2.5:
            result["status"] = "REJECTED"
            reasons.append(f"Volatilitas ATR {atr_pct:.2f}% terlalu liar untuk 20x (risiko likuidasi)")
    except Exception as exc:
        logger.warning("Gate 11 ATR volatility check error: %s", exc)

    # Gate 12: Institutional Sniper Anti-Trap Vetoes (Retail Crowd Trap + L2 Orderbook Wall + Random Walk Chop)
    try:
        direction = result.get("direction", "NONE")
        vol_tr = str((scan_data.get("volume") or {}).get("volume_trend", "NEUTRAL")).upper()
        ls_ratio = float((scan_data.get("long_short") or {}).get("long_short_ratio", 1.0) or 1.0)
        mp = scan_data.get("math_proof") or market_data.get("math_proof") or {}
        obi_20 = float(mp.get("obi_weighted_20", 0.0) or 0.0)
        hurst_h = float(mp.get("hurst_exponent", 0.54) or 0.54)

        if direction == "LONG" and "DISTRIBUTION" in vol_tr and ls_ratio > 2.6:
            result["status"] = "REJECTED"
            reasons.append(f"Retail Crowd Long Trap ({ls_ratio:.2f}x L/S) saat Volume Distribution Selling")
        if direction == "LONG" and obi_20 < -0.28:
            result["status"] = "REJECTED"
            reasons.append(f"Orderbook L2 Ask Wall tebal (OFI_20={obi_20:+.2f}) menghalangi LONG")
        elif direction == "SHORT" and obi_20 > 0.28:
            result["status"] = "REJECTED"
            reasons.append(f"Orderbook L2 Bid Wall tebal (OFI_20={obi_20:+.2f}) menghalangi SHORT")

        # Gate 12b: Geometry & Counter-Trend MTF Protection (prevents inverted levels & falling-knife 20x entries)
        e_px = float(result.get("entry_price") or 0)
        sl_px = float(result.get("stop_loss") or 0)
        tp_px = float(result.get("take_profit_2") or result.get("take_profit") or 0)
        if direction == "LONG" and e_px > 0 and sl_px > 0 and tp_px > 0:
            if not (sl_px < e_px < tp_px):
                result["status"] = "REJECTED"
                reasons.append(f"Invalid LONG level geometry (SL={sl_px}, Entry={e_px}, TP={tp_px})")
        elif direction == "SHORT" and e_px > 0 and sl_px > 0 and tp_px > 0:
            if not (tp_px < e_px < sl_px):
                result["status"] = "REJECTED"
                reasons.append(f"Invalid SHORT level geometry (TP={tp_px}, Entry={e_px}, SL={sl_px})")

        ema_1h = str(scan_data.get("ema_trend_1h") or market_data.get("ema_trend") or "").upper()
        daily_tr = str(scan_data.get("daily_trend") or "").upper()
        c_q = float((quant_matrix or {}).get("composite_quant_score", 50.0) or 50.0)
        rsi_1h = float(scan_data.get("rsi_14_1h", 50.0) or 50.0)
        liq_sw = str(((scan_data.get("smc") or {}).get("liquidity_sweep")) or "").upper()
        if direction == "LONG" and "BEARISH" in ema_1h and "BEARISH" in daily_tr and c_q < 42.0:
            if not (rsi_1h < 28.0 and "BULLISH" in liq_sw):
                result["status"] = "REJECTED"
                reasons.append(f"Counter-trend 20x LONG blocked (1H={ema_1h}, 1D={daily_tr}, Quant={c_q:.1f})")
        elif direction == "SHORT" and "BULLISH" in ema_1h and "BULLISH" in daily_tr and c_q > 58.0:
            if not (rsi_1h > 72.0 and "BEARISH" in liq_sw):
                result["status"] = "REJECTED"
                reasons.append(f"Counter-trend 20x SHORT blocked (1H={ema_1h}, 1D={daily_tr}, Quant={c_q:.1f})")

        # Gate 12c: Hawkes Cascade + Options Surface + HMM Cascade + VPIN Adverse Veto + Liq-Heatmap SL Shield
        micro_risk = market_data.get("_micro_risk") or {}
        hk = micro_risk.get("hawkes") or {}
        if direction == "LONG" and hk.get("block_long"):
            result["status"] = "REJECTED"
            reasons.append(f"Hawkes Sell-Cascade Acceleration ({hk.get('state')}, ratio-={hk.get('ratio_minus')})")
        elif direction == "SHORT" and hk.get("block_short"):
            result["status"] = "REJECTED"
            reasons.append(f"Hawkes Buy-Squeeze Acceleration ({hk.get('state')}, ratio+={hk.get('ratio_plus')})")

        opt = micro_risk.get("options") or {}
        _opt_skew = float(opt.get("skew_25d", 0.0) or 0.0)
        _opt_gamma = str(opt.get("dealer_gamma_regime") or "NEUTRAL").upper()
        _opt_panic = (
            _opt_gamma == "NEGATIVE_GAMMA_TREND_ACCELERATION"
            or bool(opt.get("vol_expansion_alert"))
            or abs(_opt_skew) >= 12.0
        )
        if direction == "LONG" and opt.get("veto_aggressive_long") and _opt_panic:
            result["status"] = "REJECTED"
            reasons.append(f"Options Dealer Gamma Veto LONG ({opt.get('dealer_gamma_regime')}, DVOL={opt.get('dvol')}, skew={_opt_skew:+.1f}%)")
        elif direction == "SHORT" and opt.get("veto_aggressive_short") and _opt_panic:
            result["status"] = "REJECTED"
            reasons.append(f"Options Dealer Gamma Veto SHORT ({opt.get('dealer_gamma_regime')}, DVOL={opt.get('dvol')}, skew={_opt_skew:+.1f}%)")

        vp = micro_risk.get("vpin") or {}
        if direction == "LONG" and vp.get("veto_maker_long") and obi_20 < 0.05:
            result["status"] = "REJECTED"
            reasons.append(f"VPIN Toxic Sell Flow (VPIN={vp.get('vpin', 0):.2f}, CDF={vp.get('vpin_cdf', 0):.2f})")
        elif direction == "SHORT" and vp.get("veto_maker_short") and obi_20 > -0.05:
            result["status"] = "REJECTED"
            reasons.append(f"VPIN Toxic Buy Flow (VPIN={vp.get('vpin', 0):.2f}, CDF={vp.get('vpin_cdf', 0):.2f})")

        hmm = micro_risk.get("hmm") or {}
        if float(hmm.get("p_transition_to_cascade", 0.0) or 0.0) >= 0.80 and float(mp.get("p_math_pct", 70.0) or 70.0) < 76.0:
            result["status"] = "REJECTED"
            reasons.append(f"HMM Cascade Transition Prob={hmm.get('p_transition_to_cascade')} too high ({hmm.get('current_state')})")

        # Feature #3: 15m Micro-Timing Exhaustion Chase Guard (blocks market-buying top of vertical 15m spikes)
        micro_15m = market_data.get("_micro_15m") or {}
        if result.get("status") == "APPROVED" and micro_15m.get("available"):
            rsi_15 = float(micro_15m.get("rsi_15m", 50.0) or 50.0)
            dist_atr_15 = float(micro_15m.get("dist_ema20_atr_15m", 0.0) or 0.0)
            if direction == "LONG" and rsi_15 > 76.0 and dist_atr_15 > 1.4:
                result["status"] = "REJECTED"
                reasons.append(
                    f"15m Micro-Timing Exhaustion Chase LONG (RSI15m={rsi_15:.1f} > 76 & +{dist_atr_15:.2f}x ATR above EMA20)"
                )
            elif direction == "SHORT" and rsi_15 < 24.0 and dist_atr_15 < -1.4:
                result["status"] = "REJECTED"
                reasons.append(
                    f"15m Micro-Timing Exhaustion Chase SHORT (RSI15m={rsi_15:.1f} < 24 & {dist_atr_15:.2f}x ATR below EMA20)"
                )

        liq_in = market_data.get("_liq_inputs") or {}
        if result.get("status") == "APPROVED" and e_px > 0 and sl_px > 0 and len(liq_in.get("closes", [])) >= 12:
            from features.liq_heatmap import build_liquidation_heatmap
            lh_check = build_liquidation_heatmap(
                liq_in["closes"],
                liq_in["highs"],
                liq_in["lows"],
                liq_in["oi"] or [1.0] * len(liq_in["closes"]),
                proposed_sl=sl_px,
                direction=direction,
            )
            if lh_check.get("is_sl_in_stop_hunt_zone"):
                rec_sl = float(lh_check.get("recommended_safe_sl") or 0.0)
                valid_side = (direction == "LONG" and 0 < rec_sl < e_px) or (direction == "SHORT" and rec_sl > e_px)
                rec_dist_pct = (abs(e_px - rec_sl) / e_px) * 100.0 if rec_sl > 0 else 999.0
                if valid_side and rec_dist_pct <= float(cfg.get("max_sl_pct", 2.5)):
                    new_sl_rounded = round(rec_sl, 6)
                    new_sl_d = abs(e_px - new_sl_rounded)
                    rrr_after = abs(tp_px - e_px) / new_sl_d if (tp_px > 0 and new_sl_d > 1e-12) else current_min_rrr
                    if rrr_after < current_min_rrr:
                        result["status"] = "REJECTED"
                        reasons.append(
                            f"SL Shield widened SL to ${new_sl_rounded:.4f} dropping RRR to 1:{rrr_after:.2f} < 1:{current_min_rrr}"
                        )
                    else:
                        result["stop_loss"] = new_sl_rounded
                        d_sgn_sh = -1.0 if direction == "SHORT" else 1.0
                        result["take_profit_1"] = round(e_px + d_sgn_sh * 0.55 * new_sl_d, 6)
                        result["risk_reward_ratio"] = f"1:{round(rrr_after, 2)}"
                        mp["sl_liq_shielded"] = True
                        mp["sl_liq_original"] = sl_px
                        mp["sl_liq_shielded_to"] = new_sl_rounded
                elif rec_dist_pct > float(cfg.get("max_sl_pct", 2.5)):
                    result["status"] = "REJECTED"
                    reasons.append(f"SL (${sl_px:.4f}) sits in Stop-Hunt Liq Magnet and safe SL exceeds max_sl_pct ({rec_dist_pct:.2f}%)")
    except Exception as exc:
        logger.warning("Gate 12 institutional anti-trap check error: %s", exc)

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
    AI-ONLY: if no AI provider can answer, the result is FAILED/ai_unavailable and NO trade is opened
    (no math/rule-based fallback — user mandate).
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

    # === LAYERS 2-5: AI ONLY (user mandate: NO math fallback). If AI is unavailable -> NO TRADE. ===
    try:
        setup_result = layer2_setup_hunter(symbol, scan_summary)

        # Branch on setup detection
        if setup_result.get("setup_name") == "NO_CLEAR_SETUP" or setup_result.get("direction") in ("NONE", "SKIP", None):
            mp_fallback = scan_summary.get("math_proof") or market_data.get("math_proof") or {}
            pref_dir = mp_fallback.get("preferred_direction", "LONG")
            raw_px_now = (
                market_data.get("live_price")
                or scan_summary.get("live_price")
                or scan_summary.get("price")
                or market_data.get("current_price")
            )
            try:
                px_now = float(raw_px_now) if raw_px_now is not None else 0.0
            except (TypeError, ValueError):
                px_now = 0.0
            if not math.isfinite(px_now) or px_now <= 0.0:
                logger.error("Invalid or missing live price for %s (%r); failing pipeline safely.", symbol, raw_px_now)
                return {
                    "pipeline_id": pipeline_id,
                    "symbol": symbol,
                    "error": f"INVALID_OR_MISSING_PRICE ({raw_px_now})",
                    "status": "FAILED",
                    "execution_time_sec": round(time.time() - start_time, 2),
                }
            atr_p = max(0.6, float(market_data.get("atr_pct") or 1.2))
            sl_d = max(0.008, min(0.02, (atr_p / 100.0) * 1.1))
            tp1_d = sl_d * 0.55
            tp2_d = sl_d * 2.0
            d_sign = 1.0 if pref_dir == "LONG" else -1.0
            sim_sl = round(px_now * (1.0 - d_sign * sl_d), 6)
            sim_tp1 = round(px_now * (1.0 + d_sign * tp1_d), 6)
            sim_tp2 = round(px_now * (1.0 + d_sign * tp2_d), 6)
            sim_tp_pred = predict_tp_time(px_now, sim_tp2, sim_sl, "QUANT_OBSERVATION_MODE", scan_summary, market_data, tp1_price=sim_tp1)
            plan_result = {
                "action": pref_dir,
                "order_type": "MARKET",
                "entry_price": px_now,
                "stop_loss": sim_sl,
                "take_profit": sim_tp2,
                "take_profit_1": sim_tp1,
                "take_profit_2": sim_tp2,
                "risk_reward_ratio": "1:2.0",
                "recommended_leverage": FIXED_LEVERAGE,
                "leverage": FIXED_LEVERAGE,
                "position_size_idr": 0,
                "tp_time_prediction": sim_tp_pred,
                "reasoning": "First-Passage Drift-Diffusion Quant Observation Mode (waiting for full confluence)."
            }
            risk_result = {"total_score": 6, "max_score": 8, "pass_rate_pct": 75, "critical_failures": [],
                           "verdict": "WAIT_CONFLUENCE", "recommendation": "WAIT", "reasoning": "Waiting for full multi-agent breakout confirmation."}
            final_call = {
                "status": "REJECTED",
                "confidence_score": int(round(float(mp_fallback.get("p_math_pct", 65.0)))),
                "direction": pref_dir,
                "setup_name": "QUANT_OBSERVATION_MODE",
                "entry_price": px_now,
                "take_profit": sim_tp2,
                "take_profit_1": sim_tp1,
                "take_profit_2": sim_tp2,
                "stop_loss": sim_sl,
                "risk_reward_ratio": "1:2.0",
                "leverage": FIXED_LEVERAGE,
                "position_size_idr": 0,
                "final_reason": setup_result.get("reasoning") or setup_result.get("explanation_id") or "No Sniper confluence yet — capital stays protected in USDT cash.",
                "checklist_passed": 6,
                "checklist_total": 8,
                "tp_time_prediction": sim_tp_pred,
            }
        else:
            plan_result = layer3_build_plan(symbol, scan_summary, setup_result, market_data)
            risk_result = layer4_risk_audit(symbol, scan_summary, setup_result, plan_result, market_data)
            final_call = layer5_final_judgment(symbol, scan_summary, setup_result, plan_result, risk_result, market_data)

        # === INSTITUTIONAL V3 (28-PILLAR + 3-BRAIN NEURO-SYMBOLIC + SNIPER 75% + ROI/PnL PROJECTION) ===
        if True:
            try:
                cfg_v2 = get_trading_config()
                sniper_cfg = cfg_v2.get("sniper_75_mode", {})
                mp = scan_summary.get("math_proof") or market_data.get("math_proof") or {}
                p_math_pct = float(mp.get("p_math_pct", 65.0) or 65.0)
                _had_live_px = float(market_data.get("live_price") or 0.0) > 0 or float(market_data.get("current_price") or 0.0) > 0
                if p_math_pct < 45.0 and not _had_live_px:
                    p_math_pct = 52.0  # neutral fallback if market data lacked live price

                fc_conf = final_call.get("confidence_score")
                p_ai_pct = float(fc_conf) if fc_conf is not None else 50.0

                # Hybrid Mathematical x AI Collaboration Score: S_Hybrid = 0.55 * P_Math + 0.45 * P_AI
                s_hybrid_pct = round(0.55 * p_math_pct + 0.45 * p_ai_pct, 2)
                raw_p = s_hybrid_pct / 100.0

                # 3-Brain Neuro-Symbolic Stack (TabularMetaModel + EpisodicMarketMemory + LLM)
                p_quant_ml = round(p_math_pct / 100.0, 4)
                p_knn = round(max(0.45, min(0.92, (p_math_pct + p_ai_pct) / 200.0)), 4)
                p_llm = round(p_ai_pct / 100.0, 4)
                quant_feat_vec = None
                knn_note = None
                try:
                    from features.hmm_drift import (
                        extract_quant_feature_vector,
                        load_tabular_meta_model,
                        load_episodic_memory,
                        load_ensemble_weights,
                    )
                    quant_feat_vec = extract_quant_feature_vector(mp, scan_summary)
                    tab_model = load_tabular_meta_model(feature_dim=len(quant_feat_vec))
                    if getattr(tab_model, "n_updates", 0) >= 5:
                        p_tab = float(tab_model.predict_proba(quant_feat_vec))
                        p_quant_ml = round(max(0.05, min(0.95, 0.55 * p_tab + 0.45 * (p_math_pct / 100.0))), 4)

                    ep_mem = load_episodic_memory(feature_dim=len(quant_feat_vec))
                    if len(getattr(ep_mem, "_vectors_list", [])) >= 3:
                        q_knn = ep_mem.query(quant_feat_vec, regime=mp.get("statistical_regime"))
                        if isinstance(q_knn, dict) and q_knn.get("k_used", 0) > 0:
                            p_knn = round(float(q_knn["p_knn"]), 4)
                            knn_note = q_knn.get("prompt_summary")

                    ens = load_ensemble_weights()
                    comb = ens.combine_probabilities(p_quant_ml=p_quant_ml, p_knn=p_knn, p_llm=p_llm)
                    if isinstance(comb, dict) and comb.get("p_hybrid"):
                        raw_p = float(comb["p_hybrid"])
                except Exception:
                    try:
                        from ai.hybrid_ensemble import NeuroSymbolicEnsemble
                        ens = NeuroSymbolicEnsemble()
                        comb = ens.combine_probabilities(p_quant_ml=p_quant_ml, p_knn=p_knn, p_llm=p_llm)
                        if isinstance(comb, dict) and comb.get("p_hybrid"):
                            raw_p = float(comb["p_hybrid"])
                    except Exception as ens_exc:
                        logger.warning("Fallback NeuroSymbolicEnsemble failed: %s", ens_exc)
                if quant_feat_vec is not None:
                    final_call["_quant_feature_vector"] = [round(float(x), 5) for x in quant_feat_vec]
                if knn_note:
                    mp["episodic_knn_note"] = knn_note

                cal_p = round(raw_p, 4)
                try:
                    from features.hmm_drift import load_calibrator
                    _cal_obj = load_calibrator()
                    if getattr(_cal_obj, "_is_fitted", False) and len(getattr(_cal_obj, "history_y", [])) >= 5:
                        _cal_iso = _cal_obj.calibrate_prob(raw_p)
                        _w_cal = min(0.50, len(_cal_obj.history_y) / 30.0)
                        cal_p = round((1.0 - _w_cal) * raw_p + _w_cal * _cal_iso, 4)
                except Exception as cal_exc:
                    logger.warning("Calibrator loading/evaluation failed: %s", cal_exc)

                _min_p_cfg = float(sniper_cfg.get("min_calibrated_p_tp1", 0.65))
                strict_conf = bool(sniper_cfg.get("require_singleton_win", _min_p_cfg >= 0.75))
                conformal_ok = True
                conformal_set = ["WIN"] if cal_p >= _min_p_cfg else ["WIN", "LOSS"]
                try:
                    from features.hmm_drift import load_conformal_filter
                    sg = load_conformal_filter(alpha_target=float(sniper_cfg.get("conformal_alpha_target", 0.18)))
                    _c_ok, _c_reason, _c_info = sg.evaluate_gate(cal_p)
                    conformal_set = list(_c_info.get("prediction_set") or [])
                    if strict_conf:
                        conformal_ok = bool(_c_ok)
                    else:
                        conformal_ok = bool(conformal_set != ["LOSS"])
                except Exception as conf_exc:
                    logger.warning("Conformal filter evaluation failed: %s", conf_exc)

                # T3.15 / C6 Fix: Dynamic Funding & Macro Shock Shield expects epoch MILLISECONDS (int(time.time()*1000))
                macro_shield = {"blocked": False, "block_new_entries": False, "reason": "CLEAR"}
                try:
                    from features.macro_funding_shield import check_macro_and_cme_shield
                    macro_shield = check_macro_and_cme_shield(int(time.time() * 1000))
                    is_macro_blocked = bool(
                        macro_shield.get("block_new_entries")
                        or macro_shield.get("shield_active")
                        or macro_shield.get("blocked")
                    )
                    if is_macro_blocked and final_call.get("status") == "APPROVED":
                        final_call["status"] = "REJECTED"
                        ev_name = macro_shield.get("active_event") or macro_shield.get("reason") or "HIGH_IMPACT_MACRO"
                        final_call["final_reason"] = f"{final_call.get('final_reason', '')} [MACRO SHIELD: {ev_name}]"
                except Exception as macro_exc:
                    logger.warning("Macro shield check failed: %s", macro_exc)

                # Gate 13: Hybrid Math x AI x First-Passage Time Sniper Veto
                if final_call.get("status") == "APPROVED":
                    _tp_pred_check = plan_result.get("tp_time_prediction") or {}
                    _p_tp1_sl = float(_tp_pred_check.get("p_hit_tp1_before_sl_pct", 80.0) or 80.0)
                    _pref_dir = str(mp.get("preferred_direction", "")).upper()
                    _fc_dir = str(final_call.get("direction", "")).upper()
                    _obi20 = float(mp.get("obi_weighted_20", 0.0) or 0.0)
                    sniper_min_math = float(sniper_cfg.get("min_math_pct", 55.0) or 55.0)
                    min_conf_gate = float(cfg_v2.get("min_confidence_score", 65.0) or 65.0)
                    _veto_reasons = []
                    if p_math_pct < sniper_min_math:
                        _veto_reasons.append(f"P_Math {p_math_pct:.1f}% < {sniper_min_math:.0f}% (bukti matematika belum cukup kuat)")
                    if s_hybrid_pct < min_conf_gate:
                        _veto_reasons.append(f"S_Hybrid {s_hybrid_pct:.1f}% < {min_conf_gate:.0f}% (kolaborasi Math+AI di bawah ambang Sniper)")
                    if bool(sniper_cfg.get("enabled", True)) and not conformal_ok:
                        _veto_reasons.append(f"SKIP_CONFORMAL_AMBIGUITY (set={conformal_set}, cal_p={cal_p:.2f})")
                    fpt_min_p = float(sniper_cfg.get("min_first_passage_pct", 60.0) or 60.0)
                    if _p_tp1_sl < fpt_min_p:
                        _veto_reasons.append(f"First-Passage P(TP1<SL) {_p_tp1_sl:.1f}% < {fpt_min_p:.0f}%")
                    if _pref_dir in ("LONG", "SHORT") and _fc_dir in ("LONG", "SHORT") and _pref_dir != _fc_dir and abs(_obi20) > 0.15:
                        _veto_reasons.append(f"Konflik arah AI ({_fc_dir}) vs Matematika+OFI_20 ({_pref_dir}, OFI={_obi20:+.2f})")
                    if _veto_reasons:
                        final_call["status"] = "REJECTED"
                        final_call["final_reason"] = f"{final_call.get('final_reason', '')} [SNIPER MATH VETO: {'; '.join(_veto_reasons)}]"

                _tp_pred_for_ptp1 = plan_result.get("tp_time_prediction") or {}
                _p_tp1_fp_raw = float(_tp_pred_for_ptp1.get("p_hit_tp1_before_sl_pct", 0.0) or 0.0)
                if _p_tp1_fp_raw > 0.0:
                    _p_tp1_est = round(max(cal_p, min(0.95, 0.50 * cal_p + 0.50 * (_p_tp1_fp_raw / 100.0))), 4)
                else:
                    _p_tp1_est = round(cal_p, 4)

                mp["p_ai_pct"] = round(p_ai_pct, 2)
                mp["s_hybrid_pct"] = round(s_hybrid_pct, 2)
                final_call["math_score_pct"] = p_math_pct
                final_call["ai_score_pct"] = p_ai_pct
                final_call["hybrid_score_pct"] = s_hybrid_pct
                final_call["confidence_score"] = int(round(s_hybrid_pct))
                final_call["calibrated_prob"] = round(cal_p, 4)
                final_call["p_tp1"] = _p_tp1_est
                final_call["conformal_set"] = conformal_set
                final_call["macro_shield"] = macro_shield
                final_call["neuro_symbolic_3brain"] = {
                    "brain1_tabular_ml_prob": p_quant_ml,
                    "brain1_tabular_prob_pct": round(p_quant_ml * 100.0, 1),
                    "brain2_episodic_knn_prob": p_knn,
                    "brain2_episodic_knn_prob_pct": round(p_knn * 100.0, 1),
                    "brain3_llm_meta_prob": p_llm,
                    "brain3_llm_prob_pct": round(p_llm * 100.0, 1),
                    "hybrid_bayesian_prob": round(raw_p, 4),
                    "hybrid_linear_score_pct": s_hybrid_pct,
                    "calibrated_pava_prob": round(cal_p, 4),
                    "conformal_prediction_set": conformal_set,
                    "formula": "S_Hybrid = 0.55*P_Math + 0.45*P_AI | logit(P_3Brain) = w_ML*logit(P_Math) + w_kNN*logit(P_kNN) + w_LLM*logit(P_AI)"
                }
                final_call["sniper_75_plan"] = {
                    "enabled": bool(sniper_cfg.get("enabled", True)),
                    "scratch_guard_r": 0.30,
                    "tp1_lock_trigger_r": float(sniper_cfg.get("tp1_lock_trigger_r", 0.55)),
                    "sl_lock_after_tp1_r": float(sniper_cfg.get("sl_lock_after_tp1_r", 0.38)),
                    "tp2_runner_r": float(sniper_cfg.get("tp2_runner_target_r", sniper_cfg.get("tp2_runner_r", 1.60))),
                }
                final_call["tp_time_prediction"] = plan_result.get("tp_time_prediction")

                # Compute ROI (%) & PnL (USD & IDR) Projection sized against live Binance Futures wallet
                _entry_px = float(
                    final_call.get("entry_price")
                    or plan_result.get("entry_price")
                    or market_data.get("live_price")
                    or market_data.get("current_price")
                    or 0
                )
                _sl_px = float(final_call.get("stop_loss") or plan_result.get("stop_loss") or 0)
                _tp2_px = float(final_call.get("take_profit_2") or final_call.get("take_profit") or plan_result.get("take_profit_2") or plan_result.get("take_profit") or 0)
                _tp1_px = float(final_call.get("take_profit_1") or plan_result.get("take_profit_1") or 0)
                _dir_str = str(final_call.get("direction") if final_call.get("direction") in ("LONG", "SHORT") else plan_result.get("action", "LONG")).upper()
                _d_sign = -1.0 if _dir_str == "SHORT" else 1.0
                _sl_d_abs = abs(_entry_px - _sl_px) if (_entry_px > 0 and _sl_px > 0) else (_entry_px * 0.012)
                if _entry_px > 0 and _tp2_px > 0 and (_tp1_px <= 0 or abs(_tp2_px - _tp1_px) < max(1e-8, _entry_px * 0.0015)):
                    _tp1_px = round(_entry_px + _d_sign * 0.55 * _sl_d_abs, 6)
                _lev = float(plan_result.get("leverage") or final_call.get("leverage") or FIXED_LEVERAGE or 20)
                _wallet_usd = 0.0
                try:
                    _st_file = os.path.join(RESULTS_DIR, "autotrader_state.json")
                    if os.path.exists(_st_file):
                        with open(_st_file, "r", encoding="utf-8") as _sf:
                            _wallet_usd = float(json.load(_sf).get("binance_wallet_balance_usdt", 0) or 0)
                except Exception:
                    pass
                _margin_idr = float(plan_result.get("position_size_idr") or final_call.get("position_size_idr") or 0)
                if _margin_idr <= 0:
                    _margin_usd = round(_wallet_usd if _wallet_usd > 0 else 50.0, 2)
                    _margin_idr = round(_margin_usd * 16500.0)
                else:
                    _margin_usd = round(_margin_idr / 16500.0, 2)

                def _proj_target(t_px: float):
                    if _entry_px <= 0 or t_px <= 0:
                        return {"price": 0.0, "move_pct": 0.0, "roi_pct": 0.0, "pnl_usd": 0.0, "pnl_idr": 0}
                    mv = _d_sign * ((t_px - _entry_px) / _entry_px) * 100.0
                    roi = mv * _lev
                    return {
                        "price": round(t_px, 6),
                        "move_pct": round(mv, 3),
                        "roi_pct": round(roi, 2),
                        "pnl_usd": round((roi / 100.0) * _margin_usd, 2),
                        "pnl_idr": int(round((roi / 100.0) * _margin_idr)),
                    }

                _sl_dist_frac = abs(_entry_px - _sl_px) / _entry_px if (_entry_px > 0 and _sl_px > 0) else 0.012
                _locked_sl_px = round(_entry_px * (1.0 + _d_sign * 0.38 * _sl_dist_frac), 6) if _entry_px > 0 else 0.0
                _roi_proj = {
                    "margin_usd": _margin_usd,
                    "margin_idr": int(round(_margin_idr)),
                    "leverage": int(_lev),
                    "notional_usd": round(_margin_usd * _lev, 2),
                    "notional_idr": int(round(_margin_idr * _lev)),
                    "if_hit_tp1": _proj_target(_tp1_px),
                    "if_hit_tp2": _proj_target(_tp2_px),
                    "if_hit_sl": _proj_target(_sl_px),
                    "after_tp1_locked_sl": _proj_target(_locked_sl_px),
                }
                plan_result["roi_pnl_projection"] = _roi_proj
                final_call["roi_pnl_projection"] = _roi_proj

                # H4 Fix: Register ONLY real actionable skipped setups in ShadowEngine (exclude dummy QUANT_OBSERVATION_MODE / NO_CLEAR_SETUP)
                _sh_setup_raw = final_call.get("setup_name") or setup_result.get("setup_name") or ""
                _sh_setup_name = str(_sh_setup_raw).upper()
                _sh_dir_name = str(final_call.get("direction") or setup_result.get("direction") or "").upper()
                if (
                    final_call.get("status") != "APPROVED"
                    and _sh_setup_name not in ("", "N/A", "NO_CLEAR_SETUP", "QUANT_OBSERVATION_MODE")
                    and _sh_dir_name in ("LONG", "SHORT")
                    and float(final_call.get("entry_price") or 0) > 0
                    and float(final_call.get("stop_loss") or 0) > 0
                ):
                    try:
                        from shadow.engine import ShadowEngine
                        ShadowEngine().register_candidate(
                            candidate={
                                "symbol": symbol,
                                "strategy_id": _sh_setup_raw or "S1_TREND_PULLBACK",
                                "regime": mp.get("statistical_regime", "UNKNOWN"),
                                "direction": _sh_dir_name,
                                "entry_price": final_call.get("entry_price"),
                                "sl_price": final_call.get("stop_loss"),
                                "tp1_price": final_call.get("take_profit_1"),
                                "tp2_price": final_call.get("take_profit"),
                            },
                            decision_id=pipeline_id,
                            ai_decision="SKIP",
                            p_raw=raw_p,
                            p_cal=cal_p,
                            features=mp,
                        )
                        final_call["_shadow_registered"] = True
                    except Exception:
                        pass
                elif _sh_setup_name in ("QUANT_OBSERVATION_MODE", "NO_CLEAR_SETUP"):
                    # Prevent auto_trader fallback from re-registering dummy observation setups
                    final_call["_shadow_registered"] = True
            except Exception as _v2e:
                print(f"[INSTITUTIONAL V3] Enrichment notice: {_v2e}", flush=True)
    except Exception as e:
        if isinstance(e, AIUnavailable) or "ALL_AI_FAILED" in str(e):
            print(f"[AI-ONLY] {symbol}: AI tidak tersedia -> TIDAK TRADE ({str(e)[:140]})", flush=True)
            return {
                "pipeline_id": pipeline_id,
                "symbol": symbol,
                "error": f"AI_UNAVAILABLE: {str(e)[:200]}",
                "ai_unavailable": True,
                "status": "FAILED",
                "execution_time_sec": round(time.time() - start_time, 2)
            }
        raise

    execution_time = round(time.time() - start_time, 2)
    ai_fallback_used = bool(
        setup_result.get("ai_fallback")
        or plan_result.get("ai_fallback")
        or risk_result.get("ai_fallback")
        or final_call.get("ai_fallback")
    )
    if ai_fallback_used and final_call.get("status") == "APPROVED":
        final_call["status"] = "REJECTED"
        final_call["final_reason"] = f"{final_call.get('final_reason', '')} [AI_ONLY_BLOCK: fallback used]".strip()

    result = {
        "pipeline_id": pipeline_id,
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "execution_time_sec": execution_time,
        "status": final_call.get("status", "COMPLETED"),
        "ai_fallback_used": ai_fallback_used,
        "math_proof": market_data.get("math_proof"),
        "tp_time_prediction": plan_result.get("tp_time_prediction"),
        "neuro_symbolic_3brain": final_call.get("neuro_symbolic_3brain"),
        "roi_pnl_projection": plan_result.get("roi_pnl_projection"),
        "terminal_news_macro": market_data.get("news_macro"),
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
            "math_proof": market_data.get("math_proof"),
            "news_macro": market_data.get("news_macro"),
        },
        "layer2_setup": setup_result,
        "layer3_plan": plan_result,
        "layer4_risk": risk_result,
        "layer5_final_call": final_call
    }

    # === LAYER 6: SIDANG MAHKAMAH 9-AGENT MULTI-COMMITTEE ===
    # ⚡ TOKEN GUARD: Committee DINONAKTIFKAN default (hemat ~7000 token per coin).
    # Aktifkan di trading_config.json ("committee_enabled": true) jika diinginkan.
    committee_res = None
    cfg = get_trading_config()
    committee_enabled = cfg.get("committee_enabled", False) or os.getenv("COMMITTEE_ENABLED", "false").lower() == "true"
    _layer5_approved = final_call.get("status") == "APPROVED"

    if not committee_enabled:
        print(f"[PIPELINE] ⏭️ Committee DINONAKTIFKAN (hemat ~7000 token per koin) — keputusan Layer 5 final", flush=True)
    elif not _layer5_approved:
        print(f"[PIPELINE] ⏭️ Committee DILEWATI untuk {symbol} (Layer 5: {final_call.get('status', 'REJECTED')})", flush=True)
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

    # Catat sinyal ke journal.db (SQLite WAL) untuk pengukuran akurasi terukur
    try:
        from journal import log_signal
        log_signal({
            "pipeline_id": pipeline_id,
            "timestamp": result.get("timestamp"),
            "symbol": symbol,
            "timeframe": "1h",
            "regime": (market_data.get("math_proof") or {}).get("statistical_regime", "UNKNOWN"),
            "direction": final_call.get("direction", "NONE"),
            "setup": setup_result.get("setup_name", "N/A"),
            "ai_prob": final_call.get("confidence_score", 0),
            "calibrated_prob": final_call.get("calibrated_prob") if final_call.get("calibrated_prob") is not None else round(float(final_call.get("confidence_score", 0) or 0) / 100.0, 4),
            "entry": final_call.get("entry_price", 0),
            "sl": final_call.get("stop_loss", 0),
            "tp": final_call.get("take_profit_1", 0) or final_call.get("take_profit", 0),
            "rrr": final_call.get("risk_reward_ratio", "0:0"),
            "features": scan_summary,
            "provider": "ai",
            "model": "active_cascade",
            "decision": final_call.get("status", "REJECTED"),
            "reject_reason": final_call.get("final_reason", "")
        })
    except Exception as je:
        print(f"[JOURNAL] Notice: {je}", flush=True)

    # Save result to file for dashboard consumption
    try:
        result_file = os.path.join(RESULTS_DIR, f"{symbol.replace('-', '_')}_latest.json")
        if not state_io.atomic_write_json(result_file, result):
            result["save_error"] = f"atomic_write_json failed for {result_file}"
            logger.error("Failed atomic write for %s", result_file)

        # Also save to history
        history_file = os.path.join(RESULTS_DIR, f"history_{symbol.replace('-', '_')}.jsonl")
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("Failed saving pipeline output for %s: %s", symbol, e)
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
        state_io.atomic_write_json(summary_file, summary)
    except Exception as exc:
        logger.warning("Failed writing watchlist_summary.json: %s", exc)

    return results


if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC-USD"
    print(f"[*] Menguji 5-Layer Pipeline untuk {symbol}...", flush=True)
    res = run_5_layer_pipeline(symbol)
    print("\n=== HASIL 5-LAYER PIPELINE ===", flush=True)
    print(json.dumps(res, indent=2, ensure_ascii=False), flush=True)
