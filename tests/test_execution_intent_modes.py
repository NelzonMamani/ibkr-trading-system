from src.core.intent import build_execution_intent
from src.scanner.filters import _mechanical_stock_selection_gates
from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec


def test_execution_intent_modes() -> None:
    policy = StockSelectionSpec()
    readonly_intent = build_execution_intent(
        strategy_name="ROSS_MOMENTUM",
        mode="READONLY",
        session_phase="PREMARKET",
        policy=policy,
        execution_enabled=True,
    )
    assert readonly_intent.trade_enabled is False
    assert readonly_intent.scan_only is True

    live_intent = build_execution_intent(
        strategy_name="ROSS_MOMENTUM",
        mode="LIVE",
        session_phase="PREMARKET",
        policy=policy,
        execution_enabled=True,
    )
    assert live_intent.trade_enabled is True
    assert live_intent.scan_only is False


def test_mechanical_gates_use_policy() -> None:
    policy = StockSelectionSpec(
        gap_min_pct=42.0,
        price_min=2.0,
        price_max=3.0,
        rvol_min=9.0,
    )
    gates = _mechanical_stock_selection_gates(policy=policy)
    assert gates["min_pct_change"] == 42.0
    assert gates["min_price"] == 2.0
    assert gates["max_price"] == 3.0
    assert gates["min_rvol"] == 9.0
