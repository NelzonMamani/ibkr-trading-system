import importlib


def test_regime_adaptive_meta_allocator_strategy_policy_importable():
    module = importlib.import_module('src.strategies.regime_adaptive_meta_allocator.strategy_policy')
    assert module is not None
