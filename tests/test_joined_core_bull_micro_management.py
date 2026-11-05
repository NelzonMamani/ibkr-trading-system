"""Joined active-Core management investigation. Synthetic facts; no dispatch."""
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest

from src.config import config_resolver
from src.config.runtime_config import RunMode
from src.core.orchestrator import CoreOrchestrator
from src.core import orchestrator as core_module
from src.execution.execution_providers import PaperExecutionProvider
from src.ibkr.mutation_audit import snapshot as mutations
from test_broker_registry_exposure_admission import (
    _install_eligible_market_facts,no_external_activity,reassessment,lifecycle,_reset_config,
)
from test_joined_core_bull_micro import joined
from test_key_level_break_production_handoff import forbid_io


@pytest.mark.parametrize("position_case",["complete_empty","partial","unknown","five"])
def test_active_core_native_bull_micro_management_handoff(reassessment,monkeypatch,tmp_path,capsys,
        no_external_activity,position_case):
    # Retain real methods before inherited fixture startup stubs are installed.
    names=("_startup_recovery_allows_strategy_execution","_autonomous_recovery_allows_new_entries",
        "_daily_risk_allows_new_entries","_resolve_fill_authority_cycle",
        "_resolve_lifecycle_authority_cycle","_run_position_management_tick","_resolve_tha_decisions")
    real={n:getattr(CoreOrchestrator,n) for n in names}
    recovery_build=core_module.build_recovery_plan
    recovery_apply=core_module.apply_recovery_actions
    _install_eligible_market_facts(reassessment,monkeypatch)
    # External adapter construction boundary only: in-memory provider has real
    # empty startup inventory methods. No SDK client or broker is constructed.
    monkeypatch.setattr(core_module,"IbkrLiveBroker",lambda **kw:NS())
    providers=[]
    def provider_boundary(**kw):
        provider=PaperExecutionProvider(price_feed=NS(price_for=lambda *a:10.91,get_price=lambda *a:10.91),
            event_collector=core_module.EventCollector(),trade_registry=kw["trade_registry"],run_mode=kw["run_mode"])
        providers.append(provider)
        return provider
    monkeypatch.setattr(core_module,"IbkrExecutionProvider",provider_boundary)
    h=joined(reassessment,monkeypatch,tmp_path,position_case=position_case,
        runtime_options=dict(run_mode="PAPER",config_overrides=dict(EXECUTION_ENABLED=True,RISK_PROFILE="MICRO",
            IBKR_READONLY_ENABLED=False,IBKR_ORDER_SUBMISSION_ENABLED=True,
            IBKR_ORDER_TRANSLATION_ENABLED=True,IBKR_API_WRITE_ALLOWED=True)))
    for name,method in real.items(): monkeypatch.setattr(h.core,name,method.__get__(h.core))
    monkeypatch.setattr(core_module,"build_recovery_plan",recovery_build)
    monkeypatch.setattr(core_module,"apply_recovery_actions",recovery_apply)
    assert h.core.run_mode==RunMode.PAPER
    assert h.core.runtime_mode_manager.allow_orders
    assert h.core.execution_engine.startup_recovery_complete()
    assert h.core.execution_engine.relationship_manager is h.manager is h.strategy.relationship_manager
    assert h.core.risk_engine.relationship_manager is h.manager
    # Restore/count real admission owners instead of the inherited fixture's
    # execute/reserve tripwires. Only external dispatch remains forbidden.
    from src.execution.execution_engine import ExecutionEngine
    from src.risk.risk_engine import RiskEngine
    calls=[]
    admission=[]
    downstream=[]
    for authority,label in [(h.core.execution_engine.capital_authority,"capital"),
                            (h.core.execution_engine.strategy_allocation_authority,"allocation")]:
        reserve=type(authority).reserve.__get__(authority)
        def observe_reserve(*args,_reserve=reserve,_label=label,**kwargs):
            admission.append(_label)
            return _reserve(*args,**kwargs)
        monkeypatch.setattr(authority,"reserve",observe_reserve)
    for name in ("_run_trade_management_engine","_apply_execution_results_to_trade_management"):
        method=getattr(CoreOrchestrator,name).__get__(h.core)
        def observe_downstream(*args,_method=method,_name=name,**kwargs):
            downstream.append(_name)
            return _method(*args,**kwargs)
        monkeypatch.setattr(h.core,name,observe_downstream)
    execute=ExecutionEngine.execute_trade
    risk=RiskEngine.evaluate_trade_intent
    def observe_execute(decision):
        calls.append("execute")
        return execute(h.core.execution_engine,decision)
    def observe_risk(intent,**kwargs):
        calls.append("risk")
        return risk(h.core.risk_engine,intent,**kwargs)
    monkeypatch.setattr(h.core.execution_engine,"execute_trade",observe_execute)
    monkeypatch.setattr(h.core.risk_engine,"evaluate_trade_intent",observe_risk)
    def no_route(*args,**kwargs): pytest.fail("external dispatch forbidden")
    monkeypatch.setattr(h.core.execution_engine,"_route_order",no_route)
    try:
        assert h.core.run_once()
        first=capsys.readouterr().out
        h.life.clock.current+=timedelta(seconds=11)
        assert h.core.run_once()
        second=capsys.readouterr().out
        h.life.clock.current+=timedelta(seconds=11)
        assert h.core.run_once()
        repeated=capsys.readouterr().out
    finally:
        # Record BEFORE cleanup so release cannot hide unexpected admission.
        pending_capital=dict(h.core.execution_engine.capital_authority.active_reservations)
        pending_allocation=dict(h.core.execution_engine.strategy_allocation_authority.active_reservations)
        h.core.execution_engine.capital_authority.release_reservation(reason="OFFLINE_JOINED_PROOF_END")
        h.core.execution_engine.strategy_allocation_authority.release_reservation(reason="OFFLINE_JOINED_PROOF_END")
    assert pending_capital==pending_allocation=={}
    raw=[intent for batch in h.batches for intent in batch]
    print("JOINED_MANAGEMENT",position_case,"raw",len(raw),"calls",calls,
        "admission",admission,"downstream",downstream,"artifacts",len(h.artifacts))
    print(first+second+repeated)
    assert len(raw)==1
    assert raw[0].relationship_context["profile"]=="BULL_FLAG_MICRO_2R_V1"
    assert raw[0].entry_price==pytest.approx(10.91)
    assert raw[0].stop_loss_price==pytest.approx(10.81)
    assert raw[0].invalidation_level==pytest.approx(10.81)
    context=raw[0].relationship_context
    assert context["security_id"]=="conId:123" and context["action"]=="ENTRY"
    parent=next(p for p in h.manager._parents.values() if p["parent_id"]==context["parent_id"])
    assert parent["consumed_children"]==[context["child_id"]]
    assert "child_already_consumed" in repeated
    assert h.manager._relationship_plans=={} and h.manager.snapshot_positions()=={}
    assert h.core.execution_engine.position_records=={}
    assert h.core.trade_registry.snapshot()==[]
    assert admission==downstream==[]
    assert h.core.execution_engine.max_shares_per_order==1
    assert h.core.execution_engine.capital_authority.active_reservations=={}
    assert h.core.execution_engine.strategy_allocation_authority.active_reservations=={}
    assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}
    if position_case!="complete_empty":
        assert h.truth[-1][1].block_new_entries
        assert "POSITION_TRUTH_BLOCK_NEW_ENTRIES" in second
        assert "[PIPELINE][RISK_INPUT] intents_count=0" in second
        assert "ORDER_SUBMITTED" not in second
        assert h.artifacts==[] and calls==[]
    else:
        assert h.truth[-1][1].healthy and not h.truth[-1][1].block_new_entries
        assert "[PIPELINE][RISK_INPUT] intents_count=1" in second
        assert "[TRACE] stage=ORDER_SUBMITTED" in second
        assert h.artifacts==[] and calls==[]
        assert raw[0].decision_id is not None,"active PAPER raw intent never received canonical decision identity"
        assert h.artifacts and calls,"active PAPER artifact/risk/execution handoff absent"
