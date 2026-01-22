from src.strategy_portfolio.contracts import StrategyIdentity
from src.strategy_portfolio.registry import StrategyRegistry, StrategyRegistryEntry, StrategyState


def _entry(strategy_id: str, priority: int = 0, state: StrategyState = StrategyState.DISABLED):
    return StrategyRegistryEntry(
        identity=StrategyIdentity(strategy_id=strategy_id, strategy_version="1.0"),
        priority=priority,
        state=state,
    )


def test_registry_default_disabled():
    registry = StrategyRegistry()
    registry.register(_entry("alpha"))
    assert registry.get("alpha").state == StrategyState.DISABLED


def test_registry_enable_disable():
    registry = StrategyRegistry()
    registry.register(_entry("alpha"))
    registry.enable("alpha")
    assert registry.get("alpha").state == StrategyState.ENABLED
    registry.disable("alpha")
    assert registry.get("alpha").state == StrategyState.DISABLED


def test_registry_deterministic_sorting():
    registry = StrategyRegistry()
    registry.register(_entry("alpha", priority=5, state=StrategyState.ENABLED))
    registry.register(_entry("beta", priority=10, state=StrategyState.ENABLED))
    registry.register(_entry("gamma", priority=10, state=StrategyState.ENABLED))
    ordered = [entry.identity.strategy_id for entry in registry.list_enabled_ordered()]
    assert ordered == ["beta", "gamma", "alpha"]


def test_registry_register_idempotent():
    registry = StrategyRegistry()
    registry.register(_entry("alpha", priority=1))
    registry.register(_entry("alpha", priority=2))
    assert registry.get("alpha").priority == 2
