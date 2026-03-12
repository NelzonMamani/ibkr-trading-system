from src.risk.risk_audit import compute_capital_per_symbol


def test_dynamic_allocation_focus_1() -> None:
    assert compute_capital_per_symbol(168, 1) == 168


def test_dynamic_allocation_focus_2() -> None:
    assert compute_capital_per_symbol(168, 2) == 84


def test_dynamic_allocation_focus_4() -> None:
    assert compute_capital_per_symbol(168, 4) == 42
