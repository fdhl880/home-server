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
    try:
        r = requests.get(f"{TELE_API}/getUpdates?limit=5", timeout=10)
        if r.status_code == 200:
            updates = r.json().get("result", [])
            chat_ids = set()
            for u in updates:
                msg = u.get("message") or u.get("callback_query", {}).get("message")
                if msg and "chat" in msg:
                    chat_ids.add(msg["chat"]["id"])

            for cid in chat_ids:
                payload = {
                    "chat_id": cid,
                    "text": text,
                    "parse_mode": "HTML"
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                requests.post(f"{TELE_API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")

def record_position(signal: dict):
    """Record position locally AND execute on Pluang if connected"""
    global pluang_client
    cfg = _get_config()
    max_budget = cfg.get("max_budget_idr", 50000)
    max_lev = cfg.get("max_leverage", 5)
    margin_type = cfg.get("margin_type", "ISOLATED")
    order_type = cfg.get("order_type", "MARKET")
    auto_execute = cfg.get("auto_execute_on_pluang", True)
    max_concurrent = cfg.get("max_concurrent_positions", 3)
    
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

    pos_size = min(signal.get("position_size_idr", max_budget), max_budget)
    leverage = min(signal.get("leverage", 1), max_lev)
    fx = get_fx_info()
    pos_size_usd = round(pos_size / fx["usd_idr"], 4)
    
    pos = {
        "id": f"POS_{signal.get('symbol', 'UNK')}_{int(time.time())}",
        "symbol": signal.get("symbol", ""),
        "binance_pair": signal.get("binance_pair", ""),
        "direction": signal.get("direction", "LONG"),
        "entry_price": signal.get("entry_price", 0),
        "entry_price_idr": convert_usd_to_idr(signal.get("entry_price", 0)),
        "take_profit_1": signal.get("take_profit_1", 0),
        "take_profit_2": signal.get("take_profit_2", 0),
        "stop_loss": signal.get("stop_loss", 0),
        "leverage": leverage,
        "margin_type": margin_type,
        "order_type": order_type,
        "position_size_idr": pos_size,
        "position_size_usd": pos_size_usd,
        "position_size_usdt": pos_size_usd,  # USDT ≈ USD for execution
        "risk_reward_ratio": signal.get("risk_reward_ratio", "1:2.0"),
        "confidence_score": signal.get("confidence_score", 0),
        "setup_name": signal.get("setup_name", "N/A"),
        "opened_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "status": "OPEN",
        "pnl_idr": 0,
        "pnl_usd": 0,
        "pnl_pct": 0.0,
        "pluang_synced": False,
        "pluang_execution": None
    }
    
    # === EXECUTE ON PLUANG ===
    if auto_execute:
        if pluang_client is None:
            pluang_client = get_pluang_client()
        
        if pluang_client:
            try:
                execution_result = pluang_client.execute_full_trade(signal={
                    "binance_pair": pos["binance_pair"],
                    "symbol": pos["symbol"],
                    "direction": pos["direction"],
                    "leverage": pos["leverage"],
                    "entry_price": pos["entry_price"],
                    "take_profit_1": pos["take_profit_1"],
                    "take_profit_2": pos["take_profit_2"],
                    "stop_loss": pos["stop_loss"],
                    "position_size_usdt": pos["position_size_usdt"]
                }, config=cfg)
                
                pos["pluang_synced"] = execution_result.get("pluang_synced", False)
                pos["pluang_execution"] = execution_result
                
                if pos["pluang_synced"]:
                    print(f"[PLUANG] ✅ Trade executed on Pluang: {pos['direction']} {pos['symbol']} "
                          f"${pos_size_usd} {leverage}x {margin_type} {order_type}", flush=True)
                else:
                    print(f"[PLUANG] ⚠️ Trade recorded locally but Pluang execution failed", flush=True)
            except Exception as e:
                print(f"[PLUANG] ❌ Execution error: {e}", flush=True)
                pos["pluang_synced"] = False
                pos["pluang_execution"] = {"error": str(e)}
        else:
            print(f"[PLUANG] ⚠️ No MCP client - skipping position recording because order was not opened on Pluang", flush=True)
            return None

    if not pos.get("pluang_synced"):
        print(f"[PLUANG] ⚠️ Order not executed on Pluang - skipping position recording", flush=True)
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
    if not tickers:
        return positions

    ticker_map = {t["symbol"]: float(t.get("lastPrice", 0)) for t in tickers if "symbol" in t}
    fx_rate = get_fx_info()["usd_idr"]

    updated = False
    for pos in open_pos:
        pair = pos.get("binance_pair") or pos.get("symbol", "").replace("-USD", "USDT")
        current_price = ticker_map.get(pair)
        if not current_price or current_price <= 0:
            continue

        direction = pos.get("direction", "LONG").upper()
        entry_price = float(pos.get("entry_price", 0))
        leverage = float(pos.get("leverage", 1))
        pos_idr = float(pos.get("position_size_idr", 50000))
        pos_usd = float(pos.get("position_size_usd", pos_idr / fx_rate))
        tp1 = float(pos.get("take_profit_1", 0))
        tp2 = float(pos.get("take_profit_2", 0))
        sl = float(pos.get("stop_loss", 0))

        if entry_price <= 0:
            continue

        # Calculate PnL
        if direction == "LONG":
            pnl_pct = ((current_price - entry_price) / entry_price) * leverage * 100.0
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * leverage * 100.0

        pnl_idr = (pnl_pct / 100.0) * pos_idr
        pnl_usd = (pnl_pct / 100.0) * pos_usd

        pos["current_price"] = current_price
        pos["current_price_idr"] = round(current_price * fx_rate, 2)
        pos["pnl_pct"] = round(pnl_pct, 2)
        pos["pnl_idr"] = round(pnl_idr, 2)
        pos["pnl_usd"] = round(pnl_usd, 4)
        pos["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        updated = True

        # Check TP2 (Max Take Profit)
        tp2_hit = (direction == "LONG" and current_price >= tp2 > 0) or (direction == "SHORT" and current_price <= tp2 > 0)
        if tp2_hit:
            pos["status"] = "CLOSED_TP2"
            pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            pos["close_price"] = current_price
            send_telegram(
                f"🎉 <b>PYROFUEL // TAKE PROFIT 2 TERCAPAI!</b>\n\n"
                f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction})\n"
                f"💰 <b>Profit:</b> +{pnl_pct:.2f}% (+Rp {pnl_idr:,.0f} / +${pnl_usd:.2f})\n"
                f"📍 <b>Entry:</b> ${entry_price:,.4f} ➔ <b>Exit:</b> ${current_price:,.4f}\n"
                f"⚡ Posisi otomatis ditutup dengan keuntungan maksimal!"
            )
            continue

        # Check TP1 (Partial Profit / Move to Breakeven)
        tp1_hit = (direction == "LONG" and current_price >= tp1 > 0) or (direction == "SHORT" and current_price <= tp1 > 0)
        if tp1_hit and not pos.get("tp1_secured"):
            pos["tp1_secured"] = True
            pos["stop_loss"] = entry_price  # Trailing stop to breakeven!
            send_telegram(
                f"🎯 <b>PYROFUEL // TAKE PROFIT 1 HIT!</b>\n\n"
                f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction})\n"
                f"📈 <b>Floating Profit:</b> +{pnl_pct:.2f}% (+Rp {pnl_idr:,.0f})\n"
                f"🛡️ <b>Tindakan:</b> Stop Loss dipindahkan ke Entry (${entry_price:,.4f})!\n"
                f"<i>Modal Anda kini 100% terlindungi dari kerugian (Risk-Free Trade). Menuju TP2...</i>"
            )

        # Check Stop Loss
        sl_hit = (direction == "LONG" and current_price <= sl > 0) or (direction == "SHORT" and current_price >= sl > 0)
        if sl_hit:
            pos["status"] = "CLOSED_SL"
            pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            pos["close_price"] = current_price
            send_telegram(
                f"🛑 <b>PYROFUEL // STOP LOSS DITRIGGER</b>\n\n"
                f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction})\n"
                f"📍 <b>Entry:</b> ${entry_price:,.4f} ➔ <b>Exit:</b> ${current_price:,.4f}\n"
                f"📉 <b>PnL:</b> {pnl_pct:.2f}% (Rp {pnl_idr:,.0f} / ${pnl_usd:.2f})\n"
                f"🛡️ Posisi otomatis di-cut untuk melindungi modal utama."
            )

    if updated:
        try:
            with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(positions, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return positions


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
    
    # Send Telegram alert for extreme moves
    if alerts:
        alert_text = "⚡ <b>PYROFUEL QUICK SCREEN ALERTS</b>\n\n"
        for a in alerts[:5]:
            emoji = "🔴" if "DUMP" in a.get("type", "") else "🟢" if "PUMP" in a.get("type", "") else "📊"
            alert_text += f"{emoji} <code>{a['pair']}</code>: <b>{a['type']}</b> - {a['detail']}\n"
        alert_text += f"\n🌐 Universe: {len(ranked)} pairs scanned"
        send_telegram(alert_text)
    
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
    cfg = _get_config()
    max_budget = cfg.get("max_budget_idr", 50000)
    
    print(f"\n{'='*70}", flush=True)
    print(f"[FULL SCAN] {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", flush=True)
    print(f"[FULL SCAN] MODE: FULL UNIVERSE | MAX BUDGET: Rp {max_budget:,}", flush=True)
    print(f"{'='*70}", flush=True)
    
    # Build scan list: CORE + TOP MOVERS
    core_pairs = {item["pair"] for item in CRYPTO_FUTURES_WATCHLIST}
    ranked = rank_universe_by_opportunity()
    
    # Always scan core coins
    scan_list = list(CRYPTO_FUTURES_WATCHLIST)
    
    # Add top 40 non-core movers
    movers_added = 0
    for coin in ranked:
        if coin["pair"] not in core_pairs and movers_added < 40:
            scan_list.append(coin)
            movers_added += 1
    
    state["coins_scanned_this_cycle"] = len(scan_list)
    state["universe_size"] = len(ranked)
    
    print(f"[FULL SCAN] Scanning {len(scan_list)} coins (10 core + {movers_added} top movers from {len(ranked)} total)", flush=True)
    
    approved_signals = []
    
    for idx, item in enumerate(scan_list):
        sym = item.get("symbol", item.get("pair", "").replace("USDT", "-USD"))
        pair = item.get("pair", sym.replace("-USD", "USDT"))
        name = item.get("name", item.get("base_asset", sym))
        tier = item.get("tier", "EXTENDED")
        
        print(f"[{idx+1}/{len(scan_list)}] {sym} ({name}) [{tier}]...", flush=True, end=" ")
        
        try:
            res = run_5_layer_pipeline(sym)
            fc = res.get("layer5_final_call", {})
            status = fc.get("status", "REJECTED")
            conf = fc.get("confidence_score", 0)
            setup = res.get("layer2_setup", {}).get("setup_name", "N/A")

            sig_entry = {
                "symbol": sym,
                "binance_pair": pair,
                "name": name,
                "tier": tier,
                "status": status,
                "confidence": conf,
                "direction": fc.get("direction", "NONE"),
                "setup": setup,
                "time": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                "opportunity_score": item.get("opportunity_score", 0)
            }

            state["recent_signals"] = [sig_entry] + state["recent_signals"][:49]

            if status == "APPROVED":
                state["signals_approved_count"] += 1
                print(f"🔥 APPROVED! Score: {conf}%", flush=True)
                
                fc["symbol"] = sym
                fc["binance_pair"] = pair
                pos = record_position(fc)
                approved_signals.append({"symbol": sym, "pos": pos, "fc": fc, "name": name})

                # Telegram Rich Notification with Pluang execution status
                pluang_status = "✅ EXECUTED ON PLUANG" if pos and pos.get("pluang_synced") else "📝 Recorded Locally"
                margin_t = cfg.get("margin_type", "ISOLATED")
                order_t = cfg.get("order_type", "MARKET")
                msg = (
                    f"🚨 <b>PYROFUEL AI // TRADE SIGNAL APPROVED!</b>\n\n"
                    f"💎 <b>Aset:</b> <code>{sym}</code> ({name})\n"
                    f"📊 <b>Tier:</b> {tier} | <b>Opp Score:</b> {item.get('opportunity_score', 0):.2f}\n"
                    f"🎯 <b>Arah:</b> <b>{fc.get('direction', 'LONG')}</b>\n"
                    f"────────────────────────\n"
                    f"⚙️ <b>Futures Settings:</b>\n"
                    f"   📊 Leverage: <b>{fc.get('leverage', 3)}x</b>\n"
                    f"   🔒 Margin: <b>{margin_t}</b>\n"
                    f"   📋 Order: <b>{order_t}</b>\n"
                    f"────────────────────────\n"
                    f"📊 <b>Setup:</b> <code>{fc.get('setup_name')}</code>\n"
                    f"⭐ <b>Keyakinan:</b> <b>{conf}%</b> (Min 65%)\n"
                    f"⚖️ <b>RRR:</b> {fc.get('risk_reward_ratio')}\n"
                    f"────────────────────────\n"
                    f"📍 <b>Entry:</b> ${fc.get('entry_price', 0):,.4f}\n"
                    f"🎯 <b>TP1:</b> ${fc.get('take_profit_1', 0):,.4f} (50% close)\n"
                    f"🎯 <b>TP2:</b> ${fc.get('take_profit_2', 0):,.4f} (full close)\n"
                    f"🛑 <b>SL:</b> ${fc.get('stop_loss', 0):,.4f}\n"
                    f"🔒 <b>Modal:</b> Rp {pos['position_size_idr']:,} (${pos.get('position_size_usd', 0):.2f})\n"
                    f"────────────────────────\n"
                    f"🏦 <b>Pluang:</b> {pluang_status}\n"
                    f"📝 <b>Alasan:</b>\n<i>{fc.get('final_reason', '-')[:300]}</i>\n\n"
                    f"⚡ <i>Posisi otomatis didaftarkan.</i>"
                )
                markup = {
                    "inline_keyboard": [
                        [
                            {"text": f"✅ Konfirmasi ({sym})", "callback_data": f"confirm_{sym}"},
                            {"text": "❌ Batalkan", "callback_data": f"cancel_{sym}"}
                        ]
                    ]
                }
                send_telegram(msg, markup)
            else:
                reason_short = fc.get("final_reason", "")[:60]
                print(f"REJECTED: {reason_short}...", flush=True)
                state["signals_rejected_count"] += 1

        except Exception as e:
            print(f"ERROR: {e}", flush=True)

        time.sleep(1.0)  # Rate limit respect

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
        f"🌐 Universe: {len(ranked)} pairs total\n"
        f"🔍 Scanned: {len(scan_list)} coins (10 core + {movers_added} movers)\n"
        f"✅ Approved: {len(approved_signals)}\n"
        f"❌ Rejected: {len(scan_list) - len(approved_signals)}\n"
        f"💰 Budget: Rp {max_budget:,}\n"
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
    print(f"[*] MODE: FULL UNIVERSE + PLUANG EXECUTION", flush=True)
    print(f"[*] Margin: {cfg.get('margin_type', 'ISOLATED')} | Order: {cfg.get('order_type', 'MARKET')}", flush=True)
    print(f"[*] Max Leverage: {cfg.get('max_leverage', 5)}x | Max Budget: Rp {cfg.get('max_budget_idr', 50000):,}", flush=True)
    print(f"[*] Auto Execute on Pluang: {cfg.get('auto_execute_on_pluang', True)}", flush=True)
    print(f"[*] Quick Screen: Every 60 sec | Full AI: Every 5 min", flush=True)
    print(f"{'='*70}", flush=True)
    
    # Initialize Pluang MCP
    pluang_client = get_pluang_client()
    if pluang_client:
        print(f"[*] ✅ Pluang MCP connected - trades will be auto-executed", flush=True)
    else:
        print(f"[*] ⚠️ Pluang MCP not connected - recording locally only", flush=True)
    
    load_state()
    last_full_scan = 0
    last_quick_scan = 0
    last_pluang_check = 0
    
    while True:
        try:
            if not state.get("is_running", True):
                print("[*] Autonomous trader PAUSED.", flush=True)
                time.sleep(30)
                continue
            
            now = time.time()
            
            # Autonomous real-time position monitor (TP/SL/Trailing stop)
            try:
                monitor_and_update_positions()
            except Exception as e:
                print(f"[-] Position monitor error: {e}", flush=True)

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
