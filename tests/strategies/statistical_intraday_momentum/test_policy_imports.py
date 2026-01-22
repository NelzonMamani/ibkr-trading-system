import importlib
import sys


def test_statistical_intraday_policy_imports_are_isolated():
    before = set(sys.modules)
    importlib.import_module("src.strategies.statistical_intraday_momentum.strategy_policy")
    importlib.import_module("src.strategies.statistical_intraday_momentum.signal_engine.signal_decision")

    newly_loaded = set(sys.modules) - before
    assert not any(
        module == "src.strategies.ross_momentum"
        or module.startswith("src.strategies.ross_momentum.")
        for module in newly_loaded
    )
