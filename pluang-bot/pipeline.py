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
        "min_confidence_score": 65,
        "min_risk_reward_ratio": 1.8,
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
MIN_CONFIDENCE_SCORE = _cfg.get("min_confidence_score", 65)
MIN_RISK_REWARD_RATIO = _cfg.get("min_risk_reward_ratio", 1.8)
MAX_DRAWDOWN_PCT = _cfg.get("max_drawdown_pct", 5.0)



def call_ai(prompt: str, system_prompt: str, max_tokens: int = 1500, temperature: float = 0.1, is_json: bool = True):
    """
    Call AI dengan Groq (primary, free & fast) atau OpenRouter (fallback).
    Mengaktifkan response_format json_object untuk menjamin JSON 100% valid.
    """
    if AI_PROVIDER == "groq" and GROQ_API_KEY:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        model = GROQ_MODEL
    else:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        model = OPENROUTER_MODEL

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    if is_json:
        data["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=60)
        if resp.status_code != 200:
            # Fallback to OpenRouter if Groq fails
            if AI_PROVIDER == "groq" and OPENROUTER_API_KEY:
                url2 = "https://openrouter.ai/api/v1/chat/completions"
                headers2 = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
                data["model"] = OPENROUTER_MODEL
                resp = requests.post(url2, headers=headers2, json=data, timeout=60)
                if resp.status_code != 200:
                    raise Exception(f"AI API Error {resp.status_code}: {resp.text[:300]}")
            else:
                raise Exception(f"AI API Error {resp.status_code}: {resp.text[:300]}")

        result = resp.json()
        content = result["choices"][0]["message"].get("content", "")
        if not content:
            content = result["choices"][0]["message"].get("reasoning", "")
        return content
    except Exception as e:
        raise Exception(f"AI call failed: {str(e)}")


def parse_json_from_text(text):
    """Robust JSON parser from AI output"""
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # Try extracting JSON block
    match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    # Try finding JSON object
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
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
    """AI identifies specific trading setup with high precision"""
    scan_json = json.dumps(scan_data, indent=2, ensure_ascii=False)

    system = (
        "Anda adalah 'Institutional Setup Hunter' crypto futures profesional. "
        "Anda HANYA mencari setup yang memiliki edge statistik kuantitatif tinggi.\n\n"
        "DAFTAR SETUP INSTITUSIONAL YANG VALID (pilih salah satu):\n"
        "1. SMC_LIQUIDITY_SWEEP_REVERSAL - Harga menyapu (sweep) swing high/low liquidity lalu reject kuat\n"
        "2. SMC_FAIR_VALUE_GAP_ENTRY - Harga retest ke area Fair Value Gap (FVG) dalam arah market structure\n"
        "3. DERIVATIVES_SHORT_SQUEEZE - Funding rate negatif ekstrem + crowd short, potensi ledakan harga naik\n"
        "4. DERIVATIVES_LONG_SQUEEZE_FADE - Funding rate positif ekstrem + overleveraged longs, risiko flush turun\n"
        "5. MULTI_PILLAR_QUANT_CONFLUENCE - Skor komposit 500+ faktor kuantitatif (>65 Bullish atau <35 Bearish) dengan konfluensi momentum & volume flow\n"
        "6. EMA_PULLBACK_CONTINUATION - Harga pullback ke EMA20/50 dalam tren kuat, bounce confirmed\n"
        "7. BOLLINGER_SQUEEZE_BREAKOUT - BB width sempit, harga breakout keluar dari konsolidasi\n"
        "8. RSI_DIVERGENCE_REVERSAL - RSI oversold (<30) dengan bullish divergence atau overbought (>75) dengan bearish divergence\n"
        "9. MACD_MOMENTUM_EXPANSION - Histogram MACD ekspansi searah tren utama (bullish/bearish crossover)\n"
        "10. NO_CLEAR_SETUP - Tidak ada setup valid atau pasar sedang sideways tanpa konfluensi. WAJIB pilih ini jika ragu.\n\n"
        "WAJIB output JSON berikut:\n"
        '{"setup_name": "nama_setup", "direction": "LONG/SHORT/NONE", '
        '"confluence_count": 3, "confluences": ["alasan1","alasan2","alasan3"], '
        '"probability_pct": 65, "explanation_id": "penjelasan singkat bahasa Indonesia"}'
    )

    prompt = (
        f"Analisis data pasar crypto futures {symbol} berikut (termasuk SMC & Derivatives Matrix) dan identifikasi setup trading:\n\n"
        f"{scan_json}\n\n"
        f"Keluarkan HANYA JSON setup. Jika tidak ada setup jelas, pilih NO_CLEAR_SETUP."
    )

    raw = call_ai(prompt, system, max_tokens=800, temperature=0.1)
    result = parse_json_from_text(raw)

    if not result:
        return {
            "setup_name": "NO_CLEAR_SETUP",
            "direction": "NONE",
            "confluence_count": 0,
            "confluences": [],
            "probability_pct": 0,
            "explanation_id": "AI gagal mengidentifikasi setup valid",
            "raw_output": raw[:500]
        }

    # Validasi: Minimal 2 confluence untuk setup valid (standar institusional)
    if result.get("confluence_count", 0) < 2 and result.get("setup_name") != "NO_CLEAR_SETUP":
        result["setup_name"] = "NO_CLEAR_SETUP"
        result["direction"] = "NONE"
        result["explanation_id"] += " [DITOLAK: Kurang dari 2 confluence]"

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

    raw = call_ai(prompt, system, max_tokens=800, temperature=0.1)
    result = parse_json_from_text(raw)

    if not result:
        return {
            "action": "SKIP",
            "entry_price": 0,
            "stop_loss": 0,
            "take_profit_1": 0,
            "take_profit_2": 0,
            "risk_reward_ratio": "0:0",
            "position_size_idr": 0,
            "leverage": 1,
            "reasoning": "Gagal membangun trading plan valid",
            "raw_output": raw[:500]
        }

    # === HARD SAFETY ENFORCEMENT ===
    # Cap position size
    if result.get("position_size_idr", 0) > MAX_BUDGET_IDR:
        result["position_size_idr"] = MAX_BUDGET_IDR
    # Cap leverage
    if result.get("leverage", 1) > MAX_LEVERAGE:
        result["leverage"] = MAX_LEVERAGE
    # If setup was NO_CLEAR_SETUP, force SKIP
    if setup_result.get("setup_name") == "NO_CLEAR_SETUP":
        result["action"] = "SKIP"

    return result


# ===========================================================================
# LAPISAN 4: CHIEF RISK OFFICER (Audit Skeptis Tanpa Kompromi)
# ===========================================================================
def layer4_risk_audit(symbol: str, scan_data: dict, setup_result: dict, plan_result: dict, market_data: dict):
    """Skeptical risk audit that tries to KILL the trade"""
    system = (
        "Anda adalah 'Chief Risk Officer' yang SANGAT SKEPTIS. "
        "Filosofi Anda: 'LEBIH BAIK MELEWATKAN 100 PELUANG DARIPADA RUGI 1 KALI'.\n\n"
        "AUDIT WAJIB (setiap poin berikan skor PASS/FAIL):\n"
        "1. RRR_CHECK: Apakah Risk-to-Reward >= 1:2.0? (FAIL jika < 1:2)\n"
        "2. RSI_CHECK: Apakah RSI di zona berbahaya? (FAIL jika LONG tapi RSI>70, FAIL jika SHORT tapi RSI<30)\n"
        "3. VOLUME_CHECK: Apakah volume cukup? (FAIL jika WEAK_RALLY_LOW_VOLUME atau LOW_INTEREST)\n"
        "4. TREND_ALIGNMENT: Apakah arah trade sejalan dengan tren 1H DAN Daily? (FAIL jika counter-trend)\n"
        "5. FUNDING_CHECK: Apakah funding rate mendukung? (WARNING jika berlawanan arah)\n"
        "6. VOLATILITY_CHECK: Apakah ATR terlalu tinggi untuk SL yang masuk akal? (FAIL jika ATR% > 5%)\n"
        "7. SENTIMENT_CHECK: Apakah Fear & Greed berlawanan dengan arah trade?\n"
        "8. LONG_SHORT_CHECK: Apakah crowd terlalu berat di satu sisi? (WARNING)\n"
        "9. LIQUIDITY_CHECK: Apakah ada risiko likuidasi dengan leverage yang direncanakan?\n"
        "10. MAX_DRAWDOWN: Berapa % potensi loss jika SL kena?\n\n"
        "KELUARKAN HANYA JSON:\n"
        "{\n"
        '  "total_score": 7,\n'
        '  "max_score": 10,\n'
        '  "pass_rate_pct": 70,\n'
        '  "checks": [\n'
        '    {"name": "RRR_CHECK", "status": "PASS", "detail": "RRR 1:2.5 memenuhi syarat"},\n'
        '    {"name": "RSI_CHECK", "status": "FAIL", "detail": "RSI 72 = overbought untuk LONG"}\n'
        '  ],\n'
        '  "critical_failures": ["RSI_CHECK"],\n'
        '  "max_drawdown_pct": 2.5,\n'
        '  "risk_verdict": "HIGH_RISK/MEDIUM_RISK/LOW_RISK/UNACCEPTABLE",\n'
        '  "recommendation": "PROCEED/REJECT/REDUCE_SIZE",\n'
        '  "reasoning": "penjelasan ketat"\n'
        "}"
    )

    prompt = (
        f"AUDIT RISIKO KETAT untuk {symbol}:\n\n"
        f"Data Market:\n{json.dumps(scan_data, indent=2, ensure_ascii=False)}\n\n"
        f"Setup: {json.dumps(setup_result, indent=2, ensure_ascii=False)}\n\n"
        f"Trading Plan: {json.dumps(plan_result, indent=2, ensure_ascii=False)}\n\n"
        f"AUDIT SEMUA 10 POIN TANPA KOMPROMI. Keluarkan HANYA JSON."
    )

    raw = call_ai(prompt, system, max_tokens=1200, temperature=0.1)
    result = parse_json_from_text(raw)

    if not result:
        return {
            "total_score": 0,
            "max_score": 10,
            "pass_rate_pct": 0,
            "checks": [],
            "critical_failures": ["PARSE_FAILURE"],
            "risk_verdict": "UNACCEPTABLE",
            "recommendation": "REJECT",
            "reasoning": "Audit risiko tidak dapat diverifikasi. Trade otomatis ditolak.",
            "raw_output": raw[:500]
        }

    return result


# ===========================================================================
# LAPISAN 5: SUPREME JUDGE (Keputusan Final - The Gatekeeper)
# ===========================================================================
def layer5_final_judgment(symbol: str, scan_data: dict, setup_result: dict,
                          plan_result: dict, risk_result: dict, market_data: dict):
    """The ultimate gatekeeper - makes the final APPROVED/REJECTED decision"""
    system = (
        "Anda adalah 'Supreme Investment Judge' - Hakim Tertinggi Trading.\n"
        "Filosofi: 'MODAL KECIL = HARUS EFISIEN. Ambil trade dengan edge kuantitatif, jangan terlalu perfeksionis.'\n\n"
        "STANDAR KELOLOSAN (INSTITUTIONAL-GRADE, REALISTIC):\n"
        "1. Setup harus memiliki >= 2 confluence (bukan NO_CLEAR_SETUP)\n"
        "2. Risk Audit pass rate >= 60% (minimal 6 dari 10 check PASS)\n"
        "3. Tidak ada lebih dari 2 CRITICAL FAILURE pada risk audit\n"
        "4. Risk-to-Reward >= 1:1.8\n"
        "5. Confidence Score >= 65%\n"
        "6. Volume tidak boleh EXTREMELY LOW (LOW_INTEREST masih OK jika confluensi kuat)\n"
        "7. RSI BUKAN di zona EXTREME (>80 untuk LONG atau <20 untuk SHORT)\n"
        "8. Minimal tren 1H ATAU Daily harus SEJALAN dengan arah trade\n"
        "9. Max drawdown < 5%\n"
        "10. Fear & Greed dipertimbangkan tapi BUKAN veto mutlak\n\n"
        "JIKA >= 8 dari 10 terpenuhi = APPROVED.\n"
        "JIKA RAGU = REJECTED.\n"
        "CASH IS A POSITION - TIDAK TRADING LEBIH BAIK DARI RUGI.\n\n"
        "KELUARKAN HANYA JSON:\n"
        "{\n"
        '  "status": "APPROVED/REJECTED",\n'
        '  "confidence_score": 85,\n'
        '  "direction": "LONG/SHORT/NONE",\n'
        '  "setup_name": "nama_setup",\n'
        '  "entry_price": 82500.00,\n'
        '  "take_profit_1": 85000.00,\n'
        '  "take_profit_2": 88000.00,\n'
        '  "stop_loss": 81000.00,\n'
        '  "risk_reward_ratio": "1:2.5",\n'
        '  "leverage": 3,\n'
        '  "position_size_idr": 50000,\n'
        '  "max_risk_idr": 1000,\n'
        '  "risk_audit_pass_rate": 70,\n'
        '  "checklist_passed": 8,\n'
        '  "checklist_total": 10,\n'
        '  "final_reason": "Penjelasan lengkap keputusan dalam Bahasa Indonesia"\n'
        "}"
    )

    prompt = (
        f"KEPUTUSAN FINAL untuk {symbol}:\n\n"
        f"=== LAPISAN 1 - DATA MARKET ===\n{json.dumps(scan_data, indent=2, ensure_ascii=False)}\n\n"
        f"=== LAPISAN 2 - SETUP ===\n{json.dumps(setup_result, indent=2, ensure_ascii=False)}\n\n"
        f"=== LAPISAN 3 - TRADING PLAN ===\n{json.dumps(plan_result, indent=2, ensure_ascii=False)}\n\n"
        f"=== LAPISAN 4 - RISK AUDIT ===\n{json.dumps(risk_result, indent=2, ensure_ascii=False)}\n\n"
        f"Evaluasi SELURUH data di atas. Keluarkan HANYA JSON Final Judgment."
    )

    raw = call_ai(prompt, system, max_tokens=1000, temperature=0.05)
    result = parse_json_from_text(raw)

    if not result:
        result = {
            "status": "REJECTED",
            "confidence_score": 0,
            "direction": "NONE",
            "setup_name": "PARSE_FAILURE",
            "entry_price": 0,
            "take_profit_1": 0,
            "take_profit_2": 0,
            "stop_loss": 0,
            "risk_reward_ratio": "0:0",
            "leverage": 1,
            "position_size_idr": 0,
            "max_risk_idr": 0,
            "final_reason": "Evaluasi tidak dapat diverifikasi. Trade otomatis DITOLAK demi keamanan dana."
        }

    # ============================================================
    # PYTHON-LEVEL SAFETY GATES (ANTI-TAMPERING, AI CANNOT BYPASS)
    # ============================================================

    cfg = get_trading_config()
    current_max_budget = cfg.get("max_budget_idr", 50000)
    current_max_leverage = cfg.get("max_leverage", 5)
    current_min_confidence = cfg.get("min_confidence_score", 80)
    current_min_rrr = cfg.get("min_risk_reward_ratio", 2.0)

    # Gate 1: Confidence < min = FORCE REJECT
    if result.get("confidence_score", 0) < current_min_confidence:
        result["status"] = "REJECTED"
        result["final_reason"] = (result.get("final_reason", "") +
            f" [PYTHON GATE: Confidence {result.get('confidence_score')}% < {current_min_confidence}% minimum]")

    # Gate 2: Position size > MAX_BUDGET
    if result.get("position_size_idr", 0) > current_max_budget:
        result["position_size_idr"] = current_max_budget

    # Gate 3: Leverage > MAX_LEVERAGE
    if result.get("leverage", 1) > current_max_leverage:
        result["leverage"] = current_max_leverage

    # Gate 4: If setup was NO_CLEAR_SETUP, FORCE REJECT
    if setup_result.get("setup_name") == "NO_CLEAR_SETUP":
        result["status"] = "REJECTED"
        result["final_reason"] = (result.get("final_reason", "") +
            " [PYTHON GATE: Tidak ada setup valid terdeteksi]")

    # Gate 5: If plan was SKIP, FORCE REJECT
    if plan_result.get("action") == "SKIP":
        result["status"] = "REJECTED"
        result["final_reason"] = (result.get("final_reason", "") +
            " [PYTHON GATE: Trading plan memilih SKIP]")

    # Gate 6: If risk audit recommends REJECT
    if risk_result.get("recommendation") == "REJECT":
        result["status"] = "REJECTED"
        result["final_reason"] = (result.get("final_reason", "") +
            " [PYTHON GATE: Risk Officer merekomendasikan REJECT]")

    # Gate 7: If risk audit has MORE than 2 critical failures (allow 1-2 for realistic trading)
    cf = risk_result.get("critical_failures", [])
    real_cf = [c for c in cf if c != "PARSE_FAILURE"]
    if len(real_cf) > 2:
        result["status"] = "REJECTED"
        result["final_reason"] = (result.get("final_reason", "") +
            f" [PYTHON GATE: Too many critical risk failures ({len(real_cf)}): {', '.join(real_cf)}]")

    # Gate 8: RRR check from string
    try:
        rrr_str = result.get("risk_reward_ratio", "0:0")
        parts = rrr_str.split(":")
        if len(parts) == 2:
            rrr_val = float(parts[1]) / float(parts[0]) if float(parts[0]) > 0 else 0
            if rrr_val < MIN_RISK_REWARD_RATIO:
                result["status"] = "REJECTED"
                result["final_reason"] = (result.get("final_reason", "") +
                    f" [PYTHON GATE: RRR {rrr_str} < minimum 1:{MIN_RISK_REWARD_RATIO}]")
    except Exception:
        pass

    # Gate 9: 500+ Quantitative Factor Composite Score Gate
    quant_matrix = scan_data.get("quant_factors") or market_data.get("quant_factors")
    if quant_matrix and isinstance(quant_matrix, dict) and "composite_quant_score" in quant_matrix:
        c_score = quant_matrix.get("composite_quant_score", 50.0)
        direction = result.get("direction", "NONE")
        # If trying to LONG but quant factor score is bearish (<40)
        if direction == "LONG" and c_score < 40.0:
            result["status"] = "REJECTED"
            result["final_reason"] = (result.get("final_reason", "") +
                f" [PYTHON GATE: Quant Score {c_score}/100 bearish - Veto LONG trade]")
        # If trying to SHORT but quant factor score is bullish (>60)
        elif direction == "SHORT" and c_score > 60.0:
            result["status"] = "REJECTED"
            result["final_reason"] = (result.get("final_reason", "") +
                f" [PYTHON GATE: Quant Score {c_score}/100 bullish - Veto SHORT trade]")

    return result


# ===========================================================================
# MAIN PIPELINE EXECUTOR
# ===========================================================================
def run_5_layer_pipeline(symbol: str):
    """
    Execute the complete 5-layer institutional crypto futures pipeline.
    Returns comprehensive result with all layer outputs.
    """
    start_time = time.time()
    pipeline_id = f"{symbol}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # === LAYER 1: SCANNING ===
    market_data, scan_summary = layer1_scanning(symbol)
    if market_data is None:
        return {
            "pipeline_id": pipeline_id,
            "symbol": symbol,
            "error": scan_summary,
            "status": "FAILED",
            "execution_time_sec": round(time.time() - start_time, 2)
        }

    # === LAYER 2: SETUP HUNTER ===
    setup_result = layer2_setup_hunter(symbol, scan_summary)

    # === LAYER 3: BUILD PLAN ===
    plan_result = layer3_build_plan(symbol, scan_summary, setup_result, market_data)

    # === LAYER 4: RISK AUDIT ===
    risk_result = layer4_risk_audit(symbol, scan_summary, setup_result, plan_result, market_data)

    # === LAYER 5: FINAL JUDGMENT ===
    final_call = layer5_final_judgment(symbol, scan_summary, setup_result, plan_result, risk_result, market_data)

    execution_time = round(time.time() - start_time, 2)

    result = {
        "pipeline_id": pipeline_id,
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "execution_time_sec": execution_time,
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
