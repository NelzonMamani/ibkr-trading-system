"""Joined active-Core management investigation. Synthetic facts; no dispatch."""
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest

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


@pytest.mark.parametrize("position_case,transport",[
    ("complete_empty","submitted"),("partial","submitted"),("unknown","submitted"),
    ("five","submitted"),("quantity_warning_larger","submitted"),
    ("complete_empty","rejected"),("complete_empty","pending"),
    ("complete_empty","missing_id"),("complete_empty","error"),
    ("complete_empty","risk_denied"),("complete_empty","allocation_denied"),
    ("complete_empty","stop_after_risk"),("complete_empty","integrity_fault"),
    ("complete_empty","result_trace_error"),("complete_empty","native_timeout"),("complete_empty","native_submitted"),
    ("complete_empty","native_pending"),("complete_empty","native_rejected"),
    ("complete_empty","native_missing_id"),("complete_empty","native_unsupported"),
])
def test_active_core_native_bull_micro_management_handoff(reassessment,monkeypatch,tmp_path,capsys,
        no_external_activity,position_case,transport):
    native_provider=transport.startswith("native_")
    if native_provider and transport not in {"native_timeout","native_unsupported"}: transport=transport.removeprefix("native_")
    # Retain real methods before inherited fixture startup stubs are installed.
    names=("_startup_recovery_allows_strategy_execution","_autonomous_recovery_allows_new_entries",
        "_daily_risk_allows_new_entries","_resolve_fill_authority_cycle",
        "_resolve_lifecycle_authority_cycle","_run_position_management_tick","_resolve_tha_decisions")
    real={n:getattr(CoreOrchestrator,n) for n in names}
    recovery_build=core_module.build_recovery_plan
    recovery_apply=core_module.apply_recovery_actions
    _install_eligible_market_facts(reassessment,monkeypatch)
    if transport=="risk_denied":
        import test_joined_core_bull_micro as joined_module
        # Coherent external gap25 facts: Focus still eligible; unchanged Ross
        # max20 rejects through actual risk. Never replace the decision.
        facts=dict(prev_close=10.92/1.25,reference_price=10.92/1.25,
            ref_close_rth=10.92/1.25,gap_pct=25.,pct_change=25.)
        reassessment.row.update(facts)
        row_factory=joined_module._row
        def gap_row(symbol):
            row=row_factory(symbol)
            for key,value in facts.items(): setattr(row,key,value)
            return row
        monkeypatch.setattr(joined_module,"_row",gap_row)
    # External adapter construction boundary only: in-memory provider has real
    # empty startup inventory methods. No SDK client or broker is constructed.
    monkeypatch.setattr(core_module,"IbkrLiveBroker",lambda **kw:NS())
    providers=[]
    def provider_boundary(**kw):
        provider=PaperExecutionProvider(price_feed=NS(price_for=lambda *a:10.91,get_price=lambda *a:10.91),
            event_collector=core_module.EventCollector(),trade_registry=kw["trade_registry"],run_mode=kw["run_mode"])
        if native_provider:
            from src.execution.execution_providers import IbkrExecutionProvider
            # Actual native provider wrapper; only external broker inventory and
            # transport responses are synthetic. is_live/ack handling stay real.
            provider=IbkrExecutionProvider(broker=NS(positions=lambda:[],open_orders=lambda:[],
                connection_manager=NS(optional_client=None)),trade_registry=kw["trade_registry"],run_mode=kw["run_mode"])
        providers.append(provider)
        return provider
    monkeypatch.setattr(core_module,"IbkrExecutionProvider",provider_boundary)
    h=joined(reassessment,monkeypatch,tmp_path,position_case=position_case,
        runtime_options=dict(run_mode="PAPER",config_overrides=dict(EXECUTION_ENABLED=True,RISK_PROFILE="MICRO",
            IBKR_READONLY_ENABLED=False,IBKR_ORDER_SUBMISSION_ENABLED=True,
            IBKR_ORDER_TRANSLATION_ENABLED=True,IBKR_API_WRITE_ALLOWED=True,
            **({"STRATEGY_CAPITAL_ALLOCATIONS":{"ROSSMOMENTUMSTRATEGYV1":{"max_allocation_usd":1.0}}} if transport=="allocation_denied" else {}))))
    for name,method in real.items(): monkeypatch.setattr(h.core,name,method.__get__(h.core))
    monkeypatch.setattr(core_module,"build_recovery_plan",recovery_build)
    monkeypatch.setattr(core_module,"apply_recovery_actions",recovery_apply)
    assert h.core.run_mode==RunMode.PAPER
    assert h.core.runtime_mode_manager.allow_orders
    assert h.core.execution_engine.startup_recovery_complete()
    assert len(providers)==1 and h.core.execution_engine.provider is providers[0]
    assert h.core.execution_engine.relationship_manager is h.manager is h.strategy.relationship_manager
    assert h.core.risk_engine.relationship_manager is h.manager
    # Restore/count real admission owners instead of the inherited fixture's
    # execute/reserve tripwires. Only external dispatch remains forbidden.
    from src.execution.execution_engine import ExecutionEngine
    from src.risk.risk_engine import RiskEngine
    calls=[]
    risk_decisions=[]
    execution_results=[]
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
        result=execute(h.core.execution_engine,decision)
        execution_results.append(result)
        return result
    def observe_risk(intent,**kwargs):
        calls.append("risk")
        decision=risk(h.core.risk_engine,intent,**kwargs)
        risk_decisions.append(decision)
        if transport=="stop_after_risk":
            from src.core.stop_controller import StopMode
            h.core.stop_controller.request_stop(StopMode.GRACEFUL,"synthetic stop after real risk","offline-control")
        return decision
    monkeypatch.setattr(h.core.execution_engine,"execute_trade",observe_execute)
    monkeypatch.setattr(h.core.risk_engine,"evaluate_trade_intent",observe_risk)
    if transport=="integrity_fault":
        # Negative gate-fault control only: retain native formation, then
        # corrupt confirmation evidence to prove canonical admission rejects.
        # No internal success or RiskDecision is supplied.
        process=h.core.strategy_runner.process
        def corrupt_confirmation(**kwargs):
            out=process(**kwargs)
            if out:
                from src.config import config_resolver
                overrides=dict(config_resolver._CONFIG_OVERRIDES)
                overrides["SCANNER_DATA_SOURCE"]="MOCK"
                config_resolver.set_config_overrides(overrides)
                out[0].confirmation_passed=False
            return out
        monkeypatch.setattr(h.core.strategy_runner,"process",corrupt_confirmation)
    if transport=="result_trace_error":
        trace=h.core._trace_event
        def fail_after_result(stage,payload,summary=None):
            trace(stage,payload,summary)
            if stage=="EXECUTION_RESULT": raise RuntimeError("synthetic result trace failure")
        monkeypatch.setattr(h.core,"_trace_event",fail_after_result)
    from src.models.execution_result import ExecutionResult
    from copy import deepcopy
    sent=[]
    received=[]
    def offline_transport(request):
        if transport in {"risk_denied","allocation_denied","stop_after_risk","integrity_fault"}:
            pytest.fail("denied intent reached external transport boundary")
        sent.append(deepcopy(request))
        if transport=="error": raise OSError("synthetic transport uncertainty")
        result=ExecutionResult(symbol=request.symbol,trader_type=request.trader_type,
            attempted=transport not in {"rejected","result_trace_error"},status={"submitted":"Submitted","rejected":"REJECTED",
                "result_trace_error":"REJECTED","native_timeout":"TIMED_OUT","native_unsupported":"UNRECOGNIZED",
                "pending":"PendingSubmit","missing_id":"Submitted"}[transport],
            rationale="synthetic transport response",direction=request.direction,quantity=request.quantity,
            requested_quantity=request.quantity,filled_quantity=0,remaining_quantity=request.quantity,
            client_order_id=request.client_order_id,ibkr_order_id=None if transport in {"rejected","missing_id","result_trace_error"} else 71,
            acknowledged_at=h.life.clock.current.isoformat() if transport in {"submitted","pending"} else None)
        received.append(result)
        return result
    if native_provider:
        monkeypatch.setattr(providers[0].broker,"place_order",offline_transport,raising=False)
    else:
        monkeypatch.setattr(providers[0],"place_order",offline_transport)
    try:
        assert h.core.run_once()
        first=capsys.readouterr().out
        h.life.clock.current+=timedelta(seconds=11)
        if transport=="result_trace_error":
            h.core.run_once()  # Existing fault owner selects recovery/return policy.
            second=capsys.readouterr().out
            repeated=""
        else:
            assert h.core.run_once() is (transport!="stop_after_risk")
            second=capsys.readouterr().out
            h.life.clock.current+=timedelta(seconds=11)
            assert h.core.run_once() is (transport!="stop_after_risk")
            repeated=capsys.readouterr().out
    finally:
        # Record BEFORE cleanup so release cannot hide unexpected admission.
        pending_capital=deepcopy(h.core.execution_engine.capital_authority.active_reservations)
        pending_allocation=deepcopy(h.core.execution_engine.strategy_allocation_authority.active_reservations)
        h.core.execution_engine.capital_authority.release_reservation(reason="OFFLINE_JOINED_PROOF_END")
        h.core.execution_engine.strategy_allocation_authority.release_reservation(reason="OFFLINE_JOINED_PROOF_END")
    pending_expected=position_case=="complete_empty" and transport in {"submitted","pending","missing_id","error","native_timeout","native_unsupported"}
    assert bool(pending_capital)==bool(pending_allocation)==pending_expected
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
    assert parent["security_id"]==context["security_id"]
    assert parent["origin_timestamp"]==context["parent_origin"]
    assert parent["completed_timestamp"]==context["parent_completed"]
    assert context["child_timestamp"]==h.streams["10s"][-1].timestamp.isoformat()
    assert parent["consumed_children"]==[context["child_id"]]
    if transport not in {"stop_after_risk","integrity_fault","result_trace_error"}: assert "child_already_consumed" in repeated
    assert h.manager.snapshot_positions()=={}
    assert h.core.execution_engine.position_records=={}
    assert [vars(t) for t in h.core.trade_registry.snapshot()]==h.initial_registry
    assert h.core.execution_engine.max_shares_per_order==1
    assert h.core.execution_engine.capital_authority.active_reservations=={}
    assert h.core.execution_engine.strategy_allocation_authority.active_reservations=={}
    assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}
    if transport=="integrity_fault":
        assert "INTENT_REJECTED_BY_EXECUTION_INTEGRITY" in second
        assert h.artifacts==[] and calls==admission==sent==[]
        assert "[TRACE] stage=ORDER_SUBMITTED" not in second
    elif position_case!="complete_empty":
        assert h.truth[-1][1].block_new_entries
        assert "POSITION_TRUTH_BLOCK_NEW_ENTRIES" in second
        assert "[PIPELINE][RISK_INPUT] intents_count=0" in second
        assert "[TRACE] stage=ORDER_SUBMITTED" not in second
        assert h.artifacts==[] and calls==admission==sent==[]
        assert h.manager._relationship_plans=={}
    else:
        assert h.truth[-1][1].healthy and not h.truth[-1][1].block_new_entries
        assert "[PIPELINE][RISK_INPUT] intents_count=1" in second
        assert raw[0].decision_id is not None
        assert len(h.artifacts)==1 and calls.count("risk")==1
        artifact=h.artifacts[0][0]
        assert artifact.decision_id==raw[0].decision_id and artifact.run_mode=="PAPER"
        decision,=risk_decisions
        assert decision.decision_id==raw[0].decision_id
        assert decision.entry_price==raw[0].entry_price
        if transport!="risk_denied":
            assert decision.allowed and not decision.execution_blocked
            assert decision.max_position_size==1
            assert decision.stop_loss_price==raw[0].stop_loss_price
            assert decision.invalidation_level==raw[0].invalidation_level
            assert decision.relationship_context==context
            assert decision.execution_refinement_mode==raw[0].execution_refinement_mode
            assert decision.target_model==raw[0].target_model
        if transport=="risk_denied":
            assert calls==["risk"] and admission==sent==[]
            assert "ROSS_BLOCK_GAP_OUT_OF_RANGE" in second
            assert h.manager._relationship_plans=={}
        elif transport=="stop_after_risk":
            assert calls==["risk"] and admission==sent==[]
            assert "STOP_REQUESTED" in second
            assert h.manager._relationship_plans=={}
        elif transport=="allocation_denied":
            assert calls==["risk","execute"] and sent==admission==[]
            result,=execution_results
            assert not result.attempted and result.status=="BLOCKED"
            assert result.rationale.startswith("STRATEGY_ALLOC_")
            assert downstream.count("_apply_execution_results_to_trade_management")==1
            assert h.manager._relationship_plans=={}
        else:
            assert calls==["risk","execute"] and len(sent)==1
            assert admission==["allocation","capital"]
            request=sent[0]
            assert request.quantity==1
            assert request.stop_loss_price==pytest.approx(10.81)
            assert request.invalidation_level==pytest.approx(10.81)
            assert request.relationship_context==context
            assert request.target_model=="BULL_FLAG_MICRO_2R_V1"
            assert request.take_profit_price is None
            assert request.client_order_id.startswith(raw[0].decision_id)
            assert request.setup_family_id==raw[0].setup_family_id
            assert request.trigger_id==raw[0].trigger_id
            assert decision.evaluated_limits["trade_value"]==pytest.approx(10.91)
            if transport=="rejected":
                assert pending_capital==pending_allocation=={}
            if transport in {"error","native_timeout","native_unsupported"}:
                plan=h.manager._relationship_plans[context["relationship_id"]]
                assert plan.orders[request.client_order_id]["submission_uncertain_at"]
                assert pending_capital and pending_allocation
                if transport in {"native_timeout","native_unsupported"}:
                    assert execution_results[0].status=="SUBMISSION_UNKNOWN"
                    assert execution_results[0].ibkr_order_id==71
                    assert not plan.orders[request.client_order_id]["terminal"]
            assert downstream.count("_apply_execution_results_to_trade_management")==1
            assert "_run_trade_management_engine" not in downstream
        if transport=="submitted":
            assert "[TRACE] stage=ORDER_SUBMITTED" in second
            assert "order_submission_count=1" in second
        else:
            assert "[TRACE] stage=ORDER_SUBMITTED" not in second
            assert "[ORDER_SUBMITTED]" not in second
            if transport not in {"stop_after_risk","result_trace_error"}: assert "order_submission_count=0" in second

    if transport in {"rejected","result_trace_error"}:
        plan=h.manager._relationship_plans[context["relationship_id"]]
        order_id=sent[0].client_order_id
        assert plan.orders[order_id]["terminal"]
        if transport=="rejected":
            before=deepcopy(plan.orders[order_id])
            apply=CoreOrchestrator._apply_execution_results_to_trade_management.__get__(h.core)
            apply(execution_results)
            apply(execution_results)
            assert plan.orders[order_id]==before
            assert not plan.reconciled  # Existing conservative fresh-truth requirement.
            assert len(sent)==1 and calls==["risk","execute"]
            assert h.core.execution_engine.capital_authority.active_reservations=={}
            assert h.core.execution_engine.strategy_allocation_authority.active_reservations=={}
            assert h.manager.snapshot_positions()=={}
            assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}
