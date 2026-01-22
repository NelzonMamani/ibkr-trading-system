from src.strategies.statistical_intraday_momentum.signal_engine.signal_decision import decide_intent
from src.strategies.statistical_intraday_momentum.strategy_policy import default_policy
from src.strategy_portfolio.contracts import AllowState, SignalIntent
from src.strategy_portfolio.reason_codes import ReasonCode


def test_missing_context_defaults_to_no_trade():
    policy = default_policy()
    decision = decide_intent({}, policy)
    assert decision.allow_state == AllowState.DISALLOW
    assert decision.signal_intent == SignalIntent.NO_TRADE
    assert decision.reasons == [ReasonCode.MISSING_FIELD_DEFAULT.value]
