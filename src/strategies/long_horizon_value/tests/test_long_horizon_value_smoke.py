import importlib


def test_long_horizon_value_strategy_policy_importable():
    module = importlib.import_module('src.strategies.long_horizon_value.strategy_policy')
    assert module is not None
