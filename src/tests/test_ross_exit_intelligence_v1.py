from __future__ import annotations

from src.execution.execution_engine import ExecutionEngine
from src.execution.post_fill_lifecycle_engine import (
    ManagedTradeLifecycle,
    PositionLifecycleState,
    ProtectionOrderMeta,
)
from src.strategies.ross_momentum.exit_intelligence import RossExitIntelligence


class _DummyProvider:
    def __init__(self) -> None:
        self.flatten_calls = 0

    def name(self):
        return "DUMMY"

    def is_live(self):
        return False

    def get_positions(self):
        class _Snapshot:
            positions = []
        return _Snapshot()

    def get_open_orders(self):
        return []

    def flatten_position(self, **kwargs):
        self.flatten_calls += 1

        class _Result:
            filled_quantity = kwargs.get("quantity", 0)

        return _Result()

    def modify_stop_order(self, **kwargs):
        return {"ok": True, **kwargs}


def _trade(*, state: PositionLifecycleState = PositionLifecycleState.TRAILING_ELIGIBLE, break_even_activation: float = 101.0) -> ManagedTradeLifecycle:
    return ManagedTradeLifecycle(
        trade_id="t1",
        symbol="AAPL",
        strategy_id="ROSS",
        side="LONG",
        run_mode="PAPER",
        session_label="test",
        intended_qty=100,
        filled_qty=100,
        avg_fill_price=100.0,
        state=state,
        stop=ProtectionOrderMeta(order_type="STOP", side="SELL", trigger_price=99.0),
        target=ProtectionOrderMeta(order_type="LIMIT", side="SELL", trigger_price=102.0),
        break_even_activation=break_even_activation,
        trailing_activation=101.5,
        high_water_mark=100.0,
    )


def test_break_even_trigger() -> None:
    intel = RossExitIntelligence()
    trade = _trade()

    decision = intel.evaluate(trade=trade, current_price=101.2, current_volume=None, time_in_trade_sec=30)

    assert decision.action == "MOVE_STOP"
    assert decision.new_stop_price == 100.0


def test_momentum_failure_exit() -> None:
    intel = RossExitIntelligence()
    trade = _trade(break_even_activation=120.0)
    trade.high_water_mark = 102.0

    decision = intel.evaluate(trade=trade, current_price=101.3, current_volume=None, time_in_trade_sec=40)

    assert decision.action == "EXIT_MARKET"
    assert decision.reason == "momentum_failure"


def test_time_stop_exit() -> None:
    intel = RossExitIntelligence()
    trade = _trade()

    decision = intel.evaluate(trade=trade, current_price=100.1, current_volume=None, time_in_trade_sec=200)

    assert decision.action == "EXIT_MARKET"
    assert decision.reason == "time_stop_no_momentum"


def test_partial_scale_out() -> None:
    intel = RossExitIntelligence()
    trade = _trade(break_even_activation=120.0)

    decision = intel.evaluate(trade=trade, current_price=101.6, current_volume=None, time_in_trade_sec=20)

    assert decision.action == "SCALE_OUT"
    assert decision.scale_quantity == 50


def test_no_double_exit() -> None:
    provider = _DummyProvider()
    engine = ExecutionEngine(provider=provider)
    engine._provider = provider
    engine.provider = provider

    trade = _trade()
    engine.post_fill_lifecycle._trades[trade.trade_id] = trade

    engine._evaluate_exit_intelligence(symbol="AAPL", current_price=98.0)
    engine._evaluate_exit_intelligence(symbol="AAPL", current_price=97.5)

    assert provider.flatten_calls == 1


def test_high_water_mark_tracking() -> None:
    intel = RossExitIntelligence()
    trade = _trade()

    intel.evaluate(trade=trade, current_price=101.0, current_volume=None, time_in_trade_sec=10)
    assert trade.high_water_mark == 101.0

    intel.evaluate(trade=trade, current_price=100.5, current_volume=None, time_in_trade_sec=20)
    assert trade.high_water_mark == 101.0
