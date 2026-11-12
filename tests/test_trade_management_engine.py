from datetime import datetime, timedelta, timezone
import inspect

import pytest

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
    assert position.partial_taken is False
    assert position.quantity == 100
    engine.on_exec_details(symbol="ABCD", shares=-50, price=10.5, exec_id="E-partial")
    assert position.partial_taken is True
    assert position.quantity == 50
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


def test_force_lifecycle_exit_after_five_minutes_overrides_other_conditions() -> None:
    engine = _engine_with_position()
    position = engine.snapshot_positions()["ABCD"]
    position.entry_timestamp = datetime.now(timezone.utc) - timedelta(seconds=301)

    intents = engine.evaluate_cycle({"ABCD": {"current_price": 10.2}})

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


def test_evaluate_cycle_skips_symbol_when_market_state_missing() -> None:
    engine = _engine_with_position()

    intents = engine.evaluate_cycle({})

    assert intents == []


def test_generic_management_layer_does_not_embed_ross_threshold_rules() -> None:
    source = inspect.getsource(TradeManagementEngine._evaluate_exit_rules)
    assert "NO_IMMEDIATE_FOLLOW_THROUGH" not in source
    assert "STALL_AT_LEVEL" not in source
    assert "MOMENTUM_WEAKNESS" not in source


@pytest.fixture
def first_retention_case():
    """Pure selected-policy facts; native ownership is proved by Core fixtures."""
    from src.config import config_resolver
    from src.strategies.common.candles.candle_types import Candle

    original = dict(config_resolver._CONFIG_OVERRIDES)
    config_resolver.set_config_overrides(dict(original, RUN_MODE="PAPER", RUN_MODE_EFFECTIVE="PAPER",
        RISK_PROFILE="SMALL", ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=4, ROSS_SYNTHETIC_UNIT_STOPS=True,
        ROSS_SYNTHETIC_UNIT_MANAGEMENT=True, ROSS_SYNTHETIC_BULL_COST_TIGHTENING=True,
        ROSS_SYNTHETIC_MICRO_COST_FAILURE=True, ROSS_SYNTHETIC_MICRO_COST_TIGHTENING=True))
    now = datetime(2026, 11, 12, 15, 0, 30, tzinfo=timezone.utc)
    metadata = {"canonical_result_index": 0, "source_metadata": {"synthetic": True},
        "trigger_level": 9.9, "stop_level": 9.5, "invalidation_level": 9.5,
        "execution_stream": {"execution_trigger_timeframe": "10s",
            "observed_at_utc": (now - timedelta(minutes=2)).isoformat()}}
    request = {"setup_family_id": "FIRST_PULLBACK", "selected_stop_units": True, "quantity": 4,
        "stop_loss_price": 9.5, "invalidation_level": 9.5, "take_profit_price": None,
        "management_session_plan": "RTH_OPEN", "setup_metadata": metadata}
    order = {"symbol": "ABCD", "request": request, "filled": 4, "requested": 4, "terminal": True,
        "protection_confirmed": True, "last_accounted_entry_fill_at": (now - timedelta(minutes=1)).isoformat(),
        "unit_profit_exit": {"status": "FILLED", "profile": "STANDALONE_ONE_SHARE_2R_COMPLETED_CLOSE_V1",
            "occurrence": metadata, "entry_fill_price": 10.01, "original_stop": 9.5, "milestone": 11.03,
            "owned_quantity": 4, "reserved_quantity": 2, "leg_ids": ["unit1", "unit2"],
            "accounted_fill_quantity": 2, "accounted_fill_notional": "22.06",
            "last_accounted_fill_at": (now - timedelta(seconds=30)).isoformat()}}
    bar = Candle(10.02, 10.05, 9.98, 10.04, 100, timestamp=now - timedelta(seconds=20))
    try:
        yield order, bar, now
    finally:
        config_resolver.set_config_overrides(original)


@pytest.mark.parametrize("change", [
    {"setup_family_id": "BULL_FLAG"}, {"setup_family_id": "MICRO_PULLBACK"},
    {"setup_family_id": "PREMARKET_HIGH_BREAK"}, {"setup_family_id": "UNKNOWN"},
    {"relationship_context": {"profile": "BULL_FLAG_MICRO_2R_V1", "action": "ENTRY"}},
    {"target_model": "BULL_FLAG_MICRO_2R_V1"}, {"take_profit_price": 11.03},
    {"selected_stop_units": False},
])
def test_first_original_stop_retention_has_only_existing_standalone_unit_scope(first_retention_case, change):
    from src.strategies.ross_momentum.strategy_policy import selected_first_original_stop_retention_profile
    order, _, _ = first_retention_case
    request = order["request"]
    assert selected_first_original_stop_retention_profile(request)
    assert selected_first_original_stop_retention_profile(dict(request, **change)) is None


def test_first_original_stop_retention_does_not_enable_unit_management(first_retention_case):
    from src.config import config_resolver
    from src.strategies.ross_momentum.strategy_policy import selected_first_original_stop_retention_profile
    order, _, _ = first_retention_case
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES, ROSS_SYNTHETIC_UNIT_MANAGEMENT=False,
        ROSS_SYNTHETIC_BULL_COST_TIGHTENING=False, ROSS_SYNTHETIC_MICRO_COST_FAILURE=False,
        ROSS_SYNTHETIC_MICRO_COST_TIGHTENING=False))
    assert selected_first_original_stop_retention_profile(order["request"]) is None


@pytest.mark.parametrize("close", [9.99, 10.01, 10.04])
def test_first_confirmed_partial_cannot_adopt_bull_or_micro_cost_actions(first_retention_case, close):
    from copy import deepcopy
    from dataclasses import replace
    from src.strategies.ross_momentum.strategy_policy import (
        selected_first_original_stop_retention_profile, selected_cost_tightening_profile,
        selected_micro_cost_failure_profile, standalone_cost_tightening_basis,
    )
    order, bar, now = first_retention_case
    bar = replace(bar, close=close)
    before = deepcopy(order)
    engine = TradeManagementEngine()
    arguments = dict(observed_at=now, session_plan=order["request"]["management_session_plan"], entry_fill_price=10.01)
    assert selected_first_original_stop_retention_profile(order["request"])
    assert selected_cost_tightening_profile(order["request"]) is None
    assert selected_micro_cost_failure_profile(order["request"]) is None
    assert standalone_cost_tightening_basis(order, 10.01) is None
    assert engine.evaluate_selected_micro_cost_failure(order, [bar], **arguments) is None
    assert engine.evaluate_selected_micro_cost_tightening(order, [bar], **arguments) is None
    assert engine.evaluate_selected_bull_cost_tightening(order, [bar], **arguments) is None
    assert order == before and engine.snapshot_positions() == {}


def test_first_retention_preserves_existing_completed_failure_and_project_2r(first_retention_case):
    from copy import deepcopy
    from dataclasses import replace
    from src.strategies.ross_momentum.strategy_policy import (
        CENTRAL_STANDALONE_FAILURE_PROFILE, STANDALONE_ONE_SHARE_PROFIT_PROFILE,
    )
    order, bar, now = first_retention_case
    before = deepcopy(order)
    engine = TradeManagementEngine()
    arguments = dict(observed_at=now, session_plan=order["request"]["management_session_plan"])
    assert engine.evaluate_selected_completed_failure(order, [bar], **arguments) is None
    failure = engine.evaluate_selected_completed_failure(order, [replace(bar, open=9.9, low=9.78, high=9.95, close=9.8)], **arguments)
    assert failure and failure["profile"] == CENTRAL_STANDALONE_FAILURE_PROFILE
    assert failure["selected_entry"] == 9.9 and failure["occurrence"] == order["request"]["setup_metadata"]
    entry = deepcopy(order)
    entry.pop("unit_profit_exit")
    profit = engine.evaluate_selected_completed_profit(entry, [replace(bar, open=11.01, low=11.0, high=11.04, close=11.03)],
        **arguments, entry_fill_price=10.01)
    assert profit and profit["profile"] == STANDALONE_ONE_SHARE_PROFIT_PROFILE
    assert (profit["entry_fill_price"], profit["original_stop"], profit["milestone"]) == (10.01, 9.5, 11.03)
    assert order == before and engine.snapshot_positions() == {}
