from dataclasses import dataclass

from src.strategy_portfolio.allocation import AllocationConfig, allocate
from src.strategy_portfolio.arbitration import ArbitrationInput, arbitrate_symbol
from src.strategy_portfolio.contracts import AllowState, SignalIntent, StrategyIdentity
from src.strategy_portfolio.normaliser import derive_decision_intent


@dataclass(frozen=True)
class FakePolicy:
    identity: StrategyIdentity
    activation: dict
    intent: str


def test_end_to_end_smoke():
    policy = FakePolicy(
        identity=StrategyIdentity("stat_intraday", "1.0"),
        activation={"allow": True},
        intent=SignalIntent.ENTER_LONG.value,
    )
    decision = derive_decision_intent(policy, context={"symbol": "AAPL"})
    assert decision.allow_state == AllowState.ALLOW
    assert decision.signal_intent == SignalIntent.ENTER_LONG

    arbitration = arbitrate_symbol(
        [
            ArbitrationInput("AAPL", "stat_intraday", 10, decision.signal_intent),
            ArbitrationInput("AAPL", "other", 5, SignalIntent.ENTER_SHORT),
        ]
    )
    assert arbitration.winner_strategy_id == "stat_intraday"

    allocations = allocate(
        100.0,
        [
            AllocationConfig(strategy_id="stat_intraday", allocation_pct=0.6),
            AllocationConfig(strategy_id="other", allocation_pct=0.4),
        ],
    )
    allocation_map = {allocation.strategy_id: allocation for allocation in allocations}
    assert allocation_map["stat_intraday"].budget_usd == 60.0
    assert allocation_map["other"].budget_usd == 40.0
