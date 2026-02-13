import importlib


def test_pairs_divergence_reversion_strategy_policy_importable():
    module = importlib.import_module('src.strategies.pairs_divergence_reversion.strategy_policy')
    assert module is not None
