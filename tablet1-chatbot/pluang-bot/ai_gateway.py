"""
===========================================================================
PYROFUEL AI GATEWAY v3.0 — TOKEN-AWARE MULTI-PROVIDER ROUTER (T2.1 & T2.2)
===========================================================================
Institutional Token-Aware AI Gateway:
- Multi-Provider Pool:
  * Groq (multi-key pool, dynamic model discovery via GET /openai/v1/models
    with mandatory User-Agent: PyrofuelQuantBot/3.0 to bypass Cloudflare 1010)
  * Google Gemini (gemini-2.5-flash, gemini-2.5-pro with native responseSchema)
  * Cerebras, Mistral, OpenRouter (:free), NVIDIA NIM
- Token Budget Ledger (results/ai_budget_ledger.json):
  * Tracks x-ratelimit-remaining-tokens, x-ratelimit-remaining-requests,
    x-ratelimit-reset-tokens, and daily 200,000 TPD per (provider, model, key_hash)
  * Classifies 429 TPD (exhausted until UTC reset) vs 429 RPM (short cooldown)
    vs 401/402/403 (invalid/unpaid key)
- Per-Candle Prompt Hash Cache:
  * Keyed on (symbol, tf, closed_bar_ts, strategy_id, stage)
  * Guarantees at most 1 AI call per setup per closed candle
- Enforced JSON Schema & Reasoning Sanitizer:
  * Strips <think>...</think> and markdown code fences
  * Strictly validates PRIMARY, AUDITOR, and EMERGENCY schemas
  * Performs 1x automatic repair retry on schema/parse errors
===========================================================================
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LEDGER_PATH = os.path.join(BASE_DIR, "results", "ai_budget_ledger.json")

MANDATORY_USER_AGENT = "PyrofuelQuantBot/3.0"
DEFAULT_GROQ_TPD_LIMIT = 200_000


def _utc_today_str(now_ts: Optional[float] = None) -> str:
    ts = now_ts if now_ts is not None else time.time()
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _next_utc_midnight_ts(now_ts: Optional[float] = None) -> float:
    ts = now_ts if now_ts is not None else time.time()
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp() + 86400.0


def _hash_key(api_key: str) -> str:
    if not api_key:
        return "nokey"
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:10]


def _parse_reset_duration_sec(val: Optional[str], default_sec: float = 60.0) -> float:
    """
    Parse rate-limit reset strings like '12m34.5s', '2h10m', '45s', '1500ms', or numeric seconds.
    """
    if not val:
        return default_sec
    s = str(val).strip().lower()
    try:
        return max(1.0, float(s))
    except ValueError:
        pass

    if s.endswith("ms"):
        try:
            return max(0.5, float(s[:-2]) / 1000.0)
        except ValueError:
            return default_sec

    total = 0.0
    matched = False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([hms])", s):
        matched = True
        v = float(num)
        if unit == "h":
            total += v * 3600.0
        elif unit == "m":
            total += v * 60.0
        elif unit == "s":
            total += v
    return max(1.0, total) if matched else default_sec


def strip_reasoning_tags(raw_text: str) -> str:
    """
    Strip <think>...</think>, <reasoning>...</reasoning>, and markdown fences
    before JSON parsing. Handles both closed and truncated <think> blocks.
    """
    if not raw_text:
        return ""
    text = str(raw_text)
    # Remove closed <think>...</think> and <reasoning>...</reasoning>
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # If an unclosed <think> precedes a JSON object, strip up to the first '{' after it
    if re.search(r"<think>", text, flags=re.IGNORECASE):
        parts = re.split(r"<think>", text, flags=re.IGNORECASE)
        tail = parts[-1]
        brace_idx = tail.find("{")
        if brace_idx != -1:
            text = parts[0] + tail[brace_idx:]
        else:
            text = parts[0]

    # Strip markdown code blocks ```json ... ``` or ``` ... ```
    text = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", text, flags=re.DOTALL | re.IGNORECASE)
    text = text.strip()

    # Extract balanced outermost JSON object if extra prose wraps it
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return text[start_idx : end_idx + 1].strip()
    return text


def validate_decision_schema(
    payload: Any, schema_type: str = "PRIMARY"
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Strictly validate and normalize structured AI JSON output.
    Supported schema_type:
      - "PRIMARY": Meta-labeling primary decision schema (T5.1)
      - "AUDITOR": Cross-model Red-Team risk auditor schema (T5.1)
      - "EMERGENCY": Intrabar thesis invalidation emergency review schema (T6.3)
    Returns (is_valid, error_msg, normalized_dict).
    """
    if not isinstance(payload, dict):
        return False, "Payload is not a JSON object (dict)", {}

    stype = schema_type.upper()

    if stype == "PRIMARY":
        required_keys = [
            "decision",
            "selected_strategy_id",
            "direction",
            "execution_style",
            "entry_price",
            "sl_price",
            "tp_price",
            "p_win_raw",
            "key_confluences",
            "primary_failure_mode",
            "reasoning_id",
        ]
        for k in required_keys:
            if k not in payload:
                return False, f"Missing required key: '{k}'", {}

        decision = str(payload.get("decision", "")).upper().strip()
        if decision not in ("TRADE", "SKIP"):
            return False, f"Invalid decision '{decision}', must be TRADE or SKIP", {}

        direction = str(payload.get("direction", "")).upper().strip()
        if direction not in ("LONG", "SHORT", "NONE"):
            return False, f"Invalid direction '{direction}', must be LONG, SHORT, or NONE", {}

        if decision == "TRADE" and direction not in ("LONG", "SHORT"):
            return False, "TRADE decision requires direction to be LONG or SHORT", {}

        exec_style = str(payload.get("execution_style", "MAKER_FIRST_GTX")).upper().strip()
        if exec_style not in ("MAKER_FIRST_GTX", "IMMEDIATE_IOC"):
            return False, f"Invalid execution_style '{exec_style}'", {}

        try:
            entry_price = float(payload["entry_price"])
            sl_price = float(payload["sl_price"])
            tp_price = float(payload["tp_price"])
            p_win_raw = float(payload["p_win_raw"])
        except (TypeError, ValueError) as exc:
            return False, f"Numeric conversion error: {exc}", {}

        # Normalize percentage if model output 0..100 instead of 0..1, or reject out-of-range
        if not (0.0 <= p_win_raw <= 1.0):
            return False, f"p_win_raw={p_win_raw} out of [0.0, 1.0] range", {}

        if decision == "TRADE":
            if entry_price <= 0 or sl_price <= 0 or tp_price <= 0:
                return False, "TRADE decision requires positive entry_price, sl_price, and tp_price", {}
            if direction == "LONG" and not (sl_price < entry_price < tp_price):
                return False, f"Invalid LONG price ordering: SL({sl_price}) < Entry({entry_price}) < TP({tp_price}) required", {}
            if direction == "SHORT" and not (tp_price < entry_price < sl_price):
                return False, f"Invalid SHORT price ordering: TP({tp_price}) < Entry({entry_price}) < SL({sl_price}) required", {}

        confluences = payload.get("key_confluences")
        if not isinstance(confluences, list):
            return False, "key_confluences must be a JSON array of strings", {}

        reasoning_id = str(payload.get("reasoning_id", "")).strip()
        if not reasoning_id:
            return False, "reasoning_id cannot be empty", {}

        normalized = {
            "decision": decision,
            "selected_strategy_id": str(payload.get("selected_strategy_id", "")).strip(),
            "direction": direction,
            "execution_style": exec_style,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "p_win_raw": p_win_raw,
            "key_confluences": [str(x) for x in confluences],
            "primary_failure_mode": str(payload.get("primary_failure_mode", "")).strip(),
            "reasoning_id": reasoning_id,
        }
        return True, "", normalized

    elif stype == "AUDITOR":
        for k in ("verdict", "p_win_audit", "fatal_flaws", "audit_reasoning_id"):
            if k not in payload:
                return False, f"Missing required AUDITOR key: '{k}'", {}
        verdict = str(payload.get("verdict", "")).upper().strip()
        if verdict not in ("APPROVE", "VETO"):
            return False, f"Invalid auditor verdict '{verdict}', must be APPROVE or VETO", {}
        try:
            p_win_audit = float(payload["p_win_audit"])
        except (TypeError, ValueError) as exc:
            return False, f"Invalid p_win_audit: {exc}", {}
        if not (0.0 <= p_win_audit <= 1.0):
            return False, f"p_win_audit={p_win_audit} out of [0.0, 1.0]", {}
        flaws = payload.get("fatal_flaws")
        if not isinstance(flaws, list):
            return False, "fatal_flaws must be a list", {}
        normalized = {
            "verdict": verdict,
            "p_win_audit": p_win_audit,
            "fatal_flaws": [str(x) for x in flaws],
            "audit_reasoning_id": str(payload.get("audit_reasoning_id", "")).strip(),
        }
        return True, "", normalized

    elif stype == "EMERGENCY":
        for k in ("action", "p_survive_ai", "reasoning_id"):
            if k not in payload:
                return False, f"Missing required EMERGENCY key: '{k}'", {}
        action = str(payload.get("action", "")).upper().strip()
        if action not in ("ABORT_THESIS_SCRATCH", "HOLD_POSITION"):
            return False, f"Invalid emergency action '{action}'", {}
        try:
            p_survive_ai = float(payload["p_survive_ai"])
        except (TypeError, ValueError) as exc:
            return False, f"Invalid p_survive_ai: {exc}", {}
        if not (0.0 <= p_survive_ai <= 1.0):
            return False, f"p_survive_ai={p_survive_ai} out of [0.0, 1.0]", {}
        normalized = {
            "action": action,
            "p_survive_ai": p_survive_ai,
            "reasoning_id": str(payload.get("reasoning_id", "")).strip(),
        }
        return True, "", normalized

    return False, f"Unknown schema_type '{schema_type}'", {}


def classify_http_error(
    status_code: int, body_text: str, headers: Optional[Dict[str, str]] = None
) -> Tuple[str, float]:
    """
    Classify provider HTTP errors into:
      - ("EXHAUSTED_TPD", reset_epoch_ts)
      - ("COOLDOWN_RPM", cooldown_until_ts)
      - ("INVALID_OR_UNPAID", cooldown_until_ts)
      - ("TRANSIENT_ERROR", cooldown_until_ts)
    """
    now = time.time()
    hdrs = {k.lower(): v for k, v in (headers or {}).items()}
    low_body = (body_text or "").lower()

    if status_code in (401, 402, 403):
        return "INVALID_OR_UNPAID", now + 86400.0

    if status_code == 429:
        # Check if TPD (Tokens Per Day) or daily quota exhausted
        is_tpd = any(
            marker in low_body
            for marker in (
                "tokens per day",
                "(tpd)",
                "tpd",
                "daily limit",
                "requests per day",
                "(rpd)",
                "quota exceeded for the day",
                "per day",
            )
        )
        if is_tpd:
            reset_tok = hdrs.get("x-ratelimit-reset-tokens") or hdrs.get("x-ratelimit-reset-requests")
            if reset_tok:
                dur = _parse_reset_duration_sec(reset_tok, default_sec=_next_utc_midnight_ts(now) - now)
                # Ensure TPD lock lasts at least 5 minutes or until UTC midnight
                return "EXHAUSTED_TPD", max(now + dur, _next_utc_midnight_ts(now))
            return "EXHAUSTED_TPD", _next_utc_midnight_ts(now)

        # Otherwise 429 RPM / TPM short cooldown
        retry_after = (
            hdrs.get("retry-after")
            or hdrs.get("x-ratelimit-reset-requests")
            or hdrs.get("x-ratelimit-reset-tokens")
        )
        wait_sec = _parse_reset_duration_sec(retry_after, default_sec=30.0)
        return "COOLDOWN_RPM", now + min(wait_sec, 300.0)

    return "TRANSIENT_ERROR", now + 15.0


def _infer_model_family(model_name: str) -> str:
    m = (model_name or "").lower()
    if "qwen" in m:
        return "qwen"
    if "llama" in m:
        return "llama"
    if "deepseek" in m:
        return "deepseek"
    if "gemini" in m:
        return "gemini"
    if "mistral" in m or "mixtral" in m:
        return "mistral"
    if "gemma" in m:
        return "gemma"
    return m.split("/")[0] if "/" in m else m


class AIGateway:
    """
    Multi-Provider Token-Aware AI Gateway (T2.1 & T2.2).
    """

    PROVIDER_CONFIGS = {
        "groq": {
            "chat_url": "https://api.groq.com/openai/v1/chat/completions",
            "models_url": "https://api.groq.com/openai/v1/models",
            "default_models": [
                "openai/gpt-oss-120b",
                "qwen/qwen3.8-27b",
                "openai/gpt-oss-20b",
            ],
            "tpd_limit": DEFAULT_GROQ_TPD_LIMIT,
            "env_keys": ("GROQ_API_KEYS", "GROQ_API_KEY"),
        },
        "gemini": {
            "chat_url_template": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            "default_models": ["gemini-2.5-flash", "gemini-2.5-pro"],
            "tpd_limit": 1_000_000,
            "env_keys": ("GEMINI_API_KEYS", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
        },
        "cerebras": {
            "chat_url": "https://api.cerebras.ai/v1/chat/completions",
            "default_models": ["llama-3.3-70b", "qwen-3-32b"],
            "tpd_limit": 500_000,
            "env_keys": ("CEREBRAS_API_KEYS", "CEREBRAS_API_KEY"),
        },
        "mistral": {
            "chat_url": "https://api.mistral.ai/v1/chat/completions",
            "default_models": ["mistral-small-latest"],
            "tpd_limit": 500_000,
            "env_keys": ("MISTRAL_API_KEYS", "MISTRAL_API_KEY"),
        },
        "openrouter": {
            "chat_url": "https://openrouter.ai/api/v1/chat/completions",
            "default_models": [
                "meta-llama/llama-3.3-70b-instruct:free",
                "qwen/qwen3-32b:free",
                "deepseek/deepseek-r1:free",
            ],
            "tpd_limit": 300_000,
            "env_keys": ("OPENROUTER_API_KEYS", "OPENROUTER_API_KEY"),
        },
        "nvidia": {
            "chat_url": "https://integrate.api.nvidia.com/v1/chat/completions",
            "default_models": ["meta/llama-3.3-70b-instruct"],
            "tpd_limit": 500_000,
            "env_keys": ("NVIDIA_API_KEYS", "NVIDIA_API_KEY"),
        },
    }

    def __init__(
        self,
        ledger_path: Optional[str] = None,
        provider_keys: Optional[Dict[str, List[str]]] = None,
        http_client: Optional[Any] = None,
        discover_groq_models: bool = False,
        persist_ledger: bool = True,
    ):
        self.ledger_path = ledger_path or DEFAULT_LEDGER_PATH
        self.persist_ledger = persist_ledger
        self._lock = threading.RLock()
        self.session = http_client or requests.Session()
        if hasattr(self.session, "headers") and isinstance(self.session.headers, dict):
            self.session.headers.update({"User-Agent": MANDATORY_USER_AGENT})

        self.provider_keys: Dict[str, List[str]] = self._load_provider_keys(provider_keys)
        self.provider_models: Dict[str, List[str]] = {
            p: list(cfg["default_models"]) for p, cfg in self.PROVIDER_CONFIGS.items()
        }

        self.ledger: Dict[str, Any] = {
            "utc_date": _utc_today_str(),
            "buckets": {},
            "total_calls_today": 0,
            "total_tokens_today": 0,
        }
        self._load_ledger()

        # Per-candle prompt cache: (symbol, tf, closed_bar_ts, strategy_id, stage) -> response dict
        self._candle_cache: Dict[Tuple[str, ...], Dict[str, Any]] = {}

        if discover_groq_models and self.provider_keys.get("groq"):
            self.discover_groq_models()

    def _load_provider_keys(
        self, explicit_keys: Optional[Dict[str, List[str]]] = None
    ) -> Dict[str, List[str]]:
        pool: Dict[str, List[str]] = {p: [] for p in self.PROVIDER_CONFIGS}
        if explicit_keys:
            for p, keys in explicit_keys.items():
                if p in pool and keys:
                    pool[p].extend([k.strip() for k in keys if k and k.strip()])

        for p, cfg in self.PROVIDER_CONFIGS.items():
            if pool[p]:
                continue
            collected: List[str] = []
            for env_name in cfg["env_keys"]:
                raw = os.environ.get(env_name, "")
                if raw:
                    for part in raw.split(","):
                        clean = part.strip().strip('"').strip("'")
                        if clean and clean not in collected:
                            collected.append(clean)
            # Also check numbered keys like GROQ_API_KEY_1, GROQ_API_KEY_2, etc.
            base_env = cfg["env_keys"][-1]
            for idx in range(1, 10):
                numbered = os.environ.get(f"{base_env}_{idx}", "").strip().strip('"').strip("'")
                if numbered and numbered not in collected:
                    collected.append(numbered)
            pool[p] = collected
        return pool

    def _bucket_id(self, provider: str, model: str, api_key: str) -> str:
        return f"{provider}:{model}:{_hash_key(api_key)}"

    def _ensure_utc_day_current(self, now_ts: Optional[float] = None) -> None:
        today = _utc_today_str(now_ts)
        if self.ledger.get("utc_date") != today:
            self.ledger = {
                "utc_date": today,
                "buckets": {},
                "total_calls_today": 0,
                "total_tokens_today": 0,
            }
            self._save_ledger()

    def _load_ledger(self) -> None:
        if not self.persist_ledger or not self.ledger_path:
            return
        if os.path.exists(self.ledger_path):
            try:
                with open(self.ledger_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("utc_date") == _utc_today_str():
                    self.ledger = data
            except Exception:
                pass

    def _save_ledger(self) -> None:
        if not self.persist_ledger or not self.ledger_path:
            return
        try:
            os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
            tmp_path = f"{self.ledger_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.ledger, f, indent=2)
            os.replace(tmp_path, self.ledger_path)
        except Exception:
            pass

    def _get_bucket(self, provider: str, model: str, api_key: str) -> Dict[str, Any]:
        bid = self._bucket_id(provider, model, api_key)
        buckets = self.ledger.setdefault("buckets", {})
        if bid not in buckets:
            tpd_limit = self.PROVIDER_CONFIGS.get(provider, {}).get("tpd_limit", DEFAULT_GROQ_TPD_LIMIT)
            buckets[bid] = {
                "provider": provider,
                "model": model,
                "key_hash": _hash_key(api_key),
                "status": "ACTIVE",
                "tokens_used_today": 0,
                "tpd_limit": tpd_limit,
                "remaining_tokens_header": None,
                "remaining_requests_header": None,
                "cooldown_until": 0.0,
                "calls_today": 0,
                "last_error": None,
            }
        return buckets[bid]

    def is_bucket_available(
        self, provider: str, model: str, api_key: str, estimated_tokens: int = 1200, now_ts: Optional[float] = None
    ) -> bool:
        now = now_ts if now_ts is not None else time.time()
        with self._lock:
            self._ensure_utc_day_current(now)
            b = self._get_bucket(provider, model, api_key)
            status = b.get("status", "ACTIVE")
            cooldown_until = float(b.get("cooldown_until", 0.0))

            if status == "INVALID_OR_UNPAID":
                return False

            if cooldown_until > now:
                return False
            elif status in ("EXHAUSTED_TPD", "COOLDOWN_RPM", "TRANSIENT_ERROR") and cooldown_until <= now:
                # Cooldown expired
                b["status"] = "ACTIVE"
                b["cooldown_until"] = 0.0

            # Check TPD ledger limit
            used = int(b.get("tokens_used_today", 0))
            tpd_limit = int(b.get("tpd_limit", DEFAULT_GROQ_TPD_LIMIT))
            if used + estimated_tokens > tpd_limit:
                b["status"] = "EXHAUSTED_TPD"
                b["cooldown_until"] = _next_utc_midnight_ts(now)
                self._save_ledger()
                return False

            return True

    def update_from_headers_and_usage(
        self,
        provider: str,
        model: str,
        api_key: str,
        headers: Optional[Dict[str, str]],
        tokens_used: int,
        now_ts: Optional[float] = None,
    ) -> None:
        now = now_ts if now_ts is not None else time.time()
        hdrs = {k.lower(): v for k, v in (headers or {}).items()}
        with self._lock:
            self._ensure_utc_day_current(now)
            b = self._get_bucket(provider, model, api_key)
            b["tokens_used_today"] = int(b.get("tokens_used_today", 0)) + int(tokens_used)
            b["calls_today"] = int(b.get("calls_today", 0)) + 1
            self.ledger["total_tokens_today"] = int(self.ledger.get("total_tokens_today", 0)) + int(tokens_used)
            self.ledger["total_calls_today"] = int(self.ledger.get("total_calls_today", 0)) + 1

            rem_tok = hdrs.get("x-ratelimit-remaining-tokens")
            if rem_tok is not None:
                try:
                    rem_tok_int = int(float(rem_tok))
                    b["remaining_tokens_header"] = rem_tok_int
                    if rem_tok_int < 500:
                        reset_str = hdrs.get("x-ratelimit-reset-tokens")
                        dur = _parse_reset_duration_sec(reset_str, default_sec=30.0)
                        b["status"] = "COOLDOWN_RPM"
                        b["cooldown_until"] = now + dur
                except ValueError:
                    pass

            rem_req = hdrs.get("x-ratelimit-remaining-requests")
            if rem_req is not None:
                try:
                    rem_req_int = int(float(rem_req))
                    b["remaining_requests_header"] = rem_req_int
                    if rem_req_int <= 0:
                        reset_str = hdrs.get("x-ratelimit-reset-requests")
                        dur = _parse_reset_duration_sec(reset_str, default_sec=60.0)
                        b["status"] = "COOLDOWN_RPM"
                        b["cooldown_until"] = now + dur
                except ValueError:
                    pass

            if b["tokens_used_today"] >= int(b.get("tpd_limit", DEFAULT_GROQ_TPD_LIMIT)):
                b["status"] = "EXHAUSTED_TPD"
                b["cooldown_until"] = _next_utc_midnight_ts(now)

            self._save_ledger()

    def mark_bucket_error(
        self,
        provider: str,
        model: str,
        api_key: str,
        status_code: int,
        body_text: str,
        headers: Optional[Dict[str, str]] = None,
        now_ts: Optional[float] = None,
    ) -> str:
        now = now_ts if now_ts is not None else time.time()
        err_class, until_ts = classify_http_error(status_code, body_text, headers)
        with self._lock:
            self._ensure_utc_day_current(now)
            b = self._get_bucket(provider, model, api_key)
            b["status"] = err_class
            b["cooldown_until"] = until_ts
            b["last_error"] = f"HTTP {status_code}: {body_text[:200]}"
            self._save_ledger()
        return err_class

    def discover_groq_models(self) -> List[str]:
        """
        Discover active Groq models via GET https://api.groq.com/openai/v1/models
        with mandatory User-Agent: PyrofuelQuantBot/3.0 (prevents Cloudflare 1010).
        """
        keys = self.provider_keys.get("groq", [])
        if not keys:
            return self.provider_models["groq"]

        headers = {
            "Authorization": f"Bearer {keys[0]}",
            "User-Agent": MANDATORY_USER_AGENT,
            "Accept": "application/json",
        }
        try:
            resp = self.session.get(
                self.PROVIDER_CONFIGS["groq"]["models_url"],
                headers=headers,
                timeout=6.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                models_raw = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
                preferred = [
                    m
                    for m in self.PROVIDER_CONFIGS["groq"]["default_models"]
                    if m in models_raw
                ]
                for m in models_raw:
                    if m not in preferred and any(
                        tag in m.lower() for tag in ("gpt-oss", "qwen", "llama-3.3", "deepseek", "llama-3.1")
                    ):
                        if "whisper" not in m.lower() and "guard" not in m.lower() and "tts" not in m.lower():
                            preferred.append(m)
                if preferred:
                    self.provider_models["groq"] = preferred
        except Exception:
            pass
        return self.provider_models["groq"]

    def _build_candidate_routes(
        self,
        exclude_provider: Optional[str] = None,
        exclude_model_family: Optional[str] = None,
        estimated_tokens: int = 1200,
    ) -> List[Tuple[str, str, str]]:
        """
        Return ordered list of available (provider, model, api_key) routes.
        If exclude_provider / exclude_model_family are set (e.g. for Cross-Model Red-Team Auditor),
        prioritizes routes from a different model family/provider first.
        """
        primary_routes: List[Tuple[str, str, str]] = []
        fallback_routes: List[Tuple[str, str, str]] = []

        for provider in ("groq", "gemini", "cerebras", "mistral", "openrouter", "nvidia"):
            keys = self.provider_keys.get(provider, [])
            models = self.provider_models.get(provider, [])
            for model in models:
                family = _infer_model_family(model)
                for key in keys:
                    if not self.is_bucket_available(provider, model, key, estimated_tokens=estimated_tokens):
                        continue
                    is_excluded = (
                        (exclude_provider and provider == exclude_provider)
                        and (exclude_model_family and family == exclude_model_family)
                    ) or (exclude_model_family and family == exclude_model_family)
                    if is_excluded:
                        fallback_routes.append((provider, model, key))
                    else:
                        primary_routes.append((provider, model, key))

        return primary_routes + fallback_routes

    def _invoke_provider_http(
        self,
        provider: str,
        model: str,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 900,
    ) -> Tuple[int, str, Dict[str, str], int]:
        """
        Execute single HTTP request against the selected provider.
        Returns (status_code, raw_content_or_err, headers_dict, total_tokens_used).
        """
        # Ensure the word 'json' is always present in the system prompt for OpenAI json_object mode
        if "json" not in system_prompt.lower():
            system_prompt = f"{system_prompt}\nRespond strictly in valid JSON format."

        if provider == "gemini":
            url = self.PROVIDER_CONFIGS["gemini"]["chat_url_template"].format(model=model)
            headers = {
                "Content-Type": "application/json",
                "User-Agent": MANDATORY_USER_AGENT,
                "x-goog-api-key": api_key,
            }
            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                    "responseMimeType": "application/json",
                },
            }
            resp = self.session.post(url, headers=headers, json=payload, timeout=15.0)
            resp_headers = dict(getattr(resp, "headers", {}) or {})
            if resp.status_code >= 400:
                return resp.status_code, resp.text, resp_headers, 0
            data = resp.json()
            candidates = data.get("candidates", [])
            content = ""
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                content = "".join(p.get("text", "") for p in parts)
            usage = data.get("usageMetadata", {})
            tokens = int(usage.get("totalTokenCount", 0)) or (
                (len(system_prompt) + len(user_prompt) + len(content)) // 4
            )
            return 200, content, resp_headers, tokens

        else:
            url = self.PROVIDER_CONFIGS[provider]["chat_url"]
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": MANDATORY_USER_AGENT,
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            }
            resp = self.session.post(url, headers=headers, json=payload, timeout=15.0)
            resp_headers = dict(getattr(resp, "headers", {}) or {})
            if resp.status_code >= 400:
                return resp.status_code, resp.text, resp_headers, 0
            data = resp.json()
            choices = data.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            usage = data.get("usage", {})
            tokens = int(usage.get("total_tokens", 0)) or (
                (len(system_prompt) + len(user_prompt) + len(content)) // 4
            )
            return 200, content, resp_headers, tokens

    def call_structured(
        self,
        user_prompt: str,
        system_prompt: str,
        schema_type: str = "PRIMARY",
        cache_key: Optional[Tuple[Any, ...]] = None,
        exclude_provider: Optional[str] = None,
        exclude_model_family: Optional[str] = None,
        max_repair_retries: int = 1,
        estimated_tokens: int = 1200,
    ) -> Dict[str, Any]:
        """
        Execute a token-aware structured JSON AI call with:
          1. Per-candle prompt hash cache check
          2. Automatic multi-key / multi-model / multi-provider failover on 429 TPD/RPM & 401/402
          3. <think>...</think> tag stripping
          4. Strict schema validation + 1x repair retry on malformed JSON
        """
        norm_cache_key: Optional[Tuple[str, ...]] = None
        if cache_key is not None:
            norm_cache_key = tuple(str(x) for x in cache_key) + (schema_type.upper(),)
            with self._lock:
                if norm_cache_key in self._candle_cache:
                    cached = dict(self._candle_cache[norm_cache_key])
                    cached["cache_hit"] = True
                    cached["tokens_used"] = 0
                    return cached

        routes = self._build_candidate_routes(
            exclude_provider=exclude_provider,
            exclude_model_family=exclude_model_family,
            estimated_tokens=estimated_tokens,
        )
        if not routes:
            return {
                "ok": False,
                "error": "SKIP_AI_UNAVAILABLE",
                "error_detail": "All AI providers/keys are exhausted or unconfigured",
                "data": None,
                "provider": None,
                "model": None,
                "tokens_used": 0,
                "cache_hit": False,
            }

        t0 = time.time()
        total_tokens_consumed = 0
        last_err_detail = "No route succeeded"

        for provider, model, api_key in routes:
            if not self.is_bucket_available(provider, model, api_key, estimated_tokens=estimated_tokens):
                continue

            current_user_prompt = user_prompt
            for attempt in range(max_repair_retries + 1):
                try:
                    status_code, raw_text, resp_headers, tokens_used = self._invoke_provider_http(
                        provider=provider,
                        model=model,
                        api_key=api_key,
                        system_prompt=system_prompt,
                        user_prompt=current_user_prompt,
                    )
                except Exception as exc:
                    self.mark_bucket_error(provider, model, api_key, 503, str(exc))
                    last_err_detail = f"Network error on {provider}/{model}: {exc}"
                    break  # Move to next route

                if status_code >= 400:
                    err_class = self.mark_bucket_error(
                        provider, model, api_key, status_code, raw_text, resp_headers
                    )
                    last_err_detail = f"{err_class} ({status_code}) on {provider}/{model}"
                    break  # Rotate to next key/model/provider

                total_tokens_consumed += tokens_used
                self.update_from_headers_and_usage(
                    provider, model, api_key, resp_headers, tokens_used
                )

                cleaned = strip_reasoning_tags(raw_text)
                try:
                    parsed = json.loads(cleaned)
                except Exception as parse_exc:
                    last_err_detail = f"JSONDecodeError: {parse_exc}"
                    if attempt < max_repair_retries:
                        current_user_prompt = (
                            f"{user_prompt}\n\n"
                            f"[REPAIR INSTRUCTION]: Your previous output was not valid JSON ({parse_exc}). "
                            f"Return ONLY a single valid JSON object matching the required {schema_type} schema."
                        )
                        continue
                    break

                valid, val_err, normalized = validate_decision_schema(parsed, schema_type=schema_type)
                if not valid:
                    last_err_detail = f"SchemaValidationError: {val_err}"
                    if attempt < max_repair_retries:
                        current_user_prompt = (
                            f"{user_prompt}\n\n"
                            f"[REPAIR INSTRUCTION]: Your previous JSON failed schema validation: {val_err}. "
                            f"Fix the field values/types and return ONLY the corrected JSON object."
                        )
                        continue
                    break

                result = {
                    "ok": True,
                    "error": None,
                    "data": normalized,
                    "provider": provider,
                    "model": model,
                    "model_family": _infer_model_family(model),
                    "tokens_used": total_tokens_consumed,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "cache_hit": False,
                }
                if norm_cache_key is not None:
                    with self._lock:
                        self._candle_cache[norm_cache_key] = dict(result)
                return result

        return {
            "ok": False,
            "error": "SKIP_AI_UNAVAILABLE",
            "error_detail": last_err_detail,
            "data": None,
            "provider": None,
            "model": None,
            "tokens_used": total_tokens_consumed,
            "latency_ms": int((time.time() - t0) * 1000),
            "cache_hit": False,
        }

    def get_budget_summary(self) -> Dict[str, Any]:
        with self._lock:
            self._ensure_utc_day_current()
            return json.loads(json.dumps(self.ledger))
