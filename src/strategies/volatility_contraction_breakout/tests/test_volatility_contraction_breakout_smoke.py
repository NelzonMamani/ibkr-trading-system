import importlib


def test_volatility_contraction_breakout_strategy_policy_importable():
    module = importlib.import_module('src.strategies.volatility_contraction_breakout.strategy_policy')
    assert module is not None
