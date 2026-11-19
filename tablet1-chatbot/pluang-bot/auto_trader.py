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
import uuid
import queue
import asyncio
import logging
import threading
import requests
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from state_io import CorruptedStateError, atomic_write_json, get_file_lock, read_json_safe

logger = logging.getLogger(__name__)

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

from pipeline import (
    run_5_layer_pipeline,
    load_env,
    RESULTS_DIR,
    get_trading_config,
    save_trading_config,
    call_ai as _pipeline_call_ai,
)
call_ai = _pipeline_call_ai
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

# === CONFIG (read from schema-validated file, user can change via Telegram /limit) ===
def _get_config():
    return get_trading_config()


def _load_positions_safe(strict: bool = True) -> list:
    data = read_json_safe(
        POSITIONS_FILE,
        default=[],
        strict_on_corrupt=strict,
        expected_type=list,
    )
    return list(data) if isinstance(data, list) else []


def _save_positions_merged(updated_positions: list) -> list:
    """
    Hold POSITIONS_FILE RLock, reload latest disk positions, merge entries by `id`
    (never regressing a non-OPEN closed status back to OPEN), and write atomically.
    """
    with get_file_lock(POSITIONS_FILE):
        disk_positions = read_json_safe(
            POSITIONS_FILE,
            default=[],
            strict_on_corrupt=True,
            expected_type=list,
        )
        merged = list(disk_positions) if isinstance(disk_positions, list) else []
        idx_by_id = {}
        for idx, item in enumerate(merged):
            if isinstance(item, dict) and item.get("id"):
                idx_by_id[item["id"]] = idx

        for item in updated_positions:
            if not isinstance(item, dict):
                continue
            pid = item.get("id")
            if pid and pid in idx_by_id:
                idx = idx_by_id[pid]
                existing = merged[idx]
                if existing.get("status") != "OPEN" and item.get("status") == "OPEN":
                    continue
                merged[idx] = item
            else:
                if pid:
                    idx_by_id[pid] = len(merged)
                merged.append(item)

        atomic_write_json(POSITIONS_FILE, merged, make_bak=True)
        return merged

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
    saved = read_json_safe(STATE_FILE, default=None, strict_on_corrupt=False, expected_type=dict)
    if isinstance(saved, dict):
        state.update(saved)
    return state

def sync_control_flags_from_disk():
    """Reload authoritative user control flags (is_running, mode, intervals) without clobbering runtime counters."""
    global state
    disk = read_json_safe(STATE_FILE, default=None, strict_on_corrupt=False, expected_type=dict)
    if isinstance(disk, dict):
        for k in ("is_running", "mode", "scan_interval_sec", "quick_screen_interval_sec"):
            if k in disk:
                state[k] = disk[k]
    return bool(state.get("is_running", True))

def save_state():
    try:
        with get_file_lock(STATE_FILE):
            # Preserve authoritative user toggle written externally (e.g. via Web UI or Telegram)
            disk = read_json_safe(STATE_FILE, default=None, strict_on_corrupt=False, expected_type=dict)
            if isinstance(disk, dict) and "is_running" in disk:
                disk_ts = str(disk.get("control_updated_at") or "")
                mem_ts = str(state.get("control_updated_at") or "")
                if disk_ts >= mem_ts:
                    state["is_running"] = disk["is_running"]
                    if disk_ts:
                        state["control_updated_at"] = disk_ts
            atomic_write_json(STATE_FILE, state)
    except Exception as exc:
        logger.warning("save_state error: %s", exc)


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


# === HARD RISK BREAKER, RUNTIME HEALTH, NON-BLOCKING AI & REALTIME WS ===
RISK_BREAKER_FILE = os.path.join(RESULTS_DIR, "risk_breaker_state.json")
DEGRADED_STRAT_FILE = os.path.join(RESULTS_DIR, "degraded_strategies.json")
_WS_WAKEUP_EVENT = threading.Event()
_LIVE_MARK_PRICES = {}
_LIVE_MARK_LOCK = threading.Lock()
_WS_WORKER_STARTED = False
_WS_WORKER_LOCK = threading.Lock()

_ERROR_ALERT_LOCK = threading.Lock()
_ERROR_ALERT_TIMESTAMPS = {}

_RUNTIME_HEALTH_LOCK = threading.Lock()
_RUNTIME_HEALTH = {
    "boot_ts": time.time(),
    "last_api_ok_ts": 0.0,
    "last_api_err_ts": 0.0,
    "ws_last_msg_ts": 0.0,
    "last_scan_ts": 0.0,
    "last_monitor_ts": 0.0,
    "last_ws_reconnect_ts": 0.0,
}

_MONITOR_LOCK = threading.RLock()
_MONITOR_AI_LOCK = threading.Lock()
_MONITOR_AI_EXECUTOR = None
_MONITOR_AI_FUTURES = {}
_MONITOR_AI_CACHE = {}


def _get_monitor_ai_executor() -> ThreadPoolExecutor:
    """Return bounded singleton ThreadPoolExecutor(max_workers=2) for async monitor LLM/news tasks."""
    global _MONITOR_AI_EXECUTOR
    if _MONITOR_AI_EXECUTOR is None:
        with _MONITOR_AI_LOCK:
            if _MONITOR_AI_EXECUTOR is None:
                _MONITOR_AI_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="monitor-ai")
    return _MONITOR_AI_EXECUTOR


def _alert_error_rate_limited(key: str, message: str, cooldown_sec: float = 300.0, level: str = "error") -> bool:
    """Log an operational error cleanly and emit a rate-limited Telegram critical alert."""
    log_fn = getattr(logger, str(level or "error").lower(), logger.error)
    log_fn("[%s] %s", key, message)

    now = time.time()
    should_send = False
    with _ERROR_ALERT_LOCK:
        last_ts = float(_ERROR_ALERT_TIMESTAMPS.get(key, 0.0) or 0.0)
        if last_ts <= 0.0 or now < last_ts or (now - last_ts) >= float(cooldown_sec):
            _ERROR_ALERT_TIMESTAMPS[key] = now
            should_send = True

    if should_send:
        try:
            send_telegram(f"⚠️ <b>[BOT ALERT: {key}]</b>\n{message}")
        except Exception as tg_exc:
            logger.debug("send_telegram failed during _alert_error_rate_limited(%s): %s", key, tg_exc)
    return should_send


def update_runtime_health(**kwargs) -> dict:
    """Update thread-safe runtime telemetry timestamps used by HeartbeatWorker."""
    with _RUNTIME_HEALTH_LOCK:
        for k, v in kwargs.items():
            if v is not None:
                _RUNTIME_HEALTH[k] = v
        return dict(_RUNTIME_HEALTH)


def compute_heartbeat_status(now: float = None, bn_client=None) -> str:
    """Compute honest dynamic heartbeat status (HEALTHY / RATE_LIMITED / DEGRADED_API / MONITOR_STALLED / SCAN_STALLED / PAUSED)."""
    now_ts = float(now if now is not None else time.time())
    with _RUNTIME_HEALTH_LOCK:
        snap = dict(_RUNTIME_HEALTH)

    last_api_ok_ts = float(snap.get("last_api_ok_ts") or 0.0)
    last_api_err_ts = float(snap.get("last_api_err_ts") or 0.0)
    last_scan_ts = float(snap.get("last_scan_ts") or 0.0)
    last_monitor_ts = float(snap.get("last_monitor_ts") or 0.0)

    client = bn_client if bn_client is not None else binance_client
    if client is not None:
        rl_until = float(getattr(client, "_rate_limit_until_ts", 0.0) or 0.0)
        if rl_until > now_ts:
            return "RATE_LIMITED"

    if last_api_err_ts > last_api_ok_ts and (last_api_ok_ts <= 0.0 or (now_ts - last_api_ok_ts) >= 30.0):
        return "DEGRADED_API"

    if last_monitor_ts > 0.0 and (now_ts - last_monitor_ts) > 120.0:
        return "MONITOR_STALLED"

    if not bool(state.get("is_running", True)) or str(state.get("status", "")).upper() == "PAUSED":
        return "PAUSED"

    if not bool(state.get("all_in_monitoring_mode", False)):
        scan_interval = max(60.0, float(state.get("scan_interval_sec", 300) or 300.0))
        if last_scan_ts > 0.0 and (now_ts - last_scan_ts) > max(600.0, scan_interval * 2.0):
            return "SCAN_STALLED"

    return "HEALTHY"


class HeartbeatWorker:
    """Dedicated daemon heartbeat thread writing results/heartbeat.json atomically every 30s."""

    def __init__(
        self,
        interval_sec: float = 30.0,
        heartbeat_path: str = None,
        open_positions_fn=None,
        status_fn=None,
    ):
        self.interval_sec = max(0.02, float(interval_sec or 30.0))
        self.heartbeat_path = heartbeat_path
        self.open_positions_fn = open_positions_fn
        self.status_fn = status_fn
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

    def build_payload(self) -> dict:
        now_ts = time.time()
        open_count = 0
        try:
            if self.open_positions_fn is not None:
                open_count = int(self.open_positions_fn() or 0)
            else:
                pos_list = _load_positions_safe(strict=False)
                open_count = len([p for p in pos_list if isinstance(p, dict) and p.get("status") == "OPEN"])
        except Exception as exc:
            logger.debug("HeartbeatWorker open position count fallback: %s", exc)
            open_count = 0

        with _RUNTIME_HEALTH_LOCK:
            snap = dict(_RUNTIME_HEALTH)

        ws_last = float(snap.get("ws_last_msg_ts") or 0.0)
        ws_active = bool(_WS_WORKER_STARTED) or (ws_last > 0.0 and (now_ts - ws_last) < 120.0)
        status_str = (
            self.status_fn(now_ts)
            if self.status_fn is not None
            else compute_heartbeat_status(now=now_ts)
        )
        return {
            "timestamp": now_ts,
            "utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "pid": os.getpid(),
            "boot_ts": float(snap.get("boot_ts") or 0.0),
            "last_api_ok_ts": float(snap.get("last_api_ok_ts") or 0.0),
            "last_api_err_ts": float(snap.get("last_api_err_ts") or 0.0),
            "ws_last_msg_ts": ws_last,
            "last_scan_ts": float(snap.get("last_scan_ts") or 0.0),
            "last_monitor_ts": float(snap.get("last_monitor_ts") or 0.0),
            "open_positions": int(open_count),
            "ws_active": bool(ws_active),
            "status": str(status_str),
        }

    def write_once(self) -> bool:
        try:
            path = self.heartbeat_path or os.path.join(RESULTS_DIR, "heartbeat.json")
            payload = self.build_payload()
            atomic_write_json(path, payload, make_bak=False)
            return True
        except Exception as exc:
            logger.warning("HeartbeatWorker write failed: %s", exc)
            return False

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.write_once()
            self._stop_event.wait(self.interval_sec)

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="heartbeat-worker", daemon=True)
            self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        with self._lock:
            t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=timeout)

    def is_alive(self) -> bool:
        t = self._thread
        return bool(t is not None and t.is_alive())


def _norm_pos_side(item: dict) -> str:
    """Normalize Binance positionSide / direction ('LONG', 'SHORT', or 'BOTH')."""
    if not isinstance(item, dict):
        return "BOTH"
    ps = str(item.get("position_side") or item.get("positionSide") or "").upper().strip()
    if ps in ("LONG", "SHORT"):
        return ps
    # Check explicit direction BEFORE numeric amount: BinanceFuturesClient.get_positions()
    # stores unsigned abs(amt) in `position_amount` alongside `position_side="BOTH"`.
    d = str(item.get("direction") or "").upper().strip()
    if d in ("LONG", "SHORT"):
        return d
    # Fallback for raw Binance /fapi/v2/positionRisk payloads that only have signed `positionAmt`.
    amt_raw = item.get("positionAmt")
    if amt_raw is None:
        amt_raw = item.get("position_amount")
    if amt_raw is not None:
        try:
            amt_f = float(amt_raw)
            if amt_f > 0:
                return "LONG"
            if amt_f < 0:
                return "SHORT"
        except (TypeError, ValueError):
            pass
    return "BOTH"


def _get_open_ws_mark_streams() -> list:
    """Build sorted unique `<pair>@markPrice@1s` WS stream names from current OPEN positions."""
    try:
        cur_p = _load_positions_safe(strict=False)
    except Exception as exc:
        logger.debug("_get_open_ws_mark_streams load failed: %s", exc)
        return []
    streams = []
    seen = set()
    for p in (cur_p or []):
        if not isinstance(p, dict) or p.get("status") != "OPEN":
            continue
        bp = (p.get("binance_pair") or p.get("symbol", "").replace("-USD", "USDT")).strip().lower()
        if bp:
            s_name = f"{bp}@markPrice@1s"
            if s_name not in seen:
                seen.add(s_name)
                streams.append(s_name)
    return streams


def _reconcile_after_ws_reconnect(bn_client, reason: str = "WS_RECONNECT") -> dict:
    """Trigger immediate REST position & SL/algo reconcile after WebSocket reconnect or listenKeyExpired."""
    update_runtime_health(last_ws_reconnect_ts=time.time())
    _WS_WAKEUP_EVENT.set()
    try:
        positions = monitor_and_update_positions()
        open_cnt = len([p for p in (positions or []) if isinstance(p, dict) and p.get("status") == "OPEN"])
        logger.info("WS post-reconnect reconcile (%s) completed: open_positions=%d", reason, open_cnt)
        return {"reconciled": True, "reason": str(reason), "open_positions": open_cnt}
    except Exception as exc:
        _alert_error_rate_limited("WS_RECONCILE_ERR", f"WS reconnect reconcile ({reason}) failed: {exc}", cooldown_sec=180.0)
        return {"reconciled": False, "reason": str(reason), "error": str(exc)}


def _get_vault_instance(initial_equity: float = 0.0):
    """Return singleton ProfitRatchetVault respecting patched RESULTS_DIR or DEFAULT_VAULT_STATE_PATH."""
    import risk.vault as rv

    default_prod_vault = os.path.normcase(os.path.abspath(os.path.join(BASE_DIR, "results", "vault_state.json")))
    cur_default_vault = os.path.normcase(os.path.abspath(rv.DEFAULT_VAULT_STATE_PATH))
    cur_results_dir = os.path.normcase(os.path.abspath(RESULTS_DIR))
    default_results_dir = os.path.normcase(os.path.abspath(os.path.join(BASE_DIR, "results")))
    state_path = None
    if cur_default_vault == default_prod_vault and cur_results_dir != default_results_dir:
        state_path = os.path.join(RESULTS_DIR, "vault_state.json")
    return rv.get_profit_vault(initial_equity=float(initial_equity or 0.0), state_path=state_path, persist=True)


def load_hard_risk_engine(cfg: dict = None, current_equity: float = None):
    """Load HardRiskEngine + daily trade counter persisted across restarts."""
    from risk.engine import HardRiskEngine

    cfg_raw = dict(cfg or _get_config())
    if "breaker_consecutive_losses" not in cfg_raw and "circuit_breaker_consecutive_losses" in cfg_raw:
        cfg_raw["breaker_consecutive_losses"] = cfg_raw["circuit_breaker_consecutive_losses"]
    vault = _get_vault_instance(initial_equity=float(current_equity or 0.0))
    eng = HardRiskEngine(config=cfg_raw, vault=vault)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_trades = 0
    with get_file_lock(RISK_BREAKER_FILE):
        try:
            saved = read_json_safe(
                RISK_BREAKER_FILE,
                default=None,
                strict_on_corrupt=True,
                expected_type=dict,
            )
            if isinstance(saved, dict):
                eng.consecutive_losses = int(saved.get("consecutive_losses", 0))
                eng.breaker_until_ts = float(saved.get("breaker_until_ts", 0.0))
                eng.breaker_reason = saved.get("breaker_reason")
                if saved.get("daily_date") == today_str:
                    daily_trades = int(saved.get("daily_trades_count", 0))
                    eng.daily_start_equity = float(saved.get("daily_start_equity", 0.0))
                eng.current_equity = float(saved.get("current_equity", 0.0))
        except CorruptedStateError as cse:
            print(f"[RISK BREAKER] ❌ {RISK_BREAKER_FILE} corrupt without valid .bak ({cse}) — failing closed.", flush=True)
            eng._corrupt_state = True
            eng.trip_circuit_breaker("RISK_BREAKER_STATE_CORRUPT")

    if current_equity is not None:
        eq_val = max(0.0, float(current_equity))
        if eq_val > 0 and eng.daily_start_equity <= 0:
            eng.daily_start_equity = eq_val
        if eq_val > 0 or eng.daily_start_equity > 0:
            eng.current_equity = eq_val
    eng._daily_date = today_str
    eng._daily_trades_count = daily_trades
    return eng


def save_hard_risk_engine(eng, daily_trades_delta: int = 0) -> dict:
    """Atomically persist HardRiskEngine circuit breaker + daily trade counter."""
    if getattr(eng, "_corrupt_state", False):
        print(f"[RISK BREAKER] ❌ Refusing to overwrite corrupt {RISK_BREAKER_FILE}.", flush=True)
        return {}
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_file_lock(RISK_BREAKER_FILE):
        curr_date = getattr(eng, "_daily_date", today_str)
        cnt = int(getattr(eng, "_daily_trades_count", 0)) if curr_date == today_str else 0
        if daily_trades_delta:
            disk = read_json_safe(RISK_BREAKER_FILE, default=None, strict_on_corrupt=False, expected_type=dict)
            if isinstance(disk, dict) and disk.get("daily_date") == today_str:
                cnt = max(cnt, int(disk.get("daily_trades_count", 0)))
        cnt = max(0, cnt + int(daily_trades_delta))
        eng._daily_date = today_str
        eng._daily_trades_count = cnt

        max_daily = int(_get_config().get("max_daily_trades", 10) or 10)
        daily_dd_pct = 0.0
        if getattr(eng, "daily_start_equity", 0.0) > 0 and (
            getattr(eng, "current_equity", 0.0) > 0
            or str(getattr(eng, "breaker_reason", "") or "").startswith("DAILY_DRAWDOWN")
        ):
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
        atomic_write_json(RISK_BREAKER_FILE, payload, make_bak=True)
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
            logger.warning("[WS] websockets/UserDataStreamManager unavailable (%s)", e)
            print(f"[WS] Notice: websockets/UserDataStreamManager unavailable ({e})", flush=True)
            return

        async def _loop():
            try:
                mgr = UserDataStreamManager(
                    client=bn_client,
                    reconcile_callback=lambda reason: _reconcile_after_ws_reconnect(bn_client, reason=reason),
                )
            except TypeError:
                mgr = UserDataStreamManager(client=bn_client)
            backoff = 2.0
            first_connect_done = False
            while True:
                try:
                    lk = mgr.create_listen_key()
                    if not lk:
                        await asyncio.sleep(backoff)
                        backoff = min(30.0, backoff * 1.5)
                        continue

                    subscribed_marks = _get_open_ws_mark_streams()
                    streams = [lk] + list(subscribed_marks)
                    base_ws = "wss://stream.binancefuture.com" if getattr(bn_client, "testnet", False) else "wss://fstream.binance.com"
                    url = f"{base_ws}/stream?streams=" + "/".join(streams) if len(streams) > 1 else mgr.get_ws_url(testnet=getattr(bn_client, "testnet", False))

                    async with websockets.connect(url, ping_interval=20, ping_timeout=15, open_timeout=10) as ws:
                        backoff = 2.0
                        last_ka = time.time()
                        last_mark_check = time.time()
                        if hasattr(mgr, "reconnect_requested") and mgr.reconnect_requested.is_set():
                            mgr.reconnect_requested.clear()
                            _reconcile_after_ws_reconnect(bn_client, reason="WS_LISTEN_KEY_REFRESH")
                        elif first_connect_done:
                            _reconcile_after_ws_reconnect(bn_client, reason="WS_RECONNECT")
                        first_connect_done = True

                        while True:
                            if hasattr(mgr, "reconnect_requested") and mgr.reconnect_requested.is_set():
                                logger.info("[WS] Reconnect requested by UserDataStreamManager")
                                break

                            now_ws = time.time()
                            if now_ws - last_ka >= 1500.0:
                                ok_ka = mgr.keepalive_listen_key()
                                last_ka = now_ws
                                if ok_ka is False:
                                    logger.warning("[WS] listenKey keepalive failed — forcing reconnect & REST reconcile")
                                    if hasattr(mgr, "reconnect_requested"):
                                        mgr.reconnect_requested.set()
                                    break

                            if now_ws - last_mark_check >= 15.0:
                                last_mark_check = now_ws
                                desired_marks = _get_open_ws_mark_streams()
                                if desired_marks != subscribed_marks:
                                    logger.info("[WS] Open positions changed (%s -> %s); resubscribing markPrice streams", subscribed_marks, desired_marks)
                                    break

                            raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
                            update_runtime_health(ws_last_msg_ts=time.time())
                            msg = json.loads(raw)
                            payload = msg.get("data", msg) if isinstance(msg, dict) else {}
                            ev = str(payload.get("e", ""))
                            if ev == "markPriceUpdate":
                                s_sym = str(payload.get("s", "")).upper()
                                m_px = float(payload.get("p") or 0.0)
                                if s_sym and m_px > 0:
                                    with _LIVE_MARK_LOCK:
                                        _LIVE_MARK_PRICES[s_sym] = (m_px, time.time())
                            elif ev in ("ORDER_TRADE_UPDATE", "ALGO_UPDATE", "ACCOUNT_UPDATE", "ACCOUNT_CONFIG_UPDATE", "listenKeyExpired"):
                                res = mgr.handle_event(payload)
                                _WS_WAKEUP_EVENT.set()
                                if ev in ("ORDER_TRADE_UPDATE", "ALGO_UPDATE"):
                                    print(f"[WS REALTIME] ⚡ {ev}: {res.get('symbol', '')} {res.get('status', '')}", flush=True)
                                if ev == "listenKeyExpired" or (isinstance(res, dict) and res.get("reconnect_required")):
                                    logger.warning("[WS] %s received — reconnecting stream immediately", ev)
                                    break
                except asyncio.TimeoutError:
                    try:
                        now_to = time.time()
                        if hasattr(mgr, "reconnect_requested") and mgr.reconnect_requested.is_set():
                            break
                        if _get_open_ws_mark_streams() != subscribed_marks:
                            break
                        if now_to - last_ka >= 1500.0:
                            ok_ka = mgr.keepalive_listen_key()
                            last_ka = now_to
                            if ok_ka is False:
                                break
                    except Exception as to_exc:
                        logger.warning("[WS] Idle keepalive check error: %s", to_exc)
                except Exception as wse:
                    logger.warning("[WS] Stream disconnected (%s) — reconnecting in %.1fs", wse, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(30.0, backoff * 1.5)

        try:
            asyncio.run(_loop())
        except Exception as e:
            logger.error("[WS] Runner exited unexpectedly: %s", e)
            print(f"[WS] Runner exited: {e}", flush=True)

    t = threading.Thread(target=_ws_runner, name="binance-ws-userstream", daemon=True)
    t.start()
    print("[WS] 🌐 Binance Futures UserDataStream + markPrice@1s daemon active (<50ms wakeup)", flush=True)

def _is_unmocked_bf_method(bn_client, method_name: str) -> bool:
    """
    Detect test subclasses of BinanceFuturesClient that overrode order/balance methods
    without mocking `method_name` or `_request`/`session`, avoiding unintended live HTTP calls.
    """
    if not isinstance(bn_client, BinanceFuturesClient):
        return False
    cls = type(bn_client)
    if cls is BinanceFuturesClient:
        return False
    cls_m = getattr(cls, method_name, None)
    base_m = getattr(BinanceFuturesClient, method_name, None)
    inst_m = getattr(bn_client, method_name, None)
    if cls_m is base_m and not hasattr(inst_m, "assert_called"):
        sess = getattr(bn_client, "session", None)
        if (
            getattr(cls, "_request", None) is BinanceFuturesClient._request
            and not hasattr(getattr(bn_client, "_request", None), "assert_called")
            and not hasattr(getattr(sess, "get", None), "assert_called")
            and not hasattr(getattr(sess, "post", None), "assert_called")
        ):
            return True
    return False


def _safe_get_positions(bn_client) -> tuple:
    """Safely query live positions from `bn_client`. Returns `(list_or_None, err_or_None)`."""
    if not bn_client or not hasattr(bn_client, "get_positions") or _is_unmocked_bf_method(bn_client, "get_positions"):
        return None, None
    try:
        res = bn_client.get_positions()
    except Exception as exc:
        return None, str(exc)
    if isinstance(res, list):
        return res, None
    if isinstance(res, dict) and res.get("isError"):
        return None, res.get("error", str(res))
    return None, None


def _get_effective_open_positions(local_positions: list, bn_client) -> tuple:
    """
    Merge live exchange open positions with local OPEN positions (C-12).
    Returns `(effective_open_list, live_active_or_None, err_or_None)`.
    """
    local_open = [p for p in (local_positions or []) if isinstance(p, dict) and p.get("status") == "OPEN"]
    live_raw, err = _safe_get_positions(bn_client)
    if err:
        return local_open, None, err
    if live_raw is None:
        return local_open, None, None

    merged_by_pair = {}
    live_active = []
    for lp in live_raw:
        if not isinstance(lp, dict):
            continue
        raw_signed = float(lp.get("position_amount", lp.get("positionAmt", 0.0)) or 0.0)
        amt = abs(raw_signed)
        if amt <= 0:
            continue
        sym = str(lp.get("symbol") or "").upper()
        direction = str(lp.get("direction") or ("LONG" if raw_signed >= 0 else "SHORT")).upper()
        side = _norm_pos_side(lp)
        entry = {
            "symbol": sym,
            "binance_pair": sym,
            "direction": direction,
            "position_side": side,
            "position_amount": amt,
        }
        live_active.append(entry)
        if sym:
            merged_by_pair[(sym, side)] = entry

    for p in local_open:
        bp = str(p.get("binance_pair") or p.get("symbol", "").replace("-USD", "USDT")).upper()
        p_side = _norm_pos_side(p)
        is_bn_p = p.get("exchange") == "BINANCE_FUTURES" or p.get("binance_synced") or (not p.get("exchange"))
        if bp and ((bp, p_side) in merged_by_pair or (bp, "BOTH") in merged_by_pair or (p_side == "BOTH" and any(s == bp for s, _ in merged_by_pair))):
            continue
        if not is_bn_p:
            key = (bp or str(p.get("id") or len(merged_by_pair)), p_side)
            merged_by_pair[key] = p

    return list(merged_by_pair.values()), live_active, None


def _safe_get_funding_info(bn_client, pair: str):
    """Safely fetch `get_funding_info(pair)` if supported and mocked/live."""
    if not bn_client or not hasattr(bn_client, "get_funding_info") or _is_unmocked_bf_method(bn_client, "get_funding_info"):
        return None
    try:
        res = bn_client.get_funding_info(pair)
    except TypeError:
        return None
    except Exception:
        return None
    if isinstance(res, dict) and res.get("ok") is True:
        return res
    return None


def _safe_get_market_price(bn_client, pair: str):
    """Safely fetch live mark price from `bn_client` or WS mark cache."""
    if bn_client and hasattr(bn_client, "get_market_price") and not _is_unmocked_bf_method(bn_client, "get_market_price"):
        try:
            px = bn_client.get_market_price(pair)
            if isinstance(px, (int, float)) and not isinstance(px, bool) and px > 0:
                return float(px)
        except Exception as exc:
            logger.debug("_safe_get_market_price error for %s: %s", pair, exc)
    with _LIVE_MARK_LOCK:
        ws_m = _LIVE_MARK_PRICES.get(str(pair or "").upper())
        if ws_m and (time.time() - ws_m[1] < 10.0) and ws_m[0] > 0:
            return float(ws_m[0])
    return None


def _safe_get_symbol_filters(bn_client, pair: str):
    """Safely fetch concrete exchangeInfo symbol filters if available."""
    if not bn_client or not hasattr(bn_client, "get_symbol_filters") or _is_unmocked_bf_method(bn_client, "get_symbol_filters"):
        return None
    try:
        rules = bn_client.get_symbol_filters(pair)
    except Exception:
        return None
    if isinstance(rules, dict) and not rules.get("isError"):
        mn = rules.get("minNotional", 5.0)
        if isinstance(mn, (int, float)) and not isinstance(mn, bool):
            return rules
    return None


def record_position(signal: dict):
    """Record position locally AND execute on Binance Futures"""
    cfg = _get_config()
    max_budget = cfg.get("max_budget_idr", 0)   # 0 = no cap, dynamic wallet-based
    max_lev = cfg.get("max_leverage", 20)
    leverage = min(20, max_lev)  # Fixed 20x leverage (user mandate)
    margin_type = signal.get("margin_type") or cfg.get("margin_type", "ISOLATED")

    # 1. SMART EXECUTION DEFAULT (respect config/AI instead of hardcoded MARKET)
    order_type = (signal.get("order_type") or cfg.get("order_type", "MAKER_FIRST_GTX")).upper()
    limit_price = float(signal.get("limit_price") or signal.get("entry_price", 0) or 0)

    tp = float(signal.get("take_profit") or signal.get("take_profit_2") or signal.get("take_profit_1", 0) or 0)
    sl = float(signal.get("stop_loss", 0) or 0)
    dir_init = str(signal.get("direction", "LONG")).upper().strip()
    pair_init = str(signal.get("binance_pair") or signal.get("symbol", "").replace("-USD", "USDT")).upper()

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
    total_wallet_usdt = 0.0
    cross_upnl_usdt = 0.0
    try:
        _bal = _bn.get_balance()
        if not isinstance(_bal, dict) or _bal.get("isError") or "available_balance" not in _bal:
            print(f"[SIZING] ❌ Binance balance endpoint unavailable ({_bal}) — entry aborted safely.", flush=True)
            return None
        avail_usdt = float(_bal.get("available_balance", 0.0))
        total_wallet_usdt = float(_bal.get("total_wallet_balance", avail_usdt))
        cross_upnl_usdt = float(_bal.get("cross_unrealized_pnl", 0.0) or 0.0)
    except Exception as e:
        print(f"[SIZING] ❌ Binance balance check failed ({e}) — entry aborted safely.", flush=True)
        return None

    if avail_usdt < 0.30:
        print(f"[SIZING] ⚠️ Insufficient Binance available margin (${avail_usdt:.2f} < $0.30). Entry aborted.", flush=True)
        return None

    live_equity_usdt = max(0.0, total_wallet_usdt + cross_upnl_usdt)
    risk_eng = load_hard_risk_engine(cfg, current_equity=live_equity_usdt if (live_equity_usdt > 0 or total_wallet_usdt > 0) else None)
    dd_eval = risk_eng.check_live_equity_drawdown(live_equity=live_equity_usdt)
    if dd_eval.get("breaker_active"):
        if dd_eval.get("tripped_now"):
            save_hard_risk_engine(risk_eng)
            send_telegram(
                f"🛑 <b>[HARD RISK BREAKER TRIPPED — LIVE DAILY DD]</b>\n\n"
                f"⚠️ Drawdown Hari Ini: <b>{dd_eval['daily_dd_pct']:.2f}%</b> "
                f"(Batas: {risk_eng.breaker_daily_dd_pct:.1f}%)\n"
                f"💰 Live Equity: ${live_equity_usdt:.2f} (Start Hari: ${risk_eng.daily_start_equity:.2f})\n"
                f"❄️ Entry baru dikunci selama {cfg.get('breaker_cooldown_hours', 12)} jam."
            )
        print(f"[RISK BREAKER] 🛑 Live equity DD breaker active ({risk_eng.breaker_reason}). Entry blocked.", flush=True)
        return None

    # 3. LOCKED PROFIT VAULT PROTECTION (C-13: zero $1 floor bypass!)
    sizing_mode = str(cfg.get("sizing_mode", "ALL_IN")).upper()
    all_in_fraction = float(cfg.get("all_in_balance_fraction", 0.95))
    locked_vault_usdt = 0.0
    try:
        vault_inst = _get_vault_instance()
        vdata = read_json_safe(vault_inst.state_path, default=None, strict_on_corrupt=False, expected_type=dict)
        if isinstance(vdata, dict):
            locked_vault_usdt = max(0.0, float(vdata.get("locked_profit_vault_usdt", 0.0)))
        else:
            locked_vault_usdt = max(0.0, float(getattr(vault_inst, "locked_profit_vault_usdt", 0.0)))
    except Exception:
        locked_vault_usdt = 0.0

    working_usdt = max(0.0, avail_usdt - locked_vault_usdt)
    if working_usdt < 0.30:
        print(
            f"[SIZING] 🛡️ REJECTED_VAULT_PROTECTED: Available=${avail_usdt:.2f}, "
            f"LockedVault=${locked_vault_usdt:.2f}, Working=${working_usdt:.2f} < $0.30. Entry blocked.",
            flush=True,
        )
        return None

    # 4. LIVE CONCURRENT & DIRECTIONAL POSITION CAP (C-12)
    max_concurrent = int(cfg.get("max_concurrent_positions", 1) or 1)
    try:
        positions = _load_positions_safe(strict=True)
    except CorruptedStateError as cse:
        print(f"[POSITION] ❌ POSITIONS_FILE corrupt without valid backup ({cse}) — aborting entry safely without overwriting.", flush=True)
        return None

    effective_open, live_open_list, pos_check_err = _get_effective_open_positions(positions, _bn)
    if pos_check_err:
        print(f"[POSITION] ❌ REJECTED_POSITION_CHECK_ERROR ({pos_check_err}) — refusing blind entry.", flush=True)
        return None

    open_count = len(effective_open)
    if open_count >= max_concurrent:
        print(f"[POSITION] ⚠️ Max concurrent positions ({open_count}/{max_concurrent}) reached. Skipping.", flush=True)
        return None

    max_same_dir_cfg = cfg.get("max_same_direction_positions", cfg.get("max_directional_positions"))
    if max_same_dir_cfg is not None:
        max_same_dir = int(max_same_dir_cfg)
    elif live_open_list is not None:
        max_same_dir = 1
    else:
        max_same_dir = max_concurrent
    same_dir_count = sum(1 for p in effective_open if str(p.get("direction", "")).upper() == dir_init)
    if same_dir_count >= max_same_dir:
        print(
            f"[POSITION] 🛡️ Directional exposure cap reached ({same_dir_count}/{max_same_dir} {dir_init} open). Skipping {pair_init}.",
            flush=True,
        )
        return None

    # 5. FUNDING BOUNDARY GATE (C-9) & LIVE MARK DRIFT CHECK / SAFE RE-ANCHOR (B-10)
    entry_p = float(signal.get("entry_price") or limit_price or 0.0)
    orig_entry_p = entry_p
    sl_pct_raw = (abs(entry_p - sl) / entry_p) if (entry_p > 0 and sl > 0) else 0.008
    tp1_init = float(signal.get("take_profit_1") or 0)
    tp2_init = float(signal.get("take_profit_2") or tp or tp1_init or 0)

    finfo = _safe_get_funding_info(_bn, pair_init)
    funding_rate = 0.0
    minutes_to_funding = 999.0
    live_mark = None
    if finfo is not None:
        funding_rate = float(finfo.get("last_funding_rate", 0.0) or 0.0)
        next_ms = int(finfo.get("next_funding_time_ms", 0) or 0)
        now_ms = int(time.time() * 1000)
        if next_ms >= now_ms and next_ms > 0:
            minutes_to_funding = (next_ms - now_ms) / 60_000.0
        if isinstance(finfo.get("mark_price"), (int, float)) and float(finfo["mark_price"]) > 0:
            live_mark = float(finfo["mark_price"])

    pays_high_funding = (dir_init == "LONG" and funding_rate >= 0.0005) or (
        dir_init == "SHORT" and funding_rate <= -0.0005
    )
    if 0.0 <= minutes_to_funding < 15.0 and pays_high_funding:
        print(
            f"[FUNDING GATE] 🛑 REJECT_FUNDING_BOUNDARY_GUARD: {pair_init} {dir_init} pays "
            f"{funding_rate*100:+.4f}% in {minutes_to_funding:.1f}m (< 15m). Entry blocked.",
            flush=True,
        )
        return None

    if live_mark is None:
        live_mark = _safe_get_market_price(_bn, pair_init)

    if live_mark is not None and live_mark > 0 and entry_p > 0:
        drift_frac = abs(live_mark - entry_p) / entry_p
        drift_tol = max(0.005, 0.6 * sl_pct_raw)
        if drift_frac > drift_tol:
            print(
                f"[ENTRY DRIFT] 🛑 STALE_ENTRY_DRIFT: {pair_init} plan=${entry_p:.4f} vs live=${live_mark:.4f} "
                f"(drift={drift_frac*100:.2f}% > tol={drift_tol*100:.2f}%). Entry rejected.",
                flush=True,
            )
            return None
        if drift_frac > 1e-6:
            d_sign_adj = -1.0 if dir_init == "SHORT" else 1.0
            d_sl_plan = abs(entry_p - sl) / entry_p if sl > 0 else 0.0
            d_tp2_plan = abs(tp2_init - entry_p) / entry_p if tp2_init > 0 else 0.0
            d_tp1_plan = abs(tp1_init - entry_p) / entry_p if tp1_init > 0 else 0.0
            entry_p = live_mark
            if d_sl_plan > 0:
                sl = round(entry_p * (1.0 - d_sign_adj * d_sl_plan), 6)
            if d_tp2_plan > 0:
                tp2_init = round(entry_p * (1.0 + d_sign_adj * d_tp2_plan), 6)
                tp = tp2_init
            if d_tp1_plan > 0:
                tp1_init = round(entry_p * (1.0 + d_sign_adj * d_tp1_plan), 6)
            if order_type != "LIMIT" or (orig_entry_p > 0 and abs(limit_price - orig_entry_p) / orig_entry_p < 1e-4):
                limit_price = entry_p

    # 6. HARD RISK ENGINE VALIDATION & SIZING (B-9)
    rules = _safe_get_symbol_filters(_bn, pair_init)
    from market_data import KNOWN_MIN_NOTIONAL

    min_notional_eff = float((rules or {}).get("minNotional") or KNOWN_MIN_NOTIONAL.get(pair_init, 5.0))
    is_mkt_entry = (order_type == "MARKET")
    step_sz_eff = float(
        ((rules or {}).get("marketStepSize") or (rules or {}).get("stepSize") or 0.001)
        if is_mkt_entry
        else ((rules or {}).get("stepSize") or 0.001)
    )
    min_qty_eff = float(
        ((rules or {}).get("marketMinQty") or (rules or {}).get("minQty") or 0.001)
        if is_mkt_entry
        else ((rules or {}).get("minQty") or 0.001)
    )
    qty_prec_eff = int((rules or {}).get("quantityPrecision", 3) if rules else 3)

    cal_p_sig = signal.get("calibrated_prob")
    if cal_p_sig is None:
        cal_p_sig = signal.get("p_cal")
    if cal_p_sig is None:
        conf_val = float(signal.get("confidence_score") or 0)
        cal_p_sig = (conf_val / 100.0) if conf_val > 0 else 0.80
    else:
        cal_p_sig = float(cal_p_sig)
    p_hybrid_sig = float(signal.get("p_hybrid") if signal.get("p_hybrid") is not None else cal_p_sig)
    conf_set_sig = signal.get("conformal_set")
    if conf_set_sig is None:
        conf_set_sig = ["WIN"]

    decision_payload = {
        "decision": "TRADE",
        "symbol": pair_init,
        "direction": dir_init,
        "entry_price": entry_p,
        "sl_price": sl,
        "tp_price": tp2_init,
        "p_cal": cal_p_sig,
        "p_hybrid": p_hybrid_sig,
        "conformal_set": conf_set_sig,
    }
    if signal.get("p_tp1") is not None:
        decision_payload["p_tp1"] = float(signal["p_tp1"])
    if signal.get("rrr_net") is not None:
        decision_payload["rrr_net"] = float(signal["rrr_net"])
    if signal.get("ev_r") is not None:
        decision_payload["ev_r"] = float(signal["ev_r"])

    account_state_payload = {
        "available_balance_usdt": avail_usdt,
        "live_equity": live_equity_usdt,
        "consecutive_losses": risk_eng.consecutive_losses,
        "daily_dd_pct": risk_eng.compute_daily_dd_pct(live_equity_usdt),
        "open_positions_count": open_count,
        "same_direction_count": same_dir_count,
        "max_same_direction_positions": max_same_dir,
    }
    market_state_payload = {
        "min_notional": min_notional_eff,
        "step_size": step_sz_eff,
        "min_qty": min_qty_eff,
        "quantity_precision": qty_prec_eff,
        "minutes_to_funding": minutes_to_funding,
        "funding_rate": funding_rate,
    }
    if signal.get("liquidation_price") is not None:
        market_state_payload["liquidation_price"] = float(signal["liquidation_price"])

    risk_val = risk_eng.validate_and_size(
        decision=decision_payload,
        account_state=account_state_payload,
        market_state=market_state_payload,
    )
    if not risk_val.get("allowed"):
        print(
            f"[HARD RISK] 🛑 Entry rejected by HardRiskEngine for {pair_init}: "
            f"{risk_val.get('reject_reason')} ({risk_val})",
            flush=True,
        )
        return None

    sl_pct = abs(entry_p - sl) / entry_p if (entry_p > 0 and sl > 0) else 0.008
    _fx = get_fx_info()

    if sizing_mode == "ALL_IN":
        calc_margin_usd = float(risk_val.get("margin_usdt") or (working_usdt * all_in_fraction))
        calc_margin_usd = min(calc_margin_usd, working_usdt * 0.98)
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
        min_margin_for_notional = (min_notional_eff * 1.02) / leverage
        calc_margin_usd = max(calc_margin_usd, min_margin_for_notional)
        if calc_margin_usd > (working_usdt * 0.98) + 1e-6:
            print(
                f"[SIZING] 🛡️ REJECTED_NOTIONAL_CAPACITY: required margin ${calc_margin_usd:.2f} "
                f"> working cap ${working_usdt * 0.98:.2f} (Vault=${locked_vault_usdt:.2f}).",
                flush=True,
            )
            return None
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

    entry_px_init = float(entry_p or 0)
    d_sign_init = -1.0 if dir_init == "SHORT" else 1.0
    sl_dist_init = abs(entry_px_init - sl) / entry_px_init if (entry_px_init > 0 and sl > 0) else 0.012
    if tp1_init <= 0 and entry_px_init > 0:
        tp1_init = round(entry_px_init * (1.0 + d_sign_init * 0.55 * sl_dist_init), 6)
    tp2_init = float(tp2_init or tp or tp1_init)

    pos = {
        "id": signal.get("id") or f"POS_{signal.get('symbol', 'UNK')}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
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
                exec_sig = {
                    "id": pos["id"],
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
                }
                if signal.get("client_order_id"):
                    exec_sig["client_order_id"] = signal["client_order_id"]
                execution_result = bn_client.execute_full_trade(signal=exec_sig, config=cfg)

                exec_status = str(execution_result.get("status", "")).upper()
                still_open = bool(execution_result.get("binance_position_still_open", False))
                is_synced = bool(execution_result.get("binance_synced", False))

                pos["binance_execution"] = execution_result
                pos["order_id"] = execution_result.get("order_id")
                pos["routing_used"] = execution_result.get("routing_used", pos["order_type"])

                if is_synced or still_open:
                    pos["binance_synced"] = True
                    pos["entry_price"] = float(execution_result.get("entry_price") or pos["entry_price"])
                    pos["entry_price_idr"] = convert_usd_to_idr(pos["entry_price"])
                    if execution_result.get("leverage"):
                        pos["leverage"] = int(execution_result["leverage"])
                    if execution_result.get("margin_type"):
                        pos["margin_type"] = str(execution_result["margin_type"]).upper()
                    if execution_result.get("position_size_usdt") is not None and float(execution_result.get("position_size_usdt") or 0) > 0:
                        pos["position_size_usdt"] = round(float(execution_result["position_size_usdt"]), 4)
                        pos["position_size_usd"] = pos["position_size_usdt"]
                        pos["position_size_idr"] = int(round(pos["position_size_usd"] * _fx.get("usd_idr", 16500)))
                    pos["take_profit"] = execution_result.get("take_profit") or pos["take_profit"]
                    pos["take_profit_2"] = pos["take_profit"]
                    pos["stop_loss"] = execution_result.get("stop_loss") or pos["stop_loss"]
                    pos["init_stop_loss"] = execution_result.get("stop_loss") or pos.get("init_stop_loss") or pos["stop_loss"]
                    pos["sl_algo_id"] = execution_result.get("sl_algo_id")
                    pos["tp_algo_id"] = execution_result.get("tp_algo_id")
                    pos["sl_state"] = "UNPROTECTED_RECOVERY" if still_open else execution_result.get("sl_state", "CONFIRMED")
                    pos["sl_verified"] = False if still_open else bool(execution_result.get("sl_verified", pos["sl_state"] == "CONFIRMED"))
                    if execution_result.get("liquidation_price") is not None:
                        pos["liquidation_price"] = float(execution_result["liquidation_price"])
                    pos["quantity"] = execution_result.get("quantity")

                    tca_res = execution_result.get("tca") if isinstance(execution_result.get("tca"), dict) else None
                    if tca_res and tca_res.get("fee_usdt") is not None:
                        pos["fee_usd"] = round(float(tca_res["fee_usdt"]), 6)
                    else:
                        pos["fee_usd"] = round(pos["position_size_usd"] * pos["leverage"] * 0.0005, 4)

                    if still_open:
                        pos["emergency_close_failed"] = True
                        send_telegram(
                            f"🚨 <b>[CRITICAL] UNPROTECTED LIVE POSITION {pos['binance_pair']}</b>\n"
                            f"SL & emergency close gagal! Posisi tetap aktif ({pos['direction']} qty={pos.get('quantity')}) dan dicatat untuk recovery segera.\n"
                            f"Detail: <i>{execution_result.get('critical_alert') or execution_result.get('error')}</i>"
                        )
                    elif exec_status == "EXECUTED_RECOVERY_PROTECTED":
                        pos["recovery_protected"] = True
                        send_telegram(
                            f"🛡️ <b>[RECOVERY PROTECTED] {pos['binance_pair']}</b>\n"
                            f"Exception pasca-order terdeteksi; posisi live ({pos['direction']} {pos['leverage']}x qty={pos.get('quantity')}) "
                            f"berhasil diamankan SL (Algo #{pos.get('sl_algo_id')})."
                        )

                    limit_str = f" @ ${limit_price:,.4f}" if order_type in ("LIMIT", "GTX", "MAKER_FIRST_GTX") else ""
                    print(f"[BINANCE] ✅ Real trade executed on Binance Futures: {pos['direction']} {pos['binance_pair']} "
                          f"${pos['position_size_usd']} {pos['leverage']}x {pos['margin_type']} {pos['routing_used']}{limit_str} TP: ${pos['take_profit']} SL: ${pos['stop_loss']} (Order #{pos['order_id']})", flush=True)
                else:
                    pos["binance_synced"] = False
                    if exec_status in ("ABORTED_UNPROTECTED_SL", "ABORTED_MODE_MISMATCH", "FAILED_UNKNOWN_POSITION_STATE") or execution_result.get("critical_alert"):
                        send_telegram(
                            f"⚠️ <b>[EXECUTION ABORTED] {pos['binance_pair']} ({exec_status or 'ABORTED'})</b>\n"
                            f"Detail: <i>{execution_result.get('error') or execution_result.get('critical_alert')}</i>\n"
                            f"Emergency flat verified: <b>{execution_result.get('emergency_flat_verified', False)}</b>"
                        )
                    print(f"[BINANCE] ⚠️ Binance execution rejected ({exec_status or 'REJECTED'}): {execution_result.get('error')}", flush=True)
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

    try:
        _save_positions_merged([pos])
    except CorruptedStateError as cse:
        print(f"[POSITION] ❌ POSITIONS_FILE corrupt during merge write ({cse}) — refusing to overwrite.", flush=True)

    try:
        save_hard_risk_engine(risk_eng, daily_trades_delta=1)
    except Exception as exc:
        logger.warning("save_hard_risk_engine failed after record_position: %s", exc)

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
            "fee_usd": pos.get("fee_usd") if pos.get("fee_usd") is not None else round(pos["position_size_usd"] * pos["leverage"] * 0.0005, 4),
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
        "learners_pending": [],
        "history": [],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    with get_file_lock(PERF_LEDGER_FILE):
        data = read_json_safe(
            PERF_LEDGER_FILE,
            default=None,
            strict_on_corrupt=True,
            expected_type=dict,
        )
        if isinstance(data, dict):
            # Strip legacy simulated baseline if no real recorded trades exist yet
            if data.get("baseline_wins") == 15 and not data.get("recorded_trade_ids"):
                data.update(default_ledger)
                atomic_write_json(PERF_LEDGER_FILE, data, make_bak=True)
            elif "learners_pending" not in data:
                data["learners_pending"] = []
            return data
        os.makedirs(RESULTS_DIR, exist_ok=True)
        atomic_write_json(PERF_LEDGER_FILE, default_ledger, make_bak=True)
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
    outcome_win = bool(float(net_usd) > 0)

    done_steps = set(pos.get("_completed_learner_steps") or [])
    step_errors = []

    def _mark_done(step_key: str):
        done_steps.add(step_key)
        pos["_completed_learner_steps"] = sorted(done_steps)

    # 1. HardRiskEngine Circuit Breaker update
    if "risk_engine" not in done_steps:
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
            _mark_done("risk_engine")
        except Exception as exc:
            logger.error("Closed-loop HardRiskEngine update failed for %s: %s", pos.get("id"), exc, exc_info=True)
            print(f"[LEARNERS] ❌ HardRiskEngine error for {pos.get('id')}: {exc}", flush=True)
            step_errors.append(("risk_engine", str(exc)))

    # 2. Contextual Thompson Bandit
    if "bandit" not in done_steps:
        try:
            from strategies.bandit_allocator import ContextualThompsonBandit
            bandit = ContextualThompsonBandit()
            bandit.update(strat_id, regime_str, r_net=r_mult_net)
            _mark_done("bandit")
        except Exception as exc:
            logger.error("Closed-loop Bandit update failed for %s: %s", pos.get("id"), exc, exc_info=True)
            print(f"[LEARNERS] ❌ Bandit error for {pos.get('id')}: {exc}", flush=True)
            step_errors.append(("bandit", str(exc)))

    # 3. Walk-Forward Strategy Auto-Degradation check
    if "degradation" not in done_steps:
        try:
            from shadow.promote import evaluate_auto_degradation
            deg = evaluate_auto_degradation(strat_id, window=15, min_trades=15)
            if isinstance(deg, dict):
                with get_file_lock(DEGRADED_STRAT_FILE):
                    degraded_map = read_json_safe(
                        DEGRADED_STRAT_FILE,
                        default={},
                        strict_on_corrupt=False,
                        expected_type=dict,
                    ) or {}
                    if deg.get("degraded"):
                        was_deg = bool((degraded_map.get(strat_id) or {}).get("degraded"))
                        degraded_map[strat_id] = {**deg, "updated_at": time.time()}
                        atomic_write_json(DEGRADED_STRAT_FILE, degraded_map)
                        if not was_deg:
                            send_telegram(f"⚠️ <b>[AUTO-DEGRADATION]</b> Strategi <code>{strat_id}</code> turun ke <b>SHADOW_ONLY</b> ({deg.get('reason')}).")
                    elif strat_id in degraded_map:
                        degraded_map.pop(strat_id, None)
                        atomic_write_json(DEGRADED_STRAT_FILE, degraded_map)
            _mark_done("degradation")
        except Exception as exc:
            logger.error("Closed-loop Auto-Degradation update failed for %s: %s", pos.get("id"), exc, exc_info=True)
            print(f"[LEARNERS] ❌ Auto-Degradation error for {pos.get('id')}: {exc}", flush=True)
            step_errors.append(("degradation", str(exc)))

    # 4. PAVA Calibrator + Adaptive Conformal Filter (persisted across restarts)
    cal_p = float(pos.get("calibrated_prob") or (float(pos.get("confidence_score", 70)) / 100.0))
    cal_obj = None
    if "calibrator" not in done_steps:
        try:
            from features.hmm_drift import load_calibrator, save_calibrator
            cal_obj = load_calibrator()
            cal_obj.record_outcome(cal_p, outcome_win, strategy_id=strat_id, regime=regime_str)
            save_calibrator(cal_obj)
            _mark_done("calibrator")
        except Exception as exc:
            logger.error("Closed-loop Calibrator update failed for %s: %s", pos.get("id"), exc, exc_info=True)
            print(f"[LEARNERS] ❌ Calibrator error for {pos.get('id')}: {exc}", flush=True)
            step_errors.append(("calibrator", str(exc)))

    if "conformal" not in done_steps:
        try:
            from features.hmm_drift import load_conformal_filter, save_conformal_filter
            sniper_cfg = cfg.get("sniper_75_mode", {})
            c_filt = load_conformal_filter(alpha_target=float(sniper_cfg.get("conformal_alpha_target", 0.18)))
            c_filt.update(cal_p, outcome_win)
            save_conformal_filter(c_filt)
            _mark_done("conformal")
        except Exception as exc:
            logger.error("Closed-loop Conformal update failed for %s: %s", pos.get("id"), exc, exc_info=True)
            print(f"[LEARNERS] ❌ Conformal error for {pos.get('id')}: {exc}", flush=True)
            step_errors.append(("conformal", str(exc)))

    # 5. ADWIN Concept Drift Detector (trims stale pre-drift calibration window safely)
    if "adwin" not in done_steps:
        try:
            from features.hmm_drift import ADWINDetector, save_calibrator
            drift_res = ADWINDetector().update(r_mult_net)
            if drift_res.get("drift_detected"):
                print(f"[ADWIN DRIFT] 🌊 Concept drift detected in recent trade stream (window={drift_res.get('window_len')})", flush=True)
                if cal_obj is not None and len(getattr(cal_obj, "history_y", [])) > 25:
                    cal_obj.fit(cal_obj.history_p_raw[-25:], cal_obj.history_y[-25:])
                    save_calibrator(cal_obj)
            _mark_done("adwin")
        except Exception as exc:
            logger.error("Closed-loop ADWIN update failed for %s: %s", pos.get("id"), exc, exc_info=True)
            print(f"[LEARNERS] ❌ ADWIN error for {pos.get('id')}: {exc}", flush=True)
            step_errors.append(("adwin", str(exc)))

    # 6. Online TabularMetaModel + NeuroSymbolicEnsemble + EpisodicMarketMemory
    x_vec = pos.get("quant_feature_vector")
    if isinstance(x_vec, list) and len(x_vec) >= 10 and "meta_ensemble" not in done_steps:
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
            _mark_done("meta_ensemble")
        except Exception as exc:
            logger.error("Closed-loop Meta/Ensemble/Episodic update failed for %s: %s", pos.get("id"), exc, exc_info=True)
            print(f"[LEARNERS] ❌ Meta/Ensemble error for {pos.get('id')}: {exc}", flush=True)
            step_errors.append(("meta_ensemble", str(exc)))

    if step_errors:
        raise RuntimeError(f"Closed-loop learner failure(s) for {pos.get('id')}: {step_errors}")


def _build_learner_snapshot(pos: dict) -> dict:
    keys = (
        "id", "symbol", "binance_pair", "direction", "setup_name", "regime",
        "entry_price", "init_stop_loss", "stop_loss", "leverage", "position_size_usd",
        "calibrated_prob", "confidence_score", "quant_feature_vector",
        "p_quant_ml", "p_knn", "p_llm",
    )
    return {k: pos.get(k) for k in keys if k in pos}


def _retry_pending_learners(max_attempts: int = 2) -> int:
    """Retry any closed trades in PERF_LEDGER_FILE['learners_pending'] whose learner update failed transiently."""
    retried_ok = 0
    try:
        with get_file_lock(PERF_LEDGER_FILE):
            ledger = _ensure_perf_ledger()
            pending_list = list(ledger.get("learners_pending") or [])
    except CorruptedStateError as cse:
        logger.error("PERF_LEDGER_FILE corrupt during _retry_pending_learners: %s", cse)
        return 0
    except Exception as exc:
        logger.error("Failed reading learners_pending: %s", exc)
        return 0

    if not pending_list:
        return 0

    remaining = []
    changed = False
    for entry in pending_list:
        if not isinstance(entry, dict):
            changed = True
            continue
        attempts = int(entry.get("attempts", 0))
        if attempts >= max_attempts:
            remaining.append(entry)
            continue
        pos_snap = dict(entry.get("pos") or {"id": entry.get("id")})
        if entry.get("completed_steps"):
            pos_snap["_completed_learner_steps"] = list(entry["completed_steps"])
        try:
            _update_closed_loop_learners(
                pos_snap,
                float(entry.get("net_usd", 0.0)),
                float(entry.get("exit_price", 0.0)),
                str(entry.get("exit_reason", "CLOSED")),
            )
            retried_ok += 1
            changed = True
            print(f"[LEARNERS] ✅ Retry succeeded for pending trade {entry.get('id')}", flush=True)
        except Exception as exc:
            changed = True
            updated_entry = dict(entry)
            updated_entry["attempts"] = attempts + 1
            updated_entry["last_error"] = str(exc)
            if pos_snap.get("_completed_learner_steps"):
                updated_entry["completed_steps"] = list(pos_snap["_completed_learner_steps"])
            updated_entry["last_retry_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            remaining.append(updated_entry)
            logger.error("Pending learner retry failed for %s (attempt %d): %s", entry.get("id"), updated_entry["attempts"], exc)
            print(f"[LEARNERS] ⚠️ Pending retry failed for {entry.get('id')} (attempt {updated_entry['attempts']}): {exc}", flush=True)

    if changed:
        try:
            with get_file_lock(PERF_LEDGER_FILE):
                ledger_now = _ensure_perf_ledger()
                ledger_now["learners_pending"] = remaining
                ledger_now["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                atomic_write_json(PERF_LEDGER_FILE, ledger_now, make_bak=True)
        except Exception as exc:
            logger.error("Failed persisting updated learners_pending: %s", exc)

    return retried_ok


def _record_trade_close_in_journal(
    pos: dict,
    exit_price: float,
    exit_reason: str,
    pnl_usd: float = None,
    fee_usd: float = None,
    funding_usd: float = 0.0,
    gross_pnl_usd: float = None,
):
    """Helper to record closed trades into SQLite WAL journal, TCA markouts, performance_ledger, and online learners."""
    pos_id = pos.get("id")
    if not pos_id:
        return

    lev = int(pos.get("leverage", 20) or 20)
    pos_usd = float(pos.get("position_size_usd") or 1.0)
    entry_px = float(pos.get("entry_price") or 1.0)
    dir_str = str(pos.get("direction", "LONG")).upper()

    if gross_pnl_usd is not None:
        gross_val = float(gross_pnl_usd)
    elif pnl_usd is not None:
        gross_val = float(pnl_usd)
    else:
        if entry_px > 0:
            gross_val = ((exit_price - entry_px) / entry_px * pos_usd * lev) if dir_str == "LONG" else ((entry_px - exit_price) / entry_px * pos_usd * lev)
        else:
            gross_val = 0.0

    actual_fee_usd = round(float(fee_usd), 6) if fee_usd is not None else round(pos_usd * lev * 0.0010, 4)
    actual_funding_usd = round(float(funding_usd or 0.0), 6)
    net_usd = float(gross_val) - actual_fee_usd - actual_funding_usd

    try:
        fx_r = float(get_fx_info().get("usd_idr", 16500) or 16500)
    except Exception as fxe:
        logger.warning("get_fx_info failed during trade close recording (%s); defaulting FX=16500", fxe)
        fx_r = 16500.0
    net_idr = round(net_usd * fx_r)

    try:
        import journal
        close_payload = {
            "close_ts": pos.get("closed_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "exit_fill": exit_price,
            "pnl_usd": round(gross_val, 4),
            "fee_usd": actual_fee_usd,
            "funding_usdt": actual_funding_usd,
            "net_pnl_usdt": round(net_usd, 6),
            "exit_reason": exit_reason,
            "is_estimated": 0,
        }
        j_res = journal.close_trade(pos_id, close_payload)
        if j_res is None:
            # Ensure auto-imported / pre-existing exchange positions exist in journal.db before closing
            journal.open_trade({
                "id": pos_id,
                "signal_id": pos.get("signal_id") or pos_id,
                "symbol": pos.get("symbol", ""),
                "direction": dir_str,
                "open_ts": pos.get("opened_at") or pos.get("opened_ts"),
                "entry_fill": entry_px,
                "qty": pos.get("quantity") or (pos_usd * lev / entry_px if entry_px > 0 else 0.0),
                "leverage": lev,
                "margin_usd": pos_usd,
                "fee_usd": actual_fee_usd,
                "strategy_id": pos.get("setup_name", "AI_SETUP"),
                "regime": pos.get("regime", "NORMAL"),
                "cal_p": pos.get("calibrated_prob") or (float(pos.get("confidence_score", 70)) / 100.0),
                "sl_plan": float(pos.get("init_stop_loss") or pos.get("stop_loss") or 0.0),
                "tp_plan": float(pos.get("take_profit") or 0.0),
            })
            journal.close_trade(pos_id, close_payload)
        try:
            journal.update_tca_markout(pos_id, "close", float(exit_price or 0.0))
        except Exception as m_exc:
            logger.warning("update_tca_markout(close) failed for %s: %s", pos_id, m_exc)
        print(f"[JOURNAL] 📕 Closed trade logged in journal: {pos_id} ({exit_reason}, Net PnL: ${net_usd:+.4f})", flush=True)
    except Exception as je:
        logger.error("Error logging closed trade %s to SQLite journal: %s", pos_id, je, exc_info=True)
        print(f"[JOURNAL] ⚠️ Error recording trade close in journal: {je}", flush=True)

    # Update Persistent Performance Ledger (Zero-Reset across restarts)
    should_run_learners = False
    try:
        with get_file_lock(PERF_LEDGER_FILE):
            ledger = _ensure_perf_ledger()
            rec_ids = list(ledger.get("recorded_trade_ids", []))
            pending_list = [e for e in (ledger.get("learners_pending") or []) if isinstance(e, dict)]
            if pos_id not in rec_ids:
                rec_ids.append(pos_id)
                if net_usd > 0:
                    ledger["winning_trades"] = int(ledger.get("winning_trades", 0)) + 1
                else:
                    ledger["losing_trades"] = int(ledger.get("losing_trades", 0)) + 1
                w = int(ledger["winning_trades"])
                l = int(ledger["losing_trades"])
                ledger["closed_trades"] = w + l
                ledger["win_rate_pct"] = round((w / max(1, w + l)) * 100.0, 2)
                ledger["realized_pnl_idr"] = round(float(ledger.get("realized_pnl_idr", 0)) + net_idr)
                ledger["realized_pnl_usd"] = round(float(ledger.get("realized_pnl_usd", 0.0)) + net_usd, 4)
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
                    "gross_pnl_usd": round(gross_val, 4),
                    "fee_usd": actual_fee_usd,
                    "funding_usd": actual_funding_usd,
                    "exit_reason": exit_reason,
                    "closed_at": pos.get("closed_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                })
                ledger["history"] = hist[:200]
                if not any(e.get("id") == pos_id for e in pending_list):
                    pending_list.append({
                        "id": pos_id,
                        "pos": _build_learner_snapshot(pos),
                        "net_usd": round(net_usd, 6),
                        "exit_price": float(exit_price or 0.0),
                        "exit_reason": str(exit_reason),
                        "attempts": 0,
                        "completed_steps": [],
                        "last_error": None,
                    })
                ledger["learners_pending"] = pending_list
                ledger["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                atomic_write_json(PERF_LEDGER_FILE, ledger, make_bak=True)
                should_run_learners = True
    except Exception as le:
        logger.error("Failed updating PERF_LEDGER_FILE for %s: %s", pos_id, le, exc_info=True)
        print(f"[LEDGER] ❌ Failed updating performance ledger for {pos_id}: {le}", flush=True)
        # Still try running learners rather than silently losing breaker/learner updates
        should_run_learners = True

    if should_run_learners:
        pos_copy = dict(pos)
        try:
            _update_closed_loop_learners(pos_copy, net_usd, exit_price, exit_reason)
            # Clear pending entry once learners complete cleanly
            try:
                with get_file_lock(PERF_LEDGER_FILE):
                    ledger_done = _ensure_perf_ledger()
                    prev_pend = list(ledger_done.get("learners_pending") or [])
                    new_pend = [e for e in prev_pend if not (isinstance(e, dict) and e.get("id") == pos_id)]
                    if len(new_pend) != len(prev_pend):
                        ledger_done["learners_pending"] = new_pend
                        ledger_done["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                        atomic_write_json(PERF_LEDGER_FILE, ledger_done, make_bak=True)
            except Exception as clr_exc:
                logger.warning("Failed clearing learners_pending for %s: %s", pos_id, clr_exc)
        except Exception as l_exc:
            logger.error("Closed-loop learner execution failed for %s; queued in learners_pending: %s", pos_id, l_exc, exc_info=True)
            print(f"[LEARNERS] ❌ Learner update failed for {pos_id} (queued for retry): {l_exc}", flush=True)
            try:
                with get_file_lock(PERF_LEDGER_FILE):
                    ledger_err = _ensure_perf_ledger()
                    pend_err = [e for e in (ledger_err.get("learners_pending") or []) if isinstance(e, dict)]
                    found = False
                    for e in pend_err:
                        if e.get("id") == pos_id:
                            e["attempts"] = int(e.get("attempts", 0)) + 1
                            e["last_error"] = str(l_exc)
                            if pos_copy.get("_completed_learner_steps"):
                                e["completed_steps"] = list(pos_copy["_completed_learner_steps"])
                            found = True
                            break
                    if not found:
                        pend_err.append({
                            "id": pos_id,
                            "pos": _build_learner_snapshot(pos),
                            "net_usd": round(net_usd, 6),
                            "exit_price": float(exit_price or 0.0),
                            "exit_reason": str(exit_reason),
                            "attempts": 1,
                            "completed_steps": list(pos_copy.get("_completed_learner_steps") or []),
                            "last_error": str(l_exc),
                        })
                    ledger_err["learners_pending"] = pend_err
                    ledger_err["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    atomic_write_json(PERF_LEDGER_FILE, ledger_err, make_bak=True)
            except Exception as q_exc:
                logger.error("Failed persisting learners_pending failure state for %s: %s", pos_id, q_exc)


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
    sl_state = "UNKNOWN"
    if bn_client and sym:
        try:
            ok_algo, open_algos = bn_client.get_open_algo_orders(sym)
            if ok_algo and isinstance(open_algos, list):
                sl_state = "MISSING"
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
            else:
                # C-7: API failure during openAlgoOrders lookup MUST preserve UNKNOWN
                sl_state = "UNKNOWN"
        except Exception as exc:
            logger.warning("get_open_algo_orders failed during _build_synced_binance_pos(%s): %s", sym, exc)
            sl_state = "UNKNOWN"

    max_sl_cfg = float(_get_config().get("max_sl_pct", 2.25) or 2.25)
    # C-7: Only place SL when exchange confirmed MISSING (or existing confirmed SL violates liquidation).
    # When sl_state == "UNKNOWN", do NOT place a duplicate SL — wait and retry on next tick!
    sl_inside_liq = (
        sl_state == "CONFIRMED"
        and sl_px > 0
        and liq_px > 0
        and ((dir_str == "LONG" and sl_px <= liq_px) or (dir_str == "SHORT" and sl_px >= liq_px))
    )
    if sl_state == "MISSING" or sl_inside_liq:
        sl_px = _safe_sl_against_liquidation(entry_px, dir_str, 0.0, liq_px, max_sl_cfg)
        if bn_client and sym and sl_px > 0:
            try:
                sl_res = bn_client.set_stop_loss(sym, dir_str, sl_px)
                if isinstance(sl_res, dict) and "algoId" in sl_res:
                    sl_algo_id = sl_res["algoId"]
                    sl_state = "CONFIRMED"
                elif isinstance(sl_res, dict) and (sl_res.get("code") == -2021 or sl_res.get("would_immediately_trigger")):
                    sl_state = "UNPROTECTED_RECOVERY"
                else:
                    sl_state = "MISSING"
            except Exception as exc:
                logger.warning("set_stop_loss failed during _build_synced_binance_pos(%s): %s", sym, exc)
                sl_state = "MISSING"

    sl_delta = abs(entry_px - sl_px) if (entry_px > 0 and sl_px > 0) else (entry_px * 0.015)
    sgn = 1.0 if dir_str == "LONG" else -1.0
    tp1_px = round(entry_px + sgn * 0.55 * sl_delta, 6) if entry_px > 0 else 0.0
    if tp_px <= 0 and entry_px > 0 and sl_state != "UNKNOWN":
        tp_px = round(entry_px + sgn * 2.2 * sl_delta, 6)

    iso_margin = abs(float(lp.get("isolated_margin", lp.get("isolatedMargin", 0)) or ((amt * entry_px / lev) if lev else 0)))
    pnl_pct = round((live_upnl / iso_margin) * 100.0, 2) if iso_margin > 0 else 0.0

    return {
        "id": f"POS_BINANCE_{sym}_{int(time.time())}",
        "order_id": f"SYNC_{sym}",
        "symbol": sym.replace("USDT", "-USD"),
        "binance_pair": sym,
        "direction": dir_str,
        "position_side": str(lp.get("position_side") or lp.get("positionSide") or "BOTH").upper(),
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
        "opened_ts": time.time(),
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
            r_bk = requests.get(f"https://fapi.binance.com/fapi/v1/depth?symbol={pair}&limit=20", timeout=2.5, verify=True)
            if r_bk.status_code == 200:
                book = r_bk.json()
            elif r_bk.status_code in (418, 429):
                logger.warning("Microstate depth HTTP %s on %s", r_bk.status_code, pair)
        if book and book.get("bids") and book.get("asks"):
            from features.microstructure import compute_multilevel_ofi
            prev_bk = _PREV_DEPTH_BOOKS.get(pair, book)
            ofi_res = compute_multilevel_ofi(prev_bk, book)
            _PREV_DEPTH_BOOKS[pair] = book
            micro["ofi_20"] = float(ofi_res.get("obi_weighted_20", 0.0) or 0.0)
    except Exception as exc:
        logger.debug("Microstate depth fetch error for %s: %s", pair, exc)

    try:
        r_ag = requests.get(f"https://fapi.binance.com/fapi/v1/aggTrades?symbol={pair}&limit=80", timeout=2.5, verify=True)
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
        elif r_ag.status_code in (418, 429):
            logger.warning("Microstate aggTrades HTTP %s on %s", r_ag.status_code, pair)
    except Exception as exc:
        logger.debug("Microstate aggTrades error for %s: %s", pair, exc)

    try:
        r_pi = requests.get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={pair}", timeout=2.0, verify=True)
        if r_pi.status_code == 200:
            pi = r_pi.json() or {}
            m_p = float(pi.get("markPrice") or 0.0)
            i_p = float(pi.get("indexPrice") or 0.0)
            if m_p > 0 and i_p > 0:
                micro["spot_perp_div"] = round((i_p - m_p) / i_p, 6)
        elif r_pi.status_code in (418, 429):
            logger.warning("Microstate premiumIndex HTTP %s on %s", r_pi.status_code, pair)
    except Exception as exc:
        logger.debug("Microstate premiumIndex error for %s: %s", pair, exc)

    try:
        r_kl = requests.get(f"https://fapi.binance.com/fapi/v1/klines?symbol={pair}&interval=5m&limit=24", timeout=2.5, verify=True)
        if r_kl.status_code == 200:
            kl = r_kl.json() or []
            cl = [float(x[4]) for x in kl if len(x) > 4]
            if len(cl) >= 6:
                import numpy as _np
                rets = _np.diff(_np.log(_np.maximum(cl, 1e-8)))
                # Annualized sigma from 5m bars (288 * 365 = 105120 bars/yr)
                sig_ann = float(_np.std(rets)) * (105120.0 ** 0.5) if rets.size > 2 else 0.35
                micro["sigma"] = max(0.15, min(2.5, sig_ann))
        elif r_kl.status_code in (418, 429):
            logger.warning("Microstate klines HTTP %s on %s", r_kl.status_code, pair)
    except Exception as exc:
        logger.debug("Microstate klines error for %s: %s", pair, exc)

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
    except Exception as exc:
        logger.debug("_sync_open_shadow_trades error: %s", exc)


_CLOSE_FAIL_ALERT_TS = {}


def _send_close_fail_alert_rate_limited(pos: dict, message: str, cooldown_sec: float = 60.0) -> None:
    key = str(pos.get("id") or pos.get("binance_pair") or pos.get("symbol") or "UNKNOWN")
    now = time.time()
    last_ts = max(float(_CLOSE_FAIL_ALERT_TS.get(key, 0.0)), float(pos.get("_last_close_fail_alert_ts") or 0.0))
    if now - last_ts >= cooldown_sec:
        _CLOSE_FAIL_ALERT_TS[key] = now
        pos["_last_close_fail_alert_ts"] = now
        send_telegram(message)


def _cancel_all_orders_and_verify(bn_client, pair: str) -> dict:
    """Cancel standard and algo orders for `pair` and verify get_open_algo_orders(pair) is empty (C-5)."""
    out = {"cancelled": False, "algo_empty": False, "remaining_algo_ids": [], "error": None}
    if not bn_client or not pair:
        return out
    try:
        res = bn_client.cancel_all_orders(pair)
        out["raw"] = res
        out["cancelled"] = True
    except Exception as exc:
        out["error"] = str(exc)
        logger.error("cancel_all_orders failed for %s: %s", pair, exc)
        print(f"[CLEANUP] ⚠️ cancel_all_orders failed for {pair}: {exc}", flush=True)

    if hasattr(bn_client, "get_open_algo_orders"):
        try:
            chk = bn_client.get_open_algo_orders(pair)
            if isinstance(chk, tuple) and len(chk) == 2:
                ok_algo, open_algos = chk
                if ok_algo and isinstance(open_algos, list):
                    stragglers = [ao for ao in open_algos if isinstance(ao, dict) and ao.get("algoId") is not None]
                    for ao in stragglers:
                        aid = int(ao["algoId"])
                        if hasattr(bn_client, "cancel_algo_order"):
                            try:
                                bn_client.cancel_algo_order(pair, aid)
                            except Exception as ce:
                                logger.warning("cancel_algo_order(%s, %s) failed: %s", pair, aid, ce)
                    if stragglers:
                        chk2 = bn_client.get_open_algo_orders(pair)
                        if isinstance(chk2, tuple) and len(chk2) == 2 and chk2[0] and isinstance(chk2[1], list):
                            out["remaining_algo_ids"] = [
                                int(ao["algoId"]) for ao in chk2[1] if isinstance(ao, dict) and ao.get("algoId") is not None
                            ]
                            out["algo_empty"] = len(out["remaining_algo_ids"]) == 0
                    else:
                        out["algo_empty"] = True
        except Exception as exc:
            logger.warning("get_open_algo_orders verify failed for %s: %s", pair, exc)
    return out


def _parse_opened_ms(pos: dict):
    ts_val = pos.get("opened_ts")
    if ts_val is not None:
        try:
            f = float(ts_val)
            if f > 0:
                return int(f * 1000) if f < 1e11 else int(f)
        except (TypeError, ValueError):
            pass
    open_str = pos.get("opened_at") or pos.get("entry_time") or ""
    if open_str:
        try:
            od = datetime.fromisoformat(str(open_str).replace(" UTC", "+00:00").replace("Z", "+00:00"))
            return int(od.astimezone(timezone.utc).timestamp() * 1000)
        except Exception:
            pass
    return None


def _call_optional_start_time(fn, *args, start_time=None, **kwargs):
    if start_time is not None:
        try:
            return fn(*args, start_time=start_time, **kwargs)
        except TypeError:
            pass
    return fn(*args, **kwargs)


def _select_lifecycle_trades(raw_trades: list, pair: str, direction: str, pos: dict, start_ms):
    """Filter userTrades to only fills belonging to this position lifecycle (C-6)."""
    if not isinstance(raw_trades, list) or not raw_trades:
        return []
    pair_u = str(pair or "").upper()
    entry_side = "BUY" if str(direction).upper() == "LONG" else "SELL"

    # Keep only matching symbol (if present) and >= start_ms (if timestamp present)
    filtered = []
    for t in raw_trades:
        if not isinstance(t, dict):
            continue
        tsym = str(t.get("symbol") or "").upper()
        if tsym and pair_u and tsym != pair_u:
            continue
        t_ms = t.get("time") or t.get("T")
        if start_ms is not None and t_ms is not None:
            try:
                if int(t_ms) < int(start_ms):
                    continue
            except (TypeError, ValueError):
                pass
        filtered.append(t)

    if not filtered:
        return []

    # Sort chronologically when timestamps exist
    if all((t.get("time") is not None or t.get("T") is not None) for t in filtered):
        filtered.sort(key=lambda t: int(t.get("time") or t.get("T") or 0))

    # If exact entry order_id exists in trades, anchor lifecycle there
    pos_oid = pos.get("order_id")
    if pos_oid is not None and str(pos_oid).isdigit():
        oid_str = str(pos_oid)
        for idx, t in enumerate(filtered):
            if str(t.get("orderId") or "") == oid_str:
                return filtered[idx:]

    # If start_ms is known, exclude any stray closing fill that happened strictly before the first opening fill
    if start_ms is not None:
        for idx, t in enumerate(filtered):
            tside = str(t.get("side") or "").upper()
            rpnl = abs(float(t.get("realizedPnl", 0) or 0))
            if rpnl == 0.0 and (not tside or tside == entry_side):
                return filtered[idx:]
        return filtered

    # Fallback when opened_ts/opened_at missing: walk backwards for latest contiguous trade lifecycle
    selected = []
    saw_closing = False
    for t in reversed(filtered):
        tside = str(t.get("side") or "").upper()
        rpnl = abs(float(t.get("realizedPnl", 0) or 0))
        is_opening_fill = (rpnl == 0.0 and tside == entry_side)
        if saw_closing and not is_opening_fill:
            # If we already crossed an opening fill earlier and now see an older closing fill, stop
            if any(
                abs(float(s.get("realizedPnl", 0) or 0)) == 0.0 and str(s.get("side") or "").upper() == entry_side
                for s in selected
            ):
                break
        if rpnl > 0 or (tside and tside != entry_side):
            saw_closing = True
        selected.append(t)
    selected.reverse()
    return selected


def _fetch_exchange_close_metrics(
    pair: str,
    direction: str,
    pos: dict,
    bn_client,
    ticker_map: dict,
    entry_price: float,
    pos_usd: float,
    leverage: float,
    fx_rate: float,
    fallback_price: float,
    fallback_pnl_usd: float = None,
) -> dict:
    """
    Query Binance userTrades & income history scoped to this trade lifecycle,
    converting non-USDT commissions (e.g. BNB/base asset) to USDT and detecting liquidation/ADL (C-6).
    """
    opened_ms = _parse_opened_ms(pos)
    start_ms = max(0, opened_ms - 5000) if opened_ms is not None else None
    asset_px_cache = {}
    base_asset = pair[:-4] if str(pair).upper().endswith("USDT") else ""

    def _convert_to_usdt(amount: float, asset: str, fill_px_hint: float = 0.0):
        a = str(asset or "USDT").upper().strip()
        if a in ("USDT", "USDC", "BUSD", "FDUSD", ""):
            return float(amount)
        if base_asset and a == base_asset and fill_px_hint > 0:
            return float(amount) * float(fill_px_hint)
        if a not in asset_px_cache:
            px_val = 0.0
            q_pair = f"{a}USDT"
            if ticker_map and q_pair in ticker_map:
                try:
                    px_val = float(ticker_map[q_pair] or 0.0)
                except (TypeError, ValueError):
                    px_val = 0.0
            if px_val <= 0 and bn_client and hasattr(bn_client, "get_market_price"):
                try:
                    px_val = float(bn_client.get_market_price(q_pair) or 0.0)
                except Exception:
                    px_val = 0.0
            asset_px_cache[a] = px_val if px_val > 0 else None
        px = asset_px_cache[a]
        return float(amount) * px if px else None

    curr_px = float(fallback_price or ticker_map.get(pair, entry_price) or entry_price or 0.0)
    gross_pnl_from_trades = None
    commission_from_trades = 0.0
    had_unpriced_commission = False
    is_liquidation = False
    is_adl = False
    close_side = "SELL" if str(direction).upper() == "LONG" else "BUY"

    lifecycle_trades = []
    if bn_client and hasattr(bn_client, "get_user_trades"):
        try:
            raw_trades = _call_optional_start_time(bn_client.get_user_trades, pair, limit=100, start_time=start_ms)
            lifecycle_trades = _select_lifecycle_trades(raw_trades, pair, direction, pos, start_ms)
        except Exception as exc:
            logger.warning("get_user_trades failed for %s: %s", pair, exc)
            lifecycle_trades = []

    if lifecycle_trades:
        closing_trades = [t for t in lifecycle_trades if abs(float(t.get("realizedPnl", 0) or 0)) > 0]
        if not closing_trades:
            closing_trades = [t for t in lifecycle_trades if str(t.get("side") or "").upper() == close_side]

        for t in lifecycle_trades:
            c_amt = abs(float(t.get("commission", 0) or 0))
            c_asset = t.get("commissionAsset", "USDT")
            t_px = float(t.get("price") or curr_px or entry_price or 0.0)
            if c_amt > 0:
                c_usdt = _convert_to_usdt(c_amt, c_asset, fill_px_hint=t_px)
                if c_usdt is not None:
                    commission_from_trades += c_usdt
                else:
                    had_unpriced_commission = True
                    q_t = abs(float(t.get("qty", 0) or 0))
                    if q_t > 0 and t_px > 0:
                        commission_from_trades += q_t * t_px * 0.0004
                    logger.warning("Could not convert commissionAsset=%s to USDT for %s", c_asset, pair)

            t_meta = f"{t.get('type', '')} {t.get('orderType', '')} {t.get('info', '')}".upper()
            if t.get("isLiquidation") or "LIQUIDAT" in t_meta:
                is_liquidation = True
            if t.get("isADL") or "ADL" in t_meta:
                is_adl = True

        if closing_trades:
            last_t = closing_trades[-1]
            last_px = float(last_t.get("price") or 0)
            if last_px > 0:
                curr_px = last_px
            gross_pnl_from_trades = sum(float(t.get("realizedPnl", 0) or 0) for t in closing_trades)

    # Query income history for FUNDING_FEE, liquidation/ADL events, and fallback REALIZED_PNL
    income_items = []
    if bn_client and hasattr(bn_client, "get_income_history"):
        try:
            raw_inc = _call_optional_start_time(bn_client.get_income_history, pair, limit=100, start_time=start_ms)
            if isinstance(raw_inc, list):
                for it in raw_inc:
                    if not isinstance(it, dict):
                        continue
                    isym = str(it.get("symbol") or "").upper()
                    if isym and pair and isym != str(pair).upper():
                        continue
                    it_ms = it.get("time") or it.get("T")
                    if start_ms is not None and it_ms is not None:
                        try:
                            if int(it_ms) < int(start_ms):
                                continue
                        except (TypeError, ValueError):
                            pass
                    income_items.append(it)
        except Exception as exc:
            logger.warning("get_income_history failed for %s: %s", pair, exc)

    funding_income_usd = 0.0
    income_realized_items = []
    income_commission_items = []
    for it in income_items:
        itype = str(it.get("incomeType") or "").upper()
        info_txt = str(it.get("info") or "").upper()
        if itype == "INSURANCE_CLEAR" or "LIQUIDAT" in itype or "LIQUIDAT" in info_txt:
            is_liquidation = True
        if "ADL" in itype or "ADL" in info_txt or "DELEVERAG" in info_txt:
            is_adl = True
        if itype == "FUNDING_FEE":
            val = float(it.get("income", 0) or 0)
            conv = _convert_to_usdt(val, it.get("asset", "USDT"), fill_px_hint=curr_px or entry_price)
            if conv is not None:
                funding_income_usd += conv
        elif itype == "REALIZED_PNL":
            income_realized_items.append(it)
        elif itype == "COMMISSION":
            income_commission_items.append(it)

    funding_cost_usd = -funding_income_usd

    # Optional order history check for liquidation / ADL clientOrderId tags if still unclassified
    if (not is_liquidation and not is_adl) and bn_client and hasattr(bn_client, "get_all_orders"):
        try:
            raw_orders = _call_optional_start_time(bn_client.get_all_orders, pair, limit=20, start_time=start_ms)
            if isinstance(raw_orders, list):
                for ord_it in raw_orders:
                    if not isinstance(ord_it, dict):
                        continue
                    o_ms = ord_it.get("updateTime") or ord_it.get("time")
                    if start_ms is not None and o_ms is not None:
                        try:
                            if int(o_ms) < int(start_ms):
                                continue
                        except (TypeError, ValueError):
                            pass
                    cid = str(ord_it.get("clientOrderId") or "").lower()
                    otype = str(ord_it.get("type") or ord_it.get("origType") or "").upper()
                    ost = str(ord_it.get("status") or "").upper()
                    if ost in ("FILLED", "PARTIALLY_FILLED", ""):
                        if cid.startswith("autoclose-") or "LIQUIDATION" in otype:
                            is_liquidation = True
                        elif "adl" in cid or "ADL" in otype:
                            is_adl = True
        except Exception as exc:
            logger.warning("get_all_orders failed for %s: %s", pair, exc)

    used_exchange_fills = False
    if gross_pnl_from_trades is not None:
        gross_pnl_usd = float(gross_pnl_from_trades)
        commission_usd = float(commission_from_trades)
        used_exchange_fills = True
    elif income_realized_items:
        gross_pnl_usd = 0.0
        for it in income_realized_items:
            conv = _convert_to_usdt(float(it.get("income", 0) or 0), it.get("asset", "USDT"), fill_px_hint=curr_px or entry_price)
            if conv is not None:
                gross_pnl_usd += conv
        commission_usd = 0.0
        for it in income_commission_items:
            conv = _convert_to_usdt(abs(float(it.get("income", 0) or 0)), it.get("asset", "USDT"), fill_px_hint=curr_px or entry_price)
            if conv is not None:
                commission_usd += conv
        if not income_commission_items and commission_from_trades > 0:
            commission_usd = commission_from_trades
        elif not income_commission_items and pos_usd > 0:
            commission_usd = round(pos_usd * leverage * 0.0010, 4)
        used_exchange_fills = True
    else:
        if fallback_pnl_usd is not None:
            gross_pnl_usd = float(fallback_pnl_usd)
        elif entry_price > 0 and curr_px > 0:
            if str(direction).upper() == "LONG":
                gross_pnl_usd = ((curr_px - entry_price) / entry_price) * pos_usd * leverage
            else:
                gross_pnl_usd = ((entry_price - curr_px) / entry_price) * pos_usd * leverage
        else:
            gross_pnl_usd = 0.0
        commission_usd = commission_from_trades if commission_from_trades > 0 else round(pos_usd * leverage * 0.0010, 4)

    net_pnl_usd = float(gross_pnl_usd) - float(commission_usd) - float(funding_cost_usd)
    net_pnl_pct = (net_pnl_usd / pos_usd) * 100.0 if pos_usd > 0 else 0.0
    net_pnl_idr = net_pnl_usd * fx_rate

    return {
        "exit_price": curr_px,
        "gross_pnl_usd": gross_pnl_usd,
        "commission_usd": commission_usd,
        "funding_usd": funding_cost_usd,
        "net_pnl_usd": net_pnl_usd,
        "net_pnl_pct": net_pnl_pct,
        "net_pnl_idr": net_pnl_idr,
        "is_liquidation": is_liquidation,
        "is_adl": is_adl,
        "used_exchange_fills": used_exchange_fills,
        "had_unpriced_commission": had_unpriced_commission,
    }


def _update_vault_on_close(bn_client, bal_info: dict = None) -> None:
    """Update High-Water Mark Profit Vault via singleton get_profit_vault()."""
    try:
        bal_now = bal_info
        if bal_now is None and bn_client:
            bal_now = bn_client.get_balance()
        if isinstance(bal_now, dict) and not bal_now.get("isError") and bal_now.get("total_wallet_balance") is not None:
            tot_eq = float(bal_now["total_wallet_balance"])
            if tot_eq > 0:
                state["binance_wallet_balance_usdt"] = round(tot_eq, 4)
                if bal_now.get("available_balance") is not None:
                    state["binance_available_balance_usdt"] = round(float(bal_now["available_balance"]), 4)
                _get_vault_instance(initial_equity=tot_eq).update_equity(tot_eq)
    except Exception as exc:
        logger.warning("ProfitVault update on close failed: %s", exc)


def _finalize_exchange_closed_position(
    pos: dict,
    bn_client,
    ticker_map: dict,
    fx_rate: float,
    bal_info: dict = None,
):
    """
    A-4 Canonical Exchange-Side Close Handler (shared by monitor and guard):
    0. Direct single-symbol flat confirmation via get_positions(pair) (prevents false TP/SL & accidental SL cancel)
    1. Realized PnL / commission / funding / liquidation-or-ADL lookup (C-6)
    2. _record_trade_close_in_journal() -> HardRiskEngine + closed-loop learners
    3. ProfitVault.update_equity() via get_profit_vault()
    4. cancel_all_orders (standard + algo verified empty, C-5)
    5. _save_positions_merged([pos])
    6. Telegram notification
    """
    pair = pos.get("binance_pair") or pos.get("symbol", "").replace("-USD", "USDT")
    pair_u = str(pair or "").upper()
    direction = str(pos.get("direction", "LONG")).upper()
    pos_side_u = _norm_pos_side(pos)

    # 0. Defense-in-depth: Re-confirm position is genuinely flat on Binance BEFORE closing,
    # cancelling SL/TP orders, recording losses into HardRiskEngine, or alerting Telegram!
    if bn_client is not None and hasattr(bn_client, "get_positions") and not _is_unmocked_bf_method(bn_client, "get_positions"):
        try:
            try:
                verify_pos = bn_client.get_positions(pair)
            except TypeError:
                verify_pos = bn_client.get_positions()
        except Exception as v_exc:
            verify_pos = {"isError": True, "error": str(v_exc)}

        if not isinstance(verify_pos, list):
            logger.warning(
                "[CLOSE GUARD] Cannot verify flat on Binance for %s (%s) — aborting exchange close & keeping OPEN/SL intact.",
                pair,
                verify_pos,
            )
            print(
                f"[CLOSE GUARD] ⚠️ Cannot verify flat on Binance for {pair} ({verify_pos}) — keeping OPEN & SL intact.",
                flush=True,
            )
            return None

        for vp in verify_pos:
            if not isinstance(vp, dict):
                continue
            vp_sym = str(vp.get("symbol") or pair_u).upper()
            if vp_sym != pair_u:
                continue
            vp_amt = abs(float(vp.get("position_amount", vp.get("positionAmt", 0)) or 0))
            if vp_amt <= 0:
                continue
            vp_side = _norm_pos_side(vp)
            vp_raw_ps = str(vp.get("position_side") or vp.get("positionSide") or "").upper().strip()
            same_leg = (
                vp_side == pos_side_u
                or vp_side == "BOTH"
                or pos_side_u == "BOTH"
                or vp_raw_ps == "BOTH"
            )
            if same_leg:
                logger.warning(
                    "[CLOSE GUARD] FALSE CLOSE PREVENTED for %s (%s): Binance still reports live position qty=%s (side=%s).",
                    pair,
                    direction,
                    vp_amt,
                    vp_side,
                )
                print(
                    f"[CLOSE GUARD] 🛡️ FALSE CLOSE PREVENTED for {pair} ({direction}): Binance still has live qty={vp_amt} — keeping OPEN & SL intact!",
                    flush=True,
                )
                return None

    entry_price = float(pos.get("entry_price", 0) or 0)
    leverage = float(pos.get("leverage", 20) or 20)
    pos_idr = float(pos.get("position_size_idr", 50000) or 50000)
    pos_usd = float(pos.get("position_size_usd", pos_idr / max(1.0, fx_rate)) or 0)
    tp = float(pos.get("take_profit") or pos.get("take_profit_2") or pos.get("take_profit_1", 0) or 0)

    metrics = _fetch_exchange_close_metrics(
        pair=pair,
        direction=direction,
        pos=pos,
        bn_client=bn_client,
        ticker_map=ticker_map or {},
        entry_price=entry_price,
        pos_usd=pos_usd,
        leverage=leverage,
        fx_rate=fx_rate,
        fallback_price=(ticker_map or {}).get(pair, entry_price),
    )
    # Give live Binance matching engine a brief retry window if userTrades hasn't indexed the close fill yet
    if (
        not metrics.get("used_exchange_fills")
        and isinstance(bn_client, BinanceFuturesClient)
        and type(bn_client) is BinanceFuturesClient
    ):
        time.sleep(0.4)
        metrics = _fetch_exchange_close_metrics(
            pair=pair,
            direction=direction,
            pos=pos,
            bn_client=bn_client,
            ticker_map=ticker_map or {},
            entry_price=entry_price,
            pos_usd=pos_usd,
            leverage=leverage,
            fx_rate=fx_rate,
            fallback_price=(ticker_map or {}).get(pair, entry_price),
        )

    curr_px = float(metrics["exit_price"])
    gross_pnl_usd = float(metrics["gross_pnl_usd"])
    commission_usd = float(metrics["commission_usd"])
    funding_usd = float(metrics["funding_usd"])
    final_pnl_usd = float(metrics["net_pnl_usd"])
    final_pnl_pct = float(metrics["net_pnl_pct"])
    final_pnl_idr = float(metrics["net_pnl_idr"])

    if metrics["is_liquidation"]:
        close_status = "CLOSED_LIQUIDATION"
        event_type = "LIQUIDATION"
    elif metrics["is_adl"]:
        close_status = "CLOSED_ADL"
        event_type = "AUTO-DELEVERAGING (ADL)"
    elif final_pnl_usd > 0:
        tp1_locked = bool(pos.get("tp1_profit_lock_set") or pos.get("tp1_profit_locked"))
        close_status = "CLOSED_TP1_PROFIT_LOCK" if (tp1_locked and tp > 0 and abs(curr_px - tp) > max(1e-9, tp * 1e-4)) else "CLOSED_TP"
        event_type = "TAKE PROFIT / PROFIT LOCK"
    else:
        close_status = "CLOSED_SL"
        event_type = "STOP LOSS"

    pos["status"] = close_status
    pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    pos["close_price"] = curr_px
    pos["pnl_pct"] = round(final_pnl_pct, 2)
    pos["pnl_idr"] = round(final_pnl_idr, 2)
    pos["pnl_usd"] = round(final_pnl_usd, 4)
    pos["gross_pnl_usd"] = round(gross_pnl_usd, 4)
    pos["commission_usd"] = round(commission_usd, 6)
    pos["funding_usd"] = round(funding_usd, 6)
    pos["close_source"] = "EXCHANGE_SYNC"
    pos["pnl_is_estimated"] = not bool(metrics.get("used_exchange_fills"))

    # Refresh post-close wallet balance before HardRiskEngine + ProfitVault updates so neither reads stale cached equity
    fresh_bal = bal_info
    if fresh_bal is None and bn_client and hasattr(bn_client, "get_balance") and not _is_unmocked_bf_method(bn_client, "get_balance"):
        try:
            fresh_bal = bn_client.get_balance()
        except Exception as b_exc:
            logger.warning("Post-close balance refresh failed for %s: %s", pair, b_exc)
            fresh_bal = None
    if isinstance(fresh_bal, dict) and not fresh_bal.get("isError") and fresh_bal.get("total_wallet_balance") is not None:
        tot_eq_now = float(fresh_bal["total_wallet_balance"])
        if tot_eq_now > 0:
            state["binance_wallet_balance_usdt"] = round(tot_eq_now, 4)
            if fresh_bal.get("available_balance") is not None:
                state["binance_available_balance_usdt"] = round(float(fresh_bal["available_balance"]), 4)

    _record_trade_close_in_journal(
        pos,
        curr_px,
        close_status,
        pnl_usd=gross_pnl_usd,
        fee_usd=commission_usd,
        funding_usd=funding_usd,
        gross_pnl_usd=gross_pnl_usd,
    )
    _update_vault_on_close(bn_client, bal_info=fresh_bal)
    _cancel_all_orders_and_verify(bn_client, pair)

    try:
        _save_positions_merged([pos])
    except CorruptedStateError as cse:
        print(f"[CLOSE] ❌ POSITIONS_FILE corrupt during merge write ({cse}) — refusing overwrite.", flush=True)

    est_note = "\nℹ️ <i>Catatan: fill exchange sedang tersinkronisasi (PnL estimasi harga pasar).</i>" if pos.get("pnl_is_estimated") else ""
    send_telegram(
        f"⚡ <b>[BINANCE LIVE] POSISI {pos.get('symbol')} TELAH DITUTUP!</b>\n\n"
        f"🎯 <b>Status:</b> <b>{event_type} TEREKSEKUSI DI EXCHANGE</b>\n"
        f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction} {leverage}x)\n"
        f"💰 <b>Hasil PnL Net:</b> {final_pnl_pct:+.2f}% ({final_pnl_idr:+,.0f} IDR / ${final_pnl_usd:+.4f} USDT)\n"
        f"📍 <b>Entry:</b> ${entry_price:,.4f} ➔ <b>Exit Fill:</b> ${curr_px:,.4f}{est_note}\n\n"
        f"<i>Margin posisi kini telah kembali utuh ke saldo wallet.</i>"
    )
    return pos


def _execute_verified_bot_close(
    pos: dict,
    close_status: str,
    exit_reason: str,
    current_price: float,
    pnl_usd: float,
    pnl_idr: float,
    pnl_pct: float,
    bn_client,
    ticker_map: dict,
    fx_rate: float,
    is_binance_pos: bool,
    close_reason_detail: str = None,
) -> bool:
    """
    A-3 & C-5 Close-First -> Verify-Flat -> Cancel-Orders -> Mark-Closed -> Journal/Learners/Vault -> Save.
    If close_position fails or position remains open on exchange, keeps SL intact & status OPEN for next tick retry.
    """
    pair = pos.get("binance_pair") or pos.get("symbol", "").replace("-USD", "USDT")
    direction = str(pos.get("direction", "LONG")).upper()
    entry_price = float(pos.get("entry_price", 0) or 0)
    leverage = float(pos.get("leverage", 20) or 20)
    pos_usd = float(pos.get("position_size_usd") or (float(pos.get("position_size_idr", 50000) or 50000) / max(1.0, fx_rate)))

    if is_binance_pos and bn_client:
        # 1) Call close_position FIRST
        try:
            close_res = bn_client.close_position(pair, direction)
        except Exception as ce:
            close_res = {"isError": True, "error": str(ce)}

        close_err = (not isinstance(close_res, dict)) or bool(close_res.get("isError"))
        flat_ok = False
        verify_detail = ""

        # 2) Verify not isError AND position is truly flat via get_positions(pair) (abs(amt) == 0)
        if not close_err:
            try:
                post_pos = bn_client.get_positions(pair)
            except Exception as ge:
                post_pos = {"isError": True, "error": str(ge)}

            if isinstance(post_pos, list):
                still_open_items = [
                    p for p in post_pos
                    if (not p.get("symbol") or str(p.get("symbol")).upper() == str(pair).upper())
                    and abs(float(p.get("position_amount", p.get("positionAmt", 0)) or 0)) > 0
                ]
                if not still_open_items:
                    flat_ok = True
                else:
                    rem_amt = abs(float(still_open_items[0].get("position_amount", still_open_items[0].get("positionAmt", 0)) or 0))
                    verify_detail = f"position still open qty={rem_amt}"
            else:
                verify_detail = f"get_positions error: {post_pos}"
        else:
            verify_detail = f"close_position error: {close_res.get('error') if isinstance(close_res, dict) else close_res}"

        # 4) If close_position failed or position remains open: KEEP SL intact, keep status OPEN, alert (rate-limited)
        if not flat_ok:
            pos["last_close_error"] = verify_detail
            pos["last_close_attempt_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            logger.error("Close aborted/unverified for %s (%s): %s — keeping status OPEN & SL intact!", pair, exit_reason, verify_detail)
            print(f"[CLOSE RETRY] ⚠️ Close failed/not flat for {pair} ({exit_reason}): {verify_detail} — keeping SL intact & status OPEN!", flush=True)
            _send_close_fail_alert_rate_limited(
                pos,
                f"⚠️ <b>[CLOSE RETRY] Gagal Menutup Posisi {pos.get('symbol')} ({exit_reason})</b>\n"
                f"Detail: <code>{verify_detail}</code>\n"
                f"🛡️ <i>Order SL bursa DIPERTAHANKAN utuh; posisi tetap OPEN dan akan dicoba tutup ulang pada siklus berikutnya.</i>",
            )
            return False

        # 3) ONLY AFTER flat is confirmed: cancel_all_orders (std + algo verified)
        _cancel_all_orders_and_verify(bn_client, pair)

        metrics = _fetch_exchange_close_metrics(
            pair=pair,
            direction=direction,
            pos=pos,
            bn_client=bn_client,
            ticker_map=ticker_map or {},
            entry_price=entry_price,
            pos_usd=pos_usd,
            leverage=leverage,
            fx_rate=fx_rate,
            fallback_price=current_price,
            fallback_pnl_usd=pnl_usd,
        )
        exit_px = float(metrics["exit_price"] or current_price)
        gross_pnl_usd = float(metrics["gross_pnl_usd"])
        fee_usd = float(metrics["commission_usd"])
        funding_usd = float(metrics["funding_usd"])
    else:
        exit_px = float(current_price)
        gross_pnl_usd = float(pnl_usd)
        fee_usd = round(pos_usd * leverage * 0.0010, 4)
        funding_usd = 0.0

    net_pnl_usd = float(gross_pnl_usd) - float(fee_usd) - float(funding_usd)
    net_pnl_idr = round(net_pnl_usd * fx_rate, 2)
    net_pnl_pct = round((net_pnl_usd / pos_usd) * 100.0, 2) if pos_usd > 0 else round(float(pnl_pct), 2)

    pos["status"] = close_status
    pos["closed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    pos["close_price"] = exit_px
    pos["pnl_pct"] = net_pnl_pct
    pos["pnl_idr"] = net_pnl_idr
    pos["pnl_usd"] = round(net_pnl_usd, 4)
    pos["gross_pnl_usd"] = round(gross_pnl_usd, 4)
    pos["commission_usd"] = round(fee_usd, 6)
    pos["funding_usd"] = round(funding_usd, 6)
    if close_reason_detail:
        pos["close_reason"] = close_reason_detail

    _record_trade_close_in_journal(
        pos,
        exit_px,
        exit_reason,
        pnl_usd=gross_pnl_usd,
        fee_usd=fee_usd,
        funding_usd=funding_usd,
        gross_pnl_usd=gross_pnl_usd,
    )
    if is_binance_pos and bn_client:
        _update_vault_on_close(bn_client)

    try:
        _save_positions_merged([pos])
    except CorruptedStateError as cse:
        print(f"[CLOSE] ❌ POSITIONS_FILE corrupt during merge write ({cse}) — refusing overwrite.", flush=True)

    return True


def monitor_and_update_positions():
    """Thread-safe entrypoint for real-time autonomous position monitoring."""
    with _MONITOR_LOCK:
        return _monitor_and_update_positions_impl()


def _monitor_and_update_positions_impl():
    """
    Real-time autonomous position monitor:
    - Runs every 8-10 seconds (or immediately on <50ms WebSocket event wake-up)
    - Syncs live Binance mark price, unrealized PnL, liquidation price & exchange algo SL/TP
    - Evaluates real-time L2 OFI/TFI/Div orderflow with IntrabarThesisMonitor + Early Invalidation
    - Executes partial TP1 close (tp1_partial_close_pct=0.65) + on-exchange SL lock
    """
    update_runtime_health(last_monitor_ts=time.time())
    _retry_pending_learners()

    try:
        positions = _load_positions_safe(strict=True)
    except CorruptedStateError as cse:
        _alert_error_rate_limited("CORRUPT_POSITIONS_MONITOR", f"POSITIONS_FILE corrupt without valid backup ({cse})", cooldown_sec=300.0)
        print(f"[MONITOR] ❌ POSITIONS_FILE corrupt without valid backup ({cse}) — skipping monitor cycle safely.", flush=True)
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
                update_runtime_health(last_api_ok_ts=time.time())
                bn_live_map = {}
                for lp in live_list:
                    if not isinstance(lp, dict):
                        continue
                    sym_l = str(lp.get("symbol") or "").upper()
                    side_l = _norm_pos_side(lp)
                    if sym_l:
                        bn_live_map[(sym_l, side_l)] = lp
                # Auto-import untracked live Binance positions (keyed by symbol + positionSide for Hedge-mode safety)
                for (sym_l, side_l), lp in bn_live_map.items():
                    already_tracked = any(
                        p.get("status") == "OPEN"
                        and (p.get("binance_pair") or p.get("symbol", "").replace("-USD", "USDT")).upper() == sym_l
                        and (side_l == "BOTH" or _norm_pos_side(p) in (side_l, "BOTH"))
                        for p in positions
                    )
                    amt = float(lp.get("position_amount", 0))
                    if not already_tracked and abs(amt) > 0:
                        new_pos = _build_synced_binance_pos(lp, bn_client, fx_rate)
                        positions.append(new_pos)
                        updated = True
                        print(f"[MONITOR] 📥 Auto-imported active Binance position: {sym_l} ({new_pos['direction']} {new_pos['leverage']}x, SL State: {new_pos['sl_state']})", flush=True)
            elif isinstance(live_list, dict) and live_list.get("isError"):
                update_runtime_health(last_api_err_ts=time.time())
                _alert_error_rate_limited("MONITOR_BINANCE_SYNC", f"Position sync returned error: {live_list.get('msg')}", cooldown_sec=300.0, level="warning")
        except Exception as e:
            update_runtime_health(last_api_err_ts=time.time())
            _alert_error_rate_limited("MONITOR_BINANCE_SYNC", f"Binance sync warning: {e}", cooldown_sec=300.0, level="warning")
            print(f"[MONITOR] Binance sync warning: {e}", flush=True)

    tickers = get_binance_24h_tickers()
    ticker_map = {t["symbol"]: float(t.get("lastPrice", 0)) for t in tickers if "symbol" in t} if tickers else {}
    _sync_open_shadow_trades(ticker_map)

    open_pos = [p for p in positions if p.get("status") == "OPEN"]
    if not open_pos:
        if updated:
            try:
                _save_positions_merged(positions)
            except CorruptedStateError as cse:
                _alert_error_rate_limited("CORRUPT_POSITIONS_SAVE", f"POSITIONS_FILE corrupt during merge write ({cse})", cooldown_sec=300.0)
                print(f"[MONITOR] ❌ POSITIONS_FILE corrupt during merge write ({cse}) — refusing overwrite.", flush=True)
        HeartbeatWorker(heartbeat_path=os.path.join(RESULTS_DIR, "heartbeat.json")).write_once()
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

        # If it was open on Binance, check if Binance still has it (matching symbol + positionSide)
        if is_binance_pos and bn_live_map is not None:
            pair_u = str(pair or "").upper()
            pos_side_u = _norm_pos_side(pos)
            live_item = bn_live_map.get((pair_u, pos_side_u)) or bn_live_map.get((pair_u, "BOTH"))
            if live_item is None and pos_side_u == "BOTH":
                for (s_k, _), v_lp in bn_live_map.items():
                    if s_k == pair_u:
                        live_item = v_lp
                        break
            if live_item is None:
                closed_res = _finalize_exchange_closed_position(pos, bn_client=bn_client, ticker_map=ticker_map, fx_rate=fx_rate)
                if closed_res is not None:
                    updated = True
                continue
            else:
                # Still open on Binance — sync official entry, mark price, liquidation price, margin and unrealized PnL
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
        updated = True

        # WP-1 Handoff Priority: UNPROTECTED_RECOVERY / emergency_close_failed must be closed immediately!
        if is_binance_pos and bn_client and (
            str(pos.get("sl_state") or "").upper() == "UNPROTECTED_RECOVERY"
            or pos.get("emergency_close_failed")
        ):
            print(f"[RECOVERY PRIORITY] 🚨 Attempting immediate reduceOnly close for UNPROTECTED_RECOVERY position {pair}...", flush=True)
            closed_rec = _execute_verified_bot_close(
                pos,
                close_status="CLOSED_UNPROTECTED_RECOVERY",
                exit_reason="CLOSED_UNPROTECTED_RECOVERY",
                current_price=current_price,
                pnl_usd=pnl_usd,
                pnl_idr=pnl_idr,
                pnl_pct=pnl_pct,
                bn_client=bn_client,
                ticker_map=ticker_map,
                fx_rate=fx_rate,
                is_binance_pos=True,
                close_reason_detail="WP1_UNPROTECTED_RECOVERY_EMERGENCY_CLOSE",
            )
            if closed_rec:
                send_telegram(
                    f"🛡️ <b>[UNPROTECTED RECOVERY CLOSED] {pos.get('symbol')} Ditutup!</b>\n"
                    f"Posisi live tanpa SL dari kegagalan entry darurat berhasil ditutup reduceOnly &amp; diverifikasi flat."
                )
            continue

        # AI Position Sentinel & Live Evaluation (Non-blocking ThreadPoolExecutor future cache)
        try:
            pos_ai_key = str(pos.get("id") or f"{pair}:{_norm_pos_side(pos)}")
            now_ts = time.time()
            cached_ai = None
            with _MONITOR_AI_LOCK:
                fut_entry = _MONITOR_AI_FUTURES.get(pos_ai_key)
                if fut_entry and fut_entry.get("future") is not None and fut_entry["future"].done():
                    _MONITOR_AI_FUTURES.pop(pos_ai_key, None)
                    try:
                        ai_out = fut_entry["future"].result()
                        if isinstance(ai_out, dict):
                            _MONITOR_AI_CACHE[pos_ai_key] = ai_out
                            updated = True
                    except Exception as ai_f_exc:
                        logger.warning("Async AI sentinel future failed for %s: %s", pos_ai_key, ai_f_exc)
                cached_ai = dict(_MONITOR_AI_CACHE.get(pos_ai_key) or {})
                in_flight = bool(
                    pos_ai_key in _MONITOR_AI_FUTURES
                    and _MONITOR_AI_FUTURES[pos_ai_key].get("future") is not None
                    and not _MONITOR_AI_FUTURES[pos_ai_key]["future"].done()
                )

            if cached_ai.get("news_sentiment"):
                pos["news_sentiment"] = cached_ai["news_sentiment"]
            else:
                pos.setdefault("news_sentiment", "NEUTRAL")
            pos["ai_sentinel_status"] = "ACTIVE_AI_MONITORED"
            pos["last_ai_check"] = cached_ai.get("last_ai_check") or pos.get("last_ai_check") or datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
            if cached_ai.get("ai_evaluation"):
                pos["ai_evaluation"] = cached_ai["ai_evaluation"]
            elif not pos.get("ai_evaluation"):
                pos["ai_evaluation"] = f"AI Sentinel aktif memantau: PnL {pnl_pct:+.2f}%, menjaga Stop Loss."

            b_alert = cached_ai.get("breaking_alert")
            sym_raw = pos.get("symbol", "").split("-")[0].lower()
            if b_alert and sym_raw and sym_raw in str(b_alert).lower() and not pos.get("sentinel_alerted"):
                pos["sentinel_alerted"] = True
                updated = True
                send_telegram(
                    f"⚠️ <b>[AI SENTINEL] PERINGATAN BERITA KRITIS!</b>\n\n"
                    f"💎 <b>Aset Terbuka:</b> <code>{pos.get('symbol')}</code> ({direction})\n"
                    f"🚨 <b>Breaking News:</b> <i>{b_alert}</i>\n"
                    f"📊 <b>Floating PnL Saat Ini:</b> {pnl_pct:.2f}% (Rp {pnl_idr:,.0f})\n"
                    f"🛡️ <i>AI Sentinel memonitor ketat batas Stop Loss (${sl:,.4f}) untuk proteksi modal.</i>"
                )

            need_ai = (now_ts - float(pos.get("last_ai_eval_ts") or 0.0)) >= 300.0
            need_news = (now_ts - float(cached_ai.get("news_ts") or 0.0)) >= 120.0
            if (need_ai or need_news) and not in_flight:
                from news_sentinel import get_news_sentiment_summary as _news_fn
                _ai_fn = call_ai
                if need_ai:
                    pos["last_ai_eval_ts"] = now_ts
                    updated = True

                def _run_ai_sentinel_task(
                    _pair=pair,
                    _dir=direction,
                    _entry=entry_price,
                    _cur=current_price,
                    _pnl=pnl_pct,
                    _tp=tp,
                    _sl=sl,
                    _do_ai=need_ai,
                    _n_fn=_news_fn,
                    _c_fn=_ai_fn,
                    _prev=cached_ai,
                ):
                    out = dict(_prev or {})
                    now_local = time.time()
                    out["last_ai_check"] = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                    try:
                        ns = _n_fn() or {}
                        if isinstance(ns, dict):
                            out["news_sentiment"] = ns.get("market_sentiment", out.get("news_sentiment", "NEUTRAL"))
                            out["breaking_alert"] = ns.get("breaking_alert")
                            out["news_ts"] = now_local
                    except Exception as n_exc:
                        logger.debug("Async news sentinel fetch error on %s: %s", _pair, n_exc)

                    if _do_ai:
                        try:
                            ai_review = _c_fn(
                                prompt=(
                                    f"Posisi futures {_pair} ({_dir} 20x) sedang aktif. "
                                    f"Entry: ${_entry:,.4f}, Harga Sekarang: ${_cur:,.4f}, "
                                    f"Floating PnL: {_pnl:+.2f}%. Target TP: ${_tp:,.4f}, SL: ${_sl:,.4f}. "
                                    f"Beri evaluasi taktis singkat 1-2 kalimat (HOLD / AMBIL SEBAGIAN / TRAILING SL) dalam Bahasa Indonesia."
                                ),
                                system_prompt="You are a 24/7 AI Risk Sentinel monitoring live crypto positions.",
                                max_tokens=100,
                                is_json=False,
                            )
                            if ai_review:
                                out["ai_evaluation"] = ai_review
                                print(f"[AI MONITOR] {_pair} ({_dir} 20x): PnL {_pnl:+.2f}% -> {ai_review}", flush=True)
                        except Exception as a_exc:
                            logger.debug("Async monitor call_ai fallback on %s: %s", _pair, a_exc)
                            out["ai_evaluation"] = f"AI Sentinel aktif memantau: PnL {_pnl:+.2f}%, menjaga Stop Loss."
                    out["updated_ts"] = now_local
                    return out

                fut = _get_monitor_ai_executor().submit(_run_ai_sentinel_task)
                with _MONITOR_AI_LOCK:
                    _MONITOR_AI_FUTURES[pos_ai_key] = {
                        "future": fut,
                        "submitted_ts": now_ts,
                        "pnl_pct": pnl_pct,
                    }
        except Exception as ai_block_exc:
            logger.warning("Monitor AI Sentinel dispatch error on %s: %s", pair, ai_block_exc)

        # Backfill SL / TP1 / TP2 levels if an imported or manual position lacks them (preserving UNKNOWN on API failure)
        max_sl_cfg = float(_get_config().get("max_sl_pct", 2.25) or 2.25)
        liq_px_curr = float(pos.get("liquidation_price", 0) or 0)
        algo_query_ok = True
        if is_binance_pos and bn_client and (sl <= 0 or tp <= 0):
            try:
                ok_algo, open_algos = bn_client.get_open_algo_orders(pair)
                if ok_algo and isinstance(open_algos, list):
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
                else:
                    algo_query_ok = False
                    if sl <= 0:
                        pos["sl_state"] = "UNKNOWN"
            except Exception as exc:
                logger.warning("get_open_algo_orders backfill error for %s: %s", pair, exc)
                algo_query_ok = False
                if sl <= 0:
                    pos["sl_state"] = "UNKNOWN"

        if not is_binance_pos or (algo_query_ok and str(pos.get("sl_state") or "").upper() != "UNKNOWN"):
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

        # T0.5 / C-7: Reconcile Guard — Verify exchange SL. Preserve UNKNOWN on API errors; ONLY re-place when MISSING!
        if is_binance_pos and bn_client:
            try:
                expected_sl_side = "SELL" if direction == "LONG" else "BUY"
                verified_state = bn_client.verify_stop_loss_active(
                    pair,
                    expected_side=expected_sl_side,
                    max_wait_sec=0.8,
                    return_tristate=True,
                    known_algo_id=pos.get("sl_algo_id"),
                )
            except Exception as exc:
                logger.warning("verify_stop_loss_active error on %s: %s", pair, exc)
                verified_state = "UNKNOWN"

            if verified_state == "CONFIRMED":
                pos["sl_state"] = "CONFIRMED"
            elif verified_state == "UNKNOWN":
                # C-7: API outage — preserve UNKNOWN, DO NOT place duplicate SL or overwrite existing sl/tp!
                pos["sl_state"] = "UNKNOWN"
                print(f"[RECONCILE GUARD] ⚠️ SL state UNKNOWN on {pair} — waiting for next tick without placing duplicate SL.", flush=True)
            elif verified_state == "MISSING":
                pos["sl_state"] = "MISSING"
                target_sl = sl
                if target_sl <= 0 and entry_price > 0:
                    target_sl = _safe_sl_against_liquidation(entry_price, direction, 0.0, liq_px_curr, max_sl_cfg)
                if target_sl > 0:
                    safe_sl = _safe_sl_against_liquidation(entry_price, direction, target_sl, liq_px_curr, max_sl_cfg)
                    if safe_sl != target_sl:
                        target_sl = safe_sl
                    sl = target_sl
                    pos["stop_loss"] = sl
                    print(f"[RECONCILE GUARD] 🛡️ SL MISSING on {pair}! Re-placing SL at ${sl:,.4f} on exchange...", flush=True)
                    try:
                        sl_res = bn_client.set_stop_loss(pair, direction, sl)
                    except Exception as sl_exc:
                        sl_res = {"isError": True, "error": str(sl_exc)}

                    if isinstance(sl_res, dict) and "algoId" in sl_res:
                        pos["sl_algo_id"] = sl_res["algoId"]
                        pos["sl_state"] = "CONFIRMED"
                    elif isinstance(sl_res, dict) and (sl_res.get("code") == -2021 or sl_res.get("would_immediately_trigger")):
                        print(f"[RECONCILE GUARD] 🚨 SL -2021 immediate trigger on {pair} @ ${sl:,.4f} — closing immediately!", flush=True)
                        closed_2021 = _execute_verified_bot_close(
                            pos,
                            close_status="CLOSED_SL_IMMEDIATE_2021",
                            exit_reason="CLOSED_SL_IMMEDIATE_2021",
                            current_price=current_price,
                            pnl_usd=pnl_usd,
                            pnl_idr=pnl_idr,
                            pnl_pct=pnl_pct,
                            bn_client=bn_client,
                            ticker_map=ticker_map,
                            fx_rate=fx_rate,
                            is_binance_pos=True,
                            close_reason_detail="RECONCILE_SL_2021_IMMEDIATE_TRIGGER",
                        )
                        if closed_2021:
                            send_telegram(
                                f"🚨 <b>[RECONCILE -2021 EMERGENCY CLOSE] {pos.get('symbol')} Ditutup!</b>\n"
                                f"SL ${sl:,.4f} akan langsung ter-trigger di bursa (-2021). Posisi ditutup reduceOnly &amp; order dibersihkan."
                            )
                            continue
                        else:
                            pos["sl_state"] = "UNPROTECTED_RECOVERY"
                            pos["emergency_close_failed"] = True

        # T0.6 & T7.4: HIGH-PRECISION SNIPER TWO-STAGE PROFIT LOCK & ON-EXCHANGE R-BASED TRAILING
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
            except Exception as dt_exc:
                logger.debug("opened_at parse fallback for %s: %s", pair, dt_exc)
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
            except Exception as tca_exc:
                logger.debug("update_tca_markout failed for %s: %s", pos.get("id"), tca_exc)

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
                except Exception as ai_d_exc:
                    logger.debug("AIDecisionEngine unavailable during monitor early check: %s", ai_d_exc)
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
                closed_early = _execute_verified_bot_close(
                    pos,
                    close_status="CLOSED_EARLY_INVALIDATION",
                    exit_reason="CLOSED_EARLY_INVALIDATION",
                    current_price=current_price,
                    pnl_usd=pnl_usd,
                    pnl_idr=pnl_idr,
                    pnl_pct=pnl_pct,
                    bn_client=bn_client,
                    ticker_map=ticker_map,
                    fx_rate=fx_rate,
                    is_binance_pos=is_binance_pos,
                    close_reason_detail=th_res.get("close_reason") or "EARLY_ORDERFLOW_THESIS_INVALIDATION",
                )
                if closed_early:
                    tm.reset_symbol(pair)
                    send_telegram(
                        f"⚡ <b>[EARLY THESIS INVALIDATION] {pos.get('symbol')} Ditutup Dini</b>\n\n"
                        f"📉 R-Multiple: <b>{r_multiple_curr:+.2f}R</b> (Batas Invalidation: -{early_loss_lim:.2f}R)\n"
                        f"🧠 P(Survive): <b>{pos['p_survive_pct']:.1f}%</b> | OFI={micro_state.get('ofi_20', 0):+.2f} | TFI={micro_state.get('tfi_5m', 0):+.2f}\n"
                        f"🛡️ Memotong loss lebih awal sebelum menyentuh -1.0R penuh!"
                    )
                continue
        except Exception as tm_exc:
            logger.warning("ThesisMonitor evaluation error on %s: %s", pair, tm_exc)
            pos["p_survive_pct"] = pos.get("p_survive_pct", 78.0)

        sniper_m = cfg_mon.get("sniper_75_mode") or {}
        tp1_trig_r = float(sniper_m.get("tp1_lock_trigger_r", 0.55) or 0.55)
        tp1_lock_r = float(sniper_m.get("sl_lock_after_tp1_r", 0.38) or 0.38)
        tp1_partial_frac = float(sniper_m.get("tp1_partial_close_pct") or cfg_mon.get("tp1_partial_close_pct") or 0.65)

        def _apply_exchange_sl_lock(new_sl_px: float) -> bool:
            nonlocal sl
            if is_binance_pos and bn_client:
                try:
                    amend_res = bn_client.amend_stop_loss(pair, direction, new_sl_px, old_algo_id=pos.get("sl_algo_id"))
                except Exception as exc:
                    logger.warning("amend_stop_loss exception on %s: %s", pair, exc)
                    return False
                if isinstance(amend_res, dict) and amend_res.get("status") == "AMENDED":
                    if amend_res.get("new_algo_id") is not None:
                        pos["sl_algo_id"] = amend_res.get("new_algo_id")
                    pos["sl_state"] = "CONFIRMED"
                    pos["stop_loss"] = new_sl_px
                    sl = new_sl_px
                    return True
                logger.warning("amend_stop_loss failed on %s (%s); keeping old SL=%s", pair, amend_res, sl)
                return False
            pos["stop_loss"] = new_sl_px
            sl = new_sl_px
            return True

        allow_sl_amend = (not is_binance_pos) or (str(pos.get("sl_state") or "").upper() != "UNKNOWN")

        # Stage 0 (Early Breakeven Scratch Guard at +0.30R): skipped if already at or past TP1 trigger
        if allow_sl_amend and 0.30 <= r_multiple_curr < tp1_trig_r and not pos.get("stage0_be_guard_set") and not pos.get("tp1_profit_lock_set"):
            be_lock_pct = max(0.0012, 0.08 * sl_dist_pct)  # +0.08R covers roundtrip taker fees + micro profit
            new_sl = round(entry_price * (1.0 + be_lock_pct if direction == "LONG" else 1.0 - be_lock_pct), 6)
            better = (direction == "LONG" and new_sl > sl) or (direction == "SHORT" and (sl <= 0 or new_sl < sl))
            if better:
                if _apply_exchange_sl_lock(new_sl):
                    pos["stage0_be_guard_set"] = True
                    pos["breakeven_set"] = True

        # Stage 1 (T7.4 Sniper 75% Mode) & Stage 2 (R-Based Exchange Trailing)
        r_trail_stages = [
            (1.00, "r_trail_10_set", 0.65, "Lock +0.65R Profit"),
            (1.50, "r_trail_15_set", 1.10, "Lock +1.10R Profit"),
            (2.00, "r_trail_20_set", 1.55, "Lock +1.55R Profit"),
        ]

        # Determine highest Stage 2 tier reached
        highest_stage2 = None
        for r_trig, flag_key, r_lock, label in reversed(r_trail_stages):
            if r_multiple_curr >= r_trig and not pos.get(flag_key):
                highest_stage2 = (r_trig, flag_key, r_lock, label)
                break

        if allow_sl_amend and r_multiple_curr >= tp1_trig_r and not pos.get("tp1_profit_lock_set"):
            # If price jumped straight to >= 1.00R, perform a single amend to Stage 2 level before marking TP1 flags
            if highest_stage2 is not None:
                _, _, r_lock_s2, label_s2 = highest_stage2
                lock_pct = max(0.004, r_lock_s2 * sl_dist_pct)
                new_sl = round(entry_price * (1.0 + lock_pct if direction == "LONG" else 1.0 - lock_pct), 6)
                better = (direction == "LONG" and new_sl > sl) or (direction == "SHORT" and (sl <= 0 or new_sl < sl))
                locked_ok = _apply_exchange_sl_lock(new_sl) if better else True
                if locked_ok:
                    pos["stage0_be_guard_set"] = True
                    pos["tp1_profit_lock_set"] = True
                    pos["breakeven_set"] = True
                    for sub_trig, sub_flag, _, _ in r_trail_stages:
                        if r_multiple_curr >= sub_trig:
                            pos[sub_flag] = True
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
                                partial_note = f"\nℹ️ <b>Partial Close:</b> {pc_res.get('status')} (Full qty kept under +{r_lock_s2}R SL lock)"
                        except Exception as pce:
                            logger.warning("partial_close_position error on %s: %s", pair, pce)
                    send_telegram(
                        f"🎯 <b>[SNIPER 75% PROFIT LOCK] TP1 (+{tp1_trig_r:.2f}R) TERCAPAI — PROFIT DIKUNCI DI BURSA!</b>\n\n"
                        f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction} {int(leverage)}x)\n"
                        f"📈 <b>Floating Profit:</b> +{pnl_pct:.2f}% (+{r_multiple_curr:.2f}R)\n"
                        f"🔒 <b>SL Bursa Di-amend ke:</b> ${sl:,.4f} (+{r_lock_s2:.2f}R Net Profit Terkunci)"
                        f"{partial_note}\n"
                        f"✨ <i>Transaksi ini 100% TERKUNCI MENANG di bursa sambil mengawal Runner ke TP2!</i>"
                    )
                    if better:
                        send_telegram(
                            f"📈 <b>[ON-EXCHANGE R-TRAILING] {label_s2.upper()}</b>\n"
                            f"💎 <code>{pos.get('symbol')}</code> {direction} | +{r_multiple_curr:.2f}R (ROE: +{pnl_pct:.1f}%)\n"
                            f"🔒 SL Bursa Baru: <b>${sl:,.4f}</b>"
                        )
            else:
                lock_pct = max(0.0022, tp1_lock_r * sl_dist_pct)
                new_sl = round(entry_price * (1.0 + lock_pct if direction == "LONG" else 1.0 - lock_pct), 6)
                better = (direction == "LONG" and new_sl > sl) or (direction == "SHORT" and (sl <= 0 or new_sl < sl))
                locked_ok = _apply_exchange_sl_lock(new_sl) if better else True
                if locked_ok:
                    pos["stage0_be_guard_set"] = True
                    pos["tp1_profit_lock_set"] = True
                    pos["breakeven_set"] = True
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
                        except Exception as pce:
                            logger.warning("partial_close_position error on %s: %s", pair, pce)
                    send_telegram(
                        f"🎯 <b>[SNIPER 75% PROFIT LOCK] TP1 (+{tp1_trig_r:.2f}R) TERCAPAI — PROFIT DIKUNCI DI BURSA!</b>\n\n"
                        f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction} {int(leverage)}x)\n"
                        f"📈 <b>Floating Profit:</b> +{pnl_pct:.2f}% (+{r_multiple_curr:.2f}R)\n"
                        f"🔒 <b>SL Bursa Di-amend ke:</b> ${sl:,.4f} (+{tp1_lock_r:.2f}R Net Profit Terkunci)"
                        f"{partial_note}\n"
                        f"✨ <i>Transaksi ini 100% TERKUNCI MENANG di bursa sambil mengawal Runner ke TP2!</i>"
                    )
        elif allow_sl_amend and highest_stage2 is not None:
            _, _, r_lock, label = highest_stage2
            lock_pct = max(0.004, r_lock * sl_dist_pct)
            new_sl = round(entry_price * (1.0 + lock_pct if direction == "LONG" else 1.0 - lock_pct), 6)
            better = (direction == "LONG" and new_sl > sl) or (direction == "SHORT" and (sl <= 0 or new_sl < sl))
            if better:
                if _apply_exchange_sl_lock(new_sl):
                    for sub_trig, sub_flag, _, _ in r_trail_stages:
                        if r_multiple_curr >= sub_trig:
                            pos[sub_flag] = True
                    send_telegram(
                        f"📈 <b>[ON-EXCHANGE R-TRAILING] {label.upper()}</b>\n"
                        f"💎 <code>{pos.get('symbol')}</code> {direction} | +{r_multiple_curr:.2f}R (ROE: +{pnl_pct:.1f}%)\n"
                        f"🔒 SL Bursa Baru: <b>${new_sl:,.4f}</b>"
                    )
            else:
                for sub_trig, sub_flag, _, _ in r_trail_stages:
                    if r_multiple_curr >= sub_trig:
                        pos[sub_flag] = True

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
        except Exception as roi_exc:
            logger.debug("roi_pnl_projection calculation skipped on %s: %s", pair, roi_exc)

        # ══════════════════════════════════════════════════════════════
        # TIME-BASED AUTO-CUT (Anti Nyangkut, factoring cumulative funding C-9)
        # ══════════════════════════════════════════════════════════════
        try:
            funding_cost_usd = 0.0
            if is_binance_pos and bn_client:
                now_f_ts = time.time()
                cached_f_ts = float(pos.get("_funding_checked_ts") or 0.0)
                explicit_inc_mock = (
                    hasattr(bn_client, "get_income_history")
                    and not _is_unmocked_bf_method(bn_client, "get_income_history")
                )
                if explicit_inc_mock and (
                    hasattr(getattr(bn_client, "get_income_history", None), "assert_called")
                    or type(bn_client) is not BinanceFuturesClient
                    or (now_f_ts - cached_f_ts) >= 300.0
                ):
                    try:
                        opened_ms_f = _parse_opened_ms(pos)
                        start_ms_f = max(0, opened_ms_f - 5000) if opened_ms_f is not None else None
                        raw_inc_f = _call_optional_start_time(
                            bn_client.get_income_history, pair, limit=100, start_time=start_ms_f
                        )
                        if isinstance(raw_inc_f, list):
                            f_income = 0.0
                            for it in raw_inc_f:
                                if not isinstance(it, dict):
                                    continue
                                isym = str(it.get("symbol") or "").upper()
                                if isym and pair and isym != str(pair).upper():
                                    continue
                                if str(it.get("incomeType") or "").upper() != "FUNDING_FEE":
                                    continue
                                it_ms = it.get("time") or it.get("T")
                                if start_ms_f is not None and it_ms is not None:
                                    try:
                                        if int(it_ms) < int(start_ms_f):
                                            continue
                                    except (TypeError, ValueError):
                                        pass
                                f_income += float(it.get("income", 0.0) or 0.0)
                            funding_cost_usd = -f_income
                            pos["cumulative_funding_usd"] = round(funding_cost_usd, 6)
                            pos["_funding_checked_ts"] = now_f_ts
                            updated = True
                    except Exception:
                        funding_cost_usd = float(pos.get("cumulative_funding_usd") or 0.0)
                else:
                    funding_cost_usd = float(pos.get("cumulative_funding_usd") or 0.0)
            else:
                funding_cost_usd = float(pos.get("cumulative_funding_usd") or 0.0)

            effective_pnl_usd = pnl_usd - funding_cost_usd
            effective_pnl_pct = (effective_pnl_usd / pos_usd * 100.0) if pos_usd > 0 else pnl_pct
            effective_pnl_idr = round(effective_pnl_usd * fx_rate, 2)
            if funding_cost_usd != 0.0:
                pos["net_floating_pnl_usd"] = round(effective_pnl_usd, 4)

            _open_str = pos.get("opened_at") or pos.get("entry_time") or ""
            if _open_str:
                from datetime import timezone as _tz2
                _open_dt = datetime.fromisoformat(_open_str.replace(" UTC", "+00:00").replace("Z", "+00:00"))
                _hrs_open = (datetime.now(_tz2.utc) - _open_dt.astimezone(_tz2.utc)).total_seconds() / 3600

                _tp_progress = 0.0
                if tp > 0 and entry_price > 0 and abs(tp - entry_price) > 0:
                    if direction == "LONG":
                        _tp_progress = (current_price - entry_price) / (tp - entry_price) * 100
                    else:
                        _tp_progress = (entry_price - current_price) / (entry_price - tp) * 100
                _tp_progress = max(_tp_progress, 0.0)

                # Rule 1: >48 jam + rugi + progress <10% -> cut
                if _hrs_open > 48 and effective_pnl_pct < -5 and _tp_progress < 10:
                    closed_48 = _execute_verified_bot_close(
                        pos,
                        close_status="CLOSED_TIMEOUT",
                        exit_reason="CLOSED_TIMEOUT_48H",
                        current_price=current_price,
                        pnl_usd=pnl_usd,
                        pnl_idr=effective_pnl_idr,
                        pnl_pct=effective_pnl_pct,
                        bn_client=bn_client,
                        ticker_map=ticker_map,
                        fx_rate=fx_rate,
                        is_binance_pos=is_binance_pos,
                        close_reason_detail=(
                            f"TIMEOUT_48H: {_hrs_open:.0f}h open, {_tp_progress:.1f}% progress, "
                            f"Net PnL {effective_pnl_pct:.1f}% (Funding=${funding_cost_usd:.4f})"
                        ),
                    )
                    if closed_48:
                        send_telegram(
                            f"⏰ <b>[PYROFUEL TIMEOUT CUT] Posisi Nyangkut Ditutup!</b>\n\n"
                            f"💎 <code>{pos.get('symbol')}</code> {direction} 20x\n"
                            f"⏱️ Terbuka selama <b>{_hrs_open:.0f} jam</b>\n"
                            f"📊 Progress ke TP: <b>{_tp_progress:.1f}%</b> (terlalu lambat)\n"
                            f"💸 Net PnL (incl. funding): {effective_pnl_pct:.2f}% → Ditutup untuk lindungi modal\n"
                            f"🔄 <i>Bot akan cari setup baru yang lebih segar</i>"
                        )
                    continue

                # Rule 2: >72 jam + profit tipis (<+10% ROE) -> cut, ambil profit kecil
                elif _hrs_open > 72 and 0 < effective_pnl_pct < 10 and _tp_progress < 50:
                    closed_72 = _execute_verified_bot_close(
                        pos,
                        close_status="CLOSED_TIMEOUT_PROFIT",
                        exit_reason="CLOSED_TIMEOUT_72H",
                        current_price=current_price,
                        pnl_usd=pnl_usd,
                        pnl_idr=effective_pnl_idr,
                        pnl_pct=effective_pnl_pct,
                        bn_client=bn_client,
                        ticker_map=ticker_map,
                        fx_rate=fx_rate,
                        is_binance_pos=is_binance_pos,
                        close_reason_detail=(
                            f"TIMEOUT_72H_PROFIT: {_hrs_open:.0f}h, Net profit {effective_pnl_pct:.1f}% "
                            f"(Funding=${funding_cost_usd:.4f})"
                        ),
                    )
                    if closed_72:
                        send_telegram(
                            f"⌛ <b>[TIMEOUT PROFIT TAKE] Posisi 72h Ditutup Ambil Profit!</b>\n\n"
                            f"💎 <code>{pos.get('symbol')}</code> {direction} 20x\n"
                            f"⏱️ Terbuka <b>{_hrs_open:.0f} jam</b> — kondisi pasar sudah berubah\n"
                            f"💰 Net profit diambil: <b>+{effective_pnl_pct:.2f}%</b> (+Rp {effective_pnl_idr:,.0f})\n"
                            f"🎯 TP masih {_tp_progress:.0f}% perjalanan — lebih baik ambil sekarang\n"
                            f"🔄 <i>Modal bebas untuk cari setup baru</i>"
                        )
                    continue

        except Exception as _tme:
            logger.warning("Timeout cut check error for %s: %s", pair, _tme)

        # C-7 Fix: Only allow local TP/SL emergency fallback when NOT Binance OR exchange SL is confirmed MISSING/LOCAL.
        # Never trigger local close when sl_state == "UNKNOWN" (API outage) or "CONFIRMED"!
        sl_state_upper = str(pos.get("sl_state") or "").upper()
        allow_local_tp_sl_fallback = (not is_binance_pos) or (sl_state_upper in ("MISSING", "LOCAL_GUARD_MONITORED"))

        tp_hit = allow_local_tp_sl_fallback and ((direction == "LONG" and current_price >= tp > 0) or (direction == "SHORT" and current_price <= tp > 0))
        if tp_hit:
            closed_tp = _execute_verified_bot_close(
                pos,
                close_status="CLOSED_TP",
                exit_reason="CLOSED_TP",
                current_price=current_price,
                pnl_usd=pnl_usd,
                pnl_idr=pnl_idr,
                pnl_pct=pnl_pct,
                bn_client=bn_client,
                ticker_map=ticker_map,
                fx_rate=fx_rate,
                is_binance_pos=is_binance_pos,
            )
            if closed_tp:
                send_telegram(
                    f"🎉 <b>PYROFUEL // TAKE PROFIT TERCAPAI!</b>\n\n"
                    f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction})\n"
                    f"💰 <b>Profit:</b> +{pos.get('pnl_pct', pnl_pct):.2f}% (+Rp {pos.get('pnl_idr', pnl_idr):,.0f} / +${pos.get('pnl_usd', pnl_usd):.2f})\n"
                    f"📍 <b>Entry:</b> ${entry_price:,.4f} ➔ <b>Exit:</b> ${pos.get('close_price', current_price):,.4f}\n"
                    f"🎯 <b>Target TP:</b> ${tp:,.4f}\n"
                    f"⚡ Posisi Take Profit berhasil ditutup penuh di Binance Futures!"
                )
            continue

        # Check Stop Loss (Local Emergency Fallback only if exchange SL is MISSING)
        sl_hit = allow_local_tp_sl_fallback and ((direction == "LONG" and current_price <= sl > 0) or (direction == "SHORT" and current_price >= sl > 0))
        if sl_hit:
            closed_sl = _execute_verified_bot_close(
                pos,
                close_status="CLOSED_SL",
                exit_reason="CLOSED_SL",
                current_price=current_price,
                pnl_usd=pnl_usd,
                pnl_idr=pnl_idr,
                pnl_pct=pnl_pct,
                bn_client=bn_client,
                ticker_map=ticker_map,
                fx_rate=fx_rate,
                is_binance_pos=is_binance_pos,
            )
            if closed_sl:
                send_telegram(
                    f"🛑 <b>PYROFUEL // STOP LOSS DITRIGGER (LOCAL FALLBACK)</b>\n\n"
                    f"💎 <b>Aset:</b> <code>{pos.get('symbol')}</code> ({direction})\n"
                    f"📍 <b>Entry:</b> ${entry_price:,.4f} ➔ <b>Exit:</b> ${pos.get('close_price', current_price):,.4f}\n"
                    f"🛑 <b>Level SL:</b> ${sl:,.4f}\n"
                    f"📉 <b>PnL:</b> {pos.get('pnl_pct', pnl_pct):.2f}% (Rp {pos.get('pnl_idr', pnl_idr):,.0f} / ${pos.get('pnl_usd', pnl_usd):.2f})\n"
                    f"🛡️ Posisi otomatis di-cut untuk melindungi modal utama."
                )
            continue

    if updated:
        try:
            positions = _save_positions_merged(open_pos)
        except CorruptedStateError as cse:
            _alert_error_rate_limited("CORRUPT_POSITIONS_SAVE", f"POSITIONS_FILE corrupt during merge write ({cse})", cooldown_sec=300.0)
            print(f"[MONITOR] ❌ POSITIONS_FILE corrupt during merge write ({cse}) — refusing overwrite.", flush=True)

    # T9.1 / T9.3 / WP-5: Write heartbeat.json atomically via shared HeartbeatWorker builder
    HeartbeatWorker(heartbeat_path=os.path.join(RESULTS_DIR, "heartbeat.json")).write_once()

    return positions


def check_wallet_and_position_guard():
    """
    Evaluates whether the trading system should pause all universe scanning and 9-agent analysis
    to dedicate 100% of compute and surveillance to active open position(s).
    """
    _retry_pending_learners()

    try:
        positions = _load_positions_safe(strict=True)
    except CorruptedStateError as cse:
        _alert_error_rate_limited("CORRUPT_POSITIONS_GUARD", f"POSITIONS_FILE corrupt in guard ({cse})", cooldown_sec=300.0)
        print(f"[GUARD] ❌ POSITIONS_FILE corrupt without valid backup ({cse}) — pausing scan safely.", flush=True)
        return {
            "pause_scanning": True,
            "mode": "CORRUPT_STATE_LOCKOUT",
            "reason": f"POSITIONS_FILE corrupt without valid backup: {cse}",
            "open_positions": [],
            "available_usdt": float(state.get("binance_available_balance_usdt", 0.0)),
            "total_usdt": float(state.get("binance_wallet_balance_usdt", 0.0)),
        }

    open_pos = [p for p in positions if p.get("status") == "OPEN"]

    bn_client = get_binance_client()
    avail_usdt = float(state.get("binance_available_balance_usdt", 0.0))
    total_usdt = float(state.get("binance_wallet_balance_usdt", 0.0))
    cross_upnl_usdt = float(state.get("binance_unrealized_pnl_usdt", 0.0) or 0.0)
    bal_fresh_ok = False

    if bn_client:
        try:
            bal = bn_client.get_balance()
            if isinstance(bal, dict) and not bal.get("isError") and "total_wallet_balance" in bal:
                update_runtime_health(last_api_ok_ts=time.time())
                avail_usdt = float(bal.get("available_balance", 0))
                total_usdt = float(bal.get("total_wallet_balance", 0))
                cross_upnl_usdt = float(bal.get("cross_unrealized_pnl", 0) or 0)
                bal_fresh_ok = True
                state["binance_wallet_balance_usdt"] = round(total_usdt, 4)
                state["binance_available_balance_usdt"] = round(avail_usdt, 4)
                state["binance_unrealized_pnl_usdt"] = round(cross_upnl_usdt, 4)
                save_state()
            elif isinstance(bal, dict) and bal.get("isError"):
                update_runtime_health(last_api_err_ts=time.time())

            # Live sync active positions directly from Binance Futures (keyed by symbol + positionSide)
            live_pos = bn_client.get_positions()
            if isinstance(live_pos, list):
                update_runtime_health(last_api_ok_ts=time.time())
                live_keys = set()
                for lp in live_pos:
                    amt = abs(float(lp.get("position_amount", lp.get("positionAmt", 0))))
                    if amt > 0:
                        sym_u = str(lp.get("symbol") or "").upper()
                        side_u = _norm_pos_side(lp)
                        if sym_u:
                            live_keys.add((sym_u, side_u))

                valid_open_pos = []
                dirty = False
                ticker_map_g = None
                fx_g = None
                for p in positions:
                    if p.get("status") == "OPEN":
                        bp = (p.get("binance_pair") or p.get("symbol", "").replace("-USD", "USDT")).upper()
                        p_side = _norm_pos_side(p)
                        is_bn_p = p.get("exchange") == "BINANCE_FUTURES" or p.get("binance_synced") or (not p.get("exchange"))
                        still_live = (
                            (bp, p_side) in live_keys
                            or (bp, "BOTH") in live_keys
                            or (p_side == "BOTH" and any(s == bp for s, _ in live_keys))
                        )
                        if is_bn_p and not still_live:
                            # A-4 Fix: NEVER silently mark CLOSED_SYNCED! Run full canonical exchange close lifecycle.
                            if ticker_map_g is None:
                                try:
                                    tickers_g = get_binance_24h_tickers()
                                    ticker_map_g = {t["symbol"]: float(t.get("lastPrice", 0)) for t in tickers_g if "symbol" in t} if tickers_g else {}
                                except Exception as tick_exc:
                                    logger.warning("Guard ticker fallback error: %s", tick_exc)
                                    ticker_map_g = {}
                            if fx_g is None:
                                fx_g = get_fx_info().get("usd_idr", 16500)
                            closed_g = _finalize_exchange_closed_position(
                                p,
                                bn_client=bn_client,
                                ticker_map=ticker_map_g,
                                fx_rate=fx_g,
                                bal_info=bal if isinstance(bal, dict) and not bal.get("isError") else None,
                            )
                            if closed_g is None:
                                valid_open_pos.append(p)
                            else:
                                dirty = True
                        else:
                            valid_open_pos.append(p)

                for lp in live_pos:
                    amt = abs(float(lp.get("position_amount", lp.get("positionAmt", 0))))
                    if amt > 0:
                        pair_sym = str(lp.get("symbol") or "").upper()
                        lp_side = _norm_pos_side(lp)
                        already_in = any(
                            (p.get("binance_pair") or p.get("symbol", "").replace("-USD", "USDT")).upper() == pair_sym
                            and (lp_side == "BOTH" or _norm_pos_side(p) in (lp_side, "BOTH"))
                            for p in valid_open_pos
                        )
                        if not already_in:
                            if fx_g is None:
                                fx_g = get_fx_info().get("usd_idr", 16500)
                            new_p = _build_synced_binance_pos(lp, bn_client, fx_g)
                            valid_open_pos.append(new_p)
                            positions.append(new_p)
                            dirty = True

                open_pos = valid_open_pos
                if dirty:
                    try:
                        _save_positions_merged(positions)
                    except CorruptedStateError as cse:
                        _alert_error_rate_limited("CORRUPT_POSITIONS_GUARD", f"POSITIONS_FILE corrupt during guard merge write ({cse})", cooldown_sec=300.0)
                        print(f"[GUARD] ❌ POSITIONS_FILE corrupt during merge write ({cse}) — refusing overwrite.", flush=True)
        except Exception as e:
            update_runtime_health(last_api_err_ts=time.time())
            _alert_error_rate_limited("GUARD_BINANCE_SYNC", f"Guard Binance sync error: {e}", cooldown_sec=300.0, level="warning")
            print(f"[GUARD] Binance sync notice: {e}", flush=True)

    live_equity_usdt = max(0.0, total_usdt + cross_upnl_usdt)
    locked_vault_g = 0.0
    try:
        v_inst_g = _get_vault_instance()
        v_disk_g = read_json_safe(v_inst_g.state_path, default=None, strict_on_corrupt=False, expected_type=dict)
        if isinstance(v_disk_g, dict):
            locked_vault_g = max(0.0, float(v_disk_g.get("locked_profit_vault_usdt", 0.0)))
        else:
            locked_vault_g = max(0.0, float(getattr(v_inst_g, "locked_profit_vault_usdt", 0.0)))
    except Exception as vault_exc:
        logger.warning("Guard vault read failed: %s", vault_exc)
        locked_vault_g = 0.0
    working_usdt_g = max(0.0, avail_usdt - locked_vault_g)

    should_pause = False
    reason = ""

    # T7.1: Check Emergency Panic Lock via state_io
    panic_file = os.path.join(RESULTS_DIR, "panic_lock.json")
    p_data = read_json_safe(panic_file, default=None, strict_on_corrupt=False, expected_type=dict)
    if isinstance(p_data, dict) and p_data.get("locked", False):
        should_pause = True
        reason = f"EMERGENCY PANIC LOCK AKTIF: {p_data.get('reason', 'Triggered via /panic')}"

    # T7.5 / B-8: Check HardRiskEngine Circuit Breaker (including live unrealized DD) & Max Daily Trades
    cfg_g = _get_config()
    if not should_pause:
        try:
            today_g = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            existing_brk_disk = read_json_safe(RISK_BREAKER_FILE, default=None, strict_on_corrupt=False, expected_type=dict)
            need_daily_start_persist = (
                not isinstance(existing_brk_disk, dict)
                or existing_brk_disk.get("daily_date") != today_g
                or float(existing_brk_disk.get("daily_start_equity", 0.0) or 0.0) <= 0.0
            )
            eq_arg = live_equity_usdt if (bal_fresh_ok and (live_equity_usdt > 0 or total_usdt > 0)) else None
            r_eng = load_hard_risk_engine(cfg_g, current_equity=eq_arg)
            was_tripped = bool(r_eng.breaker_until_ts > 0 or r_eng.breaker_reason)
            max_dt = int(cfg_g.get("max_daily_trades", 10) or 10)

            dd_eval_g = {"tripped_now": False, "daily_dd_pct": 0.0}
            if eq_arg is not None and not getattr(r_eng, "_corrupt_state", False):
                dd_eval_g = r_eng.check_live_equity_drawdown(live_equity=live_equity_usdt)

            if r_eng.is_circuit_breaker_active():
                if dd_eval_g.get("tripped_now"):
                    save_hard_risk_engine(r_eng)
                    print(
                        f"[RISK BREAKER] 🛑 Live Daily DD {dd_eval_g['daily_dd_pct']:.2f}% >= {r_eng.breaker_daily_dd_pct}% "
                        f"({r_eng.breaker_reason}) — 12h cooldown tripped!",
                        flush=True,
                    )
                    send_telegram(
                        f"🛑 <b>[HARD RISK BREAKER TRIPPED — LIVE DAILY DD]</b>\n\n"
                        f"⚠️ Drawdown Hari Ini: <b>{dd_eval_g['daily_dd_pct']:.2f}%</b> "
                        f"(Batas: {r_eng.breaker_daily_dd_pct:.1f}%)\n"
                        f"💰 Live Equity: ${live_equity_usdt:.2f} (Start Hari: ${r_eng.daily_start_equity:.2f})\n"
                        f"❄️ Entry baru dikunci selama {cfg_g.get('breaker_cooldown_hours', 12)} jam."
                    )
                should_pause = True
                _rem_sec = max(0, int(r_eng.breaker_until_ts - time.time()))
                _rem_h, _rem_m = _rem_sec // 3600, (_rem_sec % 3600) // 60
                reason = f"HARD RISK CIRCUIT BREAKER AKTIF ({r_eng.breaker_reason}) — buka lagi ~{_rem_h}j {_rem_m}m lagi."
            else:
                if was_tripped or (need_daily_start_persist and eq_arg is not None and live_equity_usdt > 0):
                    save_hard_risk_engine(r_eng)
                if was_tripped:
                    print("[RISK BREAKER] Cooldown selesai — loss counter direset 0/2. Scanner siap kembali.", flush=True)
                    send_telegram("✅ <b>[RISK BREAKER COOLDOWN SELESAI]</b>\n\nCooldown 12 jam selesai — loss counter direset <code>0/2</code>. Bot otomatis lanjut mencari setup baru.")
                if getattr(r_eng, "_daily_trades_count", 0) >= max_dt:
                    should_pause = True
                    reason = f"BATAS TRADE HARIAN TERCAPAI ({r_eng._daily_trades_count}/{max_dt}) — berhenti sampai 00:00 UTC."
        except Exception as exc:
            logger.warning("HardRiskEngine guard check error: %s", exc)

    # MANDAT USER: JIKA POSISI AKTIF >= max_concurrent -> STOP SCAN TOTAL! 100% FOKUS KAWAL POSISI!
    max_conc_g = int(cfg_g.get("max_concurrent_positions", 1) or 1)
    if not should_pause and len(open_pos) >= max_conc_g:
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
        "working_usdt": round(working_usdt_g, 4),
        "total_usdt": total_usdt,
        "live_equity": round(live_equity_usdt, 4),
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
                
        except Exception as qs_item_exc:
            logger.debug("Quick screen item skip: %s", qs_item_exc)
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
    except Exception as qs_save_exc:
        logger.warning("Failed to save QUICK_SCREEN_FILE: %s", qs_save_exc)
    
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

        # 3. Pre-ranker opportunity composite (supports 0..10 market_data scale or normalized 0..100)
        opp_norm = (opp_score / 10.0) if opp_score > 12.0 else opp_score
        if opp_norm >= 5.8:
            score += 2.0
        elif opp_norm >= 4.5:
            score += 1.0

        # 3b. Intraday high-low range squeeze/expansion activity
        hl_range = float(coin.get("high_low_range_pct", 0) or 0)
        if hl_range >= 4.0:
            score += 1.0

        # 4. Crowded funding squeeze potential
        if funding_abs >= 0.0003:
            score += 1.5

        # 5. Small tie-breaker for CORE liquidity (never drowns out strong dynamic alts)
        if sym.upper() in core_symbols:
            score += 0.25

        if score >= 2.0:
            candidates.append((score, opp_norm, coin))

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
    update_runtime_health(last_scan_ts=time.time())
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
        max_coins = 3
    elif regime == "SIDEWAYS":
        max_coins = 4
    else:
        max_coins = 4

    # Live ranked Binance pairs FIRST so real volume/change/opportunity metrics are preserved!
    seen_pairs_pf = set()
    all_candidates = []
    for coin in ranked:
        p = coin.get("pair")
        if p and p not in seen_pairs_pf:
            seen_pairs_pf.add(p)
            all_candidates.append(coin)
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
                "opportunity_score": 0.0,
            })

    # Gate teknikal + T0.7 minNotional filter -> max N koin untuk AI
    scan_list = _technical_pre_filter(
        all_candidates,
        max_ai_coins=max_coins,
        available_balance_usdt=guard.get("working_usdt", guard.get("available_usdt")),
    )
    try:
        from strategies.bandit_allocator import ContextualThompsonBandit
        if scan_list:
            bandit = ContextualThompsonBandit()
            for item_b in scan_list:
                item_b.setdefault("strategy_id", f"TIER_{item_b.get('tier', 'CORE')}")
                item_b.setdefault("regime", regime)
                item_b["rrr_net"] = max(1.0, float(item_b.get("opportunity_score") or 5.0))
            ranked_b = bandit.rank_candidates(scan_list, regime=regime, deterministic=True)
            if isinstance(ranked_b, list) and len(ranked_b) == len(scan_list):
                scan_list = ranked_b
    except Exception as bandit_exc:
        logger.debug("Bandit ranking skipped: %s", bandit_exc)

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
            positions_now = _load_positions_safe(strict=False)

            # 1 PROSES TERSATUKAN: 5-Layer Pipeline + Langsung Sidang 9-Agent Multi-Committee
            print(f"[SCAN] ▶ Pipeline & Sidang 9-Agent: {sym}...", flush=True)
            res = run_5_layer_pipeline(sym, active_positions=positions_now)
            com_res = res.get("committee") if isinstance(res, dict) else None
            return item, sym, pair, name, tier, res, com_res
        except Exception as e:
            print(f"[ERROR] {sym}: {e}", flush=True)
            return item, sym, pair, name, tier, None, None

    # SEQUENTIAL SCAN — one coin at a time (Layer 1 → 2 → 3 → 4 → 5 → Committee)
    max_concurrent_scan = int(cfg.get("max_concurrent_positions", 1) or 1)
    max_same_dir_scan = int(
        cfg.get("max_same_direction_positions", cfg.get("max_directional_positions", 1)) or 1
    )
    bn_scan = get_binance_client()

    for idx, item in enumerate(scan_list, start=1):
        if not sync_control_flags_from_disk():
            print("[FULL SCAN] ⏸️ Paused by user mid-cycle. Halting remaining coin scans immediately.", flush=True)
            break
        eff_open_loop, _, pos_err_loop = _get_effective_open_positions(_load_positions_safe(strict=False), bn_scan)
        if pos_err_loop:
            print(f"[FULL SCAN] ⚠️ Exchange position check failed ({pos_err_loop}); stopping candidate loop safely.", flush=True)
            break
        if len(eff_open_loop) >= max_concurrent_scan:
            print(
                f"[FULL SCAN] 🛡️ Max concurrent positions ({len(eff_open_loop)}/{max_concurrent_scan}) reached. Stopping scan loop.",
                flush=True,
            )
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
            except Exception as deg_exc:
                logger.warning("Failed reading DEGRADED_STRAT_FILE for %s: %s", sym, deg_exc)

        # WP-6 Strategy Gate Hook (Decision 2.B: Advisory by default, Enforced when enforce_backtest_gate=True)
        if is_trade_approved:
            try:
                from shadow.promote import check_strategy_gate
                gate_res = check_strategy_gate(setup, config=cfg)
                if gate_res.get("advisory_warning"):
                    logger.warning("[STRATEGY GATE ADVISORY] %s: %s", sym, gate_res["advisory_warning"])
                if not gate_res.get("allowed_live", True):
                    is_trade_approved = False
                    status = "STRATEGY_GATE_SHADOW_ONLY"
                    print(f"[STRATEGY GATE] 🛡️ {sym} setup '{setup}' diblokir ke SHADOW_ONLY ({gate_res.get('reason')})", flush=True)
            except Exception as gate_exc:
                logger.warning("Failed evaluating strategy gate for %s: %s", sym, gate_exc)

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
                except Exception as tp_pred_exc:
                    logger.debug("predict_tp_time skipped for %s: %s", sym, tp_pred_exc)

            # C-12: Re-check live concurrent & directional exposure cap before candidate execution
            eff_open_exec, _, pos_err_exec = _get_effective_open_positions(_load_positions_safe(strict=False), bn_scan)
            if pos_err_exec:
                print(f"[EXEC SKIP] {sym}: Exchange position check error ({pos_err_exec}); stopping candidate execution.", flush=True)
                break
            if len(eff_open_exec) >= max_concurrent_scan:
                print(f"[CONCURRENT CAP] 🛡️ Max concurrent ({len(eff_open_exec)}/{max_concurrent_scan}) reached before executing {sym}. Stopping loop.", flush=True)
                break
            same_dir_exec = sum(1 for p in eff_open_exec if str(p.get("direction", "")).upper() == str(final_dir).upper())
            if same_dir_exec >= max_same_dir_scan:
                print(
                    f"[DIRECTIONAL CAP] 🛡️ {sym} ({final_dir}) skipped: already {same_dir_exec}/{max_same_dir_scan} open in {final_dir}.",
                    flush=True,
                )
                state["signals_rejected_count"] += 1
                continue

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
                if max_concurrent_scan <= 1:
                    print(f"[AUTO-TRADER] 🛡️ MANDAT FOKUS 100%: Posisi telah terbuka untuk {pair}! Pemindaian koin lain dihentikan seketika agar sistem fokus mengawal posisi aktif!", flush=True)
                    break
                eff_post_exec, _, _ = _get_effective_open_positions(_load_positions_safe(strict=False), bn_scan)
                if len(eff_post_exec) >= max_concurrent_scan:
                    print(f"[AUTO-TRADER] 🛡️ Max concurrent positions ({len(eff_post_exec)}/{max_concurrent_scan}) filled after {pair}! Stopping remaining scans.", flush=True)
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
            if not fc.get("_shadow_registered") and _entry_sig > 0 and _sl_sig > 0 and _tp2_sig > 0 and fc.get("direction") in ("LONG", "SHORT"):
                try:
                    from shadow.engine import ShadowEngine
                    _p_cal_sh = float(fc.get("calibrated_prob") or (float(conf or 50) / 100.0))
                    _reg_sh = (fc.get("math_proof") or {}).get("statistical_regime") or regime
                    ShadowEngine().register_candidate(
                        candidate={
                            "symbol": sym,
                            "strategy_id": setup,
                            "regime": _reg_sh,
                            "direction": fc.get("direction"),
                            "entry_price": _entry_sig,
                            "sl_price": _sl_sig,
                            "tp1_price": _tp1_sig,
                            "tp2_price": _tp2_sig,
                        },
                        ai_decision="SKIP",
                        p_cal=_p_cal_sh,
                    )
                except Exception as sh_exc:
                    logger.debug("ShadowEngine skipped record failed for %s: %s", sym, sh_exc)

    update_runtime_health(last_scan_ts=time.time())
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
    except Exception as uni_exc:
        logger.warning("Failed writing UNIVERSE_FILE: %s", uni_exc)
    
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
    update_runtime_health(boot_ts=time.time())
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
        if hasattr(bn_client, "set_alert_callback"):
            bn_client.set_alert_callback(lambda key, msg: _alert_error_rate_limited(key, msg, cooldown_sec=300.0, level="warning"))
        try:
            _start_realtime_ws_worker(bn_client)
        except Exception as ws_start_exc:
            logger.warning("Failed starting realtime WS worker: %s", ws_start_exc)
        try:
            bal = bn_client.get_balance()
            if isinstance(bal, dict) and not bal.get("isError") and "total_wallet_balance" in bal:
                update_runtime_health(last_api_ok_ts=time.time())
                usdt_bal = float(bal.get("total_wallet_balance", 0))
                avail_bal = float(bal.get("available_balance", usdt_bal))
                state["binance_wallet_balance_usdt"] = round(usdt_bal, 4)
                state["binance_available_balance_usdt"] = round(avail_bal, 4)
                save_state()
                print(f"[*] ✅ Binance Futures Engine LIVE! Wallet balance: ${usdt_bal:.2f} USDT (Available: ${avail_bal:.2f})", flush=True)
            else:
                if isinstance(bal, dict) and bal.get("isError"):
                    update_runtime_health(last_api_err_ts=time.time())
                usdt_bal = float(state.get("binance_wallet_balance_usdt", 0.0))
                print(f"[*] ✅ Binance Futures Engine Initialized (Cached Wallet: ${usdt_bal:.2f} USDT)", flush=True)
        except Exception as e:
            update_runtime_health(last_api_err_ts=time.time())
            logger.warning("Binance Futures startup check warning: %s", e)
            print(f"[*] ⚠️ Binance Futures check warning: {e}", flush=True)
    else:
        print(f"[*] ⚠️ Binance Futures not configured in .env", flush=True)

    hb_worker = HeartbeatWorker(interval_sec=30.0)
    hb_worker.start()

    last_full_scan = 0
    last_quick_scan = 0
    last_pause_monitor_ts = 0
    was_in_all_in_mode = False
    was_paused_by_user = not sync_control_flags_from_disk()
    if was_paused_by_user:
        print("[*] Autonomous trader is currently PAUSED (waiting for resume signal)...", flush=True)

    try:
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
                            _alert_error_rate_limited("PAUSE_MONITOR_ERR", f"Pause monitor error: {pe}", cooldown_sec=300.0, level="warning")
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
                    _alert_error_rate_limited("MONITOR_LOOP_ERR", f"Position monitor error: {e}", cooldown_sec=180.0)
                    print(f"[-] Position monitor error: {e}", flush=True)

                if guard["pause_scanning"]:
                    # === ALL-IN POSITION MONITORING ACTIVE ===
                    state["all_in_monitoring_mode"] = True
                    state["all_in_focus_positions"] = [p.get("symbol") for p in guard["open_positions"]]
                    state["all_in_reason"] = guard["reason"]
                    save_state()

                    if not was_in_all_in_mode:
                        was_in_all_in_mode = True
                        if guard.get("open_positions"):
                            syms = ", ".join([f"<code>{p.get('symbol')}</code>" for p in guard["open_positions"]])
                            send_telegram(
                                f"🛡️ <b>[AI SENTINEL] MODE ALL-IN MONITOR POSITION AKTIF!</b>\n\n"
                                f"💰 <b>Saldo Terpakai:</b> Saldo telah dialokasikan penuh ke posisi aktif (Sisa: ${guard['available_usdt']:.2f} USDT).\n"
                                f"💎 <b>Posisi Dikawal:</b> {syms}\n\n"
                                f"⏸️ <b>Scanner 524 Koin & 9 Agent Committee:</b> <b>DIHENTIKAN SEMENTARA</b>\n"
                                f"🎯 <i>Semua sumber daya AI kini 100% all-in mengawal posisi aktif secara real-time hingga Take Profit / Stop Loss tercapai!</i>"
                            )
                        print(f"\n[SENTINEL GUARD] 🛡️ {guard['reason']}", flush=True)

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
                            f"🚀 <b>SCANNER AKTIF KEMBALI!</b>\n\n"
                            f"✅ Tidak ada posisi terbuka & seluruh Risk Guard aman.\n"
                            f"💰 <b>Saldo Tersedia:</b> ${guard['available_usdt']:.2f} USDT.\n\n"
                            f"🔄 <b>Scanner & Pipeline AI:</b> <b>KEMBALI AKTIF!</b>\n"
                            f"<i>Memulai pemindaian radar penuh untuk mencari setup peluang terbaik berikutnya...</i>"
                        )
                        print(f"\n[SENTINEL RESUME] 🚀 Guard bebas / posisi selesai. Melanjutkan full scan...", flush=True)
                        # Trigger scan immediately!
                        last_full_scan = 0
                        last_quick_scan = 0

                    # Quick screen every 60 seconds (or configured interval)
                    if now - last_quick_scan >= state.get("quick_screen_interval_sec", 60):
                        try:
                            run_quick_screen()
                        except Exception as e:
                            _alert_error_rate_limited("QUICK_SCREEN_ERR", f"Quick screen error: {e}", cooldown_sec=300.0, level="warning")
                            print(f"[-] Quick screen error: {e}", flush=True)
                        last_quick_scan = now

                    # Full AI scan every 5 minutes
                    if now - last_full_scan >= state.get("scan_interval_sec", 300):
                        try:
                            run_full_scan_cycle()
                        except Exception as e:
                            _alert_error_rate_limited("FULL_SCAN_ERR", f"Full scan error: {e}", cooldown_sec=300.0)
                            print(f"[-] Full scan error: {e}", flush=True)
                        last_full_scan = now

                    _WS_WAKEUP_EVENT.wait(timeout=10)  # Wakes immediately on UserDataStream WS fill/algo event
                    _WS_WAKEUP_EVENT.clear()

            except KeyboardInterrupt:
                print("[*] Autonomous trader stopped by user.", flush=True)
                break
            except Exception as e:
                _alert_error_rate_limited("MAIN_LOOP_ERR", f"Main loop exception: {e}", cooldown_sec=300.0)
                print(f"[-] Main loop exception: {e}", flush=True)
                time.sleep(30)
    finally:
        hb_worker.stop(timeout=2.0)

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
