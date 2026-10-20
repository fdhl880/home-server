"""
===========================================================================
PYROFUEL TELEGRAM BOT v3.0 - FULL UNIVERSE CRYPTO FUTURES AI
===========================================================================
Token: 8829535429:AAHFHM56RDNAd7-ax6Dd-3V3g9OZEleYi5M (@idrisginting_bot)
Koleksi Aset: ALL Binance USDT Perpetual Futures (~200+ coins)
Fitur: 5-Layer AI Pipeline, Pluang MCP Execution, Live Token Validation

DAFTAR PERINTAH:
/start      - Welcome & daftar perintah
/login      - Hubungkan akun Pluang Anda via OAuth resmi
/scan       - Full scan CORE 10 + Top movers
/scan [coin]- Analisis koin spesifik (misal: /scan btc)
/konfirmasi [coin] - Eksekusi order riil ke Pluang Futures
/universe   - Status seluruh universe (200+ pairs)
/top        - Top 20 movers saat ini
/btc, /eth, /sol - Analisis instan koin utama
/status     - Status koneksi Pluang, portfolio & posisi aktif
/auto       - Status autonomous trading engine
/limit [n]  - Ubah batas modal per trade
/leverage [n] - Ubah batas leverage
/fx         - Kurs USD/IDR real-time
/convert [n] [usd/idr] - Konversi mata uang
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
    convert_usd_to_idr, convert_idr_to_usd, rank_universe_by_opportunity
)
from pluang_mcp import PluangMCPClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "tokens.json")
POSITIONS_FILE = os.path.join(RESULTS_DIR, "active_positions.json")
STATE_FILE = os.path.join(RESULTS_DIR, "autotrader_state.json")

ENV = load_env()
TELEGRAM_TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "").strip()
TELE_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def _max_budget():
    return get_trading_config().get("max_budget_idr", 50000)

def _max_leverage():
    return get_trading_config().get("max_leverage", 5)

def get_pluang_client():
    """Load client and verify access token live against Pluang MCP.
    Tries refresh_token automatically if access_token is expired."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            t = json.load(f)
        token = t.get("access_token")
        refresh = t.get("refresh_token")
        if not token:
            return None

        # Check if token is likely expired (>55 min old)
        acquired = t.get("acquired_at", 0)
        expires_in = t.get("expires_in", 3600)
        if time.time() - acquired > (expires_in - 300):
            # Token likely expired, try refresh first
            if refresh:
                print("[Pluang] Token likely expired, attempting refresh...", flush=True)
                client = PluangMCPClient(token)
                if client._refresh_token():
                    try:
                        client.initialize()
                        if not (client._last_error and "401" in str(client._last_error)):
                            print("[Pluang] ✅ Token refreshed and verified!", flush=True)
                            return client
                    except Exception:
                        pass
            return None

        # Token still within TTL, verify it
        client = PluangMCPClient(token)
        try:
            client.initialize()
            if client._last_error and "401" in str(client._last_error):
                # Unexpected 401, try refresh
                if refresh and client._refresh_token():
                    return client
                return None
            return client
        except Exception as e:
            if "401" in str(e) and refresh:
                if client._refresh_token():
                    return client
            return None
    except Exception as e:
        print(f"[-] Pluang client error: {e}", flush=True)
        return None

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
        return r.json()
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
    lev_val = plan.get('leverage') or fc.get('leverage', 1)
    modal_val = plan.get('position_size_idr') or fc.get('position_size_idr', max_budget)

    text = (
        f"🛡️ <b>PYROFUEL 5-LAYER FUTURES AUDIT</b>\n"
        f"<b>Aset:</b> <code>{symbol}</code> (${layer1.get('current_price', 0):,})\n"
        f"<b>Harga IDR:</b> Rp {convert_usd_to_idr(layer1.get('current_price', 0)):,.0f}\n"
        f"<b>RSI (14):</b> {layer1.get('rsi_14')} | <b>Tren EMA:</b> {layer1.get('ema_trend')}\n"
        f"<b>MACD:</b> {layer1.get('macd', {}).get('trend')} | <b>Vol:</b> {layer1.get('volume_profile', {}).get('volume_trend')}\n"
        f"📊 <b>Quant Factor Matrix:</b> <b>{c_score}/100</b> ({total_f}+ faktor | {regime})\n"
        f"────────────────────────\n"
        f"🎯 <b>1. Setup Hunter:</b> <code>{setup.get('setup_name', 'N/A')}</code> ({setup.get('direction', 'NONE')})\n"
        f"<i>\"{setup.get('explanation_id', '')}\"</i>\n\n"
        f"📐 <b>2. Trading Plan (AI Governed):</b> {plan.get('action', 'SKIP')}\n"
        f"• Order: {order_t}{limit_p_str} | Lev: {lev_val}x\n"
        f"• Entry: ${plan.get('entry_price', 0):,} | SL: ${sl_val:,}\n"
        f"• Take Profit: ${tp_val:,}\n"
        f"• Modal: Rp {modal_val:,} | RRR: {plan.get('risk_reward_ratio', 'N/A')}\n\n"
        f"🔍 <b>3. CRO Risk Audit:</b> {risk.get('risk_verdict', 'N/A')}\n"
        f"• Score: {risk.get('total_score', 0)}/{risk.get('max_score', 10)} ({risk.get('pass_rate_pct', 0)}%)\n\n"
        f"⚖️ <b>4. Supreme Judge Decision:</b> {badge}\n"
        f"• <b>Skor Keyakinan:</b> {fc.get('confidence_score', 0)}% (Min {min_conf}%)\n"
        f"• <b>Modal AI:</b> Rp {modal_val:,}\n\n"
        f"📌 <b>Pertimbangan Final:</b>\n{fc.get('final_reason', '-')[:450]}\n"
    )
    return text, status

def execute_trade_with_pluang(symbol: str, chat_id: int, callback_query_id: str = None):
    """Execute real trade on Pluang Futures via MCP"""
    raw_sym = symbol.upper().strip().replace("USDT", "-USD")
    if not raw_sym.endswith("-USD"):
        raw_sym = raw_sym + "-USD"
    
    cfg = get_trading_config()
    max_budget = cfg.get("max_budget_idr", 50000)
    max_lev = cfg.get("max_leverage", 5)
    margin_type = cfg.get("margin_type", "ISOLATED")
    order_type = cfg.get("order_type", "MARKET")
    budget_usd = convert_idr_to_usd(max_budget)

    # 0. Check duplicate active position
    positions = []
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                positions = json.load(f)
        except Exception:
            positions = []
    existing_open = [p for p in positions if p.get("symbol") == raw_sym and p.get("status") == "OPEN"]
    if existing_open:
        last_pos = existing_open[-1]
        msg = (
            f"ℹ️ <b>POSISI {raw_sym} SUDAH AKTIF DI PLUANG!</b>\n\n"
            f"🎯 <b>Arah:</b> {last_pos.get('direction', 'LONG')}\n"
            f"📍 <b>Entry:</b> ${last_pos.get('entry_price', 0):,.4f}\n"
            f"🆔 <b>Order ID:</b> <code>{last_pos.get('order_id', 'N/A')}</code>\n\n"
            f"<i>Posisi sedang aktif dipantau. Modal Anda aman dan order tidak diduplikasi.</i>"
        )
        if callback_query_id:
            answer_callback(callback_query_id, f"Posisi {raw_sym} sudah aktif!", show_alert=False)
        send_telegram_message(chat_id, msg)
        return True

    # 1. Check Pluang Client & Token
    client = get_pluang_client()
    if not client:
        msg = (
            "⚠️ <b>KONEKSI PLUANG EXPIRED / BELUM LOGIN</b>\n\n"
            f"Order <b>{raw_sym}</b> tidak dapat dikirim ke akun Pluang karena token OAuth kadaluarsa (401 invalid_token).\n\n"
            "👉 <b>Solusi Cepat:</b>\n"
            "1. Ketik <code>/login</code> di Telegram ini untuk membuka link otorisasi Pluang, ATAU\n"
            "2. Jalankan perintah ini di Termux:\n"
            "   <code>python pluang-bot/auth_pluang.py --force</code>\n\n"
            "<i>🛡️ Modal USDT Anda tetap 100% aman karena tidak ada order yang terpotong.</i>"
        )
        if callback_query_id:
            answer_callback(callback_query_id, "Gagal: Token Pluang expired! Silakan ketik /login", show_alert=True)
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
        send_telegram_message(chat_id, f"⏳ <i>Menghitung analisis teknikal kuantitatif untuk {raw_sym}...</i>")
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

    # AI governs modal/position size
    pos_idr = float(signal.get("position_size_idr") or max_budget)
    pos_usd = round(pos_idr / 16500.0, 2)

    # AI governs leverage
    leverage = int(signal.get("leverage") or 5)
    if max_lev > 0:
        leverage = min(leverage, max_lev)

    # Pluang only supports Single Take Profit (NO dual TP)
    tp = float(signal.get("take_profit") or signal.get("take_profit_2") or signal.get("take_profit_1", 0))
    sl = float(signal.get("stop_loss", 0))

    limit_info = f" (@ ${limit_price:,.4f})" if order_type == "LIMIT" else ""
    send_telegram_message(
        chat_id,
        f"⚡ <i>Mengirim order {order_type}{limit_info} {direction} {raw_sym} ({leverage}x) senilai Rp {pos_idr:,} (${pos_usd:.2f} USDT) ke Pluang Futures...</i>"
    )

    # 3. Call Pluang MCP execute_full_trade
    try:
        execution_result = client.execute_full_trade(
            signal={
                "binance_pair": raw_sym.replace("-USD", "USDT"),
                "symbol": raw_sym,
                "direction": direction,
                "leverage": leverage,
                "margin_type": margin_type,
                "order_type": order_type,
                "limit_price": limit_price,
                "entry_price": entry_price,
                "take_profit": tp,
                "take_profit_1": tp,
                "take_profit_2": tp,
                "stop_loss": sl,
                "position_size_idr": pos_idr,
                "position_size_usdt": pos_usd
            },
            config={
                "margin_type": margin_type,
                "order_type": order_type,
                "max_leverage": max_lev,
                "max_budget_idr": max_budget
            }
        )

        pluang_synced = execution_result.get("pluang_synced", False)

        if pluang_synced:
            # Record position in active_positions.json
            positions = []
            if os.path.exists(POSITIONS_FILE):
                try:
                    with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                        positions = json.load(f)
                except Exception:
                    positions = []

            open_res = execution_result.get("steps", {}).get("open_position", {})
            order_id = open_res.get("orderId") or open_res.get("id") or "LIVE_EXECUTED"

            new_pos = {
                "id": f"POS_{raw_sym}_{int(time.time())}",
                "symbol": raw_sym,
                "binance_pair": raw_sym.replace("-USD", "USDT"),
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
                "pluang_synced": True,
                "order_id": order_id,
                "pluang_execution": execution_result
            }
            positions.append(new_pos)
            with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(positions, f, indent=2, ensure_ascii=False)

            if callback_query_id:
                answer_callback(callback_query_id, f"Order {raw_sym} berhasil dibuka di Pluang!", show_alert=False)

            limit_txt = f" (@ ${limit_price:,.4f})" if order_type == "LIMIT" else ""
            msg = (
                f"⚡ <b>ORDER BERHASIL DIEKSEKUSI DI PLUANG!</b>\n\n"
                f"💎 <b>Aset:</b> <code>{raw_sym}</code>\n"
                f"🎯 <b>Arah:</b> <b>{direction}</b>\n"
                f"📋 <b>Order Type:</b> <b>{order_type}{limit_txt}</b>\n"
                f"📊 <b>Leverage:</b> <b>{leverage}x</b> ({margin_type})\n"
                f"💰 <b>Modal (AI):</b> <b>Rp {pos_idr:,}</b> (${pos_usd:.2f} USDT)\n"
                f"📍 <b>Entry:</b> ${entry_price:,.4f}\n"
                f"🎯 <b>Take Profit (Single TP):</b> ${tp:,.4f}\n"
                f"🛑 <b>Stop Loss:</b> ${sl:,.4f}\n"
                f"🆔 <b>Order ID Pluang:</b> <code>{order_id}</code>\n"
                f"⏰ <b>Waktu:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}\n\n"
                f"<i>Posisi aktif kini langsung terpantau di Pluang & Bloomberg Terminal.</i>"
            )
            send_telegram_message(chat_id, msg)
            return True
        else:
            err = execution_result.get("error") or "Order ditolak oleh Pluang API"
            if callback_query_id:
                answer_callback(callback_query_id, f"Pluang: {err[:60]}", show_alert=True)
            msg = (
                f"❌ <b>PLUANG MENOLAK ORDER {raw_sym}</b>\n\n"
                f"Detail Error dari Pluang:\n<code>{err}</code>\n\n"
                f"<i>Catatan: Tidak ada modal yang terpotong. Sinyal tidak didaftarkan sebagai posisi aktif.</i>"
            )
            send_telegram_message(chat_id, msg)
            return False

    except Exception as e:
        if callback_query_id:
            answer_callback(callback_query_id, f"Error: {str(e)[:60]}", show_alert=True)
        send_telegram_message(chat_id, f"❌ <b>Error Eksekusi Pluang:</b>\n<code>{e}</code>")
        return False

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            qs = parse_qs(parsed.query)
            if "code" in qs:
                code = qs["code"][0]
                target_chat_id = None
                pending_file = os.path.join(BASE_DIR, "pending_auth.json")
                if os.path.exists(pending_file):
                    try:
                        with open(pending_file, "r", encoding="utf-8") as pf:
                            target_chat_id = json.load(pf).get("chat_id")
                    except Exception:
                        pass
                if not target_chat_id:
                    last_cid_file = os.path.join(BASE_DIR, "last_chat_id.txt")
                    if os.path.exists(last_cid_file):
                        try:
                            with open(last_cid_file, "r") as cf:
                                target_chat_id = int(cf.read().strip())
                        except Exception:
                            pass

                success = exchange_oauth_code(code, target_chat_id)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                status_color = "#22c55e" if success else "#ef4444"
                status_title = "✅ Login Berhasil! Akun Pluang Terhubung" if success else "⚠️ Gagal Menukar Token"
                status_desc = "Akun Pluang Anda berhasil dihubungkan ke Bot Telegram. Status Pluang di Telegram kini 🟢 HIJAU (Aktif)." if success else "Kode otentikasi gagal ditukar. Silakan coba /login ulang dari Telegram."
                html = f"""
                <html>
                <body style="font-family:sans-serif; text-align:center; padding:50px; background:#0f172a; color:#f8fafc;">
                    <h1 style="color:{status_color};">{status_title}</h1>
                    <p style="font-size:18px;">{status_desc}</p>
                    <p style="color:#94a3b8;">Anda boleh menutup tab browser ini dan kembali ke Telegram.</p>
                </body>
                </html>
                """
                self.wfile.write(html.encode("utf-8"))
            elif "error" in qs:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h1>Error Login: {qs['error'][0]}</h1>".encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return

def start_callback_server():
    try:
        server = HTTPServer(("0.0.0.0", 8080), OAuthCallbackHandler)
        print("[*] Local OAuth Callback Server listening on port 8080...", flush=True)
        server.serve_forever()
    except Exception as e:
        print(f"[!] Info: Port 8080 callback notice ({e})", flush=True)

def handle_login_command(chat_id):
    """Generate official Pluang OAuth URL, save pending PKCE, and send interactive instructions"""
    try:
        from auth_pluang import get_or_create_client, generate_pkce, AUTH_ENDPOINT, REDIRECT_URI
        cid = get_or_create_client()
        cv, cc = generate_pkce()
        scopes = "market:read portfolio:read trade:write"
        auth_url = (
            f"{AUTH_ENDPOINT}?response_type=code"
            f"&client_id={cid}"
            f"&redirect_uri={REDIRECT_URI}"
            f"&scope={scopes.replace(' ', '%20')}"
            f"&code_challenge={cc}"
            f"&code_challenge_method=S256"
        )

        # Save pending_auth.json with code_verifier and chat_id for instant callback
        pending_file = os.path.join(BASE_DIR, "pending_auth.json")
        with open(pending_file, "w", encoding="utf-8") as pf:
            json.dump({
                "client_id": cid,
                "code_verifier": cv,
                "url": auth_url,
                "chat_id": chat_id,
                "timestamp": time.time()
            }, pf, indent=2)

        try:
            with open(os.path.join(BASE_DIR, "last_chat_id.txt"), "w") as cf:
                cf.write(str(chat_id))
        except Exception:
            pass

        reply_markup = {
            "inline_keyboard": [
                [{"text": "🔑 Buka Halaman Login Pluang", "url": auth_url}]
            ]
        }
        send_telegram_message(
            chat_id,
            "🔐 <b>LOGIN / SAMBUNGKAN AKUN PLUANG (INSTAN)</b>\n\n"
            "Untuk membuka posisi futures otomatis dengan USDT/IDR Anda, akun Pluang harus dihubungkan via OAuth resmi:\n\n"
            "👉 <b>Langkah Mudah:</b>\n"
            "1. Klik tombol <b>Buka Halaman Login Pluang</b> di bawah\n"
            "2. Masukkan nomor HP & PIN Pluang Anda di browser\n"
            "3. Setujui izin akses trading untuk bot\n"
            "4. <b>Di PC/Laptop:</b> Bot akan otomatis menangkap login Anda & langsung IJO!\n"
            "5. <b>Di HP / Browser Eksternal:</b> Jika dialihkan ke link localhost, cukup <b>COPY URL tersebut atau kodenya, lalu PASTE LANGSUNG ke chat bot ini!</b>\n\n"
            "<i>Bot akan otomatis menukar kode & status Pluang Anda langsung IJO (🟢 Terhubung & Verified)!</i>",
            reply_markup=reply_markup
        )
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Gagal membuat link login: {e}")

def exchange_oauth_code(code_str: str, chat_id: int = None):
    """Exchange OAuth code or redirect URL for tokens and activate immediately"""
    code_val = code_str.strip()
    if "code=" in code_val:
        from urllib.parse import urlparse, parse_qs
        try:
            parsed = parse_qs(urlparse(code_val).query)
            if "code" in parsed:
                code_val = parsed["code"][0]
        except Exception:
            for part in code_val.split("&"):
                if "code=" in part:
                    code_val = part.split("code=")[-1].split()[0]

    pending_file = os.path.join(BASE_DIR, "pending_auth.json")
    if not os.path.exists(pending_file):
        if chat_id:
            send_telegram_message(
                chat_id,
                "⚠️ <b>Tidak ada sesi login aktif.</b>\n"
                "Ketik <code>/login</code> terlebih dahulu untuk membuat link otentikasi baru."
            )
        return False

    try:
        with open(pending_file, "r", encoding="utf-8") as f:
            pending = json.load(f)

        if not chat_id and pending.get("chat_id"):
            chat_id = pending.get("chat_id")

        token_payload = {
            "grant_type": "authorization_code",
            "client_id": pending["client_id"],
            "code": code_val,
            "redirect_uri": "http://localhost:8080/callback",
            "code_verifier": pending["code_verifier"]
        }
        if chat_id:
            send_telegram_message(chat_id, "⏳ <i>Menghubungkan ke server Pluang untuk aktivasi token...</i>")
        resp = requests.post("https://mcp.pluang.com/token", data=token_payload, timeout=15)
        if resp.status_code == 200:
            token_data = resp.json()
            token_data["acquired_at"] = time.time()
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=2)

            client = get_pluang_client()
            bal_info = ""
            if client:
                try:
                    b_res = client.get_balance()
                    if isinstance(b_res, dict) and "content" in b_res and b_res["content"]:
                        txt = b_res["content"][0].get("text", "")
                        bal_info = f"\n\n💰 <b>Status Wallet Pluang:</b>\n<code>{txt[:250]}</code>"
                except Exception:
                    pass

                if chat_id:
                    send_telegram_message(
                        chat_id,
                        f"🟢 <b>LOGIN BERHASIL! STATUS KONEKSI PLUANG IJO!</b>\n\n"
                        f"✅ Akun Pluang Anda berhasil terhubung via OAuth resmi.\n"
                        f"✅ Akses token aktif & verified live terhadap Pluang MCP.\n"
                        f"✅ AI Trading Engine kini siap membuka posisi otomatis.{bal_info}\n\n"
                        f"Ketik <code>/status</code> untuk melihat portofolio Anda, atau <code>/scan</code> untuk mencari peluang trade."
                    )
                print("[+] OAuth token exchanged successfully & saved to tokens.json!", flush=True)
                return True
            else:
                if chat_id:
                    send_telegram_message(chat_id, "⚠️ Token diterima namun inisialisasi Pluang MCP gagal. Silakan coba <code>/login</code> ulang.")
                return False
        else:
            if chat_id:
                send_telegram_message(
                    chat_id,
                    f"❌ <b>Gagal Menukar Kode Pluang:</b>\n"
                    f"Status: {resp.status_code}\n"
                    f"Detail: <code>{resp.text[:300]}</code>\n\n"
                    f"<i>Kode otentikasi hanya berlaku satu kali. Ketik <code>/login</code> untuk membuat yang baru.</i>"
                )
            print(f"[-] Token exchange failed ({resp.status_code}): {resp.text}", flush=True)
            return False
    except Exception as e:
        if chat_id:
            send_telegram_message(chat_id, f"❌ Terjadi kesalahan saat aktivasi: {e}")
        print(f"[-] Activation exception: {e}", flush=True)
        return False

def run_radar_scan(chat_id):
    """Fast Parallel Quant Radar Scan (Top 3 Candidates in Parallel - <10s)"""
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
    
    client = get_pluang_client()
    pluang_badge = "🟢 <b>CONNECTED & VERIFIED</b>" if client else "🔴 <b>TOKEN EXPIRED (Ketik /login)</b>"

    ai_desc = "Google Gemini 3.8 Flash (Flagship AI)" if GEMINI_API_KEY else f"Groq ({GROQ_MODEL})"

    text = (
        f"📊 <b>STATUS SISTEM TRADING AI CRYPTO FUTURES</b>\n"
        f"────────────────────────\n"
        f"🏦 <b>Pluang Status:</b> {pluang_badge}\n"
        f"🤖 <b>AI Utama:</b> {ai_desc} (6+ AI Cascade)\n"
        f"📈 <b>Quant Matrix:</b> 500+ Factors (Simons, Wyckoff, Minervini, DeMark)\n"
        f"🌐 <b>Universe:</b> {len(universe)} crypto futures pairs\n"
        f"🔒 <b>Limit Modal:</b> Rp {cfg.get('max_budget_idr', 50000):,} per trade\n"
        f"   <i>(= ${convert_idr_to_usd(cfg.get('max_budget_idr', 50000)):.2f} USD)</i>\n"
        f"⚡ <b>Leverage Max:</b> {cfg.get('max_leverage', 5)}x ({cfg.get('margin_type', 'ISOLATED')})\n"
        f"💱 <b>Kurs USD/IDR:</b> Rp {fx['usd_idr']:,.0f}\n"
        f"💼 <b>Posisi Aktif:</b> {len(open_pos)} posisi\n"
        f"────────────────────────\n"
    )
    if open_pos:
        text += "<b>Daftar Posisi Aktif:</b>\n"
        for p in open_pos[:10]:
            synced_mark = "✅ Pluang Live" if p.get("pluang_synced") else "📝 Lokal"
            text += (f"• <code>{p['symbol']}</code> {p['direction']} @ ${p.get('entry_price', 0):,.4f} "
                     f"(Lev: {p.get('leverage', 1)}x, {synced_mark})\n")
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
    coin_name = coin_name.upper().strip()
    symbol = None
    for item in CRYPTO_FUTURES_WATCHLIST:
        if coin_name in [item["name"].upper(), item["symbol"].upper(), 
                          item["pair"].upper(), item["symbol"].replace("-USD", "").upper()]:
            symbol = item["symbol"]
            break
    if not symbol:
        test_pair = coin_name if coin_name.endswith("USDT") else coin_name + "USDT"
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
                {"text": f"✅ Konfirmasi & Eksekusi ({symbol})", "callback_data": f"confirm_{symbol}"},
                {"text": "❌ Batalkan", "callback_data": f"cancel_{symbol}"}
            ]]}
        send_telegram_message(chat_id, text, markup)
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Error analisis {symbol}: {e}")

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
                    try:
                        with open(os.path.join(BASE_DIR, "last_chat_id.txt"), "w") as cf:
                            cf.write(str(chat_id))
                    except Exception:
                        pass
                    msg_text = update["message"]["text"].strip()
                    msg_lower = msg_text.lower()

                    # Intercept OAuth code / redirect URL pasted by user
                    # Catches: http://localhost:8080/callback?code=XXX, raw code strings, /code XXX
                    is_oauth = False
                    if "code=" in msg_text:
                        is_oauth = True
                    elif msg_lower.startswith("/code"):
                        is_oauth = True
                    elif "callback" in msg_lower and "localhost" in msg_lower:
                        is_oauth = True
                    elif len(msg_text) > 35 and " " not in msg_text and not msg_text.startswith("/"):
                        # Likely a raw OAuth code pasted directly
                        is_oauth = True

                    if is_oauth:
                        code_cand = msg_text
                        if msg_lower.startswith("/code"):
                            parts = msg_text.split()
                            code_cand = parts[1] if len(parts) >= 2 else ""
                        if code_cand:
                            exchange_oauth_code(code_cand, chat_id)
                            continue

                    if msg_lower in ["/start", "start", "halo", "help", "/help"]:
                        cfg = get_trading_config()
                        universe = get_full_universe()
                        client = get_pluang_client()
                        pluang_txt = "🟢 Terhubung" if client else "🔴 Perlu /login"
                        welcome = (
                            "👋 <b>Halo! Saya Pyrofuel AI Crypto Futures Trading v3.0</b>\n\n"
                            f"🏦 <b>Pluang Status:</b> {pluang_txt}\n"
                            f"🌐 <b>Universe:</b> {len(universe)} crypto futures pairs\n"
                            f"🔒 <b>Limit Modal:</b> Rp {cfg.get('max_budget_idr', 50000):,}\n"
                            f"⚡ <b>Max Leverage:</b> {cfg.get('max_leverage', 5)}x\n\n"
                            "Sistem dirancang dengan <b>5-Layer AI Pipeline</b>:\n"
                            "• Scanner ➔ Setup Hunter ➔ Plan ➔ Risk Audit ➔ Supreme Judge\n\n"
                            "<b>📋 Perintah:</b>\n"
                            "• <code>/login</code> - Hubungkan akun Pluang Anda via OAuth\n"
                            "• <code>/konfirmasi [coin]</code> - Eksekusi riil ke Pluang Futures\n"
                            "• <code>/scan</code> - Scan 30 coins (core + top movers)\n"
                            "• <code>/scan [coin]</code> - Analisis spesifik (misal: /scan btc)\n"
                            "• <code>/universe</code> - Status full universe 200+ pairs\n"
                            "• <code>/top</code> - Top 20 movers saat ini\n"
                            "• <code>/btc</code> <code>/eth</code> <code>/sol</code> - Analisis cepat\n"
                            "• <code>/status</code> - Portfolio & posisi aktif (AI Sentinel)\n"
                            "• <code>/pnl</code> - Win Rate % & Total P&L Real-time\n"
                            "• <code>/news</code> - AI Crypto News & Macro Sentiment\n"
                            "• <code>/auto</code> - Status auto-trading\n"
                            "• <code>/limit [n]</code> - Ubah batas modal\n"
                            "• <code>/leverage [n]</code> - Ubah batas leverage\n"
                            "• <code>/fx</code> - Kurs USD/IDR real-time\n"
                            "• <code>/convert [n] [usd/idr]</code> - Konversi mata uang"
                        )
                        send_telegram_message(chat_id, welcome)

                    elif msg_lower in ["/login", "login", "/auth", "auth"]:
                        handle_login_command(chat_id)

                    elif msg_lower.startswith("/konfirmasi") or msg_lower.startswith("/confirm") or msg_lower.startswith("/approve") or msg_lower.startswith("/beli"):
                        parts = msg_text.split()
                        if len(parts) >= 2:
                            coin = parts[1].upper().strip().replace("-USD", "").replace("USDT", "")
                            threading.Thread(target=execute_trade_with_pluang, args=(coin, chat_id), daemon=True).start()
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
                                threading.Thread(target=execute_trade_with_pluang, args=(latest_approved, chat_id), daemon=True).start()
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

                    if cb_data.startswith("buy_") or cb_data.startswith("confirm_"):
                        symbol = cb_data.replace("buy_", "").replace("confirm_", "")
                        answer_callback(cb_id, f"⚡ Mengeksekusi order {symbol}...")
                        # Run in thread for instant response - don't block polling
                        t = threading.Thread(
                            target=execute_trade_with_pluang,
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
