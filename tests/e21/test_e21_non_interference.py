from src.strategy_portfolio.arbitration import ArbitrationInput, arbitrate_all
from src.strategy_portfolio.contracts import SignalIntent


def test_non_interference_arbitration_inputs_immutable():
    inputs = [
        ArbitrationInput(
            symbol="E21",
            strategy_id="alpha",
            priority=5,
            proposed_intent=SignalIntent.ENTER_LONG,
        ),
        ArbitrationInput(
            symbol="E21",
            strategy_id="beta",
            priority=4,
            proposed_intent=SignalIntent.HOLD,
        ),
    ]
    snapshot = list(inputs)
    arbitrate_all(inputs)
    assert inputs == snapshot
