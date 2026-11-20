"""
Trading configuration schema validation, alias normalization, SHA-256 hashing,
and last-known-good runtime reload protection (WP-0).
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
from typing import Any, Callable, Dict, Iterable, Optional

from state_io import atomic_write_json, get_file_lock

logger = logging.getLogger(__name__)

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(BOT_DIR, "trading_config.json")

DEFAULT_TRADING_CONFIG: Dict[str, Any] = {
    "max_budget_idr": 0,
    "max_leverage": 20,
    "fixed_leverage": 20,
    "margin_type": "ISOLATED",
    "sizing_mode": "ALL_IN",
    "all_in_balance_fraction": 0.95,
    "risk_pct": 5.0,
    "probation_risk_pct": 2.0,
    "max_sl_pct": 2.25,
    "min_sl_pct": 0.45,
    "min_liq_to_sl_ratio": 2.0,
    "min_confidence_score": 65,
    "min_risk_reward_ratio": 1.5,
    "min_ev_r": 0.20,
    "max_drawdown_pct": 25.0,
    "breaker_daily_dd_pct": 15.0,
    "circuit_breaker_consecutive_losses": 2,
    "breaker_consecutive_losses": 2,
    "breaker_cooldown_hours": 12,
    "committee_enabled": False,
    "ai_manages_execution": True,
    "ai_manages_leverage": False,
    "ai_manages_order_type": True,
    "tp_sl_mode": "SNIPER_TWO_STAGE",
    "sniper_75_mode": {
        "enabled": True,
        "conformal_enabled": False,
        "min_calibrated_p_tp1": 0.60,
        "min_first_passage_pct": 60.0,
        "require_singleton_win": False,
        "conformal_alpha_target": 0.18,
        "tp1_lock_trigger_r": 0.55,
        "tp1_partial_close_pct": 0.65,
        "sl_lock_after_tp1_r": 0.38,
        "tp2_runner_target_r": 1.60,
        "early_invalidation_max_loss_r": 0.35,
    },
    "profit_vault": {
        "enabled": True,
        "hwm_step_pct": 15.0,
        "lock_fraction": 0.35,
    },
    "max_concurrent_positions": 1,
    "max_daily_trades": 10,
    "currency": "USDT",
    "auto_execute": True,
    "auto_execute_on_binance": True,
    "trading_mode": "AI_QUANT_SOVEREIGN_V3",
}

_LAST_KNOWN_GOOD: Dict[str, Dict[str, Any]] = {}
_LAST_LOGGED_HASH: Dict[str, str] = {}

_ALLOWED_MARGIN_TYPES = {"ISOLATED", "CROSSED"}
_ALLOWED_SIZING_MODES = {"ALL_IN", "RISK_FRACTIONAL", "FRACTIONAL", "FIXED"}
_BOOL_FIELDS = (
    "committee_enabled",
    "ai_manages_execution",
    "ai_manages_leverage",
    "ai_manages_order_type",
    "auto_execute",
    "auto_execute_on_binance",
)


class ConfigValidationError(ValueError):
    """Raised when trading_config.json fails type, range, or alias checks."""


def _norm_path(path: Optional[str]) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(path or DEFAULT_CONFIG_PATH)))


def _check_number(
    val: Any,
    name: str,
    *,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    min_inclusive: bool = True,
    max_inclusive: bool = True,
    integer_only: bool = False,
) -> float | int:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ConfigValidationError(f"'{name}' must be a number, got {type(val).__name__}: {val!r}")
    if integer_only and not isinstance(val, int):
        raise ConfigValidationError(f"'{name}' must be an integer, got {type(val).__name__}: {val!r}")
    num = float(val)
    if not math.isfinite(num):
        raise ConfigValidationError(f"'{name}' must be finite, got {val!r}")
    if min_val is not None:
        if (min_inclusive and num < min_val) or (not min_inclusive and num <= min_val):
            op = ">=" if min_inclusive else ">"
            raise ConfigValidationError(f"'{name}' must be {op} {min_val}, got {val!r}")
    if max_val is not None:
        if (max_inclusive and num > max_val) or (not max_inclusive and num >= max_val):
            op = "<=" if max_inclusive else "<"
            raise ConfigValidationError(f"'{name}' must be {op} {max_val}, got {val!r}")
    return int(val) if integer_only else num


def _check_bool(val: Any, name: str) -> bool:
    if not isinstance(val, bool):
        raise ConfigValidationError(f"'{name}' must be a boolean, got {type(val).__name__}: {val!r}")
    return val


def _check_nonempty_str(val: Any, name: str) -> str:
    if not isinstance(val, str) or not val.strip():
        raise ConfigValidationError(f"'{name}' must be a non-empty string, got {val!r}")
    return val.strip()


def normalize_breaker_aliases(
    raw_cfg: Dict[str, Any],
    updated_keys: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """
    Synchronize `circuit_breaker_consecutive_losses` <-> `breaker_consecutive_losses`.
    Rejects conflicting explicit values unless only one alias was provided in `updated_keys`.
    """
    out = dict(raw_cfg)
    has_cb = "circuit_breaker_consecutive_losses" in out and out["circuit_breaker_consecutive_losses"] is not None
    has_br = "breaker_consecutive_losses" in out and out["breaker_consecutive_losses"] is not None

    if has_cb and has_br:
        if out["circuit_breaker_consecutive_losses"] != out["breaker_consecutive_losses"]:
            upd = set(updated_keys or ())
            if "breaker_consecutive_losses" in upd and "circuit_breaker_consecutive_losses" not in upd:
                out["circuit_breaker_consecutive_losses"] = out["breaker_consecutive_losses"]
            elif "circuit_breaker_consecutive_losses" in upd and "breaker_consecutive_losses" not in upd:
                out["breaker_consecutive_losses"] = out["circuit_breaker_consecutive_losses"]
            else:
                raise ConfigValidationError(
                    "Conflicting breaker aliases: "
                    f"circuit_breaker_consecutive_losses={out['circuit_breaker_consecutive_losses']!r} "
                    f"!= breaker_consecutive_losses={out['breaker_consecutive_losses']!r}"
                )
    elif has_cb:
        out["breaker_consecutive_losses"] = out["circuit_breaker_consecutive_losses"]
    elif has_br:
        out["circuit_breaker_consecutive_losses"] = out["breaker_consecutive_losses"]
    else:
        default_val = DEFAULT_TRADING_CONFIG["breaker_consecutive_losses"]
        out["circuit_breaker_consecutive_losses"] = default_val
        out["breaker_consecutive_losses"] = default_val

    return out


def validate_trading_config(
    raw_cfg: Dict[str, Any],
    *,
    updated_keys: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """
    Validate types, safe bounds, and alias normalization for trading_config.json.
    Returns a normalized copy of the merged config or raises `ConfigValidationError`.
    """
    if not isinstance(raw_cfg, dict):
        raise ConfigValidationError(f"Trading config root must be a JSON object, got {type(raw_cfg).__name__}")

    normalized_raw = normalize_breaker_aliases(raw_cfg, updated_keys=updated_keys)

    merged = copy.deepcopy(DEFAULT_TRADING_CONFIG)
    for key, value in normalized_raw.items():
        if key in ("sniper_75_mode", "profit_vault"):
            if not isinstance(value, dict):
                raise ConfigValidationError(f"'{key}' must be an object, got {type(value).__name__}")
            merged[key].update(value)
        else:
            merged[key] = value

    # Numeric & integer bounds
    merged["max_budget_idr"] = _check_number(merged["max_budget_idr"], "max_budget_idr", min_val=0)
    merged["fixed_leverage"] = _check_number(
        merged["fixed_leverage"], "fixed_leverage", min_val=1, max_val=20, integer_only=True
    )
    merged["max_leverage"] = _check_number(
        merged["max_leverage"], "max_leverage", min_val=1, max_val=20, integer_only=True
    )
    merged["all_in_balance_fraction"] = _check_number(
        merged["all_in_balance_fraction"],
        "all_in_balance_fraction",
        min_val=0.0,
        max_val=0.98,
        min_inclusive=False,
        max_inclusive=True,
    )
    merged["risk_pct"] = _check_number(
        merged["risk_pct"], "risk_pct", min_val=0.0, max_val=25.0, min_inclusive=False
    )
    merged["probation_risk_pct"] = _check_number(
        merged["probation_risk_pct"], "probation_risk_pct", min_val=0.0, max_val=25.0, min_inclusive=False
    )
    merged["min_sl_pct"] = _check_number(
        merged["min_sl_pct"], "min_sl_pct", min_val=0.0, max_val=5.0, min_inclusive=False
    )
    merged["max_sl_pct"] = _check_number(
        merged["max_sl_pct"], "max_sl_pct", min_val=0.0, max_val=5.0, min_inclusive=False
    )
    if merged["min_sl_pct"] > merged["max_sl_pct"]:
        raise ConfigValidationError(
            f"'min_sl_pct' ({merged['min_sl_pct']}) cannot exceed 'max_sl_pct' ({merged['max_sl_pct']})"
        )
    merged["min_liq_to_sl_ratio"] = _check_number(
        merged["min_liq_to_sl_ratio"], "min_liq_to_sl_ratio", min_val=1.0, max_val=20.0
    )
    merged["min_confidence_score"] = _check_number(
        merged["min_confidence_score"], "min_confidence_score", min_val=0.0, max_val=100.0
    )
    merged["min_risk_reward_ratio"] = _check_number(
        merged["min_risk_reward_ratio"], "min_risk_reward_ratio", min_val=0.0, max_val=20.0, min_inclusive=False
    )
    merged["min_ev_r"] = _check_number(merged["min_ev_r"], "min_ev_r", min_val=0.0, max_val=5.0)
    merged["max_drawdown_pct"] = _check_number(
        merged["max_drawdown_pct"], "max_drawdown_pct", min_val=0.0, max_val=100.0, min_inclusive=False
    )
    merged["breaker_daily_dd_pct"] = _check_number(
        merged["breaker_daily_dd_pct"], "breaker_daily_dd_pct", min_val=0.0, max_val=50.0, min_inclusive=False
    )
    cb_losses = _check_number(
        merged["circuit_breaker_consecutive_losses"],
        "circuit_breaker_consecutive_losses",
        min_val=1,
        max_val=20,
        integer_only=True,
    )
    merged["circuit_breaker_consecutive_losses"] = cb_losses
    merged["breaker_consecutive_losses"] = cb_losses
    merged["breaker_cooldown_hours"] = _check_number(
        merged["breaker_cooldown_hours"], "breaker_cooldown_hours", min_val=1.0, max_val=168.0
    )
    merged["max_concurrent_positions"] = _check_number(
        merged["max_concurrent_positions"], "max_concurrent_positions", min_val=1, max_val=20, integer_only=True
    )
    merged["max_daily_trades"] = _check_number(
        merged["max_daily_trades"], "max_daily_trades", min_val=1, max_val=500, integer_only=True
    )

    # Enums & strings
    margin_type = _check_nonempty_str(merged["margin_type"], "margin_type").upper()
    if margin_type not in _ALLOWED_MARGIN_TYPES:
        raise ConfigValidationError(f"'margin_type' must be one of {_ALLOWED_MARGIN_TYPES}, got {margin_type!r}")
    merged["margin_type"] = margin_type

    sizing_mode = _check_nonempty_str(merged["sizing_mode"], "sizing_mode").upper()
    if sizing_mode not in _ALLOWED_SIZING_MODES:
        raise ConfigValidationError(f"'sizing_mode' must be one of {_ALLOWED_SIZING_MODES}, got {sizing_mode!r}")
    merged["sizing_mode"] = sizing_mode

    merged["tp_sl_mode"] = _check_nonempty_str(merged["tp_sl_mode"], "tp_sl_mode")
    merged["currency"] = _check_nonempty_str(merged["currency"], "currency").upper()
    merged["trading_mode"] = _check_nonempty_str(merged["trading_mode"], "trading_mode")

    # Booleans
    for bkey in _BOOL_FIELDS:
        merged[bkey] = _check_bool(merged[bkey], bkey)

    # Nested: sniper_75_mode
    sn = merged["sniper_75_mode"]
    sn["enabled"] = _check_bool(sn["enabled"], "sniper_75_mode.enabled")
    sn["min_calibrated_p_tp1"] = _check_number(
        sn["min_calibrated_p_tp1"],
        "sniper_75_mode.min_calibrated_p_tp1",
        min_val=0.0,
        max_val=1.0,
        min_inclusive=False,
        max_inclusive=False,
    )
    if "conformal_enabled" in sn:
        sn["conformal_enabled"] = _check_bool(
            sn["conformal_enabled"], "sniper_75_mode.conformal_enabled"
        )
    if "min_first_passage_pct" in sn:
        sn["min_first_passage_pct"] = _check_number(
            sn["min_first_passage_pct"],
            "sniper_75_mode.min_first_passage_pct",
            min_val=10.0,
            max_val=100.0,
        )
    if "require_singleton_win" in sn:
        sn["require_singleton_win"] = _check_bool(
            sn["require_singleton_win"], "sniper_75_mode.require_singleton_win"
        )
    sn["conformal_alpha_target"] = _check_number(
        sn["conformal_alpha_target"],
        "sniper_75_mode.conformal_alpha_target",
        min_val=0.0,
        max_val=0.5,
        min_inclusive=False,
    )
    sn["tp1_lock_trigger_r"] = _check_number(
        sn["tp1_lock_trigger_r"], "sniper_75_mode.tp1_lock_trigger_r", min_val=0.0, max_val=10.0, min_inclusive=False
    )
    sn["tp1_partial_close_pct"] = _check_number(
        sn["tp1_partial_close_pct"], "sniper_75_mode.tp1_partial_close_pct", min_val=0.0, max_val=1.0
    )
    sn["sl_lock_after_tp1_r"] = _check_number(
        sn["sl_lock_after_tp1_r"], "sniper_75_mode.sl_lock_after_tp1_r", min_val=0.0, max_val=10.0
    )
    if sn["sl_lock_after_tp1_r"] > sn["tp1_lock_trigger_r"]:
        raise ConfigValidationError(
            "'sniper_75_mode.sl_lock_after_tp1_r' cannot exceed 'sniper_75_mode.tp1_lock_trigger_r'"
        )
    sn["tp2_runner_target_r"] = _check_number(
        sn["tp2_runner_target_r"], "sniper_75_mode.tp2_runner_target_r", min_val=0.0, max_val=20.0, min_inclusive=False
    )
    sn["early_invalidation_max_loss_r"] = _check_number(
        sn["early_invalidation_max_loss_r"],
        "sniper_75_mode.early_invalidation_max_loss_r",
        min_val=0.0,
        max_val=1.0,
        min_inclusive=False,
    )

    # Nested: profit_vault
    pv = merged["profit_vault"]
    pv["enabled"] = _check_bool(pv["enabled"], "profit_vault.enabled")
    pv["hwm_step_pct"] = _check_number(
        pv["hwm_step_pct"], "profit_vault.hwm_step_pct", min_val=0.0, max_val=200.0, min_inclusive=False
    )
    pv["lock_fraction"] = _check_number(
        pv["lock_fraction"],
        "profit_vault.lock_fraction",
        min_val=0.0,
        max_val=1.0,
        min_inclusive=False,
        max_inclusive=False,
    )

    return merged


def compute_config_hash(cfg: Dict[str, Any]) -> str:
    """Compute canonical SHA-256 hex digest for a validated trading config dict."""
    canonical = json.dumps(cfg, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _emit_alert(msg: str, alert_fn: Optional[Callable[[str], None]] = None) -> None:
    logger.error(msg)
    if alert_fn is not None:
        try:
            alert_fn(msg)
        except Exception as cb_exc:
            logger.warning("Config alert callback failed: %s", cb_exc)


def load_trading_config(
    config_path: Optional[str] = None,
    alert_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Load, validate, and SHA-256 log `trading_config.json`.

    On invalid runtime reload (parse error, schema error, or vanished file after startup),
    logs/alerts and falls back to the last known-good config for that path rather than
    bad or defaulted values.
    """
    target = os.path.abspath(config_path or DEFAULT_CONFIG_PATH)
    cache_key = _norm_path(target)
    lock = get_file_lock(target)

    with lock:
        try:
            with open(target, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            if cache_key in _LAST_KNOWN_GOOD:
                _emit_alert(
                    f"Config file {target} disappeared at runtime; falling back to last known-good config.",
                    alert_fn,
                )
                return copy.deepcopy(_LAST_KNOWN_GOOD[cache_key])
            validated = validate_trading_config({})
            cfg_hash = compute_config_hash(validated)
            _LAST_KNOWN_GOOD[cache_key] = copy.deepcopy(validated)
            _LAST_LOGGED_HASH[cache_key] = cfg_hash
            logger.info(
                "Trading config missing at %s; initialized validated defaults sha256=%s",
                target,
                cfg_hash,
            )
            return copy.deepcopy(validated)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            _emit_alert(f"Failed to read/parse trading config at {target}: {exc}", alert_fn)
            if cache_key in _LAST_KNOWN_GOOD:
                logger.warning(
                    "Rejected invalid runtime config reload for %s; falling back to last known-good (sha256=%s).",
                    target,
                    _LAST_LOGGED_HASH.get(cache_key),
                )
                return copy.deepcopy(_LAST_KNOWN_GOOD[cache_key])
            bak_path = f"{target}.bak"
            if os.path.exists(bak_path):
                try:
                    with open(bak_path, "r", encoding="utf-8") as bf:
                        bak_raw = json.load(bf)
                    validated_bak = validate_trading_config(bak_raw)
                    cfg_hash = compute_config_hash(validated_bak)
                    _LAST_KNOWN_GOOD[cache_key] = copy.deepcopy(validated_bak)
                    _LAST_LOGGED_HASH[cache_key] = cfg_hash
                    logger.warning(
                        "Recovered startup trading config from %s sha256=%s",
                        bak_path,
                        cfg_hash,
                    )
                    return copy.deepcopy(validated_bak)
                except Exception as bak_exc:
                    logger.error("Backup config %s also invalid: %s", bak_path, bak_exc)
            fallback = validate_trading_config({})
            logger.warning("Falling back to validated default trading config (corrupt primary left untouched).")
            return copy.deepcopy(fallback)

        try:
            validated = validate_trading_config(raw)
        except ConfigValidationError as exc:
            _emit_alert(f"Rejected invalid trading config at {target}: {exc}", alert_fn)
            if cache_key in _LAST_KNOWN_GOOD:
                logger.warning(
                    "Falling back to last known-good config for %s (sha256=%s).",
                    target,
                    _LAST_LOGGED_HASH.get(cache_key),
                )
                return copy.deepcopy(_LAST_KNOWN_GOOD[cache_key])
            fallback = validate_trading_config({})
            logger.warning("Startup config invalid and no last known-good available; using validated defaults.")
            return copy.deepcopy(fallback)

        cfg_hash = compute_config_hash(validated)
        prev_hash = _LAST_LOGGED_HASH.get(cache_key)
        if prev_hash is None:
            logger.info("Loaded validated trading config (%s) sha256=%s", target, cfg_hash)
        elif prev_hash != cfg_hash:
            logger.info("Reloaded validated trading config (%s) sha256=%s (prev=%s)", target, cfg_hash, prev_hash)

        _LAST_LOGGED_HASH[cache_key] = cfg_hash
        _LAST_KNOWN_GOOD[cache_key] = copy.deepcopy(validated)
        return copy.deepcopy(validated)


def save_validated_trading_config(
    updates: Dict[str, Any],
    config_path: Optional[str] = None,
    *,
    enforce_fixed_leverage: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Merge `updates` onto current validated config, validate against schema,
    and persist atomically with `.bak`. Raises `ConfigValidationError` on invalid updates.
    """
    if not isinstance(updates, dict):
        raise ConfigValidationError(f"Config updates must be a dict, got {type(updates).__name__}")
    target = os.path.abspath(config_path or DEFAULT_CONFIG_PATH)
    cache_key = _norm_path(target)
    lock = get_file_lock(target)

    with lock:
        current = load_trading_config(target)
        merged = copy.deepcopy(current)
        for k, v in updates.items():
            if k in ("sniper_75_mode", "profit_vault") and isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v

        if enforce_fixed_leverage is not None:
            merged["max_leverage"] = enforce_fixed_leverage
            merged["fixed_leverage"] = enforce_fixed_leverage

        validated = validate_trading_config(merged, updated_keys=updates.keys())
        if not atomic_write_json(target, validated, make_bak=True):
            raise OSError(f"Failed to write trading config to {target}")

        cfg_hash = compute_config_hash(validated)
        _LAST_KNOWN_GOOD[cache_key] = copy.deepcopy(validated)
        _LAST_LOGGED_HASH[cache_key] = cfg_hash
        logger.info("Saved validated trading config (%s) sha256=%s", target, cfg_hash)
        return copy.deepcopy(validated)
