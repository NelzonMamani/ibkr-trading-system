import importlib


def test_support_resistance_channel_strategy_policy_importable():
    module = importlib.import_module('src.strategies.support_resistance_channel.strategy_policy')
    assert module is not None
