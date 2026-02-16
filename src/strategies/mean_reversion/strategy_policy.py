"""Authoritative strategy policy wrapper for Mean Reversion."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.strategies.mean_reversion.mean_reversion_strategy_policy import (
    MeanReversionPolicyConfig,
)
from src.strategies.mean_reversion.scanner_policy import (
    mean_reversion_stock_selection_spec,
)


@dataclass(frozen=True)
class MeanReversionStrategyPolicy:
    name: str = "mean_reversion"
    version: str = "1.0"
    stock_selection: object = field(default_factory=mean_reversion_stock_selection_spec)
    risk_policy: MeanReversionPolicyConfig = field(default_factory=MeanReversionPolicyConfig)
    execution_policy: dict[str, object] = field(
        default_factory=lambda: {
            "order_type_primary": "LIMIT",
            "allow_market_orders": False,
        }
    )
    setup_families: tuple[str, ...] = (
        "MEAN_REVERSION_OVEREXTENSION",
        "MEAN_REVERSION_EXHAUSTION",
        "MEAN_REVERSION_RECLAIM",
    )


POLICY = MeanReversionStrategyPolicy()
