import importlib


def test_vwap_reclaim_strategy_policy_importable():
    module = importlib.import_module('src.strategies.vwap_reclaim.strategy_policy')
    assert module is not None
