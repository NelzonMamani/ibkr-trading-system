from datetime import datetime, timedelta, timezone

from src.execution.post_fill_lifecycle_engine import PostFillLifecycleEngine, PositionLifecycleState


class _ExecProvider:
    def __init__(self) -> None:
        self.stop_calls = []
        self.target_calls = []
        self.intent_calls = []

    def place_stop_order(self, **kwargs):
        self.stop_calls.append(kwargs)
        return {"broker_order_id": "STOP-1", "status": "Submitted"}

    def place_target_order(self, **kwargs):
        self.target_calls.append(kwargs)
        return {"broker_order_id": "TGT-1", "status": "Submitted"}

    def submit_trade_intent(self, intent):
        self.intent_calls.append(intent)


def _open_trade(provider: _ExecProvider, trade_id: str = "T-1") -> PostFillLifecycleEngine:
    engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=provider)
    engine.activate_trade_management_after_fill(
        trade_id=trade_id,
        symbol="AAPL",
        side="LONG",
        filled_qty=10,
        avg_fill_price=100.0,
        strategy_id="P01",
        market_state={"recent_pullback_low": 99.0},
    )
    return engine


def test_stop_set_on_entry() -> None:
    provider = _ExecProvider()
    engine = _open_trade(provider)
    trade = engine.get_trade("T-1")
    assert trade is not None
    assert trade.state == PositionLifecycleState.PROTECTED
    assert trade.stop_price == 99.0
    assert trade.initial_risk_R == 1.0


def test_break_even_activation() -> None:
    provider = _ExecProvider()
    engine = _open_trade(provider)
    intents = engine.evaluate_trade_management(trade_id="T-1", current_price=101.0, market_state={})
    trade = engine.get_trade("T-1")
    assert trade is not None
    assert trade.state == PositionLifecycleState.EXIT_PENDING
    assert intents and intents[0].metadata["requested_qty"] == 5


def test_trailing_updates_from_structure() -> None:
    provider = _ExecProvider()
    engine = _open_trade(provider)
    trade = engine.get_trade("T-1")
    assert trade is not None
    engine.record_exit_fill(
        trade_id="T-1",
        fill_price=101.0,
        fill_time="2026-04-16T09:35:00+00:00",
        actual_qty=5,
        reason="target_fill_broker",
    )
    trade = engine.get_trade("T-1")
    assert trade is not None
    trade.partial_exit_count = 1
    intents = engine.evaluate_trade_management(
        trade_id="T-1",
        current_price=101.4,
        market_state={"higher_low_1m": 101.5},
    )
    assert intents == []
    trade = engine.get_trade("T-1")
    assert trade is not None
    assert trade.state == PositionLifecycleState.TRAILING_ACTIVE
    assert trade.stop_price and trade.stop_price > 100.0


def test_partial_exit_execution_intent() -> None:
    provider = _ExecProvider()
    engine = _open_trade(provider)
    intents = engine.evaluate_trade_management(trade_id="T-1", current_price=101.0, market_state={})
    assert len(intents) == 1
    assert intents[0].metadata["action"] == "EXIT"
    assert intents[0].metadata["requested_qty"] == 5


def test_full_exit_lifecycle_on_stop_hit() -> None:
    provider = _ExecProvider()
    engine = _open_trade(provider)
    intents = engine.evaluate_trade_management(trade_id="T-1", current_price=98.9, market_state={})
    assert len(intents) == 1
    engine.record_exit_fill(
        trade_id="T-1",
        fill_price=98.9,
        fill_time="2026-04-16T09:36:00+00:00",
        actual_qty=10,
        reason="stop_fill_broker",
    )
    trade = engine.get_trade("T-1")
    assert trade is not None
    assert trade.state == PositionLifecycleState.EXITED


def test_time_based_exit() -> None:
    provider = _ExecProvider()
    engine = _open_trade(provider)
    trade = engine.get_trade("T-1")
    assert trade is not None
    trade.entry_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    intents = engine.evaluate_trade_management(
        trade_id="T-1",
        current_price=100.0,
        market_state={},
    )
    assert intents
    assert intents[0].metadata["exit_type"] == "TIME_EXIT"


def test_pnl_correctness_after_partials() -> None:
    provider = _ExecProvider()
    engine = _open_trade(provider)
    engine.record_exit_fill(
        trade_id="T-1",
        fill_price=101.0,
        fill_time="2026-04-16T09:35:00+00:00",
        actual_qty=5,
        reason="target_fill_broker",
    )
    engine.record_exit_fill(
        trade_id="T-1",
        fill_price=102.0,
        fill_time="2026-04-16T09:40:00+00:00",
        actual_qty=5,
        reason="trailing_fill_broker",
    )
    trade = engine.get_trade("T-1")
    assert trade is not None
    assert trade.realized_pnl == 15.0
    assert trade.avg_exit_price == 101.5
    assert trade.remaining_qty == 0
