"""Joined active-Core management investigation. Synthetic facts; no dispatch."""
from datetime import timedelta, timezone
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
    ("complete_empty","native_late_fill"),("complete_empty","native_late_management_green_child"),
    *[("complete_empty","native_late_"+case) for case in
      ("pending","unrelated","negative","fractional","no_price","nan_price",
       *["assessment_"+stage for stage in ("before_allocation","allocation_audit_failure","before_capital","capital_audit_failure","allocation_error","accounting_error","processor_error","processor_after","completion_error","relationship_write_failure")],
       "collector_error","processor_error","processor_after","rejected","cancelled","partial",
       "missing_counts","unknown_status","oversize","uncertain","regression","accounting_error","allocation_error","completion_error","binding_error","stop_oversize","stop_bad_price","stop_bad_status","processor_cancel","processor_deadline","management","management_pending","management_uncertain",
       "management_unknown","management_unreconciled","management_no_protection","management_stale",
       "management_future","management_bad","management_daily_lock","management_protection_pending","management_protection_missing","management_forming","management_snapshot_failure",
       *["management_interleave_"+name for name in ("stop_before","stop_during_submit","cancel_delayed","cancel_rejected","cancel_late","uncertain_repeat","both_stop_first","both_reduce_first","both_same_cycle","duplicate_reorder","interrupted_reduce","identity_later","identity_ambiguous","identity_wrong_security","identity_fractional","identity_wrong_side","identity_absent","identity_decimal","identity_wrong_type","identity_protection_collision","identity_duplicate_native","reduction_cancel_rejected","reduction_cancel_uncertain","reduction_cancel_late_fill","invalid_version_bool","invalid_version_future","invalid_protective_bool","invalid_protective_future")])],
])
def test_active_core_native_bull_micro_management_handoff(reassessment,monkeypatch,tmp_path,capsys,
        no_external_activity,position_case,transport):
    green_child_case=transport=="native_late_management_green_child"
    if green_child_case:transport="native_late_management"
    late_fill=transport.startswith("native_late_")
    late_case=transport.removeprefix("native_late_") if late_fill else None
    assessment_case=late_case.removeprefix("assessment_") if late_case and late_case.startswith("assessment_") else None
    if assessment_case: late_case=assessment_case
    interleaving=late_case.removeprefix("management_interleave_") if late_case and late_case.startswith("management_interleave_") else None
    management_case=late_case is not None and late_case.startswith("management")
    stop_fault=late_case in {"stop_oversize","stop_bad_price","stop_bad_status"}
    malformed=late_case in {"negative","fractional","no_price","nan_price","missing_counts","unknown_status","oversize","binding_error"}
    failed_pass=bool(assessment_case) or malformed or late_case in {"collector_error","processor_error","processor_after","accounting_error","allocation_error","completion_error","processor_cancel","processor_deadline"}
    if late_fill: transport="native_timeout" if late_case=="uncertain" else "native_submitted"
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
    cached_facts={}
    broker_fills={72:0,73:0}  # Independent monotonic external position facts, not last status arrival.
    callback_reads=[]
    protection_requests=[]
    protective_orders=[]
    working_orders=[]
    cancelled_orders=set()
    cancel_requests=[]
    market_close=[11.10]
    management_fault_active=[False]
    cancel_mode=["confirmed"]
    def synthetic_cancel(**kwargs):
        cancel_requests.append(str(kwargs["broker_order_id"]))
        if cancel_mode[0]=="uncertain": raise OSError("synthetic cancel uncertainty")
        if cancel_mode[0] in {"delayed","rejected"}:
            return {"status":"PendingCancel" if cancel_mode[0]=="delayed" else "Rejected",
                    "broker_order_id":kwargs["broker_order_id"]}
        cancelled_orders.add(str(kwargs["broker_order_id"]))
        return {"status":"Cancelled","broker_order_id":kwargs["broker_order_id"]}
    def external_open_orders():
        if late_case=="management_snapshot_failure" and management_fault_active[0]:
            raise OSError("synthetic order snapshot unavailable")
        terminal=(str(cached_facts.get(71,{}).get("status","")).upper() in {"FILLED","REJECTED","CANCELLED"}
                  or (late_case=="regression" and bool(protection_requests)))
        if management_case:
            protection=[] if late_case=="management_protection_missing" else protective_orders
            return [o for o in protection+working_orders if str(o.orderId) not in cancelled_orders
                and str(cached_facts.get(o.orderId,{}).get("status","")).upper() not in {"FILLED","REJECTED","CANCELLED"}]
        return list(protective_orders)+(list(working_orders) if not terminal else [])
    def cached_status(order_id):
        callback_reads.append(order_id)
        if late_case=="collector_error" and cached_facts:
            raise RuntimeError("synthetic cached callback read failure")
        return dict(cached_facts.get(order_id,{}))
    def unexpected_protection(**kwargs):
        protection_requests.append(kwargs)
        assert late_fill and cached_facts[71]["filled"]==1
        assert not malformed, "malformed callback must not reach protection"
        assert kwargs["quantity"]==1 and kwargs["stop_price"]==pytest.approx(10.81)
        protective_orders.append(NS(orderId=72,contract=NS(symbol="JPM"),
            order=NS(orderType="STP",parentId=71,orderRef="",action="SELL",totalQuantity=1,auxPrice=10.81),
            orderState=NS(status="PendingSubmit" if late_case=="management_protection_pending" else "Submitted")))
        return {"broker_order_id":None if late_case=="management_no_protection" else "72",
            "status":"Rejected" if late_case=="management_no_protection" else ("PendingSubmit" if late_case=="management_protection_pending" else "Submitted"),"order_type":"STP"}
    def provider_boundary(**kw):
        provider=PaperExecutionProvider(price_feed=NS(price_for=lambda *a:10.91,get_price=lambda *a:10.91),
            event_collector=core_module.EventCollector(),trade_registry=kw["trade_registry"],run_mode=kw["run_mode"])
        if native_provider:
            from src.execution.execution_providers import IbkrExecutionProvider
            # Actual native provider wrapper; only external broker inventory and
            # transport responses are synthetic. is_live/ack handling stay real.
            from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionManager, IbkrConnectionConfig
            manager=IbkrConnectionManager(IbkrConnectionConfig('offline',0,999,5,'LIVE',True,'PAPER'))
            manager._client=NS(cached_order_status=cached_status,is_connected=lambda:True)
            for method in ('connect','ensure_connected','get_client','_connect_locked'):
                monkeypatch.setattr(manager,method,lambda *a,**k:pytest.fail('Implicit provider connection forbidden'))
            provider=IbkrExecutionProvider(broker=NS(positions=lambda:[],open_orders=external_open_orders,
                connection_manager=manager,
                place_stop_order=unexpected_protection,cancel_order=synthetic_cancel),trade_registry=kw["trade_registry"],run_mode=kw["run_mode"])
        providers.append(provider)
        return provider
    monkeypatch.setattr(core_module,"IbkrExecutionProvider",provider_boundary)
    h=joined(reassessment,monkeypatch,tmp_path,position_case=position_case,
        runtime_options=dict(run_mode="PAPER",config_overrides=dict(EXECUTION_ENABLED=True,RISK_PROFILE="MICRO",
            IBKR_READONLY_ENABLED=False,IBKR_ORDER_SUBMISSION_ENABLED=True,
            IBKR_ORDER_TRANSLATION_ENABLED=True,IBKR_API_WRITE_ALLOWED=True,
            **({"STRATEGY_CAPITAL_ALLOCATIONS":{"ROSSMOMENTUMSTRATEGYV1":{"max_allocation_usd":1.0}}} if transport=="allocation_denied" else {}))))
    if green_child_case:
        from dataclasses import replace
        # Same external child high/low and all prior management assertions;
        # only the pause colour/shape changes to the supported green hammer.
        h.streams["10s"][-2]=replace(h.streams["10s"][-2],open=10.89,close=10.90)
    # One fixed external clock for snapshot coherence; never renew evidence.
    from src.execution import execution_engine as execution_module
    monkeypatch.setattr(execution_module,"datetime",h.life.clock)
    if late_fill:
        from src.ibkr.position_snapshot import BrokerPositionResult
        def external_positions():
            held=(bool(assessment_case) or management_case or late_case in {"fill","partial","uncertain","regression","processor_error","processor_after","stop_oversize","stop_bad_price","stop_bad_status","management"}) and bool(cached_facts) and not (management_case and cached_facts.get(73,{}).get("filled")==1)
            quantity=(1-sum(broker_fills.values())) if interleaving and cached_facts else int(held)
            rows=(NS(symbol="JPM",position=quantity,con_id=123,avgCost=10.91,account="SYNTHETIC_TEST"),) if quantity else ()
            return BrokerPositionResult(rows,"UNAVAILABLE" if late_case=="management_unknown" and management_fault_active[0]
                else "COMPLETE","SYNTHETIC_TEST",h.life.clock.now(timezone.utc))
        h.core.connection_manager._ibkr_connection_manager.existing_client.position_snapshot=external_positions
    if management_case:
        from src.ibkr.market_data_client import HistoricalDataResult
        from src.execution import trade_management_engine as management_module
        emit=h.core.event_collector.emit
        def fixed_clock_emit(*args,**kwargs):
            kwargs.setdefault("timestamp",h.life.clock.now(timezone.utc))
            return emit(*args,**kwargs)
        monkeypatch.setattr(h.core.event_collector,"emit",fixed_clock_emit)
        def external_history(*args,**kwargs):
            now=h.life.clock.current
            bars=tuple(NS(open=market_close[0]-.10,high=market_close[0]+.01,low=10.80,
                close=market_close[0]-.01*(2-i),volume=1000.,timestamp=now-timedelta(minutes=3-i)) for i in range(3))
            if management_fault_active[0]:
                if late_case=="management_stale":
                    bars=tuple(NS(**dict(vars(b),timestamp=b.timestamp-timedelta(hours=2))) for b in bars)
                if late_case=="management_future": bars[-1].timestamp=now+timedelta(minutes=1)
                if late_case=="management_forming": bars[-1].timestamp=now-timedelta(seconds=1)
                if late_case=="management_bad": bars[-1].low=-1.
            return HistoricalDataResult("COMPLETE_BARS",bars,end_received=True)
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
    callback_drains=[]
    callback_results=[]
    collect=h.core.execution_engine.collect_relationship_updates
    def observe_collect(**kwargs):
        callback_drains.append(True)
        results=collect(**kwargs)
        callback_results.extend(deepcopy(results))
        return results
    monkeypatch.setattr(h.core.execution_engine,"collect_relationship_updates",observe_collect)
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
        reducing=management_case and request.direction=="SELL"
        if reducing and interleaving=="stop_during_submit":
            cached_facts[72]={"status":"Filled","filled":1,"remaining":0,"avgFillPrice":10.81}
            broker_fills[72]=1
        if reducing and (late_case=="management_uncertain" or interleaving=="uncertain_repeat"):
            working_orders.append(NS(orderId=73,contract=NS(symbol=request.symbol),
                order=NS(orderType="MKT",parentId=0,orderRef=request.client_order_id,action="SELL",totalQuantity=1),
                orderState=NS(status="PendingSubmit")))
            h.life.clock.current+=timedelta(microseconds=1)
            raise OSError("synthetic unresolved management submission")
        if reducing and interleaving and interleaving.startswith("identity_"):
            # Canonical inventory reports an unresolved working order, not an
            # authoritative absence that could legitimately resolve uncertainty.
            working_orders.append(NS(orderId=73,contract=NS(symbol=request.symbol,conId=123),
                order=NS(orderType="MKT",parentId=0,orderRef="",action="SELL",totalQuantity=1),
                orderState=NS(status="PendingSubmit")))
        result=ExecutionResult(symbol=request.symbol,trader_type=request.trader_type,
            attempted=transport not in {"rejected","result_trace_error"},status={"submitted":"Submitted","rejected":"REJECTED",
                "result_trace_error":"REJECTED","native_timeout":"TIMED_OUT","native_unsupported":"UNRECOGNIZED",
                "pending":"PendingSubmit","missing_id":"Submitted"}[transport] if not (reducing and late_case=="management_pending") else "PendingSubmit",
            rationale="synthetic transport response",direction=request.direction,quantity=request.quantity,
            requested_quantity=request.quantity,filled_quantity=0,remaining_quantity=request.quantity,
            client_order_id=request.client_order_id,ibkr_order_id=None if transport in {"rejected","missing_id","result_trace_error"} or (reducing and interleaving and interleaving.startswith("identity_")) else (73 if reducing else 71),
            acknowledged_at=h.life.clock.current.isoformat() if transport in {"submitted","pending"} else None)
        if native_provider and result.ibkr_order_id and result.status.upper() not in {"REJECTED","FAILED"}:
            working_orders.append(NS(orderId=result.ibkr_order_id,contract=NS(symbol=request.symbol),
                order=NS(orderType="MKT",parentId=0,orderRef=request.client_order_id,action=request.direction,totalQuantity=1),
                orderState=NS(status="Submitted")))
        received.append(result)
        return result
    if native_provider:
        monkeypatch.setattr(providers[0].broker,"place_order",offline_transport,raising=False)
    else:
        monkeypatch.setattr(providers[0],"place_order",offline_transport)
    assessment_error=None
    if interleaving and interleaving.startswith("invalid_version_"):
        build=h.core.execution_engine._order_from_risk_decision
        def corrupt_retained_version(*args,**kwargs):
            request=build(*args,**kwargs)
            if request.direction=="SELL":
                owned_plan=h.manager._relationship_plans[request.relationship_context["relationship_id"]]
                owned_plan.orders[request.client_order_id]["owner_effect_version"]=True if interleaving.endswith("bool") else 999
                decision=args[0] if args else kwargs["risk_decision"]
                owned_plan.orders[request.client_order_id]["decision_id"]=decision.decision_id
                h.manager._save_relationship_state()
            return request
        monkeypatch.setattr(h.core.execution_engine,"_order_from_risk_decision",corrupt_retained_version)
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
            if late_fill:
                # Submission is actual Core/risk/execution; only a later native
                # callback fact is supplied at the existing external cache seam.
                raw_now=[i for batch in h.batches for i in batch]
                assert len(raw_now)==1 and len(sent)==1 and len(h.artifacts)==1
                if green_child_case:
                    assert len(h.strategy._pattern_registry.patterns)==33
                    assert raw_now[0].setup_metadata['source_metadata']['pullback_variant']=='SINGLE_GREEN_LOWER_WICK'
                    assert any(child.detected and child.setup_metadata.get('pullback_variant')=='SINGLE_GREEN_LOWER_WICK'
                        for source,child in h.children)

                plan=h.manager._relationship_plans[raw_now[0].relationship_context["relationship_id"]]
                assert plan.entry_quantity==0 and not plan.entry_terminal
                assert plan.e0 is None and plan.milestone_price is None
                assert h.manager.snapshot_positions()=={}
                assert h.core.execution_engine.post_fill_lifecycle.get_trade(plan.initial_order_id) is None
                assert protection_requests==[]
                assert h.core.execution_engine.capital_authority.active_reservations
                assert h.core.execution_engine.strategy_allocation_authority.active_reservations
                assert execution_results[0].filled_quantity==0
                if management_case: assert downstream.count("_run_trade_management_engine")==0
                initial_integrity=h.core.execution_engine.execution_integrity_flag
                initial_trace_missing=sorted({"SUBMIT","ACK","FILL"}-h.core.execution_engine._order_trace_stages.get(sent[0].client_order_id,set()))
                if late_case=="uncertain":
                    assert execution_results[0].status=="SUBMISSION_UNKNOWN"
                    assert plan.orders[sent[0].client_order_id]["submission_uncertain_at"]
                else: assert execution_results[0].acknowledged_at
                assert sent[0].client_order_id.startswith(raw_now[0].decision_id)
                assert raw_now[0].decision_id==h.artifacts[0][0].decision_id==risk_decisions[0].decision_id
                assert str(plan.orders[sent[0].client_order_id]["broker_order_id"])=="71"
                assert sent[0].relationship_context==raw_now[0].relationship_context
                assert plan.parent_id==raw_now[0].relationship_context["parent_id"]
                parent=next(p for p in h.manager._parents.values() if p["parent_id"]==plan.parent_id)
                assert parent["consumed_children"]==[raw_now[0].relationship_context["child_id"]]
                assert sent[0].quantity==1 and h.core.execution_engine.max_shares_per_order==1
                assert sent[0].stop_loss_price==pytest.approx(10.81)
                facts={"status":"Filled","filled":1,"remaining":0,"avgFillPrice":10.91}
                if late_case=="pending": facts.update(status="PendingSubmit",filled=0,remaining=1,avgFillPrice=0)
                if late_case=="negative": facts.update(filled=-1)
                if late_case=="fractional": facts.update(filled=1.5)
                if late_case=="no_price": facts.pop("avgFillPrice")
                if late_case=="nan_price": facts.update(avgFillPrice=float("nan"))
                if late_case=="missing_counts": facts.pop("filled")
                if late_case=="unknown_status": facts.update(status="UNVERIFIED")
                if late_case=="oversize": facts.update(filled=2)
                if late_case=="rejected": facts.update(status="Rejected",filled=0,remaining=1,avgFillPrice=0)
                if late_case=="cancelled": facts.update(status="Cancelled",filled=0,remaining=1,avgFillPrice=0)
                if late_case=="partial": facts.update(status="Submitted")
                cached_facts[99 if late_case=="unrelated" else 71]=facts
                if management_case:
                    h.core.connection_manager._client=NS(intraday_bars_from_history=external_history)
                    monkeypatch.setattr(management_module,"datetime",h.life.clock)
                if assessment_case in {"before_allocation","before_capital"}:
                    def before_effect(*args,**kwargs): raise RuntimeError("synthetic evidence interruption")
                    monkeypatch.setattr(h.core.execution_engine,
                        "_convert_strategy_allocation_for_fill" if assessment_case=="before_allocation" else "_convert_capital_for_fill",before_effect)
                if assessment_case in {"allocation_audit_failure","capital_audit_failure"}:
                    owner=(h.core.execution_engine.strategy_allocation_authority if assessment_case=="allocation_audit_failure"
                        else h.core.execution_engine.capital_authority)
                    audit=owner._audit
                    def failed_audit_boundary(event_type,**payload):
                        if event_type=="EXPOSURE": raise RuntimeError("synthetic evidence interruption")
                        return audit(event_type,**payload)
                    monkeypatch.setattr(owner,"_audit",failed_audit_boundary)
                if assessment_case=="relationship_write_failure":
                    write=h.core.storage_engine.store_management_state
                    def failed_relationship_write(state_id,payload):
                        if payload["plans"][plan.relationship_id]["orders"][plan.initial_order_id]["filled"]==1:
                            raise RuntimeError("synthetic relationship state persistence failure")
                        return write(state_id,payload)
                    monkeypatch.setattr(h.core.storage_engine,"store_management_state",failed_relationship_write)
                if late_case=="binding_error":
                    # Negative retained-request corruption: never a permission patch.
                    plan.orders[sent[0].client_order_id]["request"]["client_order_id"]="wrong-occurrence"
                if late_case=="completion_error":
                    save=h.manager._save_relationship_state
                    def completion_failure():
                        entry=plan.orders[sent[0].client_order_id]
                        if entry["filled"]==1 and not entry.get("cached_update_in_progress"):
                            raise RuntimeError("synthetic completion persistence failure")
                        return save()
                    monkeypatch.setattr(h.manager,"_save_relationship_state",completion_failure)
                if late_case=="accounting_error":
                    log=h.core.execution_engine._execution_log
                    def accounting_failure(stage,**kwargs):
                        log(stage,**kwargs)
                        if stage=="FILL": raise RuntimeError("synthetic post-accounting diagnostic failure")
                    monkeypatch.setattr(h.core.execution_engine,"_execution_log",accounting_failure)
                if late_case=="allocation_error":
                    convert=h.core.execution_engine._convert_strategy_allocation_for_fill
                    def allocation_failure(*args,**kwargs):
                        convert(*args,**kwargs)
                        raise RuntimeError("synthetic partial-accounting failure")
                    monkeypatch.setattr(h.core.execution_engine,"_convert_strategy_allocation_for_fill",allocation_failure)
                if late_case in {"processor_error","processor_after","processor_cancel","processor_deadline"}:
                    apply=h.core._apply_execution_results_to_trade_management
                    def processing_failure(results):
                        if any(r.rationale=="CACHED_BROKER_CALLBACK" for r in results):
                            if late_case=="processor_after": apply(results)
                            if late_case in {"processor_cancel","processor_deadline"}:
                                from src.core.acquisition import AcquisitionCancelled,AcquisitionDeadlineExceeded
                                raise (AcquisitionCancelled if late_case=="processor_cancel" else AcquisitionDeadlineExceeded)()
                            raise RuntimeError("synthetic cached result processor failure")
                        return apply(results)
                    monkeypatch.setattr(h.core,"_apply_execution_results_to_trade_management",processing_failure)
            h.life.clock.current+=timedelta(seconds=11)
            if late_case=="processor_cancel":
                from src.core.acquisition import AcquisitionCancelled
                with pytest.raises(AcquisitionCancelled): h.core.run_once()
                result=None
            else: result=h.core.run_once()
            if not failed_pass: assert result is (transport!="stop_after_risk")
            repeated=capsys.readouterr().out
            if late_case in {"accounting_error","allocation_error","processor_error","processor_after","completion_error","processor_cancel","processor_deadline"}:
                # Negative owner-level replay probe only. Core is halted; no
                # admission or recovery permission is patched to resume it.
                before=(h.core.execution_engine.capital_authority.symbol_exposure("JPM"),
                    h.core.execution_engine.strategy_allocation_authority.strategy_used_exposure("RossMomentumStrategyV1"))
                with pytest.raises(RuntimeError,match="CACHED_EXECUTION_UPDATE_RECOVERY_REQUIRED"):
                    collect()
                assert before==(h.core.execution_engine.capital_authority.symbol_exposure("JPM"),
                    h.core.execution_engine.strategy_allocation_authority.strategy_used_exposure("RossMomentumStrategyV1"))
            if late_fill and not failed_pass:
                if late_case=="regression":
                    # Older nonterminal status must not reopen confirmed fill truth.
                    cached_facts[71].update(status="PendingCancel",filled=0,remaining=1,avgFillPrice=0)
                if stop_fault:
                    cached_facts[72]={"status":"UNVERIFIED" if late_case=="stop_bad_status" else "Filled",
                        "filled":2 if late_case=="stop_oversize" else 1,"remaining":0,
                        "avgFillPrice":True if late_case=="stop_bad_price" else 10.81}
                # Same cumulative external cache on the next real cycle.
                h.life.clock.current+=timedelta(seconds=11)
                repeated_result=h.core.run_once()
                if not stop_fault and late_case!="management_no_protection": assert repeated_result
                repeated+=capsys.readouterr().out
                if management_case:
                    assert plan.entry_terminal
                    if late_case!="management_no_protection": assert plan.reconciled
                    assert len(sent)==1 and not plan.milestone_consumed
                    if interleaving:
                        _exercise_stop_reduction_interleaving(h=h,plan=plan,case=interleaving,
                            cached=cached_facts,broker_fills=broker_fills,working_orders=working_orders,sent=sent,market_close=market_close,cancel_mode=cancel_mode,
                            cancelled=cancelled_orders,cancels=cancel_requests,capsys=capsys,tmp_path=tmp_path,
                            monkeypatch=monkeypatch,no_external_activity=no_external_activity)
                        return  # Existing finally still releases isolated test ledgers after captured assertions.
                    market_close[0]=plan.milestone_price
                    management_fault_active[0]=True
                    if late_case=="management_snapshot_failure":
                        h.life.clock.current+=timedelta(seconds=16)  # Expire prior canonical protection evidence.
                    if late_case=="management_unreconciled":
                        working_orders.append(NS(orderId=99,contract=NS(symbol="JPM"),
                            order=NS(orderType="MKT",parentId=0,orderRef="unrelated",action="SELL",totalQuantity=1),
                            orderState=NS(status="Submitted")))
                        h.life.clock.current+=timedelta(seconds=16)  # Normal snapshot expiry, no forced refresh.
                    if late_case=="management_daily_lock":
                        from test_p10_daily_risk_governor import _record_closed_trade
                        from src.config import config_resolver
                        config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,
                            DAILY_RISK_MAX_LOSS_AMOUNT=10.,DAILY_RISK_EXISTING_POSITION_POLICY="MANAGED_ONLY"))
                        _record_closed_trade(h.core.event_collector,-11.,timestamp=h.life.clock.current,trade_id="synthetic-loss")
                    h.life.clock.current+=timedelta(seconds=1)
                    h.core.run_once()
                    repeated+=capsys.readouterr().out
                    blocked=late_case in {"management_unknown","management_unreconciled","management_no_protection",
                        "management_stale","management_future","management_bad","management_protection_pending","management_protection_missing","management_snapshot_failure"}
                    assert len(sent)==(1 if blocked else 2), "active Core recurring management authority mismatch"
                    if not blocked:
                        for _ in range(2):
                            h.life.clock.current+=timedelta(seconds=1)
                            h.core.run_once()
                            repeated+=capsys.readouterr().out
                        assert len(sent)==2 and not plan.milestone_consumed
                        if late_case in {"management","management_daily_lock"}:
                            cached_facts[73]={"status":"Filled","filled":1,"remaining":0,"avgFillPrice":market_close[0]}
                            h.life.clock.current+=timedelta(seconds=1)
                            h.core.run_once()
                            repeated+=capsys.readouterr().out
                            h.life.clock.current+=timedelta(seconds=1)
                            h.core.run_once()
                            repeated+=capsys.readouterr().out
    finally:
        if assessment_case:
            try:
                _assess_retained_execution_evidence(h=h,plan=plan,stage=assessment_case,
                    cached=cached_facts,protection_requests=protection_requests,tmp_path=tmp_path,
                    no_external_activity=no_external_activity)
            except BaseException as exc:
                assessment_error=exc  # Isolated ledger cleanup must still run on an evidence assertion failure.
        # Record BEFORE cleanup so release cannot hide unexpected admission.
        pending_capital=deepcopy(h.core.execution_engine.capital_authority.active_reservations)
        pending_allocation=deepcopy(h.core.execution_engine.strategy_allocation_authority.active_reservations)
        h.core.execution_engine.capital_authority.release_reservation(reason="OFFLINE_JOINED_PROOF_END")
        h.core.execution_engine.strategy_allocation_authority.release_reservation(reason="OFFLINE_JOINED_PROOF_END")
        # Isolated fixture teardown only; retain BEFORE values for assertions.
        used_capital=h.core.execution_engine.capital_authority.symbol_exposure("JPM")
        used_allocation=h.core.execution_engine.strategy_allocation_authority.strategy_used_exposure("RossMomentumStrategyV1")
        if used_capital:
            h.core.execution_engine.capital_authority.release_exposure(symbol="JPM",notional=used_capital,
                strategy_id="RossMomentumStrategyV1",reason="OFFLINE_JOINED_PROOF_END")
        if used_allocation:
            h.core.execution_engine.strategy_allocation_authority.release_exposure(strategy_id="RossMomentumStrategyV1",
                notional=used_allocation,reason="OFFLINE_JOINED_PROOF_END")
    if assessment_error is not None: raise assessment_error
    if assessment_case: return  # Evidence assertions run before isolated ledger teardown.
    if management_case:
        blocked=late_case in {"management_unknown","management_unreconciled","management_no_protection",
            "management_stale","management_future","management_bad","management_protection_pending","management_protection_missing","management_snapshot_failure"}
        if blocked:
            assert len(sent)==1 and plan.milestone_order_id is None
        else:
            assert sent[1].direction=="SELL" and sent[1].quantity==1
            assert sent[1].relationship_context["relationship_id"]==plan.relationship_id
            parent=next(p for p in h.manager._parents.values() if p["parent_id"]==plan.parent_id)
            assert parent["consumed_children"]==[sent[0].relationship_context["child_id"]]
            assert plan.original_stop==pytest.approx(10.81) and plan.e0==pytest.approx(10.91)
            management_result,=[r for r in execution_results if (r.relationship_context or {}).get("action")=="REDUCE"]
            assert management_result.filled_quantity==0  # Later callback, never the acknowledgement, proves reduction.
            assert h.core.execution_engine.submission_confirmed(management_result)==(late_case not in {"management_pending","management_uncertain"})
            if late_case in {"management","management_daily_lock"}:
                assert plan.milestone_consumed and plan.milestone_filled==1
                assert h.manager.snapshot_positions()=={} and h.core.trade_registry.snapshot()==[]
                assert used_capital==used_allocation==0
                assert cancelled_orders=={"72"} and cancel_requests==["72"] and len(sent)==2
                assert plan.parent_id==sent[0].relationship_context["parent_id"]
                assert sent[1].client_order_id==plan.milestone_order_id and plan.milestone_quantity==1
            else:
                assert not plan.milestone_consumed and h.manager.snapshot_positions()["JPM"].quantity==1
                assert used_capital==used_allocation==pytest.approx(10.91)
            if late_case=="management_daily_lock": assert "DAILY_RISK][BLOCK_NEW_ENTRIES" in repeated
        if late_case=="management_snapshot_failure":
            assert not plan.reconciled and h.core.execution_engine._relationship_orders_asof is None
            assert h.core.execution_engine._relationship_open_orders  # Old rows retained but cannot grant authority.
        if late_case!="management_no_protection":
            assert len(callback_drains)==len(h.truth)  # One ingestion per complete active cycle.
        else:
            assert len(callback_drains)>=len(h.truth)  # Existing protection failure aborts before truth.

        assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}
        return
    if late_fill:
        # Failing-before requirement, not a helper invocation/permission patch.
        # Preserve the precise missing active-Core callback lifecycle evidence.
        print("LATE_FILL_BOUNDARY",dict(cached_status="Filled",cached_quantity=1,
            callback_drains=len(callback_drains),callback_reads=len(callback_reads),
            management_cycles=downstream.count("_run_trade_management_engine"),
            result_processing=downstream.count("_apply_execution_results_to_trade_management"),
            entry_quantity=plan.entry_quantity,entry_terminal=plan.entry_terminal,
            frozen=plan.e0 is not None,protection_requests=len(protection_requests),
            initial_integrity=initial_integrity,initial_trace_missing=initial_trace_missing,
            pending_capital=bool(pending_capital),pending_allocation=bool(pending_allocation),
            requests=len(sent),risk_calls=calls.count("risk"),artifacts=len(h.artifacts)))
        assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}
        assert h.core.execution_engine.capital_authority.active_reservations=={}
        assert h.core.execution_engine.strategy_allocation_authority.active_reservations=={}
        assert callback_drains, "active Core never drains existing native terminal-fill cache"
        assert len(sent)==len(h.artifacts)==calls.count("risk")==1
        assert h.core.execution_engine.capital_authority.symbol_exposure("JPM")==0
        assert h.core.execution_engine.strategy_allocation_authority.strategy_used_exposure("RossMomentumStrategyV1")==0
        if failed_pass:
            if not malformed and late_case!="collector_error":
                assert plan.orders[sent[0].client_order_id]["cached_update_in_progress"]["filled"]==1
                assert plan.paused
            assert h.core.execution_engine.execution_integrity_flag
            assert cached_facts  # External cumulative evidence was not consumed/destructively popped.
            assert len(h.truth)==2  # Abort before position reconciliation or another admission.
            if malformed or late_case=="collector_error":
                assert plan.entry_quantity==0 and h.core.execution_engine.position_records=={}
                assert protection_requests==[] and pending_capital and pending_allocation
                assert used_capital==used_allocation==0
            elif late_case in {"accounting_error","allocation_error"}:
                assert plan.entry_quantity==0 and h.core.execution_engine.position_records=={}
                assert used_allocation==pytest.approx(10.91) and not pending_allocation
                assert used_capital==pytest.approx(10.91 if late_case=="accounting_error" else 0)
                assert bool(pending_capital)==(late_case=="allocation_error")
                assert protection_requests==[]
            else:
                # Real execution accounting/protection may precede processor failure;
                # preserve those facts, rather than manufacture rollback/release.
                assert h.core.execution_engine.position_records[sent[0].client_order_id]["filled_qty"]==1
                assert len(protection_requests)==1
                assert plan.entry_quantity==int(late_case in {"processor_after","completion_error"})
                assert used_capital==used_allocation==pytest.approx(10.91)
                assert not pending_capital and not pending_allocation
            return
        if stop_fault:
            assert len(h.truth)==3  # Malformed stop evidence aborts before reconciliation.
            assert h.core.execution_engine.execution_integrity_flag
            assert h.manager.snapshot_positions()["JPM"].quantity==1
            assert len(h.core.execution_engine.position_records)==1
            assert plan.entry_quantity==1 and len(plan.orders)==1
            assert used_capital==used_allocation==pytest.approx(10.91)
            assert len(protection_requests)==1
            return
        if late_case in {"pending","unrelated","rejected","cancelled"}:
            assert plan.entry_quantity==0 and h.core.execution_engine.position_records=={}
            assert protection_requests==[] and plan.e0 is None
            assert used_capital==used_allocation==0
            assert bool(pending_capital)==bool(pending_allocation)==(late_case in {"pending","unrelated"})
            return
        # Preserve any pre-existing pending-order trace flag; ingestion cannot
        # grant permission or clear integrity merely because a later fill arrives.
        assert h.core.execution_engine.execution_integrity_flag==initial_integrity
        assert len(h.truth)==4
        assert plan.entry_quantity==1
        assert plan.entry_terminal is (late_case!="partial")
        assert plan.entry_notional==pytest.approx(10.91)
        assert h.manager.snapshot_positions()["JPM"].quantity==1
        assert len(protection_requests)==1  # Repeated cache/cycles cannot duplicate protection.
        assert h.core.execution_engine.position_records[sent[0].client_order_id]["filled_qty"]==1
        assert len(h.core.trade_registry.snapshot())==1 and h.core.trade_registry.snapshot()[0].quantity==1
        assert not pending_capital and not pending_allocation
        assert used_capital==used_allocation==pytest.approx(10.91)
        callback,=[r for r in callback_results if r.filled_quantity]
        assert callback.client_order_id==sent[0].client_order_id and str(callback.ibkr_order_id)=="71"
        assert float(callback.average_fill_price)==pytest.approx(10.91)
        assert callback.relationship_context==sent[0].relationship_context
        assert callback.stop_loss_price==sent[0].stop_loss_price
        assert plan.orders[sent[0].client_order_id]["request"]["invalidation_level"]==pytest.approx(10.81)
        snapshot,verdict=h.truth[-1]
        assert snapshot.system_positions["JPM"].quantity==snapshot.broker_positions["JPM"].quantity==1
        assert verdict.healthy
        assert plan.reconciled is (late_case!="partial")
        protection=h.core.execution_engine.post_fill_lifecycle.get_trade(plan.initial_order_id)
        assert protection.filled_qty==protection.stop.quantity==1
        assert protection.stop.trigger_price==pytest.approx(10.81) and protection.target is None
        if late_case!="partial":
            assert plan.e0==pytest.approx(10.91) and plan.r0==pytest.approx(.10)
            assert plan.milestone_price==pytest.approx(plan.e0+2*plan.r0)
        assert len(sent)==1  # Evaluation with missing market state cannot dispatch a reduction.
        assert not plan.milestone_consumed and plan.milestone_quantity is None
        return  # Callback ingestion proof, not recurring 2R management certification.
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
    if native_provider and transport=="submitted":
        # Acknowledgement is submission evidence, never authoritative fill truth.
        plan=h.manager._relationship_plans[context["relationship_id"]]
        assert plan.entry_quantity==0 and not plan.entry_terminal
        assert plan.e0 is None and plan.r0 is None and plan.milestone_price is None
        assert not plan.milestone_consumed
        assert h.core.execution_engine.post_fill_lifecycle.get_trade(plan.initial_order_id) is None
        assert protection_requests==[]
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


@pytest.mark.parametrize("mode",["READ_ONLY","SIM","LIVE"])
def test_cached_ingestion_does_not_activate_other_modes(reassessment,monkeypatch,tmp_path,
        no_external_activity,mode):
    _install_eligible_market_facts(reassessment,monkeypatch)
    h=joined(reassessment,monkeypatch,tmp_path,position_case="complete_empty",
        runtime_options={"run_mode":mode})
    def forbidden():
        pytest.fail("PAPER callback handoff must not activate another mode")
    monkeypatch.setattr(h.core.execution_engine,"collect_relationship_updates",forbidden)
    assert h.core.run_once()
    assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}


@pytest.mark.parametrize("kind",["stop","deadline"])
def test_management_history_acquisition_control_flow(monkeypatch,no_external_activity,kind):
    from src.core.acquisition import AcquisitionCancelled,AcquisitionDeadlineExceeded
    error=AcquisitionCancelled if kind=="stop" else AcquisitionDeadlineExceeded
    def interrupted(*args,**kwargs): raise error()
    core=CoreOrchestrator.__new__(CoreOrchestrator)
    core.connection_manager=NS(optional_client=NS(intraday_bars_from_history=interrupted))
    with pytest.raises(error): core._get_trade_management_recent_candles("SYNTHETIC",10)
    assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}


def _exercise_stop_reduction_interleaving(*,h,plan,case,cached,broker_fills,working_orders,sent,market_close,cancel_mode,
        cancelled,cancels,capsys,tmp_path,monkeypatch,no_external_activity):
    """External cumulative facts only. Never equate broker sells with local clamps."""
    import json
    from copy import deepcopy
    states=[]
    engine=h.core.execution_engine
    accounting_calls=[]
    for label,authority in (("capital",engine.capital_authority),("allocation",engine.strategy_allocation_authority)):
        release=authority.release_exposure
        def observed_release(*args,_release=release,_label=label,**kwargs):
            accounting_calls.append(dict(owner=_label,arguments=deepcopy(kwargs)))
            return _release(*args,**kwargs)
        monkeypatch.setattr(authority,"release_exposure",observed_release)
    def snapshot(stage,result=None):
        life=engine.post_fill_lifecycle.get_trade(plan.protection_trade_id or plan.initial_order_id)
        broker_sells=sum(broker_fills.values())
        position=h.manager.snapshot_positions().get("JPM")
        state=dict(stage=stage,result=result,relationship=plan.relationship_id,
            requests=[dict(id=r.client_order_id,side=r.direction,quantity=r.quantity,
                relationship=(r.relationship_context or {}).get("relationship_id")) for r in sent],
            broker_sells=broker_sells,broker_net=1-broker_sells,
            local_quantity=position.quantity if position else 0,
            registry=[dict(symbol=t.symbol,quantity=t.quantity) for t in h.core.trade_registry.snapshot()],
            capital=engine.capital_authority.symbol_exposure("JPM"),
            allocation=engine.strategy_allocation_authority.strategy_used_exposure("RossMomentumStrategyV1"),
            reservations=deepcopy(engine.capital_authority.active_reservations),
            allocation_reservations=deepcopy(engine.strategy_allocation_authority.active_reservations),
            reconciled=plan.reconciled,paused=plan.paused,pending_cancel=plan.pending_stop_cancel,
            pending_resize=plan.pending_stop_resize,milestone_consumed=plan.milestone_consumed,
            lifecycle_qty=life.filled_qty if life else None,
            lifecycle_state=str(life.state) if life else None,
            stop_status=str(life.stop.status) if life and life.stop else None,
            stop_quantity=life.stop.quantity if life and life.stop else None,
            orders=deepcopy(plan.orders),callbacks=deepcopy(cached),cancels=list(cancels),
            failsafe=engine._failsafe_block_new_entries,
            truth_block=h.truth[-1][1].block_new_entries,truth_exit_block=h.truth[-1][1].block_exits,
            accounting_calls=deepcopy(accounting_calls),
            canonical_orders_asof=str(getattr(engine,"_relationship_orders_asof",None)),
            canonical_orders=[vars(row) if not isinstance(row,dict) else row for row in getattr(engine,"_relationship_open_orders",[])])
        states.append(state)
        return state
    def cycle(stage):
        h.life.clock.current+=timedelta(seconds=1)
        result=h.core.run_once()
        output=capsys.readouterr().out
        state=snapshot(stage,result)
        state["diagnostics"]=[line for line in output.splitlines() if any(tag in line for tag in
            ("EXIT_FILL_REJECTED","ERROR","HALT","RECONCILIATION][SUMMARY"))][-12:]
        return state
    def filled(order_id,price):
        broker_fills[order_id]=1
        cached[order_id]=dict(status="Filled",filled=1,remaining=0,avgFillPrice=price)
    try:
        assert len(sent)==1 and sent[0].quantity==1
        assert plan.reconciled and plan.entry_terminal and plan.e0==pytest.approx(10.91)
        assert engine.capital_authority.active_reservations=={}
        snapshot("filled_owned_protected_below_2R")
        market_close[0]=plan.milestone_price
        if case.startswith("invalid_protective_"):
            plan.orders[plan.initial_order_id]["owner_effect_version"]=True if case.endswith("bool") else 999
            h.manager._save_relationship_state()
            filled(72,10.81)
        if case=="stop_before": filled(72,10.81)
        first=cycle("threshold")
        assert len(sent)==(1 if case=="stop_before" or case.startswith("invalid_") else 2)
        if case.startswith("invalid_"):
            cycle("invalid_schema_remains_blocked")
            assert len(sent)==1 and not plan.milestone_consumed
            target=plan.orders[plan.initial_order_id if case.startswith("invalid_protective_") else plan.milestone_order_id]
            assert type(target["owner_effect_version"]) is (bool if case.endswith("bool") else int)
            assert target["owner_effect_version"]==(True if case.endswith("bool") else 999)
            if case.startswith("invalid_protective_"):
                assert not any((o.get("request",{}).get("relationship_context") or {}).get("protective_stop_fill") for o in plan.orders.values())
                assert engine.capital_authority.symbol_exposure("JPM")==pytest.approx(10.91)
        elif case=="stop_before":
            cycle("duplicate_stop")
            assert len(sent)==1 and plan.milestone_order_id is None
        else:
            assert sent[1].direction=="SELL" and sent[1].quantity==1
            assert sent[1].relationship_context["relationship_id"]==plan.relationship_id
            assert sent[1].client_order_id==plan.milestone_order_id
            if case.startswith("cancel_"):
                cancel_mode[0]="rejected" if case=="cancel_rejected" else "uncertain" if case=="cancel_late" else "delayed"
            if case=="interrupted_reduce":
                apply=h.core._apply_execution_results_to_trade_management
                def interrupted(results):
                    apply(results)
                    if any(r.filled_quantity and str(r.ibkr_order_id)=="73" for r in results):
                        raise RuntimeError("synthetic interruption after reduction processing")
                monkeypatch.setattr(h.core,"_apply_execution_results_to_trade_management",interrupted)
            if case.startswith("identity_") or case.startswith("reduction_cancel_"):
                if case.startswith("reduction_cancel_"):
                    cancel_mode[0]="uncertain" if case=="reduction_cancel_uncertain" else "rejected"
                filled(72,10.81)
                cycle("stop_exhausts_owned_position")
                owned=plan.orders[plan.milestone_order_id]
                assert not owned["terminal"]
                if case.startswith("identity_"):
                    assert not owned.get("broker_order_id") and "73" not in cancels
                    working_orders.clear()  # Later external snapshot resolves or contradicts the opaque order.
                    from decimal import Decimal
                    for native_id in ([] if case=="identity_absent" else [73,74] if case=="identity_ambiguous" else [72] if case=="identity_protection_collision" else [73]):
                        working_orders.append(NS(orderId=native_id,contract=NS(symbol="JPM",conId=999 if case=="identity_wrong_security" else 123),
                            order=NS(orderType="STP" if case=="identity_wrong_type" else "MKT",parentId=0,orderRef=plan.milestone_order_id,
                                action="BUY" if case=="identity_wrong_side" else "SELL",
                                totalQuantity=1.5 if case=="identity_fractional" else Decimal("1") if case=="identity_decimal" else 1),orderState=NS(status="Submitted")))
                    if case=="identity_duplicate_native":
                        working_orders.append(NS(orderId=73,contract=NS(symbol="OTHER",conId=999),
                            order=NS(orderType="MKT",parentId=0,orderRef="different-order",action="SELL",totalQuantity=1),
                            orderState=NS(status="Submitted")))
                    h.life.clock.current+=timedelta(seconds=16)
                    cycle("fresh_canonical_identity_evidence")
                    if case in {"identity_later","identity_decimal"}:
                        assert owned["broker_order_id"]=="73" and cancels==["73"]
                    elif case=="identity_absent":
                        assert owned["terminal"] and owned["status"]=="RECONCILED_ABSENT" and not cancels
                    else:
                        assert not owned.get("broker_order_id") and not cancels
                elif case=="reduction_cancel_uncertain":
                    assert not owned.get("cancel_requested") and not owned["terminal"]
                    cancel_mode[0]="confirmed"
                    cycle("retry_existing_cancel_after_transport_failure")
                    assert owned["cancel_requested"] and not owned["terminal"]
                else:
                    assert cancels==["73"] and owned["cancel_requested"] and not owned["terminal"]
                if case=="reduction_cancel_late_fill":
                    filled(73,plan.milestone_price)
                    cycle("late_fill_despite_cancel_rejection")
                elif case in {"identity_later","identity_decimal","reduction_cancel_rejected","reduction_cancel_uncertain"}:
                    cached[73]=dict(status="Cancelled",filled=0,remaining=1,avgFillPrice=0)
                    cycle("authoritative_reduction_terminal_without_fill")
                    assert owned["terminal"] and owned["filled"]==0
            elif case in {"both_stop_first","stop_during_submit"}:
                filled(72,10.81)
                cycle("stop_fill_while_reduction_working")
                if case=="both_stop_first":
                    filled(73,plan.milestone_price)
                    cycle("late_reduction_fill")
            elif case=="both_same_cycle":
                filled(72,10.81);filled(73,plan.milestone_price)
                cycle("both_terminal_facts")
            elif case!="uncertain_repeat":
                filled(73,plan.milestone_price)
                cycle("reduction_fill")
                if case=="both_reduce_first":
                    filled(72,10.81)
                    cycle("late_stop_fill_after_cancel_response")
            accounting_before_repeats=deepcopy(accounting_calls)
            cycle("repeat1")
            cycle("repeat2")
            assert accounting_calls==accounting_before_repeats
            if case=="duplicate_reorder":
                cached[73]=dict(status="PendingCancel",filled=0,remaining=1,avgFillPrice=0)
                cycle("delayed_older_status")
                filled(73,plan.milestone_price)
                cycle("duplicate_terminal")
            if case.startswith("cancel_"):
                assert plan.pending_stop_cancel=="72"  # Requests/failed replies are not cancellation proof.
                if case=="cancel_late":
                    cached[72]=dict(status="Cancelled",filled=0,remaining=1,avgFillPrice=0)
                    cancelled.add("72")  # Independent later canonical absence, not the cancel request.
                    cycle("late_cancel_and_canonical_absence")
            assert len(sent)==2  # No unsafe resubmission, even when callbacks contradict.
        final=snapshot("final_before_fixture_cleanup")
        assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}
        # Every non-entry request stays bound to the actual relationship.
        assert all((r.relationship_context or {}).get("relationship_id")==plan.relationship_id for r in sent)
        if case=="uncertain_repeat":
            assert not plan.milestone_consumed and final["local_quantity"]==1
            assert final["capital"]==final["allocation"]==pytest.approx(10.91) and cancels==[]
            assert any(o.get("submission_uncertain_at") and not o["terminal"] for o in plan.orders.values())
        if case=="stop_before":
            assert final["broker_net"]==final["local_quantity"]==final["lifecycle_qty"]==0
            assert final["capital"]==final["allocation"]==0
            assert sum(o["filled"] for o in plan.orders.values() if o["action"]=="EXIT")==1
            assert cancels==[]
            assert sum(c["owner"]=="capital" for c in accounting_calls)==1
        if case in {"cancel_delayed","cancel_rejected"}:
            assert final["local_quantity"]==final["lifecycle_qty"]==0 and final["capital"]==0
            assert final["pending_cancel"]=="72" and not final["reconciled"]
            assert "72" not in cancelled and set(cancels)=={"72"}
            assert final["stop_status"]==("Rejected" if case=="cancel_rejected" else "PendingCancel")
        if case=="cancel_late":
            assert final["pending_cancel"] is None and final["reconciled"]
            assert "72" in cancelled and final["local_quantity"]==0
        if case=="duplicate_reorder":
            assert final["local_quantity"]==final["lifecycle_qty"]==final["capital"]==0
            assert final["broker_net"]==0 and plan.milestone_consumed
            assert cancels==["72"] and plan.orders[plan.milestone_order_id]["filled"]==1
            assert accounting_calls==accounting_before_repeats
        if case not in {"uncertain_repeat"}:
            assert not final["reservations"] and not final["allocation_reservations"]
        if case=="stop_during_submit":
            assert final["broker_net"]==0 and final["local_quantity"]==0
            assert not plan.orders[plan.milestone_order_id]["terminal"]
            assert plan.orders[plan.milestone_order_id]["broker_order_id"]=="73"
            if "73" not in cancels:
                raise StopReductionSafetyGap("stop fill leaves confirmed outstanding reduction uncancelled")
        if case.startswith("both_") or case=="reduction_cancel_late_fill":
            assert final["broker_sells"]==2 and final["broker_net"]==-1
            assert sum(o["filled"] for o in plan.orders.values() if o["action"] in {"EXIT","REDUCE"})==2
            assert final["local_quantity"]==final["lifecycle_qty"]==0
            assert final["capital"]==final["allocation"]==0
            assert final["truth_block"] and not final["reconciled"]  # Existing downstream critical safeguard.
            assert sum(c["owner"]=="capital" for c in accounting_calls)==2
            assert sum(c["owner"]=="allocation" for c in accounting_calls)==2
            if not plan.paused:
                raise StopReductionSafetyGap("excess SELL evidence is accepted without owner recovery latch")
            rejected=[o for o in plan.orders.values() if o.get("lifecycle_application_rejected")]
            assert len(rejected)==1 and rejected[0]["lifecycle_application_rejected"]["error"]=="qty_exceeds_open"
            assert rejected[0].get("cached_update_in_progress")
            assert not engine.startup_recovery_complete() and engine._failsafe_block_new_entries
            assert engine.startup_recovery_block_reason()=="RELATIONSHIP_EXIT_APPLICATION_REJECTED"
            before=deepcopy((engine.position_records,plan.orders,len(accounting_calls)))
            with pytest.raises(RuntimeError,match="CACHED_EXECUTION_UPDATE_RECOVERY_REQUIRED"):
                engine.collect_relationship_updates()
            assert before==deepcopy((engine.position_records,plan.orders,len(accounting_calls)))
            from src.execution.trade_management_engine import TradeManagementEngine
            restored=TradeManagementEngine(persistence_adapter=h.manager._persistence,
                state_namespace=h.manager._state_namespace.removeprefix("ross-bull-micro:"))
            restored.restore_relationship_state()
            saved=restored._relationship_plans[plan.relationship_id]
            assert saved.paused and any(o.get("lifecycle_application_rejected") for o in saved.orders.values())
            assert sum(o["filled"] for o in saved.orders.values() if o["action"] in {"EXIT","REDUCE"})==2
        if case=="interrupted_reduce":
            assert any(o.get("cached_update_in_progress") for o in plan.orders.values())
            before=deepcopy((engine.position_records,plan.orders,final["capital"]))
            with pytest.raises(RuntimeError,match="CACHED_EXECUTION_UPDATE_RECOVERY_REQUIRED"):
                engine.collect_relationship_updates()
            assert before==deepcopy((engine.position_records,plan.orders,engine.capital_authority.symbol_exposure("JPM")))
        _assess_interleaving_recovery_evidence(h=h,plan=plan,case=case,states=states,tmp_path=tmp_path)
    finally:
        (tmp_path/"interleaving-summary.json").write_text(json.dumps(dict(case=case,states=states),default=str,sort_keys=True))
        with capsys.disabled():
            print("INTERLEAVING",case,json.dumps([{k:v for k,v in s.items() if k in {
                "stage","broker_sells","broker_net","local_quantity","capital","reconciled","paused",
                "lifecycle_qty","stop_status","pending_cancel","failsafe","truth_block"}} for s in states],sort_keys=True))


class StopReductionSafetyGap(AssertionError):
    """Retained demonstrated invariant failure; no production correction authorized."""


def _assess_retained_execution_evidence(*,h,plan,stage,cached,protection_requests,tmp_path,no_external_activity):
    """Test-only assessment. Live observations are NEVER durable application proof."""
    import json
    import sqlite3
    from copy import deepcopy
    from src.execution.trade_management_engine import TradeManagementEngine
    from src.execution.execution_engine import ExecutionEngine
    from src.core.capital_management_authority import CapitalManagementAuthority
    from src.core.strategy_capital_allocation_authority import StrategyCapitalAllocationAuthority
    engine=h.core.execution_engine
    storage=h.core.storage_engine
    assert storage.enabled and storage.backend=="sqlite"
    # A separate read-only connection sees committed records, not a writer's
    # uncommitted buffers or the manager's current in-memory values.
    with sqlite3.connect(f"file:{storage.sqlite_path}?mode=ro",uri=True) as db:
        db.row_factory=sqlite3.Row
        row=db.execute("SELECT reason FROM position_lifecycle_transitions WHERE transition_id=?",
            (h.manager._state_namespace,)).fetchone()
        durable=json.loads(row[0])
        capital=[dict(r) for r in db.execute("SELECT * FROM capital_audit_events")]
        allocation=[dict(r) for r in db.execute("SELECT * FROM strategy_allocation_audit_events")]
        lifecycle=[dict(r) for r in db.execute("SELECT * FROM trade_lifecycle_events")]
        stops=[dict(r) for r in db.execute("SELECT * FROM stop_authority_events")]
    saved=durable["plans"][plan.relationship_id]
    saved_order=saved["orders"][plan.initial_order_id]
    assert saved_order["request"]["client_order_id"]==plan.initial_order_id
    assert saved_order["request"]["relationship_context"]["relationship_id"]==plan.relationship_id
    assert cached[71]==dict(status="Filled",filled=1,remaining=0,avgFillPrice=10.91)
    external_positions=h.core.connection_manager._ibkr_connection_manager.existing_client.position_snapshot()
    assert external_positions.status=="COMPLETE" and external_positions.rows[0].position==1
    cap_effects=[r for r in capital if r["event_type"]=="EXPOSURE" and r["order_id"]==plan.initial_order_id]
    alloc_effects=[r for r in allocation if r["event_type"]=="EXPOSURE" and r["order_id"]==plan.initial_order_id]
    assert all(r["status"]=="CONVERTED" for r in cap_effects+alloc_effects)
    assert all(r["trade_id"]==plan.initial_order_id for r in cap_effects+alloc_effects)
    assert all(r["exposure_before"]==0 and r["exposure_after"]==pytest.approx(10.91) for r in cap_effects)
    assert all(r["used_exposure"]==pytest.approx(10.91) for r in alloc_effects)
    # Only a positive post-mutation audit receipt could establish conversion.
    # Active facade lacks that API; absence must remain UNKNOWN.
    cap_class="APPLIED" if cap_effects else "UNKNOWN"
    alloc_class="APPLIED" if alloc_effects else "UNKNOWN"
    exact_exec=f"{plan.relationship_id}:{plan.initial_order_id}:1"
    managed=(saved_order["filled"]==1 and saved_order["notional"]==pytest.approx(10.91)
        and exact_exec in durable["seen_exec_ids"])
    management_class="APPLIED" if managed else "UNKNOWN"
    assert engine.capital_authority.storage_engine is storage
    assert engine.strategy_allocation_authority.storage_engine is storage
    assert not hasattr(storage,"insert_capital_audit_event")
    assert not hasattr(storage,"insert_strategy_allocation_audit_event")
    assert not cap_effects and not alloc_effects  # Active facade does not wire the lower-store audit API.
    assert managed==(stage in {"processor_after","completion_error"})
    stop_required=[r for r in stops if r["event_type"]=="STOP_REQUIRED" and r["lifecycle_trade_id"]==plan.initial_order_id]
    stop_ack=[r for r in stops if r["event_type"]=="STOP_ACKNOWLEDGED" and r["lifecycle_trade_id"]==plan.initial_order_id]
    assert bool(stop_required)==bool(stop_ack)==(stage in {"processor_error","processor_after","completion_error","relationship_write_failure"})
    assert all(r["entry_order_id"]==plan.initial_order_id and r["quantity"]==1 for r in stop_required+stop_ack)
    assert all(r["active_stop_order_id"]=="72" and r["stop_price"]==pytest.approx(10.81) for r in stop_ack)
    # Positive local lifecycle/ack audit is historical application proof, not
    # current broker protection or complete registry/exposure certification.
    assert saved_order.get("cached_update_in_progress")  # A progress record is not a completion receipt.
    assert plan.paused
    restored=TradeManagementEngine(persistence_adapter=storage,
        state_namespace=h.manager._state_namespace.removeprefix("ross-bull-micro:"))
    restored.restore_relationship_state()
    restored_order=restored._relationship_plans[plan.relationship_id].orders[plan.initial_order_id]
    assert restored_order["cached_update_in_progress"]==saved_order["cached_update_in_progress"]
    assert not restored._relationship_plans[plan.relationship_id].reconciled
    # Fresh owner objects have empty projections despite positive durable
    # historical receipts. Do not misclassify that as historical UNAPPLIED.
    assert CapitalManagementAuthority(storage_engine=storage).total_used_exposure==0
    assert StrategyCapitalAllocationAuthority(storage_engine=storage).strategy_used_exposure("RossMomentumStrategyV1")==0
    def forbidden_reader(*args,**kwargs): pytest.fail("restored recovery record reached callback reader")
    fresh=ExecutionEngine.__new__(ExecutionEngine)
    fresh._native_orders={};fresh._native_scope=None;fresh._native_quarantined=False
    fresh.relationship_manager=restored
    fresh._provider=NS(cached_order_update=forbidden_reader)
    with pytest.raises(RuntimeError,match="CACHED_EXECUTION_UPDATE_RECOVERY_REQUIRED"):
        fresh.collect_relationship_updates()
    assert storage.fetch_management_state(h.manager._state_namespace)==durable
    live=dict(capital=engine.capital_authority.symbol_exposure("JPM"),
        allocation=engine.strategy_allocation_authority.strategy_used_exposure("RossMomentumStrategyV1"),
        capital_reservations=deepcopy(engine.capital_authority.active_reservations),
        allocation_reservations=deepcopy(engine.strategy_allocation_authority.active_reservations),
        manager_quantity=h.manager.snapshot_positions().get("JPM").quantity if h.manager.snapshot_positions().get("JPM") else 0,
        registry=[vars(t) for t in h.core.trade_registry.snapshot()],
        position_records=deepcopy(engine.position_records),protective_requests=deepcopy(protection_requests),
        plan_paused=plan.paused,durable_paused=saved["paused"])
    report=dict(stage=stage,external_callbacks=deepcopy(cached),external_position_status=external_positions.status,
        external_position_rows=[vars(r) for r in external_positions.rows],
        classification=dict(capital_conversion=cap_class,allocation_conversion=alloc_class,
            capital_reservation_conversion=cap_class,allocation_reservation_conversion=alloc_class,
            canonical_management_processing=management_class,registry_update="UNKNOWN",
            lifecycle_creation="APPLIED" if stop_required else "UNKNOWN",
            stop_acknowledgement="APPLIED" if stop_ack else "UNKNOWN",
            current_broker_protection="UNKNOWN"),
        committed=dict(management=durable,capital_audit=capital,allocation_audit=allocation,lifecycle_events=lifecycle,stop_audit=stops),
        live_control_oracle_only=live)
    # Explicit counterexample vector: both independently run controls retain
    # these same role-bound recovery facts but one conversion mutated memory.
    if stage in {"before_allocation","allocation_audit_failure"}:
        vector=dict(progress=saved_order["cached_update_in_progress"],filled=saved_order["filled"],
            notional=saved_order["notional"],management_applied=managed,
            capital_receipts=len(cap_effects),allocation_receipts=len(alloc_effects))
        assert vector==dict(progress=dict(filled=1,remaining=0,status="FILLED",average_price=10.91),
            filled=0,notional=0.0,management_applied=False,capital_receipts=0,allocation_receipts=0)
        assert live["allocation"]==pytest.approx(0 if stage=="before_allocation" else 10.91)
        assert alloc_class=="UNKNOWN"  # Missing row must not become zero-effect proof.
        report["role_bound_counterexample_vector"]=vector
    if stage in {"before_allocation","allocation_audit_failure"}:
        _verify_fresh_process_recovery_guard(storage.sqlite_path,h.manager._state_namespace,plan.relationship_id)
    (tmp_path/"execution-evidence-assessment.json").write_text(json.dumps(report,default=str,sort_keys=True))
    _assert_owner_effect_inspection_preserves_latches(h,plan)
    assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}


def _verify_fresh_process_recovery_guard(path,namespace,relationship_id):
    """A bounded real Python restart, SQLite read-only, no owner recovery/run."""
    import subprocess
    import sys
    script='''
import sqlite3,sys
from types import SimpleNamespace
from src.storage.storage_engine import StorageEngine
from src.execution.trade_management_engine import TradeManagementEngine
from src.execution.execution_engine import ExecutionEngine
from src.core.capital_management_authority import CapitalManagementAuthority
storage=StorageEngine.__new__(StorageEngine)
storage.enabled=True;storage.backend="sqlite"
storage._store=SimpleNamespace(connection=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True))
manager=TradeManagementEngine(persistence_adapter=storage,state_namespace=sys.argv[2].removeprefix("ross-bull-micro:"))
manager.restore_relationship_state()
plan=manager._relationship_plans[sys.argv[3]]
assert not plan.reconciled and any(o.get("cached_update_in_progress") or o.get("lifecycle_application_rejected") for o in plan.orders.values())
assert CapitalManagementAuthority().total_used_exposure==0
engine=ExecutionEngine.__new__(ExecutionEngine);engine.relationship_manager=manager
engine._native_orders={};engine._native_scope=None;engine._native_quarantined=False
engine._provider=SimpleNamespace(cached_order_update=lambda *a: (_ for _ in ()).throw(AssertionError("external reader reached")))
try: engine.collect_relationship_updates()
except RuntimeError as exc: assert str(exc)=="CACHED_EXECUTION_UPDATE_RECOVERY_REQUIRED"
else: raise AssertionError("restored latch did not block")
storage._store.connection.close()
print("RESTORED_RECOVERY_GUARD_PASS")
'''
    result=subprocess.run([sys.executable,"-c",script,str(path),namespace,relationship_id],
        capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    assert "RESTORED_RECOVERY_GUARD_PASS" in result.stdout


def test_recovery_identical_sqlite_records_can_hide_different_applied_management(monkeypatch,tmp_path,no_external_activity):
    """Two isolated counterfactual instances, never replay/clear a failed update."""
    import json
    import shutil
    import sqlite3
    from src.storage.storage_engine import StorageEngine
    from src.storage.sqlite_store import SQLiteStore
    from src.execution.trade_management_engine import TradeManagementEngine
    from src.models.execution_result import ExecutionResult
    def storage_at(path):
        store=SQLiteStore(str(path));store.initialize_schema()
        storage=StorageEngine.__new__(StorageEngine)
        storage.enabled=True;storage.backend="sqlite";storage._store=store;storage.run_id=None
        return storage
    baseline=tmp_path/"baseline.sqlite"
    storage=storage_at(baseline)
    manager=TradeManagementEngine(persistence_adapter=storage)
    assert manager.register_relationship_order(relationship_id="synthetic-r",symbol="SYNTHETIC",security_id="conId:123",
        parent_id="synthetic-p",child_id="synthetic-c",order_id="synthetic-o",quantity=1,stop=10.81)
    initial=storage.fetch_management_state(manager._state_namespace)
    storage._store.close()
    independent=dict(order="synthetic-o",relationship="synthetic-r",filled=1,average_price=10.91,
        positions=(dict(symbol="SYNTHETIC",con_id=123,quantity=1),),completion="COMPLETE")
    retained=[];live=[]
    for branch in ("before_effect","after_effect_write_failure"):
        path=tmp_path/(branch+".sqlite");shutil.copyfile(baseline,path)
        branch_storage=storage_at(path)
        owner=TradeManagementEngine(persistence_adapter=branch_storage);owner.restore_relationship_state()
        fact=ExecutionResult(symbol="SYNTHETIC",trader_type="SYNTHETIC",attempted=True,status="Filled",
            rationale="synthetic external callback",direction="LONG",filled_quantity=1,remaining_quantity=0,
            average_fill_price=10.91,client_order_id="synthetic-o",ibkr_order_id=71,
            relationship_context=dict(relationship_id="synthetic-r",action="ENTRY"))
        if branch=="after_effect_write_failure":
            def fail_write(*args,**kwargs): raise RuntimeError("synthetic persistence interruption")
            with monkeypatch.context() as context:
                context.setattr(branch_storage._store,"insert_lifecycle_transitions",fail_write)
                with pytest.raises(RuntimeError,match="synthetic persistence interruption"):
                    CoreOrchestrator._apply_execution_results_to_trade_management(NS(trade_management_engine=owner),[fact])
            assert owner.snapshot_positions()["SYNTHETIC"].quantity==1
        else:
            # Control stops before invoking the processor: no application/replay.
            assert owner.snapshot_positions()=={}
        live.append(bool(owner.snapshot_positions()))
        branch_storage._store.close()
        with sqlite3.connect(f"file:{path}?mode=ro",uri=True) as db:
            retained.append(dict(full_database_dump=list(db.iterdump()),independent_external=independent))
        # Fresh process sees unchanged pending record in BOTH branches.
        reader=storage_at(path);restored=TradeManagementEngine(persistence_adapter=reader)
        restored.restore_relationship_state()
        assert reader.fetch_management_state(restored._state_namespace)==initial
        assert restored.snapshot_positions()=={} and restored._relationship_plans["synthetic-r"].orders["synthetic-o"]["filled"]==0
        reader._store.close()
    assert live==[False,True]
    assert retained[0]==retained[1]  # Full persisted DB, not selected current values, is identical.
    (tmp_path/"identical-evidence-counterexample.json").write_text(json.dumps(dict(
        external=independent,identical_database=True,controlled_application=live,
        durable_classification=["UNKNOWN","UNKNOWN"]),sort_keys=True))
    assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}


@pytest.mark.parametrize("owner_kind",["capital","allocation"])
def test_lower_store_positive_effect_receipt_survives_post_commit_failure(monkeypatch,tmp_path,no_external_activity,owner_kind):
    """Component support only: active Core facade lacks these insert methods."""
    import sqlite3
    from src.storage.sqlite_store import SQLiteStore
    from src.core.capital_management_authority import CapitalManagementAuthority
    from src.core.strategy_capital_allocation_authority import StrategyCapitalAllocationAuthority
    path=tmp_path/(owner_kind+".sqlite");store=SQLiteStore(str(path));store.initialize_schema()
    owner_type=CapitalManagementAuthority if owner_kind=="capital" else StrategyCapitalAllocationAuthority
    owner=owner_type(storage_engine=store)
    method="insert_capital_audit_event" if owner_kind=="capital" else "insert_strategy_allocation_audit_event"
    table="capital_audit_events" if owner_kind=="capital" else "strategy_allocation_audit_events"
    write=getattr(store,method)
    def committed_then_interrupted(event):
        write(event)  # Existing owner/store implementation, committed before the injected interruption.
        raise RuntimeError("synthetic post-commit interruption")
    monkeypatch.setattr(store,method,committed_then_interrupted)
    with pytest.raises(RuntimeError,match="synthetic post-commit interruption"):
        owner.convert_reservation_to_exposure(decision_id="synthetic-d",order_id="synthetic-o",trade_id="synthetic-o",
            symbol="SYNTHETIC",strategy_id="RossMomentumStrategyV1",fill_quantity=1,fill_price=10.91)
    with sqlite3.connect(f"file:{path}?mode=ro",uri=True) as db:
        db.row_factory=sqlite3.Row;rows=[dict(r) for r in db.execute("SELECT * FROM "+table)]
    assert len(rows)==1 and rows[0]["event_type"]=="EXPOSURE" and rows[0]["order_id"]=="synthetic-o"
    assert rows[0]["trade_id"]=="synthetic-o" and rows[0]["approved_quantity"]==1
    assert rows[0]["exposure_after" if owner_kind=="capital" else "used_exposure"]==pytest.approx(10.91)
    fresh=owner_type(storage_engine=store)
    assert (fresh.total_used_exposure if owner_kind=="capital" else fresh.strategy_used_exposure("RossMomentumStrategyV1"))==0
    # Positive post-mutation receipt proves APPLIED for this component operation;
    # the fresh zero projection does not prove historical UNAPPLIED. No replay.
    store.close()
    assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}


def _assess_interleaving_recovery_evidence(*,h,plan,case,states,tmp_path):
    """Existing synthetic sequence evidence; never promote cleanup to recovery."""
    import json
    import sqlite3
    from copy import deepcopy
    engine=h.core.execution_engine
    storage=h.core.storage_engine
    def committed():
        with sqlite3.connect(f"file:{storage.sqlite_path}?mode=ro",uri=True) as db:
            row=db.execute("SELECT reason FROM position_lifecycle_transitions WHERE transition_id=?",
                (h.manager._state_namespace,)).fetchone()
            return json.loads(row[0])
    before=committed()
    saved=before["plans"][plan.relationship_id]
    rejected=[o for o in saved["orders"].values() if o.get("lifecycle_application_rejected")]
    classification=dict(capital_effects="UNKNOWN",allocation_effects="UNKNOWN",registry_effects="UNKNOWN",
        second_lifecycle_exit="UNKNOWN",canonical_management="UNKNOWN",recovery_record="UNKNOWN")
    if case.startswith("both_") or case=="reduction_cancel_late_fill":
        assert len(rejected)==1 and rejected[0]["lifecycle_application_rejected"]["error"]=="qty_exceeds_open"
        assert rejected[0]["lifecycle_application_rejected"]["cumulative_quantity"]==1
        assert saved["paused"] and any(o.get("cached_update_in_progress") for o in saved["orders"].values())
        assert sum(o["filled"] for o in saved["orders"].values() if o["action"] in {"EXIT","REDUCE"})==2
        for order_id,order in saved["orders"].items():
            if order["filled"]:
                assert f"{plan.relationship_id}:{order_id}:1" in before["seen_exec_ids"]
        # Specific bound negative application receipt, not a missing record:
        # actual record_exit_fill validates qty_exceeds_open BEFORE mutating.
        classification.update(second_lifecycle_exit="UNAPPLIED",canonical_management="APPLIED",recovery_record="APPLIED")
        _verify_fresh_process_recovery_guard(storage.sqlite_path,h.manager._state_namespace,plan.relationship_id)
    if case=="interrupted_reduce":
        assert any(o.get("cached_update_in_progress") for o in saved["orders"].values())
        assert plan.paused and plan.pending_stop_cancel=="72"
        retained={key:deepcopy(o["cached_update_in_progress"]) for key,o in plan.orders.items() if o.get("cached_update_in_progress")}
        # Existing ordinary stop-cleanup owner consumes independent synthetic
        # canonical absence only. No accounting/collector replay or flag clearing.
        engine.refresh_relationship_order_snapshot()
        assert plan.pending_stop_cancel is None and plan.paused
        assert retained=={key:o["cached_update_in_progress"] for key,o in plan.orders.items() if o.get("cached_update_in_progress")}
        with pytest.raises(RuntimeError,match="CACHED_EXECUTION_UPDATE_RECOVERY_REQUIRED"):
            engine.collect_relationship_updates()
        assert engine._failsafe_block_new_entries
        after=committed()["plans"][plan.relationship_id]
        assert after["paused"] and all(after["orders"][key]["cached_update_in_progress"]==value for key,value in retained.items())
        classification.update(canonical_management="APPLIED",recovery_record="APPLIED")
    if case=="identity_absent":
        owned=saved["orders"][plan.milestone_order_id]
        assert owned["status"]=="RECONCILED_ABSENT" and owned["terminal"] and owned["filled"]==0
        assert not owned.get("lifecycle_application_rejected") and not owned.get("cached_update_in_progress")
        classification["own_absence_resolution"]="APPLIED"
    if case=="cancel_late":
        assert saved["pending_stop_cancel"] is None
        assert any(s["pending_cancel"]=="72" for s in states)
        assert not any(o.get("cached_update_in_progress") or o.get("lifecycle_application_rejected") for o in saved["orders"].values())
        classification["own_cleanup_resolution"]="APPLIED"
    if case=="duplicate_reorder":
        assert saved["orders"][plan.milestone_order_id]["filled"]==1
        assert saved["milestone_consumed"]
        classification["canonical_management"]="APPLIED"
    _assert_owner_effect_inspection_preserves_latches(h,plan)
    (tmp_path/"interleaving-recovery-evidence.json").write_text(json.dumps(dict(case=case,
        classification=classification,committed_before=before,committed_after=committed()),default=str,sort_keys=True))


def _prospective_effect_fixture(tmp_path,owner_kind,effect="CONVERT"):
    from src.storage.storage_engine import StorageEngine
    from src.storage.sqlite_store import SQLiteStore
    from src.core.capital_management_authority import CapitalManagementAuthority
    from src.core.strategy_capital_allocation_authority import StrategyCapitalAllocationAuthority
    store=SQLiteStore(str(tmp_path/(owner_kind+effect+".sqlite")));store.initialize_schema()
    storage=StorageEngine.__new__(StorageEngine)
    storage.enabled=True;storage.backend="sqlite";storage._store=store;storage.run_id=None
    owner=(CapitalManagementAuthority if owner_kind=="capital" else StrategyCapitalAllocationAuthority)(run_mode="PAPER",storage_engine=storage)
    if effect=="RELEASE":
        owner.convert_reservation_to_exposure(order_id="seed",symbol="SYNTHETIC",strategy_id="RossMomentumStrategyV1",fill_quantity=1,fill_price=10.91)
    binding=dict(version=1,mode="PAPER",security_id="conId:123",symbol="SYNTHETIC",relationship_id="synthetic-r",
        decision_id="synthetic-d",order_id="synthetic-o",native_order_id="71",owner=owner_kind,effect=effect,
        cumulative_quantity=1,delta_quantity=1,average_price=10.91,delta_price=10.91)
    def apply(b=None):
        evidence=binding if b is None else b
        if effect=="CONVERT":
            return owner.convert_reservation_to_exposure(order_id="synthetic-o",decision_id="synthetic-d",
                trade_id="synthetic-o",symbol="SYNTHETIC",strategy_id="RossMomentumStrategyV1",fill_quantity=evidence["delta_quantity"],fill_price=evidence["delta_price"],effect_evidence=evidence)
        kwargs=dict(strategy_id="RossMomentumStrategyV1",quantity=evidence["delta_quantity"],price=evidence["delta_price"],effect_evidence=evidence)
        if owner_kind=="capital": kwargs["symbol"]="SYNTHETIC"
        return owner.release_exposure(**kwargs)
    def used():
        return owner.total_used_exposure if owner_kind=="capital" else owner.strategy_used_exposure("RossMomentumStrategyV1")
    return NS(storage=storage,store=store,owner=owner,binding=binding,apply=apply,used=used)


@pytest.mark.parametrize("owner_kind",["capital","allocation"])
@pytest.mark.parametrize("effect",["CONVERT","RELEASE"])
@pytest.mark.parametrize("boundary",["capability","prepare_write","after_prepare","after_mutation","after_commit"])
def test_prospective_owner_effect_interruption_boundaries(monkeypatch,tmp_path,no_external_activity,owner_kind,effect,boundary):
    import sqlite3
    h=_prospective_effect_fixture(tmp_path,owner_kind,effect)
    before=h.used()
    if boundary=="capability":
        monkeypatch.setattr(h.store,"insert_owner_effect_record",None)
    elif boundary=="prepare_write":
        def fail_prepare(*args,**kwargs): raise OSError("synthetic prepare failure")
        monkeypatch.setattr(h.store,"insert_owner_effect_record",fail_prepare)
    elif boundary=="after_prepare":
        prepare=h.storage.prepare_owner_effect
        def fail_prepared(*args,**kwargs):
            prepare(*args,**kwargs)
            raise OSError("synthetic interruption after durable prepare")
        monkeypatch.setattr(h.storage,"prepare_owner_effect",fail_prepared)
    else:
        finish=h.storage.finish_owner_effect
        def fail_finish(*args,**kwargs):
            if boundary=="after_commit": finish(*args,**kwargs)
            raise OSError("synthetic receipt interruption")
        monkeypatch.setattr(h.storage,"finish_owner_effect",fail_finish)
    with pytest.raises((RuntimeError,OSError)):
        h.apply()
    after=h.used()
    assert after==pytest.approx(before if boundary in {"capability","prepare_write","after_prepare"} else (10.91 if effect=="CONVERT" else 0))
    assessment=h.storage.inspect_owner_effect(h.binding,independent_fact=dict(h.binding))
    assert assessment["resolved"] is False
    assert assessment.get("outcome")==("OBSERVED_APPLIED" if boundary=="after_commit" else "UNKNOWN")
    if boundary in {"after_prepare","after_mutation","after_commit"}:
        # Another attempt must fail BEFORE any effect, even if the first caller
        # never received receipt acknowledgement. No accounting replay.
        with pytest.raises(sqlite3.IntegrityError): h.apply()
        assert h.used()==after
    if boundary in {"after_prepare","after_mutation"}:
        effect_id,expected=h.storage._owner_effect_record(h.binding,phase="PREPARED")
        assert h.store.fetch_owner_effect_record(effect_id+":prepare")==expected
        assert h.store.fetch_owner_effect_record(effect_id+":outcome") is None
    h.store.close()
    assert no_external_activity==[] and mutations()=={"place":0,"modify":0,"cancel":0}


@pytest.mark.parametrize("owner_kind",["capital","allocation"])
def test_prospective_identity_conflict_restart_and_readonly_assessment(monkeypatch,tmp_path,no_external_activity,owner_kind):
    from copy import deepcopy
    from src.storage.sqlite_store import SQLiteStore
    from src.core.capital_management_authority import CapitalManagementAuthority
    from src.core.strategy_capital_allocation_authority import StrategyCapitalAllocationAuthority
    import sqlite3
    h=_prospective_effect_fixture(tmp_path,owner_kind)
    h.apply()
    baseline=h.used()
    for changes in ({"average_price":11.},{"native_order_id":"999"},{"decision_id":"another"},{"security_id":"conId:999"}):
        altered={**h.binding,**changes}
        with pytest.raises(sqlite3.IntegrityError): h.apply(altered)
        assert h.used()==baseline
        assert not h.storage.inspect_owner_effect(altered,independent_fact=altered)["resolved"]
    assert h.storage.inspect_owner_effect(h.binding,independent_fact={**h.binding,"cumulative_quantity":2})["reason"]=="OWNER_EFFECT_IDENTITY_CONFLICT"
    # Fresh process-local owner state is NOT restored from audit evidence.
    path=h.store.path;h.store.close();h.storage._store=SQLiteStore(path)
    owner_type=CapitalManagementAuthority if owner_kind=="capital" else StrategyCapitalAllocationAuthority
    fresh=owner_type(run_mode="PAPER",storage_engine=h.storage)
    assert (fresh.total_used_exposure if owner_kind=="capital" else fresh.strategy_used_exposure("RossMomentumStrategyV1"))==0
    with pytest.raises(sqlite3.IntegrityError):
        fresh.convert_reservation_to_exposure(order_id="synthetic-o",decision_id="synthetic-d",trade_id="synthetic-o",
            symbol="SYNTHETIC",strategy_id="RossMomentumStrategyV1",fill_quantity=1,fill_price=10.91,effect_evidence=h.binding)
    assert (fresh.total_used_exposure if owner_kind=="capital" else fresh.strategy_used_exposure("RossMomentumStrategyV1"))==0
    result=h.storage.inspect_owner_effect(h.binding,independent_fact=dict(h.binding))
    assert result==dict(resolved=False,reason="NON_ATOMIC_EFFECT_AND_MISSING_FULL_UPDATE_PROOF",outcome="OBSERVED_APPLIED",atomic_application=False)
    h.storage._store.close()
    assert no_external_activity==[]


@pytest.mark.parametrize("changes",[{"version":2},{"cumulative_quantity":True},{"delta_quantity":2},{"average_price":float("nan")},{"extra":"caller assertion"}])
def test_prospective_schema_rejects_before_effect(tmp_path,no_external_activity,changes):
    h=_prospective_effect_fixture(tmp_path,"capital")
    bad={**h.binding,**changes}
    with pytest.raises((ValueError,TypeError)): h.apply(bad)
    assert h.used()==0
    assert h.storage.inspect_owner_effect(bad,independent_fact=bad)["resolved"] is False
    h.store.close()
    assert no_external_activity==[]


def test_explicit_pre_mutation_rejection_and_historical_non_authority(tmp_path,no_external_activity):
    h=_prospective_effect_fixture(tmp_path,"capital")
    # An unversioned historical operation is not upgraded to effect authority.
    h.owner.convert_reservation_to_exposure(symbol="SYNTHETIC",strategy_id="RossMomentumStrategyV1",fill_quantity=1,fill_price=10.91)
    assert h.storage.inspect_owner_effect(h.binding,independent_fact=h.binding)["reason"]=="HISTORICAL_OR_MISSING_EVIDENCE"
    before=h.used()
    zero={**h.binding,"delta_quantity":0,"cumulative_quantity":0}
    assert h.apply(zero)==0 and h.used()==before
    result=h.storage.inspect_owner_effect(zero,independent_fact=zero)
    assert result["outcome"]=="REJECTED_BEFORE_MUTATION" and not result["resolved"]
    h.store.close()
    assert no_external_activity==[]



def _assert_owner_effect_inspection_preserves_latches(h,plan):
    from copy import deepcopy
    import json
    engine=h.core.execution_engine; storage=h.core.storage_engine
    before=deepcopy((plan.orders,plan.paused,plan.reconciled,engine.startup_recovery_state,
        engine.startup_recovery_result,engine._failsafe_block_new_entries))
    durable=storage.fetch_management_state(h.manager._state_namespace)
    rows=storage._store.connection.execute("SELECT reason FROM position_lifecycle_transitions WHERE intent='OWNER_EFFECT_EVIDENCE' AND transition_id LIKE '%:prepare'").fetchall()
    for row in rows:
        binding=json.loads(row[0])["binding"]
        result=storage.inspect_owner_effect(binding,independent_fact=dict(binding))
        assert result["resolved"] is False  # Even matching execution facts cannot prove atomic full-update recovery.
    assert before==deepcopy((plan.orders,plan.paused,plan.reconciled,engine.startup_recovery_state,
        engine.startup_recovery_result,engine._failsafe_block_new_entries))
    assert storage.fetch_management_state(h.manager._state_namespace)==durable



@pytest.mark.parametrize("failure",["sqlite","io","missing_capability"])
def test_owner_effect_lost_evidence_is_explicitly_blocked(monkeypatch,tmp_path,no_external_activity,failure):
    import sqlite3
    h=_prospective_effect_fixture(tmp_path,"capital");h.apply();before=h.used()
    if failure=="missing_capability":
        monkeypatch.setattr(h.store,"fetch_owner_effect_record",None)
    else:
        def fail_read(*args): raise (sqlite3.DatabaseError if failure=="sqlite" else OSError)("private synthetic storage error")
        monkeypatch.setattr(h.store,"fetch_owner_effect_record",fail_read)
    result=h.storage.inspect_owner_effect(h.binding,independent_fact=h.binding)
    assert not result["resolved"] and result.get("outcome","UNKNOWN")=="UNKNOWN"
    assert result["reason"] in {"OWNER_EFFECT_STORAGE_UNAVAILABLE","OWNER_EFFECT_EVIDENCE_UNAVAILABLE"}
    assert "private" not in str(result) and h.used()==before
    h.store.close();assert no_external_activity==[]



@pytest.mark.parametrize("owner_kind",["capital","allocation"])
@pytest.mark.parametrize("quantity,price",[(True,10.91),(1.0,10.91),(1,True),(1,float("inf"))])
def test_prospective_owner_rejects_actual_untyped_values(tmp_path,no_external_activity,owner_kind,quantity,price):
    h=_prospective_effect_fixture(tmp_path,owner_kind)
    with pytest.raises(ValueError,match="OWNER_EFFECT_INPUT_INVALID"):
        h.owner.convert_reservation_to_exposure(order_id="synthetic-o",symbol="SYNTHETIC",strategy_id="RossMomentumStrategyV1",
            fill_quantity=quantity,fill_price=price,effect_evidence=h.binding)
    assert h.used()==0
    assert h.storage.inspect_owner_effect(h.binding,independent_fact=h.binding)["reason"]=="HISTORICAL_OR_MISSING_EVIDENCE"
    h.store.close();assert no_external_activity==[]



def test_owner_effect_future_database_version_blocks_before_mutation(tmp_path,no_external_activity):
    h=_prospective_effect_fixture(tmp_path,"capital")
    h.store.connection.execute("INSERT INTO schema_meta(version) VALUES (999)");h.store.connection.commit()
    with pytest.raises(RuntimeError,match="OWNER_EFFECT_DATABASE_VERSION_UNSUPPORTED"): h.apply()
    assert h.used()==0
    assert h.storage.inspect_owner_effect(h.binding,independent_fact=h.binding)["reason"]=="OWNER_EFFECT_DATABASE_VERSION_UNSUPPORTED"
    h.store.close();assert no_external_activity==[]


@pytest.mark.parametrize("tamper",["schema","atomic","identity"])
def test_owner_effect_corrupt_outcome_never_grants_resolution(tmp_path,no_external_activity,tamper):
    import json
    h=_prospective_effect_fixture(tmp_path,"capital");h.apply();before=h.used()
    effect_id,_=h.storage._owner_effect_record(h.binding,phase="PREPARED")
    raw=json.loads(h.store.fetch_owner_effect_record(effect_id+":outcome"))
    if tamper=="schema": raw["schema_version"]=999
    if tamper=="atomic": raw["atomic_application"]=True
    if tamper=="identity": raw["binding"]["native_order_id"]="999"
    h.store.connection.execute("UPDATE position_lifecycle_transitions SET reason=? WHERE transition_id=?",
        (json.dumps(raw,sort_keys=True),effect_id+":outcome"));h.store.connection.commit()
    result=h.storage.inspect_owner_effect(h.binding,independent_fact=h.binding)
    assert result["reason"]=="OWNER_EFFECT_SCHEMA_OR_IDENTITY_INVALID" and not result["resolved"]
    assert h.used()==before
    h.store.close();assert no_external_activity==[]
