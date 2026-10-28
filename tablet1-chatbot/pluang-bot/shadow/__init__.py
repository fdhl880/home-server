"""
PYROFUEL BOT - SHADOW ACCOUNT & AUTO-PROMOTION PACKAGE (Phase 8)
"""
from shadow.engine import ShadowEngine
from shadow.promote import (
    evaluate_auto_degradation,
    evaluate_shadow_promotion,
    StrategyLifecycleManager,
)

__all__ = [
    "ShadowEngine",
    "evaluate_auto_degradation",
    "evaluate_shadow_promotion",
    "StrategyLifecycleManager",
]
