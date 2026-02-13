import importlib


def test_opening_drive_strategy_policy_importable():
    module = importlib.import_module('src.strategies.opening_drive.strategy_policy')
    assert module is not None
