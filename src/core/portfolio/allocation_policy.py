from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ARBITRATION_DENY_KILL_SWITCH = "ARBITRATION_DENY_KILL_SWITCH"
ARBITRATION_DENY_GLOBAL_PORTFOLIO_CAP = "ARBITRATION_DENY_GLOBAL_PORTFOLIO_CAP"
ARBITRATION_DENY_STRATEGY_BUDGET = "ARBITRATION_DENY_STRATEGY_BUDGET"
ARBITRATION_DENY_MAX_STRATEGY_POSITIONS = "ARBITRATION_DENY_MAX_STRATEGY_POSITIONS"
ARBITRATION_DENY_SCALE_IN_NOT_ALLOWED = "ARBITRATION_DENY_SCALE_IN_NOT_ALLOWED"
ARBITRATION_DENY_INCOMPATIBLE_OPEN_POSITION = "ARBITRATION_DENY_INCOMPATIBLE_OPEN_POSITION"
ARBITRATION_DENY_CRITICAL_DRIFT = "ARBITRATION_DENY_CRITICAL_DRIFT"
ARBITRATION_APPROVE_NEW_ENTRY = "ARBITRATION_APPROVE_NEW_ENTRY"
ARBITRATION_APPROVE_SCALE_IN = "ARBITRATION_APPROVE_SCALE_IN"
ARBITRATION_PASS_EXIT_REDUCTION = "ARBITRATION_PASS_EXIT_REDUCTION"
ARBITRATION_DEFER_LOWER_PRIORITY = "ARBITRATION_DEFER_LOWER_PRIORITY"


@dataclass(frozen=True)
class StrategyCapitalBudget:
    strategy_name: str
    enabled: bool
    max_gross_exposure: float
    max_open_positions: int
    priority_rank: int
    allow_scale_in: bool
    allow_new_entries: bool
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioAllocationSnapshot:
    total_portfolio_exposure: float
    remaining_portfolio_capacity: float
    total_open_positions: int
    per_strategy_exposure: dict[str, float] = field(default_factory=dict)
    per_strategy_open_positions: dict[str, int] = field(default_factory=dict)
    kill_switch_active: bool = False
    drift_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArbitrationDecision:
    candidate_id: str
    symbol: str
    strategy_name: str
    requested_trade_value: float
    approved: bool
    approval_type: str
    approved_trade_value: float
    reason_code: str
    rationale: str
    priority_rank: int
    portfolio_capacity_before: float
    portfolio_capacity_after: float
    classification: str = "UNCLASSIFIED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
