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
import queue
import asyncio
import threading
import requests
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from features.hmm_drift import atomic_write_json
except Exception:
    def atomic_write_json(path: str, payload) -> bool:
        try:
            tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
            return True
        except Exception:
            return False

try:
    import bootstrap_credentials
    bootstrap_credentials.bootstrap()
except Exception:
    pass

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

def sync_control_flags_from_disk():
    """Reload authoritative user control flags (is_running, mode, intervals) without clobbering runtime counters."""
    global state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                disk = json.load(f)
            if isinstance(disk, dict):
                for k in ("is_running", "mode", "scan_interval_sec", "quick_screen_interval_sec"):
                    if k in disk:
                        state[k] = disk[k]
        except Exception:
            pass
    return bool(state.get("is_running", True))

def save_state():
    try:
        # Preserve authoritative user toggle written externally (e.g. via Web UI or Telegram)
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    disk = json.load(f)
                if isinstance(disk, dict) and "is_running" in disk:
                    disk_ts = str(disk.get("control_updated_at") or "")
                    mem_ts = str(state.get("control_updated_at") or "")
                    if disk_ts >= mem_ts:
                        state["is_running"] = disk["is_running"]
                        if disk_ts:
                            state["control_updated_at"] = disk_ts
            except Exception:
                pass
        atomic_write_json(STATE_FILE, state)
    except Exception:
        pass


# === NON-BLOCKING TELEGRAM QUEUE WORKER (Zero loop stall, no polling getUpdates) ===
_TG_QUEUE = queue.Queue(maxsize=200)
_TG_WORKER_STARTED = False
_TG_WORKER_LOCK = threading.Lock()


def _telegram_sender_loop():
    while True:
        item = _TG_QUEUE.get()
        try:
            url, payload = item
            requests.post(url, json=payload, timeout=8)
        except Exception as e:
            print(f"[TELEGRAM ASYNC ERROR] {e}", flush=True)
        finally:
            try:
                _TG_QUEUE.task_done()
            except Exception:
                pass


def _ensure_telegram_worker():
    global _TG_WORKER_STARTED
    if _TG_WORKER_STARTED:
        return
    with _TG_WORKER_LOCK:
        if not _TG_WORKER_STARTED:
            t = threading.Thread(target=_telegram_sender_loop, name="tg-async-sender", daemon=True)
            t.start()
            _TG_WORKER_STARTED = True


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
        return

    _ensure_telegram_worker()
    url = f"{TELE_API}/sendMessage"
    for cid in chat_ids:
        payload = {"chat_id": cid, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            _TG_QUEUE.put_nowait((url, payload))
        except queue.Full:
            try:
                _TG_QUEUE.get_nowait()
                _TG_QUEUE.put_nowait((url, payload))
            except Exception:
                pass


# === HARD RISK BREAKER & REALTIME WS USER DATA STREAM ===
RISK_BREAKER_FILE = os.path.join(RESULTS_DIR, "risk_breaker_state.json")
DEGRADED_STRAT_FILE = os.path.join(RESULTS_DIR, "degraded_strategies.json")
_WS_WAKEUP_EVENT = threading.Event()
_LIVE_MARK_PRICES = {}
_LIVE_MARK_LOCK = threading.Lock()
_WS_WORKER_STARTED = False
_WS_WORKER_LOCK = threading.Lock()


def load_hard_risk_engine(cfg: dict = None, current_equity: float = None):
    """Load HardRiskEngine + daily trade counter persisted across restarts."""
    from risk.engine import HardRiskEngine
    from risk.vault import ProfitRatchetVault

    cfg_raw = dict(cfg or _get_config())
    if "breaker_consecutive_losses" not in cfg_raw and "circuit_breaker_consecutive_losses" in cfg_raw:
        cfg_raw["breaker_consecutive_losses"] = cfg_raw["circuit_breaker_consecutive_losses"]
    vault = ProfitRatchetVault(initial_equity=float(current_equity or 0.0), persist=True)
    eng = HardRiskEngine(config=cfg_raw, vault=vault)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_trades = 0
    if os.path.exists(RISK_BREAKER_FILE):
        try:
            with open(RISK_BREAKER_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                eng.consecutive_losses = int(saved.get("consecutive_losses", 0))
                eng.breaker_until_ts = float(saved.get("breaker_until_ts", 0.0))
                eng.breaker_reason = saved.get("breaker_reason")
                if saved.get("daily_date") == today_str:
                    daily_trades = int(saved.get("daily_trades_count", 0))
                    eng.daily_start_equity = float(saved.get("daily_start_equity", 0.0))
                eng.current_equity = float(saved.get("current_equity", 0.0))
        except Exception:
            pass

    if current_equity is not None and current_equity > 0:
        eng.current_equity = float(current_equity)
        if eng.daily_start_equity <= 0:
            eng.daily_start_equity = float(current_equity)
    eng._daily_date = today_str
    eng._daily_trades_count = daily_trades
    return eng


def save_hard_risk_engine(eng, daily_trades_delta: int = 0) -> dict:
    """Atomically persist HardRiskEngine circuit breaker + daily trade counter."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    curr_date = getattr(eng, "_daily_date", today_str)
    cnt = int(getattr(eng, "_daily_trades_count", 0)) if curr_date == today_str else 0
    cnt = max(0, cnt + int(daily_trades_delta))
    eng._daily_date = today_str
    eng._daily_trades_count = cnt

    max_daily = int(_get_config().get("max_daily_trades", 10) or 10)
    daily_dd_pct = 0.0
    if getattr(eng, "daily_start_equity", 0.0) > 0 and getattr(eng, "current_equity", 0.0) > 0:
        daily_dd_pct = max(0.0, (eng.daily_start_equity - eng.current_equity) / eng.daily_start_equity * 100.0)

    payload = {
        "consecutive_losses": int(eng.consecutive_losses),
        "breaker_consecutive_losses_limit": int(eng.breaker_consecutive_losses),
        "breaker_until_ts": float(eng.breaker_until_ts),
        "breaker_active": bool(eng.is_circuit_breaker_active()),
        "breaker_reason": eng.breaker_reason,
        "daily_date": today_str,
        "daily_trades_count": cnt,
        "max_daily_trades": max_daily,
        "daily_start_equity": round(float(eng.daily_start_equity), 4),
        "current_equity": round(float(eng.current_equity), 4),
        "daily_dd_pct": round(daily_dd_pct, 2),
        "breaker_daily_dd_limit_pct": float(eng.breaker_daily_dd_pct),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    atomic_write_json(RISK_BREAKER_FILE, payload)
    return payload


def _start_realtime_ws_worker(bn_client):
    """Start background daemon thread running Binance Futures UserDataStream + markPrice WS via websockets."""
    global _WS_WORKER_STARTED
    if _WS_WORKER_STARTED or bn_client is None:
        return
    with _WS_WORKER_LOCK:
        if _WS_WORKER_STARTED:
            return
        _WS_WORKER_STARTED = True

    def _ws_runner():
        try:
            import websockets
            from exec.userstream import UserDataStreamManager
        except Exception as e:
            print(f"[WS] Notice: websockets/UserDataStreamManager unavailable ({e})", flush=True)
            return

        async def _loop():
            mgr = UserDataStreamManager(client=bn_client)
            backoff = 2.0
            while True:
                try:
                    lk = mgr.create_listen_key()
                    if not lk:
                        await asyncio.sleep(15.0)
                        continue
                    streams = [lk]
                    try:
                        if os.path.exists(POSITIONS_FILE):
                            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                                cur_p = json.load(f)
                            for p in (cur_p or []):
                                if p.get("status") == "OPEN":
                                    bp = (p.get("binance_pair") or p.get("symbol", "").replace("-USD", "USDT")).lower()
                                    if bp:
                                        streams.append(f"{bp}@markPrice@1s")
                    except Exception:
                        pass

                    base_ws = "wss://stream.binancefuture.com" if getattr(bn_client, "testnet", False) else "wss://fstream.binance.com"
                    url = f"{base_ws}/stream?streams=" + "/".join(streams) if len(streams) > 1 else mgr.get_ws_url(testnet=getattr(bn_client, "testnet", False))

                    async with websockets.connect(url, ping_interval=20, ping_timeout=15, open_timeout=10) as ws:
                        backoff = 2.0
                        last_ka = time.time()
                        while True:
                            if time.time() - last_ka >= 1500.0:
                                mgr.keepalive_listen_key()
                                last_ka = time.time()
                            raw = await asyncio.wait_for(ws.recv(), timeout=60.0)
                            msg = json.loads(raw)
                            payload = msg.get("data", msg) if isinstance(msg, dict) else {}
                            ev = str(payload.get("e", ""))
                            if ev == "markPriceUpdate":
                                s_sym = str(payload.get("s", "")).upper()
                                m_px = float(payload.get("p") or 0.0)
                                if s_sym and m_px > 0:
                                    with _LIVE_MARK_LOCK:
                                        _LIVE_MARK_PRICES[s_sym] = (m_px, time.time())
                            elif ev in ("ORDER_TRADE_UPDATE", "ALGO_UPDATE", "ACCOUNT_UPDATE", "ACCOUNT_CONFIG_UPDATE"):
                                res = mgr.handle_event(payload)
                                _WS_WAKEUP_EVENT.set()
                                if ev in ("ORDER_TRADE_UPDATE", "ALGO_UPDATE"):
                                    print(f"[WS REALTIME] ⚡ {ev}: {res.get('symbol', '')} {res.get('status', '')}", flush=True)
                except asyncio.TimeoutError:
                    try:
                        mgr.keepalive_listen_key()
                    except Exception:
                        pass
                except Exception as wse:
                    await asyncio.sleep(backoff)
                    backoff = min(30.0, backoff * 1.5)

        try:
            asyncio.run(_loop())
        except Exception as e:
            print(f"[WS] Runner exited: {e}", flush=True)

    t = threading.Thread(target=_ws_runner, name="binance-ws-userstream", daemon=True)
    t.start()
    print("[WS] 🌐 Binance Futures UserDataStream + markPrice@1s daemon active (<50ms wakeup)", flush=True)

def record_position(signal: dict):
    """Record position locally AND execute on Binance Futures"""
    cfg = _get_config()
    max_budget = cfg.get("max_budget_idr", 0)   # 0 = no cap, dynamic wallet-based
    max_lev = cfg.get("max_leverage", 20)
    leverage = min(20, max_lev)  # Fixed 20x leverage (user mandate)
    margin_type = signal.get("margin_type") or cfg.get("margin_type", "ISOLATED")

    # 1. SMART EXECUTION DEFAULT (respect config/AI instead of hardcoded MARKET)
    order_type = (signal.get("order_type") or cfg.get("order_type", "MAKER_FIRST_GTX")).upper()
    limit_price = float(signal.get("limit_price") or signal.get("entry_price", 0))

    tp = float(signal.get("take_profit") or signal.get("take_profit_2") or signal.get("take_profit_1", 0))
    sl = float(signal.get("stop_loss", 0))

    # 1b. Hard Risk Circuit Breaker & Max Daily Trades check
    risk_eng = load_hard_risk_engine(cfg)
    max_daily_trades = int(cfg.get("max_daily_trades", 10) or 10)
    if risk_eng.is_circuit_breaker_active():
        print(f"[RISK BREAKER] 🛑 Circuit Breaker active ({risk_eng.breaker_reason}). Entry blocked.", flush=True)
        return None
    if getattr(risk_eng, "_daily_trades_count", 0) >= max_daily_trades:
        print(f"[RISK BREAKER] 🛑 Daily trade limit reached ({risk_eng._daily_trades_count}/{max_daily_trades}). Entry blocked.", flush=True)
        return None

    # 2. LIVE WALLET CHECK (NO hardcoded fake $100/$10 balance fallback!)
    _bn = get_binance_client()
    if not _bn:
        print("[SIZING] ❌ Binance client not configured — refusing fake balance sizing.", flush=True)
        return None
    avail_usdt = 0.0
    total_equity_usdt = 0.0
    try:
        _bal = _bn.get_balance()
        if not isinstance(_bal, dict) or _bal.get("isError") or "available_balance" not in _bal:
            print(f"[SIZING] ❌ Binance balance endpoint unavailable ({_bal}) — entry aborted safely.", flush=True)
            return None
        avail_usdt = float(_bal.get("available_balance", 0.0))
        total_equity_usdt = float(_bal.get("total_wallet_balance", avail_usdt))
    except Exception as e:
        print(f"[SIZING] ❌ Binance balance check failed ({e}) — entry aborted safely.", flush=True)
        return None

    if avail_usdt < 0.30:
        print(f"[SIZING] ⚠️ Insufficient Binance available margin (${avail_usdt:.2f} < $0.30). Entry aborted.", flush=True)
        return None
    risk_eng = load_hard_risk_engine(cfg, current_equity=total_equity_usdt)

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
    
    entry_px_init = float(signal.get("entry_price") or 0)
    dir_init = str(signal.get("direction", "LONG")).upper()
    d_sign_init = -1.0 if dir_init == "SHORT" else 1.0
    sl_dist_init = abs(entry_px_init - sl) / entry_px_init if (entry_px_init > 0 and sl > 0) else 0.012
    tp1_init = float(signal.get("take_profit_1") or 0)
    if tp1_init <= 0 and entry_px_init > 0:
        tp1_init = round(entry_px_init * (1.0 + d_sign_init * 0.55 * sl_dist_init), 6)
    tp2_init = float(signal.get("take_profit_2") or tp or tp1_init)

    pos = {
        "id": f"POS_{signal.get('symbol', 'UNK')}_{int(time.time())}",
        "symbol": signal.get("symbol", ""),
        "binance_pair": signal.get("binance_pair", ""),
        "direction": dir_init,
        "entry_price": entry_px_init,
        "entry_price_idr": convert_usd_to_idr(entry_px_init),
        "take_profit": tp2_init,
        "take_profit_1": tp1_init,
        "take_profit_2": tp2_init,
        "stop_loss": sl,
        "init_stop_loss": sl,
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
        "regime": signal.get("regime", "NORMAL"),
        "p_quant_ml": signal.get("p_quant_ml"),
        "p_knn": signal.get("p_knn"),
        "p_llm": signal.get("p_llm"),
        "calibrated_prob": signal.get("calibrated_prob"),
        "conformal_set": signal.get("conformal_set"),
        "quant_feature_vector": signal.get("quant_feature_vector"),
        "estimated_time_horizon": signal.get("estimated_time_horizon", "N/A"),
        "opened_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "opened_ts": time.time(),
        "max_r_reached": 0.0,
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
                    "position_size_usdt": pos["position_size_usdt"],
                    "math_proof": signal.get("math_proof") or {},
                }, config=cfg)
                
                pos["binance_synced"] = execution_result.get("binance_synced", False)
                pos["binance_execution"] = execution_result
                pos["order_id"] = execution_result.get("order_id")
                pos["routing_used"] = execution_result.get("routing_used", pos["order_type"])
                
                if pos["binance_synced"]:
                    pos["entry_price"] = execution_result.get("entry_price") or pos["entry_price"]
                    pos["take_profit"] = execution_result.get("take_profit") or pos["take_profit"]
                    pos["stop_loss"] = execution_result.get("stop_loss") or pos["stop_loss"]
                    pos["init_stop_loss"] = execution_result.get("stop_loss") or pos.get("init_stop_loss") or pos["stop_loss"]
                    pos["sl_algo_id"] = execution_result.get("sl_algo_id")
                    pos["tp_algo_id"] = execution_result.get("tp_algo_id")
                    pos["sl_state"] = execution_result.get("sl_state", "CONFIRMED")
                    pos["quantity"] = execution_result.get("quantity")
                    limit_str = f" @ ${limit_price:,.4f}" if order_type in ("LIMIT", "GTX", "MAKER_FIRST_GTX") else ""
                    print(f"[BINANCE] ✅ Real trade executed on Binance Futures: {pos['direction']} {pos['binance_pair']} "
                          f"${pos_size_usd} {leverage}x {margin_type} {pos['routing_used']}{limit_str} TP: ${pos['take_profit']} SL: ${pos['stop_loss']} (Order #{pos['order_id']})", flush=True)
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
    atomic_write_json(POSITIONS_FILE, positions)

    try:
        save_hard_risk_engine(risk_eng, daily_trades_delta=1)
    except Exception:
        pass

    # Log new position & TCA execution to SQLite WAL Journal
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
            "fee_usd": round(pos["position_size_usd"] * pos["leverage"] * 0.0005, 4),
            "strategy_id": pos.get("setup_name", "AI_SETUP"),
            "regime": pos.get("regime", "NORMAL"),
            "cal_p": pos.get("calibrated_prob") or (float(pos.get("confidence_score", 70)) / 100.0),
        })
        tca_payload = (pos.get("binance_execution") or {}).get("tca")
        if isinstance(tca_payload, dict) and tca_payload:
            tca_exec_id = journal.record_tca_execution({**tca_payload, "trade_id": pos["id"]})
            pos["tca_exec_id"] = tca_exec_id
        print(f"[JOURNAL] 📖 Open trade & TCA recorded in journal: {pos['id']}", flush=True)
    except Exception as je:
        print(f"[JOURNAL] ⚠️ Journal open trade logging error: {je}", flush=True)

    return pos


PERF_LEDGER_FILE = os.path.join(RESULTS_DIR, "performance_ledger.json")

def _ensure_perf_ledger() -> dict:
    """
    Load or initialize the Persistent Performance Ledger from real verified closed trades (zero fake seed).
    """
    default_ledger = {
        "baseline_wins": 0,
        "baseline_losses": 0,
        "baseline_realized_pnl_idr": 0,
        "baseline_realized_pnl_usd": 0.0,
        "winning_trades": 0,
        "losing_trades": 0,
        "closed_trades": 0,
        "win_rate_pct": 0.0,
        "realized_pnl_idr": 0,
        "realized_pnl_usd": 0.0,
        "recorded_trade_ids": [],
        "history": [],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    if os.path.exists(PERF_LEDGER_FILE):
        try:
            with open(PERF_LEDGER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Strip legacy simulated baseline if no real recorded trades exist yet
                if data.get("baseline_wins") == 15 and not data.get("recorded_trade_ids"):
                    data.update(default_ledger)
                else:
                    return data
        except Exception:
            pass
    try:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        atomic_write_json(PERF_LEDGER_FILE, default_ledger)
    except Exception:
        pass
    return default_ledger


def _update_closed_loop_learners(pos: dict, net_usd: float, exit_price: float, exit_reason: str):
    """Run closed-loop online updates on close: HardRiskEngine, Bandit, Degradation, Calibrator, Conformal, ADWIN, 3-Brain."""
    cfg = _get_config()
    strat_id = str(pos.get("setup_name") or "AI_SETUP")
    regime_str = str(pos.get("regime") or "NORMAL")
    entry_px = float(pos.get("entry_price") or 1.0)
    init_sl = float(pos.get("init_stop_loss") or pos.get("stop_loss") or 0.0)
    lev = float(pos.get("leverage", 20) or 20)
    pos_usd = float(pos.get("position_size_usd") or 1.0)
    sl_dist = max(0.0045, abs(entry_px - init_sl) / entry_px) if (entry_px > 0 and init_sl > 0) else 0.008
    risk_usd = max(0.02, pos_usd * lev * sl_dist)
    r_mult_net = round(float(net_usd) / risk_usd, 4)
    outcome_win = bool(r_mult_net > 0 or net_usd > 0)

    # 1. HardRiskEngine Circuit Breaker update
    try:
        eq_now = state.get("binance_wallet_balance_usdt")
        eng = load_hard_risk_engine(cfg, current_equity=float(eq_now) if eq_now else None)
        res_brk = eng.record_trade_result(net_pnl_usdt=float(net_usd), new_equity=float(eq_now) if eq_now else None)
        save_hard_risk_engine(eng)
        if res_brk.get("breaker_active"):
            send_telegram(
                f"🛑 <b>[HARD RISK BREAKER TRIPPED]</b>\n\n"
                f"⚠️ Alasan: <code>{res_brk.get('breaker_reason')}</code>\n"
                f"📉 Loss Beruntun: {res_brk.get('consecutive_losses')} | Daily DD: {res_brk.get('daily_dd_pct')}%\n"
                f"❄️ Entry baru dikunci otomatis selama {cfg.get('breaker_cooldown_hours', 12)} jam untuk proteksi ekuitas."
            )
    except Exception:
        pass

    # 2. Contextual Thompson Bandit
    try:
        from strategies.bandit_allocator import ContextualThompsonBandit
        bandit = ContextualThompsonBandit()
        bandit.update(strat_id, regime_str, r_net=r_mult_net)
    except Exception:
        pass

    # 3. Walk-Forward Strategy Auto-Degradation check
    try:
        from shadow.promote import evaluate_auto_degradation
        deg = evaluate_auto_degradation(strat_id, window=15, min_trades=15)
        if isinstance(deg, dict):
            degraded_map = {}
            if os.path.exists(DEGRADED_STRAT_FILE):
                try:
                    with open(DEGRADED_STRAT_FILE, "r", encoding="utf-8") as f:
                        degraded_map = json.load(f) or {}
                except Exception:
                    degraded_map = {}
            if deg.get("degraded"):
                was_deg = bool((degraded_map.get(strat_id) or {}).get("degraded"))
                degraded_map[strat_id] = {**deg, "updated_at": time.time()}
                atomic_write_json(DEGRADED_STRAT_FILE, degraded_map)
                if not was_deg:
                    send_telegram(f"⚠️ <b>[AUTO-DEGRADATION]</b> Strategi <code>{strat_id}</code> turun ke <b>SHADOW_ONLY</b> ({deg.get('reason')}).")
            elif strat_id in degraded_map:
                degraded_map.pop(strat_id, None)
                atomic_write_json(DEGRADED_STRAT_FILE, degraded_map)
    except Exception:
        pass

    # 4. PAVA Calibrator + Adaptive Conformal Filter
    cal_p = float(pos.get("calibrated_prob") or (float(pos.get("confidence_score", 70)) / 100.0))
    try:
        from calibration import ProbabilityCalibrator
        ProbabilityCalibrator().record_outcome(cal_p, 1 if outcome_win else 0)
    except Exception:
        pass
    try:
        from ai.conformal import AdaptiveConformalFilter
        sniper_cfg = cfg.get("sniper_75_mode", {})
        AdaptiveConformalFilter(alpha_target=float(sniper_cfg.get("conformal_alpha_target", 0.18))).update(
            p_hat=cal_p, y_true=1 if outcome_win else 0
        )
    except Exception:
        pass

    # 5. ADWIN Concept Drift Detector
    try:
        from features.hmm_drift import ADWINDetector
        drift_res = ADWINDetector().update(r_mult_net)
        if drift_res.get("drift_detected"):
            print(f"[ADWIN DRIFT] 🌊 Concept drift detected in recent trade stream (window={drift_res.get('window_len')})", flush=True)
    except Exception:
        pass

    # 6. Online TabularMetaModel + NeuroSymbolicEnsemble + EpisodicMarketMemory
    x_vec = pos.get("quant_feature_vector")
    if isinstance(x_vec, list) and len(x_vec) >= 10:
        try:
            from features.hmm_drift import (
                load_tabular_meta_model,
                save_tabular_meta_model,
                load_ensemble_weights,
                save_ensemble_weights,
                append_episodic_episode,
            )
            tab_model = load_tabular_meta_model(feature_dim=len(x_vec))
            tab_model.partial_fit(x_vec, 1 if outcome_win else 0)
            save_tabular_meta_model(tab_model)

            p_ml = float(pos.get("p_quant_ml") or 0.65)
            p_knn = float(pos.get("p_knn") or 0.65)
            p_llm = float(pos.get("p_llm") or (float(pos.get("confidence_score", 70)) / 100.0))
            ens = load_ensemble_weights()
            ens.update_from_outcome(p_ml, p_knn, p_llm, outcome_tp1_win=outcome_win, feature_vector=None)
            save_ensemble_weights(ens)

            append_episodic_episode(
                feature_vector=x_vec,
                r_multiple_net=r_mult_net,
                outcome_win=outcome_win,
                regime=regime_str,
                strategy_id=strat_id,
                note=f"{pos.get('symbol')} {exit_reason}",
            )
        except Exception:
            pass


def _record_trade_close_in_journal(pos: dict, exit_price: float, exit_reason: str, pnl_usd: float = None):
    """Helper to record closed trades into SQLite WAL journal, TCA markouts, performance_ledger, and online learners."""
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
        try:
            journal.update_tca_markout(pos_id, "close", float(exit_price or 0.0))
        except Exception:
            pass
        print(f"[JOURNAL] 📕 Closed trade logged in journal: {pos_id} ({exit_reason}, PnL: ${pnl_usd:+.2f})", flush=True)

        # Update Persistent Performance Ledger (Zero-Reset across restarts)
        ledger = _ensure_perf_ledger()
        rec_ids = list(ledger.get("recorded_trade_ids", []))
        if pos_id not in rec_ids:
            rec_ids.append(pos_id)
            fx_r = get_fx_info().get("usd_idr", 16500)
            net_usd = float(pnl_usd) - fee_usd
            net_idr = round(float(pos.get("pnl_idr") if pos.get("pnl_idr") is not None else net_usd * fx_r))
            if net_usd >= 0 or net_idr >= 0:
                ledger["winning_trades"] = int(ledger.get("winning_trades", 0)) + 1
            else:
                ledger["losing_trades"] = int(ledger.get("losing_trades", 0)) + 1
            w = int(ledger["winning_trades"])
            l = int(ledger["losing_trades"])
            ledger["closed_trades"] = w + l
            ledger["win_rate_pct"] = round((w / max(1, w + l)) * 100.0, 2)
            ledger["realized_pnl_idr"] = round(float(ledger.get("realized_pnl_idr", 0)) + net_idr)
            ledger["realized_pnl_usd"] = round(float(ledger.get("realized_pnl_usd", 0.0)) + net_usd, 2)
            ledger["recorded_trade_ids"] = rec_ids[-500:]
            hist = list(ledger.get("history", []))
            hist.insert(0, {
                "id": pos_id,
                "symbol": pos.get("symbol"),
                "direction": dir_str,
                "entry_price": entry_px,
                "close_price": exit_price,
                "pnl_idr": net_idr,
                "pnl_usd": round(net_usd, 4),
                "exit_reason": exit_reason,
                "closed_at": pos.get("closed_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            })
            ledger["history"] = hist[:200]
            ledger["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            atomic_write_json(PERF_LEDGER_FILE, ledger)
            _update_closed_loop_learners(pos, net_usd, exit_price, exit_reason)
    except Exception as je:
        print(f"[JOURNAL] ⚠️ Error recording trade close in journal: {je}", flush=True)


def _safe_sl_against_liquidation(entry_px: float, direction: str, sl_px: float, liq_px: float = 0.0, max_sl_pct: float = 2.25) -> float:
    """Ensure Stop Loss is strictly valid and inside liquidation price with >=28% safety margin."""
    if entry_px <= 0:
        return sl_px
    is_long = str(direction).upper() == "LONG"
    cap_dist = entry_px * (max_sl_pct / 100.0)
    if liq_px and liq_px > 0:
        if is_long and liq_px < entry_px:
            cap_dist = min(cap_dist, (entry_px - liq_px) * 0.72)
        elif (not is_long) and liq_px > entry_px:
            cap_dist = min(cap_dist, (liq_px - entry_px) * 0.72)
    cap_dist = max(cap_dist, entry_px * 0.004)
    if sl_px <= 0:
        return round(entry_px - cap_dist if is_long else entry_px + cap_dist, 6)
    if is_long:
        if sl_px >= entry_px or (liq_px > 0 and sl_px <= liq_px):
            return round(entry_px - cap_dist, 6)
    else:
        if sl_px <= entry_px or (liq_px > 0 and sl_px >= liq_px):
            return round(entry_px + cap_dist, 6)
    return round(sl_px, 6)


def _build_synced_binance_pos(lp: dict, bn_client, fx_rate: float) -> dict:
    """Construct a complete tracked position record from a live Binance Futures position & exchange algo orders."""
    sym = lp.get("symbol", "")
    amt = abs(float(lp.get("position_amount", lp.get("positionAmt", 0)) or 0))
    entry_px = float(lp.get("entry_price", lp.get("entryPrice", 0)) or 0)
    mark_px = float(lp.get("mark_price", lp.get("markPrice", entry_px)) or entry_px)
    liq_px = float(lp.get("liquidation_price", lp.get("liquidationPrice", 0)) or 0)
    lev = int(lp.get("leverage", 20) or 20)
    raw_amt = float(lp.get("position_amount", lp.get("positionAmt", 1 if lp.get("direction") != "SHORT" else -1)) or 1)
    dir_str = str(lp.get("direction") or ("LONG" if raw_amt >= 0 else "SHORT")).upper()
    live_upnl = float(lp.get("unrealized_pnl", lp.get("unRealizedProfit", 0)) or 0)

    tp_px = 0.0
    sl_px = 0.0
    sl_algo_id = None
    tp_algo_id = None
    sl_state = "MISSING"
    if bn_client and sym:
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

    max_sl_cfg = float(_get_config().get("max_sl_pct", 2.25) or 2.25)
    if sl_px <= 0 or (liq_px > 0 and ((dir_str == "LONG" and sl_px <= liq_px) or (dir_str == "SHORT" and sl_px >= liq_px))):
        sl_px = _safe_sl_against_liquidation(entry_px, dir_str, 0.0, liq_px, max_sl_cfg)
        if bn_client and sym and sl_px > 0:
            try:
                sl_res = bn_client.set_stop_loss(sym, dir_str, sl_px)
                if isinstance(sl_res, dict) and "algoId" in sl_res:
                    sl_algo_id = sl_res["algoId"]
                    sl_state = "CONFIRMED"
                else:
                    sl_state = "LOCAL_GUARD_MONITORED"
            except Exception:
                sl_state = "LOCAL_GUARD_MONITORED"

    sl_delta = abs(entry_px - sl_px) if (entry_px > 0 and sl_px > 0) else (entry_px * 0.015)
    sgn = 1.0 if dir_str == "LONG" else -1.0
    tp1_px = round(entry_px + sgn * 0.55 * sl_delta, 6) if entry_px > 0 else 0.0
    if tp_px <= 0 and entry_px > 0:
        tp_px = round(entry_px + sgn * 2.2 * sl_delta, 6)

    iso_margin = abs(float(lp.get("isolated_margin", lp.get("isolatedMargin", 0)) or ((amt * entry_px / lev) if lev else 0)))
    pnl_pct = round((live_upnl / iso_margin) * 100.0, 2) if iso_margin > 0 else 0.0

    return {
        "id": f"POS_BINANCE_{sym}_{int(time.time())}",
        "order_id": f"SYNC_{sym}",
        "symbol": sym.replace("USDT", "-USD"),
        "binance_pair": sym,
        "direction": dir_str,
        "entry_price": entry_px,
        "entry_price_idr": round(entry_px * fx_rate, 2),
        "current_price": mark_px,
        "current_price_idr": round(mark_px * fx_rate, 2),
        "liquidation_price": liq_px,
        "take_profit": tp_px,
        "take_profit_1": tp1_px,
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
        "pnl_pct": pnl_pct,
        "pnl_usd": round(live_upnl, 4),
        "pnl_idr": round(live_upnl * fx_rate, 2),
        "unrealized_pnl": round(live_upnl, 4),
        "exchange": "BINANCE_FUTURES",
        "binance_synced": True,
        "ai_sentinel_status": "ACTIVE_AI_MONITORED",
    }


_THESIS_MONITOR = None
_MICRO_STATE_CACHE = {}
_PREV_DEPTH_BOOKS = {}
_SHADOW_LAST_SYNC_TS = 0.0


def _get_thesis_monitor():
    global _THESIS_MONITOR
    if _THESIS_MONITOR is None:
        from exec.thesis_monitor import IntrabarThesisMonitor
        _THESIS_MONITOR = IntrabarThesisMonitor(survival_threshold=0.18, required_consecutive_breaches=3)
    return _THESIS_MONITOR


def _fetch_live_micro_state(pair: str, bn_client=None) -> dict:
    """Compute real OFI_20, TFI_5m, spot_perp_div, and annualized sigma (20s cache)."""
    now = time.time()
    cached = _MICRO_STATE_CACHE.get(pair)
    if cached and (now - cached[0] < 20.0):
        return cached[1]

    micro = {"ofi_20": 0.0, "tfi_5m": 0.0, "spot_perp_div": 0.0, "vpin": 0.35, "oi_quadrant": "NEUTRAL", "sigma": 0.35}
    try:
        book = bn_client.get_order_book(pair, limit=20) if bn_client and hasattr(bn_client, "get_order_book") else {}
        if not book:
            r_bk = requests.get(f"https://fapi.binance.com/fapi/v1/depth?symbol={pair}&limit=20", timeout=2.5, verify=False)
            if r_bk.status_code == 200:
                book = r_bk.json()
        if book and book.get("bids") and book.get("asks"):
            from features.microstructure import compute_multilevel_ofi
            prev_bk = _PREV_DEPTH_BOOKS.get(pair, book)
            ofi_res = compute_multilevel_ofi(prev_bk, book)
            _PREV_DEPTH_BOOKS[pair] = book
            micro["ofi_20"] = float(ofi_res.get("obi_weighted_20", 0.0) or 0.0)
    except Exception:
        pass

    try:
        r_ag = requests.get(f"https://fapi.binance.com/fapi/v1/aggTrades?symbol={pair}&limit=80", timeout=2.5, verify=False)
        if r_ag.status_code == 200:
            trades = r_ag.json() or []
            buy_v, sell_v = 0.0, 0.0
            for t in trades:
                q_usd = float(t.get("p") or 0) * float(t.get("q") or 0)
                if bool(t.get("m", False)):
                    sell_v += q_usd
                else:
                    buy_v += q_usd
            tot_v = buy_v + sell_v
            if tot_v > 0:
                micro["tfi_5m"] = round((buy_v - sell_v) / tot_v, 4)
    except Exception:
        pass

    try:
        r_pi = requests.get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={pair}", timeout=2.0, verify=False)
        if r_pi.status_code == 200:
            pi = r_pi.json() or {}
            m_p = float(pi.get("markPrice") or 0.0)
            i_p = float(pi.get("indexPrice") or 0.0)
            if m_p > 0 and i_p > 0:
                micro["spot_perp_div"] = round((i_p - m_p) / i_p, 6)
    except Exception:
        pass

    try:
        r_kl = requests.get(f"https://fapi.binance.com/fapi/v1/klines?symbol={pair}&interval=5m&limit=24", timeout=2.5, verify=False)
        if r_kl.status_code == 200:
            kl = r_kl.json() or []
            cl = [float(x[4]) for x in kl if len(x) > 4]
            if len(cl) >= 6:
                import numpy as _np
                rets = _np.diff(_np.log(_np.maximum(cl, 1e-8)))
                # Annualized sigma from 5m bars (288 * 365 = 105120 bars/yr)
                sig_ann = float(_np.std(rets)) * (105120.0 ** 0.5) if rets.size > 2 else 0.35
                micro["sigma"] = max(0.15, min(2.5, sig_ann))
    except Exception:
        pass

    _MICRO_STATE_CACHE[pair] = (now, micro)
    return micro


def _sync_open_shadow_trades(ticker_map: dict):
    """Periodically update counterfactual shadow_trades against live market prices (60s throttle)."""
    global _SHADOW_LAST_SYNC_TS
    now = time.time()
    if not ticker_map or (now - _SHADOW_LAST_SYNC_TS < 60.0):
        return
    _SHADOW_LAST_SYNC_TS = now
    try:
        import journal
        from shadow.engine import ShadowEngine
        with journal.get_db() as conn:
            open_syms = [r["symbol"] for r in conn.execute("SELECT DISTINCT symbol FROM shadow_trades WHERE status = 'OPEN'").fetchall()]
        if not open_syms:
            return
        se = ShadowEngine()
        for sym in open_syms:
            pair = sym.replace("-USD", "USDT").upper()
            px = float(ticker_map.get(pair) or 0.0)
            if px > 0:
                se.update_open_shadows(sym, {"close": px, "high": px, "low": px})
    except Exception:
        pass


def monitor_and_update_positions():
    """
    Real-time autonomous position monitor:
    - Runs every 8-10 seconds (or immediately on <50ms WebSocket event wake-up)
    - Syncs live Binance mark price, unrealized PnL, liquidation price & exchange algo SL/TP
    - Evaluates real-time L2 OFI/TFI/Div orderflow with IntrabarThesisMonitor + Early Invalidation
    - Executes partial TP1 close (tp1_partial_close_pct=0.65) + on-exchange SL lock
    """
    positions = []
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                positions = json.load(f)
        except Exception:
            positions = []

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
                        new_pos = _build_synced_binance_pos(lp, bn_client, fx_rate)
                        positions.append(new_pos)
                        updated = True
                        print(f"[MONITOR] 📥 Auto-imported active Binance position: {sym} ({new_pos['direction']} {new_pos['leverage']}x, SL State: {new_pos['sl_state']})", flush=True)
        except Exception as e:
            print(f"[MONITOR] Binance sync warning: {e}", flush=True)

    tickers = get_binance_24h_tickers()
    ticker_map = {t["symbol"]: float(t.get("lastPrice", 0)) for t in tickers if "symbol" in t} if tickers else {}
    _sync_open_shadow_trades(ticker_map)

    open_pos = [p for p in positions if p.get("status") == "OPEN"]
    if not open_pos:
        if updated:
            atomic_write_json(POSITIONS_FILE, positions)
        return []

    cfg_mon = _get_config()
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
                # Still open on Binance — sync official entry, mark price, liquidation price, margin and unrealized PnL
                live_item = bn_live_map[pair]
                live_entry = float(live_item.get("entry_price", 0) or 0)
                if live_entry > 0:
                    entry_price = live_entry
                    pos["entry_price"] = entry_price
                    pos["entry_price_idr"] = round(entry_price * fx_rate, 2)
                live_liq = float(live_item.get("liquidation_price", 0) or 0)
                if live_liq > 0:
                    pos["liquidation_price"] = live_liq
                live_margin = abs(float(live_item.get("isolated_margin", 0) or 0))
                if live_margin > 0:
                    pos_usd = live_margin
                    pos_idr = live_margin * fx_rate
                    pos["position_size_usd"] = round(pos_usd, 4)
                    pos["position_size_usdt"] = round(pos_usd, 4)
                    pos["position_size_idr"] = round(pos_idr, 2)
                if not pos.get("order_id") or str(pos.get("order_id")) == "None":
                    pos["order_id"] = f"SYNC_{pair}"
                current_price = float(live_item.get("mark_price", 0)) or ticker_map.get(pair, entry_price)
                with _LIVE_MARK_LOCK:
                    _ws_m = _LIVE_MARK_PRICES.get(pair)
                    if _ws_m and (time.time() - _ws_m[1] < 3.0) and _ws_m[0] > 0:
                        current_price = float(_ws_m[0])
                live_upnl = float(live_item.get("unrealized_pnl", 0))
                pnl_usd = live_upnl
                pnl_idr = live_upnl * fx_rate
                pnl_pct = (live_upnl / pos_usd * 100.0) if pos_usd > 0 else 0.0
                pos["unrealized_pnl"] = round(live_upnl, 4)
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

        # Backfill SL / TP1 / TP2 levels if an imported or manual position lacks them
        max_sl_cfg = float(_get_config().get("max_sl_pct", 2.25) or 2.25)
        liq_px_curr = float(pos.get("liquidation_price", 0) or 0)
        if is_binance_pos and bn_client and (sl <= 0 or tp <= 0):
            try:
                ok_algo, open_algos = bn_client.get_open_algo_orders(pair)
                if ok_algo:
                    for ao in open_algos:
                        otype = str(ao.get("orderType", ao.get("type", ""))).upper()
                        tpx = float(ao.get("triggerPrice", ao.get("stopPrice", 0)) or 0)
                        if "TAKE_PROFIT" in otype and tpx > 0 and tp <= 0:
                            tp = tpx
                            pos["take_profit"] = tp
                            pos["take_profit_2"] = tp
                            pos["tp_algo_id"] = ao.get("algoId")
                        elif "STOP" in otype and tpx > 0 and sl <= 0:
                            sl = tpx
                            pos["stop_loss"] = sl
                            pos["init_stop_loss"] = pos.get("init_stop_loss") or sl
                            pos["sl_algo_id"] = ao.get("algoId")
                            pos["sl_state"] = "CONFIRMED"
            except Exception:
                pass
        if sl <= 0 and entry_price > 0:
            sl = _safe_sl_against_liquidation(entry_price, direction, 0.0, liq_px_curr, max_sl_cfg)
            pos["stop_loss"] = sl
            pos["init_stop_loss"] = pos.get("init_stop_loss") or sl
        if entry_price > 0 and sl > 0:
            sl_del = abs(entry_price - sl)
            sgn_d = 1.0 if direction == "LONG" else -1.0
            if tp <= 0:
                tp = round(entry_price + sgn_d * 2.2 * sl_del, 6)
                pos["take_profit"] = tp
                pos["take_profit_2"] = tp
            if not pos.get("take_profit_1") or abs(float(pos.get("take_profit_1") or 0) - tp) < max(1e-8, entry_price * 0.0015):
                pos["take_profit_1"] = round(entry_price + sgn_d * 0.55 * sl_del, 6)

        # T0.5: Reconcile Guard — Ensure exchange SL is CONFIRMED; if UNCONFIRMED/MISSING, clamp safely & re-place automatically
        if is_binance_pos and bn_client and sl > 0:
            try:
                expected_sl_side = "SELL" if direction == "LONG" else "BUY"
                sl_state = bn_client.verify_stop_loss_active(pair, expected_side=expected_sl_side, max_wait_sec=0.8, return_tristate=True)
                pos["sl_state"] = sl_state
                if sl_state != "CONFIRMED":
                    safe_sl = _safe_sl_against_liquidation(entry_price, direction, sl, liq_px_curr, max_sl_cfg)
                    if safe_sl != sl:
                        sl = safe_sl
                        pos["stop_loss"] = sl
                    print(f"[RECONCILE GUARD] 🛡️ SL {sl_state} on {pair}! Re-placing SL at ${sl:,.4f} on exchange...", flush=True)
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
        pos["max_r_reached"] = round(max(float(pos.get("max_r_reached") or 0.0), r_multiple_curr), 3)

        # Compute elapsed time & record +1m / +5m Post-Trade Markout in SQLite journal
        elapsed_sec = 0.0
        _open_str_m = pos.get("opened_at") or pos.get("entry_time") or ""
        if pos.get("opened_ts"):
            elapsed_sec = max(0.0, time.time() - float(pos["opened_ts"]))
        elif _open_str_m:
            try:
                from datetime import timezone as _tz_m
                _od = datetime.fromisoformat(_open_str_m.replace(" UTC", "+00:00").replace("Z", "+00:00"))
                elapsed_sec = max(0.0, (datetime.now(_tz_m.utc) - _od.astimezone(_tz_m.utc)).total_seconds())
            except Exception:
                elapsed_sec = 0.0
        if pos.get("id"):
            try:
                import journal
                if elapsed_sec >= 60.0 and not pos.get("markout_1m_done"):
                    if journal.update_tca_markout(pos["id"], "1m", current_price):
                        pos["markout_1m_done"] = True
                if elapsed_sec >= 300.0 and not pos.get("markout_5m_done"):
                    if journal.update_tca_markout(pos["id"], "5m", current_price):
                        pos["markout_5m_done"] = True
            except Exception:
                pass

        # Real Orderflow Intrabar First-Passage Survival & Early Invalidation (0.35R / Structural Reversal)
        try:
            micro_state = _fetch_live_micro_state(pair, bn_client=bn_client)
            tm = _get_thesis_monitor()
            early_loss_lim = abs(float(cfg_mon.get("early_invalidation_max_loss_r", 0.35) or 0.35))
            allow_ai_emg = (
                r_multiple_curr <= -early_loss_lim
                and (time.time() - float(pos.get("last_ai_emg_ts") or 0.0) >= 90.0)
            )
            decide_eng = None
            if allow_ai_emg:
                pos["last_ai_emg_ts"] = time.time()
                try:
                    from ai.decide import AIDecisionEngine
                    decide_eng = AIDecisionEngine()
                except Exception:
                    decide_eng = None

            th_res = tm.evaluate_position(
                symbol=pair,
                direction=direction,
                entry_price=entry_price,
                current_price=current_price,
                sl_price=sl if sl > 0 else init_sl,
                tp_price=tp if tp > 0 else entry_price * (1.02 if direction == "LONG" else 0.98),
                elapsed_sec=elapsed_sec,
                micro_state=micro_state,
                sigma=float(micro_state.get("sigma", 0.35)),
                max_r_reached=float(pos.get("max_r_reached") or 0.0),
                decide_engine=decide_eng,
            )
            pos["p_survive_pct"] = round(float(th_res.get("p_survive", 0.78)) * 100.0, 1)
            pos["orderflow_mu_drift"] = th_res.get("mu_drift")
            pos["ofi_20_live"] = micro_state.get("ofi_20")
            pos["tfi_5m_live"] = micro_state.get("tfi_5m")

            should_early_exit = (
                (r_multiple_curr <= -early_loss_lim)
                and (bool(th_res.get("should_scratch")) or int(th_res.get("consecutive_breaches", 0)) >= 3)
            )
            if should_early_exit:
                pos["status"] = "CLOSED_EARLY_INVALIDATION"
                pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                pos["close_price"] = current_price
                pos["close_reason"] = th_res.get("close_reason") or "EARLY_ORDERFLOW_THESIS_INVALIDATION"
                _record_trade_close_in_journal(pos, current_price, "CLOSED_EARLY_INVALIDATION", pnl_usd)
                if is_binance_pos and bn_client:
                    try:
                        bn_client.close_position(pair, direction)
                        bn_client.cancel_all_orders(pair)
                    except Exception as _ee:
                        print(f"[EARLY INVALIDATION CLOSE ERROR] {_ee}", flush=True)
                tm.reset_symbol(pair)
                send_telegram(
                    f"⚡ <b>[EARLY THESIS INVALIDATION] {pos.get('symbol')} Ditutup Dini</b>\n\n"
                    f"📉 R-Multiple: <b>{r_multiple_curr:+.2f}R</b> (Batas Invalidation: -{early_loss_lim:.2f}R)\n"
                    f"🧠 P(Survive): <b>{pos['p_survive_pct']:.1f}%</b> | OFI={micro_state.get('ofi_20', 0):+.2f} | TFI={micro_state.get('tfi_5m', 0):+.2f}\n"
                    f"🛡️ Memotong loss lebih awal sebelum menyentuh -1.0R penuh!"
                )
                updated = True
                continue
        except Exception:
            pos["p_survive_pct"] = pos.get("p_survive_pct", 78.0)

        # Stage 0 (Early Breakeven Scratch Guard at +0.30R / +6% ROE):
        # Prevents winning trades that reach +0.30R from ever reversing into a full -1.0R loss!
        if r_multiple_curr >= 0.30 and not pos.get("stage0_be_guard_set") and not pos.get("tp1_profit_lock_set"):
            be_lock_pct = max(0.0012, 0.08 * sl_dist_pct)  # +0.08R covers roundtrip taker fees + micro profit
            new_sl = round(entry_price * (1.0 + be_lock_pct if direction == "LONG" else 1.0 - be_lock_pct), 6)
            better = (direction == "LONG" and new_sl > sl) or (direction == "SHORT" and (sl <= 0 or new_sl < sl))
            if better:
                pos["stage0_be_guard_set"] = True
                pos["breakeven_set"] = True
                if is_binance_pos and bn_client:
                    try:
                        amend_res = bn_client.amend_stop_loss(pair, direction, new_sl, old_algo_id=pos.get("sl_algo_id"))
                        if isinstance(amend_res, dict) and amend_res.get("status") == "AMENDED":
                            pos["sl_algo_id"] = amend_res.get("new_algo_id")
                            pos["sl_state"] = "CONFIRMED"
                    except Exception:
                        pass
                pos["stop_loss"] = new_sl
                sl = new_sl

        # Stage 1 (T7.4 Sniper 75% Mode): At +0.55R, lock SL on exchange at +0.38R & Partial Close (tp1_partial_close_pct=0.65)
        sniper_m = cfg_mon.get("sniper_75_mode") or {}
        tp1_trig_r = float(sniper_m.get("tp1_lock_trigger_r", 0.55) or 0.55)
        tp1_lock_r = float(sniper_m.get("sl_lock_after_tp1_r", 0.38) or 0.38)
        tp1_partial_frac = float(cfg_mon.get("tp1_partial_close_pct", 0.65) or 0.65)
        if r_multiple_curr >= tp1_trig_r and not pos.get("tp1_profit_lock_set"):
            lock_pct = max(0.0022, tp1_lock_r * sl_dist_pct)
            new_sl = round(entry_price * (1.0 + lock_pct if direction == "LONG" else 1.0 - lock_pct), 6)
            better = (direction == "LONG" and new_sl > sl) or (direction == "SHORT" and (sl <= 0 or new_sl < sl))
            if better:
                pos["tp1_profit_lock_set"] = True
                pos["breakeven_set"] = True
                if is_binance_pos and bn_client:
                    amend_res = bn_client.amend_stop_loss(pair, direction, new_sl, old_algo_id=pos.get("sl_algo_id"))
                    if isinstance(amend_res, dict) and amend_res.get("status") == "AMENDED":
                        pos["sl_algo_id"] = amend_res.get("new_algo_id")
                        pos["sl_state"] = "CONFIRMED"
                pos["stop_loss"] = new_sl
                sl = new_sl

                partial_note = ""
                if is_binance_pos and bn_client and tp1_partial_frac > 0 and not pos.get("tp1_partial_closed"):
                    try:
                        pc_res = bn_client.partial_close_position(pair, direction, fraction=tp1_partial_frac)
                        pos["tp1_partial_result"] = pc_res
                        if pc_res.get("partial_closed"):
                            pos["tp1_partial_closed"] = True
                            pos["quantity"] = pc_res.get("remaining_qty", pos.get("quantity"))
                            partial_note = f"\n💵 <b>Partial Close {int(tp1_partial_frac*100)}%:</b> Realized {pc_res.get('closed_qty')} (Sisa {pc_res.get('remaining_qty')} Runner)"
                        else:
                            partial_note = f"\nℹ️ <b>Partial Close:</b> {pc_res.get('status')} (Full qty kept under +{tp1_lock_r}R SL lock)"
                    except Exception:
                        pass

                send_telegram(
                    f"🎯 <b>[SNIPER 75% PROFIT LOCK] TP1 (+{tp1_trig_r:.2f}R) TERCAPAI — PROFIT DIKUNCI DI BURSA!</b>\n\n"
                    f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction} {int(leverage)}x)\n"
                    f"📈 <b>Floating Profit:</b> +{pnl_pct:.2f}% (+{r_multiple_curr:.2f}R)\n"
                    f"🔒 <b>SL Bursa Di-amend ke:</b> ${new_sl:,.4f} (+{tp1_lock_r:.2f}R Net Profit Terkunci)"
                    f"{partial_note}\n"
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

        # Blueprint v3 C4: Legacy Flash Crash Exit removed.
        # Native exchange STOP_MARKET orders handle stop-loss protection directly.

        # ══════════════════════════════════════════════════════════════
        # PREDIKSI ROI (%) & PnL (USD / IDR) JIKA SENTUH TP1, TP2, DAN SL
        # ══════════════════════════════════════════════════════════════
        try:
            _margin_usd = float(pos_usd if pos_usd > 0 else 2.96)
            _margin_idr = float(pos_idr if pos_idr > 0 else _margin_usd * fx_rate)
            _lev = float(leverage if leverage > 0 else 20.0)
            _tp2_px = float(pos.get("take_profit_2") or tp or (entry_price * (1.024 if direction == "LONG" else 0.976)))
            _tp1_px = float(pos.get("take_profit_1") or (entry_price + 0.55 * abs(entry_price - init_sl) * (1.0 if direction == "LONG" else -1.0)))
            _sl_px = float(sl if sl > 0 else (init_sl if init_sl > 0 else entry_price * (0.988 if direction == "LONG" else 1.012)))
            _dir_sign = 1.0 if direction == "LONG" else -1.0

            def _calc_target_metrics(target_px: float):
                if entry_price <= 0 or target_px <= 0:
                    return {"price": 0.0, "move_pct": 0.0, "roi_pct": 0.0, "pnl_usd": 0.0, "pnl_idr": 0}
                move_pct = _dir_sign * ((target_px - entry_price) / entry_price) * 100.0
                roi_pct = move_pct * _lev
                t_pnl_usd = (roi_pct / 100.0) * _margin_usd
                t_pnl_idr = round((roi_pct / 100.0) * _margin_idr)
                return {
                    "price": round(target_px, 6),
                    "move_pct": round(move_pct, 3),
                    "roi_pct": round(roi_pct, 2),
                    "pnl_usd": round(t_pnl_usd, 2),
                    "pnl_idr": int(t_pnl_idr),
                }

            _tp1_m = _calc_target_metrics(_tp1_px)
            _tp2_m = _calc_target_metrics(_tp2_px)
            _sl_m = _calc_target_metrics(_sl_px)
            _lock_sl_px = round(entry_price * (1.0 + 0.38 * sl_dist_pct * _dir_sign), 6)
            _lock_sl_m = _calc_target_metrics(_lock_sl_px)

            pos["take_profit_1"] = _tp1_m["price"]
            pos["take_profit_2"] = _tp2_m["price"]
            pos["tp1_roi_pct"] = _tp1_m["roi_pct"]
            pos["tp1_pnl_usd"] = _tp1_m["pnl_usd"]
            pos["tp1_pnl_idr"] = _tp1_m["pnl_idr"]
            pos["tp2_roi_pct"] = _tp2_m["roi_pct"]
            pos["tp2_pnl_usd"] = _tp2_m["pnl_usd"]
            pos["tp2_pnl_idr"] = _tp2_m["pnl_idr"]
            pos["sl_roi_pct"] = _sl_m["roi_pct"]
            pos["sl_pnl_usd"] = _sl_m["pnl_usd"]
            pos["sl_pnl_idr"] = _sl_m["pnl_idr"]
            pos["is_sl_in_profit"] = bool(_sl_m["roi_pct"] > 0)
            pos["roi_pnl_projection"] = {
                "margin_usd": round(_margin_usd, 2),
                "margin_idr": int(round(_margin_idr)),
                "leverage": int(_lev),
                "notional_usd": round(_margin_usd * _lev, 2),
                "notional_idr": int(round(_margin_idr * _lev)),
                "if_hit_tp1": _tp1_m,
                "if_hit_tp2": _tp2_m,
                "if_hit_sl": _sl_m,
                "after_tp1_locked_sl": _lock_sl_m,
                "is_sl_in_profit": bool(_sl_m["roi_pct"] > 0),
            }
        except Exception:
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


        # C6 Fix: For Binance positions, let Binance exchange-side STOP_MARKET orders handle execution.
        # Only allow local emergency close if position has been open > 300s AND exchange SL is confirmed MISSING.
        time_since_open_sec = 0.0
        open_time_str = pos.get("opened_at") or pos.get("entry_time") or ""
        if open_time_str:
            try:
                from datetime import timezone as _tz
                open_dt = datetime.fromisoformat(open_time_str.replace(" UTC", "+00:00").replace("Z", "+00:00"))
                time_since_open_sec = (datetime.now(_tz.utc) - open_dt.astimezone(_tz.utc)).total_seconds()
            except Exception:
                time_since_open_sec = 0.0

        sl_state_upper = str(pos.get("sl_state") or "").upper()
        allow_local_tp_sl_fallback = (not is_binance_pos) or (sl_state_upper != "CONFIRMED")

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
        atomic_write_json(POSITIONS_FILE, positions)

    # T9.1 / T9.3: Write heartbeat.json atomically for watchdog & /health diagnostics
    try:
        hb_path = os.path.join(RESULTS_DIR, "heartbeat.json")
        atomic_write_json(hb_path, {
            "timestamp": time.time(),
            "utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "open_positions": len([p for p in positions if p.get("status") == "OPEN"]),
            "ws_active": bool(_WS_WORKER_STARTED),
            "status": "HEALTHY",
        })
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
    avail_usdt = float(state.get("binance_available_balance_usdt", 0.0))
    total_usdt = float(state.get("binance_wallet_balance_usdt", 0.0))
    
    if bn_client:
        try:
            bal = bn_client.get_balance()
            if isinstance(bal, dict) and not bal.get("isError") and "total_wallet_balance" in bal:
                avail_usdt = float(bal.get("available_balance", 0))
                total_usdt = float(bal.get("total_wallet_balance", 0))
                state["binance_wallet_balance_usdt"] = round(total_usdt, 4)
                state["binance_available_balance_usdt"] = round(avail_usdt, 4)
                state["binance_unrealized_pnl_usdt"] = round(float(bal.get("cross_unrealized_pnl", 0)), 4)
                save_state()
            
            # Live sync active positions directly from Binance Futures
            live_pos = bn_client.get_positions()
            if isinstance(live_pos, list):
                live_symbols = set()
                for lp in live_pos:
                    amt = abs(float(lp.get("position_amount", lp.get("positionAmt", 0))))
                    if amt > 0:
                        live_symbols.add(lp.get("symbol", ""))

                valid_open_pos = []
                dirty = False
                for p in positions:
                    if p.get("status") == "OPEN":
                        bp = p.get("binance_pair") or p.get("symbol", "").replace("-USD", "USDT")
                        if bp not in live_symbols:
                            p["status"] = "CLOSED_SYNCED"
                            p["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                            p["close_reason"] = "POSITION_NO_LONGER_ACTIVE_ON_EXCHANGE"
                            dirty = True
                            print(f"[GUARD] 🧹 Zombie position cleared for {bp} (not active on Binance)", flush=True)
                        else:
                            valid_open_pos.append(p)

                for lp in live_pos:
                    amt = abs(float(lp.get("position_amount", lp.get("positionAmt", 0))))
                    if amt > 0:
                        pair_sym = lp.get("symbol", "")
                        if not any(p.get("binance_pair") == pair_sym or p.get("symbol", "").replace("-USD", "USDT") == pair_sym for p in valid_open_pos):
                            new_p = _build_synced_binance_pos(lp, bn_client, get_fx_info()["usd_idr"])
                            valid_open_pos.append(new_p)
                            positions.append(new_p)
                            dirty = True

                open_pos = valid_open_pos
                if dirty:
                    atomic_write_json(POSITIONS_FILE, positions)
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

    # T7.5: Check HardRiskEngine Circuit Breaker & Max Daily Trades
    if not should_pause:
        try:
            cfg_g = _get_config()
            r_eng = load_hard_risk_engine(cfg_g, current_equity=total_usdt if total_usdt > 0 else None)
            max_dt = int(cfg_g.get("max_daily_trades", 10) or 10)
            if r_eng.is_circuit_breaker_active():
                should_pause = True
                reason = f"HARD RISK CIRCUIT BREAKER AKTIF ({r_eng.breaker_reason}) — entry baru ditahan otomatis."
            elif getattr(r_eng, "_daily_trades_count", 0) >= max_dt:
                should_pause = True
                reason = f"BATAS TRADE HARIAN TERCAPAI ({r_eng._daily_trades_count}/{max_dt}) — berhenti sampai 00:00 UTC."
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
        atomic_write_json(QUICK_SCREEN_FILE, screen_data)
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

    for coin in screen_pool:
        pair = coin.get("pair", "")
        sym = coin.get("symbol", pair.replace("USDT", "-USD"))
        change_24h = abs(float(coin.get("price_change_24h_pct", 0) or 0))
        vol_usd = float(coin.get("volume_24h_usd", 0) or 0)
        opp_score = float(coin.get("opportunity_score", 0) or 0)
        funding_abs = abs(float(coin.get("funding_rate", coin.get("lastFundingRate", 0)) or 0))

        # Quantitative Opportunity Scoring (Squeeze/Pullback/Funding + Liquidity, avoiding blown-out chases)
        score = 0.0

        # 1. Liquidity & Depth Proxy (institutional futures volume)
        if vol_usd > 150_000_000:
            score += 2.0
        elif vol_usd > 35_000_000:
            score += 1.2

        # 2. Constructive volatility / pullback vs overextended FOMO chase
        if 1.2 <= change_24h <= 6.5:
            score += 2.0
        elif 0.4 <= change_24h < 1.2:
            score += 1.2  # Squeeze coiling candidate
        elif change_24h > 8.5:
            score -= 1.5  # Penalize late vertical exhaustion chase

        # 3. Pre-ranker opportunity composite
        if opp_score >= 70:
            score += 2.0
        elif opp_score >= 55:
            score += 1.0

        # 4. Crowded funding squeeze potential
        if funding_abs >= 0.0003:
            score += 1.5

        # 5. Modest anchor liquidity bonus for CORE futures (no unconditional bypass!)
        if sym.upper() in core_symbols:
            score += 0.8

        if score >= 2.0:
            candidates.append((score, opp_score, coin))

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    final = [c for _, _, c in candidates[:max_ai_coins]]

    print(
        f"[PRE-FILTER] {len(screen_pool)} koin eligible di-screen -> {len(final)} setup berkualitas lolos (tanpa paksa flat-core) -> AI pipeline",
        flush=True,
    )
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

    # Gate teknikal + T0.7 minNotional filter -> max N koin untuk AI
    scan_list = _technical_pre_filter(
        all_candidates,
        max_ai_coins=max_coins,
        available_balance_usdt=guard.get("available_usdt"),
    )
    try:
        from strategies.bandit_allocator import ContextualThompsonBandit
        if scan_list:
            bandit = ContextualThompsonBandit()
            ranked_b = bandit.rank_candidates(scan_list, regime=regime)
            if isinstance(ranked_b, list) and len(ranked_b) == len(scan_list):
                scan_list = ranked_b
    except Exception:
        pass

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
        if not sync_control_flags_from_disk():
            print("[FULL SCAN] ⏸️ Paused by user mid-cycle. Halting remaining coin scans immediately.", flush=True)
            break
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

        # Strategy Auto-Degradation Gate: if setup demoted to SHADOW_ONLY, block real capital
        if is_trade_approved and os.path.exists(DEGRADED_STRAT_FILE):
            try:
                with open(DEGRADED_STRAT_FILE, "r", encoding="utf-8") as df:
                    deg_map = json.load(df) or {}
                if bool((deg_map.get(setup) or {}).get("degraded")):
                    is_trade_approved = False
                    status = "STRATEGY_DEMOTED_SHADOW_ONLY"
                    print(f"[AUTO-DEGRADATION] 🛡️ {sym} setup '{setup}' sedang SHADOW_ONLY ({deg_map[setup].get('reason')})", flush=True)
            except Exception:
                pass

        # BIDIRECTIONAL BTC GUARD (Blueprint T3.1):
        # 1. Batalkan sinyal LONG altcoin jika BTC sedang dump tajam
        # 2. Batalkan sinyal SHORT altcoin jika BTC sedang pump tajam (anti short-squeeze)
        candidate_dir = com_dir if com_dir in ("LONG", "SHORT") else fc.get("direction", "NONE")
        if is_trade_approved and candidate_dir in ("LONG", "SHORT") and sym not in ("BTC-USD", "BTCUSDT"):
            try:
                from market_data import get_market_indicators_fast
                btc_data = get_market_indicators_fast("BTCUSDT")
                if isinstance(btc_data, dict):
                    btc_rsi = float(btc_data.get("rsi_14") or 50.0)
                    btc_p = float(btc_data.get("current_price") or 0.0)
                    btc_e20 = float(btc_data.get("ema_20") or 0.0)
                    btc_e9 = float(btc_data.get("ema_9") or 0.0)
                    btc_chg4h = float(btc_data.get("change_4h_pct") or 0.0)
                    if candidate_dir == "LONG" and (btc_rsi < 40.0 or (btc_p < btc_e20 and btc_e9 < btc_e20 and btc_chg4h < -1.5)):
                        is_trade_approved = False
                        status = "REJECTED_BTC_DUMP"
                        print(f"[BTC GUARD] 🛡️ Altcoin LONG di {sym} DIBATALKAN: BTC sedang dump (RSI: {btc_rsi:.1f}, 4h: {btc_chg4h:+.2f}%)", flush=True)
                    elif candidate_dir == "SHORT" and (btc_rsi > 62.0 or (btc_p > btc_e20 and btc_e9 > btc_e20 and btc_chg4h > 1.5)):
                        is_trade_approved = False
                        status = "REJECTED_BTC_PUMP"
                        print(f"[BTC GUARD] 🛡️ Altcoin SHORT di {sym} DIBATALKAN: BTC sedang pump kuat (RSI: {btc_rsi:.1f}, 4h: {btc_chg4h:+.2f}%)", flush=True)
            except Exception as btc_err:
                print(f"[BTC GUARD] ⚠️ Error evaluating BTC trend: {btc_err}", flush=True)

        _plan_sig = (res.get("layer3_plan") or {}) if isinstance(res, dict) else {}
        _entry_sig = float(fc.get("entry_price") or _plan_sig.get("entry_price") or 0)
        _sl_sig = float(fc.get("stop_loss") or _plan_sig.get("stop_loss") or 0)
        _tp1_sig = float(fc.get("take_profit_1") or _plan_sig.get("take_profit_1") or 0)
        _tp2_sig = float(fc.get("take_profit_2") or fc.get("take_profit") or _plan_sig.get("take_profit_2") or _plan_sig.get("take_profit") or _tp1_sig or 0)

        sig_entry = {
            "symbol": sym,
            "binance_pair": pair,
            "name": name,
            "tier": tier,
            "status": "APPROVED" if is_trade_approved else status,
            "confidence": max(conf, com_conf),
            "confidence_pct": max(conf, com_conf),
            "direction": com_dir if com_dir in ("LONG", "SHORT") else fc.get("direction", "NONE"),
            "setup": setup,
            "setup_name": setup,
            "entry_price": _entry_sig,
            "stop_loss": _sl_sig,
            "take_profit": _tp2_sig,
            "take_profit_1": _tp1_sig,
            "take_profit_2": _tp2_sig,
            "committee_approved": com_approved,
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
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

            _ns_meta = fc.get("neuro_symbolic_3brain") or (res.get("neuro_symbolic_3brain") if isinstance(res, dict) else {}) or {}
            _mp_meta = (res.get("math_proof") if isinstance(res, dict) else None) or {}
            _order_type_exec = (fc.get("order_type") or _plan_sig.get("order_type") or cfg.get("order_type", "MAKER_FIRST_GTX")).upper()

            exec_plan = {
                "symbol": sym,
                "binance_pair": pair,
                "direction": final_dir,
                "action": final_dir,
                "confidence_score": max(conf, com_conf),
                "setup_name": setup,
                "regime": (_mp_meta.get("statistical_regime") if isinstance(_mp_meta, dict) else None) or regime,
                "entry_price": trade_params.get("entry_price") or fc.get("entry_price"),
                "position_size_idr": budget_allocated,
                "leverage": leverage_allocated,
                "take_profit_1": trade_params.get("tp1_price") or fc.get("take_profit_1"),
                "take_profit_2": trade_params.get("tp2_price") or fc.get("take_profit_2"),
                "take_profit": trade_params.get("tp2_price") or fc.get("take_profit"),
                "stop_loss": trade_params.get("sl_price") or fc.get("stop_loss"),
                "margin_type": "ISOLATED",
                "order_type": _order_type_exec,
                "math_proof": _mp_meta,
                "p_quant_ml": _ns_meta.get("brain1_tabular_ml_prob"),
                "p_knn": _ns_meta.get("brain2_episodic_knn_prob"),
                "p_llm": _ns_meta.get("brain3_llm_meta_prob"),
                "calibrated_prob": fc.get("calibrated_prob"),
                "conformal_set": fc.get("conformal_set"),
                "quant_feature_vector": fc.get("_quant_feature_vector"),
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
                tp1_val = float(exec_plan.get("take_profit_1") or pos.get("take_profit_1") or 0)
                tp_val = float(exec_plan.get("take_profit_2") or exec_plan.get("take_profit") or tp1_val or 0)
                sl_val = float(exec_plan.get("stop_loss") or pos.get("stop_loss") or 0)
                ent_val = float(pos.get("entry_price") or exec_plan.get("entry_price") or 0)
                lev_val = 20
                d_s = -1.0 if final_dir == "SHORT" else 1.0
                tp1_roi = round(d_s * ((tp1_val - ent_val) / ent_val) * lev_val * 100.0, 2) if (ent_val > 0 and tp1_val > 0) else 13.2
                tp2_roi = round(d_s * ((tp_val - ent_val) / ent_val) * lev_val * 100.0, 2) if (ent_val > 0 and tp_val > 0) else 48.0
                sl_roi = round(d_s * ((sl_val - ent_val) / ent_val) * lev_val * 100.0, 2) if (ent_val > 0 and sl_val > 0) else -24.0
                tp1_pnl_idr = int(round((tp1_roi / 100.0) * pos_idr))
                tp2_pnl_idr = int(round((tp2_roi / 100.0) * pos_idr))
                sl_pnl_idr = int(round((sl_roi / 100.0) * pos_idr))

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
                    f"🚨 <b>PYROFUEL // SNIPER HYBRID MATH+AI TRADE EXECUTED!</b>\n\n"
                    f"💎 <b>Aset:</b> <code>{pair}</code> ({name})\n"
                    f"🎯 <b>Arah:</b> <b>{final_dir}</b> (Hybrid Confidence: <b>{exec_plan['confidence_score']}%</b>)\n"
                    f"────────────────────────\n"
                    f"⚙️ <b>Parameters & Prediksi ROI/PnL:</b>\n"
                    f"   📊 Leverage: <b>{lev_val}x ISOLATED (Fixed)</b>\n"
                    f"   💰 Modal Margin: <b>${pos_usd:.2f} USDT</b> (~Rp {pos_idr:,})\n"
                    f"   📍 Entry: ${ent_val:,.4f}\n"
                    f"   🎯 Hit TP1 Lock (+0.55R @ ${tp1_val:,.4f}): <b>+{tp1_roi:.1f}% ROI (+Rp {tp1_pnl_idr:,})</b>\n"
                    f"   🚀 Hit Full TP2 (@ ${tp_val:,.4f}): <b>+{tp2_roi:.1f}% ROI (+Rp {tp2_pnl_idr:,})</b>\n"
                    f"   🛑 Hit Stop Loss (@ ${sl_val:,.4f}): <b>{sl_roi:.1f}% ROI (-Rp {abs(sl_pnl_idr):,})</b>\n"
                    f"────────────────────────\n"
                    f"{eta_section}\n"
                    f"────────────────────────\n"
                    f"🏛️ <b>Kolaborasi Matematika + Multi-Agent AI:</b>\n"
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
            if _entry_sig > 0 and _sl_sig > 0 and _tp2_sig > 0 and fc.get("direction") in ("LONG", "SHORT"):
                try:
                    from shadow.engine import ShadowEngine
                    ShadowEngine().register_candidate({
                        "symbol": sym,
                        "strategy_id": setup,
                        "regime": regime,
                        "direction": fc.get("direction"),
                        "entry_price": _entry_sig,
                        "sl_price": _sl_sig,
                        "tp_price": _tp2_sig,
                        "ai_decision": "SKIP",
                        "p_cal": fc.get("calibrated_prob") or (float(conf or 50) / 100.0),
                    }, ai_decision="SKIP", skip_reason=reason_short)
                except Exception:
                    pass

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
        atomic_write_json(UNIVERSE_FILE, universe_data)
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
    
    load_state()
    bn_client = get_binance_client()
    if bn_client:
        try:
            _start_realtime_ws_worker(bn_client)
        except Exception:
            pass
        try:
            bal = bn_client.get_balance()
            if isinstance(bal, dict) and not bal.get("isError") and "total_wallet_balance" in bal:
                usdt_bal = float(bal.get("total_wallet_balance", 0))
                avail_bal = float(bal.get("available_balance", usdt_bal))
                state["binance_wallet_balance_usdt"] = round(usdt_bal, 4)
                state["binance_available_balance_usdt"] = round(avail_bal, 4)
                save_state()
                print(f"[*] ✅ Binance Futures Engine LIVE! Wallet balance: ${usdt_bal:.2f} USDT (Available: ${avail_bal:.2f})", flush=True)
            else:
                usdt_bal = float(state.get("binance_wallet_balance_usdt", 0.0))
                print(f"[*] ✅ Binance Futures Engine Initialized (Cached Wallet: ${usdt_bal:.2f} USDT)", flush=True)
        except Exception as e:
            print(f"[*] ⚠️ Binance Futures check warning: {e}", flush=True)
    else:
        print(f"[*] ⚠️ Binance Futures not configured in .env", flush=True)

    last_full_scan = 0
    last_quick_scan = 0
    last_pause_monitor_ts = 0
    was_in_all_in_mode = False
    was_paused_by_user = not sync_control_flags_from_disk()
    if was_paused_by_user:
        print("[*] Autonomous trader is currently PAUSED (waiting for resume signal)...", flush=True)

    while True:
        try:
            is_active = sync_control_flags_from_disk()
            if not is_active:
                if not was_paused_by_user:
                    was_paused_by_user = True
                    state["status"] = "PAUSED"
                    save_state()
                    print("[*] Autonomous trader PAUSED by user (active position SL supervision continues).", flush=True)
                now_pause = time.time()
                if now_pause - last_pause_monitor_ts >= 8:
                    last_pause_monitor_ts = now_pause
                    try:
                        guard = check_wallet_and_position_guard()
                        monitor_and_update_positions()
                        state["all_in_monitoring_mode"] = bool(guard.get("pause_scanning"))
                        state["all_in_focus_positions"] = [p.get("symbol") for p in guard.get("open_positions", [])]
                        save_state()
                    except Exception as pe:
                        print(f"[PAUSE MONITOR NOTICE] {pe}", flush=True)
                time.sleep(2)
                continue
            elif was_paused_by_user:
                was_paused_by_user = False
                state["status"] = "RUNNING"
                print("[*] Autonomous trader RESUMED by user! Triggering immediate scan cycle...", flush=True)
                last_full_scan = 0
                last_quick_scan = 0
            
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
                
                # In all-in mode, skip scanning! Focus 100% on the open position with <50ms WS wake-up.
                _WS_WAKEUP_EVENT.wait(timeout=8)
                _WS_WAKEUP_EVENT.clear()
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
                
                _WS_WAKEUP_EVENT.wait(timeout=10)  # Wakes immediately on UserDataStream WS fill/algo event
                _WS_WAKEUP_EVENT.clear()
            
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
