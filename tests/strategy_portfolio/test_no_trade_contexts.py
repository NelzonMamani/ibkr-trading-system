from dataclasses import dataclass

from src.strategy_portfolio.contracts import AllowState, DecisionIntent, SignalIntent
from src.strategy_portfolio.normaliser import apply_no_trade_contexts


@dataclass(frozen=True)
class FakeContext:
    code: str


def test_apply_no_trade_contexts_blocks_decision():
    decision = DecisionIntent(
        allow_state=AllowState.ALLOW,
        signal_intent=SignalIntent.ENTER_LONG,
    )
    blocked = apply_no_trade_contexts(decision, [FakeContext(code="RISK_BLOCK")])
    assert blocked.allow_state == AllowState.DISALLOW
    assert blocked.signal_intent == SignalIntent.NO_TRADE
    assert blocked.reasons == ["RISK_BLOCK"]
