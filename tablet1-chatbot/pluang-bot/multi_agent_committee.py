"""
===========================================================================
PYROFUEL MULTI-AGENT COMMITTEE ENGINE v3.0 (ADVERSARIAL VETO-ONLY EDITION)
===========================================================================
Terinspirasi dari:
- TradingAgents (Tauric Research): Multi-agent adversarial LLM framework
- ai-hedge-fund (virattt): Investor-persona agents & conviction synthesis
- Vibe-Trading (HKUDS): Regime & memory-aware risk governance
- LangAlpha (ginlix): Thesis-driven persistent research workspace
- hummingbot: Market making spread calculation

ARSITEKTUR v3.0 (VETO-ONLY, DIRECTION-SYMMETRIC, GEAR & AI-MEMORY AWARE):
  1. Dipanggil HANYA jika Layer 5 Supreme Judge sudah APPROVED (hemat token).
  2. Reuses exact Layer 1 532-factor quant + L2 OBI-20 + Hurst + ADX + RSI15m
     + BTC 4H Macro + AI Trade Memory (ZERO redundant market fetches).
  3. Direction-Symmetric Adversarial Debate:
     - Advocate Researcher (Pro-Setup) membela arah sinyal (LONG atau SHORT)
     - Red-Team Adversary (Bear/Skeptic) mencari jebakan/fakeout/divergensi BTC/
       pola kalah di AI Trade Memory terhadap arah sinyal tersebut
     - Advocate Rebuttal menangkis serangan dengan SL/TP1/RRR struktural
  4. Gear-Aware Risk Officer (Audit-Only):
     - Mengikuti leverage & sizing Sistem Gigi aktif (G1 20x / G2 12x / G3 8x)
     - TIDAK PERNAH menimpa SL/TP/Entry/Direction tervalidasi dari Layer 3/5!
  5. AI Supreme Portfolio Manager (Veto-Only Judge):
     - Menimbang seluruh debat + AI Trade Memory dan memutus APPROVE atau VETO.
===========================================================================
"""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from pipeline import call_ai, get_trading_config, RESULTS_DIR
    from market_data import get_market_indicators, convert_usd_to_idr, convert_idr_to_usd
except ImportError:
    def call_ai(p, **kw): return "N/A"
    def get_trading_config(): return {}
    def convert_usd_to_idr(x): return x * 16500
    def convert_idr_to_usd(x): return x / 16500
    def get_market_indicators(s): return {}
    RESULTS_DIR = "results"

try:
    import state_io
except ImportError:
    state_io = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMMITTEE_LOG_FILE = os.path.join(RESULTS_DIR, "committee_log.json")
THESIS_FILE = os.path.join(RESULTS_DIR, "active_thesis.json")


def _normalize_funding_pct(raw_funding: Any) -> float:
    """Normalize funding rate to percentage (e.g., 0.0001 decimal -> 0.01%)."""
    if isinstance(raw_funding, dict):
        if raw_funding.get("funding_rate_pct") is not None:
            try:
                v = float(raw_funding["funding_rate_pct"])
                return round(v * 100.0, 4) if (0.0 < abs(v) < 0.005) else round(v, 4)
            except (TypeError, ValueError):
                pass
        raw_val = raw_funding.get("funding_rate_raw", raw_funding.get("funding_rate", 0.0))
    else:
        raw_val = raw_funding
    try:
        v = float(raw_val or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if 0.0 < abs(v) < 0.005:
        return round(v * 100.0, 4)
    return round(v, 4)


def _extract_json_obj(raw_text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None
    s = raw_text.strip()
    if "```" in s:
        s = re.sub(r"```(?:json)?", "", s).strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _resolve_active_gear_profile(config: Dict[str, Any], pipeline_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if isinstance(pipeline_context, dict) and isinstance(pipeline_context.get("active_gear"), dict):
        return dict(pipeline_context["active_gear"])
    try:
        g_path = os.path.join(RESULTS_DIR, "gear_state.json")
        if state_io is not None and os.path.exists(g_path):
            gd = state_io.read_json_safe(g_path, default=None, strict_on_corrupt=False, expected_type=dict)
            if isinstance(gd, dict) and isinstance(gd.get("active_profile"), dict):
                prof = dict(gd["active_profile"])
                prof.setdefault("gear", gd.get("current_gear", 1))
                return prof
    except Exception:
        pass
    return {
        "gear": 1,
        "code": "GEAR_1_TURBO",
        "leverage": int(config.get("fixed_leverage", 20) or 20),
        "sizing_mode": str(config.get("sizing_mode", "ALL_IN")).upper(),
        "all_in_balance_fraction": float(config.get("all_in_balance_fraction", 0.95) or 0.95),
        "risk_pct": float(config.get("risk_pct", 5.0) or 5.0),
    }


# ============================================================
# ANALYST TEAM (Round 1 — uses live Layer 1 quant/micro data!)
# ============================================================

def run_technical_analyst(symbol: str, market_data: dict, use_llm: bool = True):
    price = float(market_data.get("live_price") or market_data.get("price") or market_data.get("current_price") or 0)
    rsi = float(market_data.get("rsi_14", 50) or 50)
    ema_trend = str(market_data.get("ema_trend") or "NEUTRAL").upper()
    ema20 = float(market_data.get("ema_20", price) or price)
    ema50 = float(market_data.get("ema_50", price) or price)
    change_24h = float(market_data.get("change_24h_pct", 0) or 0)
    volume = float(market_data.get("volume_24h_usd", 0) or 0)
    high_24h = float(market_data.get("high_24h", price * 1.02) or (price * 1.02))
    low_24h = float(market_data.get("low_24h", price * 0.98) or (price * 0.98))
    bb_width = (high_24h - low_24h) / price * 100 if price > 0 else 5.0

    mp = market_data.get("math_proof") if isinstance(market_data.get("math_proof"), dict) else {}
    hurst = float(mp.get("hurst_exponent", 0.50) or 0.50)
    adx14 = float(mp.get("adx_14", 0.0) or 0.0)
    obi20 = float(mp.get("obi_weighted_20", 0.0) or 0.0)
    p_math = float(mp.get("p_math_pct", 50.0) or 50.0)
    stat_reg = str(mp.get("statistical_regime", "NORMAL") or "NORMAL")

    trend_score = 0
    signals: List[str] = []
    if "BULL" in ema_trend or price > ema20:
        trend_score += 1
        signals.append("Struktur EMA Bullish")
    elif "BEAR" in ema_trend or price < ema20:
        trend_score -= 1
        signals.append("Struktur EMA Bearish")
    if ema20 > ema50:
        trend_score += 1
    elif ema20 < ema50:
        trend_score -= 1
    if rsi < 35:
        trend_score += 2
        signals.append(f"RSI {rsi:.1f} Oversold")
    elif rsi > 65:
        trend_score -= 2
        signals.append(f"RSI {rsi:.1f} Overbought")
    if obi20 >= 0.15:
        trend_score += 1
        signals.append(f"OBI-20 Beli ({obi20:+.2f})")
    elif obi20 <= -0.15:
        trend_score -= 1
        signals.append(f"OBI-20 Jual ({obi20:+.2f})")
    if volume > 250_000_000:
        signals.append(f"Likuiditas Kuat (${volume/1e6:.0f}M)")
    signals.append(f"Regime={stat_reg} (H={hurst:.2f}, ADX={adx14:.1f}, P_Math={p_math:.1f}%)")

    verdict = "BULLISH" if trend_score >= 2 else ("BEARISH" if trend_score <= -2 else "NEUTRAL")
    analysis = f"Trend {verdict}. RSI={rsi:.1f}, EMA={ema_trend}, OBI20={obi20:+.2f}, Regime={stat_reg} (H={hurst:.2f}, ADX={adx14:.1f})."
    if use_llm:
        try:
            prompt = (
                f"Technical Analyst crypto futures. {symbol}: Harga=${price:,.4f}, RSI={rsi:.1f}, "
                f"EMA={ema_trend}, OBI20={obi20:+.2f}, Hurst={hurst:.2f}, ADX={adx14:.1f}, Regime={stat_reg}. "
                f"Analisis teknikal 2 kalimat padat, Bahasa Indonesia."
            )
            analysis = call_ai(
                prompt,
                system_prompt="You are a professional crypto technical analyst. Answer concisely in Indonesian.",
                max_tokens=160,
                is_json=False,
            )
        except Exception as e:
            print(f"[Committee] TechnicalAnalyst AI error: {e}", flush=True)

    return {
        "agent": "TechnicalAnalyst",
        "verdict": verdict,
        "trend_score": trend_score,
        "signals": signals,
        "rsi": rsi,
        "bb_width_pct": round(bb_width, 2),
        "obi_20": obi20,
        "hurst": hurst,
        "adx_14": adx14,
        "stat_regime": stat_reg,
        "analysis": analysis,
    }


def run_sentiment_analyst(symbol: str, market_data: dict, use_llm: bool = True):
    change_24h = float(market_data.get("change_24h_pct", 0) or 0)
    volume = float(market_data.get("volume_24h_usd", 0) or 0)
    news_m = market_data.get("news_macro") if isinstance(market_data.get("news_macro"), dict) else {}
    news_sent = str(news_m.get("market_sentiment", "NEUTRAL")).upper()

    if change_24h > 8:
        sentiment, fg = "EXTREME_BULLISH", 82
    elif change_24h > 3:
        sentiment, fg = "BULLISH", 66
    elif change_24h > 0:
        sentiment, fg = "SLIGHTLY_BULLISH", 54
    elif change_24h > -3:
        sentiment, fg = "SLIGHTLY_BEARISH", 44
    elif change_24h > -8:
        sentiment, fg = "BEARISH", 32
    else:
        sentiment, fg = "EXTREME_FEAR", 18

    analysis = f"Sentimen {sentiment.replace('_', ' ').title()} (24h {change_24h:+.2f}%), News={news_sent}, F&G ~{fg}/100."
    if use_llm:
        try:
            prompt = (
                f"Sentiment Analyst crypto. {symbol}: Change 24h={change_24h:+.2f}%, "
                f"Vol=${volume/1e6:.0f}M, News={news_sent}, Proxy={sentiment} (F&G~{fg}). "
                f"Analisis sentimen 2 kalimat padat, Bahasa Indonesia."
            )
            analysis = call_ai(
                prompt,
                system_prompt="You are a professional crypto sentiment analyst. Answer concisely in Indonesian.",
                max_tokens=150,
                is_json=False,
            )
        except Exception as e:
            print(f"[Committee] SentimentAnalyst AI error: {e}", flush=True)

    return {
        "agent": "SentimentAnalyst",
        "sentiment": sentiment,
        "news_sentiment": news_sent,
        "fear_greed": fg,
        "change_24h": change_24h,
        "analysis": analysis,
    }


def run_fundamentals_agent(symbol: str, market_data: dict, use_llm: bool = True):
    volume = float(market_data.get("volume_24h_usd", 0) or 0)
    oi = float(market_data.get("open_interest_usd", volume * 0.3) or (volume * 0.3))
    funding_pct = _normalize_funding_pct(market_data.get("funding_rate", 0.0))

    if funding_pct >= 0.05:
        bias, fsig = "BEARISH", f"Longs terlalu padat (+{funding_pct:.4f}% — risiko long squeeze)"
    elif funding_pct >= 0.015:
        bias, fsig = "NEUTRAL_BULLISH", f"Funding positif terkendali (+{funding_pct:.4f}%)"
    elif funding_pct <= -0.05:
        bias, fsig = "BULLISH", f"Shorts terlalu padat ({funding_pct:.4f}% — potensi short squeeze)"
    elif funding_pct <= -0.015:
        bias, fsig = "NEUTRAL_BEARISH", f"Funding negatif terkendali ({funding_pct:.4f}%)"
    else:
        bias, fsig = "NEUTRAL", f"Funding seimbang ({funding_pct:+.4f}%)"

    oi_vol = oi / volume if volume > 0 else 0.3
    analysis = f"Funding {funding_pct:+.4f}% — {fsig}. OI/Vol={oi_vol:.2f}, Bias={bias}."
    if use_llm:
        try:
            prompt = (
                f"On-Chain & Derivatives Analyst crypto futures. {symbol}: Vol=${volume/1e6:.0f}M, "
                f"OI/Vol={oi_vol:.2f}, Funding={funding_pct:+.4f}% ({fsig}). "
                f"Analisis derivatif 2 kalimat padat, Bahasa Indonesia."
            )
            analysis = call_ai(
                prompt,
                system_prompt="You are a professional on-chain and derivatives analyst. Answer concisely in Indonesian.",
                max_tokens=150,
                is_json=False,
            )
        except Exception as e:
            print(f"[Committee] FundamentalsAgent AI error: {e}", flush=True)

    return {
        "agent": "FundamentalsAgent",
        "fundamental_bias": bias,
        "funding_rate": funding_pct,
        "funding_rate_pct": funding_pct,
        "funding_signal": fsig,
        "oi_vol_ratio": round(oi_vol, 3),
        "analysis": analysis,
    }


def run_macro_analyst(symbol: str, market_data: dict, btc_macro: Optional[dict] = None):
    change_24h = float(market_data.get("change_24h_pct", 0) or 0)
    btc_m = btc_macro if isinstance(btc_macro, dict) else {}
    btc_4h = float(btc_m.get("btc_4h_pct", 0.0) or 0.0)
    btc_tr = str(btc_m.get("btc_1h_trend", "UNKNOWN")).upper()

    if abs(btc_4h) >= 1.6:
        regime = "RISK_ON" if btc_4h > 0 else "RISK_OFF"
        note = f"BTC 4H impulse kuat ({btc_4h:+.2f}%, {btc_tr}) — altcoin wajib searah BTC"
    elif abs(change_24h) > 6.5:
        regime, note = "HIGH_VOLATILITY", f"Volatilitas tinggi (24h {change_24h:+.1f}%) — waspada fakeout wick"
    elif change_24h > 2:
        regime, note = "RISK_ON", f"Risk-on moderat (BTC 4H {btc_4h:+.2f}%)"
    elif change_24h < -2:
        regime, note = "RISK_OFF", f"Risk-off moderat (BTC 4H {btc_4h:+.2f}%)"
    else:
        regime, note = "CONSOLIDATION", f"Konsolidasi / range (BTC 4H {btc_4h:+.2f}%)"

    coin = symbol.replace("-USD", "").replace("USDT", "").upper()
    is_major = coin in {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "AVAX", "LINK", "SUI", "LTC"}
    macro_score = 1 if regime == "RISK_ON" else (-1 if regime == "RISK_OFF" else 0)
    return {
        "agent": "MacroAnalyst",
        "macro_regime": regime,
        "macro_score": macro_score,
        "btc_4h_pct": btc_4h,
        "btc_trend": btc_tr,
        "is_major_coin": is_major,
        "analysis": note,
    }


# ============================================================
# RESEARCHER TEAM (Direction-Symmetric Pro vs Red-Team Debate)
# ============================================================

def run_bull_researcher(
    symbol: str,
    analyst_reports: list,
    proposed_direction: str = "LONG",
    setup_name: str = "AI_SETUP",
    memory_context: str = "",
):
    """Advocate Researcher defending the proposed setup direction (LONG or SHORT)."""
    dir_u = str(proposed_direction or "LONG").upper()
    if dir_u not in ("LONG", "SHORT"):
        dir_u = "LONG"

    align_tokens = ("BULL", "OVERSOLD", "RISK_ON") if dir_u == "LONG" else ("BEAR", "OVERBOUGHT", "RISK_OFF")
    opp_tokens = ("BEAR", "OVERBOUGHT", "RISK_OFF") if dir_u == "LONG" else ("BULL", "OVERSOLD", "RISK_ON")

    pro_sigs = [
        f"[{r.get('agent')}] {r.get('verdict', '') or r.get('sentiment', '') or r.get('fundamental_bias', '') or r.get('macro_regime', '')}"
        for r in analyst_reports
        if any(x in str(r.get("verdict", "") or r.get("sentiment", "") or r.get("fundamental_bias", "") or r.get("macro_regime", "")) for x in align_tokens)
    ]
    opp_sigs = [
        r for r in analyst_reports
        if any(x in str(r.get("verdict", "") or r.get("sentiment", "") or r.get("fundamental_bias", "") or r.get("macro_regime", "")) for x in opp_tokens)
    ]
    advocate_strength = max(0.35, min(0.95, (len(pro_sigs) + 1) / max(len(analyst_reports) + 1, 2)))
    ctx = " | ".join([str(r.get("analysis", ""))[:95] for r in analyst_reports])
    mem_snippet = f" Memori AI: {memory_context[:140]}." if memory_context else ""

    try:
        prompt = (
            f"Advocate Researcher ({'Bull' if dir_u == 'LONG' else 'Short'} Thesis): "
            f"Argumentasikan secara objektif kenapa {dir_u} {symbol} ({setup_name}) punya edge kuat. "
            f"Konfluensi searah: {pro_sigs or ['Layer1-5 Approved']}. Kontra: {len(opp_sigs)}. "
            f"Data: {ctx[:260]}.{mem_snippet} "
            f"Tulis 2-3 kalimat padat berbasis data. Bahasa Indonesia."
        )
        argument = call_ai(
            prompt,
            system_prompt=f"You are an institutional trading advocate evaluating a {dir_u} futures setup. Be concise and factual in Indonesian.",
            max_tokens=180,
            is_json=False,
        )
    except Exception as e:
        print(f"[Committee] AdvocateResearcher AI error: {e}", flush=True)
        argument = f"Setup {setup_name} ({dir_u}) didukung {len(pro_sigs)} konfluensi analis dengan kekuatan {advocate_strength:.0%}."

    return {
        "agent": "BullResearcher",
        "advocate_direction": dir_u,
        "bull_strength": round(advocate_strength, 2),
        "bullish_signals": pro_sigs,
        "argument": argument,
    }


def run_bear_researcher(
    symbol: str,
    analyst_reports: list,
    bull_report: Optional[dict] = None,
    proposed_direction: str = "LONG",
    memory_context: str = "",
):
    """Red-Team Adversary hunting real structural traps/fakeouts against proposed_direction."""
    dir_u = str(proposed_direction or "LONG").upper()
    risks: List[str] = []
    for r in analyst_reports:
        rsi_v = float(r.get("rsi", 50) or 50)
        if dir_u == "LONG" and rsi_v > 68:
            risks.append(f"RSI Overbought ({rsi_v:.1f}) rawan koreksi")
        elif dir_u == "SHORT" and rsi_v < 32:
            risks.append(f"RSI Oversold ({rsi_v:.1f}) rawan short-cover bounce")

        fb = str(r.get("fundamental_bias", ""))
        if dir_u == "LONG" and fb == "BEARISH":
            risks.append("Funding sangat positif — risiko long squeeze")
        elif dir_u == "SHORT" and fb == "BULLISH":
            risks.append("Funding sangat negatif — risiko short squeeze")

        btc_4h = float(r.get("btc_4h_pct", 0.0) or 0.0)
        if dir_u == "LONG" and btc_4h <= -1.0:
            risks.append(f"BTC 4H melemah ({btc_4h:+.2f}%) — headwind untuk LONG")
        elif dir_u == "SHORT" and btc_4h >= 1.0:
            risks.append(f"BTC 4H menguat ({btc_4h:+.2f}%) — headwind untuk SHORT")

        if float(r.get("bb_width_pct", 0) or 0) > 14:
            risks.append("Volatilitas 24h ekstrem (>14%) — risiko wick stop-hunt")

    if memory_context and "CAUTION: poor history on this coin" in memory_context:
        risks.append("AI Trade Memory mencatat performa buruk berulang di koin ini")

    concrete_risk_count = len(risks)
    if not risks:
        risks = ["Tidak ada red-flag fatal mayor; perhatikan disiplin SL dan eksekusi maker"]

    ctx = " | ".join([str(r.get("analysis", ""))[:85] for r in analyst_reports])
    adv_arg = (bull_report.get("argument", "")[:140]) if isinstance(bull_report, dict) else ""
    mem_snippet = f" AI_MEMORY: {memory_context[:160]}." if memory_context else ""

    try:
        prompt = (
            f"Red-Team Adversary (Risk Skeptic): Uji ketat rencana {dir_u} {symbol}. "
            f"Tesis Pro: '{adv_arg}'. "
            f"Temuan risiko nyata: {risks}. Data analis: {ctx[:220]}.{mem_snippet} "
            f"Jelaskan risiko jebakan paling nyata (atau nyatakan jika tidak ada cacat fatal) dalam 2-3 kalimat. Bahasa Indonesia."
        )
        argument = call_ai(
            prompt,
            system_prompt="You are an adversarial crypto risk skeptic stress-testing a futures trade. Distinguish real fatal flaws from minor noise. Answer concisely in Indonesian.",
            max_tokens=180,
            is_json=False,
        )
    except Exception as e:
        print(f"[Committee] RedTeamAdversary AI error: {e}", flush=True)
        argument = f"Audit Red-Team untuk {dir_u}: {'; '.join(risks[:3])}."

    bear_strength = round(min(concrete_risk_count / 3.0, 1.0), 2) if concrete_risk_count > 0 else 0.25
    return {
        "agent": "BearResearcher",
        "signal": "BEARISH" if dir_u == "LONG" else "BULLISH",
        "bias": "ADVERSARIAL_SKEPTIC",
        "confidence_pct": round(bear_strength * 100, 1),
        "bear_strength": bear_strength,
        "concrete_risk_count": concrete_risk_count,
        "risk_factors": risks,
        "argument": argument,
        "core_thesis": argument,
    }


def run_bull_rebuttal(
    symbol: str,
    bull_report: dict,
    bear_report: dict,
    proposed_direction: str = "LONG",
    plan_summary: str = "",
):
    bear_arg = (bear_report.get("argument", "")[:150]) if isinstance(bear_report, dict) else ""
    plan_note = f" Rencana: {plan_summary}." if plan_summary else ""
    try:
        prompt = (
            f"Advocate Rebuttal ({proposed_direction} {symbol}): Red-Team menyatakan '{bear_arg}'.{plan_note} "
            f"Tangkis secara konkret dengan level invalidasi SL, TP1 profit-lock, dan struktur pasar dalam 1-2 kalimat. Bahasa Indonesia."
        )
        rebuttal = call_ai(
            prompt,
            system_prompt="You are a disciplined trading advocate rebutting risk objections using exact SL/TP structure. Answer concisely in Indonesian.",
            max_tokens=140,
            is_json=False,
        )
    except Exception as e:
        print(f"[Committee] AdvocateRebuttal AI error: {e}", flush=True)
        rebuttal = f"Risiko Red-Team dimitigasi oleh SL struktural ketat dan TP1 profit-lock (+0.90R) sesuai rencana Layer 3."
    return rebuttal


# ============================================================
# TRADER AGENT (Tactical Mediator — preserves Layer 5 direction)
# ============================================================

def run_trader_agent(
    symbol: str,
    price: float,
    bull_report: dict,
    bear_report: dict,
    rebuttal: str,
    analyst_reports: list,
    proposed_direction: Optional[str] = None,
    layer5_conf: Optional[float] = None,
):
    bs = float(bull_report.get("bull_strength", 0.5) or 0.5)
    br = float(bear_report.get("bear_strength", 0.35) or 0.35)
    net_conviction = bs - br * 0.70

    if proposed_direction in ("LONG", "SHORT"):
        # Veto-only mode: NEVER flip LONG<->SHORT! Only confirm or express low conviction.
        base_c = float(layer5_conf) if layer5_conf is not None else 75.0
        adj = (bs - br) * 15.0
        confidence = round(max(40.0, min(95.0, base_c + adj)), 1)
        direction = proposed_direction if (confidence >= 55.0 and br < 0.90) else "SKIP"
    else:
        confidence = round(max(35.0, min(95.0, 50.0 + net_conviction * 45.0)), 1)
        if confidence >= 50 and bs >= br:
            direction = "LONG"
        elif confidence >= 50 and br > bs:
            direction = "SHORT"
        else:
            direction = "SKIP"

    decision = (
        f"Sintesis taktis: Pertahankan {direction} {symbol} @ ${price:,.4f} "
        f"(keyakinan {confidence:.0f}%, Pro={bs:.2f} vs RedTeam={br:.2f})."
    )
    if proposed_direction is None:
        try:
            prompt = (
                f"Trader Agent: Simpulkan perdebatan {symbol} @ ${price:,.4f}. "
                f"Pro: {bull_report.get('argument', '')[:100]} | Kontra: {bear_report.get('argument', '')[:100]} | "
                f"Rebuttal: {rebuttal[:100]} | Arah: {direction} ({confidence:.0f}%). "
                f"Sintesis taktis 2 kalimat, Bahasa Indonesia."
            )
            decision = call_ai(
                prompt,
                system_prompt="You are the Chief Trader Agent mediating adversarial debate. Answer concisely in Indonesian.",
                max_tokens=140,
                is_json=False,
            )
        except Exception as e:
            print(f"[Committee] TraderAgent AI error: {e}", flush=True)

    return {
        "agent": "TraderAgent",
        "signal": direction,
        "direction": direction,
        "confidence_pct": confidence,
        "net_conviction": round(net_conviction, 3),
        "decision": decision,
        "rebuttal_accepted": True,
    }


# ============================================================
# RISK OFFICER (Gear-Aware & Audit-Only — never rewrites Layer 3 SL/TP!)
# ============================================================

def run_risk_officer(
    symbol: str,
    price: float,
    direction: str,
    confidence: float,
    market_data: dict,
    config: dict,
    pipeline_context: Optional[Dict[str, Any]] = None,
):
    """
    Gear-Aware Audit-Only Risk Officer:
    - When `pipeline_context` provides Layer 3/5 plan_result, audits its exact
      entry/SL/TP1/TP2 geometry against active config & Gear 1/2/3 WITHOUT
      re-fetching Binance balance or inventing conflicting SL/TP prices!
    """
    gear_prof = _resolve_active_gear_profile(config, pipeline_context)
    leverage = int(gear_prof.get("leverage") or config.get("fixed_leverage", 20) or 20)
    sizing_mode = str(gear_prof.get("sizing_mode") or config.get("sizing_mode", "ALL_IN")).upper()
    min_rrr = float(config.get("min_risk_reward_ratio", 1.8) or 1.8)
    min_sl_pct = float(config.get("min_sl_pct", 0.90) or 0.90)
    max_sl_pct = float(config.get("max_sl_pct", 2.25) or 2.25)

    change_24h = abs(float(market_data.get("change_24h_pct", 3) or 3))
    bb_width = float(market_data.get("bb_width_pct", 5) or 5)
    volatility = (change_24h + bb_width) / 2.0

    fc = (pipeline_context or {}).get("final_call") if isinstance(pipeline_context, dict) else None
    plan = (pipeline_context or {}).get("plan_result") if isinstance(pipeline_context, dict) else None

    if isinstance(fc, dict) or isinstance(plan, dict):
        src = fc if (isinstance(fc, dict) and float(fc.get("stop_loss") or 0) > 0) else (plan or {})
        entry_px = float(src.get("entry_price") or price or 0)
        sl = float(src.get("stop_loss") or 0)
        tp1 = float(src.get("take_profit_1") or 0)
        tp2 = float(src.get("take_profit_2") or src.get("take_profit") or 0)
        sl_dist_pct = (abs(entry_px - sl) / entry_px * 100.0) if (entry_px > 0 and sl > 0) else 0.0
        risk_pp = abs(entry_px - sl)
        reward_pp = abs(tp2 - entry_px) if tp2 > 0 else abs(tp1 - entry_px)
        actual_rrr = (reward_pp / risk_pp) if risk_pp > 1e-12 else 0.0
        sl_ok = (min_sl_pct - 0.05) <= sl_dist_pct <= (max_sl_pct + 0.05)
        rrr_ok = actual_rrr >= (min_rrr - 0.05)
        risk_approved = bool(sl_ok and rrr_ok and direction in ("LONG", "SHORT") and confidence >= 55.0)
        budget_idr = int(src.get("position_size_idr") or 0)
        available_usdt = 0.0
        time_horizon = ((plan or {}).get("tp_time_prediction") or {}).get("eta_label", "N/A")
        var95 = round(max(0.0, volatility * 0.1 * leverage), 2)
        risk_note = (
            f"Audit-Only Gear {gear_prof.get('gear', 1)} ({leverage}x {sizing_mode}): "
            f"SL={sl_dist_pct:.2f}% ({'OK' if sl_ok else 'OUT_OF_CORRIDOR'}), "
            f"RRR=1:{actual_rrr:.2f} ({'OK' if rrr_ok else 'LOW'})"
        )
    else:
        # Standalone committee call fallback (non-pipeline)
        available_usdt = 0.0
        fx_rate = convert_usd_to_idr(1.0)
        budget_idr = int(config.get("max_budget_idr") or 0)
        atr_pct = max(0.95, min(2.0, volatility * 0.5))
        if direction == "LONG":
            sl = price * (1.0 - atr_pct / 100.0)
            tp1 = price * (1.0 + atr_pct / 100.0 * 0.90)
            tp2 = price * (1.0 + atr_pct / 100.0 * max(2.0, min_rrr))
        elif direction == "SHORT":
            sl = price * (1.0 + atr_pct / 100.0)
            tp1 = price * (1.0 - atr_pct / 100.0 * 0.90)
            tp2 = price * (1.0 - atr_pct / 100.0 * max(2.0, min_rrr))
        else:
            sl = tp1 = tp2 = price
        risk_pp = abs(price - sl)
        reward_pp = abs(tp2 - price)
        actual_rrr = (reward_pp / risk_pp) if risk_pp > 1e-12 else 0.0
        risk_approved = bool(actual_rrr >= min_rrr and confidence >= 50.0 and direction in ("LONG", "SHORT"))
        var95 = round(convert_idr_to_usd(budget_idr or 50000) * leverage * volatility / 100.0 * 1.65, 2)
        time_horizon = "~2-6 jam (Intraday)"
        risk_note = f"Standalone Audit Gear {gear_prof.get('gear', 1)} ({leverage}x {sizing_mode}): RRR=1:{actual_rrr:.2f}, Vol={volatility:.1f}%"

    return {
        "agent": "RiskOfficer",
        "signal": "APPROVED" if risk_approved else "VETOED",
        "risk_approved": risk_approved,
        "confidence_pct": round(confidence, 1),
        "wallet_usdt_available": round(available_usdt, 4),
        "recommended_budget_idr": budget_idr,
        "recommended_leverage": leverage,
        "leverage": leverage,
        "gear_code": gear_prof.get("code", "GEAR_1_TURBO"),
        "sizing_mode": sizing_mode,
        "sl_price": round(sl, 6),
        "tp1_price": round(tp1, 6),
        "tp2_price": round(tp2, 6),
        "actual_rrr": round(actual_rrr, 2),
        "var_95_usd": round(var95, 2),
        "volatility_pct": round(volatility, 2),
        "estimated_time_horizon": time_horizon,
        "risk_note": risk_note,
    }


# ============================================================
# PORTFOLIO MANAGER (AI Supreme Veto-Only Judge)
# ============================================================

def run_portfolio_manager(
    symbol: str,
    trader_report: dict,
    risk_report: dict,
    existing_positions: list,
    config: dict,
    bull_report: Optional[dict] = None,
    bear_report: Optional[dict] = None,
    rebuttal: str = "",
    memory_context: str = "",
    pipeline_context: Optional[Dict[str, Any]] = None,
):
    max_concurrent = int(config.get("max_concurrent_positions", 1) or 1)
    open_pos = [p for p in (existing_positions or []) if isinstance(p, dict) and p.get("status") == "OPEN"]
    rejections: List[str] = []

    if trader_report.get("direction") not in ("LONG", "SHORT"):
        rejections.append("Trader merekomendasikan SKIP (conviction tidak cukup)")
    if not risk_report.get("risk_approved"):
        rejections.append(f"Risk Officer Veto: {risk_report.get('risk_note', 'risk parameter invalid')}")
    if len(open_pos) >= max_concurrent:
        rejections.append(f"Kapasitas portofolio penuh ({len(open_pos)}/{max_concurrent})")
    if symbol in [p.get("symbol") for p in open_pos]:
        rejections.append(f"{symbol} sudah memiliki posisi terbuka")

    if rejections:
        decision = f"VETOED: {'; '.join(rejections[:2])}"
        return {
            "agent": "PortfolioManager",
            "signal": "REJECTED",
            "approved": False,
            "rejection_reasons": rejections,
            "open_count": len(open_pos),
            "decision": decision,
            "executive_summary": decision,
        }

    # AI Supreme PM Adversarial Veto Check (only runs when hard portfolio & risk checks pass!)
    approved = True
    decision = f"APPROVED (Konsensus Sidang 9-Agent tercapai untuk {trader_report.get('direction')} {symbol})"
    fatal_flaw = ""
    if isinstance(pipeline_context, dict):
        mp = (pipeline_context.get("scan_summary") or {}).get("math_proof") or {}
        btc_m = (pipeline_context.get("scan_summary") or {}).get("btc_macro") or {}
        fc = pipeline_context.get("final_call") or {}
        dir_u = str(fc.get("direction") or trader_report.get("direction") or "LONG").upper()
        setup_u = str((pipeline_context.get("setup_result") or {}).get("setup_name") or fc.get("setup_name") or "AI_SETUP")

        sys_pm = (
            "You are the Supreme Portfolio Manager (Veto-Only Judge) of a crypto futures desk.\n"
            "This setup ALREADY passed 5 quant+AI layers, math gates, and SL/RRR validation.\n"
            "Your job: review the Advocate vs Red-Team debate, BTC 4H macro, microstructure, and AI_MEMORY.\n"
            "RULES:\n"
            "- Output APPROVE unless there is a CONCRETE, live price-action/orderflow FATAL FLAW (clear fakeout trap, "
            "strong opposite BTC 4H impulse >=1.6%, severe exhaustion, OR AI_MEMORY explicitly flags '[CAUTION: poor history on this coin]' with >=3 live losses).\n"
            "- NEVER veto simply because AI_MEMORY has 0 closed trades yet, small kNN sample, or generic/textbook caution.\n"
            "- Respond ONLY in JSON: {\"verdict\":\"APPROVE\" or \"VETO\",\"confidence_pct\":78,\"fatal_flaw\":\"\",\"decision\":\"1 sentence in Indonesian\"}"
        )
        usr_pm = (
            f"Candidate: {dir_u} {symbol} ({setup_u}), Layer5Conf={fc.get('confidence_score', 75)}%, "
            f"P_Math={mp.get('p_math_pct', 70)}%, OBI20={mp.get('obi_weighted_20', 0)}, "
            f"Hurst={mp.get('hurst_exponent', 0.5)}, Regime={mp.get('statistical_regime', 'NORMAL')}, "
            f"BTC_4H={btc_m.get('btc_4h_pct', 0)}% ({btc_m.get('btc_1h_trend', 'UNKNOWN')}).\n"
            f"RiskAudit: {risk_report.get('risk_note', 'OK')}\n"
            f"ProAdvocate: {(bull_report or {}).get('argument', '')[:180]}\n"
            f"RedTeamAdversary: {(bear_report or {}).get('argument', '')[:180]}\n"
            f"Rebuttal: {str(rebuttal)[:140]}\n"
            f"AI_MEMORY: {memory_context[:200] if memory_context else 'None'}\n"
            f"Verdict JSON only:"
        )
        try:
            raw_pm = call_ai(usr_pm, system_prompt=sys_pm, max_tokens=180, is_json=True)
            parsed = _extract_json_obj(raw_pm)
            if isinstance(parsed, dict):
                v_str = str(parsed.get("verdict", "APPROVE")).upper().strip()
                dec_str = str(parsed.get("decision") or "").strip()
                flaw_str = str(parsed.get("fatal_flaw") or "").strip()
                if v_str in ("VETO", "REJECT", "REJECTED"):
                    approved = False
                    fatal_flaw = flaw_str or dec_str or "Fatal trap terdeteksi oleh Sidang 9-Agent"
                    rejections.append(fatal_flaw)
                    decision = f"VETOED: {fatal_flaw}"
                else:
                    approved = True
                    decision = dec_str or decision
        except Exception as exc:
            print(f"[Committee] Supreme PM AI fallback to deterministic PASS: {exc}", flush=True)

    return {
        "agent": "PortfolioManager",
        "signal": "APPROVED" if approved else "REJECTED",
        "approved": approved,
        "fatal_flaw": fatal_flaw,
        "rejection_reasons": rejections,
        "open_count": len(open_pos),
        "decision": decision,
        "executive_summary": decision,
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
        "bid_price": round(price * (1 - spread / 100), 6),
        "ask_price": round(price * (1 + spread / 100), 6),
        "midpoint": round(price, 6),
    }


# ============================================================
# THESIS ENGINE (LangAlpha persistent workspace — atomic I/O)
# ============================================================

def save_thesis(symbol, result):
    thesis = {}
    if state_io is not None:
        thesis = state_io.read_json_safe(THESIS_FILE, default={}, strict_on_corrupt=False, expected_type=dict) or {}
    elif os.path.exists(THESIS_FILE):
        try:
            with open(THESIS_FILE, "r", encoding="utf-8") as f:
                thesis = json.load(f)
        except Exception:
            thesis = {}

    consensus = result.get("consensus", {})
    thesis[symbol] = {
        "symbol": symbol,
        "direction": consensus.get("action", result.get("direction")),
        "confidence": consensus.get("confidence_pct", result.get("confidence_pct")),
        "approved": result.get("approved"),
        "bull_arg": result.get("bull_researcher", {}).get("argument", "")[:220],
        "bear_arg": result.get("bear_researcher", {}).get("argument", "")[:220],
        "rebuttal": str(result.get("bull_rebuttal", ""))[:180],
        "trader_decision": result.get("trader_agent", {}).get("decision", "")[:220],
        "risk": result.get("risk_officer", {}),
        "trade_plan": result.get("trade_plan", {}),
        "collaboration_transcript": result.get("collaboration_transcript", []),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if state_io is not None:
            state_io.atomic_write_json(THESIS_FILE, thesis, make_bak=False)
        else:
            with open(THESIS_FILE, "w", encoding="utf-8") as f:
                json.dump(thesis, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_active_thesis(symbol):
    if state_io is not None:
        data = state_io.read_json_safe(THESIS_FILE, default={}, strict_on_corrupt=False, expected_type=dict) or {}
        return data.get(symbol)
    if not os.path.exists(THESIS_FILE):
        return None
    try:
        with open(THESIS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get(symbol)
    except Exception:
        return None


# ============================================================
# MAIN COMMITTEE ORCHESTRATOR
# ============================================================

def run_multi_agent_committee(
    symbol: str,
    existing_positions=None,
    active_positions=None,
    pipeline_context: Optional[Dict[str, Any]] = None,
):
    """
    Jalankan Sidang 9-Agent Adversarial Veto-Only Committee secara terstruktur.
    Jika dipanggil dari pipeline (`pipeline_context` terisi), seluruh data Layer 1-5
    + AI Trade Memory + Sistem Gigi digunakan ulang tanpa fetch ganda dan TANPA
    menimpa parameter SL/TP/Direction/Leverage Layer 3-5.
    """
    if existing_positions is None:
        existing_positions = active_positions or []
    config = get_trading_config()
    t0 = time.time()
    is_pipeline_mode = isinstance(pipeline_context, dict) and bool(pipeline_context)
    print(f"\n[Committee] Memulai Sidang 9-Agent Adversarial Veto-Only untuk {symbol}...", flush=True)

    scan_summary = (pipeline_context or {}).get("scan_summary") if is_pipeline_mode else None
    market_data = dict((pipeline_context or {}).get("market_data") or {}) if is_pipeline_mode else {}
    if not market_data:
        try:
            market_data = get_market_indicators(symbol) or {}
        except Exception as e:
            print(f"[Committee] Market data error: {e}", flush=True)
            market_data = {}

    if isinstance(scan_summary, dict):
        if "math_proof" in scan_summary and "math_proof" not in market_data:
            market_data["math_proof"] = scan_summary["math_proof"]
        if "news_macro" in scan_summary and "news_macro" not in market_data:
            market_data["news_macro"] = scan_summary["news_macro"]

    price = float(
        ((pipeline_context or {}).get("final_call") or {}).get("entry_price")
        or market_data.get("live_price")
        or market_data.get("price")
        or market_data.get("current_price")
        or 0
    )
    if not price:
        return {"symbol": symbol, "error": "No market data", "approved": False, "direction": "SKIP"}

    if "bb_width_pct" not in market_data:
        h = float(market_data.get("high_24h", price * 1.02) or (price * 1.02))
        l = float(market_data.get("low_24h", price * 0.98) or (price * 0.98))
        market_data["bb_width_pct"] = (h - l) / price * 100.0 if price > 0 else 5.0

    volatility = abs(float(market_data.get("change_24h_pct", 3) or 3))
    volume = float(market_data.get("volume_24h_usd", 0) or 0)
    spread_info = calculate_optimal_spread(symbol, price, volatility, volume)

    fc_in = (pipeline_context or {}).get("final_call") or {}
    setup_in = (pipeline_context or {}).get("setup_result") or {}
    proposed_dir = str(fc_in.get("direction") or setup_in.get("direction") or "").upper()
    if proposed_dir not in ("LONG", "SHORT"):
        proposed_dir = None
    setup_name = str(setup_in.get("setup_name") or fc_in.get("setup_name") or "AI_SETUP")
    memory_context = str((pipeline_context or {}).get("memory_context") or "")
    btc_macro = (scan_summary or {}).get("btc_macro") if isinstance(scan_summary, dict) else {}

    # ------------------------------------------------------------
    # ROUND 1: 4 SPECIALIST ANALYSTS (deterministic in pipeline mode -> saves ~4,500 tokens!)
    # ------------------------------------------------------------
    use_r1_llm = not is_pipeline_mode
    analyst_map: Dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(run_technical_analyst, symbol, market_data, use_r1_llm): "technical",
            ex.submit(run_sentiment_analyst, symbol, market_data, use_r1_llm): "sentiment",
            ex.submit(run_fundamentals_agent, symbol, market_data, use_r1_llm): "fundamentals",
            ex.submit(run_macro_analyst, symbol, market_data, btc_macro): "macro",
        }
        for fut in as_completed(futures):
            k = futures[fut]
            try:
                analyst_map[k] = fut.result()
            except Exception as e:
                analyst_map[k] = {"agent": k, "error": str(e), "analysis": "Error"}

    reports = list(analyst_map.values())

    # ------------------------------------------------------------
    # ROUND 2, 3, 4: DIRECTION-SYMMETRIC ADVERSARIAL DEBATE
    # ------------------------------------------------------------
    debate_dir = proposed_dir or "LONG"
    bull = run_bull_researcher(symbol, reports, proposed_direction=debate_dir, setup_name=setup_name, memory_context=memory_context)
    bear = run_bear_researcher(symbol, reports, bull, proposed_direction=debate_dir, memory_context=memory_context)

    plan_summary = ""
    if is_pipeline_mode and fc_in:
        plan_summary = (
            f"Entry=${float(fc_in.get('entry_price') or price):.4f}, "
            f"SL=${float(fc_in.get('stop_loss') or 0):.4f}, "
            f"TP1=${float(fc_in.get('take_profit_1') or 0):.4f}, "
            f"TP2=${float(fc_in.get('take_profit_2') or fc_in.get('take_profit') or 0):.4f}, "
            f"RRR={fc_in.get('risk_reward_ratio', '1:2.0')}"
        )
    rebuttal = run_bull_rebuttal(symbol, bull, bear, proposed_direction=debate_dir, plan_summary=plan_summary)

    # ------------------------------------------------------------
    # ROUND 5: TRADER AGENT MEDIATION
    # ------------------------------------------------------------
    l5_conf = float(fc_in.get("confidence_score")) if (is_pipeline_mode and fc_in.get("confidence_score") is not None) else None
    trader = run_trader_agent(
        symbol, price, bull, bear, rebuttal, reports,
        proposed_direction=proposed_dir,
        layer5_conf=l5_conf,
    )

    # ------------------------------------------------------------
    # ROUND 6: GEAR-AWARE AUDIT-ONLY RISK OFFICER
    # ------------------------------------------------------------
    risk = run_risk_officer(
        symbol, price, trader["direction"], trader["confidence_pct"], market_data, config,
        pipeline_context=pipeline_context,
    )

    # ------------------------------------------------------------
    # ROUND 7: AI SUPREME PORTFOLIO MANAGER (VETO-ONLY VERDICT)
    # ------------------------------------------------------------
    pm = run_portfolio_manager(
        symbol, trader, risk, existing_positions, config,
        bull_report=bull,
        bear_report=bear,
        rebuttal=rebuttal,
        memory_context=memory_context,
        pipeline_context=pipeline_context,
    )

    elapsed = round(time.time() - t0, 2)
    final_dir = (proposed_dir or trader["direction"]) if pm["approved"] else "SKIP"
    final_act = "BUY" if final_dir == "LONG" else ("SELL" if final_dir == "SHORT" else "HOLD")

    transcript = [
        {
            "round": 1,
            "speaker": "Analyst Team",
            "role": "Quant & Macro Brief",
            "content": (
                f"Tech: {analyst_map.get('technical', {}).get('verdict', '-')}, "
                f"Sent: {analyst_map.get('sentiment', {}).get('sentiment', '-')}, "
                f"Deriv: {analyst_map.get('fundamentals', {}).get('funding_signal', '-')}, "
                f"Macro: {analyst_map.get('macro', {}).get('macro_regime', '-')}"
            ),
        },
        {"round": 2, "speaker": f"Advocate Researcher ({debate_dir})", "role": "Pro-Setup Thesis", "content": bull.get("argument", "")},
        {"round": 3, "speaker": "Red-Team Adversary", "role": "Trap & Fakeout Hunter", "content": bear.get("argument", "")},
        {"round": 4, "speaker": "Advocate Rebuttal", "role": "Structural Defense", "content": rebuttal},
        {"round": 5, "speaker": "Trader Agent", "role": "Tactical Mediation", "content": trader.get("decision", "")},
        {
            "round": 6,
            "speaker": "Risk Officer",
            "role": f"Gear-Aware Audit ({risk.get('gear_code', 'G1')})",
            "content": f"Status: {risk.get('signal')} | {risk.get('risk_note', '')}",
        },
        {"round": 7, "speaker": "Portfolio Manager", "role": "Supreme Veto-Only Verdict", "content": pm.get("decision", "")},
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
        "mode": "VETO_ONLY_ADVERSARIAL" if is_pipeline_mode else "STANDALONE",
        "price": price,
        "price_idr": convert_usd_to_idr(price),
        "direction": final_dir,
        "approved": pm["approved"],
        "confidence_pct": trader["confidence_pct"],
        "elapsed_sec": elapsed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "estimated_time_horizon": time_horizon,
        "spread_info": spread_info,
        "consensus": {
            "action": final_act,
            "direction": final_dir,
            "confidence_pct": trader["confidence_pct"],
            "approved": pm["approved"],
            "risk_reward_ratio": f"1:{risk.get('actual_rrr', 2.0):.2f}",
            "executive_summary": pm["decision"],
            "summary": pm["decision"],
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
            "portfolio_manager": pm,
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
        "portfolio_manager": pm,
    }

    save_thesis(symbol, result)
    _log_result(result)
    print(f"[Committee] {'APPROVED' if pm['approved'] else 'VETOED'} ({final_dir}) — {elapsed}s", flush=True)
    return result


def _log_result(result):
    logs = []
    if state_io is not None:
        logs = state_io.read_json_safe(COMMITTEE_LOG_FILE, default=[], strict_on_corrupt=False, expected_type=list) or []
    elif os.path.exists(COMMITTEE_LOG_FILE):
        try:
            with open(COMMITTEE_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    logs.insert(0, {
        "symbol": result.get("symbol"),
        "direction": result.get("direction"),
        "approved": result.get("approved"),
        "confidence": result.get("confidence_pct"),
        "mode": result.get("mode", "STANDALONE"),
        "elapsed": result.get("elapsed_sec"),
        "ts": result.get("timestamp"),
    })
    try:
        if state_io is not None:
            state_io.atomic_write_json(COMMITTEE_LOG_FILE, logs[:100], make_bak=False)
        else:
            with open(COMMITTEE_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(logs[:100], f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def run_quick_committee(symbol, market_data):
    """Versi cepat rule-based tanpa AI — untuk screening massal."""
    price = float(market_data.get("price", market_data.get("last_price", 0)) or 0)
    rsi = float(market_data.get("rsi_14", 50) or 50)
    change_24h = float(market_data.get("change_24h_pct", market_data.get("price_change_24h_pct", 0)) or 0)
    volume = float(market_data.get("volume_24h_usd", 0) or 0)

    score = 0
    signals = []
    if rsi < 35:
        score += 2
        signals.append("RSI oversold")
    elif rsi > 65:
        score -= 1
        signals.append("RSI overbought")
    if change_24h > 3:
        score += 1
        signals.append("Momentum positif")
    elif change_24h < -8:
        score -= 2
        signals.append("Downtrend kuat")
    if volume > 5e8:
        score += 1
        signals.append("Volume tinggi")

    if score >= 2:
        direction, confidence = "LONG", min(85, 50 + score * 8)
    elif score <= -2:
        direction, confidence = "SHORT", min(85, 50 + abs(score) * 8)
    else:
        direction, confidence = "SKIP", 40

    return {
        "symbol": symbol,
        "quick_score": score,
        "direction": direction,
        "confidence_pct": confidence,
        "signals": signals,
        "price": price,
        "rsi": rsi,
        "change_24h": change_24h,
        "volume_m": round(volume / 1e6, 1),
        "quick_mode": True,
    }
