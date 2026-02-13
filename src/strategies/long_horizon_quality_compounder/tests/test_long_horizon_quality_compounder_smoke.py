import importlib


def test_long_horizon_quality_compounder_strategy_policy_importable():
    module = importlib.import_module('src.strategies.long_horizon_quality_compounder.strategy_policy')
    assert module is not None
