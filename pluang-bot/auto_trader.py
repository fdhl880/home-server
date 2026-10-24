"""
===========================================================================
PYROFUEL AUTONOMOUS CRYPTO FUTURES TRADER v3.0
===========================================================================
FULL UNIVERSE SCANNER + PLUANG EXECUTION ENGINE

Autonomous background agent that:
1. Fetches FULL Binance Futures universe dynamically
2. Smart-ranks all coins by opportunity score (vol, momentum, range)
3. Scans TOP 50 movers through 5-Layer AI Pipeline every cycle
4. CORE 10 coins ALWAYS scanned regardless of rank
5. If APPROVED trade found → EXECUTES ON PLUANG + Records + Telegram alert
6. Full futures control: Leverage, Margin Type, Order Type, TP/SL
7. Updates shared JSON database for Bloomberg Dashboard
8. Currency conversion: All USD amounts also shown in IDR

PLUANG EXECUTION:
- Auto set margin type (ISOLATED/CROSS) per config
- Auto set leverage per config
- Open position via MARKET/LIMIT order
- Auto place TP1 (50% partial close) + TP2 (full close) + SL orders
- TP1 hit → SL moves to breakeven (risk-free)
- All execution logged to results/execution_log.json

CYCLE STRATEGY:
- Every 60 seconds: Quick screen ALL coins (just technicals, no AI)
- Every 5 minutes: Full 5-layer AI pipeline on TOP 50 + CORE 10
- Prioritizes coins with highest opportunity score (volatility + volume)
==========================================================================
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timezone
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

from pipeline import run_5_layer_pipeline, load_env, RESULTS_DIR, get_trading_config, save_trading_config
from multi_agent_committee import run_multi_agent_committee, get_active_thesis
from market_data import (
    CRYPTO_FUTURES_WATCHLIST,
    get_full_universe,
    get_top_movers,
    get_universe_summary,
    get_market_indicators_fast,
    get_fx_info,
    convert_usd_to_idr,
    convert_idr_to_usd,
    rank_universe_by_opportunity,
    get_binance_24h_tickers,
)
from pluang_mcp import PluangMCPClient
from binance_futures import BinanceFuturesClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(RESULTS_DIR, "autotrader_state.json")
POSITIONS_FILE = os.path.join(RESULTS_DIR, "active_positions.json")
QUICK_SCREEN_FILE = os.path.join(RESULTS_DIR, "quick_screen.json")
UNIVERSE_FILE = os.path.join(RESULTS_DIR, "universe_state.json")
EXECUTION_LOG_FILE = os.path.join(RESULTS_DIR, "execution_log.json")
TOKEN_FILE = os.path.join(BASE_DIR, "tokens.json")

ENV = load_env()
TELEGRAM_TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "").strip()
TELE_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# === BINANCE FUTURES CLIENT ===
binance_client = None

def get_binance_client():
    """Initialize Binance Futures client if API keys are configured"""
    global binance_client
    if binance_client is not None:
        return binance_client
    current_env = load_env()
    ak = current_env.get("BINANCE_API_KEY", "").strip()
    sk = current_env.get("BINANCE_API_SECRET", "").strip()
    if ak and sk:
        binance_client = BinanceFuturesClient(api_key=ak, api_secret=sk)
        print(f"[BINANCE] ✅ Binance Futures Engine initialized ({ak[:8]}...)", flush=True)
        return binance_client
    return None

# === PLUANG MCP CLIENT ===
def get_pluang_client():
    """Initialize Pluang MCP client with auto-refresh if token expired"""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                data = json.load(f)
            token = data.get("access_token")
            refresh = data.get("refresh_token")
            if not token:
                return None

            # Check if token is likely expired (>55 min old)
            acquired = data.get("acquired_at", 0)
            expires_in = data.get("expires_in", 3600)
            if time.time() - acquired > (expires_in - 300):
                if refresh:
                    print(f"[PLUANG] Token likely expired, attempting refresh...", flush=True)
                    client = PluangMCPClient(token)
                    if client._refresh_token():
                        try:
                            client.initialize()
                            if not (client._last_error and "401" in str(client._last_error)):
                                print(f"[PLUANG] ✅ Token refreshed and verified!", flush=True)
                                return client
                        except Exception:
                            pass
                print(f"[PLUANG] ⚠️ Token expired and refresh failed. Need re-login.", flush=True)
                return None

            client = PluangMCPClient(token)
            client.initialize()
            if client._last_error and "401" in str(client._last_error):
                if refresh and client._refresh_token():
                    print(f"[PLUANG] ✅ Token refreshed on 401", flush=True)
                    return client
                return None
            print(f"[PLUANG] ✅ MCP Client connected", flush=True)
            return client
        except Exception as e:
            print(f"[PLUANG] ⚠️ MCP connection failed: {e}", flush=True)
    return None

pluang_client = None  # Lazy initialized

# === CONFIG (read from file, user can change via Telegram /limit) ===
def _get_config():
    return get_trading_config()

# Default state
state = {
    "is_running": True,
    "scan_interval_sec": 300,       # 5 min full AI pipeline cycle
    "quick_screen_interval_sec": 60, # 60 sec quick technical screen
    "last_scan_time": None,
    "last_quick_screen_time": None,
    "total_scans_done": 0,
    "total_quick_screens": 0,
    "signals_approved_count": 0,
    "signals_rejected_count": 0,
    "active_positions_count": 0,
    "universe_size": 0,
    "coins_scanned_this_cycle": 0,
    "recent_signals": [],
    "quick_alerts": [],
    "mode": "FULL_UNIVERSE"  # FULL_UNIVERSE or CORE_ONLY
}

def load_state():
    global state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                state.update(saved)
        except Exception:
            pass
    return state

def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def send_telegram(text, reply_markup=None):
    if not TELEGRAM_TOKEN:
        return
    chat_ids = set()
    cid_file = os.path.join(BASE_DIR, "last_chat_id.txt")
    if os.path.exists(cid_file):
        try:
            with open(cid_file, "r", encoding="utf-8") as f:
                cid = f.read().strip()
                if cid:
                    chat_ids.add(int(cid))
        except Exception:
            pass
    env_cid = ENV.get("TELEGRAM_CHAT_ID", "").strip()
    if env_cid:
        try:
            chat_ids.add(int(env_cid))
        except Exception:
            pass

    if not chat_ids:
        # Fallback to getUpdates only if no chat_id has ever been recorded
        try:
            r = requests.get(f"{TELE_API}/getUpdates?limit=5", timeout=10)
            if r.status_code == 200:
                updates = r.json().get("result", [])
                for u in updates:
                    msg = u.get("message") or u.get("callback_query", {}).get("message")
                    if msg and "chat" in msg:
                        chat_ids.add(msg["chat"]["id"])
        except Exception:
            pass

    for cid in chat_ids:
        payload = {
            "chat_id": cid,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            requests.post(f"{TELE_API}/sendMessage", json=payload, timeout=10)
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")

def record_position(signal: dict):
    """Record position locally AND execute on Pluang if connected"""
    global pluang_client
    cfg = _get_config()
    max_budget = cfg.get("max_budget_idr", 0)   # 0 = no cap, dynamic wallet-based
    max_lev = 20
    margin_type = signal.get("margin_type") or cfg.get("margin_type", "ISOLATED")
    
    # 1. AI GOVERNS ORDER TYPE & LIMIT PRICE
    order_type = (signal.get("order_type") or cfg.get("order_type", "MARKET")).upper()
    limit_price = float(signal.get("limit_price") or signal.get("entry_price", 0))

    # 2. AI GOVERNS MODAL (POSITION SIZE) — dynamic wallet-based Kelly sizing
    pos_size = float(signal.get("position_size_idr") or 0)
    # If pos_size is 0 or too small: dynamically size from live Binance wallet
    if pos_size < 5000:
        try:
            _bn = get_binance_client()
            if _bn:
                _bal = _bn.get_balance()
                avail_usdt = float(_bal.get("available_balance", 0))
                _fx = get_fx_info()
                avail_idr = avail_usdt * _fx["usd_idr"]
                # Kelly fraction ~30-60% of available balance depending on confidence
                conf = float(signal.get("confidence_score", 65))
                kelly_frac = max(0.15, min(0.60, conf / 100.0 * 0.8))
                pos_size = max(10000, int(avail_idr * kelly_frac))
            else:
                pos_size = 50000   # offline fallback
        except Exception:
            pos_size = 50000
    # If config max_budget_idr > 0, cap to it; 0 means no cap
    if max_budget > 0:
        pos_size = min(pos_size, max_budget)

    # FIXED LEVERAGE: Always 20x (user mandate)
    leverage = 20
    max_lev = cfg.get("max_leverage", 20)
    leverage = min(leverage, max_lev)  # already 20, but enforce config cap

    # 4. PLUANG ONLY SUPPORTS SINGLE TAKE PROFIT (NO DUAL TP)
    tp = float(signal.get("take_profit") or signal.get("take_profit_2") or signal.get("take_profit_1", 0))
    sl = float(signal.get("stop_loss", 0))

    fx = get_fx_info()
    pos_size_usd = round(pos_size / fx["usd_idr"], 4)

    auto_execute = cfg.get("auto_execute_on_pluang", True)
    max_concurrent = cfg.get("max_concurrent_positions", 5)
    
    # Check concurrent position limit
    positions = []
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                positions = json.load(f)
        except Exception:
            positions = []
    
    open_count = len([p for p in positions if p.get("status") == "OPEN"])
    if open_count >= max_concurrent:
        print(f"[POSITION] ⚠️ Max concurrent positions ({max_concurrent}) reached. Skipping.", flush=True)
        return None
    
    pos = {
        "id": f"POS_{signal.get('symbol', 'UNK')}_{int(time.time())}",
        "symbol": signal.get("symbol", ""),
        "binance_pair": signal.get("binance_pair", ""),
        "direction": signal.get("direction", "LONG"),
        "entry_price": signal.get("entry_price", 0),
        "entry_price_idr": convert_usd_to_idr(signal.get("entry_price", 0)),
        "take_profit": tp,
        "take_profit_1": tp,  # alias for backward compat
        "take_profit_2": tp,  # alias for backward compat
        "stop_loss": sl,
        "leverage": leverage,
        "margin_type": margin_type,
        "order_type": order_type,
        "limit_price": limit_price,
        "position_size_idr": pos_size,
        "position_size_usd": pos_size_usd,
        "position_size_usdt": pos_size_usd,  # USDT ≈ USD for execution
        "risk_reward_ratio": signal.get("risk_reward_ratio", "1:2.0"),
        "confidence_score": signal.get("confidence_score", 0),
        "setup_name": signal.get("setup_name", "N/A"),
        "estimated_time_horizon": signal.get("estimated_time_horizon", "N/A"),
        "opened_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "status": "OPEN",
        "pnl_idr": 0,
        "pnl_usd": 0,
        "pnl_pct": 0.0,
        "pluang_synced": False,
        "pluang_execution": None
    }
    
    # === EXECUTE REAL TRADE (BINANCE FUTURES PRIMARY) ===
    if auto_execute:
        bn_client = get_binance_client()
        if bn_client:
            try:
                execution_result = bn_client.execute_full_trade(signal={
                    "binance_pair": pos["binance_pair"],
                    "symbol": pos["symbol"],
                    "direction": pos["direction"],
                    "leverage": pos["leverage"],
                    "margin_type": pos["margin_type"],
                    "order_type": pos["order_type"],
                    "limit_price": pos["limit_price"],
                    "entry_price": pos["entry_price"],
                    "take_profit": pos["take_profit"],
                    "stop_loss": pos["stop_loss"],
                    "position_size_usdt": pos["position_size_usdt"]
                }, config=cfg)
                
                pos["binance_synced"] = execution_result.get("binance_synced", False)
                pos["binance_execution"] = execution_result
                pos["exchange"] = "BINANCE_FUTURES"
                pos["order_id"] = execution_result.get("order_id")
                
                if pos["binance_synced"]:
                    limit_str = f" @ ${limit_price:,.4f}" if order_type == "LIMIT" else ""
                    print(f"[BINANCE] ✅ Real trade executed on Binance Futures: {pos['direction']} {pos['binance_pair']} "
                          f"${pos_size_usd} {leverage}x {margin_type} {order_type}{limit_str} TP: ${tp} SL: ${sl} (Order #{pos['order_id']})", flush=True)
                else:
                    print(f"[BINANCE] ⚠️ Binance execution rejected: {execution_result.get('error')}", flush=True)
                    return None
            except Exception as e:
                print(f"[BINANCE] ❌ Execution exception: {e}", flush=True)
                return None
        else:
            # Fallback to Pluang
            if pluang_client is None:
                pluang_client = get_pluang_client()
            
            if pluang_client:
                try:
                    execution_result = pluang_client.execute_full_trade(signal={
                        "binance_pair": pos["binance_pair"],
                        "symbol": pos["symbol"],
                        "direction": pos["direction"],
                        "leverage": pos["leverage"],
                        "margin_type": pos["margin_type"],
                        "order_type": pos["order_type"],
                        "limit_price": pos["limit_price"],
                        "entry_price": pos["entry_price"],
                        "take_profit": pos["take_profit"],
                        "take_profit_1": pos["take_profit"],
                        "take_profit_2": pos["take_profit"],
                        "stop_loss": pos["stop_loss"],
                        "position_size_idr": pos["position_size_idr"],
                        "position_size_usdt": pos["position_size_usdt"]
                    }, config=cfg)
                    
                    pos["pluang_synced"] = execution_result.get("pluang_synced", False)
                    pos["pluang_execution"] = execution_result
                    pos["exchange"] = "PLUANG"
                except Exception as e:
                    print(f"[PLUANG] ❌ Execution error: {e}", flush=True)
                    pos["pluang_synced"] = False
            else:
                print(f"[EXECUTION] ⚠️ No active exchange client configured", flush=True)
                return None

    if not pos.get("binance_synced") and not pos.get("pluang_synced"):
        print(f"[EXECUTION] ⚠️ Order not executed on exchange - skipping recording to prevent fake reports", flush=True)
        return None

    positions.append(pos)
    try:
        with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(positions, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return pos


def monitor_and_update_positions():
    """
    Real-time autonomous position monitor:
    - Runs every 10 seconds in background
    - Evaluates live prices of open positions
    - Calculates floating PnL in USD and IDR
    - Auto-executes TP2 (close with profit)
    - Auto-executes TP1 (move SL to breakeven, risk-free trade)
    - Auto-executes SL (protect capital)
    - Sends Telegram notification on any event
    """
    if not os.path.exists(POSITIONS_FILE):
        return []

    try:
        with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
            positions = json.load(f)
    except Exception:
        return []

    open_pos = [p for p in positions if p.get("status") == "OPEN"]
    if not open_pos:
        return []

    tickers = get_binance_24h_tickers()
    ticker_map = {t["symbol"]: float(t.get("lastPrice", 0)) for t in tickers if "symbol" in t} if tickers else {}
    fx_rate = get_fx_info()["usd_idr"]

    # 1. Live synchronization with Binance Futures active positions
    bn_client = get_binance_client()
    bn_live_map = None
    if bn_client:
        try:
            live_list = bn_client.get_positions()
            if isinstance(live_list, list):
                bn_live_map = {p["symbol"]: p for p in live_list}
        except Exception as e:
            print(f"[MONITOR] Binance sync warning: {e}", flush=True)

    updated = False
    for pos in open_pos:
        pair = pos.get("binance_pair") or pos.get("symbol", "").replace("-USD", "USDT")
        direction = pos.get("direction", "LONG").upper()
        entry_price = float(pos.get("entry_price", 0))
        leverage = float(pos.get("leverage", 1))
        pos_idr = float(pos.get("position_size_idr", 50000))
        pos_usd = float(pos.get("position_size_usd", pos_idr / fx_rate))
        tp = float(pos.get("take_profit") or pos.get("take_profit_2") or pos.get("take_profit_1", 0))
        sl = float(pos.get("stop_loss", 0))

        # Check if position was executed on Binance Futures
        is_binance_pos = pos.get("exchange") == "BINANCE_FUTURES" or pos.get("binance_synced")

        # If it was open on Binance, check if Binance still has it
        if is_binance_pos and bn_live_map is not None:
            if pair not in bn_live_map:
                # The position was closed on Binance (via native TP/SL or manual close)
                curr_px = ticker_map.get(pair, entry_price)
                if direction == "LONG":
                    final_pnl_pct = ((curr_px - entry_price) / entry_price) * leverage * 100.0 if entry_price > 0 else 0
                else:
                    final_pnl_pct = ((entry_price - curr_px) / entry_price) * leverage * 100.0 if entry_price > 0 else 0
                
                final_pnl_idr = (final_pnl_pct / 100.0) * pos_idr
                final_pnl_usd = (final_pnl_pct / 100.0) * pos_usd
                
                pos["status"] = "CLOSED_TP" if final_pnl_pct >= 0 else "CLOSED_SL"
                pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                pos["close_price"] = curr_px
                pos["pnl_pct"] = round(final_pnl_pct, 2)
                pos["pnl_idr"] = round(final_pnl_idr, 2)
                pos["pnl_usd"] = round(final_pnl_usd, 4)
                
                event_type = "TAKE PROFIT" if final_pnl_pct >= 0 else "STOP LOSS"
                send_telegram(
                    f"⚡ <b>[BINANCE LIVE] POSISI {pos.get('symbol')} TELAH DITUTUP!</b>\n\n"
                    f"🎯 <b>Status:</b> <b>{event_type} TEREKSEKUSI DI EXCHANGE</b>\n"
                    f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction} {leverage}x)\n"
                    f"💰 <b>Hasil PnL:</b> {final_pnl_pct:+.2f}% ({final_pnl_idr:+,.0f} IDR / ${final_pnl_usd:+.2f} USDT)\n"
                    f"📍 <b>Entry:</b> ${entry_price:,.4f} ➔ <b>Exit:</b> ${curr_px:,.4f}\n\n"
                    f"<i>Margin posisi kini telah kembali utuh ke saldo wallet.</i>"
                )
                updated = True
                continue
            else:
                # Still open on Binance — sync official mark price and unrealized PnL
                live_item = bn_live_map[pair]
                current_price = float(live_item.get("mark_price", 0)) or ticker_map.get(pair, entry_price)
                live_upnl = float(live_item.get("unrealized_pnl", 0))
                pnl_usd = live_upnl
                pnl_idr = live_upnl * fx_rate
                pnl_pct = (live_upnl / pos_usd * 100.0) if pos_usd > 0 else 0.0
        else:
            current_price = ticker_map.get(pair, entry_price)
            if entry_price > 0:
                if direction == "LONG":
                    pnl_pct = ((current_price - entry_price) / entry_price) * leverage * 100.0
                else:
                    pnl_pct = ((entry_price - current_price) / entry_price) * leverage * 100.0
                pnl_idr = (pnl_pct / 100.0) * pos_idr
                pnl_usd = (pnl_pct / 100.0) * pos_usd
            else:
                pnl_pct = pnl_idr = pnl_usd = 0.0

        if not current_price or current_price <= 0:
            continue

        pos["current_price"] = current_price
        pos["current_price_idr"] = round(current_price * fx_rate, 2)
        pos["pnl_pct"] = round(pnl_pct, 2)
        pos["pnl_idr"] = round(pnl_idr, 2)
        pos["pnl_usd"] = round(pnl_usd, 4)
        pos["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # AI Position Sentinel & Live Evaluation
        try:
            from news_sentinel import get_news_sentiment_summary
            news_sum = get_news_sentiment_summary()
            pos["news_sentiment"] = news_sum.get("market_sentiment", "NEUTRAL")
            pos["ai_sentinel_status"] = "ACTIVE_AI_MONITORED"
            pos["last_ai_check"] = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

            # Periodic AI commentary on open position (every ~5 mins)
            now_ts = time.time()
            if now_ts - pos.get("last_ai_eval_ts", 0) >= 300:
                pos["last_ai_eval_ts"] = now_ts
                try:
                    ai_review = call_ai(
                        prompt=(
                            f"Posisi futures {pair} ({direction} 20x) sedang aktif. "
                            f"Entry: ${entry_price:,.4f}, Harga Sekarang: ${current_price:,.4f}, "
                            f"Floating PnL: {pnl_pct:+.2f}%. Target TP: ${tp:,.4f}, SL: ${sl:,.4f}. "
                            f"Beri evaluasi taktis singkat 1-2 kalimat (HOLD / AMBIL SEBAGIAN / TRAILING SL) dalam Bahasa Indonesia."
                        ),
                        system_prompt="You are a 24/7 AI Risk Sentinel monitoring live crypto positions.",
                        max_tokens=100,
                        is_json=False
                    )
                    pos["ai_evaluation"] = ai_review
                    print(f"[AI MONITOR] {pair} ({direction} 20x): PnL {pnl_pct:+.2f}% -> {ai_review}", flush=True)
                except Exception:
                    pos["ai_evaluation"] = f"AI Sentinel aktif memantau: PnL {pnl_pct:+.2f}%, menjaga Stop Loss."

            b_alert = news_sum.get("breaking_alert")
            sym_raw = pos.get("symbol", "").split("-")[0].lower()
            if b_alert and sym_raw in b_alert.lower() and not pos.get("sentinel_alerted"):
                pos["sentinel_alerted"] = True
                send_telegram(
                    f"⚠️ <b>[AI SENTINEL] PERINGATAN BERITA KRITIS!</b>\n\n"
                    f"💎 <b>Aset Terbuka:</b> <code>{pos.get('symbol')}</code> ({direction})\n"
                    f"🚨 <b>Breaking News:</b> <i>{b_alert}</i>\n"
                    f"📊 <b>Floating PnL Saat Ini:</b> {pnl_pct:.2f}% (Rp {pnl_idr:,.0f})\n"
                    f"🛡️ <i>AI Sentinel memonitor ketat batas Stop Loss (${sl:,.4f}) untuk proteksi modal.</i>"
                )
        except Exception:
            pass

        updated = True

        # Check Take Profit
        tp_hit = (direction == "LONG" and current_price >= tp > 0) or (direction == "SHORT" and current_price <= tp > 0)
        if tp_hit:
            pos["status"] = "CLOSED_TP"
            pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            pos["close_price"] = current_price
            if is_binance_pos and bn_client:
                try:
                    bn_client.close_position(pair, direction)
                    bn_client.cancel_all_orders(pair)
                except Exception as e:
                    print(f"[BINANCE CLOSE TP ERROR] {e}")
            send_telegram(
                f"🎉 <b>PYROFUEL // TAKE PROFIT TERCAPAI!</b>\n\n"
                f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction})\n"
                f"💰 <b>Profit:</b> +{pnl_pct:.2f}% (+Rp {pnl_idr:,.0f} / +${pnl_usd:.2f})\n"
                f"📍 <b>Entry:</b> ${entry_price:,.4f} ➔ <b>Exit:</b> ${current_price:,.4f}\n"
                f"🎯 <b>Target TP:</b> ${tp:,.4f}\n"
                f"⚡ Posisi Take Profit berhasil ditutup penuh di Binance Futures!"
            )
            continue

        # Check Stop Loss
        sl_hit = (direction == "LONG" and current_price <= sl > 0) or (direction == "SHORT" and current_price >= sl > 0)
        if sl_hit:
            pos["status"] = "CLOSED_SL"
            pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            pos["close_price"] = current_price
            if is_binance_pos and bn_client:
                try:
                    bn_client.close_position(pair, direction)
                    bn_client.cancel_all_orders(pair)
                except Exception as e:
                    print(f"[BINANCE CLOSE SL ERROR] {e}")
            send_telegram(
                f"🛑 <b>PYROFUEL // STOP LOSS DITRIGGER</b>\n\n"
                f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction})\n"
                f"📍 <b>Entry:</b> ${entry_price:,.4f} ➔ <b>Exit:</b> ${current_price:,.4f}\n"
                f"🛑 <b>Level SL:</b> ${sl:,.4f}\n"
                f"📉 <b>PnL:</b> {pnl_pct:.2f}% (Rp {pnl_idr:,.0f} / ${pnl_usd:.2f})\n"
                f"🛡️ Posisi otomatis di-cut untuk melindungi modal utama."
            )
            continue

    if updated:
        try:
            with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(positions, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return positions


def check_wallet_and_position_guard():
    """
    Evaluates whether the trading system should pause all universe scanning and 9-agent analysis
    to dedicate 100% of compute and surveillance to active open position(s).
    """
    positions = []
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                positions = json.load(f)
        except Exception:
            positions = []

    open_pos = [p for p in positions if p.get("status") == "OPEN"]
    
    bn_client = get_binance_client()
    avail_usdt = 100.0
    total_usdt = 100.0
    
    if bn_client:
        try:
            bal = bn_client.get_balance()
            if isinstance(bal, dict):
                avail_usdt = float(bal.get("available_balance", 0))
                total_usdt = float(bal.get("total_wallet_balance", 0))
        except Exception as e:
            print(f"[GUARD] Balance check notice: {e}", flush=True)

    should_pause = False
    reason = ""

    # Criteria for pausing scan & going ALL-IN on monitoring:
    # 1. At least 1 active open position exists
    # 2. Available balance is exhausted or depleted (available < 2.5 USDT or <= 35% of total balance, meaning capital is deployed)
    # OR max concurrent positions reached
    if len(open_pos) > 0:
        if avail_usdt < 2.5 or (total_usdt > 0 and (avail_usdt / total_usdt) < 0.35):
            should_pause = True
            sym_list = ", ".join([p.get("symbol", "") for p in open_pos])
            reason = (
                f"Saldo wallet terpakai penuh untuk {len(open_pos)} posisi aktif ({sym_list}). "
                f"Sisa saldo tersedia: ${avail_usdt:.2f} USDT (Total: ${total_usdt:.2f} USDT). "
                f"Scanner & 9-Agent beristirahat, memusatkan 100% monitor pada posisi terbuka."
            )
        elif len(open_pos) >= _get_config().get("max_concurrent_positions", 5):
            should_pause = True
            reason = f"Maksimal posisi aktif tercapai ({len(open_pos)} posisi). Fokus monitoring posisi aktif."

    return {
        "pause_scanning": should_pause,
        "mode": "ALL_IN_MONITOR" if should_pause else "UNIVERSE_SCANNER",
        "reason": reason,
        "open_positions": open_pos,
        "available_usdt": avail_usdt,
        "total_usdt": total_usdt
    }


# ===================================================================
# QUICK SCREEN: Technical-only fast scan for alerts
# ===================================================================
def run_quick_screen():
    """
    Fast technical screen of ALL coins — NO AI call.
    Detects: extreme RSI, Bollinger squeeze, huge volume spike.
    Runs every 60 seconds.
    """
    load_state()
    print(f"\n{'='*60}", flush=True)
    print(f"[QUICK SCREEN] {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')} - Screening full universe...", flush=True)
    
    ranked = rank_universe_by_opportunity()
    state["universe_size"] = len(ranked)
    
    alerts = []
    
    # Quick screen top movers using pre-fetched data from rank function
    for coin in ranked[:80]:  # Screen top 80 by opportunity
        try:
            bp = coin["pair"]
            price = coin.get("last_price", 0)
            change = coin.get("price_change_24h_pct", 0)
            vol = coin.get("volume_24h_usd", 0)
            
            alert = None
            
            # Detect extreme 24h moves (>8% either direction)
            if abs(change) > 8:
                direction = "PUMP" if change > 0 else "DUMP"
                alert = {
                    "pair": bp,
                    "type": f"EXTREME_{direction}",
                    "detail": f"{change:+.2f}% in 24h",
                    "price": price,
                    "volume_usd": vol,
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                }
            
            # Detect very high volume (>$500M daily for non-BTC)
            elif vol > 500_000_000 and bp not in ["BTCUSDT", "ETHUSDT"]:
                alert = {
                    "pair": bp,
                    "type": "VOLUME_SPIKE",
                    "detail": f"Vol ${vol/1e6:,.0f}M (unusual)",
                    "price": price,
                    "change": f"{change:+.2f}%",
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                }
            
            if alert:
                alerts.append(alert)
                
        except Exception:
            continue
    
    state["quick_alerts"] = alerts[:20]
    state["last_quick_screen_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    state["total_quick_screens"] = state.get("total_quick_screens", 0) + 1
    save_state()
    
    # Save quick screen results
    try:
        screen_data = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "universe_size": len(ranked),
            "screened": min(len(ranked), 80),
            "alerts_count": len(alerts),
            "alerts": alerts,
            "top_20_movers": [{
                "pair": c["pair"],
                "score": c.get("opportunity_score", 0),
                "change_24h": c.get("price_change_24h_pct", 0),
                "volume_usd": c.get("volume_24h_usd", 0),
                "price": c.get("last_price", 0)
            } for c in ranked[:20]],
            "fx_rate": get_fx_info()
        }
        with open(QUICK_SCREEN_FILE, "w", encoding="utf-8") as f:
            json.dump(screen_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    
    # Quick screen alerts saved to file only — NOT sent to Telegram (too noisy)
    # Data is still available in quick_screen.json for the Bloomberg dashboard
    
    print(f"[QUICK SCREEN] Done: {len(ranked)} pairs, {len(alerts)} alerts", flush=True)
    return alerts


# ===================================================================
# FULL AI PIPELINE SCAN CYCLE
# ===================================================================
def run_full_scan_cycle():
    """
    Full 5-Layer AI Pipeline scan on:
    - ALL 10 CORE coins (always)
    - TOP 40 movers from the universe (by opportunity score)
    Total: up to ~50 coins per cycle
    """
    load_state()
    guard = check_wallet_and_position_guard()
    if guard.get("pause_scanning"):
        print(f"\n{'='*70}", flush=True)
        print(f"[FULL SCAN] 🛡️ SCANNER DILEWATI: {guard['reason']}", flush=True)
        print(f"{'='*70}", flush=True)
        return []

    cfg = _get_config()
    max_budget = cfg.get("max_budget_idr", 0)   # 0 = dynamic wallet-based
    
    print(f"\n{'='*70}", flush=True)
    print(f"[FULL SCAN] {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", flush=True)
    sizing_mode = f"Dynamic Wallet-Based" if max_budget == 0 else f"Capped Rp {max_budget:,}"
    print(f"[FULL SCAN] MODE: FULL UNIVERSE | SIZING: {sizing_mode}", flush=True)
    print(f"{'='*70}", flush=True)
    
    # Build scan list: Top 10 actionable coins by opportunity score from all 524 pairs
    ranked = rank_universe_by_opportunity()
    
    scan_list = [
        {"symbol": "BTC-USD", "pair": "BTCUSDT", "name": "Bitcoin", "tier": "T1_MEGA"},
        {"symbol": "ETH-USD", "pair": "ETHUSDT", "name": "Ethereum", "tier": "T1_MEGA"},
        {"symbol": "SOL-USD", "pair": "SOLUSDT", "name": "Solana", "tier": "T2_LARGE"},
    ]
    anchor_pairs = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
    for coin in ranked:
        if coin.get("pair") not in anchor_pairs and len(scan_list) < 10:
            scan_list.append(coin)
    
    state["coins_scanned_this_cycle"] = len(scan_list)
    state["universe_size"] = len(ranked)
    
    print(f"[FULL SCAN] Scanning Top {len(scan_list)} actionable coins (from {len(ranked)} total)", flush=True)
    
    approved_signals = []

    def _scan_one(item):
        sym = item.get("symbol", item.get("pair", "").replace("USDT", "-USD"))
        pair = item.get("pair", sym.replace("-USD", "USDT"))
        name = item.get("name", item.get("base_asset", sym))
        tier = item.get("tier", "EXTENDED")
        try:
            # 1. Jalankan 5-Layer Institutional AI Pipeline (SEQUENTIAL — one coin at a time)
            print(f"[SCAN] ▶ Layer 1-5 Pipeline: {sym}...", flush=True)
            res = run_5_layer_pipeline(sym)

            # 2. Sidang 9-Agent Multi-Committee (setelah pipeline selesai, SEQUENTIAL)
            positions_now = []
            if os.path.exists(POSITIONS_FILE):
                try:
                    with open(POSITIONS_FILE, "r", encoding="utf-8") as pf:
                        positions_now = json.load(pf)
                except Exception:
                    pass
            print(f"[SCAN] ▶ 9-Agent Committee: {sym}...", flush=True)
            com_res = run_multi_agent_committee(sym, positions_now)
            return item, sym, pair, name, tier, res, com_res
        except Exception as e:
            print(f"[ERROR] {sym}: {e}", flush=True)
            return item, sym, pair, name, tier, None, None

    # SEQUENTIAL SCAN — one coin at a time (Layer 1 → 2 → 3 → 4 → 5 → Committee)
    # This ensures each coin fully completes its pipeline before the next starts.
    for item in scan_list:
        item, sym, pair, name, tier, res, com_res = _scan_one(item)
        if not res or "error" in res:
            continue

        fc = res.get("layer5_final_call", {})
        status = fc.get("status", "REJECTED")
        conf = fc.get("confidence_score", 0)
        setup = res.get("layer2_setup", {}).get("setup_name", "N/A")

        # Evaluasi konsensus kolaboratif 9-Agent Committee
        com_approved = bool(com_res and com_res.get("approved"))
        com_dir = com_res.get("direction", "SKIP") if com_res else "SKIP"
        com_conf = com_res.get("confidence_pct", 0) if com_res else 0

        # Cek veto komite: jika komite menolak (misal Risk Officer atau Bear veto), batalkan demi keamanan modal
        is_trade_approved = False
        if com_approved and com_dir in ("LONG", "SHORT") and com_conf >= 60:
            is_trade_approved = True
            status = "APPROVED_BY_COMMITTEE"
        elif status == "APPROVED" and (not com_res or com_approved):
            is_trade_approved = True
        elif status == "APPROVED" and com_res and not com_approved:
            pm_dec = com_res.get("portfolio_manager", {}).get("decision", "Risk veto")
            print(f"[COMMITTEE VETO] {sym}: Pipeline lolos tapi 9-Agent Committee mem-veto: {pm_dec}", flush=True)
            status = "REJECTED_BY_COMMITTEE"

        sig_entry = {
            "symbol": sym,
            "binance_pair": pair,
            "name": name,
            "tier": tier,
            "status": "APPROVED" if is_trade_approved else status,
            "confidence": max(conf, com_conf),
            "direction": com_dir if com_dir in ("LONG", "SHORT") else fc.get("direction", "NONE"),
            "setup": setup,
            "committee_approved": com_approved,
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            "opportunity_score": item.get("opportunity_score", 0)
        }

        state["recent_signals"] = [sig_entry] + state["recent_signals"][:49]

        if is_trade_approved:
            state["signals_approved_count"] += 1
            final_dir = com_dir if com_dir in ("LONG", "SHORT") else fc.get("direction", "LONG")
            trade_params = (com_res.get("trade_params") or {}) if com_res else {}
            
            # Gunakan Kelly sizing dan leverage dari Risk Officer komite
            budget_allocated = trade_params.get("budget_idr") or fc.get("position_size_idr", max_budget)
            if max_budget > 0:
                budget_allocated = min(budget_allocated, max_budget)
            leverage_allocated = 20  # Always 20x (user mandate)

            exec_plan = {
                "symbol": sym,
                "binance_pair": pair,
                "direction": final_dir,
                "action": final_dir,
                "confidence_score": max(conf, com_conf),
                "setup_name": setup,
                "entry_price": trade_params.get("entry_price") or fc.get("entry_price"),
                "position_size_idr": budget_allocated,
                "leverage": leverage_allocated,
                "take_profit_1": trade_params.get("tp1_price") or fc.get("take_profit_1"),
                "take_profit_2": trade_params.get("tp2_price") or fc.get("take_profit_2"),
                "take_profit": trade_params.get("tp2_price") or fc.get("take_profit"),
                "stop_loss": trade_params.get("sl_price") or fc.get("stop_loss"),
                "margin_type": "ISOLATED",
                "order_type": "MARKET",
                "estimated_time_horizon": (
                    trade_params.get("estimated_time_horizon")
                    or (com_res.get("estimated_time_horizon") if com_res else None)
                    or fc.get("estimated_time_horizon", "N/A")
                )
            }

            print(f"🔥 KONSENSUS MULTI-AGENT APPROVED! {sym} ({final_dir}) Keyakinan: {exec_plan['confidence_score']}%", flush=True)
            pos = record_position(exec_plan)

            # ONLY broadcast "TRADE EXECUTED" when Binance has verified order execution
            if pos and pos.get("binance_synced"):
                approved_signals.append({"symbol": sym, "pos": pos, "fc": exec_plan, "name": name})
                order_id_str = f" (Order #{pos.get('order_id')})" if pos.get('order_id') else ""
                exchange_status = f"✅ EXECUTED ON BINANCE FUTURES{order_id_str}"

                pos_idr = pos.get('position_size_idr', budget_allocated)
                pos_usd = pos.get('position_size_usd', round(pos_idr / 16500.0, 2))
                tp_val = exec_plan.get("take_profit_2") or exec_plan.get("take_profit_1", 0)
                sl_val = exec_plan.get("stop_loss", 0)
                lev_val = 20

                bull_note = com_res.get("bull_researcher", {}).get("argument", "")[:120] if com_res else ""
                bear_note = com_res.get("bear_researcher", {}).get("argument", "")[:120] if com_res else ""

                msg = (
                    f"🚨 <b>PYROFUEL // 9-AGENT COMMITTEE TRADE EXECUTED!</b>\n\n"
                    f"💎 <b>Aset:</b> <code>{pair}</code> ({name})\n"
                    f"🎯 <b>Arah:</b> <b>{final_dir}</b> (Keyakinan: <b>{exec_plan['confidence_score']}%</b>)\n"
                    f"────────────────────────\n"
                    f"⚙️ <b>Parameters (Kelly Criterion + VaR):</b>\n"
                    f"   📊 Leverage: <b>{lev_val}x ISOLATED (Fixed)</b>\n"
                    f"   💰 Modal: <b>${pos_usd:.2f} USDT</b> (~Rp {pos_idr:,})\n"
                    f"   📍 Entry: ${exec_plan.get('entry_price', 0):,.4f}\n"
                    f"   🎯 Take Profit: ${tp_val:,.4f}\n"
                    f"   🛑 Stop Loss: ${sl_val:,.4f}\n"
                    f"────────────────────────\n"
                    f"⏱️ <b>Est. Waktu Tercapai TP:</b> <b>{exec_plan.get('estimated_time_horizon', 'N/A')}</b>\n"
                    f"────────────────────────\n"
                    f"🏛️ <b>Kolaborasi Sidang Multi-Agent:</b>\n"
                    f"   🟢 <i>Bull Case:</i> {bull_note}\n"
                    f"   🔴 <i>Bear Risk:</i> {bear_note}\n"
                    f"   👑 <i>Konsensus:</i> {com_res.get('portfolio_manager',{}).get('decision','') if com_res else 'Approved'}\n"
                    f"────────────────────────\n"
                    f"🏦 <b>Status Bursa:</b> {exchange_status}\n"
                    f"⚡ <b>100% TERKONFIRMASI: Order #{pos.get('order_id')} terpasang di Binance Futures!</b>"
                )
                send_telegram(msg)
            else:
                # Setup passed 5 layers and committee, but could not be filled on Binance (e.g. margin/notional cap)
                print(f"[EXEC NOT FILLED] {sym}: Konsensus lolos tapi order tidak masuk Binance Futures. Tidak tercatat di portofolio.", flush=True)
                state["signals_rejected_count"] += 1
                send_telegram(
                    f"⚠️ <b>KONSENSUS APPROVED TAPI TIDAK DAPAT MASUK BINANCE</b>\n\n"
                    f"💎 <b>Aset:</b> <code>{pair}</code> ({final_dir} 20x)\n"
                    f"🛡️ <b>Keterangan:</b> Saldo margin tidak mencukupi atau bursa menolak order.\n"
                    f"ℹ️ <b>Status:</b> Posisi <b>TIDAK DIBUKA</b> dan <b>TIDAK TERCATAT</b> di portofolio. Modal 100% aman dalam cash USDT."
                )
        else:
            reason_short = (com_res.get("portfolio_manager", {}).get("decision") if com_res else fc.get("final_reason", ""))[:70]
            print(f"REJECTED {sym}: {reason_short}...", flush=True)
            state["signals_rejected_count"] += 1

    state["total_scans_done"] += 1
    state["last_scan_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    save_state()
    
    # Save universe state
    try:
        universe_data = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "universe_size": len(ranked),
            "scanned_this_cycle": len(scan_list),
            "approved_count": len(approved_signals),
            "approved_symbols": [s["symbol"] for s in approved_signals],
            "fx_rate": get_fx_info(),
            "config": cfg
        }
        with open(UNIVERSE_FILE, "w", encoding="utf-8") as f:
            json.dump(universe_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    
    # Summary Telegram
    summary_msg = (
        f"📊 <b>PYROFUEL SCAN CYCLE #{state['total_scans_done']} COMPLETE</b>\n\n"
        f"🌐 Universe: {len(ranked)} pairs total (Binance Futures)\n"
        f"🔍 Scanned: {len(scan_list)} top actionable coins (Sequential 5-Layer AI Pipeline + 9-Agent)\n"
        f"✅ Approved: {len(approved_signals)}\n"
        f"❌ Rejected: {len(scan_list) - len(approved_signals)}\n"
        f"💰 Sizing: {'Dynamic Wallet-Based (Kelly)' if max_budget == 0 else f'Capped Rp {max_budget:,}'}\n"
        f"⚡ Leverage: FIXED 20x (user mandate)\n"
        f"⏱️ Next cycle: ~5 min"
    )
    if not approved_signals:
        summary_msg += "\n\n<i>🛡️ Tidak ada setup valid. Dana aman dalam cash.</i>"
    send_telegram(summary_msg)
    
    print(f"\n[FULL SCAN] Cycle complete. {len(approved_signals)} approved out of {len(scan_list)} scanned.", flush=True)
    print(f"[FULL SCAN] Next cycle in {state['scan_interval_sec']} seconds...", flush=True)


def start_loop():
    """
    Main loop with two-tier scanning:
    1. Quick Screen every 60 seconds (technical only, no AI)
    2. Full AI Pipeline every 5 minutes (top 50 coins)
    3. Pluang execution on APPROVED signals
    """
    global pluang_client
    cfg = _get_config()
    
    print(f"{'='*70}", flush=True)
    print(f"[*] PYROFUEL AUTONOMOUS CRYPTO FUTURES TRADER v3.0", flush=True)
    print(f"[*] PRIMARY EXECUTION ENGINE: BINANCE FUTURES", flush=True)
    print(f"[*] Margin: {cfg.get('margin_type', 'ISOLATED')} | Order: {cfg.get('order_type', 'MARKET')}", flush=True)
    print(f"[*] Leverage: 20x ISOLATED (Fixed) | Max Budget: Rp {cfg.get('max_budget_idr', 50000):,}", flush=True)
    print(f"[*] Auto Execute: {cfg.get('auto_execute_on_pluang', True)}", flush=True)
    print(f"[*] Quick Screen: Every 60 sec | Full AI: Every 5 min", flush=True)
    print(f"{'='*70}", flush=True)
    
    bn_client = get_binance_client()
    if bn_client:
        try:
            bal = bn_client.get_balance()
            usdt_bal = bal.get("total_wallet_balance", 0) if isinstance(bal, dict) else 0
            print(f"[*] ✅ Binance Futures Engine LIVE! Wallet balance: ${usdt_bal:.2f} USDT", flush=True)
        except Exception as e:
            print(f"[*] ⚠️ Binance Futures check warning: {e}", flush=True)
    else:
        print(f"[*] ⚠️ Binance Futures not configured in .env", flush=True)

    # Initialize Pluang MCP as fallback
    pluang_client = get_pluang_client()
    if pluang_client:
        print(f"[*] ✅ Pluang MCP connected (Secondary)", flush=True)
    else:
        print(f"[*] ⚪ Pluang MCP not active (Binance is Primary)", flush=True)
    
    load_state()
    last_full_scan = 0
    last_quick_scan = 0
    last_pluang_check = 0
    was_in_all_in_mode = False
    
    while True:
        try:
            if not state.get("is_running", True):
                print("[*] Autonomous trader PAUSED.", flush=True)
                time.sleep(30)
                continue
            
            now = time.time()
            guard = check_wallet_and_position_guard()
            
            # Autonomous real-time position monitor (TP/SL/Trailing stop)
            try:
                monitor_and_update_positions()
            except Exception as e:
                print(f"[-] Position monitor error: {e}", flush=True)

            if guard["pause_scanning"]:
                # === ALL-IN POSITION MONITORING ACTIVE ===
                state["all_in_monitoring_mode"] = True
                state["all_in_focus_positions"] = [p.get("symbol") for p in guard["open_positions"]]
                state["all_in_reason"] = guard["reason"]
                save_state()
                
                if not was_in_all_in_mode:
                    was_in_all_in_mode = True
                    syms = ", ".join([f"<code>{p.get('symbol')}</code>" for p in guard["open_positions"]])
                    send_telegram(
                        f"🛡️ <b>[AI SENTINEL] MODE ALL-IN MONITOR POSITION AKTIF!</b>\n\n"
                        f"💰 <b>Saldo Terpakai:</b> Saldo telah dialokasikan penuh ke posisi aktif (Sisa: ${guard['available_usdt']:.2f} USDT).\n"
                        f"💎 <b>Posisi Dikawal:</b> {syms}\n\n"
                        f"⏸️ <b>Scanner 524 Koin & 9 Agent Committee:</b> <b>DIHENTIKAN SEMENTARA</b>\n"
                        f"🎯 <i>Semua sumber daya AI kini 100% all-in mengawal posisi aktif secara real-time hingga Take Profit / Stop Loss tercapai!</i>"
                    )
                    print(f"\n[SENTINEL ALL-IN] 🛡️ {guard['reason']}", flush=True)
                
                # In all-in mode, skip scanning! Focus 100% on the open position.
                time.sleep(8)
                continue

            else:
                # === NORMAL SCANNING ACTIVE ===
                if was_in_all_in_mode:
                    was_in_all_in_mode = False
                    state["all_in_monitoring_mode"] = False
                    state["all_in_focus_positions"] = []
                    save_state()
                    send_telegram(
                        f"🚀 <b>POSISI SELESAI & SALDO TELAH PULIH!</b>\n\n"
                        f"✅ Posisi sebelumnya telah selesai (Take Profit / Stop Loss tereksekusi).\n"
                        f"💰 <b>Saldo Tersedia:</b> ${guard['available_usdt']:.2f} USDT (Modal kembali cair ke wallet).\n\n"
                        f"🔄 <b>Scanner 524 Koin & 9 Agent Committee:</b> <b>KEMBALI AKTIF!</b>\n"
                        f"<i>Memulai pemindaian radar penuh untuk mencari setup peluang terbaik berikutnya...</i>"
                    )
                    print(f"\n[SENTINEL RESUME] 🚀 Posisi selesai. Melanjutkan full scan 524 pairs...", flush=True)
                    # Trigger scan immediately!
                    last_full_scan = 0
                    last_quick_scan = 0

                # Re-check Pluang connection every 5 minutes
                if now - last_pluang_check >= 300:
                    old_client = pluang_client
                    pluang_client = get_pluang_client()
                    if pluang_client and not old_client:
                        print("[PLUANG] 🔄 Reconnected to Pluang MCP!", flush=True)
                        send_telegram("🟢 <b>PLUANG RECONNECTED!</b>\nToken berhasil di-refresh. Auto-trading kembali aktif.")
                    elif not pluang_client and old_client:
                        print("[PLUANG] ⚠️ Lost connection to Pluang MCP", flush=True)
                        send_telegram(
                            "🔴 <b>PLUANG TOKEN EXPIRED</b>\n\n"
                            "Token Pluang kadaluarsa dan refresh gagal.\n"
                            "Auto-trading dihentikan sementara.\n\n"
                            "👉 Ketik <code>/login</code> di Telegram untuk re-login."
                        )
                    last_pluang_check = now

                # Quick screen every 60 seconds (or configured interval)
                if now - last_quick_scan >= state.get("quick_screen_interval_sec", 60):
                    try:
                        run_quick_screen()
                    except Exception as e:
                        print(f"[-] Quick screen error: {e}", flush=True)
                    last_quick_scan = now
                
                # Full AI scan every 5 minutes
                if now - last_full_scan >= state.get("scan_interval_sec", 300):
                    try:
                        run_full_scan_cycle()
                    except Exception as e:
                        print(f"[-] Full scan error: {e}", flush=True)
                    last_full_scan = now
                
                time.sleep(10)  # Check every 10 seconds
            
        except KeyboardInterrupt:
            print("[*] Autonomous trader stopped by user.", flush=True)
            break
        except Exception as e:
            print(f"[-] Main loop exception: {e}", flush=True)
            time.sleep(30)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_full_scan_cycle()
    elif len(sys.argv) > 1 and sys.argv[1] == "--quick":
        run_quick_screen()
    elif len(sys.argv) > 1 and sys.argv[1] == "--universe":
        summary = get_universe_summary()
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        start_loop()
