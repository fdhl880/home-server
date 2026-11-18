"""
===========================================================================
PYROFUEL HIGH-WATER MARK PROFIT RATCHET VAULT v3.0 (T7.3)
===========================================================================
Protects accumulated profits under `20x ISOLATED ALL_IN` sizing:
- Persists `initial_session_equity`, `high_water_mark_equity`, and
  `locked_profit_vault_usdt` in `results/vault_state.json`.
- Whenever realized account equity reaches or exceeds `HWM * 1.15` (+15% growth
  above the previous High-Water Mark):
    delta_profit = current_equity - high_water_mark_equity
    locked_profit_vault_usdt += 0.35 * delta_profit
    high_water_mark_equity = current_equity
- When computing `ALL_IN` margin, only active working capital is exposed:
    working_balance = max(0.0, available_balance - locked_profit_vault_usdt)
    margin_all_in   = 0.95 * working_balance
  ensuring locked profits are NEVER burned even during a 2-loss circuit-breaker
  drawdown or tail-risk event.
===========================================================================
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from state_io import CorruptedStateError, atomic_write_json, get_file_lock, read_json_safe

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_VAULT_STATE_PATH = os.path.join(BASE_DIR, "results", "vault_state.json")

_VAULT_SINGLETON_LOCK = threading.RLock()
_VAULT_SINGLETONS: Dict[str, "ProfitRatchetVault"] = {}


class ProfitRatchetVault:
    """
    High-Water Mark Profit Ratchet Vault (T7.3).
    """

    def __init__(
        self,
        initial_equity: float = 0.0,
        state_path: Optional[str] = None,
        ratchet_step_pct: float = 0.15,
        lock_fraction: float = 0.35,
        persist: bool = True,
    ):
        self.state_path = state_path or DEFAULT_VAULT_STATE_PATH
        self.ratchet_step_pct = float(ratchet_step_pct)
        self.lock_fraction = float(lock_fraction)
        self.persist = bool(persist)
        self._lock = get_file_lock(self.state_path) if (self.persist and self.state_path) else threading.RLock()
        self._state_corrupt = False

        self.initial_session_equity: float = float(initial_equity)
        self.baseline_equity: float = float(initial_equity)
        self.high_water_mark_equity: float = float(initial_equity)
        self.locked_profit_vault_usdt: float = 0.0
        self.net_transfers_usdt: float = 0.0
        self.ratchet_events: List[Dict[str, Any]] = []
        self.transfer_events: List[Dict[str, Any]] = []

        loaded = self._load_state()
        if not self._state_corrupt:
            if initial_equity > 0 and self.high_water_mark_equity <= 0:
                self.initial_session_equity = float(initial_equity)
                self.baseline_equity = float(initial_equity)
                self.high_water_mark_equity = float(initial_equity)
                self._save_state()
            elif initial_equity > 0 and not loaded and self.persist and self.state_path:
                self._save_state()

    def _load_state(self) -> bool:
        if not self.persist or not self.state_path:
            return False
        with self._lock:
            try:
                data = read_json_safe(
                    self.state_path,
                    default=None,
                    strict_on_corrupt=True,
                    expected_type=dict,
                )
            except CorruptedStateError as exc:
                self._state_corrupt = True
                logger.error("ProfitVault state corrupt at %s (%s); refusing to overwrite.", self.state_path, exc)
                return False

            self._state_corrupt = False
            if isinstance(data, dict):
                self.initial_session_equity = float(
                    data.get("initial_session_equity", self.initial_session_equity)
                )
                self.high_water_mark_equity = float(
                    data.get("high_water_mark_equity", self.high_water_mark_equity)
                )
                self.baseline_equity = float(
                    data.get("baseline_equity", self.initial_session_equity or self.baseline_equity)
                )
                self.locked_profit_vault_usdt = float(
                    data.get("locked_profit_vault_usdt", self.locked_profit_vault_usdt)
                )
                self.net_transfers_usdt = float(
                    data.get("net_transfers_usdt", self.net_transfers_usdt)
                )
                self.ratchet_events = list(data.get("ratchet_events", []))
                self.transfer_events = list(data.get("transfer_events", []))
                return True
            return False

    def _save_state(self) -> None:
        if not self.persist or not self.state_path or self._state_corrupt:
            return
        with self._lock:
            payload = {
                "initial_session_equity": round(self.initial_session_equity, 6),
                "baseline_equity": round(self.baseline_equity, 6),
                "high_water_mark_equity": round(self.high_water_mark_equity, 6),
                "locked_profit_vault_usdt": round(self.locked_profit_vault_usdt, 6),
                "net_transfers_usdt": round(self.net_transfers_usdt, 6),
                "ratchet_step_pct": self.ratchet_step_pct,
                "lock_fraction": self.lock_fraction,
                "ratchet_events": self.ratchet_events[-50:],
                "transfer_events": self.transfer_events[-50:],
                "updated_at": int(time.time()),
            }
            ok = atomic_write_json(self.state_path, payload, make_bak=True)
            if not ok:
                logger.error("Failed to persist ProfitVault state to %s", self.state_path)

    def update_equity(self, current_equity: float) -> Dict[str, Any]:
        """
        Evaluate `current_equity` against `high_water_mark_equity * (1 + ratchet_step_pct)`.
        Locks `35%` of new profit whenever equity exceeds `HWM * 1.15`.
        """
        eq = max(0.0, float(current_equity))
        with self._lock:
            if self.persist and self.state_path and os.path.exists(self.state_path):
                self._load_state()
                if self._state_corrupt:
                    return {
                        "ratcheted": False,
                        "newly_locked_usdt": 0.0,
                        "locked_profit_vault_usdt": self.locked_profit_vault_usdt,
                        "high_water_mark_equity": self.high_water_mark_equity,
                        "working_balance_usdt": self.get_working_balance(eq),
                        "error": "VAULT_STATE_CORRUPT",
                    }

            if self.high_water_mark_equity <= 0.0 and eq > 0.0:
                self.initial_session_equity = eq
                self.baseline_equity = eq
                self.high_water_mark_equity = eq
                self._save_state()
                return {
                    "ratcheted": False,
                    "newly_locked_usdt": 0.0,
                    "locked_profit_vault_usdt": self.locked_profit_vault_usdt,
                    "high_water_mark_equity": self.high_water_mark_equity,
                    "baseline_equity": self.baseline_equity,
                    "working_balance_usdt": self._get_working_balance_locked(eq),
                }

            threshold = self.high_water_mark_equity * (1.0 + self.ratchet_step_pct)
            if eq >= threshold - 1e-9 and self.high_water_mark_equity > 0:
                delta_profit = eq - self.high_water_mark_equity
                newly_locked = self.lock_fraction * delta_profit
                prev_hwm = self.high_water_mark_equity
                self.locked_profit_vault_usdt += newly_locked
                self.high_water_mark_equity = eq
                event = {
                    "ts": int(time.time()),
                    "prev_hwm": round(prev_hwm, 6),
                    "new_hwm": round(eq, 6),
                    "delta_profit": round(delta_profit, 6),
                    "newly_locked_usdt": round(newly_locked, 6),
                    "total_locked_usdt": round(self.locked_profit_vault_usdt, 6),
                }
                self.ratchet_events.append(event)
                self._save_state()
                return {
                    "ratcheted": True,
                    "newly_locked_usdt": newly_locked,
                    "locked_profit_vault_usdt": self.locked_profit_vault_usdt,
                    "high_water_mark_equity": self.high_water_mark_equity,
                    "baseline_equity": self.baseline_equity,
                    "working_balance_usdt": self._get_working_balance_locked(eq),
                }

            return {
                "ratcheted": False,
                "newly_locked_usdt": 0.0,
                "locked_profit_vault_usdt": self.locked_profit_vault_usdt,
                "high_water_mark_equity": self.high_water_mark_equity,
                "baseline_equity": self.baseline_equity,
                "working_balance_usdt": self._get_working_balance_locked(eq),
            }

    def record_transfer(
        self,
        delta_usdt: float,
        note: str = "",
        from_vault: bool = False,
    ) -> Dict[str, Any]:
        """
        C-13: Adjust `high_water_mark_equity` and `baseline_equity` for external
        deposits (`delta_usdt > 0`) and withdrawals (`delta_usdt < 0`) so deposits
        never falsely trigger a 35% vault ratchet and withdrawals do not skew equity curves.
        """
        import math as _math

        delta = float(delta_usdt)
        if not _math.isfinite(delta):
            raise ValueError(f"delta_usdt must be finite, got {delta_usdt!r}")

        with self._lock:
            if self.persist and self.state_path and os.path.exists(self.state_path):
                self._load_state()
                if self._state_corrupt:
                    return {
                        "recorded": False,
                        "error": "VAULT_STATE_CORRUPT",
                        "delta_usdt": delta,
                        "locked_profit_vault_usdt": self.locked_profit_vault_usdt,
                        "high_water_mark_equity": self.high_water_mark_equity,
                        "baseline_equity": self.baseline_equity,
                    }

            if delta == 0.0:
                return {
                    "recorded": False,
                    "delta_usdt": 0.0,
                    "locked_profit_vault_usdt": self.locked_profit_vault_usdt,
                    "high_water_mark_equity": self.high_water_mark_equity,
                    "baseline_equity": self.baseline_equity,
                    "net_transfers_usdt": self.net_transfers_usdt,
                }

            prev_hwm = self.high_water_mark_equity
            prev_base = self.baseline_equity
            prev_locked = self.locked_profit_vault_usdt

            if delta > 0.0:
                if self.initial_session_equity <= 0.0 and prev_base <= 0.0:
                    self.initial_session_equity = delta
                self.baseline_equity = max(0.0, prev_base + delta)
                self.high_water_mark_equity = max(0.0, prev_hwm + delta)
            else:
                self.baseline_equity = max(0.0, prev_base + delta)
                self.high_water_mark_equity = max(0.0, prev_hwm + delta)
                if from_vault:
                    self.locked_profit_vault_usdt = max(0.0, prev_locked + delta)
                elif self.locked_profit_vault_usdt > self.high_water_mark_equity:
                    self.locked_profit_vault_usdt = max(0.0, self.high_water_mark_equity)

            self.net_transfers_usdt += delta
            self.transfer_events.append({
                "ts": int(time.time()),
                "delta_usdt": round(delta, 6),
                "from_vault": bool(from_vault),
                "note": str(note or "")[:120],
                "prev_hwm": round(prev_hwm, 6),
                "new_hwm": round(self.high_water_mark_equity, 6),
                "prev_baseline": round(prev_base, 6),
                "new_baseline": round(self.baseline_equity, 6),
                "locked_vault_usdt": round(self.locked_profit_vault_usdt, 6),
            })
            self._save_state()
            return {
                "recorded": True,
                "delta_usdt": delta,
                "prev_hwm": prev_hwm,
                "high_water_mark_equity": self.high_water_mark_equity,
                "baseline_equity": self.baseline_equity,
                "net_transfers_usdt": self.net_transfers_usdt,
                "locked_profit_vault_usdt": self.locked_profit_vault_usdt,
            }

    def record_external_transfer(
        self,
        amount_usdt: float,
        note: str = "",
        from_vault: bool = False,
    ) -> Dict[str, Any]:
        """Alias for `record_transfer`."""
        return self.record_transfer(delta_usdt=amount_usdt, note=note, from_vault=from_vault)

    def apply_transfer_baseline(self, delta_usdt: float, note: str = "", from_vault: bool = False) -> Dict[str, Any]:
        """Alias for `record_transfer`."""
        return self.record_transfer(delta_usdt=delta_usdt, note=note, from_vault=from_vault)

    def _get_working_balance_locked(self, available_balance: float) -> float:
        if self._state_corrupt:
            return 0.0
        return max(0.0, float(available_balance) - self.locked_profit_vault_usdt)

    def get_working_balance(self, available_balance: float) -> float:
        """
        Return active working capital after subtracting `locked_profit_vault_usdt`.
        Guaranteed >= 0 and NEVER touches locked vault funds.
        """
        with self._lock:
            if self.persist and self.state_path and os.path.exists(self.state_path):
                self._load_state()
            return self._get_working_balance_locked(available_balance)

    def get_tradable_working_balance(self, available_balance: float) -> float:
        return self.get_working_balance(available_balance)

    def compute_all_in_working_capital(
        self,
        available_balance: float,
        all_in_fraction: float = 0.95,
        leverage: int = 20,
    ) -> Dict[str, float]:
        with self._lock:
            if self.persist and self.state_path and os.path.exists(self.state_path):
                self._load_state()
            working = self._get_working_balance_locked(available_balance)
            margin_usdt = working * float(all_in_fraction)
            notional_usdt = margin_usdt * int(leverage)
            return {
                "total_available_usdt": float(available_balance),
                "locked_vault_usdt": float(self.locked_profit_vault_usdt),
                "working_balance_usdt": working,
                "margin_usdt": margin_usdt,
                "notional_usdt": notional_usdt,
                "high_water_mark_equity": float(self.high_water_mark_equity),
                "hwm_equity": float(self.high_water_mark_equity),
                "baseline_equity": float(self.baseline_equity),
                "net_transfers_usdt": float(self.net_transfers_usdt),
            }

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            if self.persist and self.state_path and os.path.exists(self.state_path):
                self._load_state()
            return {
                "locked_profit_vault_usdt": float(self.locked_profit_vault_usdt),
                "locked_vault_usdt": float(self.locked_profit_vault_usdt),
                "high_water_mark_equity": float(self.high_water_mark_equity),
                "hwm_equity": float(self.high_water_mark_equity),
                "baseline_equity": float(self.baseline_equity),
                "net_transfers_usdt": float(self.net_transfers_usdt),
                "working_balance_usdt": self._get_working_balance_locked(self.high_water_mark_equity),
            }


def get_profit_vault(
    initial_equity: float = 0.0,
    state_path: Optional[str] = None,
    ratchet_step_pct: float = 0.15,
    lock_fraction: float = 0.35,
    persist: bool = True,
) -> ProfitRatchetVault:
    """Return a shared singleton `ProfitRatchetVault` per persisted `state_path`."""
    if not persist:
        return ProfitRatchetVault(
            initial_equity=initial_equity,
            state_path=state_path,
            ratchet_step_pct=ratchet_step_pct,
            lock_fraction=lock_fraction,
            persist=False,
        )
    resolved_path = state_path or DEFAULT_VAULT_STATE_PATH
    key = os.path.normcase(os.path.abspath(os.path.normpath(resolved_path)))
    with _VAULT_SINGLETON_LOCK:
        inst = _VAULT_SINGLETONS.get(key)
        if inst is None:
            inst = ProfitRatchetVault(
                initial_equity=initial_equity,
                state_path=resolved_path,
                ratchet_step_pct=ratchet_step_pct,
                lock_fraction=lock_fraction,
                persist=True,
            )
            _VAULT_SINGLETONS[key] = inst
        elif initial_equity > 0 and inst.high_water_mark_equity <= 0 and not inst._state_corrupt:
            with inst._lock:
                if inst.high_water_mark_equity <= 0:
                    inst.initial_session_equity = float(initial_equity)
                    inst.baseline_equity = float(initial_equity)
                    inst.high_water_mark_equity = float(initial_equity)
                    inst._save_state()
        return inst


def reset_profit_vault_cache() -> None:
    """Clear cached singleton vault instances (for isolated test cleanup)."""
    with _VAULT_SINGLETON_LOCK:
        _VAULT_SINGLETONS.clear()


ProfitVault = ProfitRatchetVault
