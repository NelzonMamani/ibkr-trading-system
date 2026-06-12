"""Ross float policy section."""

from __future__ import annotations

from dataclasses import dataclass

from src.strategies.ross_momentum.strategy_policy import POLICY_V2, StockSelectionSpec


@dataclass(frozen=True)
class FloatPolicy:
    max_millions: float
    data_sources: tuple[str, ...]
    cache_policy: str

    @classmethod
    def from_stock_selection(cls, stock_selection: StockSelectionSpec) -> "FloatPolicy":
        v2_float = POLICY_V2.stock_selection_law.float_model
        return cls(
            max_millions=float(stock_selection.float_max_millions),
            data_sources=tuple(v2_float.float_data_sources),
            cache_policy=str(v2_float.cache_policy_commentary),
        )
