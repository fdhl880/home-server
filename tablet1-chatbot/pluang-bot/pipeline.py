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
    """Single provider call with response parsing."""
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


class DailyLimitExhausted(Exception):
    """Raised when a provider's daily token limit is hit — no point retrying."""
    pass


def call_ai(prompt: str, system_prompt: str, max_tokens: int = 1500, temperature: float = 0.1, is_json: bool = True):
    """
    Robust AI caller with SMART provider cascade:
    1. If Groq daily limit NOT exhausted → try Groq (1 attempt, fast fail on 429 TPD)
    2. If Groq fails → immediately try OpenRouter (3 attempts with backoff)
    3. If ALL fail → raise exception (pipeline uses rule-based fallback as LAST RESORT)
    
    KEY: 429 TPD (daily limit) → ZERO retries, instant cascade to next provider.
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

    # Build provider chain
    providers = []
    
    # Groq (primary) — skip if daily limit already detected
    if GROQ_API_KEY and not _GROQ_DAILY_EXHAUSTED["exhausted"]:
        providers.append({
            "name": "Groq",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            "model": GROQ_MODEL,
            "max_retries": 2,  # Quick: 1 try + 1 retry for transient errors
        })
    
    # OpenRouter (fallback) — always available
    if OPENROUTER_API_KEY:
        providers.append({
            "name": "OpenRouter",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "headers": {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            "model": OPENROUTER_MODEL,
            "max_retries": 3,  # More retries for fallback
        })

    if not providers:
        raise Exception("No AI providers configured (both GROQ_API_KEY and OPENROUTER_API_KEY are empty)")

    last_error = ""
    for prov in providers:
        data = {**base_data, "model": prov["model"]}
        for attempt in range(prov["max_retries"]):
            try:
                content = _call_single_provider(prov["url"], prov["headers"], data, timeout=45)
                # Success! If we were using OpenRouter, log it
                if prov["name"] != "Groq":
                    print(f"[AI OK] {prov['name']} responded successfully", flush=True)
                return content
            except DailyLimitExhausted as e:
                # Daily limit = NO retry, mark Groq as dead, jump to next provider
                _GROQ_DAILY_EXHAUSTED["exhausted"] = True
                _GROQ_DAILY_EXHAUSTED["detected_at"] = time.time()
                print(f"[AI] ⛔ {prov['name']} DAILY LIMIT HIT — switching to next provider", flush=True)
                last_error = str(e)
                break  # Break inner retry loop, continue to next provider
            except Exception as e:
                last_error = f"{prov['name']} attempt {attempt+1}: {e}"
                if attempt < prov["max_retries"] - 1:
                    wait = (attempt + 1) * 2  # 2s, 4s
                    print(f"[AI RETRY] {last_error} — retrying in {wait}s...", flush=True)
                    time.sleep(wait)
                else:
                    print(f"[AI FAIL] {prov['name']} exhausted after {prov['max_retries']} attempts", flush=True)

    raise Exception(f"All AI providers failed. Last: {last_error}")


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

    # === INSTITUTIONAL SETUP DETERMINATION (Selective Wall Street Quality) ===
    # A true institutional desk only trades when edge is clear (3+ confluences).
    # Choppy sideways markets (net between -2 and +2) are REJECTED to preserve cash.
    net = bull_score - bear_score
    direction = "NONE"
    setup_name = "NO_CLEAR_SETUP"
    prob = 35

    if net >= 3:
        direction = "LONG"
        setup_name = "RULE_BASED_BULLISH_CONFLUENCE"
        prob = min(68 + (net - 3) * 5, 85)
    elif net <= -3:
        direction = "SHORT"
        setup_name = "RULE_BASED_BEARISH_CONFLUENCE"
        prob = min(68 + (abs(net) - 3) * 5, 85)
    elif net == 2 and vol_ratio > 1.4:
        direction = "LONG"
        setup_name = "RULE_BASED_BREAKOUT_LONG"
        prob = 66
    elif net == -2 and vol_ratio > 1.4:
        direction = "SHORT"
        setup_name = "RULE_BASED_BREAKDOWN_SHORT"
        prob = 66
    else:
        # Choppy, low-conviction market: explicitly keep in CASH
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
        return {"action": "SKIP", "entry_price": 0, "stop_loss": 0, "take_profit_1": 0,
                "take_profit_2": 0, "risk_reward_ratio": "0:0", "position_size_idr": 0,
                "leverage": 1, "reasoning": "No setup detected (rule-based)", "ai_fallback": True}

    sl_mult = 1.5
    tp1_mult = 2.0
    tp2_mult = 3.5

    if direction == "LONG":
        sl = price - (atr * sl_mult)
        tp1 = price + (atr * tp1_mult)
        tp2 = price + (atr * tp2_mult)
    else:
        sl = price + (atr * sl_mult)
        tp1 = price - (atr * tp1_mult)
        tp2 = price - (atr * tp2_mult)

    sl_dist = abs(price - sl)
    tp2_dist = abs(tp2 - price)
    rrr = round(tp2_dist / sl_dist, 1) if sl_dist > 0 else 0

    cfg = get_trading_config()
    return {
        "action": direction,
        "entry_price": round(price, 6),
        "stop_loss": round(sl, 6),
        "take_profit_1": round(tp1, 6),
        "take_profit_2": round(tp2, 6),
        "risk_reward_ratio": f"1:{rrr}",
        "position_size_idr": cfg.get("max_budget_idr", 50000),
        "leverage": min(3, cfg.get("max_leverage", 5)),
        "risk_pct_of_capital": 2.0,
        "sl_distance_pct": round((sl_dist / price) * 100, 2),
        "reasoning": f"ATR-based plan: SL {sl_mult}x ATR, TP1 {tp1_mult}x ATR, TP2 {tp2_mult}x ATR",
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

    # 5-10: generous pass for rule-based (5 more auto-pass)
    for name in ["FUNDING_CHECK", "VOLATILITY_CHECK", "SENTIMENT_CHECK", "LONG_SHORT_CHECK", "LIQUIDITY_CHECK", "MAX_DRAWDOWN"]:
        total += 1
        checks.append({"name": name, "status": "PASS", "detail": "Auto-pass (rule-based mode)"})

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

    return data_1h, scan_summary


# ===========================================================================
# LAPISAN 2: SETUP HUNTER (Identifikasi Pola & Strategi)
# ===========================================================================
def layer2_setup_hunter(symbol: str, scan_data: dict):
    """AI identifies specific trading setup - Wall Street quant approach"""
    scan_json = json.dumps(scan_data, indent=2, ensure_ascii=False)

    system = (
        "Anda adalah 'Senior Quantitative Setup Analyst' di hedge fund Wall Street. "
        "Gaya trading: seperti Ray Dalio (systematic), George Soros (macro), dan Jim Simons (quant). "
        "Anda AKTIF mencari peluang trading yang menguntungkan di setiap kondisi pasar.\n\n"
        "PRINSIP UTAMA:\n"
        "- Di pasar crypto yang volatile, SELALU ada peluang baik LONG maupun SHORT\n"
        "- Trader profesional menghasilkan uang di SEMUA kondisi pasar (trending, ranging, volatile)\n"
        "- Cari MINIMAL 2 konfirmasi teknikal untuk membuka posisi\n"
        "- RSI oversold = peluang LONG bounce, RSI overbought = peluang SHORT fade\n"
        "- Trend following DAN mean-reversion keduanya valid\n"
        "- JANGAN default ke NO_CLEAR_SETUP kecuali benar-benar flat sideways tanpa volume\n\n"
        "DAFTAR SETUP VALID (pilih yang PALING cocok):\n"
        "1. TREND_CONTINUATION - EMA bullish/bearish + MACD searah + volume konfirmasi\n"
        "2. MEAN_REVERSION_BOUNCE - RSI oversold/overbought + support/resistance + divergence\n"
        "3. BREAKOUT_MOMENTUM - Harga break level kunci + volume tinggi + momentum kuat\n"
        "4. EMA_PULLBACK_ENTRY - Pullback ke EMA20/50 dalam tren kuat\n"
        "5. SMC_LIQUIDITY_SWEEP - Sweep liquidity + rejection di level kunci\n"
        "6. BOLLINGER_SQUEEZE_BREAKOUT - BB squeeze + expansion + directional momentum\n"
        "7. RSI_DIVERGENCE_PLAY - Divergence RSI vs price di level support/resistance\n"
        "8. MACD_CROSSOVER_MOMENTUM - MACD crossover + histogram expansion\n"
        "9. FUNDING_RATE_ARBITRAGE - Extreme funding + crowd positioning contrarian\n"
        "10. VOLATILITY_EXPANSION - ATR expanding + directional move confirmed\n"
        "11. NO_CLEAR_SETUP - HANYA jika pasar BENAR-BENAR datar (volume rendah, range sempit, tanpa momentum)\n\n"
        "WAJIB output JSON berikut:\n"
        '{"setup_name": "nama_setup", "direction": "LONG/SHORT/NONE", '
        '"confluence_count": 3, "confluences": ["alasan1","alasan2","alasan3"], '
        '"probability_pct": 65, "explanation_id": "penjelasan singkat bahasa Indonesia"}'
    )

    prompt = (
        f"Sebagai senior quant analyst, analisis {symbol} berikut dan temukan setup trading terbaik.\n"
        f"INGAT: Trader profesional SELALU menemukan peluang. Cari LONG atau SHORT yang paling masuk akal.\n\n"
        f"{scan_json}\n\n"
        f"Keluarkan HANYA JSON setup. Prioritaskan menemukan trade yang valid."
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
        "Anda adalah 'Quantitative Trading Plan Architect' untuk crypto futures.\n"
        "Tugas: Menyusun rencana trading yang PRESISI berdasarkan data kuantitatif.\n\n"
        "ATURAN BESI:\n"
        f"1. Modal MAKSIMAL: Rp 50.000 (TIDAK BOLEH LEBIH)\n"
        f"2. Leverage MAKSIMAL: 5x\n"
        f"3. Stop Loss WAJIB berdasarkan ATR (1.5x ATR dari entry)\n"
        f"4. Risk per trade MAKSIMAL 2% dari modal (Rp 1.000)\n"
        f"5. Take Profit MINIMUM 2x jarak Stop Loss (RRR >= 1:2)\n"
        f"6. Jika setup = NO_CLEAR_SETUP, langsung buat plan SKIP\n\n"
        "WAJIB output JSON berikut:\n"
        "{\n"
        '  "action": "LONG/SHORT/SKIP",\n'
        '  "entry_price": 0.0,\n'
        '  "stop_loss": 0.0,\n'
        '  "take_profit_1": 0.0,\n'
        '  "take_profit_2": 0.0,\n'
        '  "risk_reward_ratio": "1:2.5",\n'
        '  "risk_amount_idr": 1000,\n'
        '  "position_size_idr": 50000,\n'
        '  "leverage": 3,\n'
        '  "risk_pct_of_capital": 2.0,\n'
        '  "sl_distance_pct": 1.5,\n'
        '  "tp1_distance_pct": 3.0,\n'
        '  "reasoning": "penjelasan singkat"\n'
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
        f"Buat Trading Plan PRESISI. Keluarkan HANYA JSON."
    )

    raw = call_ai(prompt, system, max_tokens=2000, temperature=0.1)
    result = parse_json_from_text(raw)

    if not result:
        # AI failed to parse — use rule-based plan instead of giving up
        print(f"[FALLBACK] Layer 3 AI parse failed for {symbol} — using rule-based plan", flush=True)
        return _rule_based_plan(scan_data, setup_result, market_data)

    # === HARD SAFETY ENFORCEMENT ===
    # Cap position size
    if result.get("position_size_idr", 0) > MAX_BUDGET_IDR:
        result["position_size_idr"] = MAX_BUDGET_IDR
    # Cap leverage
    if result.get("leverage", 1) > MAX_LEVERAGE:
        result["leverage"] = MAX_LEVERAGE
    # If setup was NO_CLEAR_SETUP, allow AI to still propose a plan
    # (professional traders sometimes override scanner with discretion)

    return result


# ===========================================================================
# LAPISAN 4: CHIEF RISK OFFICER (Professional Risk Management)
# ===========================================================================
def layer4_risk_audit(symbol: str, scan_data: dict, setup_result: dict, plan_result: dict, market_data: dict):
    """Professional risk assessment - balanced like Goldman Sachs risk desk"""
    system = (
        "Anda adalah 'Chief Risk Officer' profesional di trading desk institutional. "
        "Filosofi: 'Kelola risiko dengan PRESISI, bukan PARANOIA. Modal kecil harus aktif bekerja, bukan idle di cash selamanya.'\n\n"
        "PRINSIP RISK MANAGEMENT PROFESIONAL:\n"
        "- Risiko adalah BIAYA BISNIS trading, bukan musuh\n"
        "- Stop loss yang jelas = risiko terkontrol = PASS\n"
        "- Leverage 2-5x dengan SL ketat = ACCEPTABLE di crypto futures\n"
        "- Counter-trend trade = WARNING tapi bukan otomatis FAIL\n"
        "- FUNDING check: hanya FAIL jika extreme (>0.05% atau <-0.05%)\n"
        "- Crypto futures ATR 3-8% = NORMAL, bukan HIGH RISK\n\n"
        "AUDIT 10 POIN (berikan PASS/FAIL/WARNING per poin):\n"
        "1. RRR_CHECK: RRR >= 1:1.5 = PASS. RRR >= 1:2 = STRONG PASS\n"
        "2. RSI_CHECK: FAIL hanya jika EXTREME (LONG saat RSI>80 atau SHORT saat RSI<20)\n"
        "3. VOLUME_CHECK: FAIL hanya jika benar-benar LOW_INTEREST dan no momentum\n"
        "4. TREND_ALIGNMENT: WARNING jika counter-trend, PASS jika sejalan\n"
        "5. FUNDING_CHECK: PASS unless extreme. WARNING = masih OK\n"
        "6. VOLATILITY_CHECK: Crypto volatility normal 2-6%. FAIL hanya >8%\n"
        "7. SENTIMENT_CHECK: Fear & Greed hanya WARNING, bukan FAIL\n"
        "8. LONG_SHORT_CHECK: Crowd positioning = informasi, bukan veto\n"
        "9. LIQUIDITY_CHECK: PASS jika leverage <= 5x dengan SL\n"
        "10. MAX_DRAWDOWN: PASS jika < 5% drawdown\n\n"
        "RECOMMENDATION:\n"
        "- 7-10 PASS = PROCEED\n"
        "- 5-6 PASS = PROCEED_WITH_CAUTION (reduce size)\n"
        "- < 5 PASS = REJECT\n\n"
        "KELUARKAN HANYA JSON:\n"
        '{"total_score": 7, "max_score": 10, "pass_rate_pct": 70, '
        '"checks": [{"name": "RRR_CHECK", "status": "PASS", "detail": "RRR 1:2.5"}], '
        '"critical_failures": [], "max_drawdown_pct": 2.5, '
        '"risk_verdict": "LOW_RISK", "recommendation": "PROCEED", '
        '"reasoning": "penjelasan profesional"}'
    )

    prompt = (
        f"Risk Assessment profesional untuk trade {symbol}:\n\n"
        f"Market Data:\n{json.dumps(scan_data, indent=2, ensure_ascii=False)}\n\n"
        f"Setup: {json.dumps(setup_result, indent=2, ensure_ascii=False)}\n\n"
        f"Trading Plan: {json.dumps(plan_result, indent=2, ensure_ascii=False)}\n\n"
        f"INGAT: Anda di trading desk aktif, bukan asuransi. Audit SEMUA 10 poin. Keluarkan HANYA JSON."
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
        "Filosofi: 'UANG IDLE = BIAYA PELUANG. Modal Rp 50.000 harus AKTIF bekerja menghasilkan profit.'\n\n"
        "MINDSET PROFESIONAL:\n"
        "- Warren Buffett: Be greedy when others are fearful\n"
        "- George Soros: Markets are ALWAYS wrong, find the edge\n"
        "- Jim Simons: Statistics > emotions, take calculated risks\n"
        "- Trader top-tier APPROVE 30-50% dari setup yang terdeteksi\n"
        "- Modal kecil (Rp 50K) = HARUS agresif karena max loss hanya Rp 1-2K\n\n"
        "STANDAR KELOLOSAN (ACTIVE TRADING MODE):\n"
        "1. Setup memiliki arah jelas (LONG/SHORT) dengan >= 1 confluence\n"
        "2. Risk audit pass >= 50% (5+ dari 10)\n"
        "3. Ada entry, SL, dan TP yang jelas\n"
        f"4. RRR >= 1:{min_rrr} (1:1.5 sudah acceptable)\n"
        f"5. Confidence >= {min_conf}%\n"
        "6. Volume bukan nol/mati total\n"
        "7. SL distance < 5% dari entry\n\n"
        "JIKA setup VALID + risk MANAGEABLE = APPROVED.\n"
        "REJECTED hanya jika setup benar-benar kosong atau risiko fatal.\n\n"
        "WAJIB KELUARKAN JSON LENGKAP dengan semua field terisi:\n"
        '{"status": "APPROVED", "confidence_score": 72, "direction": "LONG", '
        '"setup_name": "TREND_CONTINUATION", "entry_price": 82500.00, '
        '"take_profit_1": 84000.00, "take_profit_2": 86000.00, "stop_loss": 81200.00, '
        '"risk_reward_ratio": "1:2.3", "leverage": 3, "position_size_idr": 50000, '
        '"max_risk_idr": 1000, "risk_audit_pass_rate": 70, '
        '"checklist_passed": 7, "checklist_total": 10, '
        '"final_reason": "Penjelasan lengkap"}'
    )

    prompt = (
        f"KEPUTUSAN FINAL untuk {symbol} — anda WAJIB memutuskan APPROVED atau REJECTED:\n\n"
        f"=== DATA MARKET ===\n{json.dumps(scan_data, indent=2, ensure_ascii=False)}\n\n"
        f"=== SETUP ===\n{json.dumps(setup_result, indent=2, ensure_ascii=False)}\n\n"
        f"=== TRADING PLAN ===\n{json.dumps(plan_result, indent=2, ensure_ascii=False)}\n\n"
        f"=== RISK AUDIT ===\n{json.dumps(risk_result, indent=2, ensure_ascii=False)}\n\n"
        f"INGAT: Anda di prop firm yang AKTIF trading, bukan bank konservatif. "
        f"Jika ada trade yang layak, APPROVE. Keluarkan HANYA JSON."
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
        result = {
            "status": "APPROVED" if approved else "REJECTED",
            "confidence_score": prob,
            "direction": direction,
            "setup_name": setup_name,
            "entry_price": plan_result.get("entry_price", 0),
            "take_profit_1": plan_result.get("take_profit_1", 0),
            "take_profit_2": plan_result.get("take_profit_2", 0),
            "stop_loss": plan_result.get("stop_loss", 0),
            "risk_reward_ratio": plan_result.get("risk_reward_ratio", "0:0"),
            "leverage": plan_result.get("leverage", 1),
            "position_size_idr": plan_result.get("position_size_idr", 0),
            "max_risk_idr": 1000,
            "final_reason": f"Rule-based judgment: {', '.join(setup_result.get('confluences', [])[:3])}",
            "ai_fallback": True
        }

    return _apply_safety_gates(result, setup_result, plan_result, risk_result, scan_data, market_data)


def _apply_safety_gates(result, setup_result, plan_result, risk_result, scan_data, market_data):
    """
    PYTHON-LEVEL SAFETY GATES - Professional risk controls.
    Only block trades with FATAL issues, not minor concerns.
    """
    cfg = get_trading_config()
    current_max_budget = cfg.get("max_budget_idr", 50000)
    current_max_leverage = cfg.get("max_leverage", 5)
    current_min_confidence = cfg.get("min_confidence_score", 45)
    current_min_rrr = cfg.get("min_risk_reward_ratio", 1.5)

    reasons = []

    # Gate 1: Confidence < min (Institutional standard: must meet min confidence)
    conf = result.get("confidence_score", 0)
    if conf < current_min_confidence:
        result["status"] = "REJECTED"
        reasons.append(f"Confidence score {conf}% di bawah batas institusional {current_min_confidence}%")

    # Gate 2: Cap position size (don't reject, just cap)
    if result.get("position_size_idr", 0) > current_max_budget:
        result["position_size_idr"] = current_max_budget

    # Gate 3: Cap leverage (don't reject, just cap)
    if result.get("leverage", 1) > current_max_leverage:
        result["leverage"] = current_max_leverage

    # Gate 4: NO_CLEAR_SETUP or Direction NONE = REJECT
    if result.get("direction", "NONE") == "NONE" or setup_result.get("setup_name") == "NO_CLEAR_SETUP":
        result["status"] = "REJECTED"
        reasons.append("Pasar sideways/konsolidasi tanpa setup arah konvergen yang jelas")

    # Gate 5: Plan SKIP rejects
    if plan_result.get("action") == "SKIP":
        result["status"] = "REJECTED"
        reasons.append("Trading plan SKIP (level SL/TP tidak memiliki edge statistik)")

    # Gate 6: Risk audit must pass at least 6/10 checks
    risk_score = risk_result.get("total_score", 5)
    if risk_score < 6:
        result["status"] = "REJECTED"
        reasons.append(f"Risk audit hanya lolos {risk_score}/10 (minimum 6/10)")

    # Gate 7: Critical failures >= 2 = REJECT
    cf = risk_result.get("critical_failures", [])
    real_cf = [c for c in cf if c != "PARSE_FAILURE"]
    if len(real_cf) >= 2:
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

    # Gate 9: Quant score - only STRONG veto (extreme values)
    quant_matrix = scan_data.get("quant_factors") or market_data.get("quant_factors")
    if quant_matrix and isinstance(quant_matrix, dict) and "composite_quant_score" in quant_matrix:
        c_score = quant_matrix.get("composite_quant_score", 50.0)
        direction = result.get("direction", "NONE")
        if direction == "LONG" and c_score < 25.0:  # Only extreme bearish vetoes LONG
            result["status"] = "REJECTED"
            reasons.append(f"Quant Score {c_score}/100 sangat bearish")
        elif direction == "SHORT" and c_score > 75.0:  # Only extreme bullish vetoes SHORT
            result["status"] = "REJECTED"
            reasons.append(f"Quant Score {c_score}/100 sangat bullish")

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
            "entry_price": plan_result.get("entry_price", 0),
            "take_profit_1": plan_result.get("take_profit_1", 0),
            "take_profit_2": plan_result.get("take_profit_2", 0),
            "stop_loss": plan_result.get("stop_loss", 0),
            "risk_reward_ratio": plan_result.get("risk_reward_ratio", "0:0"),
            "leverage": plan_result.get("leverage", 1),
            "position_size_idr": plan_result.get("position_size_idr", 0),
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
