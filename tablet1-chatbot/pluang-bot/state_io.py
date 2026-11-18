"""
Atomic, thread-safe JSON state I/O utilities for Pyrofuel Bot (WP-0).

Provides:
- Global per-path re-entrant locks keyed by normalized absolute path (`get_file_lock`).
- Crash-safe atomic JSON writes (`atomic_write_json`) with:
  * unique per-call temp filenames (`pid + tid + uuid`)
  * strict RFC-8259 JSON serialization (`allow_nan=False`)
  * `f.flush()` + `os.fsync(f.fileno())`
  * `.bak` backup snapshot of the prior valid file before replacement
  * 3x retry on Windows `PermissionError` during `os.replace`
  * guaranteed orphaned `.tmp` cleanup and explicit error logging
- Corrupt-aware JSON reads (`read_json_safe`) that distinguish missing files from
  corrupt/unreadable files, recover from `.bak` without ever overwriting corrupt
  files, and raise `CorruptedStateError` when `strict_on_corrupt=True`.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, Optional, Tuple, Union

logger = logging.getLogger(__name__)

_REGISTRY_LOCK = threading.Lock()
_FILE_LOCKS: Dict[str, threading.RLock] = {}


class CorruptedStateError(RuntimeError):
    """Raised when a critical state file and its .bak fallback are corrupt or unreadable."""


def _normalize_lock_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(str(path))))


def get_file_lock(path: str) -> threading.RLock:
    """Return the shared re-entrant lock registered for normalized `path`."""
    key = _normalize_lock_key(path)
    with _REGISTRY_LOCK:
        lock = _FILE_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _FILE_LOCKS[key] = lock
        return lock


def _unique_tmp_path(base_path: str) -> str:
    return f"{base_path}.tmp.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:12]}"


def _replace_with_retry(
    src: str,
    dst: str,
    max_attempts: int = 3,
    sleep_sec: float = 0.05,
) -> None:
    for attempt in range(max_attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt >= max_attempts - 1:
                raise
            time.sleep(sleep_sec)


def _write_text_atomic_unlocked(target_path: str, text: str) -> None:
    tmp_path = _unique_tmp_path(target_path)
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        _replace_with_retry(tmp_path, target_path, max_attempts=3, sleep_sec=0.05)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError as rm_exc:
                logger.warning("Failed to remove orphaned temp file %s: %s", tmp_path, rm_exc)


def _backup_prior_valid_json(target_path: str) -> None:
    if not os.path.exists(target_path):
        return
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            raw = f.read()
        if not raw.strip():
            logger.warning("Skipping .bak update: prior file %s is empty.", target_path)
            return
        json.loads(raw)
    except Exception as exc:
        logger.warning(
            "Skipping .bak update because prior file %s is not valid JSON (%s); preserving any existing .bak.",
            target_path,
            exc,
        )
        return

    bak_path = f"{target_path}.bak"
    try:
        _write_text_atomic_unlocked(bak_path, raw)
    except Exception as exc:
        logger.warning("Failed to write backup %s: %s", bak_path, exc)


def atomic_write_json(
    path: str,
    obj: Any,
    make_bak: bool = True,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> bool:
    """
    Atomically write `obj` as UTF-8 JSON to `path`.

    Returns True on success, False on failure (after logging the error and cleaning
    up any temporary file).
    """
    target_path = os.path.abspath(str(path))
    try:
        payload_str = json.dumps(
            obj,
            indent=indent,
            ensure_ascii=ensure_ascii,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        logger.error("atomic_write_json serialization failed for %s: %s", target_path, exc)
        return False

    lock = get_file_lock(target_path)
    with lock:
        try:
            parent = os.path.dirname(target_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            if make_bak:
                _backup_prior_valid_json(target_path)
            _write_text_atomic_unlocked(target_path, payload_str)
            return True
        except Exception as exc:
            logger.error("atomic_write_json failed for %s: %s", target_path, exc, exc_info=True)
            return False


def _load_json_file(
    file_path: str,
    expected_type: Optional[Union[type, Tuple[type, ...]]] = None,
) -> Any:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if expected_type is not None and not isinstance(data, expected_type):
        raise ValueError(
            f"Unexpected JSON root type {type(data).__name__}; expected {expected_type}"
        )
    return data


def read_json_safe(
    path: str,
    default: Any = None,
    strict_on_corrupt: bool = False,
    expected_type: Optional[Union[type, Tuple[type, ...]]] = None,
) -> Any:
    """
    Safely read JSON from `path` under its per-file lock.

    - If `path` does not exist (`FileNotFoundError`), returns `copy.deepcopy(default)`.
    - If `path` is corrupt/unreadable, NEVER overwrites `path` and tries `{path}.bak`.
    - If `.bak` also fails or is missing:
      * when `strict_on_corrupt=True`, raises `CorruptedStateError`
      * otherwise logs the error and returns `copy.deepcopy(default)`.
    """
    target_path = os.path.abspath(str(path))
    bak_path = f"{target_path}.bak"
    lock = get_file_lock(target_path)

    with lock:
        try:
            return _load_json_file(target_path, expected_type=expected_type)
        except FileNotFoundError:
            return copy.deepcopy(default)
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError, OSError) as primary_exc:
            logger.error(
                "Corrupt or unreadable JSON state at %s (%s); attempting .bak fallback.",
                target_path,
                primary_exc,
            )
            try:
                recovered = _load_json_file(bak_path, expected_type=expected_type)
                logger.warning(
                    "Recovered valid state for %s from backup %s (corrupt primary left untouched).",
                    target_path,
                    bak_path,
                )
                return recovered
            except Exception as bak_exc:
                logger.error(
                    "Backup fallback %s unavailable or invalid for %s (%s).",
                    bak_path,
                    target_path,
                    bak_exc,
                )
                if strict_on_corrupt:
                    raise CorruptedStateError(
                        f"State file '{target_path}' is corrupt/unreadable ({primary_exc}) "
                        f"and backup '{bak_path}' failed ({bak_exc})."
                    ) from primary_exc
                return copy.deepcopy(default)
