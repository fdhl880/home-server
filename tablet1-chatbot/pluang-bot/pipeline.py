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
from datetime import datetime, timezone

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
    env_path = os.path.join(BASE_DIR, ".env")
    env = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env

ENV = load_env()

# ===== AI PROVIDER CONFIGURATION =====
AI_PROVIDER = ENV.get("AI_PROVIDER", "groq")  # "groq" or "openrouter"
GROQ_API_KEY = ENV.get("GROQ_API_KEY", "")
GROQ_MODEL = ENV.get("GROQ_MODEL", "openai/gpt-oss-120b")
OPENROUTER_API_KEY = ENV.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = ENV.get("OPENROUTER_MODEL", "minimax/minimax-m3.1-flash:free")
GEMINI_API_KEY = ENV.get("GEMINI_API_KEY", "")
CEREBRAS_API_KEY = ENV.get("CEREBRAS_API_KEY", "")

# Free backup models on OpenRouter — RANKED FROM SMARTEST TO LEAST SMART
# Based on LMSYS Arena + benchmark scores + parameter count
OPENROUTER_FREE_MODELS = [
    "minimax/minimax-m3.1-flash:free",      # #2: 1M context, strong agentic/coding
    "nvidia/nemotron-3-super-120b-a12b:free", # #3: 120B MoE, high reasoning
    "google/gemma-4-31b-it:free",            # #4: 31B, near-proprietary logic
    "cohere/north-mini-code:free",           # #5: Specialized coding
    "openrouter/free",                       # #6: Auto-router (picks any available)
]

CONFIG_FILE = os.path.join(BASE_DIR, "trading_config.json")

def get_trading_config():
    cfg = {
        "max_budget_idr": 50000,
        "max_leverage": 5,
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
    return cfg

def save_trading_config(new_config: dict):
    cfg = get_trading_config()
    cfg.update(new_config)
    cfg["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass
    return cfg

# Initial config
_cfg = get_trading_config()
MAX_BUDGET_IDR = _cfg.get("max_budget_idr", 50000)
MAX_LEVERAGE = _cfg.get("max_leverage", 5)
MIN_CONFIDENCE_SCORE = _cfg.get("min_confidence_score", 45)
MIN_RISK_REWARD_RATIO = _cfg.get("min_risk_reward_ratio", 1.5)
MAX_DRAWDOWN_PCT = _cfg.get("max_drawdown_pct", 5.0)


# Circuit breaker: if Groq daily limit hit, skip Groq for rest of session
_GROQ_DAILY_EXHAUSTED = {"exhausted": False, "detected_at": 0}


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


def _call_gemini_provider(api_key, model, messages, max_tokens=1500, temperature=0.1, timeout=60):
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
    
    payload = {
        "contents": gemini_contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json"
        }
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


def call_ai(prompt: str, system_prompt: str, max_tokens: int = 1500, temperature: float = 0.1, is_json: bool = True):
    """
    ULTIMATE AI caller — 6-deep provider cascade, NEVER falls back to rule-based math.
    
    CASCADE ORDER (configurable via AI_PROVIDER):
    1. Primary provider (OpenRouter or Groq based on AI_PROVIDER setting)
    2. Secondary provider (the other one)
    3. OpenRouter FREE model rotation (gemma-4, nemotron, cohere, auto-router)
    4. Google Gemini Flash (free, different infrastructure entirely)
    5. Cerebras (free, ultra-fast inference)
    
    If ALL 6+ providers fail → raises Exception (pipeline handles gracefully).
    NEVER returns rule-based/manual calculations. Always AI.
    """
    global _GROQ_DAILY_EXHAUSTED

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    base_data = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    if is_json:
        base_data["response_format"] = {"type": "json_object"}

    # ===== BUILD PROVIDER CHAIN — SORTED BY INTELLIGENCE (SMARTEST FIRST) =====
    providers = []
    
    # --- Tier 1: Google Gemini 3.8 Flash (proprietary Google reasoning model — SMARTEST) ---
    gemini_prov = None
    if GEMINI_API_KEY:
        gemini_prov = {
            "name": "Gemini-Flash",
            "type": "gemini",
            "api_key": GEMINI_API_KEY,
            "model": "gemini-3.8-flash",
            "max_retries": 1,
        }

    # --- Tier 2: Groq (GPT-OSS-120B — 120B reasoning model) ---
    groq_prov = {
        "name": "Groq",
        "type": "openai_compat",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "headers": {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        "model": GROQ_MODEL,
        "max_retries": 1,
    }

    # --- Tier 3: Primary OpenRouter ---
    openrouter_prov = {
        "name": "OpenRouter",
        "type": "openai_compat",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "headers": {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
        "model": OPENROUTER_MODEL,
        "max_retries": 2,
    }

    # Build order based on AI_PROVIDER preference (default: Gemini first if available, else Groq, else OpenRouter)
    if AI_PROVIDER.lower() == "gemini" and gemini_prov:
        providers.append(gemini_prov)
        if GROQ_API_KEY and not _GROQ_DAILY_EXHAUSTED["exhausted"]:
            providers.append(groq_prov)
        if OPENROUTER_API_KEY:
            providers.append(openrouter_prov)
    elif AI_PROVIDER.lower() == "openrouter":
        if gemini_prov:
            providers.append(gemini_prov)  # Smartest first
        if OPENROUTER_API_KEY:
            providers.append(openrouter_prov)
        if GROQ_API_KEY and not _GROQ_DAILY_EXHAUSTED["exhausted"]:
            providers.append(groq_prov)
    else:  # groq or default
        if gemini_prov:
            providers.append(gemini_prov)  # Smartest first
        if GROQ_API_KEY and not _GROQ_DAILY_EXHAUSTED["exhausted"]:
            providers.append(groq_prov)
        if OPENROUTER_API_KEY:
            providers.append(openrouter_prov)

    # --- Tier 4: OpenRouter FREE model rotation (backup, sorted by intelligence) ---
    if OPENROUTER_API_KEY:
        for free_model in OPENROUTER_FREE_MODELS:
            if free_model != OPENROUTER_MODEL:  # Don't duplicate primary
                providers.append({
                    "name": f"OR-{free_model.split('/')[0]}",
                    "type": "openai_compat",
                    "url": "https://openrouter.ai/api/v1/chat/completions",
                    "headers": {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                    "model": free_model,
                    "max_retries": 1,
                })

    # --- Tier 5: Cerebras (free, ultra-fast) ---
    if CEREBRAS_API_KEY:
        providers.append({
            "name": "Cerebras",
            "type": "openai_compat",
            "url": "https://api.cerebras.ai/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {CEREBRAS_API_KEY}", "Content-Type": "application/json"},
            "model": "qwen-3.8-27b",
            "max_retries": 2,
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
                if prov["type"] == "gemini":
                    # Gemini has its own API format
                    content = _call_gemini_provider(
                        prov["api_key"], prov["model"], messages,
                        max_tokens=max_tokens, temperature=temperature, timeout=35
                    )
                else:
                    # OpenAI-compatible endpoint (Groq, OpenRouter, Cerebras)
                    data = {**base_data, "model": prov["model"]}
                    content = _call_single_provider(prov["url"], prov["headers"], data, timeout=45)
                
                # Success!
                print(f"[AI OK] {prov_name} ({prov.get('model', '?')}) responded ✅", flush=True)
                return content
                
            except DailyLimitExhausted as e:
                _GROQ_DAILY_EXHAUSTED["exhausted"] = True
                _GROQ_DAILY_EXHAUSTED["detected_at"] = time.time()
                print(f"[AI] ⛔ {prov_name} DAILY LIMIT HIT — cascading to next provider", flush=True)
                last_error = str(e)
                break  # Break inner retry loop, continue to next provider
            except Exception as e:
                last_error = f"{prov_name} attempt {attempt+1}: {e}"
                if attempt < prov["max_retries"] - 1:
                    wait = (attempt + 1) * 2
                    print(f"[AI RETRY] {last_error} — retrying in {wait}s...", flush=True)
                    time.sleep(wait)
                else:
                    print(f"[AI SKIP] {prov_name} exhausted after {prov['max_retries']} attempts", flush=True)

    raise Exception(
        f"⛔ ALL {len(providers_tried)} AI providers failed! "
        f"Tried: {' → '.join(providers_tried)}. "
        f"Last error: {last_error}"
    )



# ===================================================================
# RULE-BASED TECHNICAL FALLBACK (when ALL AI providers are down)
# ===================================================================
def _rule_based_setup(scan_data: dict):
    """
    Pure-technical consensus engine — NO AI needed.
    Returns setup dict mimicking Layer 2 output.
    Used when Groq + OpenRouter both fail.
    """
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
    """Rule-based trading plan when AI is down."""
    price = market_data.get("current_price", scan_data.get("price", 0))
    atr = market_data.get("atr_14", 0)
    atr_pct = market_data.get("atr_pct", 0) or (atr / price * 100 if price else 0)
    direction = setup.get("direction", "NONE")

    if direction == "NONE" or price <= 0:
        return {"action": "SKIP", "order_type": "MARKET", "entry_price": 0, "limit_price": 0,
                "stop_loss": 0, "take_profit": 0, "take_profit_1": 0, "take_profit_2": 0,
                "risk_reward_ratio": "0:0", "position_size_idr": 0,
                "leverage": 1, "reasoning": "No setup detected (rule-based)", "ai_fallback": True}

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
        "take_profit_1": round(tp, 6),  # backward compatibility alias
        "take_profit_2": round(tp, 6),  # backward compatibility alias
        "risk_reward_ratio": f"1:{rrr}",
        "position_size_idr": 50000,
        "leverage": 5,
        "risk_pct_of_capital": 2.0,
        "sl_distance_pct": round((sl_dist / price) * 100, 2),
        "tp_distance_pct": round((tp_dist / price) * 100, 2),
        "reasoning": f"ATR Single TP plan: SL {sl_mult}x ATR, TP {tp_mult}x ATR (Pluang Single TP)",
        "ai_fallback": True
    }


def _rule_based_risk(scan_data: dict, setup: dict, plan: dict, market_data: dict):
    """Rule-based risk audit when AI is down."""
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
    liq_ok = lev <= 5
    if liq_ok: total += 1
    checks.append({"name": "LIQUIDITY_CHECK", "status": "PASS" if liq_ok else "FAIL", "detail": f"Lev: {lev}x"})

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

    # Generate scan summary for AI consumption
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
        "quant_factors": data_1h.get("quant_factors"),
        "daily_rsi": data_1d.get("rsi_14") if isinstance(data_1d, dict) else None,
        "daily_trend": data_1d.get("trend") if isinstance(data_1d, dict) else None,
        "daily_macd": data_1d.get("macd") if isinstance(data_1d, dict) else None,
    }

    # Macro Breaking News & Sentiment Sentinel
    try:
        from news_sentinel import get_news_sentiment_summary
        scan_summary["news_macro"] = get_news_sentiment_summary()
    except Exception:
        scan_summary["news_macro"] = {"market_sentiment": "NEUTRAL", "sentiment_score": 50}

    return data_1h, scan_summary


# ===========================================================================
# LAPISAN 2: SETUP HUNTER (Identifikasi Pola & Strategi)
# ===========================================================================
def layer2_setup_hunter(symbol: str, scan_data: dict):
    """AI identifies specific trading setup - Wall Street quant approach"""
    scan_json = json.dumps(scan_data, indent=2, ensure_ascii=False)

    system = (
        "Anda adalah 'Senior Quantitative Setup Analyst' di Wall Street Institutional Hedge Fund "
        "(gaya Renaissance Technologies / Jim Simons, Paul Tudor Jones, Mark Minervini, Richard Wyckoff).\n"
        "Data scan mencakup 500+ faktor kuantitatif 5 pilar (Momentum, Mean Reversion, Volume & Order Flow, "
        "Volatility Regime, Institutional Derivatives & Smart Money Concepts).\n\n"
        "Gaya analisis: OBJEKTIF, SKEPTIS, dan BERBASIS DATA MURNI 500+ FAKTOR.\n\n"
        "PRINSIP UTAMA (KETAT):\n"
        "- JANGAN paksakan trade jika data teknikal 500+ faktor tidak mendukung\n"
        "- Minimal 3 konfirmasi teknikal INDEPENDEN yang KUAT untuk setup valid\n"
        "- RSI antara 35-65 = NETRAL, bukan sinyal\n"
        "- MACD flat/sideways = bukan sinyal\n"
        "- Volume rendah atau rata-rata = bukan konfirmasi\n"
        "- Jika indikator saling bertentangan (RSI bearish tapi EMA bullish) = NO_CLEAR_SETUP\n"
        "- Lebih baik MELEWATKAN trade daripada memaksakan entry tanpa edge\n"
        "- NO_CLEAR_SETUP adalah keputusan VALID dan SERING terjadi di pasar sideways\n\n"
        "DAFTAR SETUP VALID (pilih HANYA jika 3+ konfirmasi terpenuhi):\n"
        "1. TREND_CONTINUATION - EMA bullish/bearish + MACD searah + volume di atas rata-rata\n"
        "2. MEAN_REVERSION_BOUNCE - RSI <30 atau >70 + di level support/resistance kuat + divergence\n"
        "3. BREAKOUT_MOMENTUM - Harga break level kunci + volume >1.5x rata-rata + candle besar\n"
        "4. EMA_PULLBACK_ENTRY - Pullback ke EMA20/50 dalam tren kuat + RSI bounce\n"
        "5. SMC_LIQUIDITY_SWEEP - Sweep liquidity + rejection candle + volume konfirmasi\n"
        "6. BOLLINGER_SQUEEZE_BREAKOUT - BB squeeze + expansion + volume spike\n"
        "7. RSI_DIVERGENCE_PLAY - Divergence RSI vs price + di level S/R + volume konfirmasi\n"
        "8. MACD_CROSSOVER_MOMENTUM - MACD crossover + histogram expanding + trend searah\n"
        "9. FUNDING_RATE_ARBITRAGE - Extreme funding (>0.03% atau <-0.03%) + crowd over-positioned\n"
        "10. VOLATILITY_EXPANSION - ATR expanding >50% + directional candle + volume\n"
        "11. NO_CLEAR_SETUP - Pasar sideways, sinyal campur, volume rendah, atau <3 konfirmasi\n\n"
        "WAJIB output JSON berikut:\n"
        '{"setup_name": "nama_setup", "direction": "LONG/SHORT/NONE", '
        '"confluence_count": 3, "confluences": ["alasan1","alasan2","alasan3"], '
        '"probability_pct": 65, "explanation_id": "penjelasan singkat bahasa Indonesia"}'
    )

    prompt = (
        f"Analisis OBJEKTIF untuk {symbol}. Jangan paksakan trade jika data tidak mendukung.\n"
        f"Jika <3 konfirmasi kuat, keluarkan NO_CLEAR_SETUP.\n\n"
        f"{scan_json}\n\n"
        f"Keluarkan HANYA JSON setup."
    )

    raw = call_ai(prompt, system, max_tokens=2000, temperature=0.15)
    result = parse_json_from_text(raw)

    if not result:
        # Fallback to rule-based instead of giving up
        return _rule_based_setup(scan_data)

    # If AI returns low confluence but has direction, still allow it
    if result.get("confluence_count", 0) < 1 and result.get("setup_name") != "NO_CLEAR_SETUP":
        result["confluence_count"] = max(result.get("confluence_count", 0), 1)

    return result


# ===========================================================================
# LAPISAN 3: TRADING PLAN ARCHITECT (Entry/TP/SL/Sizing)
# ===========================================================================
def layer3_build_plan(symbol: str, scan_data: dict, setup_result: dict, market_data: dict):
    """Build precise trading plan with strict money management"""
    current_price = market_data.get("current_price", 0)
    atr = market_data.get("atr_14", 0)

    system = (
        "Anda adalah 'Quantitative Trading Plan Architect' untuk crypto futures di Pluang.\n"
        "Tugas: Menyusun rencana trading yang PRESISI berdasarkan data kuantitatif.\n\n"
        "AI MEMEGANG KENDALI PENUH EKSEKUSI:\n"
        "1. LEVERAGE DIATUR OLEH AI: Tentukan leverage secara cerdas (1x - 20x) berdasarkan volatilitas ATR, jarak SL, dan keyakinan setup. Volatilitas tinggi -> leverage rendah (2x-5x); setup solid/volatilitas terukur -> leverage lebih tinggi.\n"
        "2. ORDER TYPE DIATUR OLEH AI: Pilih 'MARKET' (jika butuh eksekusi instan saat momentum/breakout) atau 'LIMIT' (jika butuh entry di harga tertentu/pullback support-resistance). Jika LIMIT, wajib berikan 'limit_price'.\n"
        "3. MODAL (POSITION SIZE) DIATUR OLEH AI: Hitung alokasi modal per trade (position_size_idr) secara dinamis sesuai risk management dan jarak Stop Loss (misal Rp 25.000 - Rp 250.000).\n"
        "4. PLUANG HANYA MENDUKUNG SINGLE TAKE PROFIT: DILARANG membuat dual TP (TP1/TP2). Buat TEPAT 1 target Take Profit ('take_profit') dan 1 Stop Loss ('stop_loss'). RRR minimal 1:1.5.\n"
        "5. Stop Loss WAJIB dihitung logis berdasarkan ATR (1.5x - 2x ATR dari entry) atau struktur SMC.\n"
        "6. Jika setup = NO_CLEAR_SETUP, buat action SKIP.\n\n"
        "WAJIB output JSON berikut:\n"
        "{\n"
        '  "action": "LONG/SHORT/SKIP",\n'
        '  "order_type": "MARKET/LIMIT",\n'
        '  "entry_price": 0.0,\n'
        '  "limit_price": 0.0,\n'
        '  "stop_loss": 0.0,\n'
        '  "take_profit": 0.0,\n'
        '  "risk_reward_ratio": "1:2.5",\n'
        '  "position_size_idr": 50000,\n'
        '  "leverage": 5,\n'
        '  "risk_amount_idr": 1000,\n'
        '  "risk_pct_of_capital": 2.0,\n'
        '  "sl_distance_pct": 1.5,\n'
        '  "tp_distance_pct": 3.75,\n'
        '  "reasoning": "penjelasan singkat mengenai alasan entry, level SL/TP, leverage, dan order type"\n'
        "}"
    )

    prompt = (
        f"Data Market {symbol}:\n"
        f"- Harga saat ini: ${current_price}\n"
        f"- ATR (14): ${atr} ({market_data.get('atr_pct')}%)\n"
        f"- RSI: {market_data.get('rsi_14')}\n"
        f"- EMA Trend: {market_data.get('ema_trend')}\n"
        f"- Resistance 1: ${scan_data.get('levels', {}).get('resistance_1')}\n"
        f"- Support 1: ${scan_data.get('levels', {}).get('support_1')}\n"
        f"- Bollinger: {json.dumps(scan_data.get('bollinger_1h', {}))}\n"
        f"- Volume: {json.dumps(scan_data.get('volume', {}))}\n\n"
        f"Setup yang terdeteksi:\n{json.dumps(setup_result, indent=2, ensure_ascii=False)}\n\n"
        f"Buat Trading Plan PRESISI. Tentukan leverage, order_type (MARKET/LIMIT), limit_price, modal IDR, dan SINGLE take_profit. Keluarkan HANYA JSON."
    )

    raw = call_ai(prompt, system, max_tokens=2000, temperature=0.1)
    result = parse_json_from_text(raw)

    if not result:
        # AI failed to parse — use rule-based plan instead of giving up
        print(f"[FALLBACK] Layer 3 AI parse failed for {symbol} — using rule-based plan", flush=True)
        return _rule_based_plan(scan_data, setup_result, market_data)

    # Standardize single take_profit and aliases
    tp = result.get("take_profit") or result.get("take_profit_2") or result.get("take_profit_1") or 0
    result["take_profit"] = tp
    result["take_profit_1"] = tp
    result["take_profit_2"] = tp

    # Default order_type & limit_price if omitted
    if not result.get("order_type"):
        result["order_type"] = "MARKET"
    if result["order_type"].upper() == "LIMIT" and not result.get("limit_price"):
        result["limit_price"] = result.get("entry_price", current_price)
    elif result["order_type"].upper() != "LIMIT":
        result["limit_price"] = result.get("entry_price", current_price)

    # Cap leverage to exchange maximum safety (25x)
    lev = int(result.get("leverage") or 5)
    result["leverage"] = max(1, min(lev, 25))

    # Fallback position size if invalid
    if not result.get("position_size_idr") or result.get("position_size_idr") <= 0:
        result["position_size_idr"] = 50000

    return result


# ===========================================================================
# LAPISAN 4: CHIEF RISK OFFICER (Professional Risk Management)
# ===========================================================================
def layer4_risk_audit(symbol: str, scan_data: dict, setup_result: dict, plan_result: dict, market_data: dict):
    """Professional risk assessment - balanced like Goldman Sachs risk desk"""
    system = (
        "Anda adalah 'Chief Risk Officer' profesional di trading desk institutional. "
        "Filosofi: 'LINDUNGI MODAL TERLEBIH DAHULU. Profit hanya datang jika modal terjaga.'\n\n"
        "PRINSIP RISK MANAGEMENT KETAT:\n"
        "- Stop loss yang jelas dan ketat WAJIB ada\n"
        "- Counter-trend trade = FAIL (jangan melawan tren dominan)\n"
        "- Leverage >3x tanpa support/resistance kuat = WARNING\n"
        "- Volume rendah = FAIL (tidak ada likuiditas untuk exit)\n"
        "- RSI netral (35-65) dengan LONG/SHORT = WARNING (tidak ada edge)\n\n"
        "AUDIT 11 POIN (berikan PASS/FAIL/WARNING per poin, JUJUR):\n"
        "1. RRR_CHECK: RRR >= 1:2 = PASS. RRR < 1:1.5 = FAIL\n"
        "2. RSI_CHECK: FAIL jika LONG saat RSI>70 atau SHORT saat RSI<30\n"
        "3. VOLUME_CHECK: FAIL jika volume di bawah rata-rata 20 periode\n"
        "4. TREND_ALIGNMENT: FAIL jika counter-trend pada timeframe 1h DAN 1d\n"
        "5. FUNDING_CHECK: WARNING jika funding >0.01% searah posisi\n"
        "6. VOLATILITY_CHECK: FAIL jika ATR >6% (terlalu volatile untuk entry baru)\n"
        "7. SENTIMENT_CHECK: WARNING jika Fear & Greed extreme\n"
        "8. LONG_SHORT_CHECK: WARNING jika 70%+ crowd di sisi yang sama\n"
        "9. LIQUIDITY_CHECK: FAIL jika leverage >5x atau spread terlalu lebar\n"
        "10. MAX_DRAWDOWN: FAIL jika potential drawdown >3% dari modal\n"
        "11. NEWS_CHECK: FAIL jika ada breaking news negatif/hack/exploit pada koin ini; WARNING jika sentiment berita BEARISH saat posisi LONG\n\n"
        "RECOMMENDATION:\n"
        "- 9-11 PASS = PROCEED\n"
        "- 7-8 PASS = PROCEED_WITH_CAUTION\n"
        "- < 7 PASS = REJECT\n\n"
        "KELUARKAN HANYA JSON:\n"
        '{"total_score": 8, "max_score": 11, "pass_rate_pct": 73, '
        '"checks": [{"name": "RRR_CHECK", "status": "PASS", "detail": "RRR 1:2.5"}], '
        '"critical_failures": [], "max_drawdown_pct": 2.5, '
        '"risk_verdict": "LOW_RISK", "recommendation": "PROCEED", '
        '"reasoning": "penjelasan profesional"}'
    )

    prompt = (
        f"Risk Assessment KETAT untuk trade {symbol}:\n\n"
        f"Market Data:\n{json.dumps(scan_data, indent=2, ensure_ascii=False)}\n\n"
        f"Setup: {json.dumps(setup_result, indent=2, ensure_ascii=False)}\n\n"
        f"Trading Plan: {json.dumps(plan_result, indent=2, ensure_ascii=False)}\n\n"
        f"Audit JUJUR. Jangan bias approve. Jika ada kelemahan, katakan FAIL. Keluarkan HANYA JSON."
    )

    raw = call_ai(prompt, system, max_tokens=2500, temperature=0.1)
    result = parse_json_from_text(raw)

    if not result:
        # Use rule-based risk instead of auto-rejecting
        return _rule_based_risk(scan_data, setup_result, plan_result, market_data)

    return result


# ===========================================================================
# LAPISAN 5: SUPREME JUDGE (Final Decision - Professional Trading Desk)
# ===========================================================================
def layer5_final_judgment(symbol: str, scan_data: dict, setup_result: dict,
                          plan_result: dict, risk_result: dict, market_data: dict):
    """Final decision maker - balanced like a professional prop trading desk"""
    cfg = get_trading_config()
    min_conf = cfg.get("min_confidence_score", 45)
    min_rrr = cfg.get("min_risk_reward_ratio", 1.5)
    system = (
        "Anda adalah 'Head of Trading Desk' di prop firm institusional.\n"
        "Filosofi: 'KUALITAS > KUANTITAS. Hanya ambil trade dengan edge statistik yang jelas.'\n\n"
        "MINDSET PROFESIONAL:\n"
        "- Warren Buffett: 'Rule 1: Never lose money. Rule 2: Never forget rule 1.'\n"
        "- Jim Simons: Hanya trade dengan probabilitas matematis yang jelas\n"
        "- Top-tier prop firms APPROVE hanya 10-20% setup (sangat selektif)\n"
        "- Tidak trade = keputusan yang VALID dan sering lebih bijak\n\n"
        "STANDAR KELOLOSAN (KETAT):\n"
        "1. Setup memiliki arah jelas (LONG/SHORT) dengan >= 3 confluence INDEPENDEN\n"
        "2. Risk audit pass >= 70% (7+ dari 10)\n"
        "3. Entry, SL, dan TP yang LOGIS berdasarkan level teknikal nyata\n"
        f"4. RRR >= 1:{min_rrr}\n"
        f"5. Confidence >= {min_conf}%\n"
        "6. Volume di atas rata-rata (konfirmasi partisipasi pasar)\n"
        "7. SL distance < 3% dari entry\n"
        "8. Tidak ada critical failure di risk audit\n\n"
        "REJECT jika:\n"
        "- Setup NO_CLEAR_SETUP atau <3 konfirmasi\n"
        "- Risk audit gagal >=4 poin\n"
        "- Indikator saling bertentangan tanpa resolusi\n"
        "- Volume rendah (tidak ada likuiditas)\n\n"
        "WAJIB KELUARKAN JSON LENGKAP:\n"
        '{"status": "APPROVED", "confidence_score": 72, "direction": "LONG", '
        '"order_type": "MARKET", "limit_price": 82500.00, '
        '"setup_name": "TREND_CONTINUATION", "entry_price": 82500.00, '
        '"take_profit": 86000.00, "stop_loss": 81200.00, '
        '"risk_reward_ratio": "1:2.3", "leverage": 5, "position_size_idr": 50000, '
        '"max_risk_idr": 1000, "risk_audit_pass_rate": 70, '
        '"checklist_passed": 7, "checklist_total": 10, '
        '"final_reason": "Penjelasan lengkap"}'
    )

    prompt = (
        f"KEPUTUSAN FINAL untuk {symbol} — APPROVED atau REJECTED:\n\n"
        f"=== DATA MARKET ===\n{json.dumps(scan_data, indent=2, ensure_ascii=False)}\n\n"
        f"=== SETUP ===\n{json.dumps(setup_result, indent=2, ensure_ascii=False)}\n\n"
        f"=== TRADING PLAN ===\n{json.dumps(plan_result, indent=2, ensure_ascii=False)}\n\n"
        f"=== RISK AUDIT ===\n{json.dumps(risk_result, indent=2, ensure_ascii=False)}\n\n"
        f"Analisis JUJUR. Keputusan eksekusi (leverage, order_type, modal IDR, dan SINGLE take_profit untuk Pluang) ditentukan secara presisi oleh AI. "
        f"APPROVE hanya jika edge statistik JELAS. Keluarkan HANYA JSON."
    )

    raw = call_ai(prompt, system, max_tokens=2500, temperature=0.1)
    result = parse_json_from_text(raw)

    if not result:
        # If AI parse fails, use rule-based judgment instead of auto-reject
        cfg2 = get_trading_config()
        direction = setup_result.get("direction", "NONE")
        prob = setup_result.get("probability_pct", 0)
        risk_score = risk_result.get("total_score", 0)
        setup_name = setup_result.get("setup_name", "NO_CLEAR_SETUP")
        approved = (
            direction != "NONE" and
            setup_name != "NO_CLEAR_SETUP" and
            prob >= cfg2.get("min_confidence_score", 45) and
            risk_score >= 5 and
            plan_result.get("action") not in ("SKIP", None)
        )
        tp_val = plan_result.get("take_profit") or plan_result.get("take_profit_2") or plan_result.get("take_profit_1", 0)
        result = {
            "status": "APPROVED" if approved else "REJECTED",
            "confidence_score": prob,
            "direction": direction,
            "setup_name": setup_name,
            "order_type": plan_result.get("order_type", "MARKET"),
            "limit_price": plan_result.get("limit_price", plan_result.get("entry_price", 0)),
            "entry_price": plan_result.get("entry_price", 0),
            "take_profit": tp_val,
            "take_profit_1": tp_val,
            "take_profit_2": tp_val,
            "stop_loss": plan_result.get("stop_loss", 0),
            "risk_reward_ratio": plan_result.get("risk_reward_ratio", "0:0"),
            "leverage": plan_result.get("leverage", 5),
            "position_size_idr": plan_result.get("position_size_idr", 50000),
            "max_risk_idr": 1000,
            "final_reason": f"Rule-based judgment: {', '.join(setup_result.get('confluences', [])[:3])}",
            "ai_fallback": True
        }
    else:
        tp_val = result.get("take_profit") or result.get("take_profit_2") or result.get("take_profit_1") or plan_result.get("take_profit") or plan_result.get("take_profit_2", 0)
        result["take_profit"] = tp_val
        result["take_profit_1"] = tp_val
        result["take_profit_2"] = tp_val
        if not result.get("order_type"):
            result["order_type"] = plan_result.get("order_type", "MARKET")
        if not result.get("limit_price"):
            result["limit_price"] = plan_result.get("limit_price", result.get("entry_price", 0))
        if not result.get("leverage"):
            result["leverage"] = plan_result.get("leverage", 5)
        if not result.get("position_size_idr"):
            result["position_size_idr"] = plan_result.get("position_size_idr", 50000)

    return _apply_safety_gates(result, setup_result, plan_result, risk_result, scan_data, market_data)


def _apply_safety_gates(result, setup_result, plan_result, risk_result, scan_data, market_data):
    """
    PYTHON-LEVEL SAFETY GATES - Balanced institutional risk controls.
    Block only CLEARLY dangerous trades, allow setups with reasonable edge.
    AI governs leverage, limit/market order type, modal, and single Take Profit.
    """
    cfg = get_trading_config()
    current_max_budget = cfg.get("max_budget_idr", 500000)
    current_max_leverage = cfg.get("max_leverage", 25)
    current_min_confidence = cfg.get("min_confidence_score", 45)
    current_min_rrr = cfg.get("min_risk_reward_ratio", 1.5)

    # Preserve AI-governed parameters
    tp_val = result.get("take_profit") or plan_result.get("take_profit") or plan_result.get("take_profit_2", 0)
    result["take_profit"] = tp_val
    result["take_profit_1"] = tp_val
    result["take_profit_2"] = tp_val
    result["order_type"] = result.get("order_type") or plan_result.get("order_type", "MARKET")
    result["limit_price"] = result.get("limit_price") or plan_result.get("limit_price", result.get("entry_price", 0))

    reasons = []

    # Gate 1: Confidence < min
    conf = result.get("confidence_score", 0)
    if conf < current_min_confidence:
        result["status"] = "REJECTED"
        reasons.append(f"Confidence score {conf}% di bawah batas {current_min_confidence}%")

    # Gate 2: Bounded by max capital setting (AI manages modal)
    if result.get("position_size_idr", 0) > current_max_budget:
        result["position_size_idr"] = current_max_budget
    elif result.get("position_size_idr", 0) <= 0:
        result["position_size_idr"] = 50000

    # Gate 3: Bounded by max leverage setting (AI manages leverage)
    if result.get("leverage", 1) > current_max_leverage:
        result["leverage"] = current_max_leverage
    elif result.get("leverage", 1) < 1:
        result["leverage"] = 1

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
def run_5_layer_pipeline(symbol: str):
    """
    Execute the complete 5-layer institutional crypto futures pipeline.
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

    # Quick short-circuit if no valid setup detected: saves 3 AI API calls & 10+ seconds per coin
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
            "leverage": 1,
            "position_size_idr": 0,
            "final_reason": setup_result.get("reasoning") or "Pasar sideways tanpa setup terkonfirmasi. Dana aman di USDT.",
            "checklist_passed": 0,
            "checklist_total": 10
        }
        res_payload = {
            "pipeline_id": pipeline_id,
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "execution_time_sec": round(time.time() - start_time, 2),
            "status": "COMPLETED",
            "ai_fallback_used": ai_fallback_used,
            "layer1_scanning": scan_summary,
            "layer2_setup": setup_result,
            "layer3_plan": plan_result,
            "layer4_risk": risk_result,
            "layer5_final_call": final_call
        }
        try:
            os.makedirs(RESULTS_DIR, exist_ok=True)
            fname = os.path.join(RESULTS_DIR, f"{symbol.replace('-', '_')}_latest.json")
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(res_payload, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return res_payload

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
            "leverage": plan_result.get("leverage", 5),
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
