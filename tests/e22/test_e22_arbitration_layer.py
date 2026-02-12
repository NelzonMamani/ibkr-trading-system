from src.e22.strategy_scalability_and_arbitration import (
    E22PolicyConfig,
    IntentArbitrator,
    apply_e22_arbitration_layer,
)
from src.models.data_models import TradeIntent


def _intent(strategy: str, symbol: str, confidence: float = 0.8, direction: str = "LONG") -> TradeIntent:
    return TradeIntent(
        symbol=symbol,
        direction=direction,
        strategy_name=strategy,
        confidence=confidence,
        rationale="e22 test",
        trader_type="QUANT",
    )


def test_e22_arbitration_deterministic_ordering_conflict() -> None:
    intents = [
        _intent("beta", "ABC", confidence=0.6),
        _intent("alpha", "ABC", confidence=0.9),
    ]
    config = E22PolicyConfig(
        enabled=True,
        strategy_priority={"alpha": 5, "beta": 3},
        symbol_exclusivity=True,
    )
    artifact = IntentArbitrator().arbitrate(intents, config)
    assert len(artifact.allowed_intents) == 1
    assert artifact.allowed_intents[0].strategy_name == "alpha"
    assert artifact.suppression_counts_by_reason_code["SYMBOL_EXCLUSIVITY_CONFLICT"] == 1


def test_e22_cap_enforcement() -> None:
    intents = [
        _intent("s1", "AAA"),
        _intent("s1", "BBB"),
        _intent("s1", "CCC"),
    ]
    config = E22PolicyConfig(enabled=True, strategy_max_intents={"s1": 1})
    artifact = IntentArbitrator().arbitrate(intents, config)
    assert len(artifact.allowed_intents) == 1
    assert artifact.suppression_counts_by_reason_code["BUDGET_DENY"] >= 2


def test_e22_deterministic_across_runs() -> None:
    intents = [
        _intent("a", "XYZ", confidence=0.7),
        _intent("b", "XYZ", confidence=0.7),
        _intent("a", "QQQ", confidence=0.65),
    ]
    config = E22PolicyConfig(enabled=True, strategy_priority={"a": 1, "b": 1})
    first = IntentArbitrator().arbitrate(intents, config)
    second = IntentArbitrator().arbitrate(intents, config)
    assert [i.strategy_name for i in first.allowed_intents] == [i.strategy_name for i in second.allowed_intents]
    assert [i.symbol for i in first.allowed_intents] == [i.symbol for i in second.allowed_intents]
    assert first.suppression_counts_by_reason_code == second.suppression_counts_by_reason_code


def test_e22_disabled_non_regression_passthrough() -> None:
    intents = [_intent("alpha", "ABC"), _intent("beta", "ABC")]
    config = E22PolicyConfig(enabled=False)
    output, artifact = apply_e22_arbitration_layer(intents, config)
    assert output == intents
    assert artifact is None


def test_e22_enabled_returns_explainable_artifact() -> None:
    intents = [_intent("alpha", "ABC"), _intent("beta", "ABC")]
    config = E22PolicyConfig(enabled=True, strategy_priority={"alpha": 10, "beta": 1})
    output, artifact = apply_e22_arbitration_layer(intents, config)
    assert artifact is not None
    assert len(output) == 1
    assert artifact.strategy_order == ["alpha", "beta"]
    assert artifact.suppressed_intents
    assert artifact.suppressed_intents[0].reason_code
