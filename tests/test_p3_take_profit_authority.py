from __future__ import annotations

from src.core.engines.trade_lifecycle_engine import LifecycleEvent, TradeLifecycleEngine
from src.core.take_profit_authority import TakeProfitAuthority, TakeProfitTargetType
from src.execution.post_fill_lifecycle_engine import PostFillLifecycleEngine, PositionLifecycleState
from src.risk.risk_engine import RiskEngine


class _ProviderStub:
    def __init__(self) -> None:
        self.stop_calls: list[dict] = []
        self.target_calls: list[dict] = []
        self.modify_calls: list[dict] = []
        self.cancel_calls: list[dict] = []

    def place_stop_order(self, **kwargs):
        self.stop_calls.append(dict(kwargs))
        return {"broker_order_id": "STOP-1", "status": "Submitted"}

    def place_target_order(self, **kwargs):
        self.target_calls.append(dict(kwargs))
        return {"broker_order_id": "TGT-1", "status": "Submitted"}

    def modify_stop_order(self, **kwargs):
        self.modify_calls.append(dict(kwargs))
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Submitted"}

    def cancel_order(self, **kwargs):
        self.cancel_calls.append(dict(kwargs))
        return {"broker_order_id": kwargs["broker_order_id"], "status": "Cancelled"}


def _event(event_id: str, trade_id: str, event_type: str, qty: int, price: float) -> LifecycleEvent:
    return LifecycleEvent(
        event_id=event_id,
        lifecycle_trade_id=trade_id,
        symbol="AAPL",
        side="LONG",
        event_type=event_type,
        quantity=qty,
        price=price,
        timestamp=f"2026-01-01T00:00:0{event_id[-1]}+00:00",
        order_id=f"O-{event_id}",
        execution_id=f"E-{event_id}",
        source="broker_callback",
    )


def test_authority_creates_long_r_multiple_and_blocks_invalid_or_duplicate_targets() -> None:
    authority = TakeProfitAuthority()

    decision = authority.create_r_multiple_target(
        trade_id="T-1",
        symbol="AAPL",
        side="LONG",
        entry_price=100.0,
        stop_loss_price=99.0,
        live_position_quantity=10,
        source_strategy="ross_momentum",
        r_multiple=2.0,
        fraction=0.5,
        target_type=TakeProfitTargetType.PARTIAL_SCALE_OUT,
    )

    assert decision.accepted is True
    assert decision.target_price == 102.0
    assert decision.target_quantity == 5
    assert decision.lifecycle_event == "TAKE_PROFIT_CREATED"

    duplicate = authority.create_fixed_price_target(
        trade_id="T-1",
        symbol="AAPL",
        side="LONG",
        target_price=103.0,
        live_position_quantity=10,
        source_strategy="ross_momentum",
    )
    assert duplicate.accepted is False
    assert duplicate.reason_code == "DUPLICATE_TARGET_SLICE"

    no_position = authority.create_fixed_price_target(
        trade_id="T-2",
        symbol="MSFT",
        side="LONG",
        target_price=51.0,
        live_position_quantity=0,
        source_strategy="ross_momentum",
    )
    assert no_position.reason_code == "NO_LIVE_POSITION"

    exceeds_position = authority.create_fixed_price_target(
        trade_id="T-3",
        symbol="NVDA",
        side="LONG",
        target_price=151.0,
        live_position_quantity=4,
        source_strategy="ross_momentum",
        quantity=5,
    )
    assert exceeds_position.reason_code == "TARGET_QTY_EXCEEDS_POSITION"


def test_post_fill_partial_target_fill_updates_remaining_quantity_stop_and_attribution() -> None:
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=provider)
    engine.activate_trade_management_after_fill(
        trade_id="T-P3",
        symbol="AAPL",
        side="LONG",
        filled_qty=10,
        avg_fill_price=100.0,
        strategy_id="ross_momentum",
    )

    assert provider.target_calls[0]["quantity"] == 5

    result = engine.handle_broker_callback(
        {
            "event_type": "execDetails",
            "order_id": "TGT-1",
            "shares": 5,
            "price": 102.0,
            "time": "2026-01-01T10:00:00+00:00",
        }
    )

    trade = engine.get_trade("T-P3")
    assert result["handled"] is True
    assert result["partial"] is True
    assert trade is not None
    assert trade.filled_qty == 5
    assert trade.exited_qty == 5
    assert trade.realized_pnl_by_exit_reason["TAKE_PROFIT"] == 10.0
    assert trade.stop is not None
    assert trade.stop.quantity == 5
    assert trade.stop.trigger_price == 100.0
    assert provider.modify_calls[-1]["quantity"] == 5
    assert {event["event_type"] for event in trade.take_profit_events} >= {
        "TAKE_PROFIT_CREATED",
        "TAKE_PROFIT_SUBMITTED",
        "TAKE_PROFIT_PARTIALLY_FILLED",
    }


def test_target_cancel_and_reject_do_not_close_position() -> None:
    cancel_engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=_ProviderStub())
    cancel_engine.activate_trade_management_after_fill(
        trade_id="T-CANCEL",
        symbol="AAPL",
        side="LONG",
        filled_qty=4,
        avg_fill_price=100.0,
        strategy_id="ross_momentum",
    )
    cancel_result = cancel_engine.handle_broker_callback(
        {"event_type": "orderStatus", "order_id": "TGT-1", "status": "Cancelled"}
    )
    cancel_trade = cancel_engine.get_trade("T-CANCEL")
    assert cancel_result["handled"] is True
    assert cancel_trade is not None
    assert cancel_trade.state != PositionLifecycleState.EXITED
    assert cancel_trade.filled_qty == 4
    assert cancel_trade.target is not None
    assert cancel_trade.target.status == "CANCELLED"

    reject_engine = PostFillLifecycleEngine(run_mode="PAPER", execution_provider=_ProviderStub())
    reject_engine.activate_trade_management_after_fill(
        trade_id="T-REJECT",
        symbol="MSFT",
        side="LONG",
        filled_qty=4,
        avg_fill_price=100.0,
        strategy_id="ross_momentum",
    )
    reject_result = reject_engine.handle_broker_callback(
        {"event_type": "orderStatus", "order_id": "TGT-1", "status": "Rejected"}
    )
    reject_trade = reject_engine.get_trade("T-REJECT")
    assert reject_result["handled"] is True
    assert reject_trade is not None
    assert reject_trade.state != PositionLifecycleState.EXITED
    assert reject_trade.filled_qty == 4
    assert reject_trade.target is not None
    assert reject_trade.target.status == "REJECTED"


def test_read_only_cannot_submit_target_orders() -> None:
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine(run_mode="READ_ONLY", execution_provider=provider)

    result = engine.activate_trade_management_after_fill(
        trade_id="T-READONLY",
        symbol="AAPL",
        side="LONG",
        filled_qty=2,
        avg_fill_price=100.0,
        strategy_id="ross_momentum",
    )

    assert result["success"] is False
    assert provider.target_calls == []
    assert provider.stop_calls == []


def test_risk_validates_take_profit_quantity_and_degraded_state() -> None:
    engine = RiskEngine()

    assert engine.validate_take_profit_order(
        symbol="AAPL",
        requested_quantity=3,
        live_position_quantity=5,
    ).accepted is True
    assert engine.validate_take_profit_order(
        symbol="AAPL",
        requested_quantity=6,
        live_position_quantity=5,
    ).reason == "TARGET_QTY_EXCEEDS_POSITION"
    assert engine.validate_take_profit_order(
        symbol="AAPL",
        requested_quantity=1,
        live_position_quantity=5,
        broker_position_degraded=True,
    ).reason == "TARGET_STATE_DEGRADED"


def test_lifecycle_records_take_profit_audit_events_and_pnl_attribution() -> None:
    engine = TradeLifecycleEngine()
    engine.apply_event(_event("1", "T-LIFE", "ENTRY_FILL", 10, 100.0), strategy_name="ross_momentum")
    engine.apply_event(_event("2", "T-LIFE", "TAKE_PROFIT_CREATED", 5, 102.0))

    trade = engine.get_trade("T-LIFE")
    assert trade is not None
    assert trade.quantity_open == 10
    assert trade.target_price == 102.0
    assert trade.take_profit_events[-1]["event_type"] == "TAKE_PROFIT_CREATED"

    engine.apply_event(_event("3", "T-LIFE", "TAKE_PROFIT_PARTIALLY_FILLED", 5, 102.0))
    trade = engine.get_trade("T-LIFE")
    assert trade is not None
    assert trade.quantity_open == 5
    assert trade.quantity_closed == 5
    assert trade.status == "PARTIALLY_CLOSED"
    assert trade.realized_pnl_by_exit_reason["TAKE_PROFIT"] == 10.0

    engine.apply_event(_event("4", "T-LIFE", "TAKE_PROFIT_CANCELLED", 0, 0.0))
    trade = engine.get_trade("T-LIFE")
    assert trade is not None
    assert trade.quantity_open == 5
    assert trade.take_profit_events[-1]["event_type"] == "TAKE_PROFIT_CANCELLED"
