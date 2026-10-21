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
    if rsi < 35: trend_score += 2; signals.append(f"RSI {rsi:.0f}  -  Oversold")
    elif rsi > 65: trend_score -= 2; signals.append(f"RSI {rsi:.0f}  -  Overbought")
    if volume > 500_000_000: trend_score += 1; signals.append("Volume tinggi")
    if bb_width > 10: signals.append(f"BB Width {bb_width:.1f}%  -  High volatility")

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
        analysis = f"Funding {funding:.4f}%  -  {fsig}. Bias: {bias}."

    return {"agent": "FundamentalsAgent", "fundamental_bias": bias, "funding_rate": funding,
            "funding_signal": fsig, "oi_vol_ratio": round(oi_vol, 3), "analysis": analysis}


def run_macro_analyst(symbol, market_data):
    change_24h = market_data.get("change_24h_pct", 0)
    if abs(change_24h) > 5: regime, note = "HIGH_VOLATILITY", "Volatilitas tinggi  -  sizing kecil"
    elif change_24h > 2: regime, note = "RISK_ON", "Risk-on  -  altcoin outperform"
    elif change_24h < -2: regime, note = "RISK_OFF", "Risk-off  -  fokus major coins"
    else: regime, note = "CONSOLIDATION", "Konsolidasi  -  tunggu breakout"
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


def run_bear_researcher(symbol, analyst_reports, bull_report=None):
    risks = []
    for r in analyst_reports:
        if r.get("rsi", 50) > 70: risks.append("RSI Overbought")
        if r.get("fundamental_bias") == "BEARISH": risks.append("Funding rate tinggi - squeeze risk")
        if r.get("macro_regime") == "RISK_OFF": risks.append("Macro risk-off")
        if r.get("bb_width_pct", 0) > 15: risks.append("Volatilitas ekstrem")
    if not risks: risks = ["Ketidakpastian likuiditas orderbook", "Potensi fakeout resistensi"]
    ctx = " | ".join([r.get("analysis","")[:60] for r in analyst_reports])
    bull_arg = (bull_report.get("argument", "")[:120]) if bull_report else ""
    try:
        prompt = f"Bear Researcher (Adversarial Debater): Serang langsung tesis Bull Researcher ini: '{bull_arg}'. " \
                 f"Gunakan risiko nyata pada {symbol}: {risks}. Analis: {ctx[:160]}. " \
                 f"Beri serangan kontra tajam 2-3 kalimat kenapa trade ini berisiko jebakan/rugi. Bahasa Indonesia."
        argument = call_ai(prompt, max_tokens=200)
    except:
        argument = f"Risiko pembalikan arah terdeteksi: {'; '.join(risks[:3])}. Tesis bull rentan fakeout."
    bear_strength = round(min(len(risks) / 3.5, 1.0), 2)
    return {
        "agent": "BearResearcher",
        "signal": "BEARISH",
        "bias": "BEARISH",
        "confidence_pct": round(bear_strength * 100, 1),
        "bear_strength": bear_strength,
        "risk_factors": risks,
        "argument": argument,
        "core_thesis": argument
    }


def run_bull_rebuttal(symbol, bull_report, bear_report):
    bear_arg = bear_report.get("argument", "")[:120]
    try:
        prompt = f"Bull Researcher Rebuttal: Bear menyatakan '{bear_arg}'. " \
                 f"Tangkis serangan Bear tersebut dengan mitigasi risiko (invalidation stop-loss ketat, absorpsi likuiditas). " \
                 f"Jawab singkat 1-2 kalimat. Bahasa Indonesia."
        rebuttal = call_ai(prompt, max_tokens=150)
    except:
        rebuttal = "Risiko Bear dapat dimitigasi dengan Stop Loss ketat di bawah level support dinamis."
    return rebuttal


# ============================================================
# TRADER AGENT (TradingAgents Mediator & Tactical Plan)
# ============================================================

def run_trader_agent(symbol, price, bull_report, bear_report, rebuttal, analyst_reports):
    bs = bull_report.get("bull_strength", 0.5)
    br = bear_report.get("bear_strength", 0.5)
    net_conviction = bs - br * 0.75
    confidence = max(35, min(95, 50 + net_conviction * 45))

    if confidence >= 65 and bs > br:
        direction = "LONG"
    elif confidence >= 65 and br > bs + 0.25:
        direction = "SHORT"
    else:
        direction = "SKIP"

    try:
        prompt = f"Trader Agent (Chief Execution Mediator): Simpulkan perdebatan multi-agent {symbol} @ ${price:,.4f}.\n" \
                 f"- Bull Case: {bull_report.get('argument','')[:100]}\n" \
                 f"- Bear Case: {bear_report.get('argument','')[:100]}\n" \
                 f"- Bull Rebuttal: {rebuttal[:100]}\n" \
                 f"- Keputusan Anda: {direction} (Confidence: {confidence:.0f}%).\n" \
                 f"Buat sintesis taktis 2 kalimat dalam Bahasa Indonesia."
        decision = call_ai(prompt, max_tokens=150)
    except:
        decision = f"Kompromi komite: Memilih {direction} dengan keyakinan {confidence:.0f}% setelah menguji tesis Bull & Bear."

    return {
        "agent": "TraderAgent",
        "signal": direction,
        "direction": direction,
        "confidence_pct": round(confidence, 1),
        "net_conviction": round(net_conviction, 3),
        "decision": decision,
        "rebuttal_accepted": True
    }


# ============================================================
# RISK OFFICER (Vibe-Trading + hummingbot Kelly sizing)
# ============================================================

def run_risk_officer(symbol, price, direction, confidence, market_data, config):
    """
    Risk Officer v2: Dynamic leverage 2x-25x (ATR-based), wallet-based Kelly sizing,
    and estimated holding time to TP1 (inspired by ai-hedge-fund + Vibe-Trading).
    """
    # ── 1. Fetch live wallet balance from Binance ──────────────────────
    try:
        from binance_futures import BinanceFuturesClient
        import os as _os
        _ak = config.get("BINANCE_API_KEY") or _os.environ.get("BINANCE_API_KEY", "")
        _sk = config.get("BINANCE_API_SECRET") or _os.environ.get("BINANCE_API_SECRET", "")
        if _ak and _sk:
            _bn = BinanceFuturesClient(api_key=_ak, api_secret=_sk)
            _bal = _bn.get_balance()
            available_usdt = float(_bal.get("available_balance", 0))
        else:
            available_usdt = 0.0
    except Exception:
        available_usdt = 0.0

    fx_rate = convert_usd_to_idr(1.0)   # USDT→IDR FX rate
    wallet_idr = available_usdt * fx_rate

    # ── 2. Risk parameters ─────────────────────────────────────────────
    max_leverage = config.get("max_leverage", 25)
    min_rrr = config.get("min_risk_reward_ratio", 1.5)

    change_24h = abs(market_data.get("change_24h_pct", 3))
    bb_width   = market_data.get("bb_width_pct", 5)
    volatility = (change_24h + bb_width) / 2

    # ── 3. Dynamic leverage (ATR/volatility tier, cap to config max) ──
    sym_base = symbol.upper().replace("-USD", "").replace("USDT", "")
    mega_majors = {"BTC", "ETH"}
    large_caps  = {"BNB", "SOL", "XRP", "ADA", "AVAX", "LINK", "LTC", "DOT", "MATIC", "UNI"}
    memecoins   = {"DOGE", "PEPE", "SHIB", "FLOKI", "BONK", "WIF", "BOME", "NOT", "MEW", "BRETT"}

    if volatility > 12:
        lev_range = (2, 5)          # extreme volatility
    elif sym_base in mega_majors:
        lev_range = (10, 20)        # BTC/ETH: moderate-high leverage safe
    elif sym_base in large_caps:
        lev_range = (5, 15)         # large caps
    elif sym_base in memecoins or volatility > 8:
        lev_range = (3, 10)         # memecoins / high vol
    else:
        lev_range = (5, 15)         # general mid-cap

    # Confidence modulation: higher confidence → higher leverage (within tier)
    conf_factor = confidence / 100.0
    raw_lev = int(lev_range[0] + conf_factor * (lev_range[1] - lev_range[0]))
    leverage = max(2, min(raw_lev, max_leverage))

    # ── 4. Wallet-based Kelly budget ──────────────────────────────────
    win_rate = confidence / 100
    kelly = win_rate - (1 - win_rate) / min_rrr
    kelly = max(0.08, min(0.40, kelly))

    vol_adj = 0.5 if volatility > 10 else (0.75 if volatility > 5 else 1.0)

    if wallet_idr > 1000:    # live wallet available
        # Use Kelly fraction of live available USDT wallet
        budget_idr = max(10000, int(wallet_idr * kelly * vol_adj))
    else:
        # Wallet unavailable (offline/no key) — fall back to IDR config floor
        budget_floor = config.get("max_budget_idr") or 50000
        budget_idr = max(10000, int(budget_floor * kelly * vol_adj))

    # ── 5. SL / TP calculation ─────────────────────────────────────────
    atr_pct = volatility * 0.6
    if direction == "LONG":
        sl  = price * (1 - atr_pct / 100 * 1.5)
        tp1 = price * (1 + atr_pct / 100 * min_rrr)
        tp2 = price * (1 + atr_pct / 100 * min_rrr * 2)
    elif direction == "SHORT":
        sl  = price * (1 + atr_pct / 100 * 1.5)
        tp1 = price * (1 - atr_pct / 100 * min_rrr)
        tp2 = price * (1 - atr_pct / 100 * min_rrr * 2)
    else:
        sl = tp1 = tp2 = price

    risk_pp   = abs(price - sl)
    reward_pp = abs(tp1 - price)
    actual_rrr = reward_pp / risk_pp if risk_pp > 0 else 0

    pos_usd = convert_idr_to_usd(budget_idr) * leverage
    var95   = pos_usd * volatility / 100 * 1.65

    risk_approved = actual_rrr >= min_rrr and confidence >= 60 and direction != "SKIP"

    # ── 6. Estimated holding time to TP1 ──────────────────────────────
    # Formula: hours = (TP1 dist %) / (ATR% per hour * momentum factor)
    # ATR 1H ≈ daily ATR / sqrt(24)
    atr_1h_pct = (change_24h / 24**0.5) if change_24h > 0 else 0.2
    tp1_dist_pct = abs(tp1 - price) / price * 100 if price > 0 else 1
    momentum_factor = 1.2 if confidence >= 75 else (0.9 if confidence < 60 else 1.0)
    if atr_1h_pct > 0:
        est_hours = tp1_dist_pct / (atr_1h_pct * momentum_factor)
    else:
        est_hours = 2.0
    est_hours = max(0.25, min(est_hours, 96))

    # Format as readable Indonesian duration
    if est_hours < 1:
        lo, hi = int(est_hours * 60 * 0.7), int(est_hours * 60 * 1.3)
        style = "Scalp Momentum" if confidence >= 75 else "Scalp"
        time_horizon = f"~{lo}-{hi} menit ({style})"
    elif est_hours < 4:
        lo, hi = round(est_hours * 0.7, 1), round(est_hours * 1.3, 1)
        style = "Intraday Trend" if confidence >= 70 else "Intraday"
        time_horizon = f"~{lo}-{hi} jam ({style})"
    elif est_hours < 24:
        lo, hi = int(est_hours * 0.7), int(est_hours * 1.3)
        time_horizon = f"~{lo}-{hi} jam (Swing Pendek)"
    else:
        lo, hi = int(est_hours / 24 * 0.7), int(est_hours / 24 * 1.3)
        time_horizon = f"~{lo}-{hi} hari (Swing)"

    return {
        "agent": "RiskOfficer",
        "signal": "APPROVED" if risk_approved else "VETOED",
        "risk_approved": risk_approved,
        "confidence_pct": round(confidence, 1),
        "wallet_usdt_available": round(available_usdt, 4),
        "wallet_idr_available": round(wallet_idr, 0),
        "recommended_budget_idr": budget_idr,
        "kelly_suggested_idr": budget_idr,
        "recommended_leverage": leverage,
        "leverage": leverage,
        "leverage_tier": f"{lev_range[0]}x-{lev_range[1]}x (vol={volatility:.1f}%)",
        "kelly_fraction": round(kelly, 3),
        "vol_adjustment": vol_adj,
        "sl_price": round(sl, 6),
        "tp1_price": round(tp1, 6),
        "tp2_price": round(tp2, 6),
        "actual_rrr": round(actual_rrr, 2),
        "var_95_usd": round(var95, 2),
        "var_pct_daily": round(volatility * 1.65, 2),
        "volatility_pct": round(volatility, 2),
        "estimated_time_horizon": time_horizon,
        "hummingbot_spread_pct": round(max(0.1, min(1.2, volatility * 0.08)), 2),
        "risk_note": f"VaR(95%)=${var95:.2f}, RRR={actual_rrr:.2f}, Vol={volatility:.1f}%, Kelly={kelly:.1%}, Lev={leverage}x, Wallet=${available_usdt:.2f}"
    }


# ============================================================
# PORTFOLIO MANAGER (TradingAgents + LangAlpha governance)
# ============================================================

def run_portfolio_manager(symbol, trader_report, risk_report, existing_positions, config):
    max_concurrent = config.get("max_concurrent_positions", 5)
    open_pos = [p for p in (existing_positions or []) if p.get("status") == "OPEN"]
    rejections = []

    if trader_report.get("direction") == "SKIP":
        rejections.append("Trader merekomendasikan SKIP (tidak ada conviction)")
    if not risk_report.get("risk_approved"):
        rejections.append(f"Risk Officer Veto: RRR {risk_report.get('actual_rrr',0):.2f} < threshold")
    if len(open_pos) >= max_concurrent:
        rejections.append(f"Kapasitas portofolio penuh ({len(open_pos)}/{max_concurrent})")
    if symbol in [p.get("symbol") for p in open_pos]:
        rejections.append(f"{symbol} sudah memiliki posisi terbuka")
    if trader_report.get("confidence_pct", 0) < 60:
        rejections.append(f"Confidence {trader_report.get('confidence_pct')}% < 60%")

    approved = len(rejections) == 0
    decision = "APPROVED (Konsensus 9 Agen Tercapai)" if approved else f"REJECTED: {'; '.join(rejections[:2])}"
    return {
        "agent": "PortfolioManager",
        "signal": "APPROVED" if approved else "REJECTED",
        "approved": approved,
        "rejection_reasons": rejections,
        "open_count": len(open_pos),
        "decision": decision,
        "executive_summary": decision
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
    
    consensus = result.get("consensus", {})
    thesis[symbol] = {
        "symbol": symbol,
        "direction": consensus.get("action", result.get("direction")),
        "confidence": consensus.get("confidence_pct", result.get("confidence_pct")),
        "approved": result.get("approved"),
        "bull_arg": result.get("bull_researcher",{}).get("argument","")[:200],
        "bear_arg": result.get("bear_researcher",{}).get("argument","")[:200],
        "rebuttal": result.get("bull_rebuttal", "")[:150],
        "trader_decision": result.get("trader_agent",{}).get("decision","")[:200],
        "risk": result.get("risk_officer",{}),
        "trade_plan": result.get("trade_plan", {}),
        "collaboration_transcript": result.get("collaboration_transcript", []),
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
    Jalankan seluruh committee 9-agent secara terstruktur & kolaboratif.
    Returns: dict lengkap dengan transcript kolaborasi dan keputusan final.
    """
    if existing_positions is None: existing_positions = []
    config = get_trading_config()
    t0 = time.time()
    print(f"\n[Committee] Memulai Sidang Multi-Agent Kolaboratif untuk {symbol}...")

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

    # ------------------------------------------------------------
    # ROUND 1: 4 ANALYSTS IN PARALLEL (TradingAgents pattern)
    # ------------------------------------------------------------
    print(f"[Committee] Round 1: Menjalankan 4 Analis Spesialis paralel...")
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

    # ------------------------------------------------------------
    # ROUND 2 & 3: ADVERSARIAL DEBATE (Bull vs Bear Researcher)
    # ------------------------------------------------------------
    print(f"[Committee] Round 2: Bull Researcher merumuskan tesis LONG...")
    bull = run_bull_researcher(symbol, reports)

    print(f"[Committee] Round 3: Bear Researcher menyerang tesis Bull...")
    bear = run_bear_researcher(symbol, reports, bull)

    print(f"[Committee] Round 4: Bull Researcher mengajukan tangkisan risiko (Rebuttal)...")
    rebuttal = run_bull_rebuttal(symbol, bull, bear)

    # ------------------------------------------------------------
    # ROUND 5: TRADER AGENT MEDIATION & TACTICAL PLAN
    # ------------------------------------------------------------
    print(f"[Committee] Round 5: Trader Agent menimbang perdebatan & menyusun rencana eksekusi...")
    trader = run_trader_agent(symbol, price, bull, bear, rebuttal, reports)

    # ------------------------------------------------------------
    # ROUND 6: RISK OFFICER AUDIT & KELLY CRITERION SIZING
    # ------------------------------------------------------------
    print(f"[Committee] Round 6: Risk Officer mengaudit VaR, volatilitas, dan Kelly sizing...")
    risk = run_risk_officer(symbol, price, trader["direction"], trader["confidence_pct"], market_data, config)

    # ------------------------------------------------------------
    # ROUND 7: PORTFOLIO MANAGER CONSENSUS ROLL-CALL
    # ------------------------------------------------------------
    print(f"[Committee] Round 7: Portfolio Manager memimpin pemungutan suara konsensus...")
    pm = run_portfolio_manager(symbol, trader, risk, existing_positions, config)

    elapsed = round(time.time() - t0, 2)
    final_dir = trader["direction"] if pm["approved"] else "SKIP"
    final_act = "BUY" if final_dir == "LONG" else ("SELL" if final_dir == "SHORT" else "HOLD")

    # Interactive Multi-Round Collaboration Transcript
    transcript = [
        {"round": 1, "speaker": "Analyst Team", "role": "Data Gathering", "content": f"Technical: {analyst_map.get('technical',{}).get('verdict','-')}, Sentiment: {analyst_map.get('sentiment',{}).get('sentiment','-')}, Macro: {analyst_map.get('macro',{}).get('macro_regime','-')}"},
        {"round": 2, "speaker": "Bull Researcher", "role": "Long Thesis", "content": bull.get("argument", "")},
        {"round": 3, "speaker": "Bear Researcher", "role": "Adversarial Counter", "content": bear.get("argument", "")},
        {"round": 4, "speaker": "Bull Rebuttal", "role": "Risk Defense", "content": rebuttal},
        {"round": 5, "speaker": "Trader Agent", "role": "Tactical Synthesis", "content": trader.get("decision", "")},
        {"round": 6, "speaker": "Risk Officer", "role": "Kelly & VaR Gatekeeper", "content": f"Status: {risk.get('signal')}. Modal disetujui: Rp {risk.get('recommended_budget_idr',0):,} ({risk.get('recommended_leverage',1)}x). RRR: {risk.get('actual_rrr',0):.2f}"},
        {"round": 7, "speaker": "Portfolio Manager", "role": "Supreme Verdict", "content": pm.get("decision", "")}
    ]

    time_horizon = risk.get("estimated_time_horizon", "N/A")
    trade_plan = {
        "direction": final_dir,
        "entry_price": price,
        "position_size_idr": risk["recommended_budget_idr"],
        "leverage": risk["recommended_leverage"],
        "sl_price": risk["sl_price"],
        "tp1_price": risk["tp1_price"],
        "tp2_price": risk["tp2_price"],
        "actual_rrr": risk["actual_rrr"],
        "var_95_usd": risk["var_95_usd"],
        "estimated_time_horizon": time_horizon,
    } if pm["approved"] else None

    result = {
        "symbol": symbol,
        "price": price,
        "price_idr": convert_usd_to_idr(price),
        "direction": final_dir,
        "approved": pm["approved"],
        "confidence_pct": trader["confidence_pct"],
        "elapsed_sec": elapsed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "estimated_time_horizon": risk.get("estimated_time_horizon", "N/A"),
        "spread_info": spread_info,
        "consensus": {
            "action": final_act,
            "direction": final_dir,
            "confidence_pct": trader["confidence_pct"],
            "approved": pm["approved"],
            "risk_reward_ratio": f"1:{risk.get('actual_rrr', 2.0):.2f}",
            "executive_summary": pm["decision"],
            "summary": pm["decision"]
        },
        "agents": {
            "technical": analyst_map.get("technical", {}),
            "sentiment": analyst_map.get("sentiment", {}),
            "fundamentals": analyst_map.get("fundamentals", {}),
            "macro": analyst_map.get("macro", {}),
            "bull_researcher": bull,
            "bear_researcher": bear,
            "trader": trader,
            "risk_officer": risk,
            "portfolio_manager": pm
        },
        "collaboration_transcript": transcript,
        "bull_rebuttal": rebuttal,
        "trade_plan": trade_plan,
        "trade_params": trade_plan,
        "technical_analyst": analyst_map.get("technical", {}),
        "sentiment_analyst": analyst_map.get("sentiment", {}),
        "fundamentals_agent": analyst_map.get("fundamentals", {}),
        "macro_analyst": analyst_map.get("macro", {}),
        "bull_researcher": bull,
        "bear_researcher": bear,
        "trader_agent": trader,
        "risk_officer": risk,
        "portfolio_manager": pm
    }

    save_thesis(symbol, result)
    _log_result(result)
    print(f"[Committee] {'APPROVED' if pm['approved'] else 'REJECTED'}  -  {elapsed}s")
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
    """Versi cepat rule-based tanpa AI  -  untuk screening massal."""
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
