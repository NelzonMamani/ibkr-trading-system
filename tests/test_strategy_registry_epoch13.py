import pytest

from src.core.orchestrator import build_orchestrator_strategy_registry
from src.strategies.strategy_base import StrategyBase
from src.strategies.strategy_contracts import (
    DecisionType,
    MarketContext,
    ScannerContext,
    SessionContext,
    StrategyDecision,
    StrategyInput,
)
from src.strategies.strategy_registry import (
    StrategyRegistry,
    build_default_registry,
    build_strategy,
)


class InvalidStrategy(StrategyBase):
    strategy_id = ""
    strategy_name = "Invalid"
    version = "1.0"

    def evaluate(self, symbol: str, inputs: StrategyInput) -> StrategyDecision:
        return StrategyDecision(
            symbol=symbol,
            strategy_id=self.strategy_id,
            decision_type=DecisionType.NO_ACTION,
            confidence=0.0,
            rationale_text="invalid",
        )


def _sample_inputs(symbol: str) -> StrategyInput:
    return StrategyInput(
        symbol=symbol,
        session_context=SessionContext.REGULAR,
        scanner_context=ScannerContext(score=0.5, rank=1),
        market_context=MarketContext(
            price=10.5,
            spread=0.02,
            volume=10000,
            rvol=2.0,
            key_levels={"atr": 0.6, "ema9": 10.2, "ema20": 10.3, "vwap": 10.4},
        ),
    )


def test_registry_deterministic_metadata_order() -> None:
    registry = build_default_registry()
    metadata_ids = [entry.strategy_id for entry in registry.list_metadata()]
    assert metadata_ids == sorted(metadata_ids)
    assert metadata_ids == ["mean_reversion", "ross_momentum"]


def test_registry_rejects_invalid_and_unregistered_strategies() -> None:
    registry = StrategyRegistry()
    with pytest.raises(ValueError, match="Strategy metadata missing"):
        registry.register(InvalidStrategy())

    registry = build_default_registry(enabled_strategy_ids=["missing_strategy"])
    with pytest.raises(ValueError, match="not registered"):
        list(registry.enabled_strategies())


def test_orchestrator_registry_smoke() -> None:
    registry = build_orchestrator_strategy_registry(
        enabled_strategy_ids=["mean_reversion"]
    )
    decisions = registry.evaluate_symbol("TEST", _sample_inputs("TEST"))

    assert len(decisions) == 1
    assert decisions[0].strategy_id == "mean_reversion"


def test_strategy_factory_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="not registered"):
        build_strategy("missing_strategy")
