"""Explicit mechanism proof; no automatic BE/trailing policy is enrolled."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from dataclasses import replace
import pytest
from ibapi.contract import Contract, ContractDetails
from src.config import config_resolver
from test_standalone_pmh_late_fill_protection import (small_central_owned,one_share_profit_case,
    enroll_unit_management,fill_unit_ids,reassessment,lifecycle,forbid_io,no_external_activity,_reset_config)


def prepare_revision(reassessment,monkeypatch,tmp_path,capsys):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    # Existing adopted management stays opt-in, and unconfirmed external quote
    # prevents its profit rule while preparing a fresh completed bar below.
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life),fault='quote_unconfirmed')
    enroll_unit_management(h,monkeypatch,price_revision=True)
    original=h.core.market_data_snapshot_manager.batch_snapshots
    def confirmed(symbols):
        values,errors=original(symbols)
        return {s:replace(v,market_data_type_confirmed=True) for s,v in values.items()},errors
    monkeypatch.setattr(h.core.market_data_snapshot_manager,'batch_snapshots',confirmed)
    from src.execution import trade_management_engine as tm
    monkeypatch.setattr(tm,'datetime',datetime)
    rule,contract=bind_native_price_rule(h,monkeypatch)
    inspected=h.core.inspect_stop_revision_prerequisite(request.client_order_id)
    assert inspected is not None
    proposal,quote,decision,guard=inspected
    return h,request,life,rule,contract,proposal,quote,decision,guard


def test_joined_core_native_stop_revision_retains_original_basis(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,rule,contract,proposal,quote,decision,guard=prepare_revision(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine;parent=h.failure_owner
    before=(life.avg_fill_price,life.selected_stop_price,request.invalidation_level)
    assert engine.request_stop_revision_prerequisite(request.client_order_id,proposal=proposal,proposed_price='10.70',
        price_rule=rule,contract=contract,route='SMART',quote=quote,decision=decision,authorization_guard=guard)
    assert parent['stop_price_revision']['status']=='CONFIRMED'
    assert (life.avg_fill_price,life.selected_stop_price,request.invalidation_level)==before
    assert all(leg.trigger_price==10.63 and leg.last_confirmed_effective_stop_price==10.70 for leg in life.stop_legs)
    assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert len(h.unit_writes)==4 and {oid for oid,_ in h.unit_writes}=={72,73,74,75}
    assert len(h.registry_batches[0][1])==33 and request.take_profit_price is None
    assert not engine.request_stop_revision_prerequisite(request.client_order_id,proposal=proposal,proposed_price='10.75',
        price_rule=rule,contract=contract,route='SMART',quote=quote,decision=decision,authorization_guard=guard)
    # The existing adopted profit route must still work with actual effective
    # native prices while E0/originalS0 remain its immutable milestone basis.
    assert h.core.run_once();capsys.readouterr()
    assert len(h.unit_writes)==6
    selected=[oid for oid,_ in h.unit_writes[4:]]
    fill_unit_ids(h,life,capsys,selected,price=h.failure_exit_price)
    assert life.filled_qty==2 and engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    fill_unit_ids(h,life,capsys,[row.orderId for row in list(h.native_open_orders)],price=10.70)
    assert life.filled_qty==0 and not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert no_external_activity==[]


@pytest.mark.parametrize('fault',['same','widen','cross_bid','wrong_route','conflicting_rule','stale_rule','old_price','unknown','rejected','stale_final','incomplete','epoch','fill_before_write','fill_during_write','persistence'])
def test_revision_boundaries_quarantine_without_retry(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life,rule,contract,proposal,quote,decision,guard=prepare_revision(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine;parent=h.failure_owner;client=h.native_client
    price='10.70';route='SMART'
    if fault=='same':price=str(life.selected_stop_price)
    if fault=='widen':price=str(life.selected_stop_price-.01)
    if fault=='cross_bid':price=str(quote.bid)
    if fault=='wrong_route':route='NASDAQ'
    if fault=='conflicting_rule':client.marketRule(26,[NS(lowEdge=0,increment=.005)])
    if fault=='stale_rule':h.life.clock.current+=__import__('datetime').timedelta(seconds=20)
    if fault in {'unknown','rejected'}:enroll_unit_management(h,monkeypatch,price_revision=True,fault=fault)
    inventory=client.openOrders
    if fault in {'stale_final','incomplete','epoch','fill_before_write'}:
        def external_inventory(**kwargs):
            result=inventory(**kwargs)
            if fault=='stale_final':h.life.clock.current+=__import__('datetime').timedelta(seconds=20)
            if fault=='incomplete':raise RuntimeError('Synthetic incomplete native inventory')
            if fault=='epoch':client._position_connection_epoch+=1
            if fault=='fill_before_write':
                h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.63)
                h.native_quantity[0]-=1
            return result
        monkeypatch.setattr(client,'openOrders',external_inventory)
    if fault in {'old_price','fill_during_write'}:
        from ibapi.client import EClient
        sdk=EClient.placeOrder
        def changed(self,native_id,c,native):
            sdk(self,native_id,c,native)
            if fault=='old_price':
                next(row for row in h.native_open_orders if row.orderId==native_id).order.auxPrice=10.63
            else:
                h.facts[native_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.70)
                h.native_quantity[0]-=1
        monkeypatch.setattr(EClient,'placeOrder',changed)
    if fault=='persistence':
        save=engine._save_selected_orders;count=[0]
        def interrupted(order_id):
            count[0]+=1
            if count[0]==1:raise RuntimeError('Synthetic reservation persistence interruption')
            return save(order_id)
        monkeypatch.setattr(engine,'_save_selected_orders',interrupted)
    invoke=lambda:engine.request_stop_revision_prerequisite(request.client_order_id,proposal=proposal,proposed_price=price,
        price_rule=rule,contract=contract,route=route,quote=quote,decision=decision,authorization_guard=guard)
    if fault in {'same','widen','cross_bid','wrong_route','conflicting_rule','stale_rule'}:
        assert not invoke() and not parent.get('stop_price_revision')
        assert not h.unit_writes and not h.unit_wires
        assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    else:
        with pytest.raises((RuntimeError,OSError)):invoke()
        assert engine._native_quarantined and parent['stop_price_revision']['status']=='RESERVED'
        assert not engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
        assert all(leg.last_confirmed_effective_stop_price==10.63 for leg in life.stop_legs)
        assert len(h.unit_wires)<=1 and len(h.unit_writes)<=1
        if fault in {'stale_final','incomplete','epoch','fill_before_write','persistence'}:assert not h.unit_wires
        before=deepcopy((engine.position_records,parent,len(h.unit_writes),len(h.unit_wires),engine.capital_authority.total_used_exposure))
        assert not invoke()
        assert before==deepcopy((engine.position_records,parent,len(h.unit_writes),len(h.unit_wires),engine.capital_authority.total_used_exposure))
    assert life.avg_fill_price==10.88 and life.selected_stop_price==10.63 and request.take_profit_price is None
    assert no_external_activity==[]


def test_flat_precedes_explicit_prerequisite(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,rule,contract,proposal,quote,decision,guard=prepare_revision(reassessment,monkeypatch,tmp_path,capsys)
    fill_unit_ids(h,life,capsys,[row.orderId for row in list(h.native_open_orders)])
    assert life.filled_qty==0
    assert h.core.inspect_stop_revision_prerequisite(request.client_order_id) is None
    assert not h.core.execution_engine.request_stop_revision_prerequisite(request.client_order_id,proposal=proposal,proposed_price='10.70',
        price_rule=rule,contract=contract,route='SMART',quote=quote,decision=decision,authorization_guard=guard)
    assert not h.unit_writes


def bind_native_price_rule(h,monkeypatch):
    client=h.native_client
    monkeypatch.setattr(client,'is_connected',lambda:True)
    monkeypatch.setattr(client,'_price_rule_observed_now',lambda:h.life.clock.current)
    contract=deepcopy(h.native_open_orders[0].contract)
    def qualify(req_id,c):
        detail=ContractDetails();detail.contract=deepcopy(contract);detail.longName='Synthetic facts'
        detail.validExchanges='SMART,NASDAQ';detail.marketRuleIds='26,27'
        client.contractDetails(req_id,detail);client.contractDetailsEnd(req_id)
    monkeypatch.setattr(client,'reqContractDetails',qualify)
    client.qualifyContracts(contract)
    old_send=client.sendMsg
    def rule_wire(message):
        client.marketRule(26,[NS(lowEdge=0,increment=.01)])
    monkeypatch.setattr(client,'sendMsg',rule_wire)
    rule=client.price_rule_snapshot(contract,route='SMART')
    assert rule.status=='COMPLETE'
    monkeypatch.setattr(client,'sendMsg',old_send)
    return rule,contract


def test_pending_revision_excludes_preapproved_profit_action(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,rule,contract,proposal,quote,decision,guard=prepare_revision(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine;parent=h.failure_owner
    from src.strategies.ross_momentum.strategy_policy import standalone_profit_quote_evidence
    profit=h.manager.evaluate_selected_completed_profit(parent,h.failure_bars,observed_at=h.life.clock.current,
        session_plan=request.management_session_plan,entry_fill_price=life.avg_fill_price)
    profit['profit_quote']=standalone_profit_quote_evidence(quote,symbol='JPM',milestone=h.profit_level,observed_at=h.life.clock.current)
    old_decision=h.core.risk_engine.evaluate_selected_failure_exit(order_id=request.client_order_id,order=parent,
        position=h.manager.snapshot_positions()['JPM'],registered=h.core.trade_registry.get_trade('JPM',request.trader_type),
        life=life,snapshot=h.core._latest_position_truth_snapshot,observed_at=h.life.clock.current,profit=True,quote=quote)
    assert old_decision.allowed and old_decision.max_position_size==2
    attempts=[];inventory=h.native_client.openOrders
    def interleaved(**kwargs):
        result=inventory(**kwargs)
        assert parent['stop_price_revision']['status']=='RESERVED'
        attempts.append(engine.request_selected_failure_exit(request.client_order_id,profit,decision=old_decision,authorization_guard=lambda now:True))
        return result
    monkeypatch.setattr(h.native_client,'openOrders',interleaved)
    assert engine.request_stop_revision_prerequisite(request.client_order_id,proposal=proposal,proposed_price='10.70',
        price_rule=rule,contract=contract,route='SMART',quote=quote,decision=decision,authorization_guard=guard)
    assert attempts and not any(attempts) and not parent.get('unit_profit_exit')
    assert len(h.unit_writes)==4 and all(native.orderType=='STP' for _,native in h.unit_writes)


@pytest.mark.parametrize('tamper',['request','ownership','role','amendment','entry_average','root_reservation','child_reservation'])
def test_blocking_inventory_cannot_change_sealed_authority(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,tamper):
    h,request,life,rule,contract,proposal,quote,decision,guard=prepare_revision(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine;parent=h.failure_owner;inventory=h.native_client.openOrders
    def altered(**kwargs):
        result=inventory(**kwargs)
        if tamper=='request':parent['request']=deepcopy(parent['request'])
        if tamper=='ownership':parent['decision_id']='UNRELATED'
        if tamper=='role':life.stop_legs[0].close_role='REDUCTION'
        if tamper=='amendment':engine._selected_order_records()[life.stop_legs[0].leg_id]['unit_amendment']={'status':'DISPATCH_UNCERTAIN'}
        if tamper=='entry_average':h.facts[71]['avgFillPrice']=10.89
        if tamper=='root_reservation':parent['stop_price_revision']=deepcopy(parent['stop_price_revision'])
        if tamper=='child_reservation':
            child=engine._selected_order_records()[life.stop_legs[0].leg_id]
            child['stop_price_revision']=deepcopy(child['stop_price_revision'])
        return result
    monkeypatch.setattr(h.native_client,'openOrders',altered)
    with pytest.raises(RuntimeError):
        engine.request_stop_revision_prerequisite(request.client_order_id,proposal=proposal,proposed_price='10.70',
            price_rule=rule,contract=contract,route='SMART',quote=quote,decision=decision,authorization_guard=guard)
    assert not h.unit_writes and not h.unit_wires and engine._native_quarantined


def test_original_truth_clock_cannot_be_renewed(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from datetime import timedelta
    from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
    h,request,life,rule,contract,proposal,quote,decision,guard=prepare_revision(reassessment,monkeypatch,tmp_path,capsys)
    snapshot=h.core._latest_position_truth_snapshot
    future=h.life.clock.current+timedelta(seconds=get_ibkr_snapshot_max_age_seconds()+1)
    assert h.manager.inspect_stop_revision_prerequisite(h.failure_owner,h.failure_bars,observed_at=future,session_plan=request.management_session_plan)
    snapshot.as_of=future
    assert not guard(future)  # New snapshot time cannot renew the captured old permission.
    assert not h.unit_writes


def test_confirmed_revision_is_durable_but_fresh_process_cannot_resume(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    import os,subprocess,sys
    h,request,life,rule,contract,proposal,quote,decision,guard=prepare_revision(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine
    assert engine.request_stop_revision_prerequisite(request.client_order_id,proposal=proposal,proposed_price='10.70',
        price_rule=rule,contract=contract,route='SMART',quote=quote,decision=decision,authorization_guard=guard)
    saved=h.core.storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
    parent=saved['orders'][request.client_order_id]
    assert parent['stop_price_revision']['status']=='CONFIRMED'
    assert parent['request']['stop_loss_price']==10.63
    from test_standalone_pmh_late_fill_protection import assert_readonly_selected_dispatch_restart
    assert_readonly_selected_dispatch_restart(h,request,timeframe='10s',profile='UNIT_STOPS')


def test_readonly_exact_client_pin_keeps_operational_default_and_never_connects(monkeypatch):
    from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionManager,IbkrConnectionConfig
    cfg=IbkrConnectionConfig('127.0.0.1',7497,71,3,'LIVE',True,'READ_ONLY')
    manager=IbkrConnectionManager(cfg)
    assert cfg.max_client_id_retries==10
    pin=manager.pin_readonly_client_id(71)
    assert pin['max_client_id_retries']==manager._config.max_client_id_retries==1
    assert manager._client is None and cfg.max_client_id_retries==10
    with pytest.raises(RuntimeError):manager.pin_readonly_client_id(72)
    manager._client=object()
    with pytest.raises(RuntimeError):manager.pin_readonly_client_id(71)
    paper=IbkrConnectionManager(replace(cfg,run_mode='PAPER',readonly_enabled=False))
    with pytest.raises(RuntimeError):paper.pin_readonly_client_id(71)


def test_exact_readonly_client_conflict_never_tries_another_id(monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_connection_manager as module
    attempts=[];retired=[]
    class SyntheticConflict:
        def __init__(self,**scope):self.id=scope['client_id'];attempts.append(self.id)
        def connect(self):raise RuntimeError('326 client id is already in use')
        def disconnect(self):retired.append(self.id)
    monkeypatch.setattr(module,'IbkrClient',SyntheticConflict)
    manager=module.IbkrConnectionManager(module.IbkrConnectionConfig('127.0.0.1',7497,71,3,'LIVE',True,'READ_ONLY'))
    manager.pin_readonly_client_id(71)
    with pytest.raises(RuntimeError):manager._connect_locked()
    assert attempts==retired==[71] and manager._client is None


def test_natural_adapter_pins_exact_id_before_any_scanner_io(monkeypatch):
    from scripts.certification import pr1040_real_readonly_runtime_observation_adapter as adapter
    from src.adapters.brokers.ibkr import ibkr_connection_manager as native
    called=[]
    class EndProbe(Exception):pass
    def pin(identity):called.append(identity);raise EndProbe
    monkeypatch.setattr(native,'get_shared_ibkr_connection_manager',lambda **kw:NS(pin_readonly_client_id=pin))
    monkeypatch.setattr(adapter,'_broker_snapshot',lambda:pytest.fail('Acquisition preceded exact-ID ownership pin'))
    env=adapter.build_safe_readonly_env({})
    env.update(READONLY_ADMISSION_TOKEN='SYNTHETIC_ONLY',IBKR_CLIENT_ID='71')
    # The real adapter updates process environment. Register every affected key
    # with the existing monkeypatch owner so teardown restores inherited state.
    for key,value in env.items():monkeypatch.setenv(key,value)
    with pytest.raises(EndProbe):adapter.collect_real_readonly_runtime_evidence(operator='SYNTHETIC_ONLY',env=env)
    assert called==[71]


def test_late_old_price_invalidates_current_certificate(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,rule,contract,proposal,quote,decision,guard=prepare_revision(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine
    assert engine.request_stop_revision_prerequisite(request.client_order_id,proposal=proposal,proposed_price='10.70',
        price_rule=rule,contract=contract,route='SMART',quote=quote,decision=decision,authorization_guard=guard)
    confirmations=[deepcopy(leg.stop_price_revision) for leg in life.stop_legs]
    assert engine._confirm_selected_unit_stops(life,engine._pmh_complete_inventory(),allow_managed=True)==4
    assert confirmations==[leg.stop_price_revision for leg in life.stop_legs]  # No clock renewal.
    h.native_open_orders[0].order.auxPrice=10.63  # Independent late/contradictory external fact.
    with pytest.raises(RuntimeError,match="NATIVE_UNIT_PROTECTION_REMAINDER_UNVERIFIED"):
        engine.collect_relationship_updates(result_processor=lambda r:h.core._apply_execution_results_to_trade_management([r]))
    assert engine._native_quarantined
    assert not engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert life.stop_legs[0].last_confirmed_effective_stop_price==10.70
    assert len(h.unit_writes)==4


def test_equal_reentrant_proposal_cannot_replace_owned_reservation(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from src.adapters.brokers.ibkr.ibkr_client import NativePriceRule
    h,request,life,rule,contract,proposal,quote,decision,guard=prepare_revision(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine
    kwargs=dict(proposal=proposal,proposed_price='10.70',price_rule=rule,contract=contract,
        route='SMART',quote=quote,decision=decision,authorization_guard=guard)
    normalize=NativePriceRule.normalize_long_stop
    retained=[]
    def interleaved(self,*args,**options):
        monkeypatch.setattr(NativePriceRule,'normalize_long_stop',normalize)
        assert engine.request_stop_revision_prerequisite(request.client_order_id,**kwargs)
        retained.append(h.failure_owner['stop_price_revision'])
        return normalize(self,*args,**options)
    monkeypatch.setattr(NativePriceRule,'normalize_long_stop',interleaved)
    assert not engine.request_stop_revision_prerequisite(request.client_order_id,**kwargs)
    assert h.failure_owner['stop_price_revision'] is retained[0]
    assert retained[0]['status']=='CONFIRMED' and not engine._native_quarantined
    assert len(h.unit_writes)==len(h.unit_wires)==4


def test_already_entered_profit_rechecks_pending_revision_at_final_write(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,rule,contract,proposal,quote,decision,guard=prepare_revision(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine;parent=h.failure_owner
    from src.strategies.ross_momentum.strategy_policy import standalone_profit_quote_evidence
    profit=h.manager.evaluate_selected_completed_profit(parent,h.failure_bars,observed_at=h.life.clock.current,
        session_plan=request.management_session_plan,entry_fill_price=life.avg_fill_price)
    profit['profit_quote']=standalone_profit_quote_evidence(quote,symbol='JPM',milestone=h.profit_level,observed_at=h.life.clock.current)
    approved=h.core.risk_engine.evaluate_selected_failure_exit(order_id=request.client_order_id,order=parent,
        position=h.manager.snapshot_positions()['JPM'],registered=h.core.trade_registry.get_trade('JPM',request.trader_type),
        life=life,snapshot=h.core._latest_position_truth_snapshot,observed_at=h.life.clock.current,profit=True,quote=quote)
    assert approved.allowed
    inventory=h.native_client.openOrders
    observed=[]
    def conflicting(**kwargs):
        rows=inventory(**kwargs)
        assert parent['unit_profit_exit']['status']=='RESERVED'  # Actual exit already entered.
        parent['stop_price_revision']={'status':'DISPATCH_UNCERTAIN'}  # Contradictory coordinator fact, never authority.
        engine._save_selected_orders(request.client_order_id)  # Existing durable owner, no forged binding digest.
        observed.append(True)
        return rows
    monkeypatch.setattr(h.native_client,'openOrders',conflicting)
    with pytest.raises(RuntimeError):
        engine.request_selected_failure_exit(request.client_order_id,profit,decision=approved,authorization_guard=lambda now:True)
    assert observed and not h.unit_wires and not h.unit_writes and engine._native_quarantined
