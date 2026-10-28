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

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_VAULT_STATE_PATH = os.path.join(BASE_DIR, "results", "vault_state.json")


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
        self._lock = threading.RLock()

        self.initial_session_equity: float = float(initial_equity)
        self.high_water_mark_equity: float = float(initial_equity)
        self.locked_profit_vault_usdt: float = 0.0
        self.ratchet_events: List[Dict[str, Any]] = []

        self._load_state()
        if initial_equity > 0 and self.high_water_mark_equity <= 0:
            self.initial_session_equity = float(initial_equity)
            self.high_water_mark_equity = float(initial_equity)
            self._save_state()

    def _load_state(self) -> None:
        if not self.persist or not self.state_path:
            return
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.initial_session_equity = float(
                        data.get("initial_session_equity", self.initial_session_equity)
                    )
                    self.high_water_mark_equity = float(
                        data.get("high_water_mark_equity", self.high_water_mark_equity)
                    )
                    self.locked_profit_vault_usdt = float(
                        data.get("locked_profit_vault_usdt", self.locked_profit_vault_usdt)
                    )
                    self.ratchet_events = list(data.get("ratchet_events", []))
            except Exception:
                pass

    def _save_state(self) -> None:
        if not self.persist or not self.state_path:
            return
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            payload = {
                "initial_session_equity": round(self.initial_session_equity, 6),
                "high_water_mark_equity": round(self.high_water_mark_equity, 6),
                "locked_profit_vault_usdt": round(self.locked_profit_vault_usdt, 6),
                "ratchet_step_pct": self.ratchet_step_pct,
                "lock_fraction": self.lock_fraction,
                "ratchet_events": self.ratchet_events[-50:],
                "updated_at": int(time.time()),
            }
            tmp_path = f"{self.state_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, self.state_path)
        except Exception:
            pass

    def update_equity(self, current_equity: float) -> Dict[str, Any]:
        """
        Evaluate `current_equity` against `high_water_mark_equity * (1 + ratchet_step_pct)`.
        Locks `35%` of new profit whenever equity exceeds `HWM * 1.15`.
        """
        eq = max(0.0, float(current_equity))
        with self._lock:
            if self.high_water_mark_equity <= 0.0 and eq > 0.0:
                self.initial_session_equity = eq
                self.high_water_mark_equity = eq
                self._save_state()
                return {
                    "ratcheted": False,
                    "newly_locked_usdt": 0.0,
                    "locked_profit_vault_usdt": self.locked_profit_vault_usdt,
                    "high_water_mark_equity": self.high_water_mark_equity,
                    "working_balance_usdt": self.get_working_balance(eq),
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
                    "working_balance_usdt": self.get_working_balance(eq),
                }

            return {
                "ratcheted": False,
                "newly_locked_usdt": 0.0,
                "locked_profit_vault_usdt": self.locked_profit_vault_usdt,
                "high_water_mark_equity": self.high_water_mark_equity,
                "working_balance_usdt": self.get_working_balance(eq),
            }

    def get_working_balance(self, available_balance: float) -> float:
        """
        Return active working capital after subtracting `locked_profit_vault_usdt`.
        Guaranteed >= 0 and NEVER touches locked vault funds.
        """
        with self._lock:
            return max(0.0, float(available_balance) - self.locked_profit_vault_usdt)

    def get_tradable_working_balance(self, available_balance: float) -> float:
        return self.get_working_balance(available_balance)

    def compute_all_in_working_capital(
        self,
        available_balance: float,
        all_in_fraction: float = 0.95,
        leverage: int = 20,
    ) -> Dict[str, float]:
        working = self.get_working_balance(available_balance)
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
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "locked_profit_vault_usdt": float(self.locked_profit_vault_usdt),
            "locked_vault_usdt": float(self.locked_profit_vault_usdt),
            "high_water_mark_equity": float(self.high_water_mark_equity),
            "hwm_equity": float(self.high_water_mark_equity),
            "working_balance_usdt": self.get_working_balance(self.high_water_mark_equity),
        }


ProfitVault = ProfitRatchetVault
