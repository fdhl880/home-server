"""
===========================================================================
PYROFUEL MULTI-AGENT COMMITTEE ENGINE v2.0
===========================================================================
Terinspirasi dari:
- TradingAgents (Tauric Research): Multi-agent LLM framework
- ai-hedge-fund (virattt): Investor-persona agents + Kelly sizing
- Vibe-Trading (HKUDS): Shadow account & backtest-aware risk mgmt
- LangAlpha (ginlix): Thesis-driven persistent research workspace
- hummingbot: Market making spread + inventory management patterns

ARSITEKTUR:
  ANALYST TEAM (paralel):
    - TechnicalAnalyst, SentimentAnalyst, FundamentalsAgent, MacroAnalyst

  RESEARCHER TEAM (debate):
    - BullResearcher vs BearResearcher

  EXECUTION:
    - TraderAgent -> RiskOfficer -> PortfolioManager (gatekeeper)

  MARKET MAKING:
    - SpreadCalculator (hummingbot-inspired)

  THESIS ENGINE:
    - Persistent workspace per simbol (LangAlpha-inspired)

SEMUA HARUS APPROVE. SATU VETO = TRADE DITOLAK.
===========================================================================
"""
import os
import json
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

try:
    from pipeline import call_ai, get_trading_config, RESULTS_DIR
    from market_data import get_market_indicators, convert_usd_to_idr, convert_idr_to_usd
except ImportError:
    def call_ai(p, **kw): return "N/A"
    def get_trading_config(): return {}
    def convert_usd_to_idr(x): return x * 16000
    def convert_idr_to_usd(x): return x / 16000
    def get_market_indicators(s): return {}
    RESULTS_DIR = "results"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMMITTEE_LOG_FILE = os.path.join(RESULTS_DIR, "committee_log.json")
THESIS_FILE = os.path.join(RESULTS_DIR, "active_thesis.json")


# ============================================================
# ANALYST TEAM (TradingAgents pattern - parallel execution)
# ============================================================

def run_technical_analyst(symbol, market_data):
    price = market_data.get("price", market_data.get("current_price", 0))
    rsi = market_data.get("rsi_14", 50)
    ema20 = market_data.get("ema_20", price)
    ema50 = market_data.get("ema_50", price)
    change_24h = market_data.get("change_24h_pct", 0)
    volume = market_data.get("volume_24h_usd", 0)
    high_24h = market_data.get("high_24h", price * 1.02)
    low_24h = market_data.get("low_24h", price * 0.98)
    bb_width = (high_24h - low_24h) / price * 100 if price > 0 else 5

    trend_score = 0
    signals = []
    if price > ema20: trend_score += 1; signals.append("Harga > EMA20 (bullish)")
    else: trend_score -= 1; signals.append("Harga < EMA20 (bearish)")
    if ema20 > ema50: trend_score += 1; signals.append("EMA20 > EMA50 (golden zone)")
    else: trend_score -= 1; signals.append("EMA20 < EMA50 (death zone)")
    if rsi < 35: trend_score += 2; signals.append(f"RSI {rsi:.0f} — Oversold")
    elif rsi > 65: trend_score -= 2; signals.append(f"RSI {rsi:.0f} — Overbought")
    if volume > 500_000_000: trend_score += 1; signals.append("Volume tinggi")
    if bb_width > 10: signals.append(f"BB Width {bb_width:.1f}% — High volatility")

    verdict = "BULLISH" if trend_score >= 2 else ("BEARISH" if trend_score <= -2 else "NEUTRAL")

    try:
        prompt = f"Technical Analyst crypto futures. {symbol}: Harga=${price:,.4f}, RSI={rsi:.1f}, " \
                 f"EMA alignment={'bullish' if ema20>ema50 else 'bearish'}, Change={change_24h:.1f}%, " \
                 f"BB Width={bb_width:.1f}%. Sinyal: {', '.join(signals[:3])}. " \
                 f"Analisis teknikal 2-3 kalimat, rekomendasi LONG/SHORT/WAIT. Bahasa Indonesia."
        analysis = call_ai(prompt, max_tokens=200)
    except:
        analysis = f"Trend {verdict}. RSI {rsi:.0f}, EMA {'bullish' if ema20 > ema50 else 'bearish'}."

    return {"agent": "TechnicalAnalyst", "verdict": verdict, "trend_score": trend_score,
            "signals": signals, "rsi": rsi, "bb_width_pct": round(bb_width, 2), "analysis": analysis}


def run_sentiment_analyst(symbol, market_data):
    change_24h = market_data.get("change_24h_pct", 0)
    volume = market_data.get("volume_24h_usd", 0)

    if change_24h > 8: sentiment, fg = "EXTREME_BULLISH", 82
    elif change_24h > 3: sentiment, fg = "BULLISH", 66
    elif change_24h > 0: sentiment, fg = "SLIGHTLY_BULLISH", 54
    elif change_24h > -3: sentiment, fg = "SLIGHTLY_BEARISH", 44
    elif change_24h > -8: sentiment, fg = "BEARISH", 32
    else: sentiment, fg = "EXTREME_FEAR", 18

    try:
        prompt = f"Sentiment Analyst crypto. {symbol}: Change 24h={change_24h:.1f}%, " \
                 f"Vol=${volume/1e6:.0f}M. Sentiment proxy: {sentiment}, F&G ~{fg}. " \
                 f"Analisis sentimen 2-3 kalimat (mood market, justified/overreaction, dampak LONG/SHORT). Bahasa Indonesia."
        analysis = call_ai(prompt, max_tokens=180)
    except:
        analysis = f"Sentimen {sentiment.replace('_',' ').title()}, Fear&Greed estimasi {fg}/100."

    return {"agent": "SentimentAnalyst", "sentiment": sentiment, "fear_greed": fg,
            "change_24h": change_24h, "analysis": analysis}


def run_fundamentals_agent(symbol, market_data):
    price = market_data.get("price", market_data.get("current_price", 0))
    volume = market_data.get("volume_24h_usd", 0)
    oi = market_data.get("open_interest_usd", volume * 0.3)
    funding = market_data.get("funding_rate", 0.0001)

    if funding > 0.001: bias, fsig = "BEARISH", "Longs dominan berlebihan (squeeze risk)"
    elif funding > 0.0003: bias, fsig = "NEUTRAL_BULLISH", "Bullish tapi terkendali"
    elif funding < -0.001: bias, fsig = "BULLISH", "Shorts dominan berlebihan (short squeeze risk)"
    elif funding < -0.0003: bias, fsig = "NEUTRAL_BEARISH", "Bearish tapi terkendali"
    else: bias, fsig = "NEUTRAL", "Pasar seimbang"

    oi_vol = oi / volume if volume > 0 else 0.3

    try:
        prompt = f"On-Chain Analyst crypto futures. {symbol}: Vol=${volume/1e6:.0f}M, " \
                 f"OI=${oi/1e6:.0f}M, OI/Vol={oi_vol:.2f}, Funding={funding:.4f}% ({fsig}). " \
                 f"Analisis fundamental 2-3 kalimat. Bahasa Indonesia."
        analysis = call_ai(prompt, max_tokens=180)
    except:
        analysis = f"Funding {funding:.4f}% — {fsig}. Bias: {bias}."

    return {"agent": "FundamentalsAgent", "fundamental_bias": bias, "funding_rate": funding,
            "funding_signal": fsig, "oi_vol_ratio": round(oi_vol, 3), "analysis": analysis}


def run_macro_analyst(symbol, market_data):
    change_24h = market_data.get("change_24h_pct", 0)
    if abs(change_24h) > 5: regime, note = "HIGH_VOLATILITY", "Volatilitas tinggi — sizing kecil"
    elif change_24h > 2: regime, note = "RISK_ON", "Risk-on — altcoin outperform"
    elif change_24h < -2: regime, note = "RISK_OFF", "Risk-off — fokus major coins"
    else: regime, note = "CONSOLIDATION", "Konsolidasi — tunggu breakout"
    coin = symbol.replace("-USD","").replace("USDT","")
    is_major = coin in ["BTC","ETH","BNB","SOL"]
    macro_score = 1 if regime == "RISK_ON" else (-1 if regime == "RISK_OFF" else 0)
    return {"agent": "MacroAnalyst", "macro_regime": regime, "macro_score": macro_score,
            "is_major_coin": is_major, "analysis": note}


# ============================================================
# RESEARCHER TEAM (TradingAgents Bull vs Bear debate)
# ============================================================

def run_bull_researcher(symbol, analyst_reports):
    bullish = [f"[{r.get('agent')}] {r.get('verdict','') or r.get('sentiment','') or r.get('fundamental_bias','')}"
               for r in analyst_reports if any(x in str(r.get('verdict','') or r.get('sentiment','') or r.get('fundamental_bias',''))
                                               for x in ["BULL","OVERSOLD","RISK_ON"])]
    bearish = [r for r in analyst_reports if any(x in str(r.get('verdict','') or r.get('sentiment','') or r.get('fundamental_bias',''))
                                                 for x in ["BEAR","OVERBOUGHT","RISK_OFF"])]
    bull_strength = len(bullish) / max(len(analyst_reports), 1)
    ctx = " | ".join([r.get("analysis","")[:60] for r in analyst_reports])
    try:
        prompt = f"Bull Researcher: argumentasikan LONG {symbol}. " \
                 f"Sinyal positif: {bullish}. Kontra: {len(bearish)} sinyal negatif. " \
                 f"Konteks: {ctx[:200]}. Argumen BULL 2-3 kalimat. Bahasa Indonesia."
        argument = call_ai(prompt, max_tokens=200)
    except:
        argument = f"{len(bullish)} sinyal bullish mendukung LONG dengan strength {bull_strength:.0%}."
    return {"agent": "BullResearcher", "bull_strength": round(bull_strength, 2),
            "bullish_signals": bullish, "argument": argument}


def run_bear_researcher(symbol, analyst_reports):
    risks = []
    for r in analyst_reports:
        if r.get("rsi", 50) > 70: risks.append("RSI Overbought")
        if r.get("fundamental_bias") == "BEARISH": risks.append("Funding rate tinggi — squeeze risk")
        if r.get("macro_regime") == "RISK_OFF": risks.append("Macro risk-off")
        if r.get("bb_width_pct", 0) > 15: risks.append("Volatilitas ekstrem")
    if not risks: risks = ["Ketidakpastian umum", "Likuiditas tidak pasti"]
    ctx = " | ".join([r.get("analysis","")[:60] for r in analyst_reports])
    try:
        prompt = f"Bear Researcher: identifikasi risiko KONTRA LONG {symbol}. " \
                 f"Faktor risiko: {risks}. Konteks: {ctx[:200]}. " \
                 f"Argumen BEAR 2-3 kalimat (kenapa SKIP lebih aman). Bahasa Indonesia."
        argument = call_ai(prompt, max_tokens=200)
    except:
        argument = f"{len(risks)} faktor risiko: {'; '.join(risks[:3])}."
    return {"agent": "BearResearcher", "bear_strength": round(min(len(risks)/4,1.0),2),
            "risk_factors": risks, "argument": argument}


# ============================================================
# TRADER AGENT (TradingAgents Trader role)
# ============================================================

def run_trader_agent(symbol, price, bull_report, bear_report, analyst_reports):
    bs = bull_report.get("bull_strength", 0.5)
    br = bear_report.get("bear_strength", 0.5)
    net_conviction = bs - br * 0.8
    confidence = max(30, min(95, 50 + net_conviction * 50))

    if confidence >= 65 and bs > br: direction = "LONG"
    elif confidence >= 65 and br > bs + 0.3: direction = "SHORT"
    else: direction = "SKIP"

    try:
        prompt = f"Trader Agent: keputusan final untuk {symbol} @ ${price:,.4f}. " \
                 f"Bull: {bull_report.get('argument','')[:120]}. " \
                 f"Bear: {bear_report.get('argument','')[:120]}. " \
                 f"Net conviction: {net_conviction:.2f}. " \
                 f"Keputusan trading 2 kalimat ({direction}). Bahasa Indonesia."
        decision = call_ai(prompt, max_tokens=150)
    except:
        decision = f"Rekomendasi {direction} dengan confidence {confidence:.0f}%."

    return {"agent": "TraderAgent", "direction": direction,
            "confidence_pct": round(confidence, 1), "net_conviction": round(net_conviction, 3),
            "decision": decision}


# ============================================================
# RISK OFFICER (Vibe-Trading + hummingbot Kelly sizing)
# ============================================================

def run_risk_officer(symbol, price, direction, confidence, market_data, config):
    max_budget_idr = config.get("max_budget_idr", 50000)
    max_leverage = config.get("max_leverage", 10)
    min_rrr = config.get("min_risk_reward_ratio", 1.5)

    change_24h = abs(market_data.get("change_24h_pct", 3))
    bb_width = market_data.get("bb_width_pct", 5)
    volatility = (change_24h + bb_width) / 2

    # Kelly Criterion sizing (ai-hedge-fund inspired)
    win_rate = confidence / 100
    kelly = win_rate - (1 - win_rate) / min_rrr
    kelly = max(0.05, min(0.25, kelly))

    vol_adj = 0.5 if volatility > 10 else (0.75 if volatility > 5 else 1.0)
    budget_idr = max(5000, min(max_budget_idr, int(max_budget_idr * kelly * vol_adj)))

    leverage = min(3, max_leverage) if volatility > 10 else (min(5, max_leverage) if volatility > 5 else min(10, max_leverage))

    atr_pct = volatility * 0.6
    if direction == "LONG":
        sl = price * (1 - atr_pct / 100 * 1.5)
        tp1 = price * (1 + atr_pct / 100 * min_rrr)
        tp2 = price * (1 + atr_pct / 100 * min_rrr * 2)
    elif direction == "SHORT":
        sl = price * (1 + atr_pct / 100 * 1.5)
        tp1 = price * (1 - atr_pct / 100 * min_rrr)
        tp2 = price * (1 - atr_pct / 100 * min_rrr * 2)
    else:
        sl = tp1 = tp2 = price

    risk_pp = abs(price - sl)
    reward_pp = abs(tp1 - price)
    actual_rrr = reward_pp / risk_pp if risk_pp > 0 else 0

    pos_usd = convert_idr_to_usd(budget_idr) * leverage
    var95 = pos_usd * volatility / 100 * 1.65

    risk_approved = actual_rrr >= min_rrr and confidence >= 60 and direction != "SKIP"

    return {
        "agent": "RiskOfficer", "risk_approved": risk_approved,
        "recommended_budget_idr": budget_idr, "recommended_leverage": leverage,
        "kelly_fraction": round(kelly, 3), "vol_adjustment": vol_adj,
        "sl_price": round(sl, 6), "tp1_price": round(tp1, 6), "tp2_price": round(tp2, 6),
        "actual_rrr": round(actual_rrr, 2), "var_95_usd": round(var95, 2),
        "volatility_pct": round(volatility, 2),
        "risk_note": f"VaR(95%)=${var95:.2f}, RRR={actual_rrr:.2f}, Vol={volatility:.1f}%, Kelly={kelly:.1%}"
    }


# ============================================================
# PORTFOLIO MANAGER (TradingAgents + LangAlpha governance)
# ============================================================

def run_portfolio_manager(symbol, trader_report, risk_report, existing_positions, config):
    max_concurrent = config.get("max_concurrent_positions", 5)
    open_pos = [p for p in existing_positions if p.get("status") == "OPEN"]
    rejections = []

    if trader_report.get("direction") == "SKIP":
        rejections.append("Trader merekomendasikan SKIP")
    if not risk_report.get("risk_approved"):
        rejections.append(f"Risk gagal: RRR={risk_report.get('actual_rrr',0):.2f} < min")
    if len(open_pos) >= max_concurrent:
        rejections.append(f"Max posisi ({max_concurrent}) tercapai")
    if symbol in [p.get("symbol") for p in open_pos]:
        rejections.append(f"{symbol} sudah ada posisi aktif")
    if trader_report.get("confidence_pct", 0) < 60:
        rejections.append(f"Confidence {trader_report.get('confidence_pct')}% < 60%")

    approved = len(rejections) == 0
    return {
        "agent": "PortfolioManager", "approved": approved,
        "rejection_reasons": rejections, "open_count": len(open_pos),
        "decision": "APPROVED ?" if approved else f"REJECTED ?: {'; '.join(rejections[:2])}"
    }


# ============================================================
# MARKET MAKING (hummingbot-inspired spread calculator)
# ============================================================

def calculate_optimal_spread(symbol, price, volatility, volume):
    base = {"BTC-USD": 0.05, "ETH-USD": 0.08, "BNB-USD": 0.12, "SOL-USD": 0.15}.get(symbol, 0.20)
    vol_mult = 1 + (volatility / 10)
    vol_disc = 0.7 if volume > 1e9 else (0.85 if volume > 1e8 else 1.0)
    spread = max(0.05, min(1.0, base * vol_mult * vol_disc))
    return {
        "spread_pct": round(spread, 3),
        "bid_price": round(price * (1 - spread/100), 6),
        "ask_price": round(price * (1 + spread/100), 6),
        "midpoint": round(price, 6)
    }


# ============================================================
# THESIS ENGINE (LangAlpha persistent workspace)
# ============================================================

def save_thesis(symbol, result):
    thesis = {}
    if os.path.exists(THESIS_FILE):
        try:
            with open(THESIS_FILE, "r", encoding="utf-8") as f:
                thesis = json.load(f)
        except: pass
    thesis[symbol] = {
        "symbol": symbol, "direction": result.get("direction"),
        "confidence": result.get("confidence_pct"),
        "bull_arg": result.get("bull_researcher",{}).get("argument","")[:150],
        "bear_arg": result.get("bear_researcher",{}).get("argument","")[:150],
        "risk": result.get("risk_officer",{}),
        "approved": result.get("approved"),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    try:
        with open(THESIS_FILE, "w", encoding="utf-8") as f:
            json.dump(thesis, f, indent=2, ensure_ascii=False)
    except: pass


def get_active_thesis(symbol):
    if not os.path.exists(THESIS_FILE): return None
    try:
        with open(THESIS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get(symbol)
    except: return None


# ============================================================
# MAIN COMMITTEE ORCHESTRATOR
# ============================================================

def run_multi_agent_committee(symbol, existing_positions=None):
    """
    Jalankan seluruh committee 7-agent secara terstruktur.
    Returns: dict lengkap dengan semua laporan dan keputusan final.
    """
    if existing_positions is None: existing_positions = []
    config = get_trading_config()
    t0 = time.time()
    print(f"\n[Committee] Menjalankan 7-Agent Committee untuk {symbol}...")

    try:
        market_data = get_market_indicators(symbol)
    except Exception as e:
        print(f"[Committee] Market data error: {e}")
        market_data = {}

    price = market_data.get("price", market_data.get("current_price", 0))
    if not price:
        return {"symbol": symbol, "error": "No market data", "approved": False, "direction": "SKIP"}

    if "bb_width_pct" not in market_data:
        h = market_data.get("high_24h", price * 1.02)
        l = market_data.get("low_24h", price * 0.98)
        market_data["bb_width_pct"] = (h - l) / price * 100 if price > 0 else 5

    volatility = abs(market_data.get("change_24h_pct", 3))
    volume = market_data.get("volume_24h_usd", 0)
    spread_info = calculate_optimal_spread(symbol, price, volatility, volume)

    # Step 2: 4 Analyst PARALEL
    print(f"[Committee] Menjalankan 4 analyst paralel...")
    analyst_map = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(run_technical_analyst, symbol, market_data): "technical",
            ex.submit(run_sentiment_analyst, symbol, market_data): "sentiment",
            ex.submit(run_fundamentals_agent, symbol, market_data): "fundamentals",
            ex.submit(run_macro_analyst, symbol, market_data): "macro",
        }
        for fut in as_completed(futures):
            k = futures[fut]
            try: analyst_map[k] = fut.result()
            except Exception as e: analyst_map[k] = {"agent": k, "error": str(e), "analysis": "Error"}

    reports = list(analyst_map.values())

    # Step 3: Researcher debate
    bull = run_bull_researcher(symbol, reports)
    bear = run_bear_researcher(symbol, reports)

    # Step 4-6: Trader ? Risk ? PM
    trader = run_trader_agent(symbol, price, bull, bear, reports)
    risk = run_risk_officer(symbol, price, trader["direction"], trader["confidence_pct"], market_data, config)
    pm = run_portfolio_manager(symbol, trader, risk, existing_positions, config)

    elapsed = round(time.time() - t0, 2)

    result = {
        "symbol": symbol, "price": price,
        "price_idr": convert_usd_to_idr(price),
        "direction": trader["direction"] if pm["approved"] else "SKIP",
        "approved": pm["approved"],
        "confidence_pct": trader["confidence_pct"],
        "elapsed_sec": elapsed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "spread_info": spread_info,
        "technical_analyst": analyst_map.get("technical", {}),
        "sentiment_analyst": analyst_map.get("sentiment", {}),
        "fundamentals_agent": analyst_map.get("fundamentals", {}),
        "macro_analyst": analyst_map.get("macro", {}),
        "bull_researcher": bull,
        "bear_researcher": bear,
        "trader_agent": trader,
        "risk_officer": risk,
        "portfolio_manager": pm,
        "trade_params": {
            "direction": trader["direction"],
            "budget_idr": risk["recommended_budget_idr"],
            "leverage": risk["recommended_leverage"],
            "sl_price": risk["sl_price"],
            "tp1_price": risk["tp1_price"],
            "tp2_price": risk["tp2_price"],
            "actual_rrr": risk["actual_rrr"],
            "var_95_usd": risk["var_95_usd"],
        } if pm["approved"] else None
    }

    save_thesis(symbol, result)
    _log_result(result)
    print(f"[Committee] {'APPROVED' if pm['approved'] else 'REJECTED'} — {elapsed}s")
    return result


def _log_result(result):
    logs = []
    if os.path.exists(COMMITTEE_LOG_FILE):
        try:
            with open(COMMITTEE_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except: pass
    logs.insert(0, {
        "symbol": result.get("symbol"), "direction": result.get("direction"),
        "approved": result.get("approved"), "confidence": result.get("confidence_pct"),
        "elapsed": result.get("elapsed_sec"), "ts": result.get("timestamp")
    })
    try:
        with open(COMMITTEE_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs[:100], f, indent=2, ensure_ascii=False)
    except: pass


def run_quick_committee(symbol, market_data):
    """Versi cepat rule-based tanpa AI — untuk screening massal."""
    price = market_data.get("price", market_data.get("last_price", 0))
    rsi = market_data.get("rsi_14", 50)
    change_24h = market_data.get("change_24h_pct", market_data.get("price_change_24h_pct", 0))
    volume = market_data.get("volume_24h_usd", 0)

    score = 0
    signals = []
    if rsi < 35: score += 2; signals.append("RSI oversold")
    elif rsi > 65: score -= 1; signals.append("RSI overbought")
    if change_24h > 3: score += 1; signals.append("Momentum positif")
    elif change_24h < -8: score -= 2; signals.append("Downtrend kuat")
    if volume > 5e8: score += 1; signals.append("Volume tinggi")

    if score >= 2: direction, confidence = "LONG", min(85, 50 + score*8)
    elif score <= -2: direction, confidence = "SHORT", min(85, 50 + abs(score)*8)
    else: direction, confidence = "SKIP", 40

    return {
        "symbol": symbol, "quick_score": score, "direction": direction,
        "confidence_pct": confidence, "signals": signals,
        "price": price, "rsi": rsi, "change_24h": change_24h,
        "volume_m": round(volume/1e6, 1), "quick_mode": True
    }
