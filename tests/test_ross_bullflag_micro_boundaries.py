"""Offline boundary regressions; no broker or natural-opportunity acceptance."""
from types import SimpleNamespace
import pytest
from src.core.engines.execution_mode_engine import ExecutionModeEngine
from src.execution.execution_engine import ExecutionEngine
from src.execution.post_fill_lifecycle_engine import PostFillLifecycleEngine

@pytest.mark.parametrize("session,rvol", [("AH", None), ("UNKNOWN", 3), ("", 3), ("RTH_OPEN", None)])
def test_ross_entry_cannot_gain_permission_from_incomplete_context(session, rvol):
    intent = SimpleNamespace(strategy_name="ROSS_MOMENTUM", action="ENTRY", execution_refinement_mode="NONE")
    result = ExecutionModeEngine().apply(intent, SimpleNamespace(session=session, rvol=rvol, spread=0.02))
    assert result.execution_mode == "REJECTED"


def test_ross_raw_add_cannot_synthesize_risk_approval():
    engine = SimpleNamespace(current_tick=0, price_feed=SimpleNamespace(price_for=lambda *args: 10))
    intent = SimpleNamespace(action="ADD", symbol="OFFLINE", quantity=1, strategy_name="ROSS_MOMENTUM", reason="fixture")
    assert ExecutionEngine._risk_decision_from_intent(engine, intent) is None


def test_selected_stop_is_used_by_post_fill_owner():
    engine = PostFillLifecycleEngine("SIM")
    result = engine.activate_trade_management_after_fill(
        trade_id="offline-structural", symbol="OFFLINE", side="LONG", filled_qty=2,
        avg_fill_price=10, strategy_id="ROSS_MOMENTUM", stop_loss_price=9.6,
        take_profit_price=None, preserve_selected_protection=True, target_model="Measured move")
    assert result["success"]
    trade = engine.snapshot()["offline-structural"]
    assert trade["stop"]["trigger_price"] == 9.6
    assert trade["target"] is None
    assert trade["target_model"] == "Measured move"


def test_canonical_owners_preserve_compatibility_and_contrasting_profiles():
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    from src.setup_engine.setup_families.micro_pullback import MicroPullbackPattern
    from src.setup_engine.setup_families import momentum
    from src.strategies.ross_momentum.patterns import momentum_patterns
    from src.strategies.common.patterns.pattern_micro_pullback import detect_micro_pullback
    from test_micro_pullback_execution_refinement import _inputs, _valid_candles
    assert momentum.BullFlagPattern is BullFlagPattern is momentum_patterns.BullFlagPattern
    assert momentum.MicroPullbackPattern is MicroPullbackPattern is momentum_patterns.MicroPullbackPattern
    inputs = _inputs(candles=_valid_candles())
    ready = MicroPullbackPattern().evaluate_readiness(inputs)
    assert ready == detect_micro_pullback(inputs)
    assert ready.detected
    # Existing readiness does not require the canonical continuation close.
    assert MicroPullbackPattern().evaluate(inputs).detected is False


def test_bull_flag_parent_can_arm_without_a_breakout_and_cannot_emit():
    from dataclasses import replace
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    from src.strategies.ross_momentum.patterns.setup_fidelity import is_tradeable_entry_candidate
    from test_bull_flag_pipeline_end_to_end import _inputs
    inputs = _inputs()
    armed = BullFlagPattern().evaluate_formation(replace(inputs, candles=inputs.candles[:-1]))
    assert armed.detected
    assert armed.setup_metadata["parent_state"] == "ARMED"
    assert armed.non_entry_signal
    assert not is_tradeable_entry_candidate(armed)[0]
    assert BullFlagPattern().evaluate(inputs).detected
    # No timestamp can be invented for this legacy untimed fixture.
    assert armed.setup_metadata["origin_timestamp"] is None


@pytest.mark.parametrize("quantity,target", [(1, None), (3, 11.0), (2, 9.0)])
def test_broker_double_protection_uses_filled_exposure_and_selected_stop(quantity, target):
    class BrokerDouble:
        def __init__(self): self.stops = []; self.targets = []
        def place_stop_order(self, **kwargs):
            self.stops.append(kwargs); return {"broker_order_id": "offline-stop", "status": "Submitted"}
        def place_target_order(self, **kwargs):
            self.targets.append(kwargs); return {"broker_order_id": "offline-target", "status": "Submitted"}
    broker = BrokerDouble()
    lifecycle = PostFillLifecycleEngine("PAPER", execution_provider=broker)
    result = lifecycle.activate_trade_management_after_fill(
        trade_id="offline-partial", symbol="OFFLINE", side="LONG", filled_qty=quantity,
        intended_qty=10, avg_fill_price=10, strategy_id="ROSS_MOMENTUM",
        stop_loss_price=9.6, take_profit_price=target, preserve_selected_protection=True)
    assert result["success"]
    assert broker.stops[0]["quantity"] == quantity
    assert broker.stops[0]["stop_price"] == 9.6
    assert len(broker.targets) == (1 if target == 11 else 0)
    if broker.targets: assert broker.targets[0]["quantity"] == quantity


def test_fill_handoff_preserves_selected_stop_and_setup_without_inventing_target():
    from src.core.orchestrator import CoreOrchestrator
    from src.execution.trade_management_engine import TradeManagementEngine
    manager = TradeManagementEngine()
    harness = SimpleNamespace(trade_management_engine=manager)
    fill = SimpleNamespace(symbol="OFFLINE", filled_quantity=1, average_fill_price=10,
        execution_id="fill-a", direction="BUY", strategy_name="ROSS_MOMENTUM",
        setup_family_id="BULL_FLAG", stop_loss_price=9.6, take_profit_price=None,
        target_model="Measured move")
    CoreOrchestrator._apply_execution_results_to_trade_management(harness, [fill, fill])
    position = manager.snapshot_positions()["OFFLINE"]
    assert position.quantity == 1
    assert position.setup_family == "BULL_FLAG"
    assert position.stop_loss_price == 9.6
    assert position.first_target_price is None
    assert position.target_type == "DESCRIPTIVE_ONLY"
    assert position.target_model == "Measured move"
    ack = SimpleNamespace(**{**vars(fill), "filled_quantity": 0, "execution_id": "ack"})
    CoreOrchestrator._apply_execution_results_to_trade_management(harness, [ack])
    assert position.quantity == 1


@pytest.mark.parametrize("session", ["AH", "UNKNOWN"])
def test_ross_protective_exit_is_not_an_entry_permission(session):
    intent = SimpleNamespace(strategy_name="ROSS_MOMENTUM", action="EXIT")
    assert ExecutionModeEngine().apply(intent, SimpleNamespace(session=session, rvol=None, spread=None)) is intent
    assert not hasattr(intent, "execution_block_reason")


def test_failed_broker_stop_update_does_not_advance_protection_truth():
    from test_post_fill_lifecycle_engine_v1 import _ProviderStub
    provider = _ProviderStub()
    engine = PostFillLifecycleEngine("PAPER", execution_provider=provider)
    engine.activate_trade_management_after_fill(trade_id="offline-stop-failure", symbol="OFFLINE",
        side="LONG", filled_qty=2, avg_fill_price=10, strategy_id="ROSS_MOMENTUM",
        stop_loss_price=9.6, preserve_selected_protection=True)
    provider.fail_stop_modifications = True
    with pytest.raises(RuntimeError):
        engine.replace_stop(trade_id="offline-stop-failure", requested_by_strategy="ROSS_MOMENTUM", new_stop_price=9.8)
    assert engine.get_trade("offline-stop-failure").stop.trigger_price == 9.6


def test_proposed_partial_does_not_count_as_a_fill():
    from src.execution.trade_management_engine import TradeManagementEngine
    from src.strategies.ross_momentum.exit_intelligence import ExitDecision
    manager = TradeManagementEngine()
    position = manager.on_exec_details(symbol="OFFLINE", shares=4, price=10, exec_id="buy",
        strategy_name="ROSS_MOMENTUM", setup_family="BULL_FLAG", stop_loss_price=9.6)
    position.current_price = 10.5
    intent = manager._apply_exit_decision(position, ExitDecision(action="SCALE_OUT", reason="fixture", scale_quantity=2))
    assert intent.quantity == 2
    assert position.quantity == 4
    assert position.partial_taken is False
    assert position.stop_loss_price == 9.6
    manager.on_exec_details(symbol="OFFLINE", shares=-2, price=10.5, exec_id="sell")
    assert position.quantity == 2
    assert position.partial_taken is True


def test_real_bull_flag_production_intent_reaches_actual_readonly_risk(monkeypatch, tmp_path):
    from dataclasses import replace
    from test_pr1082_trigger_to_intent_terminal_semantics import _base_strategy, _candles, _watchlist_row, _snapshot
    from test_bull_flag_pipeline_end_to_end import _inputs
    from src.config.config_resolver import set_config_overrides
    from src.config.runtime_config import RunMode
    from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    from src.risk.risk_engine import RiskEngine
    from datetime import datetime, timezone
    from src.strategies.ross_momentum.patterns import pattern_trace
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return cls(2026, 9, 16, 14, 35, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(pattern_trace, "datetime", Clock)
    set_config_overrides({"RUN_MODE":"READ_ONLY", "RUN_MODE_EFFECTIVE":"READ_ONLY", "EXECUTION_ENABLED":False})
    try:
        strategy = _base_strategy(monkeypatch, tmp_path, state="ready")
        registry = RossPatternRegistry(); registry._patterns = [BullFlagPattern()]
        strategy._pattern_registry = registry
        primary_rows = [(10,10.02,9.98,10,1000)]*41 + [(c.open,c.high,c.low,c.close,c.volume) for c in _inputs().candles]
        streams = {"1m":_candles(primary_rows), "5m":_candles(primary_rows,step_seconds=300),
            "10s":_candles([(10.7,10.75,10.65,10.72,100)]*29+[(10.72,10.9,10.7,10.88,200)],step_seconds=10)}
        monkeypatch.setattr(pattern_trace,"get_intraday_bars",lambda *,timeframe="1m",**kw:streams[timeframe])
        row = {**_watchlist_row(), "last_price":10.88,"bid":10.87,"ask":10.89}
        snapshot = replace(_snapshot(), last=10.88,bid=10.87,ask=10.89)
        intents = strategy.process_watchlist(watchlist=[row],snapshots={"UPC":snapshot},
            session_label="RTH_OPEN",session_phase="RTH_OPEN",timestamp_utc="offline-bull-route",mode=RunMode.READ_ONLY)
        assert len(intents)==1, strategy.last_symbol_terminal_outcomes
        assert intents[0].setup_family_id=="BULL_FLAG"
        assert intents[0].target_model=="Measured move"
        decision=RiskEngine().evaluate_trade_intent(intents[0])
        assert not decision.allowed
        assert decision.execution_blocked
        assert decision.target_model == intents[0].target_model
        assert decision.setup_family_id == intents[0].setup_family_id
        assert decision.trigger_id == intents[0].trigger_id
    finally:
        set_config_overrides(None)


@pytest.mark.parametrize("rvol,spread", [(float("nan"),.02),(2,float("inf")),("bad",.02),(2,-.1)])
def test_ross_invalid_execution_context_fails_closed(rvol, spread):
    intent=SimpleNamespace(strategy_name="ROSS_MOMENTUM",action="ENTRY")
    result=ExecutionModeEngine().apply(intent,SimpleNamespace(session="RTH_OPEN",rvol=rvol,spread=spread))
    assert result.execution_mode=="REJECTED"


def test_formation_is_snapshot_pure_and_host_timezone_independent(monkeypatch):
    from dataclasses import replace
    from datetime import datetime, timezone, timedelta
    from test_bull_flag_pipeline_end_to_end import _inputs
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
    inputs=_inputs();start=datetime(2026,10,6,13,30,tzinfo=timezone.utc)
    inputs=replace(inputs,candles=[replace(c,timestamp=start+timedelta(minutes=i)) for i,c in enumerate(inputs.candles[:-1])])
    pattern=BullFlagPattern()
    monkeypatch.setenv("TZ","Pacific/Auckland");a=pattern.evaluate_formation(inputs)
    monkeypatch.setenv("TZ","America/New_York");b=pattern.evaluate_formation(inputs)
    other=pattern.evaluate_formation(replace(inputs,symbol="OTHER"))
    assert a==b
    assert a.setup_metadata["symbol"]==inputs.symbol
    assert other.setup_metadata["symbol"]=="OTHER"
    assert a.setup_metadata["origin_timestamp"]==start
    ids=[p.pattern_id for p in RossPatternRegistry().patterns]
    assert ids.count("P_BULL_FLAG")==1
    assert ids.count("P_MICRO_PULLBACK")==1


def test_recurring_manager_stop_update_delegates_and_preserves_failure_truth():
    from src.execution.trade_management_engine import TradeManagementEngine
    calls=[]
    def reject(**kwargs): calls.append(kwargs); return {"allowed":False}
    manager=TradeManagementEngine(stop_update_callback=reject)
    position=manager.on_exec_details(symbol="OFFLINE",shares=1,price=10,exec_id="exec",
        reference_order_id="entry-order",strategy_name="ROSS_MOMENTUM",stop_loss_price=9.6)
    position.current_price=10.2
    assert not manager._apply_authorized_stop_update(position,proposed_stop_price=9.8,reason="fixture")
    assert position.stop_loss_price==9.6
    assert calls[0]["trade_id"]=="entry-order"
    assert calls[0]["requested_by_strategy"]=="ROSS_MOMENTUM"
