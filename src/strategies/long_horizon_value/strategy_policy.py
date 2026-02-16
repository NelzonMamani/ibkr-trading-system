"""
Authoritative Strategy Policy for Long Horizon Value (Buffett-Style)

This file defines WHAT the strategy believes.
No mechanics, no data fetching, no execution.
All thresholds and rules here are treated as law.
"""

from dataclasses import dataclass
from typing import Dict, List

# -----------------------------
# High-Level Verdicts
# -----------------------------
VERDICT_NEVER = "NEVER"
VERDICT_NO = "NO"
VERDICT_WATCHLIST = "WATCHLIST"
VERDICT_FOCUS = "FOCUS"
VERDICT_BUY = "BUY"

# -----------------------------
# Market Familiarity Adjustments
# -----------------------------
MARKET_CONFIDENCE_MULTIPLIER = {
    "HIGH": 1.0,
    "MEDIUM": 1.2,
    "LOW": 1.5,
}

# -----------------------------
# Core Thresholds (Conservative Defaults)
# -----------------------------
MIN_OPERATING_YEARS = 7
MIN_INTEREST_COVERAGE = 4.0
MAX_NET_DEBT_TO_EBITDA = 3.0
MIN_OWNER_EARNINGS_POSITIVE_YEARS = 5

BASE_REQUIRED_MARGIN_OF_SAFETY = 0.30  # 30%

# -----------------------------
# Portfolio Constraints (Percent-Based)
# -----------------------------
MAX_SINGLE_POSITION_PCT = 0.10
MAX_NEW_ALLOCATION_PCT = 0.05

# -----------------------------
# Policy Checklists (Declarative)
# -----------------------------
BUSINESS_QUALITY_REQUIREMENTS = [
    "UNDERSTANDABLE_BUSINESS",
    "DURABLE_DEMAND",
    "ECONOMIC_MOAT_PRESENT",
    "RATIONAL_MANAGEMENT",
]

FINANCIAL_STRENGTH_REQUIREMENTS = [
    "CONSERVATIVE_LEVERAGE",
    "STRONG_INTEREST_COVERAGE",
    "NO_REFINANCING_DEPENDENCE",
]

ECONOMIC_ENGINE_REQUIREMENTS = [
    "OWNERS_EARNINGS_ESTIMABLE",
    "POSITIVE_FREE_CASH_FLOW",
    "REASONABLE_REINVESTMENT",
]

# -----------------------------
# Decision Helpers
# -----------------------------
def required_margin_of_safety(market_confidence: str) -> float:
    multiplier = MARKET_CONFIDENCE_MULTIPLIER.get(market_confidence, 1.5)
    return BASE_REQUIRED_MARGIN_OF_SAFETY * multiplier

def portfolio_allows(target_pct: float) -> bool:
    return target_pct <= MAX_SINGLE_POSITION_PCT


@dataclass(frozen=True)
class LongHorizonValueStrategyPolicy:
    """Canonical policy wrapper for strategy governance verifiers."""

    name: str = "long_horizon_value"
    version: str = "1.0"
    stock_selection: Dict[str, object] = None  # type: ignore[assignment]
    risk_policy: Dict[str, object] = None  # type: ignore[assignment]
    execution_policy: Dict[str, object] = None  # type: ignore[assignment]
    setup_families: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stock_selection",
            {
                "universe_source": "FUNDAMENTAL_UNIVERSE",
                "top_n": 200,
                "watchlist_limit_k": 25,
                "focus_limit_m": 10,
            },
        )
        object.__setattr__(
            self,
            "risk_policy",
            {
                "max_single_position_pct": MAX_SINGLE_POSITION_PCT,
                "max_new_allocation_pct": MAX_NEW_ALLOCATION_PCT,
                "base_required_margin_of_safety": BASE_REQUIRED_MARGIN_OF_SAFETY,
            },
        )
        object.__setattr__(
            self,
            "execution_policy",
            {
                "order_type_primary": "LIMIT",
                "allow_market_orders": False,
                "rebalance_frequency": "LOW_TURNOVER",
            },
        )
        object.__setattr__(
            self,
            "setup_families",
            [
                "QUALITY_AT_REASONABLE_PRICE",
                "MARGIN_OF_SAFETY_ACCUMULATION",
                "BALANCE_SHEET_STRENGTH",
            ],
        )


POLICY = LongHorizonValueStrategyPolicy()
