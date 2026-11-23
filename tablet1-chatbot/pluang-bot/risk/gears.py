"""
===========================================================================
PYROFUEL AUTO GEAR-SHIFT COMPOUNDING ENGINE v1.0 ("SISTEM PINDAH GIGI")
===========================================================================
Automatically scales leverage, sizing mode, and liquidity strictness as live
equity grows — maximizing compounding velocity on small capital while
locking down institutional survival once profits reach Rp 10M+ and Rp 100M+:

  GEAR 1 — TURBO    (Equity < $600 / ~Rp 10 Juta):
    - Leverage: 20x ISOLATED | Sizing: ALL_IN (95% working balance)
    - Profit Ratchet Vault: locks 35% of every +15% HWM step
    - Purpose: Maximum compounding acceleration on small starting capital.

  GEAR 2 — CRUISE   ($600 <= Equity < $6,000 / ~Rp 10 Juta - Rp 100 Juta):
    - Leverage: 12x ISOLATED | Sizing: RISK_FRACTIONAL (5.0% risk per SL)
    - Profit Ratchet Vault: locks 35% of every +15% HWM step
    - Purpose: Protect tens of millions IDR from 2-loss wipeouts while
      maintaining +15% to +20% weekly growth trajectory.

  GEAR 3 — FORTRESS (Equity >= $6,000 / ~Rp 100 Juta+):
    - Leverage: 8x ISOLATED  | Sizing: RISK_FRACTIONAL (2.5% risk per SL)
    - Profit Ratchet Vault: locks 40% of every +15% HWM step
    - Universe: Top-10 liquidity giants ONLY (zero altcoin slippage wall).

Includes 10% downshift hysteresis ($540 for G2->G1, $5,400 for G3->G2) so
equity fluctuating near a threshold never oscillates rapidly between gears.
===========================================================================
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from state_io import atomic_write_json, get_file_lock, read_json_safe

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GEAR_STATE_PATH = os.path.join(BASE_DIR, "results", "gear_state.json")

DEFAULT_GEARS: List[Dict[str, Any]] = [
    {
        "gear": 1,
        "code": "GEAR_1_TURBO",
        "label": "Gigi 1 — TURBO (Akselerasi Modal Kecil)",
        "min_equity_usdt": 0.0,
        "max_equity_usdt": 600.0,
        "leverage": 20,
        "margin_type": "ISOLATED",
        "sizing_mode": "ALL_IN",
        "all_in_balance_fraction": 0.95,
        "risk_pct": 5.0,
        "vault_lock_fraction": 0.35,
        "majors_only": False,
        "min_prefilter_volume_usd": 70_000_000,
    },
    {
        "gear": 2,
        "code": "GEAR_2_CRUISE",
        "label": "Gigi 2 — CRUISE (Proteksi Modal Menengah)",
        "min_equity_usdt": 600.0,
        "max_equity_usdt": 6000.0,
        "leverage": 12,
        "margin_type": "ISOLATED",
        "sizing_mode": "RISK_FRACTIONAL",
        "all_in_balance_fraction": 0.50,
        "risk_pct": 5.0,
        "vault_lock_fraction": 0.35,
        "majors_only": False,
        "min_prefilter_volume_usd": 120_000_000,
    },
    {
        "gear": 3,
        "code": "GEAR_3_FORTRESS",
        "label": "Gigi 3 — FORTRESS (Benteng Modal Besar)",
        "min_equity_usdt": 6000.0,
        "max_equity_usdt": 1e12,
        "leverage": 8,
        "margin_type": "ISOLATED",
        "sizing_mode": "RISK_FRACTIONAL",
        "all_in_balance_fraction": 0.35,
        "risk_pct": 2.5,
        "vault_lock_fraction": 0.40,
        "majors_only": True,
        "min_prefilter_volume_usd": 250_000_000,
    },
]

_GEAR_LOCK = threading.RLock()
_GEAR_SINGLETONS: Dict[str, "AutoGearShiftEngine"] = {}


class AutoGearShiftEngine:
    """Equity-driven automatic gear-shifting engine with downshift hysteresis."""

    def __init__(
        self,
        gears: Optional[List[Dict[str, Any]]] = None,
        downshift_hysteresis_pct: float = 0.10,
        state_path: Optional[str] = None,
        persist: bool = True,
    ):
        self.gears = sorted(
            [dict(g) for g in (gears or DEFAULT_GEARS)],
            key=lambda x: int(x.get("gear", 1)),
        )
        self.downshift_hysteresis_pct = max(0.0, min(0.30, float(downshift_hysteresis_pct)))
        self.state_path = state_path or DEFAULT_GEAR_STATE_PATH
        self.persist = bool(persist)
        self._lock = get_file_lock(self.state_path) if (self.persist and self.state_path) else threading.RLock()

        self.current_gear: int = 1
        self.last_equity_usdt: float = 0.0
        self.shift_history: List[Dict[str, Any]] = []
        self._load()

    def _gear_by_num(self, num: int) -> Dict[str, Any]:
        for g in self.gears:
            if int(g.get("gear", 1)) == int(num):
                return dict(g)
        return dict(self.gears[0])

    def _load(self) -> None:
        if not self.persist or not self.state_path:
            return
        with self._lock:
            data = read_json_safe(self.state_path, default=None, strict_on_corrupt=False, expected_type=dict)
            if isinstance(data, dict):
                try:
                    self.current_gear = int(data.get("current_gear", 1) or 1)
                    self.last_equity_usdt = float(data.get("last_equity_usdt", 0.0) or 0.0)
                    self.shift_history = list(data.get("shift_history") or [])[-30:]
                except (TypeError, ValueError):
                    self.current_gear = 1

    def _save(self) -> None:
        if not self.persist or not self.state_path:
            return
        with self._lock:
            spec = self._gear_by_num(self.current_gear)
            atomic_write_json(
                self.state_path,
                {
                    "current_gear": self.current_gear,
                    "gear_code": spec.get("code"),
                    "gear_label": spec.get("label"),
                    "last_equity_usdt": round(self.last_equity_usdt, 4),
                    "active_profile": spec,
                    "shift_history": self.shift_history[-30:],
                    "updated_at": int(time.time()),
                },
                make_bak=True,
            )

    def _raw_gear_for_equity(self, equity_usdt: float) -> int:
        eq = max(0.0, float(equity_usdt or 0.0))
        chosen = int(self.gears[0]["gear"])
        for g in self.gears:
            if eq >= float(g.get("min_equity_usdt", 0.0)):
                chosen = int(g["gear"])
        return chosen

    def evaluate(self, equity_usdt: float, now_ts: Optional[float] = None) -> Dict[str, Any]:
        """
        Evaluate live equity and return active gear profile + shift event metadata.
        Upshifts happen immediately when crossing a tier boundary; downshifts require
        dropping `downshift_hysteresis_pct` (10%) below the tier's minimum equity.
        """
        eq = max(0.0, float(equity_usdt or 0.0))
        ts = float(now_ts if now_ts is not None else time.time())

        with self._lock:
            if self.persist and self.state_path and os.path.exists(self.state_path):
                self._load()

            prev_gear = self.current_gear
            target_gear = self._raw_gear_for_equity(eq) if eq > 0 else prev_gear

            if target_gear > prev_gear:
                new_gear = target_gear
            elif target_gear < prev_gear and eq > 0:
                # Apply downshift hysteresis so noise near $600 / $6000 doesn't flap gears
                curr_spec = self._gear_by_num(prev_gear)
                downshift_floor = float(curr_spec.get("min_equity_usdt", 0.0)) * (1.0 - self.downshift_hysteresis_pct)
                if eq < downshift_floor:
                    new_gear = target_gear
                else:
                    new_gear = prev_gear
            else:
                new_gear = prev_gear

            shifted = (new_gear != prev_gear)
            self.current_gear = new_gear
            if eq > 0:
                self.last_equity_usdt = eq

            profile = self._gear_by_num(new_gear)
            next_spec = next((g for g in self.gears if int(g["gear"]) == new_gear + 1), None)
            next_target_usdt = float(next_spec["min_equity_usdt"]) if next_spec else None

            if shifted:
                direction = "UP" if new_gear > prev_gear else "DOWN"
                ev = {
                    "ts": int(ts),
                    "from_gear": prev_gear,
                    "to_gear": new_gear,
                    "direction": direction,
                    "equity_usdt": round(eq, 4),
                    "code": profile["code"],
                }
                self.shift_history.append(ev)
                self._save()
            elif eq > 0 and self.persist:
                self._save()

            return {
                "gear": new_gear,
                "prev_gear": prev_gear,
                "shifted": shifted,
                "shift_direction": ("UP" if new_gear > prev_gear else "DOWN") if shifted else None,
                "code": profile["code"],
                "label": profile["label"],
                "leverage": int(profile["leverage"]),
                "margin_type": str(profile.get("margin_type", "ISOLATED")).upper(),
                "sizing_mode": str(profile["sizing_mode"]).upper(),
                "all_in_balance_fraction": float(profile.get("all_in_balance_fraction", 0.95)),
                "risk_pct": float(profile.get("risk_pct", 5.0)),
                "vault_lock_fraction": float(profile.get("vault_lock_fraction", 0.35)),
                "majors_only": bool(profile.get("majors_only", False)),
                "min_prefilter_volume_usd": float(profile.get("min_prefilter_volume_usd", 70_000_000)),
                "equity_usdt": round(eq, 4),
                "next_gear_equity_usdt": next_target_usdt,
                "progress_to_next_pct": (
                    round(min(100.0, (eq / next_target_usdt) * 100.0), 1)
                    if (next_target_usdt and next_target_usdt > 0)
                    else 100.0
                ),
            }

    def apply_to_config(self, cfg: Dict[str, Any], equity_usdt: float) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Return a shallow-copied config adjusted for the active gear + gear status dict."""
        out_cfg = dict(cfg or {})
        gear_cfg = out_cfg.get("auto_gear_system") if isinstance(out_cfg.get("auto_gear_system"), dict) else {}
        if not bool(gear_cfg.get("enabled", False)):
            return out_cfg, {
                "enabled": False,
                "gear": 1,
                "code": "GEAR_1_TURBO",
                "label": "Gigi 1 — TURBO (Static Config)",
                "shifted": False,
                "leverage": int(out_cfg.get("fixed_leverage", 20) or 20),
                "sizing_mode": str(out_cfg.get("sizing_mode", "ALL_IN")).upper(),
            }

        status = self.evaluate(equity_usdt)
        status["enabled"] = True
        out_cfg["fixed_leverage"] = int(status["leverage"])
        out_cfg["max_leverage"] = int(status["leverage"])
        out_cfg["margin_type"] = status["margin_type"]
        out_cfg["sizing_mode"] = status["sizing_mode"]
        out_cfg["all_in_balance_fraction"] = float(status["all_in_balance_fraction"])
        out_cfg["risk_pct"] = float(status["risk_pct"])
        out_cfg["min_prefilter_volume_usd"] = max(
            float(out_cfg.get("min_prefilter_volume_usd", 70_000_000) or 70_000_000),
            float(status["min_prefilter_volume_usd"]),
        )
        out_cfg["gear_majors_only"] = bool(status["majors_only"])
        out_cfg["active_gear"] = status
        return out_cfg, status


def get_gear_engine(
    config: Optional[Dict[str, Any]] = None,
    state_path: Optional[str] = None,
    persist: bool = True,
) -> AutoGearShiftEngine:
    """Return shared AutoGearShiftEngine singleton keyed by state_path."""
    gear_cfg = (config or {}).get("auto_gear_system") if isinstance(config, dict) else {}
    gears_custom = gear_cfg.get("gears") if isinstance(gear_cfg, dict) and isinstance(gear_cfg.get("gears"), list) else None
    hyst = float(gear_cfg.get("downshift_hysteresis_pct", 0.10)) if isinstance(gear_cfg, dict) else 0.10
    path = state_path or DEFAULT_GEAR_STATE_PATH
    if not persist:
        return AutoGearShiftEngine(gears=gears_custom, downshift_hysteresis_pct=hyst, state_path=path, persist=False)

    norm_p = os.path.normcase(os.path.abspath(path))
    with _GEAR_LOCK:
        inst = _GEAR_SINGLETONS.get(norm_p)
        if inst is None:
            inst = AutoGearShiftEngine(gears=gears_custom, downshift_hysteresis_pct=hyst, state_path=path, persist=True)
            _GEAR_SINGLETONS[norm_p] = inst
        elif gears_custom:
            inst.gears = sorted([dict(g) for g in gears_custom], key=lambda x: int(x.get("gear", 1)))
        return inst


def reset_gear_engine_cache() -> None:
    with _GEAR_LOCK:
        _GEAR_SINGLETONS.clear()
