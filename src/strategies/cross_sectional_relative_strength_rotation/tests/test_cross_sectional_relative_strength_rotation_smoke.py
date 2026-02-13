import importlib


def test_cross_sectional_relative_strength_rotation_strategy_policy_importable():
    module = importlib.import_module('src.strategies.cross_sectional_relative_strength_rotation.strategy_policy')
    assert module is not None
