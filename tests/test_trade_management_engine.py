from datetime import datetime, timedelta, timezone

from src.execution.trade_management_engine import TradeManagementEngine


def _engine_with_position() -> TradeManagementEngine:
    engine = TradeManagementEngine(quick_profit_threshold=0.1, max_hold_time_seconds=60)
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


def test_quick_profit_takes_partial_and_moves_stop_to_breakeven() -> None:
    engine = _engine_with_position()

    intents = engine.evaluate_cycle({"ABCD": {"current_price": 10.2}})

    assert len(intents) == 1
    assert intents[0].quantity == 50
    assert intents[0].rationale == "QUICK_PROFIT_TAKEN"
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

    intents = engine.evaluate_cycle({"ABCD": {"current_price": 10.01}})

    assert len(intents) == 1
    assert intents[0].rationale == "MAX_HOLD_TIME_EXCEEDED"
    assert intents[0].exit_type == "TIME"


def test_no_duplicate_exits_while_pending() -> None:
    engine = _engine_with_position()

    first = engine.evaluate_cycle({"ABCD": {"current_price": 9.97}})
    second = engine.evaluate_cycle({"ABCD": {"current_price": 9.95}})

    assert len(first) == 1
    assert second == []
