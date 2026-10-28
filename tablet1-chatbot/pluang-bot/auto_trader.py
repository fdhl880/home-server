"""
===========================================================================
PYROFUEL AUTONOMOUS CRYPTO FUTURES TRADER v3.0
===========================================================================
FULL UNIVERSE SCANNER + 100% BINANCE FUTURES EXECUTION ENGINE

Autonomous background agent that:
1. Fetches FULL Binance Futures universe dynamically (~200+ pairs)
2. Smart-ranks all coins by opportunity score (vol, momentum, range)
3. Scans top movers through 5-Layer AI Pipeline every cycle
4. CORE major coins ALWAYS scanned regardless of rank
5. If APPROVED trade found → EXECUTES ON BINANCE FUTURES (20x ISOLATED)
6. Full futures control: Leverage (20x), Margin Type (ISOLATED), Order Type, TP/SL
7. Updates shared JSON database for Bloomberg Dashboard
8. Currency conversion: Real-time USD & IDR valuations

BINANCE EXECUTION:
- Fixed 20x ISOLATED leverage (user mandate)
- Risk-fractional sizing (2% probation, 5% standard)
- Open position via MARKET/LIMIT order
- Auto place TP + SL hard-capped at 2.5%
- All execution logged to results/execution_log.json
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
from binance_futures import BinanceFuturesClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(RESULTS_DIR, "autotrader_state.json")
POSITIONS_FILE = os.path.join(RESULTS_DIR, "active_positions.json")
QUICK_SCREEN_FILE = os.path.join(RESULTS_DIR, "quick_screen.json")
UNIVERSE_FILE = os.path.join(RESULTS_DIR, "universe_state.json")
EXECUTION_LOG_FILE = os.path.join(RESULTS_DIR, "execution_log.json")

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
    """Record position locally AND execute on Binance Futures"""
    cfg = _get_config()
    max_budget = cfg.get("max_budget_idr", 0)   # 0 = no cap, dynamic wallet-based
    max_lev = cfg.get("max_leverage", 20)
    leverage = min(20, max_lev)  # Fixed 20x leverage (user mandate)
    margin_type = signal.get("margin_type") or cfg.get("margin_type", "ISOLATED")

    # 1. AI GOVERNS ORDER TYPE & LIMIT PRICE
    order_type = (signal.get("order_type") or cfg.get("order_type", "MARKET")).upper()
    limit_price = float(signal.get("limit_price") or signal.get("entry_price", 0))

    tp = float(signal.get("take_profit") or signal.get("take_profit_2") or signal.get("take_profit_1", 0))
    sl = float(signal.get("stop_loss", 0))

    # 2. SIZING FRAKSIONAL BERDASARKAN RISIKO (RISK_FRACTIONAL)
    # Mandat: Risiko per trade dibatasi ketat (2% saat probation, 5% setelah lolos gate).
    # Sisa margin tetap utuh di wallet untuk menjaga liquidation distance pada leverage 20x.
    avail_usdt = 100.0
    try:
        _bn = get_binance_client()
        if _bn:
            _bal = _bn.get_balance()
            if isinstance(_bal, dict) and "available_balance" in _bal:
                avail_usdt = float(_bal.get("available_balance", 0.0))
    except Exception as e:
        print(f"[SIZING] ⚠️ Balance check warning: {e}", flush=True)

    if avail_usdt <= 0:
        avail_usdt = 10.0

    # Jarak Stop Loss (%)
    entry_p = float(signal.get("entry_price") or limit_price or 0.0)
    if entry_p > 0 and sl > 0:
        sl_pct = abs(entry_p - sl) / entry_p
    else:
        sl_pct = 0.008

    # Clamp SL distance sesuai config max_sl_pct (misal 2.25%)
    max_sl = cfg.get("max_sl_pct", 2.25) / 100.0
    min_sl = cfg.get("min_sl_pct", 0.45) / 100.0
    sl_pct = max(min_sl, min(sl_pct, max_sl))

    # T7.2 & T7.3: Evaluasi sizing_mode (ALL_IN default sesuai mandat user, dengan pengunci Profit Vault)
    sizing_mode = str(cfg.get("sizing_mode", "ALL_IN")).upper()
    all_in_fraction = float(cfg.get("all_in_balance_fraction", 0.95))
    locked_vault_usdt = 0.0
    vault_file = os.path.join(RESULTS_DIR, "vault_state.json")
    if os.path.exists(vault_file):
        try:
            with open(vault_file, "r", encoding="utf-8") as vf:
                vdata = json.load(vf)
                locked_vault_usdt = max(0.0, float(vdata.get("locked_profit_vault_usdt", 0.0)))
        except Exception:
            locked_vault_usdt = 0.0

    working_usdt = max(min(avail_usdt, 1.0), avail_usdt - locked_vault_usdt)
    _fx = get_fx_info()

    if sizing_mode == "ALL_IN":
        calc_margin_usd = working_usdt * all_in_fraction
        pos_size_usd = round(calc_margin_usd, 4)
        pos_size = int(pos_size_usd * _fx.get("usd_idr", 16500))
        est_sl_loss_pct = round(sl_pct * leverage * all_in_fraction * 100.0, 2)
        print(
            f"[SIZING] 🔥 Mode ALL_IN ({all_in_fraction*100:.0f}% Working Balance): "
            f"Avail=${avail_usdt:.2f} (Vault=${locked_vault_usdt:.2f}), SL={sl_pct*100:.2f}% "
            f"(Risiko Ekuitas=-{est_sl_loss_pct:.1f}%), Margin=${pos_size_usd:.2f} USDT, Notional=${pos_size_usd*leverage:.2f}",
            flush=True,
        )
    else:
        try:
            import journal
            rep = journal.generate_report() if hasattr(journal, "generate_report") else journal.generate_gate_report()
            is_probation = (rep.get("total_trades", 0) < 20) or not rep.get("gate_passed", False)
        except Exception:
            is_probation = True
        risk_pct = cfg.get("probation_risk_pct", 2.0) if is_probation else cfg.get("risk_pct", 5.0)
        target_loss_usd = working_usdt * (risk_pct / 100.0)
        calc_margin_usd = min(target_loss_usd / (sl_pct * leverage), working_usdt * all_in_fraction)
        min_margin_for_notional = 5.5 / leverage
        calc_margin_usd = max(calc_margin_usd, min_margin_for_notional)
        if max_budget > 0:
            max_budget_usd = max_budget / _fx.get("usd_idr", 16500)
            calc_margin_usd = min(calc_margin_usd, max_budget_usd)
        pos_size_usd = round(calc_margin_usd, 4)
        pos_size = int(pos_size_usd * _fx.get("usd_idr", 16500))
        prob_tag = "PROBATION (2% risk)" if is_probation else "STANDARD (5% risk)"
        print(
            f"[SIZING] ⚖️ Mode RISK_FRACTIONAL [{prob_tag}]: Saldo=${avail_usdt:.2f}, SL={sl_pct*100:.2f}%, "
            f"Margin=${pos_size_usd:.2f} USDT (Rp {pos_size:,.0f}), Notional=${pos_size_usd*leverage:.2f}",
            flush=True,
        )

    auto_execute = cfg.get("auto_execute", cfg.get("auto_execute_on_binance", True))
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
        "exchange": "BINANCE_FUTURES"
    }
    
    # === EXECUTE REAL TRADE (100% BINANCE FUTURES) ===
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
            print("[BINANCE] ⚠️ Binance client not active! Check BINANCE_API_KEY / BINANCE_API_SECRET in .env", flush=True)
            return None

    if not pos.get("binance_synced"):
        print(f"[EXECUTION] ⚠️ Order not executed on Binance Futures - skipping recording to prevent fake reports", flush=True)
        return None

    positions.append(pos)
    try:
        with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(positions, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # Log new position to SQLite WAL Journal
    try:
        import journal
        journal.open_trade({
            "id": pos["id"],
            "signal_id": pos.get("signal_id") or pos["id"],
            "symbol": pos["symbol"],
            "direction": pos["direction"],
            "open_ts": pos["opened_at"],
            "entry_fill": pos["entry_price"],
            "qty": pos.get("quantity") or (pos["position_size_usd"] * pos["leverage"] / pos["entry_price"] if pos["entry_price"] else 0),
            "leverage": pos["leverage"],
            "margin_usd": pos["position_size_usd"],
            "fee_usd": round(pos["position_size_usd"] * pos["leverage"] * 0.0005, 4)
        })
        print(f"[JOURNAL] 📖 Open trade recorded in journal: {pos['id']}", flush=True)
    except Exception as je:
        print(f"[JOURNAL] ⚠️ Journal open trade logging error: {je}", flush=True)

    return pos


def _record_trade_close_in_journal(pos: dict, exit_price: float, exit_reason: str, pnl_usd: float = None):
    """Helper to record closed trades into SQLite WAL journal for accurate win-rate and profit factor metrics"""
    try:
        import journal
        pos_id = pos.get("id")
        if not pos_id:
            return
        lev = int(pos.get("leverage", 20))
        pos_usd = float(pos.get("position_size_usd") or 1.0)
        entry_px = float(pos.get("entry_price") or 1.0)
        dir_str = pos.get("direction", "LONG").upper()
        if pnl_usd is None:
            if dir_str == "LONG":
                pnl_usd = (exit_price - entry_px) / entry_px * pos_usd * lev if entry_px > 0 else 0.0
            else:
                pnl_usd = (entry_px - exit_price) / entry_px * pos_usd * lev if entry_px > 0 else 0.0
        fee_usd = round(pos_usd * lev * 0.0010, 4)  # ~0.10% roundtrip taker fee
        journal.close_trade(pos_id, {
            "close_ts": pos.get("closed_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "exit_fill": exit_price,
            "pnl_usd": round(pnl_usd, 4),
            "fee_usd": fee_usd,
            "exit_reason": exit_reason,
            "is_estimated": 0
        })
        print(f"[JOURNAL] 📕 Closed trade logged in journal: {pos_id} ({exit_reason}, PnL: ${pnl_usd:+.2f})", flush=True)
    except Exception as je:
        print(f"[JOURNAL] ⚠️ Error recording trade close in journal: {je}", flush=True)


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

    updated = False
    fx_rate = get_fx_info()["usd_idr"]

    # 1. Live synchronization with Binance Futures active positions
    bn_client = get_binance_client()
    bn_live_map = None
    if bn_client:
        try:
            live_list = bn_client.get_positions()
            if isinstance(live_list, list):
                bn_live_map = {p["symbol"]: p for p in live_list}
                # Auto-import untracked live Binance positions so AI sentinel & trailing stop monitor them
                for sym, lp in bn_live_map.items():
                    already_tracked = any(
                        p.get("status") == "OPEN" and (p.get("binance_pair") == sym or p.get("symbol", "").replace("-USD", "USDT") == sym)
                        for p in positions
                    )
                    amt = float(lp.get("position_amount", 0))
                    if not already_tracked and abs(amt) > 0:
                        entry_px = float(lp.get("entry_price", 0))
                        lev = int(lp.get("leverage", 20))
                        dir_str = lp.get("direction", "LONG" if amt > 0 else "SHORT")
                        # T0.5: Read existing SL/TP from Binance openAlgoOrders instead of overwriting with +3%/-1.5%
                        tp_px = 0.0
                        sl_px = 0.0
                        sl_algo_id = None
                        tp_algo_id = None
                        sl_state = "MISSING"
                        try:
                            ok_algo, open_algos = bn_client.get_open_algo_orders(sym)
                            if ok_algo:
                                for ao in open_algos:
                                    otype = str(ao.get("orderType", ao.get("type", ""))).upper()
                                    tpx = float(ao.get("triggerPrice", ao.get("stopPrice", 0)) or 0)
                                    if "TAKE_PROFIT" in otype and tpx > 0:
                                        tp_px = tpx
                                        tp_algo_id = ao.get("algoId")
                                    elif "STOP" in otype and tpx > 0:
                                        sl_px = tpx
                                        sl_algo_id = ao.get("algoId")
                                        sl_state = "CONFIRMED"
                        except Exception:
                            sl_state = "UNKNOWN"
                        if tp_px <= 0:
                            tp_px = round(entry_px * (1.015 if dir_str == "LONG" else 0.985), 6)
                        if sl_px <= 0:
                            sl_px = round(entry_px * (0.990 if dir_str == "LONG" else 1.010), 6)
                            try:
                                sl_res = bn_client.set_stop_loss(sym, dir_str, sl_px)
                                if isinstance(sl_res, dict) and "algoId" in sl_res:
                                    sl_algo_id = sl_res["algoId"]
                                    sl_state = "CONFIRMED"
                            except Exception:
                                pass
                        iso_margin = abs(float(lp.get("isolated_margin", (amt * entry_px / lev) if lev else 0)))
                        new_pos = {
                            "id": f"POS_BINANCE_{sym}_{int(time.time())}",
                            "symbol": sym.replace("USDT", "-USD"),
                            "binance_pair": sym,
                            "direction": dir_str,
                            "entry_price": entry_px,
                            "entry_price_idr": round(entry_px * fx_rate, 2),
                            "take_profit": tp_px,
                            "take_profit_1": tp_px,
                            "take_profit_2": tp_px,
                            "stop_loss": sl_px,
                            "init_stop_loss": sl_px,
                            "sl_state": sl_state,
                            "sl_algo_id": sl_algo_id,
                            "tp_algo_id": tp_algo_id,
                            "leverage": lev,
                            "margin_type": lp.get("margin_type", "ISOLATED"),
                            "order_type": "MARKET",
                            "limit_price": entry_px,
                            "position_size_usdt": iso_margin,
                            "position_size_usd": iso_margin,
                            "position_size_idr": round(iso_margin * fx_rate, 2),
                            "opened_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "status": "OPEN",
                            "pnl_pct": 0.0,
                            "pnl_usd": float(lp.get("unrealized_pnl", 0)),
                            "pnl_idr": round(float(lp.get("unrealized_pnl", 0)) * fx_rate, 2),
                            "exchange": "BINANCE_FUTURES",
                            "binance_synced": True,
                            "ai_sentinel_status": "ACTIVE_AI_MONITORED"
                        }
                        positions.append(new_pos)
                        updated = True
                        print(f"[MONITOR] 📥 Auto-imported active Binance position: {sym} ({dir_str} {lev}x, SL State: {sl_state})", flush=True)
        except Exception as e:
            print(f"[MONITOR] Binance sync warning: {e}", flush=True)

    open_pos = [p for p in positions if p.get("status") == "OPEN"]
    if not open_pos:
        if updated:
            try:
                with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
                    json.dump(positions, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        return []

    tickers = get_binance_24h_tickers()
    ticker_map = {t["symbol"]: float(t.get("lastPrice", 0)) for t in tickers if "symbol" in t} if tickers else {}
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
                realized_pnl_from_trades = None
                commission_from_trades = 0.0
                if bn_client:
                    try:
                        recent_trades = bn_client.get_user_trades(pair, limit=10)
                        if isinstance(recent_trades, list) and recent_trades:
                            closing_trades = [t for t in recent_trades if abs(float(t.get("realizedPnl", 0))) > 0]
                            if closing_trades:
                                last_t = closing_trades[-1]
                                curr_px = float(last_t.get("price", curr_px)) or curr_px
                                realized_pnl_from_trades = sum(float(t.get("realizedPnl", 0)) for t in closing_trades[-3:])
                                commission_from_trades = sum(float(t.get("commission", 0)) for t in closing_trades[-3:])
                    except Exception:
                        pass

                if realized_pnl_from_trades is not None and pos_usd > 0:
                    final_pnl_usd = realized_pnl_from_trades - commission_from_trades
                    final_pnl_pct = (final_pnl_usd / pos_usd) * 100.0
                    final_pnl_idr = final_pnl_usd * fx_rate
                else:
                    if direction == "LONG":
                        final_pnl_pct = ((curr_px - entry_price) / entry_price) * leverage * 100.0 if entry_price > 0 else 0
                    else:
                        final_pnl_pct = ((entry_price - curr_px) / entry_price) * leverage * 100.0 if entry_price > 0 else 0
                    final_pnl_idr = (final_pnl_pct / 100.0) * pos_idr
                    final_pnl_usd = (final_pnl_pct / 100.0) * pos_usd

                if final_pnl_pct >= 0:
                    close_status = "CLOSED_TP1_PROFIT_LOCK" if pos.get("tp1_profit_locked") and curr_px != tp else "CLOSED_TP"
                else:
                    close_status = "CLOSED_SL"

                pos["status"] = close_status
                pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                pos["close_price"] = curr_px
                pos["pnl_pct"] = round(final_pnl_pct, 2)
                pos["pnl_idr"] = round(final_pnl_idr, 2)
                pos["pnl_usd"] = round(final_pnl_usd, 4)
                pos["commission_usd"] = round(commission_from_trades, 6)
                _record_trade_close_in_journal(pos, curr_px, pos["status"], final_pnl_usd)

                # T7.3: Update High-Water Mark Profit Vault if available
                try:
                    from risk.vault import ProfitVault
                    bal_now = bn_client.get_balance() if bn_client else {}
                    if isinstance(bal_now, dict) and bal_now.get("total_wallet_balance"):
                        ProfitVault().update_equity(float(bal_now["total_wallet_balance"]))
                except Exception:
                    pass

                event_type = "TAKE PROFIT / PROFIT LOCK" if final_pnl_pct >= 0 else "STOP LOSS"
                send_telegram(
                    f"⚡ <b>[BINANCE LIVE] POSISI {pos.get('symbol')} TELAH DITUTUP!</b>\n\n"
                    f"🎯 <b>Status:</b> <b>{event_type} TEREKSEKUSI DI EXCHANGE</b>\n"
                    f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction} {leverage}x)\n"
                    f"💰 <b>Hasil PnL Net:</b> {final_pnl_pct:+.2f}% ({final_pnl_idr:+,.0f} IDR / ${final_pnl_usd:+.4f} USDT)\n"
                    f"📍 <b>Entry:</b> ${entry_price:,.4f} ➔ <b>Exit Fill:</b> ${curr_px:,.4f}\n\n"
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

        # T0.5: Reconcile Guard — Ensure exchange SL is CONFIRMED; if MISSING, re-place automatically
        if is_binance_pos and bn_client and sl > 0:
            try:
                expected_sl_side = "SELL" if direction == "LONG" else "BUY"
                sl_state = bn_client.verify_stop_loss_active(pair, expected_side=expected_sl_side, max_wait_sec=0.8, return_tristate=True)
                pos["sl_state"] = sl_state
                if sl_state == "MISSING":
                    print(f"[RECONCILE GUARD] 🛡️ SL MISSING on {pair}! Re-placing SL at ${sl:,.4f} on exchange...", flush=True)
                    sl_res = bn_client.set_stop_loss(pair, direction, sl)
                    if isinstance(sl_res, dict) and "algoId" in sl_res:
                        pos["sl_algo_id"] = sl_res["algoId"]
                        pos["sl_state"] = "CONFIRMED"
            except Exception:
                pass

        # T0.6 & T7.4: HIGH-PRECISION SNIPER TWO-STAGE PROFIT LOCK & ON-EXCHANGE R-BASED TRAILING
        # Replaces premature local +20% ROE breakeven with exchange-native amend_stop_loss!
        init_sl = float(pos.get("init_stop_loss") or sl or 0)
        sl_dist_pct = abs(entry_price - init_sl) / entry_price if (entry_price > 0 and init_sl > 0) else 0.008
        sl_dist_pct = max(0.0045, min(sl_dist_pct, 0.025))
        price_gain_pct = ((current_price - entry_price) / entry_price) if direction == "LONG" else ((entry_price - current_price) / entry_price)
        r_multiple_curr = price_gain_pct / sl_dist_pct if sl_dist_pct > 0 else 0.0
        pos["r_multiple_curr"] = round(r_multiple_curr, 3)

        # Stage 1 (T7.4 Sniper 75% Mode): At +0.55R, lock SL on exchange at +0.38R net profit (100% Guaranteed WIN!)
        if r_multiple_curr >= 0.55 and not pos.get("tp1_profit_lock_set"):
            lock_pct = max(0.0022, 0.38 * sl_dist_pct)
            new_sl = round(entry_price * (1.0 + lock_pct if direction == "LONG" else 1.0 - lock_pct), 6)
            better = (direction == "LONG" and new_sl > sl) or (direction == "SHORT" and (sl <= 0 or new_sl < sl))
            if better:
                pos["tp1_profit_lock_set"] = True
                pos["breakeven_set"] = True
                if is_binance_pos and bn_client:
                    amend_res = bn_client.amend_stop_loss(pair, direction, new_sl, old_algo_id=pos.get("sl_algo_id"))
                    if amend_res.get("status") == "AMENDED":
                        pos["sl_algo_id"] = amend_res.get("new_algo_id")
                        pos["sl_state"] = "CONFIRMED"
                pos["stop_loss"] = new_sl
                sl = new_sl
                send_telegram(
                    f"🎯 <b>[SNIPER 75% PROFIT LOCK] TP1 (+0.55R) TERCAPAI — PROFIT DIKUNCI DI BURSA!</b>\n\n"
                    f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction} {int(leverage)}x)\n"
                    f"📈 <b>Floating Profit:</b> +{pnl_pct:.2f}% (+{r_multiple_curr:.2f}R)\n"
                    f"🔒 <b>SL Bursa Di-amend ke:</b> ${new_sl:,.4f} (+0.38R Net Profit Terkunci)\n"
                    f"✨ <i>Transaksi ini 100% TERKUNCI MENANG di bursa sambil mengawal Runner ke TP2!</i>"
                )

        # Stage 2 (T0.6 R-Based Exchange Trailing): +1.0R -> lock +0.65R; +1.5R -> lock +1.10R; +2.0R -> lock +1.55R
        r_trail_stages = [
            (1.00, "r_trail_10_set", 0.65, "Lock +0.65R Profit"),
            (1.50, "r_trail_15_set", 1.10, "Lock +1.10R Profit"),
            (2.00, "r_trail_20_set", 1.55, "Lock +1.55R Profit"),
        ]
        for r_trig, flag_key, r_lock, label in r_trail_stages:
            if r_multiple_curr >= r_trig and not pos.get(flag_key):
                lock_pct = max(0.004, r_lock * sl_dist_pct)
                new_sl = round(entry_price * (1.0 + lock_pct if direction == "LONG" else 1.0 - lock_pct), 6)
                better = (direction == "LONG" and new_sl > sl) or (direction == "SHORT" and (sl <= 0 or new_sl < sl))
                if better:
                    pos[flag_key] = True
                    if is_binance_pos and bn_client:
                        amend_res = bn_client.amend_stop_loss(pair, direction, new_sl, old_algo_id=pos.get("sl_algo_id"))
                        if amend_res.get("status") == "AMENDED":
                            pos["sl_algo_id"] = amend_res.get("new_algo_id")
                            pos["sl_state"] = "CONFIRMED"
                    pos["stop_loss"] = new_sl
                    sl = new_sl
                    send_telegram(
                        f"📈 <b>[ON-EXCHANGE R-TRAILING] {label.upper()}</b>\n"
                        f"💎 <code>{pos.get('symbol')}</code> {direction} | +{r_multiple_curr:.2f}R (ROE: +{pnl_pct:.1f}%)\n"
                        f"🔒 SL Bursa Baru: <b>${new_sl:,.4f}</b>"
                    )

        # ══════════════════════════════════════════════════════════════
        # EMERGENCY FLASH CRASH EXIT
        # Jika harga bergerak >6% melawan posisi dalam <60 menit sejak entry,
        # tutup PAKSA tanpa menunggu SL (slippage pada 20x bisa fatal)
        # ══════════════════════════════════════════════════════════════
        try:
            open_time_str = pos.get("opened_at") or pos.get("entry_time") or ""
            if open_time_str:
                from datetime import timezone as _tz
                open_dt = datetime.fromisoformat(open_time_str.replace(" UTC", "+00:00").replace("Z", "+00:00"))
                mins_open = (datetime.now(_tz.utc) - open_dt.astimezone(_tz.utc)).total_seconds() / 60
                price_move_against = 0.0
                if direction == "LONG" and entry_price > 0:
                    price_move_against = (entry_price - current_price) / entry_price * 100
                elif direction == "SHORT" and entry_price > 0:
                    price_move_against = (current_price - entry_price) / entry_price * 100
                # Trigger: >6% against us within 90 minutes = flash crash
                if price_move_against > 6.0 and mins_open < 90:
                    pos["status"] = "CLOSED_EMERGENCY"
                    pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    pos["close_price"] = current_price
                    pos["close_reason"] = f"FLASH_CRASH_EXIT: -{price_move_against:.1f}% dalam {mins_open:.0f} menit"
                    _record_trade_close_in_journal(pos, current_price, "CLOSED_EMERGENCY", pnl_usd)
                    if is_binance_pos and bn_client:
                        try:
                            bn_client.close_position(pair, direction)
                            bn_client.cancel_all_orders(pair)
                        except Exception as _ece:
                            print(f"[EMERGENCY CLOSE ERROR] {_ece}", flush=True)
                    send_telegram(
                        f"🚨 <b>[PYROFUEL EMERGENCY EXIT] FLASH CRASH TERDETEKSI!</b>\n\n"
                        f"💎 <code>{pos.get('symbol')}</code> {direction} 20x\n"
                        f"📉 Harga bergerak <b>-{price_move_against:.1f}%</b> melawan posisi\n"
                        f"⏱️ Hanya {mins_open:.0f} menit sejak entry — potensi flash crash!\n"
                        f"✂️ <b>Posisi ditutup DARURAT</b> untuk cegah likuidasi paksa.\n"
                        f"💰 PnL: {pnl_pct:.2f}% | Exit: ${current_price:,.4f}"
                    )
                    continue
        except Exception as _fe:
            pass

        # ══════════════════════════════════════════════════════════════
        # TIME-BASED AUTO-CUT (Anti Nyangkut)
        # Jika posisi terbuka >48 jam DAN masih rugi DAN progress ke TP < 10%
        # → tutup posisi, pasar sudah berubah kondisi
        # Jika posisi terbuka >72 jam dengan profit < +5% ROE → partial cut
        # ══════════════════════════════════════════════════════════════
        try:
            _open_str = pos.get("opened_at") or pos.get("entry_time") or ""
            if _open_str:
                from datetime import timezone as _tz2
                _open_dt  = datetime.fromisoformat(_open_str.replace(" UTC", "+00:00").replace("Z", "+00:00"))
                _hrs_open = (datetime.now(_tz2.utc) - _open_dt.astimezone(_tz2.utc)).total_seconds() / 3600

                # Progress ke TP (0% = masih di entry, 100% = sudah kena TP)
                _tp_progress = 0.0
                if tp > 0 and entry_price > 0 and abs(tp - entry_price) > 0:
                    if direction == "LONG":
                        _tp_progress = (current_price - entry_price) / (tp - entry_price) * 100
                    else:
                        _tp_progress = (entry_price - current_price) / (entry_price - tp) * 100
                _tp_progress = max(_tp_progress, 0.0)

                # Rule 1: >48 jam + rugi + progress <10% → cut
                if _hrs_open > 48 and pnl_pct < -5 and _tp_progress < 10:
                    pos["status"] = "CLOSED_TIMEOUT"
                    pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    pos["close_price"] = current_price
                    pos["close_reason"] = f"TIMEOUT_48H: {_hrs_open:.0f}h open, {_tp_progress:.1f}% progress, PnL {pnl_pct:.1f}%"
                    _record_trade_close_in_journal(pos, current_price, "CLOSED_TIMEOUT_48H", pnl_usd)
                    if is_binance_pos and bn_client:
                        try:
                            bn_client.close_position(pair, direction)
                            bn_client.cancel_all_orders(pair)
                        except Exception as _te:
                            print(f"[TIMEOUT CLOSE ERROR] {_te}", flush=True)
                    send_telegram(
                        f"⏰ <b>[PYROFUEL TIMEOUT CUT] Posisi Nyangkut Ditutup!</b>\n\n"
                        f"💎 <code>{pos.get('symbol')}</code> {direction} 20x\n"
                        f"⏱️ Terbuka selama <b>{_hrs_open:.0f} jam</b>\n"
                        f"📊 Progress ke TP: <b>{_tp_progress:.1f}%</b> (terlalu lambat)\n"
                        f"💸 PnL: {pnl_pct:.2f}% → Ditutup untuk lindungi modal\n"
                        f"🔄 <i>Bot akan cari setup baru yang lebih segar</i>"
                    )
                    continue

                # Rule 2: >72 jam + profit tipis (<+10% ROE) → juga cut, ambil profit kecil
                elif _hrs_open > 72 and 0 < pnl_pct < 10 and _tp_progress < 50:
                    pos["status"] = "CLOSED_TIMEOUT_PROFIT"
                    pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    pos["close_price"] = current_price
                    pos["close_reason"] = f"TIMEOUT_72H_PROFIT: {_hrs_open:.0f}h, profit {pnl_pct:.1f}%"
                    _record_trade_close_in_journal(pos, current_price, "CLOSED_TIMEOUT_72H", pnl_usd)
                    if is_binance_pos and bn_client:
                        try:
                            bn_client.close_position(pair, direction)
                            bn_client.cancel_all_orders(pair)
                        except Exception:
                            pass
                    send_telegram(
                        f"⌛ <b>[TIMEOUT PROFIT TAKE] Posisi 72h Ditutup Ambil Profit!</b>\n\n"
                        f"💎 <code>{pos.get('symbol')}</code> {direction} 20x\n"
                        f"⏱️ Terbuka <b>{_hrs_open:.0f} jam</b> — kondisi pasar sudah berubah\n"
                        f"💰 Profit diambil: <b>+{pnl_pct:.2f}%</b> (+Rp {pnl_idr:,.0f})\n"
                        f"🎯 TP masih {_tp_progress:.0f}% perjalanan — lebih baik ambil sekarang\n"
                        f"🔄 <i>Modal bebas untuk cari setup baru</i>"
                    )
                    continue

        except Exception as _tme:
            pass


        # C6 Fix: Only execute local TP/SL market close when exchange-native SL/TP is NOT confirmed active.
        # When sl_state == "CONFIRMED", Binance Futures native MARK_PRICE algo orders own the exit.
        allow_local_tp_sl_fallback = (not is_binance_pos) or (pos.get("sl_state") == "MISSING")

        tp_hit = allow_local_tp_sl_fallback and ((direction == "LONG" and current_price >= tp > 0) or (direction == "SHORT" and current_price <= tp > 0))
        if tp_hit:
            pos["status"] = "CLOSED_TP"
            pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            pos["close_price"] = current_price
            _record_trade_close_in_journal(pos, current_price, "CLOSED_TP", pnl_usd)
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
            updated = True
            continue

        # Check Stop Loss (Local Emergency Fallback only if exchange SL is MISSING)
        sl_hit = allow_local_tp_sl_fallback and ((direction == "LONG" and current_price <= sl > 0) or (direction == "SHORT" and current_price >= sl > 0))
        if sl_hit:
            pos["status"] = "CLOSED_SL"
            pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            pos["close_price"] = current_price
            _record_trade_close_in_journal(pos, current_price, "CLOSED_SL", pnl_usd)
            if is_binance_pos and bn_client:
                try:
                    bn_client.close_position(pair, direction)
                    bn_client.cancel_all_orders(pair)
                except Exception as e:
                    print(f"[BINANCE CLOSE SL ERROR] {e}")
            send_telegram(
                f"🛑 <b>PYROFUEL // STOP LOSS DITRIGGER (LOCAL FALLBACK)</b>\n\n"
                f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction})\n"
                f"📍 <b>Entry:</b> ${entry_price:,.4f} ➔ <b>Exit:</b> ${current_price:,.4f}\n"
                f"🛑 <b>Level SL:</b> ${sl:,.4f}\n"
                f"📉 <b>PnL:</b> {pnl_pct:.2f}% (Rp {pnl_idr:,.0f} / ${pnl_usd:.2f})\n"
                f"🛡️ Posisi otomatis di-cut untuk melindungi modal utama."
            )
            updated = True
            continue

    if updated:
        try:
            with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(positions, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # T9.1 / T9.3: Write heartbeat.json for watchdog & /health diagnostics
    try:
        hb_path = os.path.join(RESULTS_DIR, "heartbeat.json")
        with open(hb_path, "w", encoding="utf-8") as hbf:
            json.dump({
                "timestamp": time.time(),
                "utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "open_positions": len([p for p in positions if p.get("status") == "OPEN"]),
                "status": "HEALTHY",
            }, hbf)
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
            
            # Live sync active positions directly from Binance Futures
            live_pos = bn_client.get_positions()
            if isinstance(live_pos, list):
                for lp in live_pos:
                    amt = abs(float(lp.get("position_amount", lp.get("positionAmt", 0))))
                    if amt > 0:
                        pair_sym = lp.get("symbol", "")
                        # Add to open_pos if not already tracked
                        if not any(p.get("binance_pair") == pair_sym or p.get("symbol", "").replace("-USD", "USDT") == pair_sym for p in open_pos):
                            open_pos.append({
                                "symbol": pair_sym.replace("USDT", "-USD"),
                                "binance_pair": pair_sym,
                                "direction": lp.get("direction") or ("LONG" if float(lp.get("positionAmt", 1)) > 0 else "SHORT"),
                                "entry_price": float(lp.get("entry_price", lp.get("entryPrice", 0))),
                                "current_price": float(lp.get("mark_price", lp.get("markPrice", 0))),
                                "unrealized_pnl": float(lp.get("unrealized_pnl", lp.get("unRealizedProfit", 0))),
                                "leverage": int(lp.get("leverage", 20)),
                                "status": "OPEN",
                                "exchange": "BINANCE_FUTURES",
                                "binance_synced": True
                            })
        except Exception as e:
            print(f"[GUARD] Binance sync notice: {e}", flush=True)

    should_pause = False
    reason = ""

    # T7.1: Check Emergency Panic Lock
    panic_file = os.path.join(RESULTS_DIR, "panic_lock.json")
    if os.path.exists(panic_file):
        try:
            with open(panic_file, "r", encoding="utf-8") as pf:
                p_data = json.load(pf)
            if p_data.get("locked", False):
                should_pause = True
                reason = f"EMERGENCY PANIC LOCK AKTIF: {p_data.get('reason', 'Triggered via /panic')}"
        except Exception:
            pass

    # MANDAT USER: JIKA ADA POSISI AKTIF -> STOP SCAN TOTAL! 100% FOKUS KAWAL POSISI!
    if not should_pause and len(open_pos) > 0:
        should_pause = True
        sym_list = ", ".join([p.get("symbol", "") for p in open_pos])
        reason = (
            f"FOKUS PENUH (100%): Terdapat {len(open_pos)} posisi aktif ({sym_list}). "
            f"Sisa saldo: ${avail_usdt:.2f} USDT (Total: ${total_usdt:.2f} USDT). "
            f"Scanner koin baru DIHENTIKAN TOTAL agar AI 100% fokus mengawal posisi terbuka hingga TP/SL!"
        )

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
    Runs every 60 seconds. (Skipped if active position exists)
    """
    load_state()
    guard = check_wallet_and_position_guard()
    if guard.get("pause_scanning"):
        print(f"[QUICK SCREEN] 🛡️ Dihentikan sementara: {guard['reason']}", flush=True)
        return []

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
# DETEKSI MARKET REGIME (Trending vs Sideways vs Volatile)
# Digunakan untuk memilih strategi yang tepat secara otomatis
# ===================================================================
def detect_market_regime(ranked_coins: list) -> dict:
    """
    Deteksi kondisi pasar saat ini dari data universe:
      TRENDING : BTC/ETH >3% change & volume spike → pakai momentum setup
      SIDEWAYS : >60% koin change <1.5% 24h → pakai range/funding strategies
      VOLATILE : ATR besar tapi arah campur → pakai mean-reversion cautious
    """
    if not ranked_coins:
        return {"regime": "UNKNOWN", "trending_pct": 0, "sideways_pct": 0}

    n = min(len(ranked_coins), 50)
    sample = ranked_coins[:n]
    changes = [abs(c.get("price_change_24h_pct", 0)) for c in sample]

    trending_count = sum(1 for ch in changes if ch > 3.0)
    sideways_count = sum(1 for ch in changes if ch < 1.5)
    volatile_count = sum(1 for ch in changes if ch > 7.0)

    trending_pct = trending_count / n * 100
    sideways_pct = sideways_count / n * 100
    volatile_pct = volatile_count / n * 100

    if volatile_pct > 20:
        regime = "VOLATILE"
    elif trending_pct > 40:
        regime = "TRENDING"
    elif sideways_pct > 55:
        regime = "SIDEWAYS"
    else:
        regime = "MIXED"

    avg_change = sum(changes) / n if n > 0 else 0
    return {
        "regime": regime,
        "trending_pct": round(trending_pct, 1),
        "sideways_pct": round(sideways_pct, 1),
        "volatile_pct": round(volatile_pct, 1),
        "avg_abs_change_24h": round(avg_change, 2),
        "n_sample": n
    }


def run_sideways_market_scanner(ranked_coins: list) -> list:
    """
    STRATEGI KHUSUS PASAR SIDEWAYS:
    Dijalankan otomatis ketika regime = SIDEWAYS (>55% koin flat <1.5%).

    Mencari dua setup terbaik di pasar flat:
    1. FUNDING RATE ARBITRAGE: funding rate ekstrem (>0.03%) → SHORT bias
       (orang bayar funding untuk hold LONG → smart money short squeeze)
    2. BOLLINGER SQUEEZE: BB width sempit + akan breakout → entry awal

    Max 5 koin dikembalikan untuk AI pipeline tambahan.
    """
    sideways_opps = []

    for coin in ranked_coins[:100]:
        pair = coin.get("pair", "")
        change = abs(coin.get("price_change_24h_pct", 0))
        vol    = coin.get("volume_24h_usd", 0)

        # Fokus pada koin yang benar-benar sideways
        if change > 3.0:
            continue
        if vol < 30_000_000:  # min $30M volume untuk likuiditas
            continue

        score = 0
        setup_type = []

        # Cek funding rate (dari ranked data jika ada)
        funding = coin.get("funding_rate", 0) or 0
        if abs(funding) > 0.025:
            score += 3
            direction = "SHORT" if funding > 0 else "LONG"
            setup_type.append(f"FUNDING_ARB({direction}:{funding:+.3f}%)")

        # Bollinger squeeze proxy: koin yg volume biasa tapi gerakan < 0.5% → squeeze
        if change < 0.8 and vol > 50_000_000:
            score += 2
            setup_type.append("BB_SQUEEZE_CANDIDATE")

        # High volume tapi flat = akumulasi diam-diam
        if change < 1.5 and vol > 100_000_000:
            score += 2
            setup_type.append("ACCUMULATION_ZONE")

        if score >= 3:
            sideways_opps.append({
                **coin,
                "sideways_score": score,
                "sideways_setups": setup_type,
                "scan_mode": "SIDEWAYS_HUNTER"
            })

    sideways_opps.sort(key=lambda x: x["sideways_score"], reverse=True)
    top = sideways_opps[:5]

    if top:
        print(f"[SIDEWAYS HUNTER] 📊 Regime SIDEWAYS — ditemukan {len(top)} setup:", flush=True)
        for c in top:
            print(f"  → {c['pair']}: {c['sideways_setups']} score={c['sideways_score']}", flush=True)
    else:
        print(f"[SIDEWAYS HUNTER] Tidak ada setup sideways yang memenuhi syarat.", flush=True)

    return top



# ===================================================================
# TOKEN BUDGET TRACKER
# ===================================================================
# Groq free tier: ~6000 TPM, ~500K TPD
# Gemini free: 15 RPM, 1500 RPD, ~1M TPM
# OpenRouter free: varies per model
#
# Per coin AI pipeline token cost (SETELAH OPTIMASI):
#   Layer 2 Setup Hunter :  input ~800  + output ~300  =  1100 tok
#   Layer 3 Plan Architect:  input ~400  + output ~250  =   650 tok
#   Layer 4 Risk Officer :   input ~300  + output ~200  =   500 tok
#   Layer 5 Final Judge  :   input ~350  + output ~200  =   550 tok
#   TOTAL per koin       :                             = ~2800 tok
#
# PRE-FILTER GATE (tanpa AI): hanya 5-8 koin lolos dari 60
# 8 koin × 2800 = ~22,400 token per siklus 5 menit = AMAN
# (dahulu: 60 koin × 7060 = 423,600 token — jauh melebihi limit)
# ===================================================================

_TOKEN_TRACKER = {
    "session_tokens_used": 0,
    "cycles_done": 0,
    "last_reset": time.time(),
}

def _estimate_tokens_this_cycle(n_coins_ai):
    """Estimasi token yang akan dipakai siklus ini."""
    tokens_per_coin = 2800  # optimized (bukan 7060 lama)
    return n_coins_ai * tokens_per_coin

def _technical_pre_filter(ranked_coins, max_ai_coins=8, available_balance_usdt=None):
    """
    GATE NOL: Filter ketat murni teknikal (TANPA AI) + T0.7 Dynamic MinNotional Filter
    untuk memilih hanya koin yang benar-benar punya edge setup DAN cukup saldo margin
    sebelum memanggil AI.

    Kriteria agar lolos (min 2 dari 4):
    1. RSI ekstrem: < 32 (oversold, siap LONG) atau > 68 (overbought, siap SHORT)
    2. Volume spike: volume 24h ratio > 1.5x rata-rata (konfirmasi partisipasi)
    3. Momentum kuat: |perubahan 24h| > 3% (bukan sideways)
    4. Volatilitas dalam range: 0.5% < ATR% < 5% (tidak terlalu flat atau terlalu liar)
    5. MACD signal: histogram tidak mendekati nol

    Core 10 coins (BTC, ETH, BNB, SOL, dll) SELALU masuk daftar prioritas JIKA memenuhi minNotional.
    """
    from market_data import get_market_indicators_fast, CRYPTO_FUTURES_WATCHLIST, filter_eligible_symbols

    cfg = _get_config()
    fixed_lev = float(cfg.get("fixed_leverage", 20))
    bal_frac = float(cfg.get("all_in_balance_fraction", 0.95))

    # T0.7: Filter out symbols whose minNotional exceeds available_balance * 0.95 * 20
    screen_pool = ranked_coins[:80]
    if available_balance_usdt is not None and available_balance_usdt > 0:
        eligible_pool, skipped_records = filter_eligible_symbols(
            screen_pool,
            available_balance_usdt=available_balance_usdt,
            leverage=int(fixed_lev),
            all_in_fraction=bal_frac,
        )
        if eligible_pool:
            if skipped_records:
                print(
                    f"[T0.7 MIN-NOTIONAL FILTER] Saldo ${available_balance_usdt:.2f} USDT "
                    f"(daya beli 20x: ${available_balance_usdt * bal_frac * fixed_lev:.2f}) → "
                    f"{len(skipped_records)} koin minNotional tinggi (mis. BTCUSDT) dilewati otomatis.",
                    flush=True,
                )
            screen_pool = eligible_pool

    # Core 10 coin symbols — selalu disertakan tanpa filter (selama lolos minNotional)
    core_symbols = {c["symbol"].upper() for c in CRYPTO_FUTURES_WATCHLIST
                    if c.get("tier") in ("CORE", "MAJOR") or
                    c["symbol"].upper() in {"BTC-USD","ETH-USD","BNB-USD","SOL-USD",
                                             "XRP-USD","DOGE-USD","ADA-USD","AVAX-USD",
                                             "LINK-USD","DOT-USD","UNI-USD","MATIC-USD"}}

    candidates = []
    forced_core = []

    for coin in screen_pool:
        pair = coin.get("pair", "")
        sym = coin.get("symbol", pair.replace("USDT", "-USD"))
        change_24h = abs(coin.get("price_change_24h_pct", 0))
        vol_usd = coin.get("volume_24h_usd", 0)
        opp_score = coin.get("opportunity_score", 0)

        # CORE coins: ambil tanpa syarat (max 4 dari core)
        if sym.upper() in core_symbols and len(forced_core) < 4:
            forced_core.append(coin)
            continue

        # Quick pre-checks dari ticker data (tanpa API tambahan):
        score = 0

        # Kriteria 1: Momentum (|24h change| > 3%)
        if change_24h > 3.0:
            score += 1

        # Kriteria 2: Volume tinggi ($50M+)
        if vol_usd > 50_000_000:
            score += 1

        # Kriteria 3: Opportunity score tinggi dari ranker
        if opp_score > 60:
            score += 1

        # Kriteria 4: Momentum sangat kuat (|24h| > 6%)
        if change_24h > 6.0:
            score += 1

        if score >= 2:
            candidates.append((score, coin))

    # Sort by score descending
    candidates.sort(key=lambda x: x[0], reverse=True)

    # Build final list: core first, then best candidates, up to max_ai_coins
    slots_for_dynamic = max(0, max_ai_coins - len(forced_core))
    final = forced_core + [c for _, c in candidates[:slots_for_dynamic]]

    print(f"[PRE-FILTER] {len(screen_pool)} koin eligible di-screen → "
          f"{len(forced_core)} core + {len(final)-len(forced_core)} dynamic = "
          f"{len(final)} lolos → AI pipeline", flush=True)
    return final


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

    # ─────────────────────────────────────────────────────────────────
    # GATE 0: DETEKSI REGIME + PRE-FILTER
    # ─────────────────────────────────────────────────────────────────
    ranked = rank_universe_by_opportunity()
    state["universe_size"] = len(ranked)

    # Deteksi regime pasar dari universe
    regime_info = detect_market_regime(ranked)
    regime = regime_info["regime"]
    state["market_regime"] = regime_info

    print(f"[MARKET REGIME] 🌡️ Kondisi: {regime} | "
          f"Trending: {regime_info['trending_pct']:.0f}% | "
          f"Sideways: {regime_info['sideways_pct']:.0f}% | "
          f"Avg 24h: {regime_info['avg_abs_change_24h']:.2f}%", flush=True)

    # Adjust agresivitas scan berdasarkan regime (fokus ke koin terbaik demi efisiensi kuota AI)
    if regime == "VOLATILE":
        max_coins = 2     # hati-hati saat volatile
    elif regime == "SIDEWAYS":
        max_coins = 3     # fokus koin terkuat saat sideways
    else:
        max_coins = 3     # trending / normal (top 3 actionable coins)

    # Gabungkan ranked + watchlist untuk pre-filter
    seen_pairs_pf = set()
    all_candidates = []
    for c in CRYPTO_FUTURES_WATCHLIST:
        pair_name = c["symbol"].replace("-USD", "USDT")
        if pair_name not in seen_pairs_pf:
            seen_pairs_pf.add(pair_name)
            all_candidates.append({
                "symbol": c["symbol"],
                "pair": pair_name,
                "name": c.get("name", c["symbol"]),
                "tier": c.get("tier", "CORE"),
                "price_change_24h_pct": 0,
                "volume_24h_usd": 0,
                "opportunity_score": 80,
            })
    for coin in ranked:
        p = coin.get("pair")
        if p and p not in seen_pairs_pf:
            seen_pairs_pf.add(p)
            all_candidates.append(coin)

    # Gate teknikal + T0.7 minNotional filter → max N koin untuk AI
    scan_list = _technical_pre_filter(
        all_candidates,
        max_ai_coins=max_coins,
        available_balance_usdt=guard.get("available_usdt"),
    )

    # SIDEWAYS BONUS: Jika pasar sideways, tambahkan koin khusus sideways strategy
    if regime == "SIDEWAYS":
        sideways_coins = run_sideways_market_scanner(ranked)
        seen_in_scan = {c.get("pair") for c in scan_list}
        added = 0
        for sc in sideways_coins:
            if sc.get("pair") not in seen_in_scan and added < 1:
                scan_list.append(sc)
                seen_in_scan.add(sc.get("pair"))
                added += 1
        if added:
            print(f"[SIDEWAYS BONUS] +{added} koin sideways strategy ditambahkan ke scan list", flush=True)

    estimated_tokens = _estimate_tokens_this_cycle(len(scan_list))
    _TOKEN_TRACKER["cycles_done"] += 1
    _TOKEN_TRACKER["session_tokens_used"] += estimated_tokens

    state["coins_scanned_this_cycle"] = len(scan_list)
    print(f"[TOKEN BUDGET] Siklus #{_TOKEN_TRACKER['cycles_done']}: "
          f"{len(scan_list)} koin | Regime: {regime} → estimasi {estimated_tokens:,} token. "
          f"Total sesi: ~{_TOKEN_TRACKER['session_tokens_used']:,} token.", flush=True)
    print(f"[FULL SCAN] AI Pipeline: {len(scan_list)} koin (dari {len(all_candidates)} universe)", flush=True)


    approved_signals = []

    def _scan_one(item):
        sym = item.get("symbol", item.get("pair", "").replace("USDT", "-USD"))
        pair = item.get("pair", sym.replace("-USD", "USDT"))
        name = item.get("name", item.get("base_asset", sym))
        tier = item.get("tier", "EXTENDED")
        try:
            positions_now = []
            if os.path.exists(POSITIONS_FILE):
                try:
                    with open(POSITIONS_FILE, "r", encoding="utf-8") as pf:
                        positions_now = json.load(pf)
                except Exception:
                    pass

            # 1 PROSES TERSATUKAN: 5-Layer Pipeline + Langsung Sidang 9-Agent Multi-Committee
            print(f"[SCAN] ▶ Pipeline & Sidang 9-Agent: {sym}...", flush=True)
            res = run_5_layer_pipeline(sym, active_positions=positions_now)
            com_res = res.get("committee") if isinstance(res, dict) else None
            return item, sym, pair, name, tier, res, com_res
        except Exception as e:
            print(f"[ERROR] {sym}: {e}", flush=True)
            return item, sym, pair, name, tier, None, None

    # SEQUENTIAL SCAN — one coin at a time (Layer 1 → 2 → 3 → 4 → 5 → Committee)
    for idx, item in enumerate(scan_list, start=1):
        pair_disp = item.get('pair') or item.get('symbol', '').replace('-USD', 'USDT')
        print(f"\n[SCAN {idx}/{len(scan_list)}] ▶ Memproses koin: {pair_disp} ({item.get('name', pair_disp)})", flush=True)
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

        # BTC TREND DUMP FILTER (Blueprint T3.1):
        # Batalkan sinyal LONG altcoin jika tren BTC sedang dump tajam
        candidate_dir = com_dir if com_dir in ("LONG", "SHORT") else fc.get("direction", "NONE")
        if is_trade_approved and candidate_dir == "LONG" and sym not in ("BTC-USD", "BTCUSDT"):
            try:
                from market_data import get_market_indicators_fast
                btc_data = get_market_indicators_fast("BTCUSDT")
                if isinstance(btc_data, dict):
                    btc_rsi = float(btc_data.get("rsi_14") or 50.0)
                    btc_p = float(btc_data.get("current_price") or 0.0)
                    btc_e20 = float(btc_data.get("ema_20") or 0.0)
                    btc_e9 = float(btc_data.get("ema_9") or 0.0)
                    btc_chg4h = float(btc_data.get("change_4h_pct") or 0.0)
                    if btc_rsi < 40.0 or (btc_p < btc_e20 and btc_e9 < btc_e20 and btc_chg4h < -1.5):
                        is_trade_approved = False
                        status = "REJECTED_BTC_DUMP"
                        print(f"[BTC GUARD] 🛡️ Altcoin LONG di {sym} DIBATALKAN: BTC sedang dump (RSI: {btc_rsi:.1f}, 4h: {btc_chg4h:+.2f}%)", flush=True)
            except Exception as btc_err:
                print(f"[BTC GUARD] ⚠️ Error evaluating BTC trend: {btc_err}", flush=True)

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
            
            # Leverage 20x fixed & Sizing via RISK_FRACTIONAL di record_position
            budget_allocated = trade_params.get("position_size_idr") or trade_params.get("budget_idr") or fc.get("position_size_idr", 0)
            if max_budget > 0 and budget_allocated > 0:
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

            # Inject TP time prediction from pipeline result
            _tp_pred = None
            if isinstance(res, dict):
                _plan = res.get("layer3_plan") or {}
                _tp_pred = _plan.get("tp_time_prediction")
            if _tp_pred and _tp_pred.get("eta_label") not in (None, "N/A"):
                exec_plan["tp_time_prediction"] = _tp_pred
                exec_plan["estimated_time_horizon"] = _tp_pred.get("eta_label", "N/A")
            else:
                # Compute on-the-fly if not in plan
                try:
                    from pipeline import predict_tp_time
                    _entry = exec_plan.get("entry_price") or 0
                    _tp    = exec_plan.get("take_profit") or 0
                    _sl    = exec_plan.get("stop_loss") or 0
                    if _entry and _tp:
                        _scan = res.get("layer1_scan") or {} if isinstance(res, dict) else {}
                        _mkt  = res.get("market_data") or {} if isinstance(res, dict) else {}
                        _tp_pred = predict_tp_time(_entry, _tp, _sl, setup, _scan, _mkt)
                        exec_plan["tp_time_prediction"] = _tp_pred
                        exec_plan["estimated_time_horizon"] = _tp_pred.get("eta_label", "N/A")
                except Exception:
                    pass

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

                # Build ETA section
                _tp_p = exec_plan.get("tp_time_prediction") or {}
                _eta_label   = _tp_p.get("eta_label") or exec_plan.get("estimated_time_horizon", "N/A")
                _eta_detail  = _tp_p.get("eta_detail", "")
                _eta_conf    = _tp_p.get("confidence_pct", 0)
                _eta_model   = _tp_p.get("model_note", "")
                _tp_dist     = _tp_p.get("tp_distance_pct", 0)
                _velocity    = _tp_p.get("effective_velocity_pct_per_hour", 0)
                _eta_best    = _tp_p.get("eta_hours_optimistic", 0)
                _eta_worst   = _tp_p.get("eta_hours_pessimistic", 0)

                def _fmt_h(h):
                    if not h: return "N/A"
                    if h < 1:   return f"{int(h*60)} menit"
                    elif h < 24: return f"{h:.0f} jam"
                    else:        return f"{h/24:.1f} hari"

                eta_section = (
                    f"⏱️ <b>Prediksi Waktu TP:</b> <b>{_eta_label}</b>\n"
                    f"   ├ Best case : {_fmt_h(_eta_best)}\n"
                    f"   ├ Realistis : {_eta_detail.split(',')[0].replace('Realistis ~','') if _eta_detail else _eta_label}\n"
                    f"   └ Worst case: {_fmt_h(_eta_worst)}\n"
                    f"   📐 TP jarak {_tp_dist:.2f}% | Velocity ~{_velocity:.3f}%/jam\n"
                    f"   🎯 Kepercayaan prediksi: {_eta_conf}%"
                ) if _tp_p else f"⏱️ <b>Est. Waktu TP:</b> {_eta_label}"

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
                    f"{eta_section}\n"
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
                print(f"[AUTO-TRADER] 🛡️ MANDAT FOKUS 100%: Posisi telah terbuka untuk {pair}! Pemindaian koin lain dihentikan seketika agar sistem fokus mengawal posisi aktif!", flush=True)
                break
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
    3. Binance Futures execution on APPROVED signals
    """
    cfg = _get_config()
    auto_exec = cfg.get('auto_execute', cfg.get('auto_execute_on_binance', True))
    
    print(f"{'='*70}", flush=True)
    print(f"[*] PYROFUEL AUTONOMOUS CRYPTO FUTURES TRADER v3.0", flush=True)
    print(f"[*] 100% BINANCE FUTURES EXECUTION ENGINE", flush=True)
    print(f"[*] Margin: {cfg.get('margin_type', 'ISOLATED')} | Order: {cfg.get('order_type', 'MARKET')}", flush=True)
    print(f"[*] Leverage: 20x ISOLATED (Fixed) | Max Budget: Rp {cfg.get('max_budget_idr', 50000):,}", flush=True)
    print(f"[*] Auto Execute: {auto_exec}", flush=True)
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

    load_state()
    last_full_scan = 0
    last_quick_scan = 0
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
