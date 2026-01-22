import importlib

from src.strategy_portfolio import contracts, reason_codes


def test_contracts_imports_have_no_side_effects():
    importlib.reload(contracts)
    importlib.reload(reason_codes)


def test_enum_values():
    assert contracts.AllowState.ALLOW.value == "ALLOW"
    assert contracts.AllowState.DISALLOW.value == "DISALLOW"
    assert contracts.SignalIntent.NO_TRADE.value == "NO_TRADE"
    assert contracts.OrderConstraint.LIMIT.value == "LIMIT"


def test_decision_intent_defaults():
    decision = contracts.DecisionIntent()
    assert decision.allow_state == contracts.AllowState.DISALLOW
    assert decision.signal_intent == contracts.SignalIntent.NO_TRADE
    assert decision.reasons == []
    assert decision.metadata == {}


def test_reason_codes_values():
    assert reason_codes.ReasonCode.ACTIVATION_DISALLOW.value == "activation_disallow"
    assert reason_codes.ReasonCode.MISSING_FIELD_DEFAULT.value == "missing_field_default"
