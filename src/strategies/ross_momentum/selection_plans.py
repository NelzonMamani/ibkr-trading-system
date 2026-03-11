from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, Tuple


class SelectionPlanBase(Protocol):
    plan_type: str


@dataclass(frozen=True)
class ScannerPlan:
    plan_type: Literal["SCANNER"] = "SCANNER"
    universe_source: str = "IBKR_TOP_GAINERS"
    ibkr_scan_code: str = "TOP_PERC_GAIN"
    top_n: int = 50
    watchlist_limit_k: int = 15
    focus_limit_m: int = 5
    policy_name: str = "DEFAULT_SCANNER"
    gating_profile: str = "MOMENTUM"
    session_allowlist: Tuple[str, ...] = ("PRE", "RTH")


@dataclass(frozen=True)
class ScreenerPlan:
    plan_type: Literal["SCREENER"] = "SCREENER"
    universe_source: str = "FUNDAMENTAL_UNIVERSE"
    filter_placeholders: Tuple[str, ...] = field(
        default_factory=lambda: ("quality", "valuation", "liquidity")
    )
    refresh_frequency: str = "DAILY"


@dataclass(frozen=True)
class PortfolioPlan:
    plan_type: Literal["PORTFOLIO"] = "PORTFOLIO"
    universe_source: str = "FUNDAMENTAL_UNIVERSE"
    rebalance_frequency: str = "MONTHLY"
    target_count: int = 20


@dataclass(frozen=True)
class EventPlan:
    plan_type: Literal["EVENT"] = "EVENT"
    universe_source: str = "EVENT_UNIVERSE"
    event_types: Tuple[str, ...] = ("EARNINGS", "NEWS")
    recency_window_minutes: int = 240


SelectionPlan = ScannerPlan | ScreenerPlan | PortfolioPlan | EventPlan
