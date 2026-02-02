"""Strategy registry and execution dispatcher."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from src.strategies.strategy_base import StrategyBase
from src.strategies.strategy_contracts import StrategyDecision, StrategyInput
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.mean_reversion.registry_adapter import MeanReversionStrategyAdapter


@dataclass
class StrategyRegistry:
    enabled_strategy_ids: Optional[List[str]] = None
    _strategies: Dict[str, StrategyBase] = field(default_factory=dict)

    def register(self, strategy: StrategyBase) -> None:
        self._strategies[strategy.strategy_id] = strategy

    def get(self, strategy_id: str) -> Optional[StrategyBase]:
        return self._strategies.get(strategy_id)

    def enabled_strategies(self) -> Iterable[StrategyBase]:
        if not self.enabled_strategy_ids:
            return list(self._strategies.values())
        return [
            strategy
            for strategy_id, strategy in self._strategies.items()
            if strategy_id in self.enabled_strategy_ids
        ]

    def evaluate_symbol(self, symbol: str, inputs: StrategyInput) -> List[StrategyDecision]:
        decisions: List[StrategyDecision] = []
        for strategy in self.enabled_strategies():
            decisions.append(strategy.evaluate(symbol, inputs))
        return decisions


def build_default_registry(
    enabled_strategy_ids: Optional[List[str]] = None,
) -> StrategyRegistry:
    registry = StrategyRegistry(enabled_strategy_ids=enabled_strategy_ids)
    registry.register(RossMomentumStrategy())
    registry.register(MeanReversionStrategyAdapter())
    return registry
