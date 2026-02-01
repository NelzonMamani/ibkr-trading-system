from src.strategies.long_horizon_value import runner
from src.strategies.long_horizon_value import strategy_policy


def test_long_horizon_value_imports():
    assert runner.LongHorizonValueRunner
    assert strategy_policy.MIN_OPERATING_YEARS > 0
