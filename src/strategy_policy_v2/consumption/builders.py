from __future__ import annotations

from src.strategy_policy_v2.policy_v2 import StrategyPolicyV2
from src.strategy_policy_v2.consumption.models import FocusResult, RankedCandidate, WatchlistResult


def _sort_ranked(ranked: list[RankedCandidate]) -> list[RankedCandidate]:
    return sorted(
        ranked,
        key=lambda row: (
            -(row.score),
            -(float(row.candidate.get("pct_change") or 0.0)),
            -(float(row.candidate.get("dollar_volume") or 0.0)),
            str(row.candidate.get("symbol") or ""),
        ),
    )


class WatchlistBuilderV2:
    def build(self, policy: StrategyPolicyV2, ranked: list[RankedCandidate]) -> WatchlistResult:
        sorted_rows = _sort_ranked(ranked)
        limit = int(getattr(policy.selection_plan, "watchlist_limit_k", 0) or 0)
        if limit <= 0:
            return WatchlistResult(watchlist=[])
        return WatchlistResult(watchlist=[row.candidate for row in sorted_rows[:limit]])


class FocusBuilderV2:
    def build(self, policy: StrategyPolicyV2, ranked: list[RankedCandidate]) -> FocusResult:
        sorted_rows = _sort_ranked(ranked)
        limit = int(getattr(policy.selection_plan, "focus_limit_m", 0) or 0)
        if limit <= 0:
            return FocusResult(focus=[])
        return FocusResult(focus=[row.candidate for row in sorted_rows[:limit]])
