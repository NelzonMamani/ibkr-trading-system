from __future__ import annotations

from src.scanner.result_models import CandidateMetrics
from src.strategy_policy_v2.consumption.models import Candidate


def candidate_metrics_to_v2(candidate: CandidateMetrics) -> Candidate:
    return {
        "symbol": candidate.symbol,
        "session_label": candidate.session_label or "",
        "last_price": candidate.last_price,
        "pct_change": candidate.pct_change,
        "volume": candidate.volume,
        "premarket_volume": candidate.premarket_volume,
        "rvol": candidate.rvol if candidate.rvol is not None else candidate.relative_volume,
        "dollar_volume": candidate.dollar_volume,
        "float_millions": candidate.float_millions,
        "spread_pct": candidate.spread_pct,
        "halted": candidate.halted,
        "ssr": candidate.ssr,
        "news_catalyst": candidate.catalyst_present,
        "gate_checks": dict(candidate.gate_checks or {}),
    }


def candidates_metrics_to_v2(candidates: list[CandidateMetrics]) -> list[Candidate]:
    return [candidate_metrics_to_v2(candidate) for candidate in candidates]
