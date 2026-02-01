from src.strategies.long_horizon_value.pipeline import (
    assemble_fundamentals,
    compute_economics,
    estimate_intrinsic_values,
)
from src.strategies.long_horizon_value.contracts.types import SymbolRef


def test_intrinsic_range_ordering():
    symbols = [SymbolRef(symbol="AAPL", exchange="SMART", currency="USD", country="US")]
    fundamentals = assemble_fundamentals(symbols, run_id="test_intrinsic", as_of_year=2024)
    economics = compute_economics(fundamentals)
    intrinsic = estimate_intrinsic_values(economics)
    value = intrinsic["AAPL"]
    assert value.low <= value.base <= value.high
