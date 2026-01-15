"""Risk limits and decision contracts for Epoch 5."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class RiskDecisionType(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ALLOW_WITH_CONSTRAINTS = "ALLOW_WITH_CONSTRAINTS"


@dataclass(frozen=True)
class RiskDecision:
    symbol: str
    decision: RiskDecisionType
    max_position_size_allowed: int
    constraints: List[str] = field(default_factory=list)
    triggered_rules: List[str] = field(default_factory=list)
    rationale_text: str = ""
    risk_flags: List[str] = field(default_factory=list)
    cycle_id: Optional[int] = None


@dataclass(frozen=True)
class RiskLimitConfig:
    max_trades_per_day: int = 5
    max_daily_loss: float = 100.0
    max_spread_pct: float = 0.03
    max_spread_abs: float = 0.05
