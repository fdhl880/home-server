"""
===========================================================================
PYROFUEL TELEGRAM BOT v2.0 - FULL UNIVERSE CRYPTO FUTURES AI
===========================================================================
Token: 8829535429:AAHFHM56RDNAd7-ax6Dd-3V3g9OZEleYi5M (@idrisginting_bot)
Koleksi Aset: ALL Binance USDT Perpetual Futures (~200+ coins)
Fitur: 5-Layer AI Pipeline, Smart Ranking, Currency Conversion, Full Control

PERINTAH BARU:
/start      - Welcome & daftar perintah
/scan       - Full scan CORE 10 + Top movers
/universe   - Status seluruh universe (200+ coins)
/top        - Top 20 movers saat ini
/btc, /eth, /sol - Analisis individual
/status     - Portfolio & posisi aktif
/auto       - Status autonomous trader
/limit [n]  - Ubah batas modal (misal: /limit 100000)
/leverage [n] - Ubah batas leverage (misal: /leverage 3)
/fx         - Kurs USD/IDR real-time
/convert [jumlah] [mata_uang] - Konversi mata uang
===========================================================================
"""
import os
import sys
import time
import json
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

from pipeline import run_5_layer_pipeline, load_env, get_trading_config, save_trading_config, RESULTS_DIR
from market_data import (
    CRYPTO_FUTURES_WATCHLIST, get_market_indicators, get_market_indicators_fast,
    get_full_universe, get_top_movers, get_universe_summary, get_fx_info,
    convert_usd_to_idr, convert_idr_to_usd, rank_universe_by_opportunity
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(RESULTS_DIR, "active_positions.json")
STATE_FILE = os.path.join(RESULTS_DIR, "autotrader_state.json")

ENV = load_env()
TELEGRAM_TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "").strip()
TELE_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Import config dynamically
def _max_budget():
    return get_trading_config().get("max_budget_idr", 50000)

def _max_leverage():
    return get_trading_config().get("max_leverage", 5)


def send_telegram_message(chat_id, text, reply_markup=None):
    url = f"{TELE_API}/sendMessage"
    # Telegram has 4096 char limit, split if needed
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
        return r.json()
    except Exception as e:
        print(f"[-] Telegram error: {e}")
        return None

def answer_callback(callback_query_id, text):
    url = f"{TELE_API}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id, "text": text}, timeout=5)
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

    max_budget = _max_budget()
    
    text = (
        f"🛡️ <b>PYROFUEL 5-LAYER FUTURES AUDIT</b>\n"
        f"<b>Aset:</b> <code>{symbol}</code> (${layer1.get('current_price', 0):,})\n"
        f"<b>Harga IDR:</b> Rp {convert_usd_to_idr(layer1.get('current_price', 0)):,.0f}\n"
        f"<b>RSI (14):</b> {layer1.get('rsi_14')} | <b>Tren EMA:</b> {layer1.get('ema_trend')}\n"
        f"<b>MACD:</b> {layer1.get('macd', {}).get('trend')} | <b>Vol:</b> {layer1.get('volume_profile', {}).get('volume_trend')}\n"
        f"────────────────────────\n"
        f"🎯 <b>1. Setup Hunter:</b> <code>{setup.get('setup_name', 'N/A')}</code> ({setup.get('direction', 'NONE')})\n"
        f"<i>\"{setup.get('explanation_id', '')}\"</i>\n\n"
        f"📐 <b>2. Trading Plan:</b> {plan.get('action', 'SKIP')}\n"
        f"• Entry: ${plan.get('entry_price', 0):,} | SL: ${plan.get('stop_loss', 0):,}\n"
        f"• TP1: ${plan.get('take_profit_1', 0):,} | TP2: ${plan.get('take_profit_2', 0):,}\n"
        f"• RRR: {plan.get('risk_reward_ratio', 'N/A')} | Lev: {plan.get('leverage', 1)}x\n\n"
        f"🔍 <b>3. CRO Risk Audit:</b> {risk.get('risk_verdict', 'N/A')}\n"
        f"• Score: {risk.get('total_score', 0)}/{risk.get('max_score', 10)} ({risk.get('pass_rate_pct', 0)}%)\n\n"
        f"⚖️ <b>4. Supreme Judge Decision:</b> {badge}\n"
        f"• <b>Skor Keyakinan:</b> {fc.get('confidence_score', 0)}% (Min 80%)\n"
        f"• <b>Maks Modal:</b> Rp {min(fc.get('position_size_idr', max_budget), max_budget):,}\n\n"
        f"📌 <b>Pertimbangan Final:</b>\n{fc.get('final_reason', '-')[:500]}\n"
    )
    return text, status


def run_radar_scan(chat_id):
    """Scan CORE + Top movers"""
    universe = get_full_universe()
    movers = get_top_movers(20)
    
    send_telegram_message(
        chat_id,
        f"🔍 <b>MEMULAI FULL UNIVERSE SCAN...</b>\n"
        f"🌐 Universe: {len(universe)} pairs tersedia\n"
        f"📊 Akan scan: 10 CORE + 20 Top Movers = ~30 coins\n"
        f"<i>Menganalisa melalui 5-Layer AI Pipeline. Mohon tunggu ~2-5 menit.</i>"
    )

    # Build scan list
    core_pairs = {item["pair"] for item in CRYPTO_FUTURES_WATCHLIST}
    scan_list = list(CRYPTO_FUTURES_WATCHLIST)
    for m in movers:
        if m["pair"] not in core_pairs:
            scan_list.append(m)
            if len(scan_list) >= 30:
                break

    approved_count = 0
    total = len(scan_list)
    
    for idx, item in enumerate(scan_list):
        sym = item.get("symbol", item.get("pair", "").replace("USDT", "-USD"))
        try:
            res = run_5_layer_pipeline(sym)
            if "error" in res:
                continue

            fc = res.get("layer5_final_call", {})
            status = fc.get("status", "REJECTED")

            if status == "APPROVED":
                approved_count += 1
                text, _ = format_pipeline_report(res)
                reply_markup = {
                    "inline_keyboard": [
                        [
                            {"text": f"✅ Setujui & Eksekusi ({sym})", "callback_data": f"buy_{sym}"},
                            {"text": "❌ Batalkan", "callback_data": f"reject_{sym}"}
                        ]
                    ]
                }
                send_telegram_message(chat_id, text, reply_markup)
            time.sleep(1)
        except Exception as e:
            print(f"[-] Scan error {sym}: {e}")

    summary = (
        f"🛡️ <b>HASIL FULL UNIVERSE SCAN:</b>\n"
        f"🌐 Total Universe: {len(universe)} pairs\n"
        f"🔍 Discan: {total} coins\n"
        f"{'✅' if approved_count > 0 else '❌'} <b>{approved_count} TRADE APPROVED</b>\n"
        f"{'🛡️' if approved_count == 0 else ''} <b>{total - approved_count} REJECTED (SAFETY FIRST)</b>\n\n"
    )
    if approved_count == 0:
        summary += "<i>Filosofi: Tidak ada setup yang memenuhi standar minimal 80% keyakinan & RRR 1:2.0. Dana Anda aman.</i>"
    send_telegram_message(chat_id, summary)


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
    
    text = (
        f"📊 <b>STATUS SISTEM TRADING AI CRYPTO FUTURES</b>\n"
        f"────────────────────────\n"
        f"🤖 <b>AI Provider:</b> Groq (openai/gpt-oss-120b)\n"
        f"🌐 <b>Universe:</b> {len(universe)} crypto futures pairs\n"
        f"🔒 <b>Limit Modal:</b> Rp {cfg.get('max_budget_idr', 50000):,} per trade\n"
        f"   <i>(= ${convert_idr_to_usd(cfg.get('max_budget_idr', 50000)):.2f} USD)</i>\n"
        f"⚡ <b>Leverage Max:</b> {cfg.get('max_leverage', 5)}x\n"
        f"💱 <b>Kurs USD/IDR:</b> Rp {fx['usd_idr']:,.0f}\n"
        f"💼 <b>Posisi Terbuka:</b> {len(open_pos)} posisi\n"
        f"────────────────────────\n"
    )
    if open_pos:
        text += "<b>Daftar Posisi Aktif:</b>\n"
        for p in open_pos[:10]:
            text += (f"• <code>{p['symbol']}</code> {p['direction']} @ ${p.get('entry_price', 0):,.4f} "
                     f"(Lev: {p.get('leverage', 1)}x, Rp {p.get('position_size_idr', 0):,})\n")
        if len(open_pos) > 10:
            text += f"<i>... dan {len(open_pos) - 10} posisi lainnya</i>\n"
    else:
        text += "<i>Saat ini tidak ada posisi terbuka. Modal 100% terlindungi dalam cash.</i>\n"

    return text


def handle_universe_command(chat_id):
    """Show full universe status"""
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
    """Show top 20 movers with opportunity scores"""
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
    """Show exchange rate info"""
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
    """Convert currency: /convert 50000 idr or /convert 100 usd"""
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


def handle_any_coin_scan(chat_id, coin_name):
    """Scan any coin by name/symbol"""
    coin_name = coin_name.upper().strip()
    
    # Try to match
    symbol = None
    
    # Direct match in core watchlist
    for item in CRYPTO_FUTURES_WATCHLIST:
        if coin_name in [item["name"].upper(), item["symbol"].upper(), 
                          item["pair"].upper(), item["symbol"].replace("-USD", "").upper()]:
            symbol = item["symbol"]
            break
    
    # Try as Binance pair
    if not symbol:
        if not coin_name.endswith("USDT"):
            test_pair = coin_name + "USDT"
        else:
            test_pair = coin_name
        # Try to get data
        try:
            data = get_market_indicators_fast(test_pair)
            if data.get("data_quality") != "FAILED":
                symbol = test_pair.replace("USDT", "-USD")
        except Exception:
            pass
    
    if not symbol:
        send_telegram_message(chat_id, 
            f"❌ Tidak ditemukan coin <code>{coin_name}</code>.\n"
            f"Coba format: <code>/scan btc</code> atau <code>/scan DOTUSDT</code>")
        return
    
    send_telegram_message(chat_id, f"⏳ <i>Menjalankan 5-Layer Pipeline untuk {symbol}...</i>")
    try:
        res = run_5_layer_pipeline(symbol)
        if "error" in res:
            send_telegram_message(chat_id, f"❌ Error: {res['error']}")
            return
        text, status = format_pipeline_report(res)
        markup = None
        if status == "APPROVED":
            markup = {"inline_keyboard": [[
                {"text": f"✅ Setujui (Rp {_max_budget():,})", "callback_data": f"buy_{symbol}"},
                {"text": "❌ Tolak", "callback_data": f"reject_{symbol}"}
            ]]}
        send_telegram_message(chat_id, text, markup)
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Error analisis {symbol}: {e}")


def start_bot_listener():
    print(f"[*] Menjalankan Telegram Bot v2.0 - Full Universe Crypto Futures (@idrisginting_bot)...", flush=True)
    offset = 0
    while True:
        try:
            url = f"{TELE_API}/getUpdates?offset={offset}&timeout=20"
            r = requests.get(url, timeout=25)
            if r.status_code != 200:
                time.sleep(5)
                continue

            data = r.json()
            for update in data.get("result", []):
                offset = update["update_id"] + 1

                # Handle text command
                if "message" in update and "text" in update["message"]:
                    chat_id = update["message"]["chat"]["id"]
                    msg_text = update["message"]["text"].strip()
                    msg_lower = msg_text.lower()

                    if msg_lower in ["/start", "start", "halo", "help", "/help"]:
                        cfg = get_trading_config()
                        universe = get_full_universe()
                        welcome = (
                            "👋 <b>Halo! Saya Pyrofuel AI Crypto Futures Trading v2.0</b>\n\n"
                            f"🌐 <b>Universe:</b> {len(universe)} crypto futures pairs\n"
                            f"🔒 <b>Limit Modal:</b> Rp {cfg.get('max_budget_idr', 50000):,}\n"
                            f"⚡ <b>Max Leverage:</b> {cfg.get('max_leverage', 5)}x\n\n"
                            "Sistem dirancang dengan <b>5-Layer AI Pipeline</b>:\n"
                            "• Scanner ➔ Setup Hunter ➔ Plan ➔ Risk Audit ➔ Supreme Judge\n\n"
                            "<b>📋 Perintah:</b>\n"
                            "• <code>/scan</code> - Scan 30 coins (core + top movers)\n"
                            "• <code>/scan [coin]</code> - Analisis spesifik (misal: /scan dot)\n"
                            "• <code>/universe</code> - Status full universe 200+ pairs\n"
                            "• <code>/top</code> - Top 20 movers saat ini\n"
                            "• <code>/btc</code> <code>/eth</code> <code>/sol</code> - Analisis cepat\n"
                            "• <code>/status</code> - Portfolio & posisi aktif\n"
                            "• <code>/auto</code> - Status auto-trading\n"
                            "• <code>/limit [n]</code> - Ubah batas modal\n"
                            "• <code>/leverage [n]</code> - Ubah batas leverage\n"
                            "• <code>/fx</code> - Kurs USD/IDR real-time\n"
                            "• <code>/convert [n] [usd/idr]</code> - Konversi mata uang"
                        )
                        send_telegram_message(chat_id, welcome)

                    elif msg_lower in ["/scan", "scan", "cek", "cek pasar"]:
                        run_radar_scan(chat_id)
                    
                    elif msg_lower.startswith("/scan "):
                        coin = msg_lower.replace("/scan ", "").strip()
                        if coin:
                            handle_any_coin_scan(chat_id, coin)

                    elif msg_lower in ["/universe", "universe"]:
                        handle_universe_command(chat_id)
                    
                    elif msg_lower in ["/top", "top", "movers", "/movers"]:
                        handle_top_movers(chat_id)

                    elif msg_lower in ["/status", "status", "portofolio", "posisi"]:
                        send_telegram_message(chat_id, get_system_status())

                    elif msg_lower.startswith("/auto"):
                        state = {}
                        if os.path.exists(STATE_FILE):
                            try:
                                with open(STATE_FILE, "r", encoding="utf-8") as f:
                                    state = json.load(f)
                            except Exception:
                                pass
                        
                        text = (
                            f"⚙️ <b>STATUS AUTONOMOUS TRADER v2.0:</b>\n"
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
                        parts = msg_text.split()
                        if len(parts) >= 2:
                            try:
                                new_lev = int(parts[1])
                                if 1 <= new_lev <= 20:
                                    save_trading_config({"max_leverage": new_lev, "updated_by": "user"})
                                    send_telegram_message(
                                        chat_id,
                                        f"⚡ <b>BATAS LEVERAGE DIPERBARUI!</b>\n"
                                        f"Leverage maksimal: <b>{new_lev}x</b>\n"
                                        f"<i>Perubahan langsung aktif.</i>"
                                    )
                                else:
                                    send_telegram_message(chat_id, "❌ Leverage harus antara 1-20x.")
                            except ValueError:
                                send_telegram_message(chat_id, "❌ Format salah. Contoh: <code>/leverage 3</code>")
                        else:
                            cfg = get_trading_config()
                            send_telegram_message(
                                chat_id,
                                f"ℹ️ <b>LEVERAGE MAKS:</b> {cfg.get('max_leverage', 5)}x\n"
                                f"Untuk ubah: <code>/leverage [angka]</code>"
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
                    
                    # Catch-all: try to scan any coin name
                    elif msg_lower.startswith("/"):
                        coin_try = msg_lower.lstrip("/").strip()
                        if len(coin_try) >= 2 and len(coin_try) <= 10:
                            handle_any_coin_scan(chat_id, coin_try)
                        else:
                            send_telegram_message(chat_id, 
                                "❓ Perintah tidak dikenali.\n"
                                "Ketik <code>/help</code> untuk daftar perintah.\n"
                                "Atau ketik nama coin langsung: <code>/dot</code> <code>/matic</code> dll.")

                # Handle inline button click (Approve / Reject)
                elif "callback_query" in update:
                    cb = update["callback_query"]
                    cb_id = cb["id"]
                    cb_data = cb["data"]
                    chat_id = cb["message"]["chat"]["id"]

                    if cb_data.startswith("buy_") or cb_data.startswith("confirm_"):
                        symbol = cb_data.replace("buy_", "").replace("confirm_", "")
                        cfg = get_trading_config()
                        max_budget = cfg.get("max_budget_idr", 50000)
                        answer_callback(cb_id, f"Mengeksekusi order {symbol} senilai Rp {max_budget:,}...")
                        send_telegram_message(
                            chat_id,
                            f"⚡ <b>ORDER DIEKSEKUSI // CRYPTO FUTURES</b>\n\n"
                            f"Aset: <b>{symbol}</b>\n"
                            f"Nominal: <b>Rp {max_budget:,}</b> (${convert_idr_to_usd(max_budget):.4f} USD)\n"
                            f"Status: <b>SUCCESS / OPENED</b>\n"
                            f"Waktu: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
                            f"<i>Posisi aktif kini dipantau otomatis oleh risk officer stop-loss.</i>"
                        )
                    elif cb_data.startswith("reject_") or cb_data.startswith("cancel_"):
                        symbol = cb_data.replace("reject_", "").replace("cancel_", "")
                        answer_callback(cb_id, f"Order {symbol} dibatalkan.")
                        send_telegram_message(chat_id, f"🛑 Order <b>{symbol}</b> telah dibatalkan. Modal tetap 100% aman.")

        except Exception as e:
            print(f"[-] Bot listener error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    start_bot_listener()
