"""Authoritative Ross policy facade introduced for PR1."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from src.strategies.ross_momentum.strategy_policy import (
    POLICY_V2,
    RossMomentumPolicy,
    StockSelectionSpec,
)

from .catalyst_policy import CatalystPolicy
from .execution_timing_policy import ExecutionTimingPolicy
from .exit_policy import ExitPolicy
from .float_policy import FloatPolicy
from .gap_policy import GapPolicy
from .pattern_input_policy import PatternInputPolicy
from .price_policy import PricePolicy
from .rvol_policy import RvolPolicy
from .watchlist_policy import WatchlistPolicy


@dataclass(frozen=True)
class RossPolicy:
    """Single import target for Ross policy authority.

    PR1 keeps the legacy strategy_policy.py values as the compatibility source,
    while exposing named sections future runtime consumers can migrate toward.
    """

    core: RossMomentumPolicy = field(default_factory=RossMomentumPolicy)

    @classmethod
    def from_stock_selection(cls, stock_selection: StockSelectionSpec) -> "RossPolicy":
        return cls(core=replace(RossMomentumPolicy(), stock_selection=stock_selection))

    @property
    def stock_selection(self) -> StockSelectionSpec:
        return self.core.stock_selection

    @property
    def price(self) -> PricePolicy:
        return PricePolicy.from_stock_selection(self.stock_selection)

    @property
    def rvol(self) -> RvolPolicy:
        return RvolPolicy.from_stock_selection(self.stock_selection)

    @property
    def gap(self) -> GapPolicy:
        return GapPolicy.from_policy(self.core)

    @property
    def float(self) -> FloatPolicy:
        return FloatPolicy.from_stock_selection(self.stock_selection)

    @property
    def catalyst(self) -> CatalystPolicy:
        return CatalystPolicy.from_stock_selection(self.stock_selection)

    @property
    def watchlist(self) -> WatchlistPolicy:
        return WatchlistPolicy.from_stock_selection(self.stock_selection)

    @property
    def pattern_inputs(self) -> PatternInputPolicy:
        return PatternInputPolicy.from_policy_v2()

    @property
    def execution_timing(self) -> ExecutionTimingPolicy:
        return ExecutionTimingPolicy.from_policy(self.core)

    @property
    def exit(self) -> ExitPolicy:
        return ExitPolicy.from_policy(self.core)

    @property
    def policy_v2(self):
        return POLICY_V2


ROSS_POLICY_AUTHORITY = RossPolicy()
