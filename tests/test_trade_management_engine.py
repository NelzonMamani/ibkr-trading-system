from datetime import datetime, timedelta, timezone

from src.execution.trade_management_engine import TradeManagementEngine


def _engine_with_position() -> TradeManagementEngine:
    engine = TradeManagementEngine(max_hold_time_seconds=60, fast_failure_seconds=20)
    engine.on_exec_details(symbol="ABCD", shares=100, price=10.0, exec_id="E1")
    return engine


def test_stop_loss_hit_triggers_full_sell() -> None:
    engine = _engine_with_position()

    intents = engine.evaluate_cycle({"ABCD": {"current_price": 9.98}})

    assert len(intents) == 1
    assert intents[0].direction == "SELL"
    assert intents[0].quantity == 100
    assert intents[0].rationale == "STOP_LOSS_HIT"
    assert intents[0].exit_type == "STOP"


def test_target_hit_takes_partial_and_moves_stop_to_breakeven() -> None:
    engine = _engine_with_position()

    intents = engine.evaluate_cycle({"ABCD": {"current_price": 10.5}})

    assert len(intents) == 1
    assert intents[0].quantity == 50
    assert intents[0].rationale == "TARGET_HIT"
    assert intents[0].exit_type == "TARGET"
    position = engine.snapshot_positions()["ABCD"]
    assert position.partial_taken is True
    assert position.stop_loss_price >= position.break_even_price


def test_weakness_exit_emits_momentum_weakness() -> None:
    engine = _engine_with_position()

    intents = engine.evaluate_cycle(
        {
            "ABCD": {
                "current_price": 10.05,
                "large_upper_wick": True,
                "green_volume_ratio": 1.0,
                "red_volume_ratio": 1.1,
            }
        }
    )

    assert len(intents) == 1
    assert intents[0].rationale == "MOMENTUM_WEAKNESS"
    assert intents[0].exit_type == "WEAKNESS"


def test_time_exit_when_max_hold_exceeded() -> None:
    engine = _engine_with_position()
    position = engine.snapshot_positions()["ABCD"]
    position.entry_timestamp = datetime.now(timezone.utc) - timedelta(seconds=120)

    intents = engine.evaluate_cycle({"ABCD": {"current_price": 10.1}})

    assert len(intents) == 1
    assert intents[0].rationale == "MAX_HOLD_TIME_EXCEEDED"
    assert intents[0].exit_type == "TIME"


def test_fast_failure_exit_when_no_follow_through() -> None:
    engine = _engine_with_position()
    position = engine.snapshot_positions()["ABCD"]
    position.entry_timestamp = datetime.now(timezone.utc) - timedelta(seconds=25)

    intents = engine.evaluate_cycle({"ABCD": {"current_price": 10.0}})

    assert len(intents) == 1
    assert intents[0].rationale == "NO_IMMEDIATE_FOLLOW_THROUGH"
    assert intents[0].exit_type == "FAST_FAILURE"


def test_stall_exit_has_priority_over_trailing_and_time() -> None:
    engine = _engine_with_position()
    position = engine.snapshot_positions()["ABCD"]
    position.partial_taken = True
    position.stop_loss_price = 9.9
    position.last_trail_price = 10.2
    position.entry_timestamp = datetime.now(timezone.utc) - timedelta(seconds=120)

    intents = engine.evaluate_cycle(
        {"ABCD": {"current_price": 10.25, "candles_since_new_high": 4}}
    )

    assert len(intents) == 1
    assert intents[0].rationale == "STALL_AT_LEVEL"
    assert intents[0].exit_type == "WEAKNESS"


def test_position_targets_initialized_on_open() -> None:
    engine = TradeManagementEngine()
    position = engine.on_exec_details(symbol="WXYZ", shares=100, price=2.3, exec_id="E2")

    assert position is not None
    assert position.first_target_price == 2.5
    assert position.second_target_price == 3.0
    assert position.target_type == "HALF_DOLLAR"


def test_no_duplicate_exits_while_pending() -> None:
    engine = _engine_with_position()

    first = engine.evaluate_cycle({"ABCD": {"current_price": 9.97}})
    second = engine.evaluate_cycle({"ABCD": {"current_price": 9.95}})

    assert len(first) == 1
    assert second == []


def test_upsert_broker_position_creates_managed_position() -> None:
    engine = TradeManagementEngine()
    position = engine.upsert_broker_position(symbol="ibm", quantity=25, avg_price=101.25)

    assert position is not None
    assert position.symbol == "IBM"
    assert position.quantity == 25
    assert position.entry_reason == "BROKER_POSITION_SYNC"
    assert position.strategy_name == "ROSS_MOMENTUM"
    assert position.break_even_price == 101.25
    assert position.exit_stage == "NONE"


def test_upsert_broker_position_updates_existing_state() -> None:
    engine = _engine_with_position()
    updated = engine.upsert_broker_position(symbol="ABCD", quantity=120, avg_price=10.4, source="IBKR_POSITION_SYNC")

    assert updated is not None
    assert updated.quantity == 120
    assert updated.entry_price == 10.4
    assert updated.break_even_price == 10.4
