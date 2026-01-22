from src.strategy_portfolio.contracts import AllowState, SignalIntent
from src.strategy_portfolio.normaliser import derive_decision_intent
from src.strategy_portfolio.reason_codes import ReasonCode


def test_empty_policy_disallow():
    decision = derive_decision_intent(None, context={})
    assert decision.allow_state == AllowState.DISALLOW
    assert decision.signal_intent == SignalIntent.NO_TRADE
    assert decision.reasons == [ReasonCode.MISSING_POLICY_FIELDS.value]


def test_minimal_policy_allows_when_flag_set():
    policy = {"activation": {"allow": True}}
    decision = derive_decision_intent(policy, context={})
    assert decision.allow_state == AllowState.ALLOW
    assert decision.signal_intent == SignalIntent.HOLD
