from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MarginOfSafetyResult:
    symbol: str
    price: float
    intrinsic_base: float
    margin_of_safety: float
    required_margin_of_safety: float
    state: str
    reasons: List[str]
    quality_score: float
    stability_score: float
    market_confidence: str


@dataclass
class FocusEntry:
    symbol: str
    priority: int
    target_pct: float
    margin_of_safety: float
    confidence: float
    checklist_summary: List[str]
    max_price: Optional[float]
    state: str
    blocked_reason: Optional[str] = None
