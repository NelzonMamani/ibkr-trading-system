from src.execution.trade_management_engine import TradeManagementEngine


def _engine_with_position() -> TradeManagementEngine:
    engine = TradeManagementEngine()
    engine.on_exec_details(symbol="ABCD", shares=100, price=10.0, exec_id="E1")
    return engine


def test_retrace_above_fifty_percent_triggers_exit() -> None:
    engine = _engine_with_position()

    intents = engine.evaluate_cycle(
        {
            "ABCD": {
                "current_price": 11.0,
                "green_volume_ratio": 1.0,
                "red_volume_ratio": 1.0,
            }
        }
    )
    assert intents == []

    intents = engine.evaluate_cycle(
        {
            "ABCD": {
                "current_price": 10.4,
                "green_volume_ratio": 1.0,
                "red_volume_ratio": 1.0,
            }
        }
    )
    assert len(intents) == 1
    assert intents[0].action == "EXIT"
    assert intents[0].reason == "RETRACE_FAILURE"


def test_red_volume_ratio_triggers_exit() -> None:
    engine = _engine_with_position()

    intents = engine.evaluate_cycle(
        {
            "ABCD": {
                "current_price": 10.1,
                "green_volume_ratio": 1.0,
                "red_volume_ratio": 1.6,
            }
        }
    )

    assert len(intents) == 1
    assert intents[0].action == "EXIT"
    assert intents[0].reason == "RED_VOLUME_EXIT"


def test_trailing_stop_updates_from_new_higher_low() -> None:
    engine = _engine_with_position()

    intents = engine.evaluate_cycle(
        {
            "ABCD": {
                "current_price": 10.2,
                "green_volume_ratio": 1.0,
                "red_volume_ratio": 1.0,
                "last_higher_low": 10.15,
                "trail_buffer": 0.05,
            }
        }
    )

    assert intents == []
    position = engine.snapshot_positions()["ABCD"]
    assert position.trailing_stop == 10.10


def test_scale_only_when_green_volume_and_structure_valid() -> None:
    engine = _engine_with_position()

    blocked = engine.evaluate_cycle(
        {
            "ABCD": {
                "current_price": 10.3,
                "green_volume_ratio": 1.6,
                "red_volume_ratio": 1.0,
                "structure_intact": True,
                "near_resistance": True,
            }
        }
    )
    assert blocked == []

    allowed = engine.evaluate_cycle(
        {
            "ABCD": {
                "current_price": 10.35,
                "green_volume_ratio": 1.7,
                "red_volume_ratio": 1.0,
                "structure_intact": True,
                "near_resistance": False,
            }
        }
    )
    assert len(allowed) == 1
    assert allowed[0].action == "ADD"


def test_no_duplicate_exits_while_pending() -> None:
    engine = _engine_with_position()

    first = engine.evaluate_cycle(
        {
            "ABCD": {
                "current_price": 10.0,
                "green_volume_ratio": 1.0,
                "red_volume_ratio": 1.6,
            }
        }
    )
    second = engine.evaluate_cycle(
        {
            "ABCD": {
                "current_price": 9.9,
                "green_volume_ratio": 1.0,
                "red_volume_ratio": 1.7,
            }
        }
    )

    assert len(first) == 1
    assert second == []
