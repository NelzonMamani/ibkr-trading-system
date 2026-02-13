import importlib


def test_time_based_seasonality_strategy_policy_importable():
    module = importlib.import_module('src.strategies.time_based_seasonality.strategy_policy')
    assert module is not None
