"""Helpers for candlestick evidence tagging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from src.strategies.ross_momentum.patterns.pattern_types import Direction


@dataclass(frozen=True)
class CandleEvidence:
    pattern_name: str
    direction: Direction
    confidence: float
    rationale: str

    def tag(self) -> str:
        return f"candle:{self.pattern_name.lower().replace(' ', '_')}"


def evidence_tags(evidence: Iterable[CandleEvidence]) -> List[str]:
    return [item.tag() for item in evidence]
