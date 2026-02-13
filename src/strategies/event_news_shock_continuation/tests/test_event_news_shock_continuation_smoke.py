import importlib


def test_event_news_shock_continuation_strategy_policy_importable():
    module = importlib.import_module('src.strategies.event_news_shock_continuation.strategy_policy')
    assert module is not None
