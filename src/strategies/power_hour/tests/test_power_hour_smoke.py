import importlib


def test_power_hour_strategy_policy_importable():
    module = importlib.import_module('src.strategies.power_hour.strategy_policy')
    assert module is not None
