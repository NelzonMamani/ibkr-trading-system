from __future__ import annotations

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.core.engines.trade_lifecycle_engine import LifecycleEvent, TradeLifecycleEngine
from src.core.portfolio.broker_position_adapter import BrokerPositionSnapshot
from src.core.position_lifecycle_engine import (
    LifecycleIntent,
    PositionLifecycle,
    PositionLifecycleEngine,
    PositionState,
)
from src.storage.storage_engine import StorageEngine


def _event(
    event_id: str,
    trade_id: str,
    event_type: str,
    qty: int,
    *,
    symbol: str = "AAPL",
    price: float = 10.0,
) -> LifecycleEvent:
    return LifecycleEvent(
        event_id=event_id,
        lifecycle_trade_id=trade_id,
        symbol=symbol,
        side="LONG",
        event_type=event_type,
        quantity=qty,
        price=price,
        timestamp=f"2026-01-01T00:00:0{event_id[-1]}+00:00",
        order_id=f"O-{event_id}",
        execution_id=f"E-{event_id}",
    )


def test_p1_position_ownership_persists_across_transition_replay(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "p1_lifecycle.db"
    monkeypatch.setenv("PERSISTENCE_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("PERSISTENCE_ENABLED", "1")
    monkeypatch.setenv("PERSISTENCE_BACKEND", "sqlite")
    set_config_overrides({})
    storage = StorageEngine()
    try:
        engine = PositionLifecycleEngine(storage_engine=storage)
        position = PositionLifecycle(symbol="AAPL", trader_type="SYSTEM")

        result = engine.apply_intent(
            position,
            LifecycleIntent.OPEN,
            requested_quantity=100,
            run_mode=RunMode.PAPER,
            reason="P1 entry",
            strategy_owner="ross_momentum",
            entry_source="strategy_signal",
            entry_intent_id="intent-1",
            entry_order_id="order-1",
        )

        assert result.accepted is True
        assert position.state == PositionState.OPEN
        assert position.current_size == 100
        assert position.remaining_size == 0

        rows = storage.fetch_lifecycle_transitions(run_id=storage.run_id)
        replayed = PositionLifecycleEngine.replay_transitions(rows)[("AAPL", "SYSTEM")]
        assert replayed.strategy_owner == "ross_momentum"
        assert replayed.entry_source == "strategy_signal"
        assert replayed.entry_intent_id == "intent-1"
        assert replayed.entry_order_id == "order-1"
        assert replayed.state == PositionState.OPEN
        assert replayed.quantity == 100
    finally:
        storage.shutdown()
        set_config_overrides({})


def test_p1_partial_fill_lifecycle_and_no_duplicate_position() -> None:
    position_engine = PositionLifecycleEngine()
    position = PositionLifecycle(symbol="AAPL", trader_type="SYSTEM")
    partial = position_engine.apply_intent(
        position,
        LifecycleIntent.OPEN,
        requested_quantity=100,
        run_mode=RunMode.LIVE,
        risk_approved=True,
        reason="broker partial",
        filled_quantity_override=37,
        fill_status_override="PARTIAL",
        strategy_owner="ross_momentum",
        entry_intent_id="intent-partial",
        entry_order_id="order-partial",
    )
    assert partial.accepted is True
    assert position.state == PositionState.PARTIALLY_FILLED
    assert position.current_size == 37
    assert position.remaining_size == 63

    trade_engine = TradeLifecycleEngine()
    trade_engine.apply_event(_event("1", "T1", "ENTRY_FILL", 37), strategy_name="ross_momentum")
    trade_engine.apply_event(_event("2", "T2", "ENTRY_FILL", 63), strategy_name="ross_momentum")
    open_trades = trade_engine.open_trades()
    assert len(open_trades) == 1
    assert open_trades[0].quantity_open == 100
    assert open_trades[0].strategy_name == "ross_momentum"


def test_p1_exit_ownership_conflict_blocks_other_strategy() -> None:
    engine = TradeLifecycleEngine()
    engine.apply_event(_event("1", "ROSS-1", "ENTRY_FILL", 10), strategy_name="ross_momentum")

    conflict = engine.validate_exit_authority(
        symbol="AAPL",
        strategy_name="statistical_intraday_momentum",
    )
    assert conflict["allowed"] is False
    assert conflict["reason_code"] == "OWNERSHIP_CONFLICT"
    assert conflict["owner_strategy"] == "ross_momentum"

    owner = engine.validate_exit_authority(symbol="AAPL", strategy_name="ross_momentum")
    assert owner["allowed"] is True
    assert owner["reason_code"] == "OWNER_MATCH"


def test_p1_broker_reconciliation_classifications_and_recovered_flat() -> None:
    engine = TradeLifecycleEngine()
    engine.apply_event(_event("1", "T1", "ENTRY_FILL", 10), strategy_name="ross_momentum")

    match = engine.reconcile_with_broker_snapshot(
        [BrokerPositionSnapshot(symbol="AAPL", quantity=10, avg_entry_price=10.0, timestamp="2026-01-01T00:00:00+00:00")]
    )
    assert match[0]["classification"] == "MATCH"

    mismatch = engine.reconcile_with_broker_snapshot(
        [BrokerPositionSnapshot(symbol="AAPL", quantity=8, avg_entry_price=10.0, timestamp="2026-01-01T00:00:00+00:00")]
    )
    assert mismatch[0]["classification"] == "MISMATCH"

    recovered = engine.apply_reconciliation_snapshot(symbol="AAPL", runtime_quantity=0, runtime_avg_entry=10.0)
    assert recovered["classification"] == "RECOVERED"
    assert engine.find_open_trade_id_for_symbol("AAPL") is None

    external = engine.reconcile_with_broker_snapshot(
        [BrokerPositionSnapshot(symbol="MSFT", quantity=5, avg_entry_price=20.0, timestamp="2026-01-01T00:00:00+00:00")]
    )
    assert external[0]["classification"] == "EXTERNAL"


def test_p1_orphan_classification_for_duplicate_lifecycle_open() -> None:
    engine = TradeLifecycleEngine()
    engine.apply_event(_event("1", "T1", "ENTRY_FILL", 10, symbol="AAPL"), strategy_name="ross_momentum")
    engine.apply_event(_event("2", "T2", "ENTRY_FILL", 5, symbol="MSFT"), strategy_name="ross_momentum")
    recovered = engine.reconcile_with_broker_snapshot(
        [BrokerPositionSnapshot(symbol="MSFT", quantity=0, avg_entry_price=0.0, timestamp="2026-01-01T00:00:00+00:00")]
    )
    assert recovered[0]["classification"] == "ORPHAN"
    assert "RECOVERED" in recovered[0]["details_json"]
    assert engine.find_open_trade_id_for_symbol("MSFT") is None
