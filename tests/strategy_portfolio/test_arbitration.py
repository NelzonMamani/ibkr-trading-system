from src.strategy_portfolio.arbitration import ArbitrationInput, arbitrate_all, arbitrate_symbol
from src.strategy_portfolio.contracts import SignalIntent
from src.strategy_portfolio.reason_codes import ReasonCode


def test_arbitrate_symbol_deterministic_winner():
    inputs = [
        ArbitrationInput("AAPL", "alpha", 5, SignalIntent.ENTER_LONG),
        ArbitrationInput("AAPL", "beta", 10, SignalIntent.ENTER_LONG),
    ]
    result = arbitrate_symbol(inputs)
    assert result.winner_strategy_id == "beta"
    assert result.winner_intent == SignalIntent.ENTER_LONG
    assert result.denied == [("alpha", ReasonCode.ARBITRATION_DENY_LOWER_PRIORITY.value)]


def test_arbitrate_symbol_tie_breaker():
    inputs = [
        ArbitrationInput("AAPL", "alpha", 10, SignalIntent.ENTER_LONG),
        ArbitrationInput("AAPL", "beta", 10, SignalIntent.ENTER_SHORT),
    ]
    result = arbitrate_symbol(inputs)
    assert result.winner_strategy_id == "alpha"


def test_arbitrate_symbol_no_trade_filtered():
    inputs = [
        ArbitrationInput("AAPL", "alpha", 10, SignalIntent.NO_TRADE),
        ArbitrationInput("AAPL", "beta", 5, SignalIntent.ENTER_LONG),
    ]
    result = arbitrate_symbol(inputs)
    assert result.winner_strategy_id == "beta"
    assert result.denied == []


def test_arbitrate_all_groups_by_symbol():
    inputs = [
        ArbitrationInput("AAPL", "alpha", 10, SignalIntent.ENTER_LONG),
        ArbitrationInput("MSFT", "beta", 5, SignalIntent.ENTER_SHORT),
    ]
    results = arbitrate_all(inputs)
    assert [result.symbol for result in results] == ["AAPL", "MSFT"]


def test_arbitrate_symbol_exit_only_when_position():
    inputs = [
        ArbitrationInput("AAPL", "alpha", 10, SignalIntent.ENTER_LONG),
        ArbitrationInput("AAPL", "beta", 5, SignalIntent.ENTER_SHORT),
    ]
    result = arbitrate_symbol(inputs, loser_position_map={"beta": True})
    assert result.exit_only == [("beta", ReasonCode.ARBITRATION_DENY_LOWER_PRIORITY.value)]


def test_arbitrate_symbol_precedence_with_multiple_strategies():
    inputs = [
        ArbitrationInput("AAPL", "alpha", 5, SignalIntent.ENTER_LONG),
        ArbitrationInput("AAPL", "gamma", 8, SignalIntent.ENTER_SHORT),
        ArbitrationInput("AAPL", "beta", 8, SignalIntent.ENTER_LONG),
    ]
    result = arbitrate_symbol(inputs)
    assert result.winner_strategy_id == "beta"
    assert result.winner_intent == SignalIntent.ENTER_LONG
    assert result.denied == [
        ("gamma", ReasonCode.ARBITRATION_DENY_LOWER_PRIORITY.value),
        ("alpha", ReasonCode.ARBITRATION_DENY_LOWER_PRIORITY.value),
    ]
