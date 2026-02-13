import importlib


def test_volatility_expansion_strategy_policy_importable():
    module = importlib.import_module('src.strategies.volatility_expansion.strategy_policy')
    assert module is not None
