from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class QualityGateResult:
    symbol: str
    passed: bool
    reasons: List[str]
    quality_score: float
    market_confidence: str
