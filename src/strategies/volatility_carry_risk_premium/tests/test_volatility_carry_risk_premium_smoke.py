import importlib


def test_volatility_carry_risk_premium_strategy_policy_importable():
    module = importlib.import_module('src.strategies.volatility_carry_risk_premium.strategy_policy')
    assert module is not None
