from src.strategy_portfolio.contracts import AllowState, DecisionIntent, SignalIntent
from src.strategy_portfolio.normaliser import apply_no_trade_contexts


def test_no_trade_context_veto():
    decision = DecisionIntent(
        allow_state=AllowState.ALLOW,
        signal_intent=SignalIntent.ENTER_LONG,
        reasons=[],
    )
    vetoed = apply_no_trade_contexts(decision, [{"code": "RISK_VETO"}])
    assert vetoed.allow_state == AllowState.DISALLOW
    assert vetoed.signal_intent == SignalIntent.NO_TRADE
    assert "RISK_VETO" in vetoed.reasons
