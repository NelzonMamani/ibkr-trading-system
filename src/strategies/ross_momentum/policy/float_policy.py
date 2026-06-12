"""Ross float policy section."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.strategies.ross_momentum.strategy_policy import POLICY_V2, StockSelectionSpec


class FloatQuality(str, Enum):
    UNKNOWN_FLOAT = "UNKNOWN_FLOAT"
    EXCELLENT_LOW_FLOAT = "EXCELLENT_LOW_FLOAT"
    ACCEPTABLE_LOW_FLOAT = "ACCEPTABLE_LOW_FLOAT"
    HIGH_FLOAT_DEGRADED = "HIGH_FLOAT_DEGRADED"
    ABOVE_MAX_REJECT = "ABOVE_MAX_REJECT"


@dataclass(frozen=True)
class FloatDecision:
    quality: FloatQuality
    satisfied: bool
    live_quality: bool
    max_shares: int
    reason: str


@dataclass(frozen=True)
class FloatPolicy:
    max_millions: float
    data_sources: tuple[str, ...]
    cache_policy: str
    excellent_max_millions: float = 10.0

    @classmethod
    def from_stock_selection(cls, stock_selection: StockSelectionSpec) -> "FloatPolicy":
        v2_float = POLICY_V2.stock_selection_law.float_model
        return cls(
            max_millions=float(stock_selection.float_max_millions),
            data_sources=tuple(v2_float.float_data_sources),
            cache_policy=str(v2_float.cache_policy_commentary),
        )

    @property
    def max_shares(self) -> int:
        return int(float(self.max_millions) * 1_000_000)

    def assess(self, float_shares: int | float | None) -> FloatDecision:
        if float_shares is None:
            return FloatDecision(
                quality=FloatQuality.UNKNOWN_FLOAT,
                satisfied=False,
                live_quality=False,
                max_shares=self.max_shares,
                reason="unknown_float",
            )
        shares = int(float(float_shares))
        if shares > self.max_shares:
            return FloatDecision(
                quality=FloatQuality.ABOVE_MAX_REJECT,
                satisfied=False,
                live_quality=False,
                max_shares=self.max_shares,
                reason="above_max_float",
            )
        if shares <= int(float(self.excellent_max_millions) * 1_000_000):
            return FloatDecision(
                quality=FloatQuality.EXCELLENT_LOW_FLOAT,
                satisfied=True,
                live_quality=True,
                max_shares=self.max_shares,
                reason="excellent_low_float",
            )
        return FloatDecision(
            quality=FloatQuality.ACCEPTABLE_LOW_FLOAT,
            satisfied=True,
            live_quality=True,
            max_shares=self.max_shares,
            reason="acceptable_low_float",
        )
