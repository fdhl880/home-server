"""
PYROFUEL BOT - AUTO-DEGRADATION GUARD & STATISTICAL SHADOW PROMOTION (Task T8.2)
1. Auto-Degradation Guard: Jika strategi live mengalami Profit Factor < 0.80 ATAU
   E[R]_net < -0.15R pada 15 trade terakhir bergulir -> otomatis diturunkan ke `shadow_only = True`.
2. Statistical Promotion Rule: Strategi `shadow_only` hanya boleh dipromosikan kembali ke live
   jika memiliki n >= 80 trade shadow independen dengan batas bawah CI_95%(E[R]_net) > +0.10R.
"""
from typing import Any, Dict, Optional
import journal


def evaluate_auto_degradation(
    strategy_id: str,
    window: int = 15,
    min_trades: int = 15,
    min_pf: float = 0.80,
    min_expectancy_r: float = -0.15,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check rolling live performance over the last `window` trades.
    Demotes to `shadow_only = True` if `n >= min_trades` and (`PF < 0.80` or `E[R]_net < -0.15R`).
    """
    metrics = journal.get_rolling_strategy_metrics(
        strategy_id=strategy_id,
        window=window,
        include_shadow=False,
        db_path=db_path,
    )
    n = int(metrics["n"])
    pf = float(metrics["profit_factor"])
    exp_r = float(metrics["expectancy_r"])

    if n >= min_trades and (pf < min_pf or exp_r < min_expectancy_r):
        return {
            **metrics,
            "degraded": True,
            "shadow_only": True,
            "action": "DEMOTE_TO_SHADOW",
            "reason": f"Auto-Degradation triggered on {n} rolling trades: PF={pf:.2f} (<{min_pf}), E[R]={exp_r:+.3f}R (<{min_expectancy_r:+.2f}R)",
        }

    return {
        **metrics,
        "degraded": False,
        "shadow_only": False,
        "action": "KEEP_LIVE",
        "reason": f"Healthy live performance (n={n}, PF={pf:.2f}, E[R]={exp_r:+.3f}R)",
    }


def evaluate_shadow_promotion(
    strategy_id: str,
    min_shadow_trades: int = 80,
    min_ci95_low_r: float = 0.10,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check if a `shadow_only` strategy qualifies for statistical promotion to live:
    Requires `n >= 80` independent resolved shadow trades AND `CI_95%_low(E[R]_net) > +0.10R`.
    """
    metrics = journal.get_rolling_strategy_metrics(
        strategy_id=strategy_id,
        window=max(int(min_shadow_trades), 250),
        include_shadow=True,
        db_path=db_path,
    )
    n = int(metrics["n"])
    ci_low = float(metrics["ci95_low"])
    exp_r = float(metrics["expectancy_r"])

    if n >= min_shadow_trades and ci_low > min_ci95_low_r:
        return {
            **metrics,
            "promote_to_live": True,
            "shadow_only": False,
            "action": "PROMOTE_TO_LIVE",
            "reason": f"Promoted to LIVE: n={n} (>= {min_shadow_trades}), CI95_low={ci_low:+.3f}R (> +{min_ci95_low_r:.2f}R), E[R]={exp_r:+.3f}R",
        }

    return {
        **metrics,
        "promote_to_live": False,
        "shadow_only": True,
        "action": "KEEP_SHADOW",
        "reason": f"Insufficient shadow proof: n={n}/{min_shadow_trades}, CI95_low={ci_low:+.3f}R (req > +{min_ci95_low_r:.2f}R)",
    }


class StrategyLifecycleManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.status_map: Dict[str, Dict[str, bool]] = {
            "S1_TREND_PULLBACK": {"enabled": True, "shadow_only": False},
            "S2_OI_VOL_BREAKOUT": {"enabled": True, "shadow_only": False},
            "S3_LIQ_CASCADE_FADE": {"enabled": True, "shadow_only": False},
            "S4_EXTREME_FUNDING_REVERSION": {"enabled": True, "shadow_only": False},
        }

    def audit_strategy(self, strategy_id: str) -> Dict[str, Any]:
        st = self.status_map.setdefault(strategy_id, {"enabled": True, "shadow_only": False})
        if not st["shadow_only"]:
            res = evaluate_auto_degradation(strategy_id, db_path=self.db_path)
            if res["degraded"]:
                st["shadow_only"] = True
            return res
        else:
            res = evaluate_shadow_promotion(strategy_id, db_path=self.db_path)
            if res["promote_to_live"]:
                st["shadow_only"] = False
            return res
