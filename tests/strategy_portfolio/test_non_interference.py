import importlib
import sys


def test_strategy_portfolio_imports_do_not_pull_ross_or_orchestrator():
    before = set(sys.modules)

    importlib.import_module("src.strategy_portfolio.contracts")
    importlib.import_module("src.strategy_portfolio.registry")
    importlib.import_module("src.strategy_portfolio.arbitration")
    importlib.import_module("src.strategy_portfolio.allocation")
    importlib.import_module("src.strategy_portfolio.normaliser")

    forbidden_prefixes = (
        "src.strategies.ross_momentum",
        "src.core.orchestrator",
    )

    newly_loaded = set(sys.modules) - before
    for prefix in forbidden_prefixes:
        assert not any(
            module == prefix or module.startswith(f"{prefix}.")
            for module in newly_loaded
        )
