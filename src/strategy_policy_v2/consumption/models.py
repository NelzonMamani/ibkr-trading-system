from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict


class Candidate(TypedDict, total=False):
    symbol: str
    session_label: str
    last_price: float
    pct_change: float
    volume: int
    premarket_volume: int
    rvol: float
    dollar_volume: float
    float_millions: float
    spread_pct: float
    halted: bool
    ssr: bool
    news_catalyst: bool | str
    gate_checks: dict[str, bool]


class CandidateView(Protocol):
    symbol: str


@dataclass(frozen=True)
class DroppedCandidate:
    candidate: Candidate
    reasons: list[str]


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SelectionResult:
    eligible: list[Candidate]
    dropped: list[DroppedCandidate]
    metrics: dict[str, Any]


@dataclass(frozen=True)
class RankedCandidate:
    candidate: Candidate
    score: float
    score_breakdown: dict[str, float]


@dataclass(frozen=True)
class RankingResult:
    ranked: list[RankedCandidate]


@dataclass(frozen=True)
class WatchlistResult:
    watchlist: list[Candidate]


@dataclass(frozen=True)
class FocusResult:
    focus: list[Candidate]
