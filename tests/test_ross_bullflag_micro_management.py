"""Synthetic offline policy contracts; no broker/Paper acceptance."""
from dataclasses import asdict
import pytest
from src.execution.trade_management_engine import TradeManagementEngine

class MemoryStorage:
    enabled = True
    def __init__(self): self.rows = {}
    def store_management_state(self, state_id, payload):
        import json
        self.rows[state_id]=json.loads(json.dumps(payload,default=str))
    def fetch_management_state(self,state_id):
        import copy
        return copy.deepcopy(self.rows.get(state_id))

def opened(quantity=8):
    store=MemoryStorage(); manager=TradeManagementEngine(persistence_adapter=store)
    assert manager.register_relationship_order(relationship_id="r",symbol="FIXTURE",security_id="conId:123",parent_id="p",child_id="c1",order_id="entry",quantity=quantity,stop=9.0)
    manager.on_relationship_order_update(relationship_id="r",order_id="entry",cumulative_quantity=quantity,average_price=10.,terminal=True,status="Filled")
    assert manager.reconcile_relationship("r",confirmed_quantity=quantity,pending_orders={},complete=True)
    return manager,store

def milestone(manager, price=12):
    position=manager.snapshot_positions()["FIXTURE"];position.current_price=price
    return manager._relationship_milestone(position)

def test_initial_partial_is_protected_but_profit_reference_waits_for_terminal_and_reconciliation():
    manager=TradeManagementEngine()
    assert manager.register_relationship_order(relationship_id="r",symbol="FIXTURE",security_id="conId:123",parent_id="p",child_id="c1",order_id="entry",quantity=4,stop=9.)
    manager.on_relationship_order_update(relationship_id="r",order_id="entry",cumulative_quantity=2,average_price=10.,terminal=False,status="PartiallyFilled")
    assert manager.snapshot_positions()["FIXTURE"].stop_loss_price==9.
    assert manager.reconcile_relationship("r",confirmed_quantity=2,pending_orders={"entry":2},complete=True)
    assert manager._relationship_plans["r"].e0 is None
    manager.on_relationship_order_update(relationship_id="r",order_id="entry",cumulative_quantity=4,average_price=10.5,terminal=True,status="Filled")
    assert manager._relationship_plans["r"].e0 is None
    assert manager.reconcile_relationship("r",confirmed_quantity=4,pending_orders={},complete=True)
    plan=manager._relationship_plans["r"]
    assert (plan.e0,plan.r0,plan.milestone_price)==(10.5,1.5,13.5)
    assert manager.snapshot_positions()["FIXTURE"].quantity==4

@pytest.mark.parametrize("quantity,expected",[(1,1),(2,1),(3,1),(7,3),(8,4)])
def test_once_only_two_r_whole_share_reduction(quantity,expected):
    manager,_=opened(quantity)
    assert milestone(manager,11.) is None
    intent=milestone(manager);assert intent.quantity==expected
    assert milestone(manager) is None
    manager.on_relationship_order_update(relationship_id="r",order_id=intent.management_action_id,cumulative_quantity=expected,average_price=12.,terminal=True,status="Filled")
    assert manager.reconcile_relationship("r",confirmed_quantity=quantity-expected,pending_orders={},complete=True)
    assert manager._relationship_plans["r"].milestone_consumed
    if quantity>1: assert milestone(manager,13.) is None

def test_partial_milestone_restart_and_cancel_resume_only_unfilled_balance():
    manager,store=opened(8);intent=milestone(manager)
    manager.on_relationship_order_update(relationship_id="r",order_id=intent.management_action_id,cumulative_quantity=1,average_price=12.,terminal=False,status="PartiallyFilled")
    manager.on_relationship_order_update(relationship_id="r",order_id=intent.management_action_id,cumulative_quantity=1,average_price=12.,terminal=False,status="PartiallyFilled")
    recovered=TradeManagementEngine(persistence_adapter=store);recovered.restore_relationship_state()
    assert recovered.snapshot_positions()["FIXTURE"].quantity==7
    assert milestone(recovered) is None
    assert recovered.reconcile_relationship("r",confirmed_quantity=7,pending_orders={intent.management_action_id:3},complete=True)
    assert milestone(recovered) is None
    recovered.on_relationship_order_update(relationship_id="r",order_id=intent.management_action_id,cumulative_quantity=1,average_price=12.,terminal=True,status="Cancelled")
    assert recovered.reconcile_relationship("r",confirmed_quantity=7,pending_orders={},complete=True)
    remaining=milestone(recovered);assert remaining.quantity==3

@pytest.mark.parametrize("quantity,expected",[(1,0),(3,0),(4,1),(7,1),(8,2)])
def test_add_uses_floor_and_preserves_pending_reservations(quantity,expected):
    manager,_=opened(quantity)
    assert manager.relationship_add_quantity("r",price=10.5,warning=False,parent_valid=True,child_id="fresh")==expected
    assert manager.relationship_add_quantity("r",price=9.9,warning=False,parent_valid=True,child_id="fresh")==0
    assert manager.relationship_add_quantity("r",price=10.5,warning=True,parent_valid=True,child_id="fresh")==0
    assert manager.relationship_add_quantity("r",price=10.5,warning=False,parent_valid=True,child_id="c1")==0

def test_add_and_trailing_never_rebase_frozen_milestone():
    manager,_=opened(8);plan=manager._relationship_plans["r"]
    assert manager.register_relationship_order(relationship_id="r",symbol="FIXTURE",security_id="conId:123",parent_id="p",child_id="c2",order_id="add",quantity=2,stop=9.5,action="ADD")
    assert manager.relationship_add_quantity("r",price=11.,warning=False,parent_valid=True,child_id="c3")==0
    manager.on_relationship_order_update(relationship_id="r",order_id="add",cumulative_quantity=2,average_price=11.,terminal=True,status="Filled")
    position=manager.snapshot_positions()["FIXTURE"];position.current_price=11.5
    manager._apply_authorized_stop_update(position,proposed_stop_price=10.,reason="fixture")
    assert (plan.e0,plan.r0,plan.milestone_price)==(10.,1.,12.)
    assert position.quantity==10
    assert plan.add_count==1

def test_nonpositive_original_risk_never_creates_milestone():
    manager=TradeManagementEngine()
    manager.register_relationship_order(relationship_id="r",symbol="FIXTURE",security_id="conId:123",parent_id="p",child_id="c",order_id="entry",quantity=1,stop=10.)
    manager.on_relationship_order_update(relationship_id="r",order_id="entry",cumulative_quantity=1,average_price=10.,terminal=True,status="Filled")
    manager.reconcile_relationship("r",confirmed_quantity=1,pending_orders={},complete=True)
    assert manager._relationship_plans["r"].paused
    assert manager._relationship_plans["r"].milestone_price is None


def test_real_registry_child_trigger_to_production_intent(monkeypatch, tmp_path):
    from dataclasses import replace
    from datetime import datetime, timezone, timedelta
    from test_pr1082_trigger_to_intent_terminal_semantics import _base_strategy, _candles, _watchlist_row, _snapshot
    from test_bull_flag_pipeline_end_to_end import _inputs
    from test_ross_pr1029_pattern_detection_certification import _micro_rows
    from src.strategies.ross_momentum.patterns import pattern_trace
    from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    from src.config.config_resolver import set_config_overrides
    from src.config.runtime_config import RunMode
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return cls(2026,9,16,14,35,30,tzinfo=timezone.utc)
    monkeypatch.setattr(pattern_trace,"datetime",Clock)
    set_config_overrides({"RUN_MODE":"READ_ONLY","RUN_MODE_EFFECTIVE":"READ_ONLY","EXECUTION_ENABLED":False})
    try:
        strategy=_base_strategy(monkeypatch,tmp_path,state="ready")
        manager=TradeManagementEngine(persistence_adapter=MemoryStorage())
        strategy.relationship_manager=manager
        registry=RossPatternRegistry();registry._patterns=[BullFlagPattern()];strategy._pattern_registry=registry
        primary_rows=[(10,10.02,9.98,10,1000)]*42+[(c.open,c.high,c.low,c.close,c.volume) for c in _inputs().candles[:-1]]
        end=datetime(2026,9,16,14,35,tzinfo=timezone.utc)
        primary=[replace(c,timestamp=c.timestamp-timedelta(minutes=1)) for c in _candles(primary_rows,end=end)]
        micro=[tuple(v+.55 if i<4 else v for i,v in enumerate(row)) for row in _micro_rows()]
        fast=_candles([(10.55,10.57,10.53,10.55,500)]*25+micro,step_seconds=10,end=end)
        fast=[replace(c,timestamp=c.timestamp+timedelta(seconds=10)) for c in fast]
        streams={"1m":primary,"5m":_candles(primary_rows,step_seconds=300,end=end),"10s":fast}
        monkeypatch.setattr(pattern_trace,"get_intraday_bars",lambda *,timeframe="1m",**kw:streams[timeframe])
        row={**_watchlist_row(),"conId":123,"gap_pct":9.2,"last_price":10.92,"bid":10.91,"ask":10.93}
        snapshot=replace(_snapshot(),last=10.92,bid=10.91,ask=10.93)
        args=dict(watchlist=[row],snapshots={"UPC":snapshot},session_label="RTH_OPEN",session_phase="RTH_OPEN",timestamp_utc="child-route",mode=RunMode.READ_ONLY)
        intents=strategy.process_watchlist(**args)
        assert len(intents)==1, strategy.last_symbol_terminal_outcomes
        intent=intents[0]
        assert intent.gap_percent == 9.2
        assert intent.target_model=="BULL_FLAG_MICRO_2R_V1"
        assert intent.relationship_context["security_id"]=="conId:123"
        assert intent.relationship_context["action"]=="ENTRY"
        assert intent.execution_refinement_mode=="FAST_MICRO_PULLBACK"
        assert intent.stop_loss_price>intent.relationship_context["parent_invalidation"]
        assert strategy.process_watchlist(**args)==[]
        # Continue the actual produced intent through the canonical risk authority.
        from src.core.intent import build_decision_artifact
        from src.risk.risk_engine import RiskEngine
        artifact=build_decision_artifact(strategy_name=strategy.name,run_mode="SIM",session_phase="RTH_OPEN",
            intents=[intent],source="offline-production-route",created_at=end.isoformat())
        intent.decision_id=artifact.decision_id
        set_config_overrides({"RUN_MODE":"PAPER","RUN_MODE_EFFECTIVE":"PAPER","EXECUTION_ENABLED":True,
            "EXECUTION_ENABLED_EFFECTIVE":True,"IBKR_READONLY":False})
        risk=RiskEngine();risk.relationship_manager=manager
        decision=risk.evaluate_trade_intent(intent)
        assert decision.allowed, (decision.reason_code,decision.rationale)
        assert decision.max_position_size==1
        assert decision.relationship_context==intent.relationship_context
        # PAPER is only an in-memory provider label here; no IBKR adapter/client.
        from src.execution.execution_engine import ExecutionEngine
        from src.execution.execution_providers import PaperExecutionProvider
        from src.core.orchestrator import CoreOrchestrator
        from types import SimpleNamespace
        class FixedPrice:
            def price_for(self,*args): return 10.92
            def get_price(self,*args): return 10.92
        set_config_overrides({"RUN_MODE":"PAPER","RUN_MODE_EFFECTIVE":"PAPER","EXECUTION_ENABLED":True,
            "EXECUTION_ENABLED_EFFECTIVE":True,"IBKR_READONLY_ENABLED":False})
        engine=ExecutionEngine(price_feed=FixedPrice())
        assert isinstance(engine.provider,PaperExecutionProvider)
        engine.relationship_manager=manager
        result=engine.execute_trade(decision)
        assert result.filled_quantity==1, (result.status,result.rationale)
        CoreOrchestrator._apply_execution_results_to_trade_management(SimpleNamespace(trade_management_engine=manager),[result])
        plan=manager._relationship_plans[intent.relationship_context["relationship_id"]]
        sim_harness=SimpleNamespace(run_mode=__import__('src.config.runtime_config',fromlist=['RunMode']).RunMode.SIM,
            trade_management_engine=manager,trade_registry=engine.trade_registry,execution_engine=engine)
        CoreOrchestrator._resolve_position_truth_cycle(sim_harness,as_of=end)
        assert plan.reconciled
        assert plan.e0==pytest.approx(float(result.average_fill_price or result.entry_price))
        assert plan.original_stop==intent.stop_loss_price
        protection=engine.post_fill_lifecycle.get_trade(plan.initial_order_id)
        assert protection.stop.trigger_price==intent.stop_loss_price
        assert protection.stop.quantity==1
        assert protection.target is None


    finally: set_config_overrides(None)


def composed_inputs():
    from dataclasses import replace
    from datetime import datetime,timezone,timedelta
    from test_bull_flag_pipeline_end_to_end import _inputs
    from test_ross_pr1029_pattern_detection_certification import _micro_rows
    from src.strategies.common.candles.candle_types import Candle
    base=_inputs();start=datetime(2026,9,16,14,27,tzinfo=timezone.utc)
    primary=[replace(c,timestamp=start+timedelta(minutes=i)) for i,c in enumerate(base.candles[:-1])]
    fast=[]
    for i,row in enumerate(_micro_rows()):
        o,h,l,c,v=row;fast.append(Candle(open=o+.55,high=h+.55,low=l+.55,close=c+.55,volume=v,
            timestamp=start+timedelta(minutes=8,seconds=i*10)))
    return replace(base,candles=primary,session_label="RTH_OPEN",timeframe_candles={"1m":primary,"10s":fast},
        timeframe_provenance={"1m":"PRESENT","10s":"PRESENT"}),start+timedelta(minutes=9)

@pytest.mark.parametrize("case",["missing_child","stale_child","missing_clock","unknown_session","missing_rvol","unclosed_child"])
def test_relationship_missing_inputs_cannot_create_child(case):
    from dataclasses import replace
    from datetime import timedelta
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    inputs,now=composed_inputs()
    if case=="missing_child": inputs=replace(inputs,timeframe_candles={"1m":inputs.candles})
    if case=="stale_child": inputs=replace(inputs,timeframe_provenance={"1m":"PRESENT","10s":"STALE"})
    if case=="missing_clock": inputs=replace(inputs,candles=[replace(c,timestamp=None) for c in inputs.candles])
    if case=="unknown_session": inputs=replace(inputs,session_label="UNKNOWN")
    if case=="missing_rvol": inputs=replace(inputs,liquidity_context=replace(inputs.liquidity_context,rvol=None))
    if case=="unclosed_child":
        inputs=replace(inputs,timeframe_candles={**inputs.timeframe_candles,"10s":[replace(c,timestamp=c.timestamp+timedelta(hours=1)) for c in inputs.timeframe_candles["10s"]]})
    result=TradeManagementEngine().compose_bull_flag(BullFlagPattern(),inputs,security_id="conId:1",now=now)
    assert not result.detected


def test_parent_invalidation_cross_security_and_timezone_independence(monkeypatch):
    from dataclasses import replace
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    inputs,now=composed_inputs();manager=TradeManagementEngine();pattern=BullFlagPattern()
    monkeypatch.setenv("TZ","Pacific/Auckland")
    a=manager.compose_bull_flag(pattern,inputs,security_id="conId:1",now=now)
    monkeypatch.setenv("TZ","America/New_York")
    b=manager.compose_bull_flag(pattern,inputs,security_id="conId:1",now=now)
    other=manager.compose_bull_flag(pattern,replace(inputs,symbol="OTHER"),security_id="conId:2",now=now)
    assert a==b and a.detected and other.detected
    assert a.setup_metadata["relationship"]["parent_id"]!=other.setup_metadata["relationship"]["parent_id"]
    broken=replace(inputs,candles=inputs.candles[:-1]+[replace(inputs.candles[-1],low=9.0)])
    assert not manager.compose_bull_flag(pattern,broken,security_id="conId:1",now=now).detected
    assert manager.compose_bull_flag(pattern,replace(inputs,symbol="OTHER"),security_id="conId:2",now=now).detected


def test_parent_armed_without_child_and_no_duplicate_after_restart():
    from dataclasses import replace
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    inputs,now=composed_inputs();store=MemoryStorage();manager=TradeManagementEngine(persistence_adapter=store)
    missing=replace(inputs,timeframe_candles={"1m":inputs.candles})
    assert not manager.compose_bull_flag(BullFlagPattern(),missing,security_id="conId:1",now=now).detected
    assert list(manager._parents.values())[0]["state"]=="ARMED"
    found=manager.compose_bull_flag(BullFlagPattern(),inputs,security_id="conId:1",now=now)
    from types import SimpleNamespace
    context=found.setup_metadata["relationship"]
    intent=SimpleNamespace(symbol=inputs.symbol,entry_price=found.trigger_level,quantity=1)
    assert manager.prepare_relationship_intent(intent,context)
    restored=TradeManagementEngine(persistence_adapter=store);restored.restore_relationship_state()
    assert not restored.compose_bull_flag(BullFlagPattern(),inputs,security_id="conId:1",now=now).detected


def test_three_logical_adds_and_one_share_aggregate_cap():
    from types import SimpleNamespace
    manager,_=opened(8)
    for i in range(3):
        assert manager.register_relationship_order(relationship_id="r",symbol="FIXTURE",security_id="conId:123",parent_id="p",child_id=f"add{i}",order_id=f"add{i}",quantity=2,stop=9.,action="ADD")
        manager.on_relationship_order_update(relationship_id="r",order_id=f"add{i}",cumulative_quantity=2,average_price=11.,terminal=True,status="Filled")
        assert manager.reconcile_relationship("r",confirmed_quantity=10+2*i,pending_orders={},complete=True)
    assert manager.relationship_add_quantity("r",price=12.,warning=False,parent_valid=True,child_id="fourth")==0
    one,_=opened(1)
    intent=SimpleNamespace(symbol="FIXTURE",entry_price=11.,quantity=1,relationship_context={"profile":"BULL_FLAG_MICRO_2R_V1","action":"ADD","relationship_id":"r","child_id":"new"})
    assert one.risk_quantity(intent,quantity_cap=1,value_cap=160.)==0


def test_failure_exit_before_milestone_and_no_default_one_r_partial():
    manager,_=opened(8);p=manager.snapshot_positions()["FIXTURE"]
    p.current_price=11.
    assert manager._evaluate_exit_rules(p,{"current_price":11.,"continuation":True}) is None
    p.current_price=8.9
    exit_intent=manager._evaluate_exit_rules(p,{"current_price":8.9})
    assert exit_intent.quantity==8
    assert exit_intent.relationship_id=="r"
    assert not manager._relationship_plans["r"].milestone_consumed


def test_actual_sqlite_state_survives_new_run_without_operational_storage(tmp_path):
    from src.storage.storage_engine import StorageEngine
    from src.storage.sqlite_store import SQLiteStore
    from datetime import datetime,timezone
    store=SQLiteStore(str(tmp_path/"isolated.sqlite3"));store.initialize_schema()
    # Real schema/foreign-key and StorageEngine methods, isolated fixture runs.
    store.connection.execute("INSERT INTO runs(run_id) VALUES (?)",("run-one",));store.connection.commit()
    adapter=StorageEngine.__new__(StorageEngine);adapter.enabled=True;adapter.backend="sqlite";adapter._store=store;adapter.run_id="run-one"
    manager=TradeManagementEngine(persistence_adapter=adapter)
    assert manager.register_relationship_order(relationship_id="r",symbol="FIXTURE",security_id="conId:123",parent_id="p",child_id="child",order_id="entry",quantity=1,stop=9.)
    store.close()
    store=SQLiteStore(str(tmp_path/"isolated.sqlite3"));adapter._store=store;adapter.run_id="run-two"
    recovered=TradeManagementEngine(persistence_adapter=adapter);recovered.restore_relationship_state()
    assert recovered._relationship_plans["r"].consumed_children==["child"]
    assert recovered._relationship_plans["r"].reconciled is False
    store.close()


def test_selected_protection_resizes_without_replacement_or_reset():
    from src.execution.post_fill_lifecycle_engine import PostFillLifecycleEngine
    from test_post_fill_lifecycle_engine_v1 import _ProviderStub
    provider=_ProviderStub();life=PostFillLifecycleEngine("PAPER",execution_provider=provider)
    life.activate_trade_management_after_fill(trade_id="entry",symbol="FIXTURE",side="LONG",filled_qty=1,
        avg_fill_price=10.,strategy_id="RossMomentumStrategyV1",stop_loss_price=9.,preserve_selected_protection=True)
    assert life.update_selected_exposure(trade_id="entry",filled_qty=3,avg_fill_price=10.2)["success"]
    assert len(provider.stop_calls)==1 and len(provider.modify_calls)==1
    assert provider.modify_calls[0]["quantity"]==3
    assert life.get_trade("entry").stop.trigger_price==9.
    provider.fail_stop_modifications=True
    assert not life.update_selected_exposure(trade_id="entry",filled_qty=4,avg_fill_price=10.3)["success"]
    assert life.get_trade("entry").filled_qty==4
    assert life.get_trade("entry").stop.quantity==3


def test_failure_preempts_pending_milestone_only_after_terminal_reconciliation():
    from src.strategies.ross_momentum.exit_intelligence import ExitDecision
    manager,_=opened(8);intent=milestone(manager);plan=manager._relationship_plans["r"]
    order=plan.orders[intent.management_action_id];order["broker_order_id"]="offline-reduce"
    calls=[];manager._cancel_order_callback=lambda **kw: calls.append(kw)
    position=manager.snapshot_positions()["FIXTURE"]
    decision=ExitDecision(action="EXIT_MARKET",reason="STOP_LOSS_BREAK")
    assert manager._apply_exit_decision(position,decision) is None
    assert manager._apply_exit_decision(position,decision) is None
    assert calls==[{"broker_order_id":"offline-reduce"}]
    manager.on_relationship_order_update(relationship_id="r",order_id=intent.management_action_id,
        cumulative_quantity=1,average_price=12.,terminal=True,status="Cancelled")
    assert manager._apply_exit_decision(position,decision) is None
    assert manager.reconcile_relationship("r",confirmed_quantity=7,pending_orders={},complete=True)
    exit_intent=manager._apply_exit_decision(position,decision)
    assert exit_intent.quantity==7 and exit_intent.exit_type=="STOP"
    assert plan.milestone_filled==1 and not plan.milestone_consumed


@pytest.mark.parametrize("con_id,accepted",[(None,False),(999,False),("123",False),(123,True)])
def test_restored_plan_requires_matching_security_in_existing_snapshot(con_id,accepted):
    from datetime import datetime,timezone
    manager,store=opened(2)
    restored=TradeManagementEngine(persistence_adapter=store);restored.restore_relationship_state()
    restored.reconcile_broker_snapshot(positions={"FIXTURE":{"quantity":2,"con_id":con_id}},
        open_orders=[],complete=True,as_of=datetime(2026,9,16,tzinfo=timezone.utc))
    assert restored._relationship_plans["r"].reconciled is accepted


def test_rejected_stop_modification_preserves_installed_price():
    from test_post_fill_lifecycle_engine_v1 import _ProviderStub
    from src.execution.post_fill_lifecycle_engine import PostFillLifecycleEngine
    provider=_ProviderStub();life=PostFillLifecycleEngine("PAPER",execution_provider=provider)
    life.activate_trade_management_after_fill(trade_id="entry",symbol="FIXTURE",side="LONG",filled_qty=1,
        avg_fill_price=10.,strategy_id="RossMomentumStrategyV1",stop_loss_price=9.,preserve_selected_protection=True)
    provider.modify_stop_order=lambda **kw: {"status":"Rejected"}
    assert not life.replace_stop(trade_id="entry",requested_by_strategy="RossMomentumStrategyV1",new_stop_price=9.5)["allowed"]
    assert life.get_trade("entry").stop.trigger_price==9.


def test_cached_late_fills_resize_one_stop_and_one_registry_position(monkeypatch):
    from types import SimpleNamespace
    from src.execution.execution_engine import ExecutionEngine
    from src.execution.post_fill_lifecycle_engine import PostFillLifecycleEngine
    from src.core.active_trade_registry import ActiveTradeRegistry
    from src.core.orchestrator import CoreOrchestrator
    from src.brokers.base_broker import BrokerOrderRequest
    from src.config.runtime_config import RunMode
    from test_post_fill_lifecycle_engine_v1 import _ProviderStub
    manager=TradeManagementEngine(persistence_adapter=MemoryStorage())
    manager.register_relationship_order(relationship_id="r",symbol="FIXTURE",security_id="conId:123",
        parent_id="p",child_id="c",order_id="entry",quantity=5,stop=9.)
    context={"profile":"BULL_FLAG_MICRO_2R_V1","relationship_id":"r","action":"ENTRY"}
    request=BrokerOrderRequest(client_order_id="entry",symbol="FIXTURE",direction="LONG",quantity=5,
        order_type="MKT",trader_type="SCALPER",strategy_name="RossMomentumStrategyV1",stop_loss_price=9.,relationship_context=context)
    plan=manager._relationship_plans["r"];plan.orders["entry"].update(request=asdict(request),broker_order_id="17")
    provider=_ProviderStub();facts={"status":"Submitted","filled":1,"remaining":4,"avgFillPrice":10.}
    provider.cached_order_update=lambda order_id: dict(facts)
    engine=ExecutionEngine.__new__(ExecutionEngine)
    engine.relationship_manager=manager;engine._provider=provider;engine.run_mode=RunMode.PAPER
    engine.post_fill_lifecycle=PostFillLifecycleEngine("PAPER",execution_provider=provider)
    engine.trade_registry=ActiveTradeRegistry();engine.position_records={};engine._failsafe_block_new_entries=False
    engine._convert_strategy_allocation_for_fill=lambda *a,**kw: None
    engine._convert_capital_for_fill=lambda *a,**kw: None
    engine._capital_decisions_by_order_id={}
    engine._strategy_allocation_decisions_by_order_id={}
    engine._record_order_stage=lambda *a,**kw: None
    engine._execution_log=lambda *a,**kw: None
    harness=SimpleNamespace(trade_management_engine=manager)
    def drain():
        results=engine.collect_relationship_updates()
        CoreOrchestrator._apply_execution_results_to_trade_management(harness,results)
        return results
    assert len(drain())==1
    assert plan.e0 is None and manager.snapshot_positions()["FIXTURE"].quantity==1
    assert engine.post_fill_lifecycle.get_trade("entry").stop.quantity==1
    assert drain()==[]
    facts.update(status="Cancelled",filled=4,remaining=1,avgFillPrice=10.3)
    assert len(drain())==1
    assert manager.snapshot_positions()["FIXTURE"].quantity==4
    assert len(provider.stop_calls)==1 and len(provider.modify_calls)==1
    assert engine.post_fill_lifecycle.get_trade("entry").stop.quantity==4
    assert len(engine.trade_registry.snapshot())==1
    assert engine.trade_registry.snapshot()[0].quantity==4
    assert engine.trade_registry.snapshot()[0].take_profit_price is None
    assert plan.e0 is None
    assert manager.reconcile_relationship("r",confirmed_quantity=4,pending_orders={},complete=True)
    assert plan.e0==10.3 and plan.milestone_price==pytest.approx(12.9)
    engine.position_records.clear() # cumulative replay after memory reset must not resize again
    facts.update(status="CANCELLED")
    assert drain()==[]
    assert len(provider.modify_calls)==1
    reduction=milestone(manager,13.)
    sell_context={"profile":"BULL_FLAG_MICRO_2R_V1","relationship_id":"r","action":"REDUCE"}
    sell=BrokerOrderRequest(client_order_id=reduction.management_action_id,symbol="FIXTURE",direction="SELL",quantity=2,
        order_type="MKT",trader_type="MANUAL",strategy_name="TRADE_MANAGEMENT",relationship_context=sell_context)
    from src.models.execution_result import ExecutionResult
    from src.core.capital_management_authority import CapitalManagementAuthority
    from src.core.strategy_capital_allocation_authority import StrategyCapitalAllocationAuthority
    allocation=StrategyCapitalAllocationAuthority();capital=CapitalManagementAuthority()
    for authority in (allocation,capital):
        authority.convert_reservation_to_exposure(decision_id=None,order_id="entry",symbol="FIXTURE",
            strategy_id="RossMomentumStrategyV1",fill_quantity=4,fill_price=10.3,trade_id="entry")
    releases=[]
    def release(authority, **kw):
        releases.append(kw)
        return authority.release_exposure(**kw)
    engine.strategy_allocation_authority=SimpleNamespace(release_exposure=lambda **kw: release(allocation,**kw))
    engine.capital_authority=SimpleNamespace(release_exposure=lambda **kw: release(capital,**kw))
    fill=ExecutionResult(symbol="FIXTURE",trader_type="MANUAL",attempted=True,status="Filled",rationale="offline",
        filled_quantity=2,remaining_quantity=0,average_fill_price=13.)
    engine._record_fill_and_position(sell,fill)
    CoreOrchestrator._apply_execution_results_to_trade_management(harness,[fill])
    assert [(t.trader_type,t.quantity) for t in engine.trade_registry.snapshot()]==[("SCALPER",2)]
    assert [r["strategy_id"] for r in releases]==["RossMomentumStrategyV1"]*2
    assert [r["price"] for r in releases]==pytest.approx([10.3,10.3])
    assert allocation.strategy_used_exposure("RossMomentumStrategyV1")==pytest.approx(20.6)
    assert capital.symbol_exposure("FIXTURE")==pytest.approx(20.6)
    manager.reconcile_relationship("r",confirmed_quantity=2,pending_orders={},complete=True)
    closing=manager._emit_exit_intent(manager.snapshot_positions()["FIXTURE"],qty=2,rationale="STOP_LOSS_BREAK",exit_type="STOP",stage="FINAL")
    close_request=BrokerOrderRequest(**{**asdict(sell),"client_order_id":closing.management_action_id})
    def cancel_failure(**kw): raise RuntimeError("offline stop cancel failed")
    provider.cancel_order=cancel_failure
    close_fill=ExecutionResult(symbol="FIXTURE",trader_type="MANUAL",attempted=True,status="Filled",rationale="offline",
        filled_quantity=2,remaining_quantity=0,average_fill_price=9.)
    engine._record_fill_and_position(close_request,close_fill)
    CoreOrchestrator._apply_execution_results_to_trade_management(harness,[close_fill])
    assert engine.trade_registry.snapshot()==[]
    assert manager.snapshot_positions()=={}
    assert allocation.strategy_used_exposure("RossMomentumStrategyV1")==pytest.approx(0.)
    assert capital.symbol_exposure("FIXTURE")==pytest.approx(0.)
    assert engine._failsafe_block_new_entries
    assert plan.pending_stop_cancel
    cleanup_calls=[]
    provider.cancel_order=lambda **kw: cleanup_calls.append(kw) or {"status":"PendingCancel"}
    provider.get_open_orders=lambda: []
    assert engine.collect_relationship_updates()==[]
    assert len(cleanup_calls)==1 and plan.pending_stop_cancel
    engine.refresh_relationship_order_snapshot()
    assert plan.pending_stop_cancel is None
    assert not engine._failsafe_block_new_entries
    assert manager.snapshot_positions()=={} and engine.trade_registry.snapshot()==[]

    old_protection=engine.post_fill_lifecycle.get_trade(plan.protection_trade_id)
    def fresh_stop(**kw):
        provider.stop_calls.append(kw)
        return {"broker_order_id":"STOP-REOPENED","status":"Submitted"}
    provider.place_stop_order=fresh_stop
    facts.update(status="Cancelled",filled=5,remaining=0,avgFillPrice=10.34)
    assert len(drain())==1
    reopened=engine.post_fill_lifecycle.get_trade(plan.protection_trade_id)
    assert reopened is not old_protection
    assert old_protection.filled_qty==0 and old_protection.state.value=="EXITED"
    assert reopened.filled_qty==1 and reopened.stop.quantity==1
    assert reopened.stop.broker_order_id=="STOP-REOPENED"
    assert reopened.state.value!="EXITED" and reopened.target is None
    assert len(provider.stop_calls)==2
    assert manager.snapshot_positions()["FIXTURE"].quantity==1
    assert manager.snapshot_positions()["FIXTURE"].reference_order_id==reopened.trade_id
    assert plan.e0==10.3 and plan.milestone_price==pytest.approx(12.9)
    assert drain()==[]


def test_new_child_can_reenter_only_after_flat_and_same_child_stays_consumed():
    from types import SimpleNamespace
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    inputs,now=composed_inputs();manager=TradeManagementEngine(persistence_adapter=MemoryStorage())
    result=manager.compose_bull_flag(BullFlagPattern(),inputs,security_id="conId:123",now=now)
    context=result.setup_metadata["relationship"]
    intent=SimpleNamespace(symbol=inputs.symbol,entry_price=result.trigger_level,quantity=1)
    assert manager.prepare_relationship_intent(intent,context)
    rel=intent.relationship_context["relationship_id"]
    manager.register_relationship_order(relationship_id=rel,symbol=inputs.symbol,security_id="conId:123",
        parent_id=context["parent_id"],child_id=context["child_id"],order_id="entry",quantity=1,stop=result.stop_level)
    manager.on_relationship_order_update(relationship_id=rel,order_id="entry",cumulative_quantity=1,
        average_price=result.trigger_level,terminal=True,status="Filled")
    manager.reconcile_relationship(rel,confirmed_quantity=1,pending_orders={},complete=True)
    exit_intent=manager._emit_exit_intent(manager.snapshot_positions()[inputs.symbol],qty=1,rationale="STOP_LOSS_BREAK",exit_type="STOP",stage="FINAL")
    manager.on_relationship_order_update(relationship_id=rel,order_id=exit_intent.management_action_id,cumulative_quantity=1,
        average_price=result.stop_level,terminal=True,status="Filled")
    assert not manager.prepare_relationship_intent(intent,context)
    fresh={**context,"child_id":"synthetic-new-child"}
    assert not manager.prepare_relationship_intent(intent,fresh)
    assert manager.reconcile_relationship(rel,confirmed_quantity=0,pending_orders={},complete=True)
    assert manager.prepare_relationship_intent(intent,fresh)
    assert intent.relationship_context["action"]=="REENTRY"
    assert intent.relationship_context["relationship_id"]!=rel


def test_recovered_stop_binds_by_retained_order_id_then_waits_for_security_truth():
    from types import SimpleNamespace
    from datetime import datetime,timezone
    from src.execution.post_fill_lifecycle_engine import PostFillLifecycleEngine
    manager,store=opened(2);plan=manager._relationship_plans["r"]
    plan.protection_broker_order_id="STOP-1";manager._save_relationship_state()
    life=PostFillLifecycleEngine("READ_ONLY")
    life.startup_safe_state([SimpleNamespace(symbol="FIXTURE",quantity=2,avg_cost=10.,strategy_name="RECOVERY")],
        [{"order_id":"STOP-1","symbol":"FIXTURE","order_type":"STP","status":"Submitted",
          "metadata":{"side":"SELL","quantity":2,"stop_price":9.,"trade_id":"entry"}}])
    restored=TradeManagementEngine(persistence_adapter=store);restored.restore_relationship_state()
    restored.bind_recovered_protection(life)
    recovered=restored._relationship_plans["r"]
    assert not recovered.paused and not recovered.reconciled
    assert recovered.protection_trade_id in life._trades
    assert life.get_trade(recovered.protection_trade_id).target is None
    assert milestone(restored) is None
    restored.reconcile_broker_snapshot(positions={"FIXTURE":{"quantity":2,"con_id":123}},open_orders=[],
        complete=True,as_of=datetime(2026,9,16,tzinfo=timezone.utc))
    assert milestone(restored).quantity==1


def test_consumed_profit_milestone_survives_fresh_add():
    manager,_=opened(16);intent=milestone(manager);plan=manager._relationship_plans["r"]
    manager.on_relationship_order_update(relationship_id="r",order_id=intent.management_action_id,
        cumulative_quantity=8,average_price=12.,terminal=True,status="Filled")
    manager.reconcile_relationship("r",confirmed_quantity=8,pending_orders={},complete=True)
    assert manager.register_relationship_order(relationship_id="r",symbol="FIXTURE",security_id="conId:123",
        parent_id="p",child_id="fresh",order_id="add",quantity=2,stop=10.,action="ADD")
    manager.on_relationship_order_update(relationship_id="r",order_id="add",cumulative_quantity=2,
        average_price=12.5,terminal=True,status="Filled")
    manager.reconcile_relationship("r",confirmed_quantity=10,pending_orders={},complete=True)
    assert plan.milestone_consumed and plan.milestone_price==12.
    assert milestone(manager,14.) is None


def test_uncertain_submission_reservation_clears_only_after_fresh_matching_truth():
    from datetime import datetime,timezone,timedelta
    manager,_=opened(8);plan=manager._relationship_plans["r"]
    manager.register_relationship_order(relationship_id="r",symbol="FIXTURE",security_id="conId:123",parent_id="p",
        child_id="add-child",order_id="failed-add",quantity=2,stop=9.,action="ADD")
    now=datetime(2026,9,16,15,tzinfo=timezone.utc)
    plan.orders["failed-add"].update(submission_uncertain_at=now.isoformat())
    def reconcile(qty,clock):
        manager.reconcile_broker_snapshot(positions={"FIXTURE":{"quantity":qty,"con_id":123}},
            open_orders=[],complete=True,as_of=clock,orders_as_of=clock)
    reconcile(8,now-timedelta(seconds=1))
    assert not plan.orders["failed-add"]["terminal"]
    reconcile(10,now+timedelta(seconds=1))
    assert not plan.orders["failed-add"]["terminal"]
    reconcile(8,now+timedelta(seconds=2))
    assert plan.orders["failed-add"]["terminal"] and plan.reconciled
    assert manager._emit_exit_intent(manager.snapshot_positions()["FIXTURE"],qty=8,
        rationale="STOP_LOSS_BREAK",exit_type="STOP",stage="FINAL").quantity==8


@pytest.mark.parametrize("raises",[True,False])
def test_provider_failure_retains_context_then_releases_only_reconciled_reservation(raises):
    from types import SimpleNamespace
    from datetime import datetime,timezone,timedelta
    from src.config.config_resolver import set_config_overrides
    from src.execution.execution_engine import ExecutionEngine
    from src.models.execution_result import ExecutionResult
    from src.brokers.base_broker import BrokerOrderRequest
    from src.core.orchestrator import CoreOrchestrator
    manager,_=opened(8)
    set_config_overrides({"RUN_MODE":"PAPER","RUN_MODE_EFFECTIVE":"PAPER","EXECUTION_ENABLED":True,
        "EXECUTION_ENABLED_EFFECTIVE":True,"IBKR_READONLY_ENABLED":False})
    try:
        engine=ExecutionEngine();engine.relationship_manager=manager
        def fail(request):
            if raises: raise RuntimeError("offline ambiguous dispatch")
            return ExecutionResult(symbol="FIXTURE",trader_type="MOMENTUM",attempted=False,status="FAILED",rationale="offline failure")
        engine._provider=SimpleNamespace(place_order=fail,is_live=lambda:False,name=lambda:"offline-double",cached_order_update=lambda _: {})
        releases=[]
        engine._release_capital_for_order=lambda *a,**kw: releases.append("capital")
        engine._release_strategy_allocation_for_order=lambda *a,**kw: releases.append("allocation")
        context={"profile":"BULL_FLAG_MICRO_2R_V1","relationship_id":"r","action":"ADD","security_id":"conId:123","parent_id":"p","child_id":"new"}
        request=BrokerOrderRequest(client_order_id="failed-add",symbol="FIXTURE",direction="LONG",quantity=2,
            order_type="MKT",trader_type="MOMENTUM",strategy_name="RossMomentumStrategyV1",stop_loss_price=9.,relationship_context=context)
        result=engine._route_order(request)
        assert result.status=="SUBMISSION_UNKNOWN" and result.relationship_context==context
        assert releases==[]
        CoreOrchestrator._apply_execution_results_to_trade_management(SimpleNamespace(trade_management_engine=manager),[result])
        plan=manager._relationship_plans["r"];assert not plan.orders["failed-add"]["terminal"]
        now=datetime.now(timezone.utc)+timedelta(seconds=1)
        manager.reconcile_broker_snapshot(positions={"FIXTURE":{"quantity":8,"con_id":123}},open_orders=[],
            complete=True,as_of=now,orders_as_of=now)
        assert plan.orders["failed-add"]["terminal"]
        assert engine.collect_relationship_updates()==[]
        assert releases==["allocation","capital"]
        assert engine.collect_relationship_updates()==[]
        assert len(releases)==2
    finally: set_config_overrides(None)


def test_composed_route_never_falls_back_to_unpaired_standalone_breakout():
    from dataclasses import replace
    from datetime import datetime,timezone,timedelta
    from test_bull_flag_pipeline_end_to_end import _inputs
    from src.setup_engine.setup_families.bull_flag import BullFlagPattern
    base=_inputs();start=datetime(2026,9,16,14,27,tzinfo=timezone.utc)
    bars=[replace(c,timestamp=start+timedelta(minutes=i)) for i,c in enumerate(base.candles)]
    inputs=replace(base,candles=bars,session_label="RTH_OPEN",timeframe_candles={"1m":bars},timeframe_provenance={"1m":"PRESENT"})
    pattern=BullFlagPattern();assert pattern.evaluate(inputs).detected
    assert not TradeManagementEngine().compose_bull_flag(pattern,inputs,security_id="conId:1",now=start+timedelta(minutes=10)).detected
    assert not TradeManagementEngine().compose_bull_flag(pattern,inputs,security_id="",now=start+timedelta(minutes=10)).detected


def test_failed_cancel_is_retryable_without_duplicate_exit():
    from src.strategies.ross_momentum.exit_intelligence import ExitDecision
    manager,_=opened(8);reduction=milestone(manager);order=manager._relationship_plans["r"].orders[reduction.management_action_id]
    order["broker_order_id"]="offline-reduce"
    calls=[]
    def cancel(**kw):
        calls.append(kw)
        if len(calls)==1: raise RuntimeError("offline disconnected")
        return {"status":"PendingCancel"}
    manager._cancel_order_callback=cancel
    position=manager.snapshot_positions()["FIXTURE"];failure=ExitDecision(action="EXIT_MARKET",reason="STOP_LOSS_BREAK")
    assert manager._apply_exit_decision(position,failure) is None
    assert not order.get("cancel_requested")
    assert manager._apply_exit_decision(position,failure) is None
    assert order["cancel_requested"] and not order["terminal"]
    assert manager._apply_exit_decision(position,failure) is None
    assert len(calls)==2


def test_real_risk_scales_existing_relationship_without_counting_new_trade(monkeypatch):
    from src.config.config_resolver import set_config_overrides
    from src.risk.risk_engine import RiskEngine
    from src.models.data_models import TradeIntent
    from src.core.active_trade_registry import ActiveTrade
    manager,_=opened(8)
    monkeypatch.setenv("TRADING_DEFAULT_CAPITAL","10000")
    set_config_overrides({"RUN_MODE":"PAPER","RUN_MODE_EFFECTIVE":"PAPER","EXECUTION_ENABLED":True,
        "EXECUTION_ENABLED_EFFECTIVE":True,"IBKR_READONLY":False,"RISK_MAX_OPEN_POSITIONS":1})
    try:
        risk=RiskEngine();risk.relationship_manager=manager
        # Isolated enlarged size only: production one-share default is untouched.
        monkeypatch.setattr(risk,"_resolve_profile_size",lambda _:16)
        risk.trade_registry.register_trade(ActiveTrade(symbol="FIXTURE",trader_type="MOMENTUM",entry_tick=1,
            entry_price=10.,direction="LONG",quantity=8,strategy_name="RossMomentumStrategyV1",stop_loss_price=9.))
        intent=TradeIntent(symbol="FIXTURE",direction="LONG",strategy_name="RossMomentumStrategyV1",confidence=.8,
            rationale="synthetic fresh-child add",trader_type="MOMENTUM",decision_id="offline-add",
            stop_loss_price=9.,gap_percent=9.2,rvol=10.,float_millions=8.,
            relationship_context={"profile":"BULL_FLAG_MICRO_2R_V1","relationship_id":"r","action":"ADD",
                "parent_id":"p","child_id":"fresh","security_id":"conId:123"})
        intent.quantity=2
        intent.entry_price=10.5
        decision=risk.evaluate_trade_intent(intent)
        assert decision.allowed, (decision.reason_code,decision.rationale)
        assert decision.max_position_size==2
        manager._relationship_plans["r"].add_count=2 # existing NORMAL profile is stricter than the relationship maximum of 3
        assert not risk.evaluate_trade_intent(intent).allowed
    finally: set_config_overrides(None)


def test_add_risk_uses_aggregate_confirmed_exposure_and_existing_profile_limits():
    from types import SimpleNamespace
    manager,_=opened(8)
    intent=SimpleNamespace(symbol="FIXTURE",entry_price=10.5,quantity=2,relationship_context={"profile":"BULL_FLAG_MICRO_2R_V1",
        "action":"ADD","relationship_id":"r","parent_id":"p","child_id":"fresh","security_id":"conId:123"})
    assert manager.risk_quantity(intent,quantity_cap=16,value_cap=1000,risk_cap=8)==0
    assert manager.risk_quantity(intent,quantity_cap=16,value_cap=1000,risk_cap=10)==1
    assert manager.risk_quantity(intent,quantity_cap=16,value_cap=1000,risk_cap=11)==2
    assert manager.risk_quantity(intent,quantity_cap=16,value_cap=1000,risk_cap=11,incremental_value_cap=10)==0


@pytest.mark.parametrize("late_quantity",[1,8])
def test_late_nonterminal_status_cannot_reopen_reconciled_entry(late_quantity):
    manager,_=opened(8);plan=manager._relationship_plans["r"]
    manager.on_relationship_order_update(relationship_id="r",order_id="entry",cumulative_quantity=late_quantity,
        average_price=10.,terminal=False,status="Submitted")
    assert plan.entry_terminal and plan.orders["entry"]["terminal"] and plan.reconciled
    assert milestone(manager).quantity==4


def test_capital_recovery_reuses_order_snapshot_and_refreshes_expiry_without_new_trade():
    from types import SimpleNamespace
    from datetime import datetime,timezone,timedelta
    from src.execution.execution_engine import ExecutionEngine
    from src.execution.startup_recovery_authority import RecoveryState
    from src.execution.post_fill_lifecycle_engine import PostFillLifecycleEngine
    from src.core.orchestrator import CoreOrchestrator
    from src.core.active_trade_registry import ActiveTradeRegistry,ActiveTrade
    from src.config.runtime_config import RunMode
    manager,_=opened(8);manager._relationship_plans["r"].reconciled=False
    engine=ExecutionEngine.__new__(ExecutionEngine);engine.relationship_manager=manager
    engine.run_mode=RunMode.PAPER;engine.startup_recovery_state=RecoveryState.RECOVERY_COMPLETE
    engine._trade_lifecycle_engine=None;engine.post_fill_lifecycle=PostFillLifecycleEngine("READ_ONLY")
    engine.strategy_allocation_authority=SimpleNamespace(recover_from_lifecycle=lambda _:None)
    engine.capital_authority=SimpleNamespace(recover_from_lifecycle=lambda _:None,recover_from_open_orders=lambda _:None)
    calls=[]
    def orders(): calls.append(1); return []
    engine._provider=SimpleNamespace(get_open_orders=orders)
    engine._recover_capital_state()
    assert engine._relationship_open_orders==[] and engine._relationship_orders_asof is not None
    assert len(calls)==1
    registry=ActiveTradeRegistry();registry.register_trade(ActiveTrade(symbol="FIXTURE",trader_type="MOMENTUM",entry_tick=1,
        entry_price=10.,quantity=8,direction="LONG",strategy_name="RossMomentumStrategyV1",stop_loss_price=9.))
    client=SimpleNamespace(positions=lambda:[SimpleNamespace(symbol="FIXTURE",quantity=8,con_id=123,avg_cost=10.)])
    harness=SimpleNamespace(run_mode=RunMode.PAPER,trade_management_engine=manager,execution_engine=engine,
        trade_registry=registry,connection_manager=SimpleNamespace(optional_client=client))
    CoreOrchestrator._resolve_position_truth_cycle(harness,as_of=datetime.now(timezone.utc))
    assert manager._relationship_plans["r"].reconciled and len(calls)==1
    engine._relationship_orders_asof-=timedelta(days=1)
    CoreOrchestrator._resolve_position_truth_cycle(harness,as_of=datetime.now(timezone.utc))
    assert manager._relationship_plans["r"].reconciled and len(calls)==2


def test_definitive_predispatch_block_releases_only_unsubmitted_milestone():
    from src.execution.execution_engine import ExecutionEngine
    from src.config.config_resolver import set_config_overrides
    manager,_=opened(8);intent=milestone(manager);plan=manager._relationship_plans["r"]
    set_config_overrides({"RUN_MODE":"READ_ONLY","RUN_MODE_EFFECTIVE":"READ_ONLY","EXECUTION_ENABLED":False,"EXECUTION_ENABLED_EFFECTIVE":False})
    try:
        engine=ExecutionEngine();engine.relationship_manager=manager
        result=engine.execute_trade(engine._risk_decision_from_intent(intent))
        assert not result.attempted
        assert plan.orders[intent.management_action_id]["terminal"]
        assert plan.milestone_filled==0 and not plan.milestone_consumed
        assert manager.reconcile_relationship("r",confirmed_quantity=8,pending_orders={},complete=True)
        retry=milestone(manager)
        assert retry.quantity==4 and retry.management_action_id!=intent.management_action_id
    finally: set_config_overrides(None)


def test_late_milestone_attempt_fill_cancels_oversized_retry_and_counts_once():
    manager,store=opened(8);first=milestone(manager);plan=manager._relationship_plans["r"]
    manager.on_relationship_order_update(relationship_id="r",order_id=first.management_action_id,
        cumulative_quantity=1,average_price=12.,terminal=True,status="Cancelled")
    manager.reconcile_relationship("r",confirmed_quantity=7,pending_orders={},complete=True)
    retry=milestone(manager);assert retry.quantity==3
    plan.orders[retry.management_action_id].update(broker_order_id="retry",request={"sent":True})
    calls=[];manager._cancel_order_callback=lambda **kw: calls.append(kw)
    manager.on_relationship_order_update(relationship_id="r",order_id=first.management_action_id,
        cumulative_quantity=2,average_price=12.,terminal=False,status="Submitted")
    assert plan.milestone_filled==2
    assert calls==[{"broker_order_id":"retry"}]
    assert not plan.orders[retry.management_action_id]["terminal"]
    manager.on_relationship_order_update(relationship_id="r",order_id=first.management_action_id,
        cumulative_quantity=2,average_price=12.,terminal=False,status="Submitted")
    assert len(calls)==1 and plan.milestone_filled==2
    manager.on_relationship_order_update(relationship_id="r",order_id=retry.management_action_id,
        cumulative_quantity=1,average_price=12.,terminal=True,status="Cancelled")
    assert plan.milestone_filled==3
    restored=TradeManagementEngine(persistence_adapter=store);restored.restore_relationship_state()
    assert restored.reconcile_relationship("r",confirmed_quantity=5,pending_orders={},complete=True)
    final=milestone(restored);assert final.quantity==1
    restored.on_relationship_order_update(relationship_id="r",order_id=final.management_action_id,
        cumulative_quantity=1,average_price=12.,terminal=True,status="Filled")
    assert restored._relationship_plans["r"].milestone_consumed


@pytest.mark.parametrize("terminal_status",["Cancelled","Inactive"])
def test_terminal_unchanged_partial_callback_releases_residual_reservations(terminal_status):
    from types import SimpleNamespace
    from src.execution.execution_engine import ExecutionEngine
    from src.brokers.base_broker import BrokerOrderRequest
    from src.core.orchestrator import CoreOrchestrator
    manager,_=opened(2);plan=manager._relationship_plans["r"]
    plan.orders["entry"].update(terminal=False,status="SUBMITTED",requested=5,broker_order_id="17")
    request=BrokerOrderRequest(client_order_id="entry",symbol="FIXTURE",direction="LONG",quantity=5,
        order_type="MKT",strategy_name="RossMomentumStrategyV1",relationship_context={"relationship_id":"r"})
    plan.orders["entry"]["request"]=asdict(request)
    engine=ExecutionEngine.__new__(ExecutionEngine);engine.relationship_manager=manager;engine.position_records={}
    engine._provider=SimpleNamespace(cached_order_update=lambda _: {"status":terminal_status,"filled":2,"remaining":3,"avgFillPrice":10.})
    engine._capital_decisions_by_order_id={"entry":"capital"}
    engine._strategy_allocation_decisions_by_order_id={"entry":"strategy"}
    released=[]
    engine.capital_authority=SimpleNamespace(release_reservation=lambda **kw: released.append(kw["decision_id"]))
    engine.strategy_allocation_authority=SimpleNamespace(release_reservation=lambda **kw: released.append(kw["decision_id"]))
    results=engine.collect_relationship_updates()
    CoreOrchestrator._apply_execution_results_to_trade_management(SimpleNamespace(trade_management_engine=manager),results)
    assert sorted(released)==["capital","strategy"]
    assert manager.snapshot_positions()["FIXTURE"].quantity==2
    assert engine.collect_relationship_updates()==[] and len(released)==2


@pytest.mark.parametrize("dispatched",[False,True])
def test_late_milestone_fill_prevents_unsent_retry_or_retries_failed_cancel(dispatched):
    manager,_=opened(8);first=milestone(manager);plan=manager._relationship_plans["r"]
    manager.on_relationship_order_update(relationship_id="r",order_id=first.management_action_id,
        cumulative_quantity=1,average_price=12.,terminal=True,status="Cancelled")
    manager.reconcile_relationship("r",confirmed_quantity=7,pending_orders={},complete=True)
    retry=milestone(manager);order=plan.orders[retry.management_action_id]
    calls=[]
    def cancel(**kw):
        calls.append(kw)
        if len(calls)==1: raise RuntimeError("offline failed cancel")
    manager._cancel_order_callback=cancel
    if dispatched: order.update(request={"sent":True},broker_order_id="retry")
    manager.on_relationship_order_update(relationship_id="r",order_id=first.management_action_id,
        cumulative_quantity=4,average_price=12.,terminal=True,status="Cancelled")
    assert plan.milestone_consumed and plan.milestone_filled==4
    if dispatched:
        assert not order["terminal"] and not order["cancel_requested"]
        manager.cancel_excess_milestone_orders(plan)
        manager.cancel_excess_milestone_orders(plan)
        assert len(calls)==2 and order["cancel_requested"] and not order["terminal"]
    else:
        assert order["terminal"] and order["status"]=="SUPERSEDED_BEFORE_DISPATCH"
        assert calls==[]


def test_completed_sim_partial_attempt_reconciles_without_future_callbacks(monkeypatch):
    from types import SimpleNamespace
    from datetime import datetime,timezone
    from src.execution.execution_engine import ExecutionEngine
    from src.core.orchestrator import CoreOrchestrator
    from src.core.active_trade_registry import ActiveTradeRegistry
    from src.brokers.sim_broker import SimBroker
    from src.brokers.base_broker import BrokerOrderRequest
    from src.execution.liquidity_engine import LiquidityEngine
    from src.config.runtime_config import RunMode
    from src.models.data_models import RiskDecision
    from src.sim.price_feed import DeterministicPriceFeed
    from src.config.config_resolver import set_config_overrides
    set_config_overrides({"RUN_MODE":"PAPER","RUN_MODE_EFFECTIVE":"PAPER","EXECUTION_ENABLED":True,
        "EXECUTION_ENABLED_EFFECTIVE":True,"IBKR_READONLY_ENABLED":False})
    try:
        manager=TradeManagementEngine();engine=ExecutionEngine()
        engine.relationship_manager=manager
        monkeypatch.setattr(LiquidityEngine,"available_liquidity",lambda **kw: 2)
        context={"relationship_id":"partial-sim","action":"ENTRY","security_id":"conId:123",
            "parent_id":"p","child_id":"c","profile":"BULL_FLAG_MICRO_2R_V1"}
        request=BrokerOrderRequest(client_order_id="sim-entry",symbol="FIXTURE",direction="LONG",quantity=5,
            order_type="MKT",trader_type="MOMENTUM",strategy_name="RossMomentumStrategyV1",stop_loss_price=1.,relationship_context=context)
        # Use the real deterministic liquidity implementation, with its gateway accepted.
        broker=engine._provider.broker if hasattr(engine._provider,"broker") else engine._provider._broker
        monkeypatch.setattr(broker,"place_order",lambda req: broker._execute_liquidity(req,0))
        releases=[]
        engine._release_capital_for_order=lambda *a,**kw: releases.append("capital")
        engine._release_strategy_allocation_for_order=lambda *a,**kw: releases.append("strategy")
        result=engine._route_order(request)
        assert result.status=="SIMULATED" and result.filled_quantity==2 and result.remaining_quantity==3
        harness=SimpleNamespace(run_mode=RunMode.SIM,trade_management_engine=manager,
            trade_registry=engine.trade_registry,execution_engine=engine)
        CoreOrchestrator._apply_execution_results_to_trade_management(harness,[result])
        CoreOrchestrator._resolve_position_truth_cycle(harness,as_of=datetime.now(timezone.utc))
        plan=manager._relationship_plans["partial-sim"]
        assert plan.entry_terminal and plan.reconciled and plan.e0>plan.original_stop
        assert sorted(releases)==["capital","strategy"]
        assert milestone_for_plan(manager,plan).quantity==1
    finally: set_config_overrides(None)


def milestone_for_plan(manager,plan):
    position=manager.snapshot_positions()[plan.symbol];position.current_price=plan.milestone_price
    return manager._relationship_milestone(position)
