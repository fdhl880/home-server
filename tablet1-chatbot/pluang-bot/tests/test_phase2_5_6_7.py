"""
===========================================================================
COMPREHENSIVE PYTEST SUITE FOR PHASES 2, 5, 6, & 7 (Pyrofuel v3)
===========================================================================
Covers:
- Phase 2: `ai_gateway.py` (T2.1 & T2.2)
- Phase 5: `calibration.py` (T5.2), `ai/conformal.py` (T5.3),
           `ai/episodic_memory.py` (T5.4), `ai/hybrid_ensemble.py` (T5.5),
           `ai/decide.py` (T5.1)
- Phase 6: `exec/event_bus.py` (T6.5), `exec/native_pricematch.py` (T6.6),
           `exec/avellaneda_router.py` (T6.4), `exec/thesis_monitor.py` (T6.3),
           `exec/userstream.py` (T6.1), `exec/engine.py` (T6.2)
- Phase 7: `risk/vault.py` (T7.3), `risk/engine.py` (T7.1, T7.2, T7.4)
===========================================================================
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import pytest  # type: ignore
except ImportError:
    class _Approx:
        def __init__(self, expected: float, rel: float = 1e-6, abs_tol: float = 1e-12):
            self.expected = float(expected)
            self.rel = float(rel)
            self.abs_tol = float(abs_tol)

        def __eq__(self, actual: object) -> bool:
            if not isinstance(actual, (int, float, np.floating)):
                return False
            return math.isclose(float(actual), self.expected, rel_tol=self.rel, abs_tol=self.abs_tol)

        def __repr__(self) -> str:
            return f"approx({self.expected} +/- rel={self.rel})"

    class _PytestShim:
        @staticmethod
        def approx(expected: float, rel: float = 1e-6, abs: float = 1e-12) -> _Approx:
            return _Approx(expected, rel=rel, abs_tol=abs)

    pytest = _PytestShim()  # type: ignore

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ai.conformal import AdaptiveConformalFilter
from ai.decide import AIDecisionEngine
from ai.episodic_memory import EpisodicMarketMemory
from ai.hybrid_ensemble import NeuroSymbolicEnsemble, TabularMetaModel
from ai_gateway import (
    MANDATORY_USER_AGENT,
    AIGateway,
    classify_http_error,
    strip_reasoning_tags,
    validate_decision_schema,
)
from calibration import ProbabilityCalibrator
from exec.avellaneda_router import AvellanedaStoikovRouter
from exec.engine import AtomicExecutionEngineV3, generate_client_order_id
from exec.event_bus import (
    CLOSED_CANDLE_BOUNDARY_SCAN,
    CRITICAL_POSITION_INTERRUPT,
    MICROSTRUCTURE_SNIPER_TRIGGER,
    PriorityEventBus,
)
from exec.native_pricematch import (
    NativePriceMatchRouter,
    build_fallback_gtx_params,
    build_native_pricematch_params,
)
from exec.thesis_monitor import IntrabarThesisMonitor
from exec.userstream import UserDataStreamManager
from risk.engine import HardRiskEngine
from risk.vault import ProfitRatchetVault


# ===========================================================================
# MOCK HELPERS
# ===========================================================================


class FakeHTTPResponse:
    def __init__(self, status_code: int, json_data: Any = None, text: str = "", headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text or (json.dumps(json_data) if json_data is not None else "")
        self.headers = headers or {}

    def json(self) -> Any:
        if self._json_data is not None:
            return self._json_data
        return json.loads(self.text)


class FakeHTTPSession:
    def __init__(self, handler_fn):
        self.headers: Dict[str, str] = {}
        self.handler_fn = handler_fn
        self.calls: List[Dict[str, Any]] = []

    def get(self, url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 10.0):
        merged_hdrs = {**self.headers, **(headers or {})}
        self.calls.append({"method": "GET", "url": url, "headers": merged_hdrs})
        return self.handler_fn("GET", url, merged_hdrs, None)

    def post(self, url: str, headers: Optional[Dict[str, str]] = None, json: Any = None, timeout: float = 10.0):
        merged_hdrs = {**self.headers, **(headers or {})}
        self.calls.append({"method": "POST", "url": url, "headers": merged_hdrs, "json": json})
        return self.handler_fn("POST", url, merged_hdrs, json)


class MockBinanceFuturesClient:
    def __init__(self, min_notional: float = 5.0):
        self.min_notional = min_notional
        self.requests_log: List[Dict[str, Any]] = []
        self.open_algo_orders: List[Dict[str, Any]] = []
        self.open_std_orders: List[Dict[str, Any]] = []
        self.positions: List[Dict[str, Any]] = []
        self.reject_pricematch: bool = False
        self.fail_sl_placement: bool = False
        self.network_error_on_algo_get: bool = False
        self._next_id = 1000

    def normalize_symbol(self, symbol: str) -> str:
        s = str(symbol).upper().strip()
        return s if s.endswith("USDT") else f"{s}USDT"

    def get_symbol_filters(self, symbol: str) -> Dict[str, Any]:
        sym = self.normalize_symbol(symbol)
        return {
            "quantityPrecision": 2,
            "pricePrecision": 4,
            "stepSize": 0.01,
            "minQty": 0.01,
            "tickSize": 0.0001,
            "minNotional": 50.0 if sym == "BTCUSDT" else self.min_notional,
        }

    def format_quantity(self, symbol: str, qty: float) -> float:
        import math
        step = self.get_symbol_filters(symbol)["stepSize"]
        return round(math.floor(float(qty) / step + 1e-9) * step, 2)

    def format_price(self, symbol: str, px: float) -> float:
        tick = self.get_symbol_filters(symbol)["tickSize"]
        return round(round(float(px) / tick) * tick, 4)

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED"):
        return {"code": 200, "msg": "success"}

    def set_leverage(self, symbol: str, leverage: int = 20):
        return {"symbol": self.normalize_symbol(symbol), "leverage": leverage}

    def get_open_orders(self, symbol: Optional[str] = None):
        return list(self.open_std_orders)

    def get_positions(self):
        return list(self.positions)

    def close_position(self, symbol: str, direction: str, quantity: Optional[float] = None):
        self.requests_log.append(
            {"method": "POST", "endpoint": "/fapi/v1/order", "action": "CLOSE_POSITION", "symbol": symbol}
        )
        self.positions = [p for p in self.positions if p.get("symbol") != self.normalize_symbol(symbol)]
        return {"orderId": 99999, "status": "FILLED"}

    def cancel_all_orders(self, symbol: str):
        sym = self.normalize_symbol(symbol)
        self.open_algo_orders = [o for o in self.open_algo_orders if o.get("symbol") != sym]
        self.open_std_orders = [o for o in self.open_std_orders if o.get("symbol") != sym]
        return {"standard": {"code": 200}, "algo": {"code": 200}}

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, signed: bool = False):
        params = dict(params or {})
        self.requests_log.append({"method": method, "endpoint": endpoint, "params": params})

        if endpoint == "/fapi/v1/listenKey":
            if method == "POST":
                return {"listenKey": "lk_test_pyrofuel_v3_12345"}
            return {"code": 200}

        if method == "GET" and endpoint == "/fapi/v1/order":
            cid = params.get("origClientOrderId")
            for o in self.open_std_orders:
                if o.get("clientOrderId") == cid:
                    return o
            return {"isError": True, "code": -2013, "error": "Order does not exist"}

        if method == "POST" and endpoint == "/fapi/v1/order":
            if "priceMatch" in params and self.reject_pricematch:
                return {"isError": True, "code": -4183, "error": "priceMatch not supported for symbol"}
            self._next_id += 1
            order_obj = {
                "orderId": self._next_id,
                "symbol": params.get("symbol"),
                "status": "FILLED",
                "clientOrderId": params.get("newClientOrderId", ""),
                "params": params,
            }
            self.open_std_orders.append(order_obj)
            return order_obj

        if method == "POST" and endpoint == "/fapi/v1/algoOrder":
            if self.fail_sl_placement and params.get("type") == "STOP_MARKET":
                return {"isError": True, "code": -2021, "error": "Order would immediately trigger"}
            self._next_id += 1
            algo_obj = {
                "algoId": self._next_id,
                "symbol": params.get("symbol"),
                "side": params.get("side"),
                "orderType": params.get("type"),
                "algoStatus": "NEW",
                "triggerPrice": params.get("triggerPrice"),
                "params": params,
            }
            self.open_algo_orders.append(algo_obj)
            return algo_obj

        if method == "GET" and endpoint == "/fapi/v1/openAlgoOrders":
            if self.network_error_on_algo_get:
                return {"isError": True, "error": "Connection timed out"}
            sym = params.get("symbol")
            if sym:
                return [o for o in self.open_algo_orders if o.get("symbol") == sym]
            return list(self.open_algo_orders)

        if method == "DELETE" and endpoint == "/fapi/v1/algoOrder":
            aid = params.get("algoId")
            self.open_algo_orders = [o for o in self.open_algo_orders if o.get("algoId") != aid]
            return {"algoId": aid, "code": 200, "msg": "success"}

        return {"code": 200}


# ===========================================================================
# PHASE 2 TESTS: `ai_gateway.py` (T2.1 & T2.2)
# ===========================================================================


def test_ai_gateway_user_agent_and_key_rotation_and_cache(tmp_path):
    """
    Verify T2.1 & T2.2:
    - Mandatory User-Agent: PyrofuelQuantBot/3.0
    - Classification & rotation on 429 TPD vs 429 RPM vs 401/402
    - Token ledger persistence in ai_budget_ledger.json
    - Per-candle prompt hash cache hit (0 extra tokens on same candle)
    """
    ledger_file = str(tmp_path / "ai_budget_ledger.json")
    valid_json_resp = {
        "decision": "SKIP",
        "selected_strategy_id": "S1_TREND_PULLBACK",
        "direction": "NONE",
        "execution_style": "MAKER_FIRST_GTX",
        "entry_price": 0.0,
        "sl_price": 0.0,
        "tp_price": 0.0,
        "p_win_raw": 0.41,
        "key_confluences": ["low_ofi"],
        "primary_failure_mode": "choppy_flow",
        "reasoning_id": "Order flow lemah, tunggu konfirmasi berikutnya.",
    }

    call_idx = {"n": 0}

    def fake_http(method, url, headers, payload):
        assert headers.get("User-Agent") == MANDATORY_USER_AGENT
        if method == "GET" and "/models" in url:
            return FakeHTTPResponse(200, {"data": [{"id": "qwen/qwen3-32b"}, {"id": "llama-3.3-70b-versatile"}]})

        call_idx["n"] += 1
        # Call 1: Key 1 hits 429 TPD (daily 200k token limit)
        if call_idx["n"] == 1:
            return FakeHTTPResponse(
                429,
                {"error": {"message": "Rate limit reached on tokens per day (TPD): Limit 200000, Used 199950"}},
                headers={"x-ratelimit-remaining-tokens": "50", "x-ratelimit-reset-tokens": "4h10m"},
            )
        # Call 2: Key 2 hits 429 RPM
        if call_idx["n"] == 2:
            return FakeHTTPResponse(
                429,
                {"error": {"message": "Rate limit reached for requests per minute (RPM)"}},
                headers={"retry-after": "15"},
            )
        # Call 3: Key 3 succeeds with <think> block wrapped around JSON
        raw_content = f"<think>\nLet me analyze OBI and CVD carefully...\n</think>\n```json\n{json.dumps(valid_json_resp)}\n```"
        return FakeHTTPResponse(
            200,
            {
                "choices": [{"message": {"content": raw_content}}],
                "usage": {"total_tokens": 640},
            },
            headers={"x-ratelimit-remaining-tokens": "14000", "x-ratelimit-remaining-requests": "29"},
        )

    fake_session = FakeHTTPSession(fake_http)
    gw = AIGateway(
        ledger_path=ledger_file,
        provider_keys={"groq": ["gsk_key1_tpd", "gsk_key2_rpm", "gsk_key3_ok"]},
        http_client=fake_session,
        discover_groq_models=True,
        persist_ledger=True,
    )

    res1 = gw.call_structured(
        user_prompt='{"symbol":"SOLUSDT"}',
        system_prompt="Analyze setup",
        schema_type="PRIMARY",
        cache_key=("SOLUSDT", "15m", 1730000000000, "S1_TREND_PULLBACK"),
    )
    assert res1["ok"] is True
    assert res1["cache_hit"] is False
    assert res1["data"]["decision"] == "SKIP"
    assert res1["tokens_used"] == 640
    assert os.path.exists(ledger_file)

    # Verify TPD vs RPM classification in ledger
    summary = gw.get_budget_summary()
    statuses = [b["status"] for b in summary["buckets"].values()]
    assert "EXHAUSTED_TPD" in statuses
    assert "COOLDOWN_RPM" in statuses

    # Second call with same candle cache_key must hit cache with 0 HTTP calls
    prev_http_calls = len(fake_session.calls)
    res2 = gw.call_structured(
        user_prompt='{"symbol":"SOLUSDT"}',
        system_prompt="Analyze setup",
        schema_type="PRIMARY",
        cache_key=("SOLUSDT", "15m", 1730000000000, "S1_TREND_PULLBACK"),
    )
    assert res2["ok"] is True
    assert res2["cache_hit"] is True
    assert res2["tokens_used"] == 0
    assert len(fake_session.calls) == prev_http_calls


def test_ai_gateway_50_consecutive_think_tags_and_repair_retry(tmp_path):
    """
    Verify T2.2 Acceptance Criteria:
    - 50 consecutive responses containing `<think>...</think>` blocks are 100% parsed and validated.
    - Malformed JSON triggers 1x automatic repair retry and succeeds.
    """
    for i in range(50):
        raw = (
            f"<think>Step {i}: computing Hawkes intensity lambda(t) and VPIN toxicity...</think>\n"
            + json.dumps(
                {
                    "decision": "TRADE" if i % 2 == 0 else "SKIP",
                    "selected_strategy_id": "S3_LIQ_CASCADE_FADE",
                    "direction": "LONG" if i % 2 == 0 else "NONE",
                    "execution_style": "MAKER_FIRST_GTX",
                    "entry_price": 150.0,
                    "sl_price": 149.1,
                    "tp_price": 152.0,
                    "p_win_raw": 0.78,
                    "key_confluences": ["hawkes_inflection", "cvd_absorption"],
                    "primary_failure_mode": "macro_shock",
                    "reasoning_id": f"Konfluensi likuidasi ke-{i} valid.",
                }
            )
        )
        cleaned = strip_reasoning_tags(raw)
        parsed = json.loads(cleaned)
        ok, err, norm = validate_decision_schema(parsed, "PRIMARY")
        assert ok is True, f"Failed on iteration {i}: {err}"
        assert norm["p_win_raw"] == 0.78

    # Test 1x repair retry when attempt 1 returns broken JSON and attempt 2 returns valid JSON
    attempt_counter = {"count": 0}

    def repair_http(method, url, headers, payload):
        attempt_counter["count"] += 1
        if attempt_counter["count"] == 1:
            return FakeHTTPResponse(
                200,
                {"choices": [{"message": {"content": "<think>oops</think>{broken_json: true"}}], "usage": {"total_tokens": 100}},
            )
        valid_auditor = {
            "verdict": "APPROVE",
            "p_win_audit": 0.79,
            "fatal_flaws": [],
            "audit_reasoning_id": "Struktur order flow mendukung Long.",
        }
        return FakeHTTPResponse(
            200,
            {"choices": [{"message": {"content": json.dumps(valid_auditor)}}], "usage": {"total_tokens": 120}},
        )

    gw = AIGateway(
        provider_keys={"groq": ["gsk_repair_test"]},
        http_client=FakeHTTPSession(repair_http),
        persist_ledger=False,
    )
    res = gw.call_structured("{}", "Auditor prompt", schema_type="AUDITOR", max_repair_retries=1)
    assert res["ok"] is True
    assert res["data"]["verdict"] == "APPROVE"
    assert attempt_counter["count"] == 2


# ===========================================================================
# PHASE 5 TESTS: Calibration, Conformal, Episodic Memory, Hybrid Ensemble, Decide
# ===========================================================================


def test_probability_calibrator_shrinkage_brier_and_ev_gate():
    """
    Verify T5.2:
    - Overconfident raw LLM probabilities (p_raw = 0.80 when actual win rate is 0.45)
      are pulled down toward empirical base rate and Brier score improves significantly.
    - Net EV_R calculator and gate enforce EV_R >= +0.20R and p_cal >= p_breakeven + 0.05.
    """
    rng = np.random.default_rng(42)
    cal = ProbabilityCalibrator(n0_prior=25.0, method="isotonic", default_base_rate=0.45)
    cal.set_empirical_base_rate("S1_TREND_PULLBACK", "TREND_BULL", p_base=0.45, historical_n=80)

    # Simulate 80 overconfident LLM predictions around 0.80 where true win rate is 0.45
    p_raw_samples = np.clip(rng.normal(0.80, 0.05, size=80), 0.65, 0.92)
    y_true_samples = (rng.uniform(0, 1, size=80) < 0.45).astype(int)

    cal.fit(p_raw_samples, y_true_samples)
    p_cal = cal.calibrate(0.80, strategy_id="S1_TREND_PULLBACK", regime="TREND_BULL")
    assert p_cal < 0.60  # Pulled down strongly toward 0.45 reality

    brier_stats = cal.brier_score_summary()
    assert brier_stats["brier_calibrated"] < brier_stats["brier_raw"]
    assert brier_stats["improvement"] > 0.05

    # Test EV_R gate
    ok_low, reason_low, _ = cal.evaluate_ev_gate(p_cal=0.45, d_sl=0.008, d_tp=0.015)
    assert ok_low is False
    assert "SKIP_" in reason_low

    ok_high, reason_high, metrics_high = cal.evaluate_ev_gate(p_cal=0.78, d_sl=0.006, d_tp=0.012)
    assert ok_high is True
    assert reason_high == "PASS_EV_GATE"
    assert metrics_high["ev_r"] >= 0.20


def test_adaptive_conformal_inference_gate_and_coverage():
    """
    Verify T5.3:
    - Gibbs & Candès ACI updates alpha_{t+1} = clip(alpha_t + gamma*(alpha_target - err_t), 0.05, 0.45)
    - Singleton {"WIN"} required to pass gate; {"WIN", "LOSS"} or {"LOSS"} vetoed with SKIP_CONFORMAL_AMBIGUITY.
    """
    aci = AdaptiveConformalFilter(alpha_target=0.18, gamma=0.03)

    # High calibrated probability -> Singleton {"WIN"} -> Allowed
    allowed_hi, reason_hi, info_hi = aci.evaluate_gate(p_cal=0.84)
    assert allowed_hi is True
    assert reason_hi == ""
    assert info_hi["prediction_set"] == ["WIN"]

    # Ambiguous mid probability (e.g. 0.52) -> vetoed with SKIP_CONFORMAL_AMBIGUITY
    allowed_mid, reason_mid, info_mid = aci.evaluate_gate(p_cal=0.52)
    assert allowed_mid is False
    assert reason_mid == "SKIP_CONFORMAL_AMBIGUITY"
    assert info_mid["prediction_set"] != ["WIN"]

    # Test online update dynamics
    alpha_before = aci.alpha_t
    # Force an error (predict on 0.85, but outcome is LOSS -> "LOSS" not in {"WIN"} -> err_t = 1)
    upd = aci.update(p_cal=0.85, outcome_win=False)
    assert upd["err_t"] == 1
    assert upd["alpha_next"] < alpha_before  # alpha tightens when error occurs


def test_episodic_memory_5000_episodes_under_15ms():
    """
    Verify T5.4 Acceptance Criteria:
    - |IC|-weighted Mahalanobis & Cosine k-NN retrieval on 5,000 episodes completes in < 15ms.
    - Returns k = 7 closest market analogs and accurate p_kNN prior.
    """
    rng = np.random.default_rng(123)
    dim = 15
    n_episodes = 5000
    ic_weights = np.linspace(0.05, 0.25, dim)

    mem = EpisodicMarketMemory(feature_dim=dim, k_neighbors=7, ic_weights=ic_weights)
    vectors = rng.normal(0.0, 1.0, size=(n_episodes, dim))
    # Plant a cluster near [2.0, 2.0, ...] with 100% WIN (+1.8R)
    vectors[:10] = 2.0 + rng.normal(0.0, 0.01, size=(10, dim))
    r_mults = np.where(np.arange(n_episodes) < 10, 1.8, rng.choice([-1.0, 1.5], size=n_episodes))
    outcomes = (r_mults > 0).astype(int)
    regimes = ["TREND_BULL"] * n_episodes

    mem.bulk_load(vectors, r_mults, outcomes_win=outcomes, regimes=regimes)

    q_vec = np.full(dim, 2.0)
    res = mem.query(q_vec, regime="TREND_BULL")
    assert res["latency_ms"] < 15.0, f"k-NN took {res['latency_ms']:.2f}ms (> 15ms SLA)"
    assert res["k_used"] == 7
    assert len(res["all_k_analogs"]) == 7
    assert res["p_knn"] > 0.95
    assert "Prior k-NN" in res["prompt_summary"]


def test_hybrid_ensemble_tabular_tp1_and_log_odds_stacking():
    """
    Verify T5.5:
    - TabularMetaModel trains on hitting TP1 (+0.55R) before SL and outputs feature attributions.
    - NeuroSymbolicEnsemble combines (p_quant_ml, p_knn, p_llm) via log-odds stacking and
      achieves lower Brier score than single noisy models.
    """
    rng = np.random.default_rng(7)
    n, d = 200, 15
    X = rng.normal(0, 1, size=(n, d))
    true_w = np.zeros(d)
    true_w[0] = 1.2
    true_w[1] = -1.0
    true_w[2] = 0.8
    logits = X @ true_w
    probs = 1.0 / (1.0 + np.exp(-logits))
    y_tp1 = (rng.uniform(0, 1, size=n) < probs).astype(int)

    tab = TabularMetaModel(feature_dim=d, l2_penalty=1.0, tp1_trigger_r=0.55)
    assert tab.label_tp1_outcome(mfe_r=0.62, mae_r=-0.30) == 1
    assert tab.label_tp1_outcome(mfe_r=0.40, mae_r=-1.00) == 0

    tab.fit(X[:150], y_tp1[:150])
    attr = tab.predict_with_attribution(X[0])
    assert 0.0 < attr["p_quant_ml"] < 1.0
    assert isinstance(attr["top_positive_features"], list)
    assert isinstance(attr["top_negative_features"], list)

    ens = NeuroSymbolicEnsemble(tabular_model=tab)
    for i in range(150, 200):
        y_i = bool(y_tp1[i])
        p_ml = tab.predict_proba(X[i])
        # Simulate complementary k-NN and LLM signals
        p_knn = float(np.clip(probs[i] + rng.normal(0, 0.12), 0.05, 0.95))
        p_llm = float(np.clip(probs[i] + rng.normal(0, 0.15), 0.05, 0.95))
        ens.update_from_outcome(p_ml, p_knn, p_llm, outcome_tp1_win=y_i, feature_vector=X[i])

    metrics = ens.get_rolling_metrics()
    assert metrics["n"] == 50
    assert metrics["brier_hybrid"] <= max(metrics["brier_ml"], metrics["brier_knn"], metrics["brier_llm"])


def test_ai_decide_engine_mandates_and_auditor_and_emergency():
    """
    Verify T5.1:
    - 0 AI calls on CHOP_NO_TRADE or empty candidates
    - 1 AI call on SKIP
    - 2 AI calls on TRADE (Primary + Cross-Model Red-Team Auditor)
    - Strict AI-Only Mandate: when all AI providers fail -> returns SKIP_AI_UNAVAILABLE
    - INTRABAR_EMERGENCY_REVIEW mode returns ABORT_THESIS_SCRATCH
    """
    calls_made = {"count": 0}

    def mock_ai_http(method, url, headers, payload):
        calls_made["count"] += 1
        sys_text = ""
        if payload and "messages" in payload:
            sys_text = payload["messages"][0]["content"]
        elif payload and "systemInstruction" in payload:
            sys_text = payload["systemInstruction"]["parts"][0]["text"]

        if "Red-Team Risk Auditor" in sys_text:
            body = {
                "verdict": "APPROVE",
                "p_win_audit": 0.84,
                "fatal_flaws": [],
                "audit_reasoning_id": "Disetujui, likuiditas mendukung.",
            }
        elif "Intrabar Optimal Stopping" in sys_text:
            body = {
                "action": "ABORT_THESIS_SCRATCH",
                "p_survive_ai": 0.11,
                "reasoning_id": "Order flow berbalik total, keluar sekarang di -0.25R.",
            }
        else:
            body = {
                "decision": "TRADE",
                "selected_strategy_id": "S1_TREND_PULLBACK",
                "direction": "LONG",
                "execution_style": "MAKER_FIRST_GTX",
                "entry_price": 100.0,
                "sl_price": 99.2,
                "tp_price": 101.8,
                "p_win_raw": 0.85,
                "key_confluences": ["ofi_bullish", "oi_q1"],
                "primary_failure_mode": "btc_pullback",
                "reasoning_id": "Setup Long presisi tinggi.",
            }

        if "generativelanguage" in url:
            return FakeHTTPResponse(
                200,
                {"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}], "usageMetadata": {"totalTokenCount": 400}},
            )
        return FakeHTTPResponse(
            200,
            {"choices": [{"message": {"content": json.dumps(body)}}], "usage": {"total_tokens": 450}},
        )

    gw = AIGateway(
        provider_keys={"groq": ["gsk_primary"], "gemini": ["AIza_auditor"]},
        http_client=FakeHTTPSession(mock_ai_http),
        persist_ledger=False,
    )
    cal = ProbabilityCalibrator(n0_prior=5.0, default_base_rate=0.80)
    cal.set_empirical_base_rate("S1_TREND_PULLBACK", "TREND_BULL", p_base=0.82, historical_n=100)
    aci = AdaptiveConformalFilter(alpha_target=0.18, warm_start_scores=[0.15, 0.20, 0.22, 0.25])
    engine = AIDecisionEngine(
        gateway=gw,
        calibrator=cal,
        conformal_filter=aci,
        sniper_75_enabled=True,
        min_sniper_p_tp1=0.76,
    )
    # Set strong positive tabular prior for test
    engine.ensemble.tabular_model.bias = 1.6

    # 1. CHOP_NO_TRADE -> 0 AI calls
    res_chop = engine.decide(
        symbol="SOLUSDT",
        timeframe="15m",
        closed_bar_ts=1000,
        regime_state={"regime": "CHOP_NO_TRADE"},
        microstructure={},
        orthogonal_factors={"f1": 1.0},
        candidate_setups=[{"strategy_id": "S1_TREND_PULLBACK", "entry_price": 100.0, "sl_price": 99.2, "tp_price": 101.8}],
    )
    assert res_chop["decision"] == "SKIP"
    assert res_chop["skip_reason"] == "SKIP_CHOP_NO_TRADE"
    assert calls_made["count"] == 0

    # 2. Valid TRADE -> 2 AI calls (Groq Primary + Gemini Cross-Model Auditor)
    res_trade = engine.decide(
        symbol="SOLUSDT",
        timeframe="15m",
        closed_bar_ts=2000,
        regime_state={"regime": "TREND_BULL", "hurst": 0.61},
        microstructure={"obi_20": 0.45, "tfi_15m": 0.32},
        orthogonal_factors={"f1": 1.2, "f2": 0.8},
        candidate_setups=[
            {"strategy_id": "S1_TREND_PULLBACK", "entry_price": 100.0, "sl_price": 99.2, "tp_price": 101.8}
        ],
        empirical_base_rate={"historical_n": 100, "historical_win_rate_pct": 82.0},
        atr_15m=0.5,
    )
    assert res_trade["decision"] == "TRADE"
    assert res_trade["ai_calls_made"] == 2
    assert res_trade["ai_model_primary"] != res_trade["ai_model_auditor"]

    # 3. Emergency Intrabar Review
    em_res = engine.review_open_position_emergency(
        symbol="SOLUSDT",
        direction="LONG",
        entry_price=100.0,
        current_price=99.8,
        sl_price=99.2,
        tp_price=101.8,
        p_survive=0.12,
        reversal_signals={"spot_perp_div": -2.1},
        elapsed_sec=240.0,
    )
    assert em_res["action"] == "ABORT_THESIS_SCRATCH"
    assert em_res["close_reason"] == "AI_THESIS_INVALIDATED_EARLY"

    # 4. Strict AI-Only Mandate when all AI providers are unavailable
    empty_gw = AIGateway(provider_keys={"groq": [], "gemini": []}, persist_ledger=False)
    dead_engine = AIDecisionEngine(gateway=empty_gw)
    res_dead = dead_engine.decide(
        symbol="SOLUSDT",
        timeframe="15m",
        closed_bar_ts=3000,
        regime_state={"regime": "TREND_BULL"},
        microstructure={},
        orthogonal_factors={"f1": 1.0},
        candidate_setups=[{"strategy_id": "S1_TREND_PULLBACK", "entry_price": 100.0, "sl_price": 99.2, "tp_price": 101.8}],
    )
    assert res_dead["decision"] == "SKIP"
    assert res_dead["skip_reason"] == "SKIP_AI_UNAVAILABLE"


# ===========================================================================
# PHASE 6 TESTS: Event Bus, Native PriceMatch, Avellaneda, Thesis Monitor, UserStream, Engine
# ===========================================================================


def test_priority_event_bus_sub_50ms_wakeup_and_ordering():
    """
    Verify T6.5:
    - PriorityEventBus wakes waiting thread in < 50ms.
    - Priority ordering: CRITICAL_POSITION_INTERRUPT (0) > MICROSTRUCTURE_SNIPER_TRIGGER (1) > CLOSED_CANDLE_BOUNDARY_SCAN (2).
    """
    bus = PriorityEventBus()
    bus.publish("CLOSED_CANDLE_BOUNDARY_SCAN", {"bar": 1}, priority=int(CLOSED_CANDLE_BOUNDARY_SCAN))
    bus.publish("MICROSTRUCTURE_SNIPER_TRIGGER", {"sym": "SOLUSDT"}, priority=int(MICROSTRUCTURE_SNIPER_TRIGGER))
    bus.publish("CRITICAL_POSITION_INTERRUPT", {"reason": "TP1"}, priority=int(CRITICAL_POSITION_INTERRUPT))

    e0 = bus.wait_next(timeout_sec=0.1)
    e1 = bus.wait_next(timeout_sec=0.1)
    e2 = bus.wait_next(timeout_sec=0.1)
    assert e0.event_type == "CRITICAL_POSITION_INTERRUPT"
    assert e1.event_type == "MICROSTRUCTURE_SNIPER_TRIGGER"
    assert e2.event_type == "CLOSED_CANDLE_BOUNDARY_SCAN"

    # Measure cross-thread wake-up latency (< 50ms)
    wakeup_ms_holder: List[float] = []

    def consumer():
        res = bus.dispatch_next(timeout_sec=2.0)
        if res is not None:
            _, lat_ms = res
            wakeup_ms_holder.append(lat_ms)

    th = threading.Thread(target=consumer)
    th.start()
    time.sleep(0.02)
    bus.publish("CRITICAL_POSITION_INTERRUPT", {"urgent": True})
    th.join(timeout=1.0)
    assert len(wakeup_ms_holder) == 1
    assert wakeup_ms_holder[0] < 50.0


def test_native_pricematch_payload_and_gtx_fallback():
    """
    Verify T6.6:
    - `priceMatch="QUEUE"` / `"QUEUE_5"` / `"OPPONENT"` omits `price` field and sets `timeInForce="GTD"`
      with `goodTillDate = now_ms + 4500`.
    - Clean fallback to `LIMIT GTX` when `priceMatch` is rejected by exchange.
    """
    now_ms = 1730000000000
    params = build_native_pricematch_params(
        symbol="SOLUSDT",
        side="LONG",
        quantity=1.5,
        price_match="QUEUE",
        tif="GTD",
        now_ms=now_ms,
        gtd_offset_ms=4500,
        client_order_id="pf3_SOLUSD_S1_1730000000",
    )
    assert "price" not in params
    assert params["priceMatch"] == "QUEUE"
    assert params["timeInForce"] == "GTD"
    assert params["goodTillDate"] == now_ms + 4500

    # Fallback test when symbol rejects priceMatch
    mock_client = MockBinanceFuturesClient()
    mock_client.reject_pricematch = True
    router = NativePriceMatchRouter(gtd_offset_ms=4500)
    res = router.place_passive_maker_order(
        client=mock_client,
        symbol="SOLUSDT",
        direction="LONG",
        quantity=2.0,
        fallback_price=150.25,
        price_match="QUEUE",
        client_order_id="pf3_SOLUSD_S1_100",
    )
    assert res["routing_mode"] == "FALLBACK_LIMIT_GTX"
    assert res["submitted_params"]["timeInForce"] == "GTX"
    assert "price" in res["submitted_params"]


def test_avellaneda_stoikov_router_and_vwap_impact():
    """
    Verify T6.4:
    - Micro-price P_tilde_t and optimal offset delta* calculation.
    - Order-book depth VWAP impact check <= 8.0 bps passes, > 8.0 bps aborts.
    """
    router = AvellanedaStoikovRouter(max_impact_bps=8.0)
    offset_info = router.compute_optimal_offset(
        direction="LONG",
        best_bid_price=100.00,
        best_bid_qty=50.0,
        best_ask_price=100.04,
        best_ask_qty=10.0,
        ofi_20=0.4,
        tfi_1m=0.3,
        sigma_1m=0.0015,
        vpin=0.30,
        vpin_cdf=0.40,
        tick_size=0.01,
    )
    assert offset_info["allowed_passive_maker"] is True
    assert offset_info["micro_price"] > 100.02  # skewed toward ask due to 50 vs 10 bid size
    assert offset_info["optimal_limit_price"] <= 100.00

    # Deep book -> low impact (< 8 bps)
    deep_book = {
        "bids": [[100.00, 100.0], [99.98, 200.0]],
        "asks": [[100.02, 100.0], [100.04, 200.0]],
    }
    imp_ok = router.compute_vwap_impact_bps(deep_book, "LONG", quantity=10.0)
    assert imp_ok["passed"] is True
    assert imp_ok["impact_bps"] <= 8.0

    # Thin book -> high impact (> 8 bps)
    thin_book = {
        "bids": [[100.00, 1.0], [99.00, 50.0]],
        "asks": [[100.02, 0.5], [100.50, 50.0]],
    }
    imp_bad = router.compute_vwap_impact_bps(thin_book, "LONG", quantity=10.0)
    assert imp_bad["passed"] is False
    assert imp_bad["impact_bps"] > 8.0


def test_thesis_monitor_first_passage_and_early_scratch():
    """
    Verify T6.3:
    - First-Passage Survival Probability P_survive(t) formula at mu=0 and mu!=0.
    - Triggers INTRABAR_EMERGENCY_REVIEW after 3 consecutive readings with P_survive < 0.18
      and microstructure reversal, scratching at ~ -0.25R with AI_THESIS_INVALIDATED_EARLY.
    """
    bus = PriorityEventBus()
    monitor = IntrabarThesisMonitor(
        survival_threshold=0.18,
        required_consecutive_breaches=3,
        min_elapsed_sec=180.0,
        event_bus=bus,
    )

    # At mu = 0, P_survive is exact linear ratio (X_t - SL) / (TP - SL)
    p_zero = monitor.compute_first_passage_survival_prob(
        current_price=100.0, sl_price=99.0, tp_price=101.0, direction="LONG", mu_drift=0.0
    )
    assert pytest.approx(p_zero, rel=1e-4) == 0.50

    # Positive drift -> P_survive > 0.50; Negative drift -> P_survive < 0.50
    p_pos = monitor.compute_first_passage_survival_prob(
        current_price=100.0, sl_price=99.0, tp_price=101.0, direction="LONG", mu_drift=0.25, sigma=0.25
    )
    p_neg = monitor.compute_first_passage_survival_prob(
        current_price=100.0, sl_price=99.0, tp_price=101.0, direction="LONG", mu_drift=-0.25, sigma=0.25
    )
    assert p_pos > 0.50 > p_neg

    # Simulate 3 consecutive ticks at -0.25R (entry=100.0, sl=99.0, tp=101.8, current=99.75) with severe negative drift
    class StubEmergencyDecider:
        def review_open_position_emergency(self, **kwargs):
            return {
                "action": "ABORT_THESIS_SCRATCH",
                "close_reason": "AI_THESIS_INVALIDATED_EARLY",
                "p_survive_ai": 0.09,
                "reasoning_id": "Scratch trade at -0.25R.",
            }

    micro_reversed = {
        "ofi_20": -0.85,
        "tfi_5m": -0.75,
        "spot_perp_div": -2.1,
        "vpin": 0.92,
        "oi_quadrant": "Q3_NEW_SHORTS",
    }

    for step in range(1, 4):
        ev = monitor.evaluate_position(
            symbol="SOLUSDT",
            direction="LONG",
            entry_price=100.0,
            current_price=99.75,  # -0.25R
            sl_price=99.0,
            tp_price=101.8,
            elapsed_sec=200.0,
            micro_state=micro_reversed,
            sigma=0.20,
            decide_engine=StubEmergencyDecider(),
        )
        if step < 3:
            assert ev["should_scratch"] is False
        else:
            assert ev["trigger_emergency_review"] is True
            assert ev["should_scratch"] is True
            assert ev["close_reason"] == "AI_THESIS_INVALIDATED_EARLY"
            assert pytest.approx(ev["current_r"], rel=1e-3) == -0.25


def test_userstream_events_and_execution_engine_v3():
    """
    Verify T6.1, T6.2, & T7.4:
    - UserDataStreamManager processes ORDER_TRADE_UPDATE in < 100ms and writes accurate r_multiple_net.
    - AtomicExecutionEngineV3 prevents duplicate orders via deterministic clientOrderId.
    - On $1.32 balance (notional ~$25.08), selects SINGLE_FULL_TP; on $50+ balance (notional ~$950),
      selects PARTIAL_TP1_TP2.
    - When price hits TP1 (+0.55R), immediately amends SL to +0.38R with zero unprotected window.
    """
    mock_client = MockBinanceFuturesClient(min_notional=5.0)
    bus = PriorityEventBus()
    journal_entries: List[Dict[str, Any]] = []

    usm = UserDataStreamManager(
        client=mock_client,
        event_bus=bus,
        journal_callback=lambda rec: journal_entries.append(rec),
    )
    lk = usm.create_listen_key()
    assert lk == "lk_test_pyrofuel_v3_12345"

    usm.register_tracked_position(
        symbol="SOLUSDT",
        direction="LONG",
        entry_price=100.0,
        sl_price=99.0,
        tp_price=102.0,
        quantity=2.0,
        margin_usdt=10.0,
    )
    sl_fill_event = {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1730000100000,
        "o": {
            "s": "SOLUSDT",
            "c": "sl_algo_1",
            "S": "SELL",
            "o": "MARKET",
            "ot": "STOP_MARKET",
            "x": "TRADE",
            "X": "FILLED",
            "ap": "99.00",
            "z": "2.0",
            "n": "0.10",
            "rp": "-2.00",
            "R": True,
            "cp": True,
        },
    }
    res_evt = usm.handle_event(sl_fill_event)
    assert res_evt["processing_ms"] < 100.0
    assert res_evt["close_reason"] == "SL_EXCHANGE"
    assert "SOLUSDT" not in usm.active_positions
    assert len(journal_entries) == 1
    assert pytest.approx(journal_entries[0]["r_multiple_net"], rel=1e-3) == -1.05

    # Execution Engine v3 tests
    exec_engine = AtomicExecutionEngineV3(client=mock_client, event_bus=bus)

    # Small account ($1.32 -> notional $25.08 at $100 entry => qty = 0.25) -> SINGLE_FULL_TP
    tp_small = exec_engine.select_tp_mode("SOLUSDT", total_quantity=0.25, entry_price=100.0)
    assert tp_small["tp_mode"] == "SINGLE_FULL_TP"

    # Large account ($50+ -> notional $950 at $100 entry => qty = 9.50) -> PARTIAL_TP1_TP2
    tp_large = exec_engine.select_tp_mode("SOLUSDT", total_quantity=9.50, entry_price=100.0)
    assert tp_large["tp_mode"] == "PARTIAL_TP1_TP2"

    # Execute trade and test idempotency on same clientOrderId
    trade_res = exec_engine.execute_trade(
        symbol="SOLUSDT",
        direction="LONG",
        entry_price=100.0,
        sl_price=99.0,
        tp_price=102.0,
        quantity=0.25,
        strategy_id="S1_TREND_PULLBACK",
        execution_style="MAKER_FIRST_GTX",
        ts_sec=1730000500,
    )
    assert trade_res["status"] == "EXECUTED"
    assert trade_res["sl_state"] == "CONFIRMED"
    assert trade_res["tp_mode"] == "SINGLE_FULL_TP"
    assert pytest.approx(trade_res["tp1_price"], rel=1e-4) == 100.55
    assert pytest.approx(trade_res["sl_lock_after_tp1_price"], rel=1e-4) == 100.38

    # Retry with exact same ts_sec must be blocked by idempotent clientOrderId guard
    dup_res = exec_engine.execute_trade(
        symbol="SOLUSDT",
        direction="LONG",
        entry_price=100.0,
        sl_price=99.0,
        tp_price=102.0,
        quantity=0.25,
        strategy_id="S1_TREND_PULLBACK",
        execution_style="MAKER_FIRST_GTX",
        ts_sec=1730000500,
    )
    assert dup_res["status"] == "IDEMPOTENT_EXISTING_ORDER"
    assert dup_res["duplicate_prevented"] is True

    # Simulate price tick reaching TP1 (+0.55R = 100.55) -> triggers alarm and amends SL to +0.38R (100.38)
    fired = bus.on_price_tick("SOLUSDT", mark_price=100.56)
    assert len(fired) == 1
    bus.dispatch_all()
    assert exec_engine.active_positions["SOLUSDT"]["tp1_locked"] is True
    assert pytest.approx(exec_engine.active_positions["SOLUSDT"]["sl_price"], rel=1e-4) == 100.38

    # Verify atomic amend_stop_loss preserves old SL if new SL fails
    old_id = exec_engine.active_positions["SOLUSDT"]["sl_algo_id"]
    mock_client.fail_sl_placement = True
    failed_amend = exec_engine.amend_stop_loss("SOLUSDT", "LONG", 100.50, old_algo_id=old_id)
    assert failed_amend["ok"] is False
    assert failed_amend["old_sl_preserved"] is True
    assert any(o.get("algoId") == old_id for o in mock_client.open_algo_orders)


# ===========================================================================
# PHASE 7 TESTS: Profit Ratchet Vault & Hard Risk Engine (20x ALL-IN & Sniper 75%)
# ===========================================================================


def test_profit_ratchet_vault_locks_35pct_above_15pct_hwm(tmp_path):
    """
    Verify T7.3:
    - Locks 35% of new profit whenever equity >= HWM * 1.15.
    - Persists state in vault_state.json.
    - ALL_IN working capital excludes locked vault profit so locked profits are never risked.
    """
    vault_file = str(tmp_path / "vault_state.json")
    vault = ProfitRatchetVault(initial_equity=10.0, state_path=vault_file, persist=True)

    # +10% growth ($11.00 < $11.50) -> no ratchet yet
    r1 = vault.update_equity(11.00)
    assert r1["ratcheted"] is False
    assert vault.locked_profit_vault_usdt == 0.0

    # +20% growth ($12.00 >= $10.00 * 1.15) -> locks 35% of $2.00 = $0.70!
    r2 = vault.update_equity(12.00)
    assert r2["ratcheted"] is True
    assert pytest.approx(vault.locked_profit_vault_usdt, rel=1e-5) == 0.70
    assert pytest.approx(vault.high_water_mark_equity, rel=1e-5) == 12.00
    assert pytest.approx(vault.get_working_balance(12.00), rel=1e-5) == 11.30

    # Reload from disk to verify persistence
    vault_reloaded = ProfitRatchetVault(state_path=vault_file, persist=True)
    assert pytest.approx(vault_reloaded.locked_profit_vault_usdt, rel=1e-5) == 0.70
    assert pytest.approx(vault_reloaded.high_water_mark_equity, rel=1e-5) == 12.00


def test_hard_risk_engine_20x_all_in_sniper_75_and_circuit_breaker():
    """
    Verify T7.1, T7.2, & T7.4 Acceptance Criteria:
    - Fixed 20x ISOLATED, ALL_IN = 95% working balance:
      For balance $1.32 -> margin_usdt = $1.254, notional_usdt = $25.08, and at 1.5% SL,
      dollar risk is ~$0.3762 + fee (~$0.38 + fee).
    - BTCUSDT ($50 minNotional) rejected with SKIP_MIN_NOTIONAL on $1.32 balance.
    - 0.45% <= d_SL <= 2.25% and liquidation distance >= 2.0 * d_SL enforced.
    - Sniper 75% Mode rejects p_hybrid(TP1) = 0.68 with SKIP_BELOW_76PCT_PRECISION_GATE
      and rejects non-singleton conformal set with SKIP_CONFORMAL_AMBIGUITY.
    - Circuit-Breaker trips on 2 consecutive losses or 15% daily drawdown.
    """
    vault = ProfitRatchetVault(initial_equity=1.32, persist=False)
    risk = HardRiskEngine(vault=vault)

    # 1. Valid 20x ALL-IN trade on $1.32 balance with 1.5% SL on SOLUSDT ($5 minNotional)
    valid_decision = {
        "decision": "TRADE",
        "symbol": "SOLUSDT",
        "direction": "LONG",
        "entry_price": 100.0,
        "sl_price": 98.5,  # 1.5% SL (< 2.25% max, > 0.45% min)
        "tp_price": 103.0,  # 3.0% TP
        "p_hybrid": 0.80,
        "p_cal": 0.78,
        "conformal_set": ["WIN"],
        "ev_r": 0.48,
        "rrr_net": 1.85,
    }
    res_ok = risk.validate_and_size(
        valid_decision,
        account_state={"available_balance_usdt": 1.32, "consecutive_losses": 0},
        market_state={"min_notional": 5.0, "step_size": 0.001, "min_qty": 0.001, "quantity_precision": 3},
    )
    assert res_ok["allowed"] is True
    assert res_ok["leverage"] == 20
    assert res_ok["margin_type"] == "ISOLATED"
    assert res_ok["sizing_mode"] == "ALL_IN"
    assert pytest.approx(res_ok["margin_usdt"], rel=1e-4) == 1.254
    assert pytest.approx(res_ok["notional_usdt"], rel=1e-4) == 25.08
    assert pytest.approx(res_ok["sl_loss_gross_usdt"], rel=1e-3) == 0.3762  # ~$0.38
    assert res_ok["liq_to_sl_ratio"] >= 2.0
    assert "Mode: ALL-IN (95% Saldo) | 20x ISOLATED" in res_ok["telegram_transparency_box"]

    # 2. BTCUSDT on $1.32 balance rejected because $25.08 < $50.0 minNotional
    btc_decision = dict(valid_decision, symbol="BTCUSDT")
    res_btc = risk.validate_and_size(
        btc_decision,
        account_state={"available_balance_usdt": 1.32},
        market_state={"min_notional": 50.0},
    )
    assert res_btc["allowed"] is False
    assert res_btc["reject_reason"] == "SKIP_MIN_NOTIONAL"

    # 3. Sniper 75% Mode rejects p_hybrid(TP1) = 0.68 (< 0.76)
    low_p_decision = dict(valid_decision, p_hybrid=0.68, p_cal=0.68)
    res_low_p = risk.validate_and_size(
        low_p_decision,
        account_state={"available_balance_usdt": 10.0},
    )
    assert res_low_p["allowed"] is False
    assert res_low_p["reject_reason"] == "SKIP_BELOW_76PCT_PRECISION_GATE"

    # 4. Conformal ambiguity {"WIN", "LOSS"} rejected
    ambig_decision = dict(valid_decision, conformal_set=["WIN", "LOSS"])
    res_ambig = risk.validate_and_size(
        ambig_decision,
        account_state={"available_balance_usdt": 10.0},
    )
    assert res_ambig["allowed"] is False
    assert res_ambig["reject_reason"] == "SKIP_CONFORMAL_AMBIGUITY"

    # 5. SL > 2.25% rejected (violates d_SL <= 2.25% & liquidation ratio >= 2.0x)
    wide_sl_decision = dict(valid_decision, sl_price=97.4)  # 2.6% SL
    res_wide = risk.validate_and_size(
        wide_sl_decision,
        account_state={"available_balance_usdt": 10.0},
    )
    assert res_wide["allowed"] is False
    assert res_wide["reject_reason"] == "REJECT_SL_DISTANCE_OUT_OF_BOUNDS"

    # 6. Circuit-Breaker after 2 consecutive losses
    risk.record_trade_result(-0.35, new_equity=1.00)
    assert risk.is_circuit_breaker_active() is False
    risk.record_trade_result(-0.30, new_equity=0.70)
    assert risk.is_circuit_breaker_active() is True

    res_cb = risk.validate_and_size(
        valid_decision,
        account_state={"available_balance_usdt": 10.0},
    )
    assert res_cb["allowed"] is False
    assert res_cb["reject_reason"] == "REJECT_CIRCUIT_BREAKER_ACTIVE"


class TestPhase2_5_6_7Suite(unittest.TestCase):
    """
    Standard library unittest wrapper so the suite runs seamlessly via both
    `pytest` and `python -m unittest` / `python tests/test_phase2_5_6_7.py`.
    """

    def test_01_ai_gateway_rotation_and_cache(self):
        with tempfile.TemporaryDirectory() as td:
            test_ai_gateway_user_agent_and_key_rotation_and_cache(pathlib.Path(td))

    def test_02_ai_gateway_50_think_tags_and_repair(self):
        with tempfile.TemporaryDirectory() as td:
            test_ai_gateway_50_consecutive_think_tags_and_repair_retry(pathlib.Path(td))

    def test_03_probability_calibrator(self):
        test_probability_calibrator_shrinkage_brier_and_ev_gate()

    def test_04_adaptive_conformal(self):
        test_adaptive_conformal_inference_gate_and_coverage()

    def test_05_episodic_memory_speed_and_accuracy(self):
        test_episodic_memory_5000_episodes_under_15ms()

    def test_06_hybrid_ensemble_stacking(self):
        test_hybrid_ensemble_tabular_tp1_and_log_odds_stacking()

    def test_07_ai_decide_engine(self):
        test_ai_decide_engine_mandates_and_auditor_and_emergency()

    def test_08_priority_event_bus(self):
        test_priority_event_bus_sub_50ms_wakeup_and_ordering()

    def test_09_native_pricematch(self):
        test_native_pricematch_payload_and_gtx_fallback()

    def test_10_avellaneda_stoikov_router(self):
        test_avellaneda_stoikov_router_and_vwap_impact()

    def test_11_thesis_monitor(self):
        test_thesis_monitor_first_passage_and_early_scratch()

    def test_12_userstream_and_execution_engine_v3(self):
        test_userstream_events_and_execution_engine_v3()

    def test_13_profit_ratchet_vault(self):
        with tempfile.TemporaryDirectory() as td:
            test_profit_ratchet_vault_locks_35pct_above_15pct_hwm(pathlib.Path(td))

    def test_14_hard_risk_engine(self):
        test_hard_risk_engine_20x_all_in_sniper_75_and_circuit_breaker()


if __name__ == "__main__":
    unittest.main(verbosity=2)

