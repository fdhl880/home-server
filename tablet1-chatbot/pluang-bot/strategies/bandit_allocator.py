"""
PYROFUEL BOT - REGIME-CONTEXTUAL DISCOUNTED THOMPSON SAMPLING BANDIT (Task T8.3)
Mengalokasikan prioritas kandidat strategi (S1..S4) secara adaptif menggunakan
distribusi posterior Beta-Bernoulli terdiskonto (faktor pelupa delta = 0.96) per pasangan
`(strategy_id, regime)` dan menyimpan status di `results/bandit_state.json`.
"""
import os
import json
from typing import Any, Dict, List, Optional, Sequence, Union
import numpy as np
from strategies.base import SetupCandidate

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STATE_PATH = os.path.join(BOT_DIR, "results", "bandit_state.json")


class ContextualThompsonBandit:
    def __init__(
        self,
        discount_factor: float = 0.96,
        prior_alpha: float = 2.0,
        prior_beta: float = 2.0,
        state_path: Optional[str] = None,
        seed: Optional[int] = None,
    ):
        self.discount_factor = float(discount_factor)
        self.prior_alpha = float(prior_alpha)
        self.prior_beta = float(prior_beta)
        self.state_path = state_path or DEFAULT_STATE_PATH
        self.rng = np.random.default_rng(seed)
        self.arms: Dict[str, Dict[str, float]] = {}
        self.load_state()

    @staticmethod
    def _arm_key(strategy_id: str, regime: str) -> str:
        return f"{strategy_id}|{regime or 'UNKNOWN'}"

    def load_state(self) -> None:
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "arms" in data:
                    self.arms = data["arms"]
                elif isinstance(data, dict):
                    self.arms = data
            except Exception:
                self.arms = {}

    def save_state(self) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.state_path)), exist_ok=True)
            payload = {
                "discount_factor": self.discount_factor,
                "prior_alpha": self.prior_alpha,
                "prior_beta": self.prior_beta,
                "arms": self.arms,
            }
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def get_arm(self, strategy_id: str, regime: str = "UNKNOWN") -> Dict[str, float]:
        key = self._arm_key(strategy_id, regime)
        if key not in self.arms:
            self.arms[key] = {
                "alpha": self.prior_alpha,
                "beta": self.prior_beta,
                "n_updates": 0,
            }
        return self.arms[key]

    def update(
        self,
        strategy_id: str,
        regime: str = "UNKNOWN",
        r_net: Optional[float] = None,
        won: Optional[bool] = None,
    ) -> Dict[str, float]:
        """
        Discounted Beta-Bernoulli update:
            alpha_{s,r} <- delta * alpha_{s,r} + I(R_net > 0)
            beta_{s,r}  <- delta * beta_{s,r}  + I(R_net <= 0)
        """
        arm = self.get_arm(strategy_id, regime)
        if won is None:
            is_win = bool((r_net or 0.0) > 0.0)
        else:
            is_win = bool(won)

        delta = self.discount_factor
        new_alpha = max(0.5, delta * float(arm["alpha"])) + (1.0 if is_win else 0.0)
        new_beta = max(0.5, delta * float(arm["beta"])) + (0.0 if is_win else 1.0)

        arm["alpha"] = round(new_alpha, 6)
        arm["beta"] = round(new_beta, 6)
        arm["n_updates"] = int(arm.get("n_updates", 0)) + 1
        self.save_state()
        return dict(arm)

    def get_posterior_mean(self, strategy_id: str, regime: str = "UNKNOWN") -> float:
        arm = self.get_arm(strategy_id, regime)
        a = float(arm["alpha"])
        b = float(arm["beta"])
        return round(a / max(a + b, 1e-9), 4)

    def sample_theta(
        self,
        strategy_id: str,
        regime: str = "UNKNOWN",
        deterministic: bool = False,
    ) -> float:
        arm = self.get_arm(strategy_id, regime)
        a = max(0.1, float(arm["alpha"]))
        b = max(0.1, float(arm["beta"]))
        if deterministic:
            return round(a / (a + b), 4)
        sample = float(self.rng.beta(a, b))
        return round(sample, 4)

    def rank_candidates(
        self,
        candidates: Sequence[Union[SetupCandidate, Dict[str, Any]]],
        regime: Optional[str] = None,
        deterministic: bool = False,
    ) -> List[Union[SetupCandidate, Dict[str, Any]]]:
        """
        Rank multiple `SetupCandidate` objects by Thompson-weighted reward:
            score_{s,r} = theta_{s,r} * RRR_{net, s}
        Attaches `bandit_theta` and `bandit_score` to each candidate.
        """
        scored = []
        for cand in candidates:
            s_id = cand["strategy_id"] if isinstance(cand, dict) else cand.strategy_id
            c_reg = regime or (cand.get("regime", "UNKNOWN") if isinstance(cand, dict) else cand.regime)
            rrr_net = float(cand.get("rrr_net", 1.6) if isinstance(cand, dict) else cand.rrr_net)

            theta = self.sample_theta(s_id, c_reg, deterministic=deterministic)
            score = round(theta * rrr_net, 4)

            if isinstance(cand, dict):
                cand["bandit_theta"] = theta
                cand["bandit_score"] = score
            else:
                cand.bandit_theta = theta
                cand.bandit_score = score
            scored.append((score, theta, cand))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored]
