"""Strategy registry and execution dispatcher."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional

from src.strategies.strategy_base import StrategyBase, StrategyMetadata
from src.strategies.strategy_contracts import (
    StrategyContract,
    StrategyDecision,
    StrategyInput,
    validate_strategy_contract,
)
from src.strategies.ross_momentum.strategy import RossMomentumStrategy
from src.strategies.mean_reversion.registry_adapter import MeanReversionStrategyAdapter

StrategyFactory = Callable[[], StrategyBase]

STRATEGY_FACTORY: Dict[str, StrategyFactory] = {
    "mean_reversion": MeanReversionStrategyAdapter,
    "ross_momentum": RossMomentumStrategy,
}


@dataclass
class StrategyRegistry:
    enabled_strategy_ids: Optional[List[str]] = None
    _strategies: Dict[str, StrategyBase] = field(default_factory=dict)
    _metadata: Dict[str, StrategyMetadata] = field(default_factory=dict)
    _contracts: Dict[str, StrategyContract] = field(default_factory=dict)

    def register(self, strategy: StrategyBase) -> None:
        metadata = strategy.get_metadata()
        contract = strategy.get_contract()
        self._validate_metadata(metadata)
        self._validate_contract(contract)
        if metadata.strategy_id in self._strategies:
            raise ValueError(
                f"Strategy '{metadata.strategy_id}' already registered in registry"
            )
        self._strategies[metadata.strategy_id] = strategy
        self._metadata[metadata.strategy_id] = metadata
        self._contracts[metadata.strategy_id] = contract

    def register_factory(self, factory: StrategyFactory) -> StrategyBase:
        strategy = factory()
        self.register(strategy)
        return strategy

    def get(self, strategy_id: str) -> Optional[StrategyBase]:
        return self._strategies.get(strategy_id)

    def enabled_strategies(self) -> Iterable[StrategyBase]:
        if not self.enabled_strategy_ids:
            return [self._strategies[key] for key in sorted(self._strategies)]
        missing = [
            strategy_id
            for strategy_id in self.enabled_strategy_ids
            if strategy_id not in self._strategies
        ]
        if missing:
            raise ValueError(f"Enabled strategies not registered: {sorted(missing)}")
        return [
            self._strategies[strategy_id]
            for strategy_id in sorted(self.enabled_strategy_ids)
        ]

    def list_metadata(self) -> List[StrategyMetadata]:
        return [self._metadata[key] for key in sorted(self._metadata)]

    def list_contracts(self) -> List[StrategyContract]:
        return [self._contracts[key] for key in sorted(self._contracts)]

    def evaluate_symbol(self, symbol: str, inputs: StrategyInput) -> List[StrategyDecision]:
        decisions: List[StrategyDecision] = []
        for strategy in self.enabled_strategies():
            decisions.append(strategy.evaluate(symbol, inputs))
        return decisions

    @staticmethod
    def _validate_metadata(metadata: StrategyMetadata) -> None:
        missing = []
        if not metadata.strategy_id:
            missing.append("strategy_id")
        if not metadata.strategy_name:
            missing.append("strategy_name")
        if not metadata.version:
            missing.append("version")
        if missing:
            raise ValueError(
                "Strategy metadata missing required field(s): "
                + ", ".join(missing)
            )

    @staticmethod
    def _validate_contract(contract: StrategyContract) -> None:
        problems = validate_strategy_contract(contract)
        if problems:
            raise ValueError(
                "Strategy contract invalid for "
                f"'{contract.strategy_id}': {', '.join(problems)}"
            )


def build_default_registry(
    enabled_strategy_ids: Optional[List[str]] = None,
) -> StrategyRegistry:
    registry = StrategyRegistry(enabled_strategy_ids=enabled_strategy_ids)
    for strategy_id in sorted(STRATEGY_FACTORY):
        registry.register_factory(STRATEGY_FACTORY[strategy_id])
    return registry


def build_strategy(strategy_id: str) -> StrategyBase:
    if strategy_id not in STRATEGY_FACTORY:
        raise ValueError(f"Strategy '{strategy_id}' is not registered in the factory")
    return STRATEGY_FACTORY[strategy_id]()
