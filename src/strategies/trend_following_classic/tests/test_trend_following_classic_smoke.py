import importlib


def test_trend_following_classic_strategy_policy_importable():
    module = importlib.import_module('src.strategies.trend_following_classic.strategy_policy')
    assert module is not None
