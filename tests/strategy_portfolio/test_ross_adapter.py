from src.models.data_models import TradeIntent
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy
from src.strategies.strategy_contracts import DecisionType, StrategyDecision
from src.strategy_portfolio.adapters import ross_momentum_adapter
from src.strategy_portfolio.contracts import AllowState, SignalIntent
from src.strategy_portfolio.reason_codes import ReasonCode


def test_adapter_imports():
    assert ross_momentum_adapter.ross_identity() is not None


def test_identity_mapping():
    policy = RossMomentumPolicy()
    identity = ross_momentum_adapter.ross_identity(policy)
    assert identity.strategy_id == policy.name
    assert identity.strategy_version == policy.version


def test_output_mapping_trade_intent():
    trade_intent = TradeIntent(
        symbol="AAPL",
        direction="LONG",
        strategy_name="RossMomentumStrategyV1",
        confidence=0.7,
        rationale="test",
    )
    decision = ross_momentum_adapter.ross_output_to_decision_intent(trade_intent)
    assert decision.allow_state == AllowState.ALLOW
    assert decision.signal_intent == SignalIntent.ENTER_LONG


def test_output_mapping_strategy_decision():
    decision = StrategyDecision(
        symbol="AAPL",
        strategy_id="ross_momentum",
        decision_type=DecisionType.NO_ACTION,
        confidence=0.0,
        rationale_text="none",
        intents=[],
    )
    mapped = ross_momentum_adapter.ross_output_to_decision_intent(decision)
    assert mapped.signal_intent == SignalIntent.NO_TRADE


def test_fail_safe_unknown_output():
    mapped = ross_momentum_adapter.ross_output_to_decision_intent(None)
    assert mapped.allow_state == AllowState.DISALLOW
    assert mapped.signal_intent == SignalIntent.NO_TRADE
    assert mapped.reasons == [ReasonCode.MAPPING_UNSUPPORTED_OUTPUT.value]
