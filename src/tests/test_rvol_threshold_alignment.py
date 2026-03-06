from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec


def test_ross_rvol_default_alignment() -> None:
    assert StockSelectionSpec().rvol_min == 2.0
