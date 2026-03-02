from __future__ import annotations

from src.strategy_policy_v2.policy_v2 import StrategyPolicyV2
from src.strategy_policy_v2.consumption.models import Candidate, RankedCandidate, RankingResult


def _clamp_norm(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return max(0.0, min(value, cap)) / cap


def _catalyst_score(catalyst: object) -> float:
    if isinstance(catalyst, bool):
        return 1.0 if catalyst else 0.0
    if isinstance(catalyst, str):
        mapping = {"HIGH": 1.0, "MEDIUM": 0.7, "LOW": 0.4, "UNCERTAIN": 0.2}
        return mapping.get(catalyst.strip().upper(), 0.0)
    return 0.0


class RankingEngineV2:
    def rank(self, policy: StrategyPolicyV2, eligible: list[Candidate]) -> RankingResult:
        ranked: list[RankedCandidate] = []
        ranking = policy.ranking_model
        float_cap = float(policy.stock_selection_law.float_model.float_max_millions or 100.0)
        if float_cap <= 0:
            float_cap = 100.0

        for candidate in eligible:
            pct_change = float(candidate.get("pct_change") or 0.0)
            rvol = float(candidate.get("rvol") or 0.0)
            float_m = float(candidate.get("float_millions") or float_cap)
            catalyst = _catalyst_score(candidate.get("news_catalyst"))
            spread_pct = float(candidate.get("spread_pct") or 0.0)
            halted = 1.0 if bool(candidate.get("halted")) else 0.0
            ssr = 1.0 if bool(candidate.get("ssr")) else 0.0

            pct_norm = _clamp_norm(pct_change, 100.0)
            rvol_norm = _clamp_norm(rvol, 20.0)
            float_inv_norm = _clamp_norm(max(0.0, float_cap - float_m), float_cap)
            liquidity_component = spread_pct + halted + (0.25 * ssr)

            score = (
                float(ranking.weight_pct_change) * pct_norm
                + float(ranking.weight_rvol) * rvol_norm
                + float(ranking.weight_float_inverse) * float_inv_norm
                + float(ranking.weight_catalyst) * catalyst
                - float(ranking.liquidity_penalty) * liquidity_component
            )

            ranked.append(
                RankedCandidate(
                    candidate=candidate,
                    score=score,
                    score_breakdown={
                        "pct_change_norm": pct_norm,
                        "rvol_norm": rvol_norm,
                        "float_inverse_norm": float_inv_norm,
                        "catalyst_quality_score": catalyst,
                        "liquidity_penalty_component": liquidity_component,
                        "score": score,
                    },
                )
            )

        return RankingResult(ranked=ranked)
