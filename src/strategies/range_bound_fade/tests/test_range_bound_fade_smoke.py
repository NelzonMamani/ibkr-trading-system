import importlib


def test_range_bound_fade_strategy_policy_importable():
    module = importlib.import_module('src.strategies.range_bound_fade.strategy_policy')
    assert module is not None
