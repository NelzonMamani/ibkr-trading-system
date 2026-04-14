from datetime import datetime, timedelta, timezone
import inspect

from src.strategies.ross_momentum.exit_intelligence import ExitDecision
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
    assert intents[0].rationale == "STOP_LOSS_BREAK"
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

    intents = engine.evaluate_cycle({"ABCD": {"current_price": 10.0}})

    assert len(intents) == 1
    assert intents[0].rationale == "TIME_STOP"
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


def test_exit_decision_source_is_strategy_owned_component() -> None:
    class StubExitIntelligence:
        def __init__(self) -> None:
            self.calls = 0

        def evaluate(self, **_: object) -> ExitDecision:
            self.calls += 1
            return ExitDecision(action="EXIT_MARKET", reason="STOP_LOSS_HIT")

    stub = StubExitIntelligence()
    engine = TradeManagementEngine(exit_intelligence=stub)  # type: ignore[arg-type]
    engine.on_exec_details(symbol="ABCD", shares=10, price=10.0, exec_id="E1")

    intents = engine.evaluate_cycle({"ABCD": {"current_price": 10.1}})

    assert stub.calls == 1
    assert len(intents) == 1
    assert intents[0].rationale == "STOP_LOSS_HIT"


def test_move_stop_decision_updates_stop_without_order_intent() -> None:
    class StubExitIntelligence:
        def evaluate(self, **_: object) -> ExitDecision:
            return ExitDecision(action="MOVE_STOP", reason="PROTECT_BREAK_EVEN", new_stop_price=10.0)

    engine = TradeManagementEngine(exit_intelligence=StubExitIntelligence())  # type: ignore[arg-type]
    engine.on_exec_details(symbol="ABCD", shares=10, price=10.0, exec_id="E1")
    position = engine.snapshot_positions()["ABCD"]
    position.stop_loss_price = 9.95

    intents = engine.evaluate_cycle({"ABCD": {"current_price": 10.05}})

    assert intents == []
    assert engine.snapshot_positions()["ABCD"].stop_loss_price == 10.0


def test_activate_trailing_decision_is_stateful_and_idempotent() -> None:
    class StubExitIntelligence:
        def __init__(self) -> None:
            self.calls = 0

        def evaluate(self, **_: object) -> ExitDecision:
            self.calls += 1
            return ExitDecision(action="ACTIVATE_TRAILING", reason="TRAILING_ARMED_AT_KEY_LEVEL")

    stub = StubExitIntelligence()
    engine = TradeManagementEngine(exit_intelligence=stub)  # type: ignore[arg-type]
    engine.on_exec_details(symbol="ABCD", shares=10, price=10.0, exec_id="E1")

    first = engine.evaluate_cycle({"ABCD": {"current_price": 10.2}})
    second = engine.evaluate_cycle({"ABCD": {"current_price": 10.25}})

    assert first == []
    assert second == []
    assert engine.snapshot_positions()["ABCD"].trailing_active is True


def test_exit_intelligence_can_be_disabled_via_env(monkeypatch) -> None:
    monkeypatch.setenv("TRADE_MGMT_EXIT_INTELLIGENCE_ENABLED", "0")
    engine = _engine_with_position()

    intents = engine.evaluate_cycle({"ABCD": {"current_price": 9.98}})

    assert intents == []


def test_generic_management_layer_does_not_embed_ross_threshold_rules() -> None:
    source = inspect.getsource(TradeManagementEngine._evaluate_exit_rules)
    assert "NO_IMMEDIATE_FOLLOW_THROUGH" not in source
    assert "STALL_AT_LEVEL" not in source
    assert "MOMENTUM_WEAKNESS" not in source
