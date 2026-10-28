"""
===========================================================================
PYROFUEL CALIBRATED AI META-LABELING DECISION ENGINE v3.0 (T5.1)
===========================================================================
Implements the 2-Stage AI Meta-Labeling + Neuro-Symbolic Stack:
- Strictly enforces the User's AI-Only Mandate:
  * If all AI providers fail or exhaust quota -> returns decision="SKIP",
    skip_reason="SKIP_AI_UNAVAILABLE" (zero rule-based fallback trading).
- Quota Conservation:
  * 0 AI calls when regime == "CHOP_NO_TRADE" or candidate_setups is empty.
  * Exactly 1 AI call when Stage-1 decides "SKIP".
  * At most 2 AI calls when Stage-1 decides "TRADE" (Stage-1 Primary +
    Stage-2 Independent Cross-Model Red-Team Auditor).
- Structural Corridor Guardrail:
  * AI may only adjust SL/TP within +/- 0.30 * ATR_15m of the primary setup
    candidate, and must satisfy d_SL in [0.45%, 2.50%] & RRR_net >= 1.60.
- Neuro-Symbolic Hybrid Stacking + Calibration + Adaptive Conformal Gate:
  * Combines TabularMetaModel (p_quant_ml), EpisodicMarketMemory (p_knn),
    and LLM (p_llm) in log-odds space -> p_hybrid -> p_cal -> Conformal Set.
- Intrabar Emergency Review Mode (`INTRABAR_EMERGENCY_REVIEW`):
  * Evaluates early thesis invalidation triggered by `exec/thesis_monitor.py`
    to scratch failing positions around -0.25R instead of -1.0R.
===========================================================================
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from ai.conformal import AdaptiveConformalFilter
from ai.episodic_memory import EpisodicMarketMemory
from ai.hybrid_ensemble import NeuroSymbolicEnsemble, TabularMetaModel
from ai_gateway import AIGateway
from calibration import ProbabilityCalibrator


PRIMARY_SYSTEM_PROMPT = (
    "You are Pyrofuel v3 Institutional Quant Meta-Labeling Strategist. "
    "Evaluate the statistical regime, order-flow microstructure, empirical base-rates, "
    "tabular ML prior, k-NN episodic analogs, and primary Triple-Barrier candidate setups. "
    "Respond strictly in valid JSON format matching the required PRIMARY decision schema."
)

AUDITOR_SYSTEM_PROMPT = (
    "You are Pyrofuel v3 Adversarial Red-Team Risk Auditor (20x ISOLATED ALL-IN protection). "
    "Search for fatal flaws in the proposed TRADE plan (e.g., opposing OI quadrant, "
    "opposing BTC anchor regime, Spot-Perp CVD divergence, VPIN toxicity, or tight liquidation). "
    "Respond strictly in valid JSON format with keys: verdict ('APPROVE' or 'VETO'), "
    "p_win_audit (0.0 to 1.0), fatal_flaws (array of strings), and audit_reasoning_id."
)

EMERGENCY_SYSTEM_PROMPT = (
    "You are Pyrofuel v3 Intrabar Optimal Stopping & Thesis Invalidation Auditor. "
    "An open 20x ISOLATED position is experiencing severe order-flow reversal and low "
    "First-Passage Survival Probability P_survive(t). Decide whether to scratch/abort the trade early "
    "('ABORT_THESIS_SCRATCH') or hold ('HOLD_POSITION'). "
    "Respond strictly in valid JSON format with keys: action, p_survive_ai, reasoning_id."
)


class AIDecisionEngine:
    """
    2-Stage Structured AI Meta-Labeling Engine + Cross-Model Auditor + Intrabar Emergency Review (T5.1).
    """

    def __init__(
        self,
        gateway: Optional[AIGateway] = None,
        calibrator: Optional[ProbabilityCalibrator] = None,
        conformal_filter: Optional[AdaptiveConformalFilter] = None,
        episodic_memory: Optional[EpisodicMarketMemory] = None,
        hybrid_ensemble: Optional[NeuroSymbolicEnsemble] = None,
        min_sl_pct: float = 0.45,
        max_sl_pct: float = 2.50,
        min_rrr_net: float = 1.60,
        atr_corridor_mult: float = 0.30,
        sniper_75_enabled: bool = False,
        min_sniper_p_tp1: float = 0.76,
    ):
        self.gateway = gateway or AIGateway(persist_ledger=False)
        self.calibrator = calibrator or ProbabilityCalibrator()
        self.conformal = conformal_filter or AdaptiveConformalFilter(alpha_target=0.18)
        self.episodic_memory = episodic_memory or EpisodicMarketMemory()
        self.ensemble = hybrid_ensemble or NeuroSymbolicEnsemble()

        self.min_sl_pct = float(min_sl_pct)
        self.max_sl_pct = float(max_sl_pct)
        self.min_rrr_net = float(min_rrr_net)
        self.atr_corridor_mult = float(atr_corridor_mult)
        self.sniper_75_enabled = bool(sniper_75_enabled)
        self.min_sniper_p_tp1 = float(min_sniper_p_tp1)

    def _validate_structural_corridor(
        self,
        ai_data: Dict[str, Any],
        candidate_setups: List[Dict[str, Any]],
        atr_15m: float = 0.0,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Verify AI's entry/SL/TP lies within +/- 0.30 * ATR_15m of the selected candidate
        and satisfies d_SL in [min_sl_pct, max_sl_pct] and RRR_net >= min_rrr_net.
        """
        sel_id = str(ai_data.get("selected_strategy_id", "")).strip()
        matched_cand = next(
            (c for c in candidate_setups if str(c.get("strategy_id", "")).strip() == sel_id),
            candidate_setups[0] if candidate_setups else None,
        )
        if not matched_cand:
            return False, "REJECT_OUT_OF_CORRIDOR: No matching candidate setup", {}

        entry = float(ai_data["entry_price"])
        sl = float(ai_data["sl_price"])
        tp = float(ai_data["tp_price"])
        if entry <= 0:
            return False, "REJECT_OUT_OF_CORRIDOR: Non-positive entry_price", {}

        # Check ATR corridor around candidate's structural SL and TP if atr_15m > 0
        cand_sl = float(matched_cand.get("sl_price", sl))
        cand_tp = float(
            matched_cand.get("tp_price")
            or matched_cand.get("tp2_price")
            or matched_cand.get("tp1_price")
            or tp
        )
        if atr_15m > 0:
            max_dev = self.atr_corridor_mult * float(atr_15m) + 1e-8
            if abs(sl - cand_sl) > max_dev:
                return (
                    False,
                    f"REJECT_OUT_OF_CORRIDOR: SL deviation {abs(sl - cand_sl):.6f} > {max_dev:.6f} (0.3*ATR)",
                    {},
                )
            if abs(tp - cand_tp) > max_dev:
                return (
                    False,
                    f"REJECT_OUT_OF_CORRIDOR: TP deviation {abs(tp - cand_tp):.6f} > {max_dev:.6f} (0.3*ATR)",
                    {},
                )

        d_sl_pct = abs(entry - sl) / entry * 100.0
        d_tp_pct = abs(tp - entry) / entry * 100.0

        if d_sl_pct < self.min_sl_pct - 1e-6 or d_sl_pct > self.max_sl_pct + 1e-6:
            return (
                False,
                f"REJECT_OUT_OF_CORRIDOR: d_SL={d_sl_pct:.3f}% outside [{self.min_sl_pct:.2f}%, {self.max_sl_pct:.2f}%]",
                {},
            )

        ev_info = self.calibrator.compute_ev_and_rrr_net(
            p_cal=float(ai_data["p_win_raw"]),
            d_sl=d_sl_pct / 100.0,
            d_tp=d_tp_pct / 100.0,
        )
        if ev_info["rrr_net"] < self.min_rrr_net - 1e-6:
            return (
                False,
                f"REJECT_OUT_OF_CORRIDOR: rrr_net={ev_info['rrr_net']:.2f} < {self.min_rrr_net:.2f}",
                ev_info,
            )

        return True, "OK", ev_info

    def decide(
        self,
        symbol: str,
        timeframe: str,
        closed_bar_ts: int,
        regime_state: Dict[str, Any],
        microstructure: Dict[str, Any],
        orthogonal_factors: Dict[str, float],
        candidate_setups: List[Dict[str, Any]],
        empirical_base_rate: Optional[Dict[str, Any]] = None,
        account_state: Optional[Dict[str, Any]] = None,
        atr_15m: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Execute the full 2-Stage AI Meta-Labeling + Hybrid Ensemble + Calibration + Conformal pipeline.
        """
        regime = str(regime_state.get("regime", "UNKNOWN")).upper().strip()

        # 0. Quota-saving pre-checks (0 AI calls)
        if regime == "CHOP_NO_TRADE":
            return {
                "decision": "SKIP",
                "skip_reason": "SKIP_CHOP_NO_TRADE",
                "symbol": symbol,
                "regime": regime,
                "ai_calls_made": 0,
                "tokens_used": 0,
            }

        if not candidate_setups:
            return {
                "decision": "SKIP",
                "skip_reason": "SKIP_NO_PRIMARY_CANDIDATE",
                "symbol": symbol,
                "regime": regime,
                "ai_calls_made": 0,
                "tokens_used": 0,
            }

        primary_cand = candidate_setups[0]
        strategy_id = str(primary_cand.get("strategy_id", "S1_TREND_PULLBACK"))

        # Compute Brain 1 (Tabular ML) & Brain 2 (k-NN Episodic Memory) priors
        factor_items = list(orthogonal_factors.items())[:25]
        feature_names = [k for k, _ in factor_items]
        feature_vec = [float(v) for _, v in factor_items]

        ml_res = self.ensemble.tabular_model.predict_with_attribution(
            feature_vec, feature_names=feature_names if feature_names else None
        )
        p_quant_ml = float(ml_res["p_quant_ml"])

        knn_res = self.episodic_memory.query(feature_vec, regime=regime)
        p_knn = float(knn_res["p_knn"])

        base_rate_info = empirical_base_rate or {
            "historical_n": 50,
            "historical_win_rate_pct": round(
                self.calibrator.get_empirical_base_rate(strategy_id, regime) * 100.0, 2
            ),
            "historical_expectancy_r": 0.28,
            "breakeven_win_rate_pct": 38.8,
        }
        acct_info = account_state or {
            "available_balance_usdt": 10.0,
            "sizing_mode": "ALL_IN",
            "leverage": 20,
            "consecutive_losses": 0,
        }

        # Build compact JSON prompt (<= 1,400 tokens)
        stage1_payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "closed_bar_ts": closed_bar_ts,
            "regime_state": regime_state,
            "microstructure": microstructure,
            "orthogonal_factors": dict(factor_items[:15]),
            "candidate_setups": candidate_setups,
            "empirical_base_rate": base_rate_info,
            "quant_ml_prior": {
                "p_tp1_ml": round(p_quant_ml, 4),
                "top_pos": ml_res["top_positive_features"],
                "top_neg": ml_res["top_negative_features"],
            },
            "episodic_knn_prior": {
                "p_knn": round(p_knn, 4),
                "summary": knn_res["prompt_summary"],
            },
            "account_state": acct_info,
        }
        user_prompt_s1 = json.dumps(stage1_payload, separators=(",", ":"))

        # Stage 1 Call
        res_s1 = self.gateway.call_structured(
            user_prompt=user_prompt_s1,
            system_prompt=PRIMARY_SYSTEM_PROMPT,
            schema_type="PRIMARY",
            cache_key=(symbol, timeframe, closed_bar_ts, strategy_id, "PRIMARY"),
        )
        ai_calls_made = 0 if res_s1.get("cache_hit") else 1
        total_tokens = int(res_s1.get("tokens_used", 0))

        # Mandatory AI-Only Rule: if AI is down/unavailable, NEVER fallback to rule-based trade
        if not res_s1.get("ok") or not res_s1.get("data"):
            return {
                "decision": "SKIP",
                "skip_reason": "SKIP_AI_UNAVAILABLE",
                "error_detail": res_s1.get("error_detail"),
                "symbol": symbol,
                "regime": regime,
                "ai_calls_made": ai_calls_made,
                "tokens_used": total_tokens,
            }

        s1_data = res_s1["data"]
        if s1_data["decision"] == "SKIP":
            return {
                "decision": "SKIP",
                "skip_reason": "SKIP_AI_PRIMARY",
                "symbol": symbol,
                "regime": regime,
                "strategy_id": s1_data.get("selected_strategy_id", strategy_id),
                "p_win_raw": s1_data["p_win_raw"],
                "reasoning_id": s1_data["reasoning_id"],
                "ai_model_primary": res_s1.get("model"),
                "ai_model_auditor": None,
                "ai_calls_made": ai_calls_made,
                "tokens_used": total_tokens,
            }

        # Validate Structural Corridor before spending tokens on Stage 2 Auditor
        corridor_ok, corridor_msg, ev_pre = self._validate_structural_corridor(
            s1_data, candidate_setups, atr_15m=atr_15m
        )
        if not corridor_ok:
            return {
                "decision": "SKIP",
                "skip_reason": "REJECT_OUT_OF_CORRIDOR",
                "corridor_detail": corridor_msg,
                "symbol": symbol,
                "regime": regime,
                "strategy_id": s1_data["selected_strategy_id"],
                "ai_model_primary": res_s1.get("model"),
                "ai_calls_made": ai_calls_made,
                "tokens_used": total_tokens,
            }

        # Stage 2 — Cross-Model Red-Team Risk Auditor (only when Stage 1 == "TRADE")
        auditor_payload = {
            "symbol": symbol,
            "regime_state": regime_state,
            "microstructure": microstructure,
            "proposed_trade": s1_data,
            "quant_ml_p": round(p_quant_ml, 4),
            "knn_p": round(p_knn, 4),
            "empirical_base_rate": base_rate_info,
        }
        res_s2 = self.gateway.call_structured(
            user_prompt=json.dumps(auditor_payload, separators=(",", ":")),
            system_prompt=AUDITOR_SYSTEM_PROMPT,
            schema_type="AUDITOR",
            cache_key=(symbol, timeframe, closed_bar_ts, strategy_id, "AUDITOR"),
            exclude_provider=res_s1.get("provider"),
            exclude_model_family=res_s1.get("model_family"),
        )
        if not res_s2.get("cache_hit"):
            ai_calls_made += 1
        total_tokens += int(res_s2.get("tokens_used", 0))

        if not res_s2.get("ok") or not res_s2.get("data"):
            return {
                "decision": "SKIP",
                "skip_reason": "SKIP_AI_UNAVAILABLE",
                "error_detail": res_s2.get("error_detail"),
                "symbol": symbol,
                "regime": regime,
                "ai_model_primary": res_s1.get("model"),
                "ai_calls_made": ai_calls_made,
                "tokens_used": total_tokens,
            }

        s2_data = res_s2["data"]
        if s2_data["verdict"] == "VETO":
            return {
                "decision": "SKIP",
                "skip_reason": "SKIP_AUDITOR_VETO",
                "symbol": symbol,
                "regime": regime,
                "strategy_id": s1_data["selected_strategy_id"],
                "p_win_raw": s1_data["p_win_raw"],
                "p_win_audit": s2_data["p_win_audit"],
                "fatal_flaws": s2_data["fatal_flaws"],
                "reasoning_id": s2_data["audit_reasoning_id"],
                "ai_model_primary": res_s1.get("model"),
                "ai_model_auditor": res_s2.get("model"),
                "ai_calls_made": ai_calls_made,
                "tokens_used": total_tokens,
            }

        # Combine Stage-1 and Stage-2 LLM probabilities
        p_llm = 0.5 * (float(s1_data["p_win_raw"]) + float(s2_data["p_win_audit"]))

        # Combine 3 Brains via Neuro-Symbolic Log-Odds Stacking
        ens_res = self.ensemble.combine_probabilities(
            p_quant_ml=p_quant_ml,
            p_knn=p_knn,
            p_llm=p_llm,
        )
        p_hybrid = float(ens_res["p_hybrid"])

        # Calibrate probability with Empirical Base-Rate Shrinkage
        explicit_base = None
        if empirical_base_rate and "historical_win_rate_pct" in empirical_base_rate:
            explicit_base = float(empirical_base_rate["historical_win_rate_pct"]) / 100.0

        p_cal = self.calibrator.calibrate(
            p_raw=p_hybrid,
            strategy_id=s1_data["selected_strategy_id"],
            regime=regime,
            explicit_p_base=explicit_base,
        )

        # Evaluate Net EV Gate
        entry = float(s1_data["entry_price"])
        sl = float(s1_data["sl_price"])
        tp = float(s1_data["tp_price"])
        d_sl_frac = abs(entry - sl) / entry
        d_tp_frac = abs(tp - entry) / entry

        ev_ok, ev_reason, ev_metrics = self.calibrator.evaluate_ev_gate(
            p_cal=p_cal, d_sl=d_sl_frac, d_tp=d_tp_frac
        )
        if not ev_ok:
            return {
                "decision": "SKIP",
                "skip_reason": "SKIP_LOW_EV_R",
                "skip_detail": ev_reason,
                "symbol": symbol,
                "regime": regime,
                "strategy_id": s1_data["selected_strategy_id"],
                "p_raw": p_llm,
                "p_hybrid": p_hybrid,
                "p_cal": p_cal,
                "ev_r": ev_metrics["ev_r"],
                "rrr_net": ev_metrics["rrr_net"],
                "ai_model_primary": res_s1.get("model"),
                "ai_model_auditor": res_s2.get("model"),
                "ai_calls_made": ai_calls_made,
                "tokens_used": total_tokens,
            }

        # Evaluate Adaptive Conformal Inference (ACI) Gate: requires singleton {"WIN"}
        conf_ok, conf_reason, conf_info = self.conformal.evaluate_gate(p_cal)
        if not conf_ok:
            return {
                "decision": "SKIP",
                "skip_reason": conf_reason,
                "conformal_set": conf_info["prediction_set"],
                "symbol": symbol,
                "regime": regime,
                "strategy_id": s1_data["selected_strategy_id"],
                "p_raw": p_llm,
                "p_hybrid": p_hybrid,
                "p_cal": p_cal,
                "ev_r": ev_metrics["ev_r"],
                "rrr_net": ev_metrics["rrr_net"],
                "ai_model_primary": res_s1.get("model"),
                "ai_model_auditor": res_s2.get("model"),
                "ai_calls_made": ai_calls_made,
                "tokens_used": total_tokens,
            }

        # Evaluate Sniper 75% Precision Gate if enabled
        if self.sniper_75_enabled and max(p_hybrid, p_cal) < self.min_sniper_p_tp1:
            return {
                "decision": "SKIP",
                "skip_reason": "SKIP_BELOW_76PCT_PRECISION_GATE",
                "symbol": symbol,
                "regime": regime,
                "strategy_id": s1_data["selected_strategy_id"],
                "p_raw": p_llm,
                "p_hybrid": p_hybrid,
                "p_cal": p_cal,
                "ev_r": ev_metrics["ev_r"],
                "rrr_net": ev_metrics["rrr_net"],
                "ai_model_primary": res_s1.get("model"),
                "ai_model_auditor": res_s2.get("model"),
                "ai_calls_made": ai_calls_made,
                "tokens_used": total_tokens,
            }

        return {
            "decision": "TRADE",
            "skip_reason": None,
            "symbol": symbol,
            "regime": regime,
            "selected_strategy_id": s1_data["selected_strategy_id"],
            "direction": s1_data["direction"],
            "execution_style": s1_data["execution_style"],
            "entry_price": entry,
            "sl_price": sl,
            "tp_price": tp,
            "sl_distance_pct": d_sl_frac * 100.0,
            "tp_distance_pct": d_tp_frac * 100.0,
            "p_win_raw": float(s1_data["p_win_raw"]),
            "p_win_audit": float(s2_data["p_win_audit"]),
            "p_llm": p_llm,
            "p_quant_ml": p_quant_ml,
            "p_knn": p_knn,
            "p_hybrid": p_hybrid,
            "p_cal": p_cal,
            "ev_r": ev_metrics["ev_r"],
            "rrr_net": ev_metrics["rrr_net"],
            "conformal_set": conf_info["prediction_set"],
            "key_confluences": s1_data["key_confluences"],
            "primary_failure_mode": s1_data["primary_failure_mode"],
            "reasoning_id": s1_data["reasoning_id"],
            "ai_model_primary": res_s1.get("model"),
            "ai_model_auditor": res_s2.get("model"),
            "ai_calls_made": ai_calls_made,
            "tokens_used": total_tokens,
        }

    def review_open_position_emergency(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        current_price: float,
        sl_price: float,
        tp_price: float,
        p_survive: float,
        reversal_signals: Dict[str, Any],
        elapsed_sec: float,
    ) -> Dict[str, Any]:
        """
        INTRABAR_EMERGENCY_REVIEW mode (T6.3):
        Evaluates whether to scratch/abort an open position early around -0.25R
        when First-Passage Survival Probability P_survive(t) < 0.18 and order-flow
        microstructure has reversed 180 degrees.
        """
        risk_dist = max(1e-8, abs(entry_price - sl_price))
        signed_move = (
            (current_price - entry_price)
            if direction.upper() == "LONG"
            else (entry_price - current_price)
        )
        current_r = signed_move / risk_dist

        payload = {
            "mode": "INTRABAR_EMERGENCY_REVIEW",
            "symbol": symbol,
            "direction": direction.upper(),
            "entry_price": entry_price,
            "current_price": current_price,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "current_r_multiple": round(current_r, 3),
            "p_survive_first_passage": round(p_survive, 4),
            "elapsed_sec": round(elapsed_sec, 1),
            "reversal_signals": reversal_signals,
        }
        res = self.gateway.call_structured(
            user_prompt=json.dumps(payload, separators=(",", ":")),
            system_prompt=EMERGENCY_SYSTEM_PROMPT,
            schema_type="EMERGENCY",
        )
        if not res.get("ok") or not res.get("data"):
            return {
                "action": "HOLD_POSITION",
                "close_reason": None,
                "skip_reason": "SKIP_AI_UNAVAILABLE",
                "current_r": current_r,
                "p_survive": p_survive,
            }

        data = res["data"]
        action = data["action"]
        return {
            "action": action,
            "close_reason": "AI_THESIS_INVALIDATED_EARLY" if action == "ABORT_THESIS_SCRATCH" else None,
            "p_survive_ai": data["p_survive_ai"],
            "reasoning_id": data["reasoning_id"],
            "current_r": current_r,
            "p_survive": p_survive,
            "ai_model": res.get("model"),
            "tokens_used": res.get("tokens_used", 0),
        }
