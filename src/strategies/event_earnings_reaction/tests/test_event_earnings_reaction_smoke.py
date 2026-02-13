import importlib


def test_event_earnings_reaction_strategy_policy_importable():
    module = importlib.import_module('src.strategies.event_earnings_reaction.strategy_policy')
    assert module is not None
