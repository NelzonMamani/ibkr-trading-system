import importlib


def test_statistical_intraday_momentum_strategy_policy_importable():
    module = importlib.import_module('src.strategies.statistical_intraday_momentum.strategy_policy')
    assert module is not None
