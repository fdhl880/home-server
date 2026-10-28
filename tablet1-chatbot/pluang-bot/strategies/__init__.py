"""
PYROFUEL BOT - QUANTITATIVE TRIPLE-BARRIER STRATEGIES PACKAGE (Phase 4 & 8)
Exports `SetupCandidate`, `S1_TREND_PULLBACK`, `S2_OI_VOL_BREAKOUT`,
`S3_LIQ_CASCADE_FADE`, `S4_EXTREME_FUNDING_REVERSION`, and `ContextualThompsonBandit`.
"""
from typing import Any, Dict, List, Optional, Sequence
from strategies.base import SetupCandidate, build_sniper_candidate
from strategies import s1_trend_pullback
from strategies import s2_oi_breakout
from strategies import s3_liq_exhaustion
from strategies import s4_funding_reversion
from strategies.bandit_allocator import ContextualThompsonBandit

ALL_STRATEGIES = {
    s1_trend_pullback.STRATEGY_ID: s1_trend_pullback.evaluate,
    s2_oi_breakout.STRATEGY_ID: s2_oi_breakout.evaluate,
    s3_liq_exhaustion.STRATEGY_ID: s3_liq_exhaustion.evaluate,
    s4_funding_reversion.STRATEGY_ID: s4_funding_reversion.evaluate,
}


def generate_all_candidates(
    klines: Sequence[Any],
    regime_state: Dict[str, Any],
    micro_state: Optional[Dict[str, Any]] = None,
    symbol: str = "",
    enabled_strategies: Optional[Sequence[str]] = None,
    bandit: Optional[ContextualThompsonBandit] = None,
    deterministic_bandit: bool = False,
) -> List[SetupCandidate]:
    """
    Evaluate all enabled Triple-Barrier primary strategies on `klines` for `regime_state`,
    and rank the resulting `SetupCandidate` list via `ContextualThompsonBandit` if provided.
    """
    regime = str((regime_state or {}).get("regime", "UNKNOWN"))
    if regime == "CHOP_NO_TRADE":
        return []

    candidates: List[SetupCandidate] = []
    for strat_id, eval_fn in ALL_STRATEGIES.items():
        if enabled_strategies is not None and strat_id not in enabled_strategies:
            continue
        cand = eval_fn(klines, regime_state, micro_state=micro_state, symbol=symbol)
        if cand is not None:
            candidates.append(cand)

    if len(candidates) > 1 and bandit is not None:
        ranked = bandit.rank_candidates(candidates, regime=regime, deterministic=deterministic_bandit)
        return [c for c in ranked if isinstance(c, SetupCandidate)]
    elif len(candidates) == 1 and bandit is not None:
        bandit.rank_candidates(candidates, regime=regime, deterministic=deterministic_bandit)

    return candidates


__all__ = [
    "SetupCandidate",
    "build_sniper_candidate",
    "ContextualThompsonBandit",
    "s1_trend_pullback",
    "s2_oi_breakout",
    "s3_liq_exhaustion",
    "s4_funding_reversion",
    "ALL_STRATEGIES",
    "generate_all_candidates",
]
