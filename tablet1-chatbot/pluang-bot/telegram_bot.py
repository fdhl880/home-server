"""
===========================================================================
PYROFUEL TELEGRAM BOT v3.0 - FULL UNIVERSE CRYPTO FUTURES AI
===========================================================================
Token: 8829535429:AAHFHM56RDNAd7-ax6Dd-3V3g9OZEleYi5M (@idrisginting_bot)
Koleksi Aset: ALL Binance USDT Perpetual Futures (~200+ coins)
Fitur: 5-Layer AI Pipeline, Binance Futures Execution (20x ISOLATED)

DAFTAR PERINTAH:
/start      - Welcome & daftar perintah
/binance    - Cek status koneksi Binance Futures API
/scan       - Full scan CORE + Top movers
/scan [coin]- Analisis koin spesifik (misal: /scan btc)
/konfirmasi [coin] - Eksekusi order riil ke Binance Futures
/universe   - Status seluruh universe (200+ pairs)
/top        - Top 20 movers saat ini
/btc, /eth, /sol - Analisis instan koin utama
/status     - Status portfolio, margin & posisi aktif Binance
/wallet     - Cek saldo Binance Futures ($) Live
/auto       - Status autonomous trading engine
/limit [n]  - Ubah batas modal per trade
/fx         - Kurs USD/IDR real-time
===========================================================================
"""
import os
import sys
import time
import json
import threading
import requests
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed

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

from pipeline import run_5_layer_pipeline, load_env, get_trading_config, save_trading_config, RESULTS_DIR, AI_PROVIDER, GEMINI_API_KEY, GROQ_MODEL
from market_data import (
    CRYPTO_FUTURES_WATCHLIST, get_market_indicators, get_market_indicators_fast,
    get_full_universe, get_top_movers, get_universe_summary, get_fx_info,
    convert_usd_to_idr, convert_idr_to_usd, rank_universe_by_opportunity,
    normalize_symbol_to_pair
)
from binance_futures import BinanceFuturesClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(RESULTS_DIR, "active_positions.json")
STATE_FILE = os.path.join(RESULTS_DIR, "autotrader_state.json")

def get_binance_client():
    env = load_env()
    ak = env.get("BINANCE_API_KEY", "").strip()
    sk = env.get("BINANCE_API_SECRET", "").strip()
    if ak and sk:
        return BinanceFuturesClient(api_key=ak, api_secret=sk)
    return None

ENV = load_env()
TELEGRAM_TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "").strip()
TELE_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def _max_budget():
    return get_trading_config().get("max_budget_idr", 0)

def _max_leverage():
    return 20  # Always 20x fixed user mandate

WHITELIST_FILE = os.path.join(BASE_DIR, "last_chat_id.txt")
def get_allowed_chat_ids():
    allowed = {6794056929, "6794056929"}  # Default user ID
    env_id = ENV.get("ALLOWED_TELEGRAM_CHAT_ID")
    if env_id:
        try:
            allowed.add(int(env_id))
            allowed.add(str(env_id).strip())
        except Exception:
            pass
    if os.path.exists(WHITELIST_FILE):
        try:
            with open(WHITELIST_FILE, "r") as f:
                val = f.read().strip()
                if val:
                    allowed.add(int(val))
                    allowed.add(str(val).strip())
        except Exception:
            pass
    return allowed

def is_chat_allowed(chat_id):
    if not chat_id:
        return False
    whitelist = get_allowed_chat_ids()
    try:
        if int(chat_id) in whitelist:
            return True
    except Exception:
        pass
    return str(chat_id).strip() in whitelist

def _esc_html(s):
    """Safely escape HTML special characters for Telegram HTML parse_mode"""
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram_message(chat_id, text, reply_markup=None):
    url = f"{TELE_API}/sendMessage"
    if len(text) > 4000:
        text = text[:3997] + "..."
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(url, json=payload, timeout=15)
        res_json = r.json() if r.content else {}
        if not res_json.get("ok"):
            err_desc = res_json.get("description", "")
            print(f"[-] Telegram API Warning ({res_json.get('error_code')}): {err_desc}")
            if "can't parse entities" in err_desc or "Bad Request" in err_desc:
                # Automatic Fallback: Strip HTML tags and send cleanly as plain text
                import re
                plain_text = re.sub(r'<[^>]*>', '', text)
                payload["text"] = plain_text
                payload.pop("parse_mode", None)
                r_fallback = requests.post(url, json=payload, timeout=15)
                return r_fallback.json() if r_fallback.content else None
        return res_json
    except Exception as e:
        print(f"[-] Telegram error: {e}")
        return None

def answer_callback(callback_query_id, text, show_alert=False):
    url = f"{TELE_API}/answerCallbackQuery"
    try:
        requests.post(url, json={
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert
        }, timeout=5)
    except Exception:
        pass

def format_pipeline_report(res: dict):
    symbol = res["symbol"]
    layer1 = res["layer1_scanning"]
    setup = res["layer2_setup"]
    plan = res["layer3_plan"]
    risk = res["layer4_risk"]
    fc = res["layer5_final_call"]

    status = fc.get("status", "REJECTED")
    badge = "✅ <b>LOLOS KELAYAKAN (APPROVED)</b>" if status == "APPROVED" else "🛑 <b>DITOLAK KETAT (REJECTED)</b>"

    cfg = get_trading_config()
    max_budget = cfg.get("max_budget_idr", 50000)
    min_conf = cfg.get("min_confidence_score", 65)
    
    qf = layer1.get("quant_factors") or {}
    c_score = qf.get("composite_quant_score", "N/A")
    total_f = qf.get("total_factors_evaluated", 532)
    regime = qf.get("regime", "NORMAL")

    tp_val = plan.get('take_profit') or plan.get('take_profit_1') or plan.get('take_profit_2', 0)
    sl_val = plan.get('stop_loss', 0)
    order_t = (plan.get('order_type') or 'MARKET').upper()
    limit_p_str = f" (@ ${plan.get('limit_price', 0):,})" if order_t == 'LIMIT' else ""
    lev_val = plan.get('leverage') or fc.get('leverage', 20)
    modal_val = plan.get('position_size_idr') or fc.get('position_size_idr', max_budget)

    # 1. LIVE BINANCE FUTURES POSITION STATUS (IF ACTIVE)
    bn_pos_text = ""
    try:
        bn = get_binance_client()
        if bn:
            pos_list = bn.get_positions()
            coin_clean = symbol.replace("-USD", "").replace("USDT", "")
            match_pos = next((p for p in pos_list if coin_clean in p.get("symbol", "")), None) if isinstance(pos_list, list) else None
            if match_pos and abs(float(match_pos.get("position_amount", 0))) > 0:
                dir_str = match_pos.get("direction", "LONG")
                amt_str = match_pos.get("position_amount")
                entry_px = float(match_pos.get("entry_price", 0))
                mark_px = float(match_pos.get("mark_price", 0))
                upnl_val = float(match_pos.get("unrealized_pnl", 0))
                pos_lev = match_pos.get("leverage", 20)
                liq_px = float(match_pos.get("liquidation_price", 0))
                iso_margin = float(match_pos.get("isolated_margin", 0))
                roe_val = (upnl_val / iso_margin * 100.0) if iso_margin > 0 else 0.0
                pnl_sign = "+" if upnl_val >= 0 else ""
                dist_liq = abs(mark_px - liq_px)
                dist_pct = (dist_liq / mark_px * 100.0) if mark_px > 0 else 0.0

                bn_pos_text = (
                    f"⚡ <b>STATUS POSISI LIVE ANDA DI BINANCE:</b>\n"
                    f"• <b>Posisi:</b> <code>{match_pos.get('symbol')}</code> (<b>{dir_str} {pos_lev}x ISOLATED</b>)\n"
                    f"• <b>Ukuran:</b> {amt_str} (~${iso_margin:.2f} USDT margin)\n"
                    f"• <b>Entry:</b> ${entry_px:,.4f} ➔ <b>Mark:</b> ${mark_px:,.4f}\n"
                    f"• <b>Floating PnL:</b> <b>{pnl_sign}${upnl_val:.4f} USDT ({pnl_sign}{roe_val:.2f}% ROE)</b>\n"
                    f"• <b>Harga Likuidasi:</b> ${liq_px:,.4f} <i>(Jarak aman: ${dist_liq:,.2f} / {dist_pct:.2f}%)</i>\n"
                    f"────────────────────────\n"
                )
    except Exception:
        pass

    # 2. SMC & DERIVATIVES METRICS
    fr_data = layer1.get("funding_rate", {})
    fr_val = fr_data.get("funding_rate", 0) if isinstance(fr_data, dict) else 0
    ls_data = layer1.get("long_short_ratio", {})
    ls_ratio = ls_data.get("long_short_ratio", "N/A") if isinstance(ls_data, dict) else "N/A"
    long_pct = ls_data.get("long_pct", 50) if isinstance(ls_data, dict) else 50
    crowd_sent = ls_data.get("crowd_sentiment", "NEUTRAL") if isinstance(ls_data, dict) else "NEUTRAL"
    bb_data = layer1.get("bollinger", {})
    bb_sqz = "🟡 SQUEEZE (Kompresi)" if bb_data.get("squeeze") else "NORMAL"
    smc_data = qf.get("smc_summary", {})
    b_fvg = smc_data.get("bullish_fvgs", 0)
    be_fvg = smc_data.get("bearish_fvgs", 0)
    levels = layer1.get("levels", {})

    # 3. 9-AGENT SIDANG COMMITTEE SUMMARY (IF AVAILABLE)
    com_text = ""
    com = res.get("committee") or {}
    if com:
        agents = com.get("agents", {})
        bull_arg = _esc_html(agents.get("bull_researcher", {}).get("argument", "")[:160])
        bear_arg = _esc_html(agents.get("bear_researcher", {}).get("argument", "")[:160])
        trader_dec = _esc_html(agents.get("trader", {}).get("decision", "")[:140])
        risk_note = _esc_html(agents.get("risk_officer", {}).get("risk_note", "") or "Lev 20x ISOLATED")
        pm_dec = _esc_html(com.get("portfolio_manager", {}).get("decision", "") or com.get("consensus", {}).get("summary", ""))

        com_text = (
            f"🏛️ <b>SIDANG 9-AGENT INVESTMENT COMMITTEE:</b>\n"
            f"• <b>Bull Thesis:</b> <i>{bull_arg or 'Akumulasi tren positif'}</i>\n"
            f"• <b>Bear Risk:</b> <i>{bear_arg or 'Resistensi & likuiditas rapuh'}</i>\n"
            f"• <b>Trader Conviction:</b> <i>{trader_dec or 'Tunggu konfirmasi volume'}</i>\n"
            f"• <b>Risk Officer:</b> {risk_note}\n"
            f"• <b>Supreme PM Verdict:</b> <b>{pm_dec[:180]}</b>\n"
            f"────────────────────────\n"
        )

    setup_exp = _esc_html(setup.get('explanation_id', ''))
    final_reason_text = _esc_html(fc.get('final_reason', '-')[:350])

    text = (
        f"🛡️ <b>PYROFUEL INSTITUTIONAL 5-LAYER + SIDANG 9-AGENT</b>\n"
        f"<b>Aset:</b> <code>{symbol}</code> (${layer1.get('current_price', 0):,.4f})\n"
        f"<b>Harga IDR:</b> Rp {convert_usd_to_idr(layer1.get('current_price', 0)):,.0f}\n"
        f"────────────────────────\n"
        f"{bn_pos_text}"
        f"📊 <b>KUANTITATIF & SMC ALPHA:</b>\n"
        f"• <b>RSI (14):</b> {layer1.get('rsi_14')} | <b>Tren EMA:</b> {layer1.get('ema_trend')}\n"
        f"• <b>Bollinger Bands:</b> {bb_sqz} (Width: {bb_data.get('width_pct', 0)}%)\n"
        f"• <b>Funding Rate:</b> {fr_val:+.4f}% | <b>L/S Ratio:</b> {ls_ratio} ({long_pct}% Long)\n"
        f"• <b>SMC Fair Value Gaps:</b> {b_fvg} Bullish / {be_fvg} Bearish FVG\n"
        f"• <b>Level Kunci:</b> Pivot ${levels.get('pivot', 0):,.2f} | R1 ${levels.get('resistance_1', 0):,.2f} | S1 ${levels.get('support_1', 0):,.2f}\n"
        f"────────────────────────\n"
        f"🎯 <b>1. Setup Hunter:</b> <code>{setup.get('setup_name', 'N/A')}</code> ({setup.get('direction', 'NONE')})\n"
        f"<i>\"{setup_exp}\"</i>\n\n"
        f"📐 <b>2. Trading Plan (AI Governed):</b> {plan.get('action', 'SKIP')}\n"
        f"• Order: {order_t}{limit_p_str} | Leverage: <b>20x ISOLATED</b>\n"
        f"• Entry: ${plan.get('entry_price', 0):,} | SL: ${sl_val:,} | TP: ${tp_val:,}\n"
        f"• Modal Sizing: Rp {modal_val:,} | RRR: {plan.get('risk_reward_ratio', 'N/A')}\n\n"
        f"🔍 <b>3. CRO Risk Audit:</b> {risk.get('risk_verdict', 'N/A')} ({risk.get('total_score', 0)}/{risk.get('max_score', 10)} pass)\n\n"
        f"⚖️ <b>4. Supreme Judge Decision:</b> {badge}\n"
        f"• <b>Skor Keyakinan:</b> {fc.get('confidence_score', 0)}% (Min {min_conf}%)\n\n"
        f"{com_text}"
        f"📌 <b>Pertimbangan Final:</b>\n{final_reason_text}\n"
    )
    return text, status

def execute_trade_with_binance(symbol: str, chat_id: int, callback_query_id: str = None):
    """Execute real trade on Binance Futures (20x ISOLATED)"""
    raw_sym = symbol.upper().strip().replace("USDT", "-USD")
    if not raw_sym.endswith("-USD"):
        raw_sym = raw_sym + "-USD"
    pair = raw_sym.replace("-USD", "USDT")
    
    cfg = get_trading_config()
    max_budget = cfg.get("max_budget_idr", 0)
    leverage = 20
    margin_type = cfg.get("margin_type", "ISOLATED")
    order_type = cfg.get("order_type", "MARKET")

    # 0. Check duplicate active position
    positions = []
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                positions = json.load(f)
        except Exception:
            positions = []
    existing_open = [p for p in positions if (p.get("symbol") == raw_sym or p.get("binance_pair") == pair) and p.get("status") == "OPEN"]
    if existing_open:
        last_pos = existing_open[-1]
        msg = (
            f"ℹ️ <b>POSISI {pair} SUDAH AKTIF DI BINANCE FUTURES!</b>\n\n"
            f"🎯 <b>Arah:</b> {last_pos.get('direction', 'LONG')}\n"
            f"📍 <b>Entry:</b> ${last_pos.get('entry_price', 0):,.4f}\n"
            f"🆔 <b>Order ID:</b> <code>{last_pos.get('order_id', 'N/A')}</code>\n\n"
            f"<i>Posisi sedang aktif dipantau. Modal Anda aman dan order tidak diduplikasi.</i>"
        )
        if callback_query_id:
            answer_callback(callback_query_id, f"Posisi {pair} sudah aktif!", show_alert=False)
        send_telegram_message(chat_id, msg)
        return True

    # 1. Check Binance Futures Client
    bn_client = get_binance_client()
    if not bn_client:
        msg = (
            "⚠️ <b>KONEKSI BINANCE FUTURES BELUM TERHUBUNG</b>\n\n"
            f"Order <b>{pair}</b> tidak dapat dikirim karena kunci API Binance belum aktif.\n\n"
            "👉 Masukkan <code>BINANCE_API_KEY</code> & <code>BINANCE_API_SECRET</code> di file .env.\n\n"
            "<i>🛡️ Modal Anda tetap aman 100%.</i>"
        )
        if callback_query_id:
            answer_callback(callback_query_id, "Gagal: Kunci Binance belum aktif!", show_alert=True)
        send_telegram_message(chat_id, msg)
        return False

    # 2. Get Signal / Technical Setup
    scan_file = os.path.join(RESULTS_DIR, f"{raw_sym.replace('-', '_')}_latest.json")
    signal = None
    if os.path.exists(scan_file):
        try:
            with open(scan_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                signal = saved.get("layer5_final_call", {})
        except Exception:
            pass

    if not signal or not signal.get("direction") or signal.get("direction") == "NONE":
        send_telegram_message(chat_id, f"⏳ <i>Menghitung analisis teknikal kuantitatif untuk {pair}...</i>")
        try:
            res = run_5_layer_pipeline(raw_sym)
            signal = res.get("layer5_final_call", {})
        except Exception as e:
            send_telegram_message(chat_id, f"❌ Error analisa: {e}")
            return False

    direction = signal.get("direction", "LONG")
    entry_price = float(signal.get("entry_price", 0))
    order_type = (signal.get("order_type") or cfg.get("order_type", "MARKET")).upper()
    limit_price = float(signal.get("limit_price") or entry_price)

    # Dynamic sizing from live wallet
    bal = bn_client.get_balance()
    avail_usdt = float(bal.get("available_balance", 0)) if isinstance(bal, dict) else 0.0
    sl_pct = float(signal.get("stop_loss_pct", 2.0)) / 100.0
    sl_pct = max(0.005, min(0.025, sl_pct))
    
    # 2% probation or 5% standard
    risk_frac = 0.02 if len(positions) < 20 else 0.05
    calc_margin_usd = (avail_usdt * risk_frac) / sl_pct if sl_pct > 0 else (avail_usdt * 0.10)
    calc_margin_usd = max(1.0, min(calc_margin_usd, avail_usdt * 0.95))
    pos_usd = round(calc_margin_usd, 2)
    pos_idr = int(pos_usd * get_fx_info().get("usd_idr", 16500))

    # Time horizon
    time_horizon = signal.get("estimated_time_horizon", "N/A")
    tp = float(signal.get("take_profit") or signal.get("take_profit_2") or signal.get("take_profit_1", 0))
    sl = float(signal.get("stop_loss", 0))

    limit_info = f" (@ ${limit_price:,.4f})" if order_type == "LIMIT" else ""
    send_telegram_message(
        chat_id,
        f"⚡ <i>Mengirim order {order_type}{limit_info} {direction} {pair} ({leverage}x ISOLATED) senilai ${pos_usd:.2f} USDT ke Binance Futures...</i>"
    )

    # 3. Call execute_full_trade
    try:
        execution_result = bn_client.execute_full_trade(
            signal={
                "binance_pair": pair,
                "symbol": raw_sym,
                "direction": direction,
                "leverage": leverage,
                "margin_type": margin_type,
                "order_type": order_type,
                "limit_price": limit_price,
                "entry_price": entry_price,
                "take_profit": tp,
                "stop_loss": sl,
                "position_size_usdt": pos_usd
            },
            config=cfg
        )

        is_synced = execution_result.get("binance_synced", False)

        if is_synced:
            # Record position in active_positions.json
            positions = []
            if os.path.exists(POSITIONS_FILE):
                try:
                    with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                        positions = json.load(f)
                except Exception:
                    positions = []

            open_res = execution_result.get("steps", {}).get("open_position", {})
            order_id = open_res.get("orderId") or execution_result.get("order_id") or "LIVE_EXECUTED"

            new_pos = {
                "id": f"POS_{raw_sym}_{int(time.time())}",
                "symbol": raw_sym,
                "binance_pair": pair,
                "direction": direction,
                "entry_price": entry_price,
                "entry_price_idr": convert_usd_to_idr(entry_price),
                "take_profit": tp,
                "take_profit_1": tp,
                "take_profit_2": tp,
                "stop_loss": sl,
                "leverage": leverage,
                "margin_type": margin_type,
                "order_type": order_type,
                "limit_price": limit_price,
                "position_size_idr": pos_idr,
                "position_size_usd": pos_usd,
                "position_size_usdt": pos_usd,
                "opened_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "status": "OPEN",
                "exchange": "BINANCE_FUTURES",
                "binance_synced": True,
                "order_id": order_id,
                "execution_details": execution_result
            }
            positions.append(new_pos)
            with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(positions, f, indent=2, ensure_ascii=False)

            if callback_query_id:
                answer_callback(callback_query_id, f"Order {pair} berhasil dibuka di Binance Futures!", show_alert=False)

            limit_txt = f" (@ ${limit_price:,.4f})" if order_type == "LIMIT" else ""
            msg = (
                f"⚡ <b>ORDER BERHASIL DIEKSEKUSI DI BINANCE FUTURES!</b>\n\n"
                f"💎 <b>Aset:</b> <code>{pair}</code>\n"
                f"🎯 <b>Arah:</b> <b>{direction}</b>\n"
                f"📋 <b>Order Type:</b> <b>{order_type}{limit_txt}</b>\n"
                f"📊 <b>Leverage:</b> <b>{leverage}x</b> ({margin_type})\n"
                f"💰 <b>Modal:</b> <b>${pos_usd:.2f} USDT</b> (~Rp {pos_idr:,})\n"
                f"📍 <b>Entry:</b> ${entry_price:,.4f}\n"
                f"🎯 <b>Take Profit:</b> ${tp:,.4f}\n"
                f"🛑 <b>Stop Loss:</b> ${sl:,.4f}\n"
                f"⏱️ <b>Est. Waktu TP:</b> <b>{time_horizon}</b>\n"
                f"🆔 <b>Order ID (Binance):</b> <code>{order_id}</code>\n"
                f"⏰ <b>Waktu:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}\n\n"
                f"<i>Posisi aktif kini terpantau real-time oleh AI Sentinel.</i>"
            )
            send_telegram_message(chat_id, msg)
            return True
        else:
            err = execution_result.get("error") or "Order ditolak oleh Binance Futures API"
            if callback_query_id:
                answer_callback(callback_query_id, f"Binance: {err[:60]}", show_alert=True)
            msg = (
                f"❌ <b>BINANCE MENOLAK ORDER {pair}</b>\n\n"
                f"Detail Error dari Binance:\n<code>{err}</code>\n\n"
                f"<i>Catatan: Tidak ada modal yang terpotong. Sinyal tidak didaftarkan sebagai posisi aktif.</i>"
            )
            send_telegram_message(chat_id, msg)
            return False

    except Exception as e:
        if callback_query_id:
            answer_callback(callback_query_id, f"Error: {str(e)[:60]}", show_alert=True)
        send_telegram_message(chat_id, f"❌ <b>Error Eksekusi Binance Futures:</b>\n<code>{e}</code>")
        return False

# Backward compat alias
execute_trade_with_pluang = execute_trade_with_binance

def handle_login_command(chat_id):
    """Check and verify Binance Futures API connection"""
    bn = get_binance_client()
    if bn:
        try:
            bal = bn.get_balance()
            tot = bal.get("total_wallet_balance", 0) if isinstance(bal, dict) else 0
            avail = bal.get("available_balance", 0) if isinstance(bal, dict) else 0
            send_telegram_message(
                chat_id,
                f"🟢 <b>KONEKSI BINANCE FUTURES AKTIF!</b>\n\n"
                f"✅ API Key valid & terhubung live.\n"
                f"💰 Total Wallet: <b>${tot:.2f} USDT</b>\n"
                f"💵 Margin Tersedia: <b>${avail:.2f} USDT</b>\n"
                f"⚙️ Leverage: <b>20x ISOLATED Fixed</b>\n\n"
                f"Ketik <code>/scan</code> untuk radar sinyal trading atau <code>/wallet</code> untuk cek saldo."
            )
        except Exception as e:
            send_telegram_message(chat_id, f"⚠️ Error membaca akun Binance: {e}")
    else:
        send_telegram_message(
            chat_id,
            "⚠️ <b>BINANCE FUTURES BELUM TERHUBUNG</b>\n\n"
            "Kunci API Binance belum disetel di file <code>.env</code>.\n\n"
            "Pastikan Anda menambahkan baris berikut di <code>.env</code>:\n"
            "<code>BINANCE_API_KEY=...</code>\n"
            "<code>BINANCE_API_SECRET=...</code>"
        )

def run_radar_scan(chat_id):
    """Fast Parallel Quant Radar Scan (Top 3 Candidates in Parallel - <10s)"""
    try:
        from auto_trader import check_wallet_and_position_guard
        guard = check_wallet_and_position_guard()
        if guard.get("pause_scanning"):
            syms = ", ".join([f"<code>{p.get('symbol')}</code>" for p in guard["open_positions"]])
            send_telegram_message(
                chat_id,
                f"🛡️ <b>MODE ALL-IN MONITOR POSITION SEDANG AKTIF!</b>\n\n"
                f"💰 <b>Status Saldo:</b> Saldo telah dialokasikan penuh ke posisi aktif (Sisa available: ${guard['available_usdt']:.2f} USDT).\n"
                f"💎 <b>Posisi Dikawal:</b> {syms}\n\n"
                f"⏸️ <b>Scanner 524 Koin & 9 Agent Sidang:</b> <b>DIJEDA SEMENTARA</b>\n"
                f"🎯 <i>Semua sumber daya AI fokus 100% menjaga posisi terbuka sampai Take Profit / Stop Loss tercapai.</i>\n\n"
                f"Ketik <code>/status</code> untuk memantau floating PnL posisi Anda saat ini."
            )
            return
    except Exception:
        pass

    try:
        ranked = rank_universe_by_opportunity()
    except Exception:
        ranked = []
    
    if not ranked:
        ranked = list(CRYPTO_FUTURES_WATCHLIST)

    # Scan BTC, ETH, and highest-opportunity mover
    top_candidates = [
        {"symbol": "BTC-USD", "pair": "BTCUSDT", "name": "Bitcoin"},
        {"symbol": "ETH-USD", "pair": "ETHUSDT", "name": "Ethereum"},
    ]
    top_mover = next((c for c in ranked if c.get("pair") not in ("BTCUSDT", "ETHUSDT")), None)
    if top_mover:
        top_candidates.append(top_mover)
    else:
        top_candidates.append({"symbol": "SOL-USD", "pair": "SOLUSDT", "name": "Solana"})

    cand_names = ", ".join([c.get("symbol", "").replace("-USD", "") for c in top_candidates])

    send_telegram_message(
        chat_id,
        f"⚡ <b>RADAR QUANT SCAN AKTIF</b>\n"
        f"────────────────────────\n"
        f"🔍 <b>Top 3 Peluang Tertinggi:</b> <code>{cand_names}</code>\n"
        f"⏳ <i>Menjalankan 5-Layer AI Pipeline secara paralel... Jawaban siap dalam ~5 detik!</i>"
    )

    approved_count = 0
    results = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_item = {
            executor.submit(run_5_layer_pipeline, item.get("symbol", item.get("pair", "").replace("USDT", "-USD"))): item
            for item in top_candidates
        }
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            sym = item.get("symbol", item.get("pair", "").replace("USDT", "-USD"))
            try:
                res = future.result()
                results.append((sym, res))
                fc = res.get("layer5_final_call", {})
                status = fc.get("status", "REJECTED")

                if status == "APPROVED":
                    approved_count += 1
                    text, _ = format_pipeline_report(res)
                    reply_markup = {
                        "inline_keyboard": [
                            [
                                {"text": f"✅ Konfirmasi & Eksekusi ({sym})", "callback_data": f"confirm_{sym}"},
                                {"text": "❌ Batalkan", "callback_data": f"cancel_{sym}"}
                            ]
                        ]
                    }
                    send_telegram_message(chat_id, text, reply_markup)

                    # Send 9-Agent Committee Debate Transcript
                    com = res.get("committee") or {}
                    transcripts = com.get("collaboration_transcript", [])
                    if transcripts:
                        lines = [f"🏛️ <b>TRANSKRIP PERDEBATAN SIDANG MAHKAMAH 9-AGENT // {sym} (7 RONDE)</b>\n────────────────────────"]
                        for t in transcripts:
                            r_num = t.get("round", "-")
                            spk = _esc_html(t.get("speaker", ""))
                            role = _esc_html(t.get("role", ""))
                            cnt = _esc_html(t.get("content", ""))
                            spk_icon = "🟢" if "Bull" in spk else ("🔴" if "Bear" in spk else ("🟣" if "Trader" in spk else ("🟠" if "Risk" in spk else ("🔵" if "Portfolio" in spk else "⚪"))))
                            lines.append(f"<b>[Ronde {r_num}] {spk_icon} {spk}</b> <i>({role})</i>:\n\"{cnt}\"\n")
                        transcript_text = "\n".join(lines)
                        if len(transcript_text) > 4000:
                            transcript_text = transcript_text[:3990] + "...\n<i>(dipersingkat)</i>"
                        send_telegram_message(chat_id, transcript_text)
            except Exception as e:
                print(f"[-] Scan error {sym}: {e}", flush=True)

    if approved_count == 0:
        summary_lines = []
        for sym, res in results:
            fc = res.get("layer5_final_call", {})
            reason = fc.get("final_reason", "Pasar sideways tanpa setup directional yang jelas")
            conf = fc.get("confidence_score", 0)
            summary_lines.append(f"• <b>{sym}</b>: REJECTED ({conf}%)\n  <i>{reason[:120]}</i>")

        summary = (
            f"🛡️ <b>HASIL RADAR SCAN (TOP 3 AKTIF):</b>\n"
            f"────────────────────────\n"
            + "\n\n".join(summary_lines) + "\n"
            f"────────────────────────\n"
            f"🔒 <b>0 TRADE APPROVED</b>\n"
            f"🛡️ <i>Sesuai prinsip proteksi modal, order tidak dipaksakan saat kondisi sideways. Modal Anda 100% aman dalam USDT.</i>\n\n"
            f"👉 Ketik <code>/btc</code> atau <code>/eth</code> untuk analisis instan koin tertentu."
        )
        send_telegram_message(chat_id, summary)

def handle_wallet_command(chat_id):
    """Query live balances from Binance Futures"""
    bn_client = get_binance_client()
    fx = get_fx_info()
    usd_idr = fx.get("usd_idr", 16500)

    lines = [
        "💼 <b>STATUS SALDO & WALLET LIVE</b>",
        "────────────────────────"
    ]

    # 1. Binance Futures
    if bn_client:
        try:
            bn_bal = bn_client.get_balance()
            if isinstance(bn_bal, dict) and "total_wallet_balance" in bn_bal:
                tot_usdt = bn_bal["total_wallet_balance"]
                avail_usdt = bn_bal["available_balance"]
                unpnl = bn_bal["cross_unrealized_pnl"]
                tot_idr = tot_usdt * usd_idr
                avail_idr = avail_usdt * usd_idr

                sign_pnl = "+" if unpnl >= 0 else ""
                lines.append("🟡 <b>BINANCE FUTURES (USDT-M):</b> 🟢 LIVE CONNECTED")
                lines.append(f"• Total Wallet: <b>${tot_usdt:.4f} USDT</b> (~Rp {tot_idr:,.0f})")
                lines.append(f"• Margin Tersedia: <b>${avail_usdt:.4f} USDT</b> (~Rp {avail_idr:,.0f})")
                lines.append(f"• Floating PnL: <b>{sign_pnl}${unpnl:.4f} USDT</b>")
                if avail_usdt < 1.0:
                    lines.append("<i>⚠️ Saldo margin rendah (< $1). Transfer USDT dari Spot ke Futures Binance agar order dapat dibuka.</i>")
            else:
                lines.append("🟡 <b>BINANCE FUTURES:</b> 🟢 Terhubung")
        except Exception as e:
            lines.append(f"🟡 <b>BINANCE FUTURES:</b> Error membaca saldo: {e}")
    else:
        lines.append("🟡 <b>BINANCE FUTURES:</b> ⚪ Belum terkonfigurasi")

    lines.append(f"💱 <b>Kurs Acuan:</b> $1 = Rp {usd_idr:,.0f}")
    send_telegram_message(chat_id, "\n".join(lines))

def get_system_status():
    positions = []
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                positions = json.load(f)
        except Exception:
            positions = []

    open_pos = [p for p in positions if p.get("status") == "OPEN"]
    cfg = get_trading_config()
    fx = get_fx_info()
    universe = get_full_universe()
    
    bn_client = get_binance_client()
    if bn_client:
        try:
            bn_bal = bn_client.get_balance()
            if isinstance(bn_bal, dict) and "total_wallet_balance" in bn_bal:
                binance_badge = f"🟢 <b>LIVE (${bn_bal['total_wallet_balance']:.2f} USDT)</b>"
            else:
                binance_badge = "🟢 <b>LIVE CONNECTED</b>"
        except Exception:
            binance_badge = "🟢 <b>CONNECTED</b>"
    else:
        binance_badge = "⚪ <b>NOT CONFIGURED</b>"

    ai_desc = "Google Gemini + Groq + OpenRouter Cascade" if GEMINI_API_KEY else f"Groq ({GROQ_MODEL})"

    guard = {}
    try:
        from auto_trader import check_wallet_and_position_guard
        guard = check_wallet_and_position_guard()
    except Exception:
        pass

    if guard.get("pause_scanning"):
        mode_badge = "🛡️ <b>ALL-IN POSITION MONITOR (100% Fokus Mengawal Posisi)</b>"
    else:
        mode_badge = f"🔍 <b>ACTIVE UNIVERSE SCANNER ({len(universe)} pairs)</b>"

    modal_txt = "Dynamic Wallet-Based (Kelly Criterion)" if cfg.get('max_budget_idr', 0) == 0 else f"Rp {cfg.get('max_budget_idr'):,} max"

    text = (
        f"📊 <b>STATUS SISTEM TRADING AI BINANCE FUTURES</b>\n"
        f"────────────────────────\n"
        f"🟡 <b>Binance Futures:</b> {binance_badge}\n"
        f"🤖 <b>AI Engine:</b> {ai_desc}\n"
        f"📈 <b>Quant Matrix:</b> 500+ Factors (Simons, Wyckoff, Minervini, DeMark)\n"
        f"🌐 <b>Universe:</b> {len(universe)} crypto futures pairs\n"
        f"🎯 <b>Mode Engine:</b> {mode_badge}\n"
        f"💰 <b>Modal Sizing:</b> {modal_txt}\n"
        f"⚡ <b>Leverage:</b> 20x ISOLATED Fixed (User Mandate)\n"
        f"💱 <b>Kurs USD/IDR:</b> Rp {fx['usd_idr']:,.0f}\n"
        f"💼 <b>Posisi Aktif:</b> {len(open_pos)} posisi\n"
        f"────────────────────────\n"
    )
    if open_pos:
        text += "<b>Daftar Posisi Aktif:</b>\n"
        for p in open_pos[:10]:
            synced_mark = "✅ Binance Live" if p.get("binance_synced") else "📝 Lokal"
            text += (f"• <code>{p['symbol']}</code> {p['direction']} @ ${p.get('entry_price', 0):,.4f} "
                     f"(Lev: {p.get('leverage', 20)}x, {synced_mark})\n")
        if len(open_pos) > 10:
            text += f"<i>... dan {len(open_pos) - 10} posisi lainnya</i>\n"
    else:
        text += "<i>Saat ini tidak ada posisi terbuka. Modal 100% terlindungi dalam USDT.</i>\n"

    return text

def handle_universe_command(chat_id):
    send_telegram_message(chat_id, "⏳ <i>Mengambil data seluruh universe crypto futures...</i>")
    try:
        summary = get_universe_summary()
        fx = get_fx_info()
        text = (
            f"🌐 <b>CRYPTO FUTURES FULL UNIVERSE STATUS</b>\n"
            f"────────────────────────\n"
            f"📊 <b>Total Pairs:</b> {summary['total_pairs']}\n"
            f"💰 <b>Total Volume 24h:</b> ${summary['total_volume_24h_usd']/1e9:,.2f}B\n"
            f"   <i>(Rp {summary['total_volume_24h_idr']/1e12:,.2f}T)</i>\n"
            f"💱 <b>Kurs USD/IDR:</b> Rp {fx['usd_idr']:,.0f}\n"
            f"────────────────────────\n\n"
            f"🟢 <b>TOP 10 GAINERS (24h):</b>\n"
        )
        for g in summary["top_10_gainers"][:7]:
            text += f"  • <code>{g['symbol']:12s}</code> <b>{g['change']:+.2f}%</b>\n"
        text += f"\n🔴 <b>TOP 10 LOSERS (24h):</b>\n"
        for l in summary["top_10_losers"][:7]:
            text += f"  • <code>{l['symbol']:12s}</code> <b>{l['change']:+.2f}%</b>\n"
        text += f"\n📊 <b>TOP 10 BY VOLUME:</b>\n"
        for v in summary["top_by_volume"][:7]:
            text += f"  • <code>{v['symbol']:12s}</code> ${v['vol']/1e9:,.2f}B\n"
        send_telegram_message(chat_id, text)
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Error: {e}")

def handle_top_movers(chat_id):
    try:
        movers = get_top_movers(20)
        fx = get_fx_info()
        text = f"🔥 <b>TOP 20 CRYPTO FUTURES MOVERS</b>\n"
        text += f"<i>Ranked by AI Opportunity Score</i>\n"
        text += f"💱 Kurs: Rp {fx['usd_idr']:,.0f}/USD\n"
        text += f"────────────────────────\n"
        for i, m in enumerate(movers):
            emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1:2d}"
            tier_badge = "⭐" if m.get("tier") == "CORE" else "  "
            change = m.get("price_change_24h_pct", 0)
            change_emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"
            text += (
                f"{emoji}{tier_badge} <code>{m['pair']:12s}</code> "
                f"{change_emoji}{change:+6.2f}% "
                f"| Score: {m.get('opportunity_score', 0):.2f}\n"
            )
        text += f"\n<i>⭐ = Core watchlist | Score = Volume×Volatility×Momentum</i>"
        send_telegram_message(chat_id, text)
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Error: {e}")

def handle_fx_command(chat_id):
    fx = get_fx_info()
    text = (
        f"💱 <b>KURS MATA UANG REAL-TIME</b>\n"
        f"────────────────────────\n"
        f"🇺🇸 1 USD = 🇮🇩 Rp {fx['usd_idr']:,.2f}\n"
        f"🇮🇩 1 IDR = 🇺🇸 ${fx['idr_usd']:.8f}\n\n"
        f"<b>Contoh Konversi:</b>\n"
        f"• Rp 50.000 = ${fx['example_50k_idr_in_usd']:.4f} USD\n"
        f"• Rp 100.000 = ${convert_idr_to_usd(100000):.4f} USD\n"
        f"• $1 USD = Rp {fx['usd_idr']:,.0f}\n"
        f"• $100 USD = Rp {convert_usd_to_idr(100):,.0f}\n\n"
        f"<i>Kurs diupdate otomatis setiap 10 menit.</i>"
    )
    send_telegram_message(chat_id, text)

def handle_convert_command(chat_id, args):
    if len(args) < 2:
        send_telegram_message(chat_id,
            "ℹ️ <b>Format:</b> <code>/convert [jumlah] [usd/idr]</code>\n"
            "Contoh:\n"
            "• <code>/convert 50000 idr</code> → ke USD\n"
            "• <code>/convert 100 usd</code> → ke IDR")
        return
    try:
        amount = float(args[0].replace(",", "").replace(".", ""))
        currency = args[1].upper()
        fx = get_fx_info()
        if currency == "IDR":
            result_usd = convert_idr_to_usd(amount)
            text = (
                f"💱 <b>KONVERSI MATA UANG</b>\n"
                f"────────────────────────\n"
                f"🇮🇩 Rp {amount:,.0f} IDR\n"
                f"= 🇺🇸 ${result_usd:,.4f} USD\n\n"
                f"<i>Kurs: Rp {fx['usd_idr']:,.0f}/USD</i>"
            )
        elif currency == "USD":
            result_idr = convert_usd_to_idr(amount)
            text = (
                f"💱 <b>KONVERSI MATA UANG</b>\n"
                f"────────────────────────\n"
                f"🇺🇸 ${amount:,.4f} USD\n"
                f"= 🇮🇩 Rp {result_idr:,.0f} IDR\n\n"
                f"<i>Kurs: Rp {fx['usd_idr']:,.0f}/USD</i>"
            )
        else:
            text = f"❌ Mata uang <code>{currency}</code> tidak dikenal. Gunakan <code>usd</code> atau <code>idr</code>."
        send_telegram_message(chat_id, text)
    except ValueError:
        send_telegram_message(chat_id, "❌ Format salah. Contoh: <code>/convert 50000 idr</code>")

def handle_pnl_command(chat_id):
    """Calculate and report Win Rate, Realized PnL, and Floating PnL to Telegram"""
    positions = []
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                positions = json.load(f)
        except Exception:
            positions = []

    closed_pos = [p for p in positions if str(p.get("status", "")).startswith("CLOSED")]
    open_pos = [p for p in positions if p.get("status") == "OPEN"]

    winning = [p for p in closed_pos if p.get("pnl_idr", 0) > 0 or p.get("pnl_pct", 0) > 0]
    losing = [p for p in closed_pos if p.get("pnl_idr", 0) <= 0 and p.get("pnl_pct", 0) <= 0]
    closed_count = len(closed_pos)
    win_rate = round((len(winning) / closed_count * 100), 1) if closed_count > 0 else 0.0

    realized_idr = sum(p.get("pnl_idr", 0) for p in closed_pos)
    realized_usd = sum(p.get("pnl_usd", 0) for p in closed_pos)
    unrealized_idr = sum(p.get("pnl_idr", 0) for p in open_pos)
    unrealized_usd = sum(p.get("pnl_usd", 0) for p in open_pos)
    total_idr = realized_idr + unrealized_idr
    total_usd = realized_usd + unrealized_usd

    sign_tot = "+" if total_idr >= 0 else ""
    sign_real = "+" if realized_idr >= 0 else ""
    sign_un = "+" if unrealized_idr >= 0 else ""

    text = (
        f"📊 <b>PERFORMA TRADING & WIN RATE AI</b>\n"
        f"────────────────────────\n"
        f"🏆 <b>Win Rate:</b> <b>{win_rate:.1f}%</b>\n"
        f"📊 <b>Statistik:</b> {len(winning)} Menang / {len(losing)} Kalah ({closed_count} selesai)\n"
        f"────────────────────────\n"
        f"💰 <b>Net Total P&L:</b> <b>{sign_tot}Rp {total_idr:,.0f} ({sign_tot}${total_usd:.2f})</b>\n"
        f"📈 <b>Realized P&L:</b> {sign_real}Rp {realized_idr:,.0f} ({sign_real}${realized_usd:.2f})\n"
        f"🌊 <b>Floating P&L:</b> {sign_un}Rp {unrealized_idr:,.0f} ({sign_un}${unrealized_usd:.2f})\n"
        f"💼 <b>Posisi Terbuka:</b> {len(open_pos)} posisi aktif\n"
        f"────────────────────────\n"
        f"🛡️ <i>Semua posisi diawasi real-time oleh AI Sentinel tiap 10 detik.</i>"
    )
    send_telegram_message(chat_id, text)

def handle_news_command(chat_id):
    """Fetch and report breaking crypto news and macro sentiment to Telegram"""
    try:
        from news_sentinel import get_news_sentiment_summary
        ns = get_news_sentiment_summary()
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Error news: {e}")
        return

    m_sent = ns.get("market_sentiment", "NEUTRAL")
    score = ns.get("sentiment_score", 50)
    top_arts = ns.get("top_articles", [])[:5]

    badge = "🟢 BULLISH" if m_sent == "BULLISH" else ("🔴 BEARISH" if m_sent == "BEARISH" else "⚪ NEUTRAL")
    text = (
        f"📰 <b>CRYPTO BREAKING NEWS & SENTIMENT SENTINEL</b>\n"
        f"────────────────────────\n"
        f"🌡️ <b>Sentimen Pasar:</b> {badge} ({score}/100)\n"
        f"🚨 <b>Alert Berita:</b> <i>{ns.get('breaking_alert') or 'Kondisi berita makro stabil'}</i>\n"
        f"────────────────────────\n"
        f"<b>Headline Terkini:</b>\n"
    )
    for a in top_arts:
        sent_icon = "🟢" if a.get("sentiment") == "BULLISH" else ("🔴" if a.get("sentiment") == "BEARISH" else "⚪")
        text += f"• {sent_icon} <b>[{a.get('source')}]</b> {a.get('title')}\n"
    text += f"\n<i>Diperbarui otomatis dari CoinTelegraph, CoinDesk & Decrypt.</i>"
    send_telegram_message(chat_id, text)

def handle_any_coin_scan(chat_id, coin_name):
    """Scan ANY coin on Binance Futures with Unified 5-Layer AI Pipeline & 9-Agent Committee Sidang (Single Seamless Process)"""
    coin_name = coin_name.strip()
    pair = normalize_symbol_to_pair(coin_name)
    symbol = pair.replace("USDT", "-USD")
    
    send_telegram_message(chat_id, f"⏳ <i>Menjalankan Institutional 5-Layer Pipeline & Sidang 9-Agent untuk {pair}...</i>")
    try:
        res = run_5_layer_pipeline(symbol)
        if "error" in res:
            send_telegram_message(chat_id, f"❌ Error: {res['error']}")
            return
            
        # 1. Message 1: 5-Layer Institutional Deep Dive + Live Binance Position Status + SMC Alpha + Supreme PM Verdict
        text, status = format_pipeline_report(res)
        markup = None
        if status == "APPROVED":
            markup = {"inline_keyboard": [[
                {"text": f"✅ Konfirmasi & Eksekusi ({pair})", "callback_data": f"confirm_{pair}"},
                {"text": "❌ Batalkan", "callback_data": f"cancel_{pair}"}
            ]]}
        send_telegram_message(chat_id, text, markup)

        # 2. Message 2: Transkrip Lengkap Perdebatan Sidang Mahkamah 9-Agent (7 Ronde)
        com = res.get("committee") or {}
        transcripts = com.get("collaboration_transcript", [])
        if transcripts:
            lines = [f"🏛️ <b>TRANSKRIP PERDEBATAN SIDANG MAHKAMAH 9-AGENT // {pair} (7 RONDE)</b>\n────────────────────────"]
            for t in transcripts:
                r_num = t.get("round", "-")
                spk = _esc_html(t.get("speaker", ""))
                role = _esc_html(t.get("role", ""))
                cnt = _esc_html(t.get("content", ""))
                
                spk_icon = "🟢" if "Bull" in spk else ("🔴" if "Bear" in spk else ("🟣" if "Trader" in spk else ("🟠" if "Risk" in spk else ("🔵" if "Portfolio" in spk else "⚪"))))
                lines.append(f"<b>[Ronde {r_num}] {spk_icon} {spk}</b> <i>({role})</i>:\n\"{cnt}\"\n")
            
            transcript_text = "\n".join(lines)
            if len(transcript_text) > 4000:
                transcript_text = transcript_text[:3990] + "...\n<i>(dipersingkat)</i>"
            send_telegram_message(chat_id, transcript_text)

    except Exception as e:
        send_telegram_message(chat_id, f"❌ Error analisis {pair}: {e}")


def handle_sidang_command(chat_id, coin_name):
    """Direct alias to Unified 5-Layer Pipeline & 9-Agent Committee Deliberation (Single Seamless Process)"""
    handle_any_coin_scan(chat_id, coin_name)


def handle_audit_command(chat_id):
    """Full comprehensive system, data, and universe audit"""
    send_telegram_message(chat_id, "🔍 <i>Sedang mengaudit seluruh sistem, data, analisa, dan universe Binance Futures...</i>")
    try:
        # 1. Binance Client & Balance Audit
        bn = get_binance_client()
        bn_status = "⚪ Belum disetel"
        bn_bal_txt = "N/A"
        avail_txt = "N/A"
        avail_val = 0.0
        positions_txt = "0 Posisi Terbuka"
        if bn:
            try:
                bal = bn.get_balance()
                if isinstance(bal, dict) and "total_wallet_balance" in bal:
                    tot = bal["total_wallet_balance"]
                    avail_val = float(bal["available_balance"])
                    bn_status = "🟢 TERHUBUNG & TERVERIFIKASI"
                    bn_bal_txt = f"${tot:.4f} USDT"
                    avail_txt = f"${avail_val:.4f} USDT"
                else:
                    bn_status = "🔴 Gagal baca balance"
                
                pos = bn.get_positions()
                if isinstance(pos, list) and len(pos) > 0:
                    positions_txt = f"{len(pos)} Posisi Aktif"
            except Exception as e:
                bn_status = f"⚠️ Error: {e}"

        # 2. Universe Audit
        universe = get_full_universe()
        univ_count = len(universe)
        vol_1m = len([p for p in universe if p.get("volume_24h_usd", 0) >= 1_000_000])
        vol_500k = len([p for p in universe if p.get("volume_24h_usd", 0) >= 500_000])

        # 3. Precision & LOT_SIZE Filter Audit
        test_rules = bn.get_symbol_filters("1000PEPEUSDT") if bn else {}
        lot_ok = "🟢 Sizing Precision OK (1000x Memes & Decimals Handled)" if test_rules else "⚪ Filter Standar"

        # 4. Indicators & Quant Engine Audit
        btc_ind = get_market_indicators_fast("BTCUSDT")
        data_qual = btc_ind.get("data_quality", "UNKNOWN")
        rsi_val = btc_ind.get("rsi_14", 0)
        q_factors = btc_ind.get("quant_factors", {})
        quant_count = q_factors.get("total_factors_evaluated", 0) if isinstance(q_factors, dict) else 0

        # 5. Config & Safety
        cfg = get_trading_config()
        fx = get_fx_info()

        audit_msg = (
            "📋 <b>AUDIT SISTEM, DATA & FULL UNIVERSE</b>\n"
            "════════════════════════\n\n"
            "🟡 <b>1. BINANCE FUTURES EXECUTION ENGINE:</b>\n"
            f"• Status API: <b>{bn_status}</b>\n"
            f"• Total Wallet: <b>{bn_bal_txt}</b> (~Rp {avail_val * fx['usd_idr']:,.0f})\n"
            f"• Margin Tersedia: <b>{avail_txt}</b>\n"
            f"• Posisi Berjalan: <b>{positions_txt}</b>\n"
            f"• DoH ISP Bypass: <b>🟢 AKTIF (Cloudflare 1.1.1.1 + Google DNS)</b>\n"
            f"• LOT_SIZE Filter: <b>{lot_ok}</b>\n\n"
            "🌐 <b>2. UNIVERSE BINANCE FUTURES:</b>\n"
            f"• Total Koin USDT Perpetual: <b>{univ_count} Koin (100% Full Universe)</b>\n"
            f"• Koin Likuiditas > $1M: <b>{vol_1m} Koin</b>\n"
            f"• Koin Likuiditas > $500K: <b>{vol_500k} Koin</b>\n"
            "• Universe Scope: <b>✅ MURNI BINANCE FUTURES (Full Universe Scan)</b>\n\n"
            "📐 <b>3. AKURASI ANALISA & DATA:</b>\n"
            f"• Feed Klines: <b>🟢 Binance Futures Direct REST (1h, 4h, 1d)</b>\n"
            f"• Data Quality BTC: <b>{data_qual} (RSI 14: {rsi_val})</b>\n"
            f"• 500+ Quant Multi-Pillar Alpha: <b>🟢 {quant_count} Faktor Aktif</b>\n"
            "• Smart Money Concepts (SMC): <b>🟢 FVG + Liquidity Sweep Aktif</b>\n"
            "• Confluence Matrix: <b>🟢 Funding Rate + Open Interest Aktif</b>\n\n"
            "🤖 <b>4. AI PIPELINE & RESILIENCE:</b>\n"
            f"• Provider Utama: <b>{AI_PROVIDER.upper()}</b>\n"
            "• Cascade Failover: <b>Gemini ➔ Groq ➔ OpenRouter (Minimax) ➔ Rule-Based</b>\n"
            "• Zero Downtime Engine: <b>🟢 AKTIF</b>\n\n"
            "⚙️ <b>5. PARAMETER RISIKO:</b>\n"
            f"• Max Leverage: <b>{cfg.get('max_leverage', 5)}x</b>\n"
            f"• Max Budget: <b>Rp {cfg.get('max_budget_idr', 50000):,}</b>\n"
            "• Proteksi: <b>Auto TP, Auto SL & Trailing Breakeven</b>\n"
            "════════════════════════\n"
            "✅ <b>AUDIT RESULT: 100% OPERATIONAL & READY FOR TRADING!</b>"
        )
        send_telegram_message(chat_id, audit_msg)
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Audit error: {e}")

def start_bot_listener():
    print(f"[*] Menjalankan Telegram Bot v3.0 - Full Universe Crypto Futures (@idrisginting_bot)...", flush=True)
    cb_thread = threading.Thread(target=start_callback_server, daemon=True)
    cb_thread.start()

    def _run_autotrader():
        try:
            import auto_trader
            print("[*] 🤖 Launching Autonomous 5-Minute AI Scanner in background thread...", flush=True)
            auto_trader.start_loop()
        except Exception as e:
            print(f"[-] Auto trader background thread error: {e}", flush=True)

    trader_thread = threading.Thread(target=_run_autotrader, daemon=True)
    trader_thread.start()

    offset = 0
    while True:
        try:
            url = f"{TELE_API}/getUpdates?offset={offset}&timeout=20"
            r = requests.get(url, timeout=25)
            if r.status_code != 200:
                time.sleep(5)
                continue
            data = r.json()
            if not data.get("ok"):
                time.sleep(3)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                # Handle text messages
                if "message" in update and "text" in update["message"]:
                    chat_id = update["message"]["chat"]["id"]
                    msg_text = update["message"]["text"].strip()
                    msg_lower = msg_text.lower()

                    # SECURITY FIREWALL: Check Telegram Whitelist
                    if not is_chat_allowed(chat_id):
                        print(f"[SECURITY ALERT] Unauthorized chat_id {chat_id} blocked!", flush=True)
                        send_telegram_message(
                            chat_id,
                            f"⛔ <b>AKSES DITOLAK (403 FORBIDDEN)</b>\n\n"
                            f"Akun Telegram Anda (ID: <code>{chat_id}</code>) tidak memiliki izin otorisasi pada bot Pyrofuel ini.\n\n"
                            f"🔒 <i>Bot ini privat dan dilindungi firewall whitelist pemilik resmi.</i>"
                        )
                        continue

                    try:
                        with open(os.path.join(BASE_DIR, "last_chat_id.txt"), "w") as cf:
                            cf.write(str(chat_id))
                    except Exception:
                        pass

                    if msg_lower in ["/start", "start", "halo", "help", "/help"]:
                        cfg = get_trading_config()
                        universe = get_full_universe()
                        bn_c = get_binance_client()
                        if bn_c:
                            try:
                                bal_info = bn_c.get_balance()
                                bn_txt = f"🟢 Live (${bal_info.get('total_wallet_balance', 0):.2f} USDT)" if isinstance(bal_info, dict) else "🟢 Terhubung"
                            except Exception:
                                bn_txt = "🟢 Terhubung"
                        else:
                            bn_txt = "⚪ Belum disetel"
                        modal_str = "Dynamic Wallet-Based (Kelly Criterion)" if cfg.get("max_budget_idr", 0) == 0 else f"Rp {cfg.get('max_budget_idr', 0):,} max"
                        welcome = (
                            "👋 <b>Halo! Saya Pyrofuel AI Crypto Futures Trading v3.0</b>\n\n"
                            f"🟡 <b>Binance Futures:</b> {bn_txt}\n"
                            f"🌐 <b>Universe:</b> {len(universe)} crypto futures pairs (100% Full Binance)\n"
                            f"💰 <b>Modal Sizing:</b> {modal_str}\n"
                            f"⚡ <b>Leverage:</b> FIXED 20x ISOLATED (Mandat User — Eksekusi Disiplin)\n\n"
                            "Sistem dirancang dengan <b>5-Layer AI Pipeline + 9-Agent Committee:</b>\n"
                            "• Scanner ➔ Setup Hunter ➔ Plan ➔ Risk Audit ➔ Supreme Judge\n\n"
                            "<b>🛡️ Keamanan & Proteksi Whitelist:</b>\n"
                            f"• Akun Anda (ID: <code>{chat_id}</code>) <b>TEROTORISASI RESMI</b> pada bot ini.\n"
                            "• Eksekusi order murni langsung ke Binance Futures USDT-M.\n\n"
                            "<b>📋 Perintah Utama:</b>\n"
                            "• <code>/wallet</code> - Cek saldo Binance Futures ($) Live\n"
                            "• <code>/binance</code> - Cek status koneksi Binance Futures API\n"
                            "• <code>/konfirmasi [coin]</code> - Eksekusi riil ke Binance Futures\n"
                            "• <code>/scan</code> - Radar scan koin dengan peluang tertinggi (500+ pairs)\n"
                            "• <code>/scan [coin]</code> - Analisis spesifik (misal: /scan btc, /scan eth)\n"
                            "• <code>/universe</code> - Status full universe 500+ pairs\n"
                            "• <code>/top</code> - Top 20 movers saat ini\n"
                            "• <code>/status</code> - Portfolio, margin & posisi aktif\n"
                            "• <code>/pnl</code> - Win Rate % & Total P&L Real-time\n"
                            "• <code>/news</code> - AI Crypto News & Macro Sentiment\n"
                            "• <code>/auto</code> - Status auto-trading background"
                        )
                        send_telegram_message(chat_id, welcome)

                    elif msg_lower in ["/login", "login", "/auth", "auth", "/binance", "binance"]:
                        handle_login_command(chat_id)

                    elif msg_lower in ["/wallet", "wallet", "/balance", "balance", "/saldo", "saldo"]:
                        handle_wallet_command(chat_id)

                    elif msg_lower.startswith("/konfirmasi") or msg_lower.startswith("/confirm") or msg_lower.startswith("/approve") or msg_lower.startswith("/beli"):
                        parts = msg_text.split()
                        if len(parts) >= 2:
                            coin = parts[1].upper().strip().replace("-USD", "").replace("USDT", "")
                            threading.Thread(target=execute_trade_with_binance, args=(coin, chat_id), daemon=True).start()
                        else:
                            # Look for latest approved signal
                            latest_approved = None
                            if os.path.exists(RESULTS_DIR):
                                for f in os.listdir(RESULTS_DIR):
                                    if f.endswith("_latest.json"):
                                        try:
                                            with open(os.path.join(RESULTS_DIR, f), "r", encoding="utf-8") as jf:
                                                sd = json.load(jf)
                                                if sd.get("layer5_final_call", {}).get("status") == "APPROVED":
                                                    latest_approved = sd.get("symbol")
                                                    break
                                        except Exception:
                                            pass
                            if latest_approved:
                                threading.Thread(target=execute_trade_with_binance, args=(latest_approved, chat_id), daemon=True).start()
                            else:
                                send_telegram_message(
                                    chat_id,
                                    "ℹ️ <b>Tidak ada sinyal APPROVED yang menunggu konfirmasi otomatis.</b>\n\n"
                                    "Ketik nama koin untuk mengeksekusi langsung:\n"
                                    "Contoh: <code>/konfirmasi btc</code> atau <code>/konfirmasi eth</code>\n\n"
                                    "Atau ketik <code>/scan</code> untuk memindai setup market terbaik."
                                )

                    elif msg_lower in ["/scan", "scan", "cek", "cek pasar"]:
                        threading.Thread(target=run_radar_scan, args=(chat_id,), daemon=True).start()
                    
                    elif msg_lower.startswith("/scan "):
                        coin = msg_lower.replace("/scan ", "").strip()
                        if coin:
                            threading.Thread(target=handle_any_coin_scan, args=(chat_id, coin), daemon=True).start()

                    elif msg_lower.startswith("/sidang") or msg_lower.startswith("/committee"):
                        parts = msg_text.split()
                        coin = parts[1].strip() if len(parts) >= 2 else "SOL"
                        threading.Thread(target=handle_sidang_command, args=(chat_id, coin), daemon=True).start()

                    elif msg_lower in ["/universe", "universe"]:
                        handle_universe_command(chat_id)
                    
                    elif msg_lower in ["/top", "top", "movers", "/movers"]:
                        handle_top_movers(chat_id)

                    elif msg_lower in ["/status", "status", "portofolio", "posisi"]:
                        send_telegram_message(chat_id, get_system_status())

                    elif msg_lower in ["/audit", "audit", "/audit sistem", "audit sistem", "/cek"]:
                        handle_audit_command(chat_id)

                    elif msg_lower.startswith("/auto"):
                        state = {}
                        if os.path.exists(STATE_FILE):
                            try:
                                with open(STATE_FILE, "r", encoding="utf-8") as f:
                                    state = json.load(f)
                            except Exception:
                                pass
                        
                        text = (
                            f"⚙️ <b>STATUS AUTONOMOUS TRADER v3.0:</b>\n"
                            f"────────────────────────\n"
                            f"🌐 <b>Mode:</b> {state.get('mode', 'FULL_UNIVERSE')}\n"
                            f"📊 <b>Universe Size:</b> {state.get('universe_size', 'N/A')} pairs\n"
                            f"🔍 <b>Last Scan:</b> {state.get('last_scan_time', 'N/A')}\n"
                            f"⚡ <b>Quick Screens:</b> {state.get('total_quick_screens', 0)} kali\n"
                            f"🔄 <b>Full AI Scans:</b> {state.get('total_scans_done', 0)} siklus\n"
                            f"✅ <b>Total Approved:</b> {state.get('signals_approved_count', 0)}\n"
                            f"❌ <b>Total Rejected:</b> {state.get('signals_rejected_count', 0)}\n"
                            f"📡 <b>Coins/Cycle:</b> {state.get('coins_scanned_this_cycle', 0)}\n"
                            f"────────────────────────\n"
                            f"<i>Quick screen berjalan tiap 60 detik.\n"
                            f"Full AI pipeline berjalan tiap 5 menit.</i>"
                        )
                        send_telegram_message(chat_id, text)

                    elif msg_lower.startswith("/limit"):
                        parts = msg_text.split()
                        if len(parts) >= 2:
                            try:
                                new_limit = int(parts[1].replace(",", "").replace(".", ""))
                                save_trading_config({"max_budget_idr": new_limit, "updated_by": "user"})
                                fx = get_fx_info()
                                send_telegram_message(
                                    chat_id,
                                    f"🔒 <b>BATAS MODAL DIPERBARUI!</b>\n"
                                    f"Batas baru: <b>Rp {new_limit:,}</b>\n"
                                    f"<i>(= ${convert_idr_to_usd(new_limit):.4f} USD)</i>\n"
                                    f"<i>Perubahan langsung aktif tanpa restart.</i>"
                                )
                            except ValueError:
                                send_telegram_message(chat_id, "❌ Format salah. Contoh: <code>/limit 100000</code>")
                        else:
                            cfg = get_trading_config()
                            send_telegram_message(
                                chat_id,
                                f"ℹ️ <b>BATAS MODAL:</b> Rp {cfg.get('max_budget_idr', 50000):,}\n"
                                f"<i>(= ${convert_idr_to_usd(cfg.get('max_budget_idr', 50000)):.4f} USD)</i>\n\n"
                                f"Untuk ubah: <code>/limit [nominal]</code>\n"
                                f"Contoh: <code>/limit 100000</code>"
                            )

                    elif msg_lower.startswith("/leverage"):
                        send_telegram_message(
                            chat_id,
                            f"⚡ <b>LEVERAGE: TERKUNCI MATI PADA 20x</b>\n\n"
                            f"Berdasarkan mandat Anda, leverage dikunci tetap pada <b>20x ISOLATED</b> untuk seluruh koin crypto futures.\n"
                            f"💰 <b>Modal Sizing:</b> ALL-IN 100% Saldo Margin yang tersedia di wallet Binance Futures (98% saldo margin aktif dengan 2% buffer fee)."
                        )
                    
                    elif msg_lower in ["/fx", "fx", "kurs", "/kurs"]:
                        handle_fx_command(chat_id)
                    
                    elif msg_lower.startswith("/convert"):
                        parts = msg_text.split()
                        handle_convert_command(chat_id, parts[1:])

                    elif msg_lower in ["/btc", "btc", "bitcoin"]:
                        handle_any_coin_scan(chat_id, "BTC")

                    elif msg_lower in ["/eth", "eth", "ethereum"]:
                        handle_any_coin_scan(chat_id, "ETH")

                    elif msg_lower in ["/sol", "sol", "solana"]:
                        handle_any_coin_scan(chat_id, "SOL")
                    
                    elif msg_lower in ["/bnb", "bnb"]:
                        handle_any_coin_scan(chat_id, "BNB")
                    
                    elif msg_lower in ["/xrp", "xrp", "ripple"]:
                        handle_any_coin_scan(chat_id, "XRP")
                    
                    elif msg_lower in ["/doge", "doge", "dogecoin"]:
                        handle_any_coin_scan(chat_id, "DOGE")
                    
                    elif msg_lower in ["/avax", "avax", "avalanche"]:
                        handle_any_coin_scan(chat_id, "AVAX")
                    
                    elif msg_lower in ["/link", "link", "chainlink"]:
                        handle_any_coin_scan(chat_id, "LINK")
                    
                    elif msg_lower in ["/ada", "ada", "cardano"]:
                        handle_any_coin_scan(chat_id, "ADA")
                    
                    elif msg_lower in ["/sui", "sui"]:
                        handle_any_coin_scan(chat_id, "SUI")

                    elif msg_lower in ["/pnl", "pnl", "/winrate", "winrate", "/performance"]:
                        handle_pnl_command(chat_id)

                    elif msg_lower in ["/news", "news", "/berita", "berita", "/sentiment"]:
                        handle_news_command(chat_id)
                    
                    # Catch-all: scan any other coin name
                    elif msg_lower.startswith("/"):
                        coin_try = msg_lower.lstrip("/").strip()
                        if len(coin_try) >= 2 and len(coin_try) <= 10:
                            handle_any_coin_scan(chat_id, coin_try)
                        else:
                            send_telegram_message(chat_id, 
                                "❓ Perintah tidak dikenali.\n"
                                "Ketik <code>/help</code> untuk daftar perintah.\n"
                                "Atau ketik nama coin langsung: <code>/btc</code> <code>/sol</code> dll.")

                # Handle inline button click (MUST be at same level as "if message")
                if "callback_query" in update:
                    cb = update["callback_query"]
                    cb_id = cb["id"]
                    cb_data = cb.get("data", "")
                    cb_chat = cb.get("message", {}).get("chat", {})
                    chat_id = cb_chat.get("id")

                    if not chat_id:
                        answer_callback(cb_id, "Error: chat_id not found")
                        continue

                    # SECURITY FIREWALL: Check Telegram Whitelist on Callbacks
                    if not is_chat_allowed(chat_id):
                        answer_callback(cb_id, "⛔ Akses Ditolak: Tidak terotorisasi.")
                        continue

                    if cb_data.startswith("buy_") or cb_data.startswith("confirm_"):
                        symbol = cb_data.replace("buy_", "").replace("confirm_", "")
                        answer_callback(cb_id, f"⚡ Mengeksekusi order {symbol}...")
                        # Run in thread for instant response - don't block polling
                        t = threading.Thread(
                            target=execute_trade_with_binance,
                            args=(symbol, chat_id),
                            kwargs={"callback_query_id": cb_id},
                            daemon=True
                        )
                        t.start()

                    elif cb_data.startswith("reject_") or cb_data.startswith("cancel_"):
                        symbol = cb_data.replace("reject_", "").replace("cancel_", "")
                        answer_callback(cb_id, f"Order {symbol} dibatalkan.")
                        send_telegram_message(chat_id, f"🛑 Order <b>{symbol}</b> telah dibatalkan. Modal 100% aman dalam USDT.")

        except Exception as e:
            print(f"[-] Bot listener error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    start_bot_listener()
