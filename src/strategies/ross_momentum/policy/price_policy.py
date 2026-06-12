"""Ross price-range policy section."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec


class PriceQuality(str, Enum):
    MISSING = "MISSING"
    SUB_DOLLAR_REJECT = "SUB_DOLLAR_REJECT"
    LOW_PRICE_DEGRADED = "LOW_PRICE_DEGRADED"
    LIVE_QUALITY = "LIVE_QUALITY"
    PREFERRED_SWEET_SPOT = "PREFERRED_SWEET_SPOT"
    HIGH_PRICE_REJECT = "HIGH_PRICE_REJECT"


@dataclass(frozen=True)
class PriceDecision:
    quality: PriceQuality
    satisfied: bool
    live_quality: bool
    preferred: bool
    rank_bonus: float
    reason: str


@dataclass(frozen=True)
class PricePolicy:
    minimum: float
    maximum: float
    live_quality_min: float = 2.0
    preferred_min: float = 5.0
    preferred_max: float = 10.0

    @classmethod
    def from_stock_selection(cls, stock_selection: StockSelectionSpec) -> "PricePolicy":
        return cls(
            minimum=float(stock_selection.price_min),
            maximum=float(stock_selection.price_max),
        )

    def assess(self, price: float | None) -> PriceDecision:
        if price is None:
            return PriceDecision(
                quality=PriceQuality.MISSING,
                satisfied=False,
                live_quality=False,
                preferred=False,
                rank_bonus=-0.25,
                reason="missing_price",
            )
        value = float(price)
        if value < self.minimum:
            return PriceDecision(
                quality=PriceQuality.SUB_DOLLAR_REJECT,
                satisfied=False,
                live_quality=False,
                preferred=False,
                rank_bonus=-0.5,
                reason="below_min_price",
            )
        if value > self.maximum:
            return PriceDecision(
                quality=PriceQuality.HIGH_PRICE_REJECT,
                satisfied=False,
                live_quality=False,
                preferred=False,
                rank_bonus=-0.5,
                reason="above_max_price",
            )
        if value < self.live_quality_min:
            return PriceDecision(
                quality=PriceQuality.LOW_PRICE_DEGRADED,
                satisfied=True,
                live_quality=False,
                preferred=False,
                rank_bonus=-0.10,
                reason="below_live_quality_price",
            )
        if self.preferred_min <= value <= self.preferred_max:
            return PriceDecision(
                quality=PriceQuality.PREFERRED_SWEET_SPOT,
                satisfied=True,
                live_quality=True,
                preferred=True,
                rank_bonus=0.15,
                reason="preferred_price_sweet_spot",
            )
        return PriceDecision(
            quality=PriceQuality.LIVE_QUALITY,
            satisfied=True,
            live_quality=True,
            preferred=False,
            rank_bonus=0.0,
            reason="price_live_quality",
        )
