"""Explicit mechanism proof; no automatic BE/trailing policy is enrolled."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from dataclasses import replace
import pytest
from ibapi.contract import Contract, ContractDetails
from ibapi.client import EClient

# Preserve the real READ encoders before function-scoped forbidden-I/O guards.
# Only the new disconnected quote fixture binds them behind synthetic sendMsg.
_NATIVE_QUOTE_CONTRACT_ENCODER = EClient.reqContractDetails
_NATIVE_QUOTE_MARKET_ENCODER = EClient.reqMktData
_NATIVE_HISTORY_READ_ENCODER = EClient.reqHistoricalData
_NATIVE_LEDGER_READ_ENCODER = EClient.reqAccountSummary
_NATIVE_LEDGER_CANCEL_ENCODER = EClient.cancelAccountSummary
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


def bind_native_price_rule(h,monkeypatch,*,query=True,bands=((0,.01),)):
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
        from ibapi.message import OUT
        if message.split('\0')[0] == str(OUT.REQ_MARKET_RULE):
            h.price_rule_dispatches=getattr(h,'price_rule_dispatches',[])+[message]
            client.marketRule(26,[NS(lowEdge=edge,increment=tick) for edge,tick in bands])
        else:old_send(message)
    monkeypatch.setattr(client,'sendMsg',rule_wire)
    rule=client.price_rule_snapshot(contract,route='SMART') if query else None
    if query:
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



def prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys,*,clock_time=(14,5,30),enroll=True,fault='none'):
    from test_standalone_pmh_late_fill_protection import micro_post_partial_case,append_micro_cost_bar,enroll_micro_cost_failure
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys,micro_clock=clock_time)
    assert request.quantity==2 and life.filled_qty==1 and len(h.unit_writes)==1 and h.unit_writes[0][1].orderType=='MKT'
    enroll_micro_cost_failure()
    bar,_=append_micro_cost_bar(h,request,life,capsys,fault='wick')  # Completed above E0, not a cost-failure bar.
    enroll_unit_management(h,monkeypatch,price_revision=True,fault=fault)
    _,contract=bind_native_price_rule(h,monkeypatch,query=False)
    if enroll:
        config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,ROSS_SYNTHETIC_MICRO_COST_TIGHTENING=True))
    return h,request,life,bar,contract


@pytest.mark.parametrize('clock_time',[(14,5,30),(16,35,30)],ids=['MORNING_10s','RTH_MID_1m'])
def test_micro_native_core_post_partial_tightening_to_protective_flat(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,clock_time):
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys,clock_time=clock_time)
    engine=h.core.execution_engine;original=(life.avg_fill_price,life.selected_stop_price,request.invalidation_level)
    assert len(h.registry_batches[0][1])==33 and request.take_profit_price is None and not request.relationship_context
    assert h.core.run_once(),capsys.readouterr().out[-5000:]
    capsys.readouterr()
    root=h.failure_owner['stop_price_revision']
    assert root['status']=='CONFIRMED' and root['proposed_price']==life.avg_fill_price
    assert len(h.unit_writes)==2 and [order.orderType for _,order in h.unit_writes]==['MKT','STP']
    assert len(h.price_rule_dispatches)==1
    assert original==(life.avg_fill_price,life.selected_stop_price,request.invalidation_level)
    assert all(leg.last_confirmed_effective_stop_price==life.avg_fill_price for leg in life.stop_legs if leg.filled_quantity==0)
    assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    for _ in range(2):
        assert h.core.run_once();capsys.readouterr()
    assert len(h.unit_writes)==2 and len(h.price_rule_dispatches)==1
    fill_unit_ids(h,life,capsys,[row.orderId for row in list(h.native_open_orders)],price=life.avg_fill_price)
    assert life.filled_qty==0 and not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert engine.capital_authority.total_used_exposure==0 and len(h.unit_writes)==2 and no_external_activity==[]


def test_micro_tightening_unknown_then_callback_can_still_account(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys,fault='unknown')
    assert not h.core.run_once()
    capsys.readouterr()
    engine=h.core.execution_engine
    assert engine._native_quarantined and len(h.unit_writes)==2
    native_id=h.unit_writes[-1][0]
    h.facts[native_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=life.avg_fill_price,
        symbol='JPM',side='SELL',orderId=native_id,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=native_id]
    h.native_quantity[0]-=1
    h.life.clock.current+=__import__('datetime').timedelta(seconds=1)
    h.core.run_once();diagnostics=capsys.readouterr().out
    assert life.filled_qty==0 and engine._native_quarantined and len(h.unit_writes)==2,diagnostics[-7000:]



def test_micro_confirmed_tightening_keeps_cost_failure_active(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from test_standalone_pmh_late_fill_protection import append_micro_cost_bar
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys)
    assert h.core.run_once();capsys.readouterr()
    assert h.failure_owner['stop_price_revision']['status']=='CONFIRMED'
    _,exit_price=append_micro_cost_bar(h,request,life,capsys)
    assert h.failure_owner['pmh_failure_exit']['profile']=='STANDALONE_MICRO_POST_PARTIAL_COST_FAILURE_V1'
    assert [order.orderType for _,order in h.unit_writes]==['MKT','STP','MKT']
    assert life.selected_stop_price==request.stop_loss_price==10.6
    fill_unit_ids(h,life,capsys,[row.orderId for row in list(h.native_open_orders)],price=exit_price)
    assert life.filled_qty==0 and h.core.execution_engine.capital_authority.total_used_exposure==0


@pytest.mark.parametrize('fault',['second_unknown','second_rejected'])
def test_shared_native_partial_remainder_mixed_revision_fill_only_drain(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    # COMPONENT/OWNER proof on accepted genuine Bull partial/remainder. No Micro
    # or relationship enrollment is fabricated to inflate genuine Micro sizing.
    from test_standalone_pmh_late_fill_protection import micro_post_partial_case
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys,family='BULL_FLAG')
    assert request.quantity==4 and life.filled_qty==2 and len(h.unit_writes)==2
    enroll_unit_management(h,monkeypatch,price_revision=True,fault=fault)
    rule,contract=bind_native_price_rule(h,monkeypatch)
    inspected=h.core.inspect_stop_revision_prerequisite(request.client_order_id)
    assert inspected
    proposal,quote,decision,guard=inspected
    engine=h.core.execution_engine
    with pytest.raises(RuntimeError):
        engine.request_stop_revision_prerequisite(request.client_order_id,proposal=proposal,proposed_price='10.70',
            price_rule=rule,contract=contract,route='SMART',quote=quote,decision=decision,authorization_guard=guard)
    remaining=[leg for leg in life.stop_legs if leg.filled_quantity==0]
    assert [leg.stop_price_revision['status'] for leg in remaining]==['CONFIRMED','DISPATCH_UNCERTAIN']
    assert [leg.last_confirmed_effective_stop_price for leg in remaining]==[10.70,10.63]
    assert h.failure_owner['stop_price_revision']['status']=='RESERVED' and engine._native_quarantined
    assert len(h.unit_writes)==4 and not engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    first_stamp=remaining[0].stop_price_revision['confirmed_observed_at']
    for index,leg in enumerate(remaining):
        native_id=int(leg.broker_order_id)
        h.facts[native_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=leg.last_confirmed_effective_stop_price,
            symbol='JPM',side='SELL',orderId=native_id,parentId=71,orderRef='PROTECT|'+life.trade_id)
        h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=native_id]
        h.native_quantity[0]-=1;h.life.clock.current+=__import__('datetime').timedelta(seconds=1)
        h.core.run_once();capsys.readouterr()
        assert life.filled_qty==1-index and engine._native_quarantined and len(h.unit_writes)==4
        state=(life.filled_qty,life.exited_qty,engine.capital_authority.total_used_exposure)
        h.core.run_once();capsys.readouterr()
        assert state==(life.filled_qty,life.exited_qty,engine.capital_authority.total_used_exposure)
    assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert engine.capital_authority.total_used_exposure==0 and remaining[0].stop_price_revision['confirmed_observed_at']==first_stamp
    assert h.failure_owner['stop_price_revision']['status']=='RESERVED' and len(h.unit_writes)==4



@pytest.mark.parametrize('fault',['default_off','quote_equality','quote_stale','quote_future','quote_unconfirmed','unknown_truth','broker_larger','unprofitable_partial','missing_partial_accounting','wrong_occurrence'])
def test_micro_tightening_genuine_route_vetoes(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    from dataclasses import replace
    from datetime import timedelta
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys,enroll=fault!='default_off')
    engine=h.core.execution_engine
    if fault.startswith('quote_'):
        original=h.core.market_data_snapshot_manager.batch_snapshots
        def quotes(symbols):
            values,errors=original(symbols)
            stamp=h.life.clock.current+timedelta(seconds=-16 if fault=='quote_stale' else 1 if fault=='quote_future' else 0)
            return {key:replace(v,bid=life.avg_fill_price if fault=='quote_equality' else v.bid,
                market_timestamp_utc=stamp,asof_utc=stamp,market_data_type_confirmed=fault!='quote_unconfirmed') for key,v in values.items()},errors
        monkeypatch.setattr(h.core.market_data_snapshot_manager,'batch_snapshots',quotes)
    if fault=='unknown_truth':
        from src.ibkr.position_snapshot import BrokerPositionResult
        monkeypatch.setattr(h.native_client,'position_snapshot',lambda:BrokerPositionResult(status='TIMEOUT'))
    if fault=='broker_larger':h.native_quantity[0]+=1
    if fault in {'unprofitable_partial','missing_partial_accounting','wrong_occurrence'}:
        # Negative authority corruption must remain vetoed by real persisted binding.
        action=h.failure_owner['unit_profit_exit']
        if fault=='unprofitable_partial':action['accounted_fill_notional']=str(life.avg_fill_price)
        if fault=='missing_partial_accounting':action.pop('accounted_fill_notional')
        if fault=='wrong_occurrence':action['occurrence']=dict(action['occurrence'],canonical_result_index=999)
    h.core.run_once();capsys.readouterr()
    assert len(h.unit_writes)==1 and not h.failure_owner.get('stop_price_revision')
    assert all(row.order.auxPrice==request.stop_loss_price for row in h.native_open_orders)


@pytest.mark.parametrize('fault',['equality','wick_only','forming','straddling','stale','future','missing','missing_accounting','unprofitable','no_partial','incomplete_partial'])
def test_micro_tightening_pure_measured_bar_and_accounting_boundaries(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    from dataclasses import replace
    from datetime import timedelta
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys)
    owner=deepcopy(h.failure_owner)
    if fault in {'equality','wick_only'}:bar=replace(bar,close=life.avg_fill_price,high=life.avg_fill_price+.03)
    if fault=='forming':bar=replace(bar,timestamp=h.life.clock.current)
    if fault=='straddling':bar=replace(bar,timestamp=datetime.fromisoformat(owner['unit_profit_exit']['last_accounted_fill_at'])-timedelta(seconds=1))
    if fault=='stale':bar=replace(bar,timestamp=bar.timestamp-timedelta(hours=1))
    if fault=='future':bar=replace(bar,timestamp=h.life.clock.current+timedelta(seconds=60))
    if fault=='missing_accounting':owner['unit_profit_exit'].pop('accounted_fill_notional')
    if fault=='unprofitable':owner['unit_profit_exit']['accounted_fill_notional']=str(life.avg_fill_price)
    if fault=='no_partial':owner.pop('unit_profit_exit')
    if fault=='incomplete_partial':owner['unit_profit_exit']['status']='MKT'
    result=h.manager.evaluate_selected_micro_cost_tightening(owner,[] if fault=='missing' else [bar],
        observed_at=h.life.clock.current,session_plan=request.management_session_plan,entry_fill_price=life.avg_fill_price)
    assert result is None and len(h.unit_writes)==1


@pytest.mark.parametrize('tick,admitted',[(.005,True),(.03,False)])
def test_micro_tightening_qualified_grid_and_executable_boundary(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,tick,admitted):
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys)
    from ibapi.message import OUT
    old_send=h.native_client.sendMsg
    def wire(message):
        if message.split('\0')[0]==str(OUT.REQ_MARKET_RULE):h.native_client.marketRule(26,[NS(lowEdge=0,increment=tick)])
        else:old_send(message)
    monkeypatch.setattr(h.native_client,'sendMsg',wire)
    h.core.run_once();capsys.readouterr()
    assert bool(h.failure_owner.get('stop_price_revision')) is admitted
    assert len(h.unit_writes)==(2 if admitted else 1)
    if admitted:assert h.failure_owner['stop_price_revision']['proposed_price']==life.avg_fill_price


def test_micro_tightening_family_and_cost_failure_priority(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from test_standalone_pmh_late_fill_protection import append_micro_cost_bar
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys)
    append_micro_cost_bar(h,request,life,capsys)
    assert not h.failure_owner.get('stop_price_revision')
    assert h.failure_owner['pmh_failure_exit']['profile']=='STANDALONE_MICRO_POST_PARTIAL_COST_FAILURE_V1'
    assert [order.orderType for _,order in h.unit_writes]==['MKT','MKT']
    assert len(h.stop_requests)==request.quantity



@pytest.mark.parametrize('partial_entry',[False,True])
def test_micro_tightening_without_profitable_partial_cannot_enroll(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,partial_entry):
    from test_standalone_pmh_late_fill_protection import enroll_micro_cost_failure
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'MICRO_PULLBACK',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True,partial=partial_entry,micro_clock=(14,5,30))
    from test_standalone_pmh_late_fill_protection import pmh_failure_case
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life),fault='equality',clock_step=5)
    enroll_unit_management(h,monkeypatch,price_revision=True)
    enroll_micro_cost_failure()
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,ROSS_SYNTHETIC_MICRO_COST_TIGHTENING=True))
    assert h.core.run_once();capsys.readouterr()
    parent=h.core.execution_engine._selected_order_records()[request.client_order_id]
    assert not parent.get('unit_profit_exit') and not parent.get('stop_price_revision') and not h.unit_writes
    assert life.filled_qty==(1 if partial_entry else request.quantity)


def test_micro_actual_unprofitable_partial_blocks_tightening(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from test_standalone_pmh_late_fill_protection import micro_post_partial_case,append_micro_cost_bar,enroll_micro_cost_failure
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys,fill_price=10.88,micro_clock=(14,5,30))
    assert h.failure_owner['unit_profit_exit']['status']=='FILLED'
    assert h.failure_owner['unit_profit_exit']['accounted_fill_notional']=='10.88'
    enroll_micro_cost_failure();enroll_unit_management(h,monkeypatch,price_revision=True)
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,ROSS_SYNTHETIC_MICRO_COST_TIGHTENING=True))
    append_micro_cost_bar(h,request,life,capsys,fault='wick')
    assert not h.failure_owner.get('stop_price_revision') and len(h.unit_writes)==1


@pytest.mark.parametrize('fault',['wrong_route','malformed_bands'])
def test_micro_missing_native_price_authority_has_no_fallback(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys)
    if fault=='wrong_route':
        h.native_open_orders[0].contract.exchange='UNQUALIFIED'
    else:
        from ibapi.message import OUT
        old_send=h.native_client.sendMsg
        def wire(message):
            if message.split('\0')[0]==str(OUT.REQ_MARKET_RULE):h.native_client.marketRule(26,[NS(lowEdge=0,increment=0)])
            else:old_send(message)
        monkeypatch.setattr(h.native_client,'sendMsg',wire)
    h.core.run_once();capsys.readouterr()
    assert not h.failure_owner.get('stop_price_revision') and len(h.unit_writes)==1



@pytest.mark.parametrize('fault',['wrong_owner','fractional','oversized','malformed_price','epoch'])
def test_micro_quarantine_drain_rejects_unbound_or_malformed_facts(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys,fault='unknown')
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine;native_id=h.unit_writes[-1][0]
    facts=dict(status='Filled',filled=1,remaining=0,avgFillPrice=life.avg_fill_price,
        symbol='JPM',side='SELL',orderId=native_id,parentId=71,orderRef='PROTECT|'+life.trade_id)
    if fault=='wrong_owner':facts['orderRef']='PROTECT|OTHER'
    if fault=='fractional':facts.update(filled=.5,remaining=.5)
    if fault=='oversized':facts.update(filled=2)
    if fault=='malformed_price':facts['avgFillPrice']=float('nan')
    if fault=='epoch':h.native_client._position_connection_epoch+=1
    h.facts[native_id]=facts
    assert not h.core.run_once();capsys.readouterr()
    assert life.filled_qty==1 and engine._native_quarantined and engine._failsafe_block_new_entries
    assert engine.capital_authority.total_used_exposure>0 and len(h.unit_writes)==2


def test_micro_quarantine_accounting_interruption_forbids_replay(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys,fault='unknown')
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine;native_id=h.unit_writes[-1][0]
    h.facts[native_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=life.avg_fill_price,
        symbol='JPM',side='SELL',orderId=native_id,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_open_orders.clear();h.native_quantity[0]=0
    apply=h.core._apply_execution_results_to_trade_management
    def interrupted(results):raise OSError('synthetic interrupted accounting effect')
    monkeypatch.setattr(h.core,'_apply_execution_results_to_trade_management',interrupted)
    assert not h.core.run_once();capsys.readouterr()
    child=next(row for row in engine._native_orders.values() if row.get('broker_order_id')==str(native_id))
    assert child['cached_update_in_progress'] and life.filled_qty==0
    assert h.manager.snapshot_positions()['JPM'].quantity==1  # Interrupted projection, never certified flat.
    observed=(life.filled_qty,life.exited_qty,engine.capital_authority.total_used_exposure)
    monkeypatch.setattr(h.core,'_apply_execution_results_to_trade_management',apply)
    assert not h.core.run_once();capsys.readouterr()
    assert child['cached_update_in_progress'] and engine._native_quarantined and engine._failsafe_block_new_entries
    assert observed==(life.filled_qty,life.exited_qty,engine.capital_authority.total_used_exposure)
    assert h.manager.snapshot_positions()['JPM'].quantity==1 and len(h.unit_writes)==2


def test_micro_quarantine_fresh_process_cannot_resume(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from test_standalone_pmh_late_fill_protection import assert_readonly_selected_dispatch_restart
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys,fault='unknown')
    assert not h.core.run_once();capsys.readouterr()
    assert_readonly_selected_dispatch_restart(h,request,timeframe='10s',profile='UNIT_MANAGEMENT')
    assert h.core.execution_engine._native_quarantined and life.filled_qty==1


def test_micro_quarantine_enrollment_optout_cannot_drop_actual_fills(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys,fault='unknown')
    assert not h.core.run_once();capsys.readouterr()
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,ROSS_SYNTHETIC_MICRO_COST_TIGHTENING=False))
    native_id=h.unit_writes[-1][0]
    h.facts[native_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=life.avg_fill_price,
        symbol='JPM',side='SELL',orderId=native_id,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_open_orders.clear();h.native_quantity[0]=0
    h.core.run_once();capsys.readouterr()
    assert life.filled_qty==0 and h.core.execution_engine._native_quarantined and len(h.unit_writes)==2


def test_micro_final_write_requires_canonical_lifecycle_identity(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine;inventory=h.native_client.openOrders;changed=[]
    def replace_owner(**kwargs):
        rows=inventory(**kwargs)
        if h.failure_owner.get('stop_price_revision') and not changed:
            engine.post_fill_lifecycle._trades[life.trade_id]=deepcopy(life)
            changed.append(True)
        return rows
    monkeypatch.setattr(h.native_client,'openOrders',replace_owner)
    h.core.run_once();capsys.readouterr()
    assert changed and len(h.unit_writes)==1 and engine._native_quarantined


def test_micro_protective_fill_race_vetoes_write_then_drains(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys)
    inventory=h.native_client.openOrders;observed=[]
    def fill_before_write(**kwargs):
        rows=inventory(**kwargs)
        if h.failure_owner.get('stop_price_revision') and not observed:
            native_id=h.native_open_orders[0].orderId
            h.facts[native_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=request.stop_loss_price,
                symbol='JPM',side='SELL',orderId=native_id,parentId=71,orderRef='PROTECT|'+life.trade_id)
            h.native_open_orders.clear();h.native_quantity[0]=0;observed.append(True)
        return rows
    monkeypatch.setattr(h.native_client,'openOrders',fill_before_write)
    assert not h.core.run_once();capsys.readouterr()
    assert observed and len(h.unit_writes)==1 and h.core.execution_engine._native_quarantined
    h.core.run_once();capsys.readouterr()
    assert life.filled_qty==0 and not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert h.core.execution_engine.capital_authority.total_used_exposure==0
    assert h.core.execution_engine._native_quarantined and h.core.execution_engine._failsafe_block_new_entries
    assert len(h.unit_writes)==1


@pytest.mark.parametrize('fault',['next_date','phase_change','future_partial_stamp'])
def test_micro_tightening_retained_session_and_partial_clock_expiry(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    from datetime import timedelta
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys)
    owner=deepcopy(h.failure_owner);now=h.life.clock.current;plan=request.management_session_plan
    if fault=='next_date':now+=timedelta(days=1)
    if fault=='phase_change':plan='RTH_MID'
    if fault=='future_partial_stamp':owner['unit_profit_exit']['last_accounted_fill_at']=(now+timedelta(seconds=1)).isoformat()
    assert h.manager.evaluate_selected_micro_cost_tightening(owner,[bar],observed_at=now,session_plan=plan,entry_fill_price=life.avg_fill_price) is None
    assert len(h.unit_writes)==1


def test_micro_tightening_scope_cannot_enroll_other_families_or_relationships(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from dataclasses import asdict
    from src.strategies.ross_momentum.strategy_policy import selected_micro_cost_tightening_profile
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys)
    assert selected_micro_cost_tightening_profile(asdict(request))
    other=asdict(request);other['setup_family_id']='BULL_FLAG'
    assert selected_micro_cost_tightening_profile(other) is None
    relationship=asdict(request);relationship['relationship_context']={'profile':'BULL_FLAG_MICRO_MANAGEMENT_V1','action':'ENTRY'}
    assert selected_micro_cost_tightening_profile(relationship) is None
    assert not h.failure_owner.get('stop_price_revision') and len(h.unit_writes)==1


def test_micro_quarantine_cannot_bless_mutated_child_before_accounting(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys,fault='unknown')
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine
    before=h.core.storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
    child=next(row for row in engine._native_orders.values() if row.get('broker_order_id')==str(h.unit_writes[-1][0]))
    child['request']['strategy_name']='UNRELATED'
    assert not h.core.run_once();capsys.readouterr()
    after=h.core.storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
    assert after['orders'][child['request']['client_order_id']]['request']==before['orders'][child['request']['client_order_id']]['request']
    assert life.filled_qty==1 and len(h.unit_writes)==2 and engine._native_quarantined



def test_micro_quarantine_concurrent_callback_frame_cannot_duplicate_accounting(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from threading import Thread
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys,fault='unknown')
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine;native_id=h.unit_writes[-1][0];errors=[];workers=[]
    h.facts[native_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=life.avg_fill_price,
        symbol='JPM',side='SELL',orderId=native_id,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_open_orders.clear();h.native_quantity[0]=0
    reader=engine._provider.cached_order_update
    def attempt():
        try:engine.collect_relationship_updates(result_processor=lambda r:h.core._apply_execution_results_to_trade_management([r]))
        except RuntimeError as error:errors.append(str(error))
    def interleaved(identity):
        if not workers:
            thread=Thread(target=attempt);workers.append(thread);thread.start();thread.join(3)
            assert not thread.is_alive()
        return reader(identity)
    monkeypatch.setattr(engine._provider,'cached_order_update',interleaved)
    try:
        h.core.run_once();capsys.readouterr()
        assert errors==['NATIVE_UNIT_CALLBACK_REENTRANCY'] and life.filled_qty==0
        assert engine.capital_authority.total_used_exposure==0 and engine._native_quarantined
        assert len(h.unit_writes)==2 and not h.manager.snapshot_positions()
    finally:
        for thread in workers:
            thread.join(3);assert not thread.is_alive()


def test_micro_quarantine_reader_cannot_bless_sibling_binding(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,bar,contract=prepare_micro_tightening(reassessment,monkeypatch,tmp_path,capsys,fault='unknown')
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine;native_id=h.unit_writes[-1][0]
    sibling=next(row for row in engine._native_orders.values() if row.get('broker_order_id')==str(h.unit_writes[0][0]))
    before=h.core.storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
    h.facts[native_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=life.avg_fill_price,
        symbol='JPM',side='SELL',orderId=native_id,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_open_orders.clear();h.native_quantity[0]=0
    reader=engine._provider.cached_order_update
    def altered(identity):
        result=reader(identity)
        if str(identity)==str(native_id):sibling['request']['strategy_name']='UNRELATED'
        return result
    monkeypatch.setattr(engine._provider,'cached_order_update',altered)
    assert not h.core.run_once();capsys.readouterr()
    after=h.core.storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
    sibling_id=sibling['request']['client_order_id']
    assert after['orders'][sibling_id]['request']==before['orders'][sibling_id]['request']
    assert life.filled_qty==1 and engine.capital_authority.total_used_exposure>0
    assert len(h.unit_writes)==2 and engine._native_quarantined


# Bull's separately adopted strategy route: genuine four-share native admission,
# actual two-share accounted partial, own cost price, no Micro cost-failure flag.
def prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys,*,clock_time=(14,10,30),enroll=True,fault='none',external_price=None,bands=((0,.01),)):
    from test_standalone_pmh_late_fill_protection import micro_post_partial_case,append_micro_cost_bar
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys,family='BULL_FLAG',bull_clock=clock_time)
    assert request.quantity==4 and life.filled_qty==2 and len(h.unit_writes)==2
    assert not config_resolver.get_ross_synthetic_micro_cost_failure()
    bar,_=append_micro_cost_bar(h,request,life,capsys,fault='wick',external_price=external_price)
    enroll_unit_management(h,monkeypatch,price_revision=True,fault=fault)
    _,contract=bind_native_price_rule(h,monkeypatch,query=False,bands=bands)
    if enroll:
        config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,ROSS_SYNTHETIC_BULL_COST_TIGHTENING=True))
    return h,request,life,bar,contract


@pytest.mark.parametrize('clock_time',[(14,10,30),(16,35,30)],ids=['MORNING_10s','RTH_MID_1m'])
def test_bull_native_core_own_cost_tightening_to_accounted_flat(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,clock_time):
    from src.strategies.ross_momentum.strategy_policy import STANDALONE_BULL_COST_TIGHTENING_PROFILE
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys,clock_time=clock_time)
    engine=h.core.execution_engine
    original=deepcopy((life.avg_fill_price,life.selected_stop_price,request.invalidation_level,request.setup_metadata,h.failure_owner['decision_id']))
    assert len(h.registry_batches[0][1])==33 and request.take_profit_price is None and not request.relationship_context
    assert request.setup_metadata['execution_stream']['execution_trigger_timeframe']==('1m' if clock_time[0]==16 else '10s')
    assert h.core.run_once(),capsys.readouterr().out[-6000:]
    capsys.readouterr();root=h.failure_owner['stop_price_revision']
    assert root['profile']==STANDALONE_BULL_COST_TIGHTENING_PROFILE and root['status']=='CONFIRMED'
    assert root['proposed_price']==life.avg_fill_price==10.88 and life.selected_stop_price==10.63
    assert [order.orderType for _,order in h.unit_writes]==['MKT','MKT','STP','STP']
    assert len(h.price_rule_dispatches)==1
    assert all(leg.last_confirmed_effective_stop_price==10.88 for leg in life.stop_legs if leg.filled_quantity==0)
    assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    for _ in range(2):
        assert h.core.run_once();capsys.readouterr()
    assert len(h.unit_writes)==4 and len(h.price_rule_dispatches)==1
    assert original==(life.avg_fill_price,life.selected_stop_price,request.invalidation_level,request.setup_metadata,h.failure_owner['decision_id'])
    fill_unit_ids(h,life,capsys,[row.orderId for row in list(h.native_open_orders)],price=10.88)
    assert life.filled_qty==0 and not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert engine.capital_authority.total_used_exposure==0 and no_external_activity==[]


@pytest.mark.parametrize('fault',['default_off','quote_equality','quote_stale','quote_future','quote_unconfirmed','unknown_truth','broker_larger','missing_accounting','wrong_occurrence'])
def test_bull_cost_tightening_native_admission_vetoes(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    from datetime import timedelta
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys,enroll=fault!='default_off')
    if fault.startswith('quote_'):
        original=h.core.market_data_snapshot_manager.batch_snapshots
        def quotes(symbols):
            values,errors=original(symbols)
            stamp=h.life.clock.current+timedelta(seconds=-16 if fault=='quote_stale' else 1 if fault=='quote_future' else 0)
            return {key:replace(v,bid=life.avg_fill_price if fault=='quote_equality' else v.bid,
                market_timestamp_utc=stamp,asof_utc=stamp,market_data_type_confirmed=fault!='quote_unconfirmed') for key,v in values.items()},errors
        monkeypatch.setattr(h.core.market_data_snapshot_manager,'batch_snapshots',quotes)
    if fault=='unknown_truth':
        from src.ibkr.position_snapshot import BrokerPositionResult
        monkeypatch.setattr(h.native_client,'position_snapshot',lambda:BrokerPositionResult(status='TIMEOUT'))
    if fault=='broker_larger':h.native_quantity[0]+=1
    if fault=='missing_accounting':h.failure_owner['unit_profit_exit'].pop('accounted_fill_notional')
    if fault=='wrong_occurrence':h.failure_owner['unit_profit_exit']['occurrence']=dict(request.setup_metadata,canonical_result_index=999)
    h.core.run_once();capsys.readouterr()
    assert len(h.unit_writes)==2 and not h.failure_owner.get('stop_price_revision')
    assert all(row.order.auxPrice==10.63 for row in h.native_open_orders)


@pytest.mark.parametrize('fault',['equality','wick','forming','straddling','stale','future','missing','no_partial','incomplete','gross_equality','no_stamp','phase','date'])
def test_bull_cost_tightening_measured_partial_and_clock_boundaries(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    from datetime import timedelta
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys)
    owner=deepcopy(h.failure_owner);now=h.life.clock.current;plan=request.management_session_plan
    if fault in {'equality','wick'}:bar=replace(bar,close=life.avg_fill_price,high=life.avg_fill_price+.03)
    if fault=='forming':bar=replace(bar,timestamp=now)
    if fault=='straddling':bar=replace(bar,timestamp=datetime.fromisoformat(owner['unit_profit_exit']['last_accounted_fill_at'])-timedelta(seconds=1))
    if fault=='stale':bar=replace(bar,timestamp=bar.timestamp-timedelta(hours=1))
    if fault=='future':bar=replace(bar,timestamp=now+timedelta(seconds=60))
    if fault=='no_partial':owner.pop('unit_profit_exit')
    if fault=='incomplete':owner['unit_profit_exit']['status']='MKT'
    if fault=='gross_equality':owner['unit_profit_exit']['accounted_fill_notional']=str(2*life.avg_fill_price)
    if fault=='no_stamp':owner['unit_profit_exit'].pop('last_accounted_fill_at')
    if fault=='phase':plan='RTH_MID'
    if fault=='date':now+=timedelta(days=1)
    assert h.manager.evaluate_selected_bull_cost_tightening(owner,[] if fault=='missing' else [bar],
        observed_at=now,session_plan=plan,entry_fill_price=life.avg_fill_price) is None
    assert len(h.unit_writes)==2 and not h.failure_owner.get('stop_price_revision')


@pytest.mark.parametrize('tick,admitted',[(.005,True),(.03,False)])
def test_bull_cost_tightening_qualified_grid_market_boundary(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,tick,admitted):
    from ibapi.message import OUT
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys)
    send=h.native_client.sendMsg
    def wire(message):
        if message.split('\0')[0]==str(OUT.REQ_MARKET_RULE):h.native_client.marketRule(26,[NS(lowEdge=0,increment=tick)])
        else:send(message)
    monkeypatch.setattr(h.native_client,'sendMsg',wire)
    h.core.run_once();capsys.readouterr()
    assert bool(h.failure_owner.get('stop_price_revision')) is admitted
    assert len(h.unit_writes)==(4 if admitted else 2)
    if admitted:assert all(row.order.auxPrice==10.88 for row in h.native_open_orders)


@pytest.mark.parametrize('fault',['second_unknown','second_rejected','unknown'])
def test_bull_own_tightening_mixed_outcomes_drain_without_retry(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    from datetime import timedelta
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys,fault=fault)
    engine=h.core.execution_engine
    assert not h.core.run_once();capsys.readouterr()
    remaining=[leg for leg in life.stop_legs if leg.filled_quantity==0]
    if fault.startswith('second_'):
        assert [leg.stop_price_revision['status'] for leg in remaining]==['CONFIRMED','DISPATCH_UNCERTAIN']
        assert [leg.last_confirmed_effective_stop_price for leg in remaining]==[10.88,10.63]
    else:
        assert remaining[0].stop_price_revision['status']=='DISPATCH_UNCERTAIN'
        assert [leg.last_confirmed_effective_stop_price for leg in remaining]==[10.63,10.63]
    writes=len(h.unit_writes)
    assert writes==(4 if fault.startswith('second_') else 3)
    assert engine._native_quarantined and h.failure_owner['stop_price_revision']['status']=='RESERVED'
    # Opt-out cannot erase retained factual ownership; contradictory original
    # price observations remain mixed, not compensation/retry permission.
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,ROSS_SYNTHETIC_BULL_COST_TIGHTENING=False))
    for index,leg in enumerate(remaining):
        identity=int(leg.broker_order_id)
        h.facts[identity]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=leg.last_confirmed_effective_stop_price,
            symbol='JPM',side='SELL',orderId=identity,parentId=71,orderRef='PROTECT|'+life.trade_id)
        h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=identity]
        h.native_quantity[0]-=1;h.life.clock.current+=timedelta(seconds=1)
        assert not h.core.run_once();capsys.readouterr()
        assert life.filled_qty==1-index and engine._native_quarantined and len(h.unit_writes)==writes
        state=(life.filled_qty,life.exited_qty,engine.capital_authority.total_used_exposure)
        assert not h.core.run_once();capsys.readouterr()
        assert state==(life.filled_qty,life.exited_qty,engine.capital_authority.total_used_exposure)
    assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert engine.capital_authority.total_used_exposure==0 and engine._failsafe_block_new_entries


@pytest.mark.parametrize('fault',['clock','owner','stop_fill','enrollment'])
def test_bull_tightening_final_write_races_fail_closed(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    from datetime import timedelta
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine;inventory=h.native_client.openOrders;observed=[]
    def changed(**kwargs):
        rows=inventory(**kwargs)
        if h.failure_owner.get('stop_price_revision') and not observed:
            observed.append(True)
            if fault=='clock':h.life.clock.current+=timedelta(seconds=20)
            if fault=='owner':engine.post_fill_lifecycle._trades[life.trade_id]=deepcopy(life)
            if fault=='enrollment':config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,ROSS_SYNTHETIC_BULL_COST_TIGHTENING=False))
            if fault=='stop_fill':
                identity=h.native_open_orders[0].orderId
                h.facts[identity]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.63,
                    symbol='JPM',side='SELL',orderId=identity,parentId=71,orderRef='PROTECT|'+life.trade_id)
                h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=identity]
                h.native_quantity[0]-=1
        return rows
    monkeypatch.setattr(h.native_client,'openOrders',changed)
    assert not h.core.run_once();capsys.readouterr()
    assert observed and len(h.unit_writes)==2 and engine._native_quarantined
    if fault=='stop_fill':
        assert not h.core.run_once();capsys.readouterr()
        assert life.filled_qty==1 and len(h.unit_writes)==2


def test_bull_cost_tightening_cold_restart_remains_quarantined(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from test_standalone_pmh_late_fill_protection import assert_readonly_selected_dispatch_restart
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys,fault='second_unknown')
    assert not h.core.run_once();capsys.readouterr()
    assert_readonly_selected_dispatch_restart(h,request,timeframe='10s',profile='UNIT_MANAGEMENT')
    assert life.filled_qty==2 and h.core.execution_engine._native_quarantined


def test_bull_tightening_scope_cannot_grant_micro_failure_or_relationship_permission(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from dataclasses import asdict
    from src.strategies.ross_momentum.strategy_policy import selected_bull_cost_tightening_profile, selected_micro_cost_failure_profile
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys)
    facts=asdict(request)
    assert selected_bull_cost_tightening_profile(facts) and not selected_micro_cost_failure_profile(facts)
    assert not selected_bull_cost_tightening_profile(dict(facts,relationship_context={'profile':'BULL_FLAG_MICRO_2R_V1','action':'ENTRY'}))
    assert not selected_bull_cost_tightening_profile(dict(facts,setup_family_id='MICRO_PULLBACK'))
    below=replace(bar,close=10.86,low=10.84,high=10.89)
    assert h.manager.evaluate_selected_bull_cost_tightening(h.failure_owner,[below],observed_at=h.life.clock.current,
        session_plan=request.management_session_plan,entry_fill_price=life.avg_fill_price) is None
    assert h.manager.evaluate_selected_micro_cost_failure(h.failure_owner,[below],observed_at=h.life.clock.current,
        session_plan=request.management_session_plan,entry_fill_price=life.avg_fill_price) is None


def test_bull_confirmed_cost_tightening_retains_structural_failure_exit(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from test_standalone_pmh_late_fill_protection import append_micro_cost_bar
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys)
    assert h.core.run_once();capsys.readouterr()
    assert h.failure_owner['stop_price_revision']['status']=='CONFIRMED'
    _,price=append_micro_cost_bar(h,request,life,capsys,fault='family_failure')
    assert 10.63<price<request.setup_metadata['trigger_level']
    assert h.failure_owner['pmh_failure_exit']['profile']=='CENTRAL_STANDALONE_COMPLETED_BAR_FAILURE_V1'
    assert [order.orderType for _,order in h.unit_writes]==['MKT','MKT','STP','STP','MKT','MKT']
    fill_unit_ids(h,life,capsys,[row.orderId for row in list(h.native_open_orders)],price=price)
    assert life.filled_qty==0 and not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert h.core.execution_engine.capital_authority.total_used_exposure==0


def test_bull_quarantined_partial_accounting_interruption_forbids_replay(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys,fault='second_unknown')
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine;identity=h.native_open_orders[0].orderId
    h.facts[identity]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.88,
        symbol='JPM',side='SELL',orderId=identity,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=identity];h.native_quantity[0]-=1
    apply=h.core._apply_execution_results_to_trade_management
    def interrupted(results):raise OSError('synthetic Bull projection interruption')
    monkeypatch.setattr(h.core,'_apply_execution_results_to_trade_management',interrupted)
    assert not h.core.run_once();capsys.readouterr()
    child=next(row for row in engine._native_orders.values() if row.get('broker_order_id')==str(identity))
    assert child['cached_update_in_progress'] and life.filled_qty==1 and h.manager.snapshot_positions()['JPM'].quantity==2
    state=(life.filled_qty,life.exited_qty,engine.capital_authority.total_used_exposure)
    monkeypatch.setattr(h.core,'_apply_execution_results_to_trade_management',apply)
    assert not h.core.run_once();capsys.readouterr()
    assert state==(life.filled_qty,life.exited_qty,engine.capital_authority.total_used_exposure)
    assert child['cached_update_in_progress'] and engine._native_quarantined and len(h.unit_writes)==4


def test_bull_actual_cost_neutral_partial_never_enrolls(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from test_standalone_pmh_late_fill_protection import micro_post_partial_case,append_micro_cost_bar
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys,family='BULL_FLAG',fill_price=10.88,bull_clock=(14,10,30))
    assert h.failure_owner['unit_profit_exit']['accounted_fill_notional']=='21.76'
    enroll_unit_management(h,monkeypatch,price_revision=True)
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,ROSS_SYNTHETIC_BULL_COST_TIGHTENING=True))
    append_micro_cost_bar(h,request,life,capsys,fault='wick')
    assert not h.failure_owner.get('stop_price_revision') and len(h.unit_writes)==2


@pytest.mark.parametrize('partial_entry',[False,True])
def test_bull_without_terminal_accounted_partial_stays_protected(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,partial_entry):
    from test_standalone_pmh_late_fill_protection import pmh_failure_case
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=8,
        risk_cap=4,synthetic_capital=800,unit_stops=True,partial=partial_entry,bull_clock=(14,10,30))
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life),fault='equality',clock_step=5)
    enroll_unit_management(h,monkeypatch,price_revision=True)
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,ROSS_SYNTHETIC_BULL_COST_TIGHTENING=True))
    assert h.core.run_once();capsys.readouterr()
    parent=h.core.execution_engine._selected_order_records()[request.client_order_id]
    assert not parent.get('unit_profit_exit') and not parent.get('stop_price_revision') and not h.unit_writes
    assert life.filled_qty==(1 if partial_entry else 4)
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']



@pytest.mark.parametrize('bands,admitted',[(((0,.01),(10.25,.05)),True),(((0,.01),(10.,.03)),False)],ids=['legal_ceiling','ambiguous_origin_denied'])
def test_bull_cost_tightening_legal_upward_grid_rounding_keeps_frozen_basis(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,bands,admitted):
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys,
        external_price=10.91,bands=bands)
    assert h.core.run_once();capsys.readouterr()
    assert bool(h.failure_owner.get('stop_price_revision')) is admitted
    if admitted:
        assert h.failure_owner['stop_price_revision']['status']=='CONFIRMED'
        assert all(row.order.auxPrice==10.90 for row in h.native_open_orders)
    else:
        assert all(row.order.auxPrice==10.63 for row in h.native_open_orders)
    assert life.avg_fill_price==10.88 and life.selected_stop_price==10.63 and request.invalidation_level==10.63
    assert life.target is None and len(h.unit_writes)==(4 if admitted else 2)


@pytest.mark.parametrize('fault',['wrong_owner','oversized','fractional'])
def test_bull_quarantine_rejects_unbound_or_nonunit_callbacks(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys,fault='second_unknown')
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine;identity=h.native_open_orders[0].orderId
    facts=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.88,
        symbol='JPM',side='SELL',orderId=identity,parentId=71,orderRef='PROTECT|'+life.trade_id)
    if fault=='wrong_owner':facts['orderRef']='PROTECT|OTHER'
    if fault=='oversized':facts['filled']=2
    if fault=='fractional':facts.update(filled=.5,remaining=.5)
    h.facts[identity]=facts
    assert not h.core.run_once();capsys.readouterr()
    assert life.filled_qty==2 and engine._native_quarantined and engine.capital_authority.total_used_exposure>0
    assert len(h.unit_writes)==4


def test_bull_tightening_never_overwrites_unexpected_tighter_native_price(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life,bar,contract=prepare_bull_tightening(reassessment,monkeypatch,tmp_path,capsys,external_price=10.95)
    # Independent unexpected external inventory is not authority to loosen or
    # bless an unowned revision. Original retained structural basis stays intact.
    for row in h.native_open_orders:row.order.auxPrice=10.93
    h.core.run_once();capsys.readouterr()
    assert len(h.unit_writes)==2 and not h.failure_owner.get('stop_price_revision')
    assert all(row.order.auxPrice==10.93 for row in h.native_open_orders)
    assert life.avg_fill_price==10.88 and life.selected_stop_price==10.63


def retained_native_cold_start_case(reassessment,monkeypatch,tmp_path,capsys,*,family='BULL_FLAG',state='confirmed'):
    """Seed through accepted owners; no reconstructed terminal lifecycle records."""
    import json,sqlite3
    if state=='pending_partial':
        h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,family,
            requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
        h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life))
        enroll_unit_management(h,monkeypatch,fault='unknown')
        assert not h.core.run_once();capsys.readouterr()
        assert h.failure_owner['unit_profit_exit']['status']!='FILLED'
        assert any(row.order.orderType=='MKT' for row in h.native_open_orders)
    else:
        factory=prepare_bull_tightening if family=='BULL_FLAG' else prepare_micro_tightening
        uncertain=state in {'mixed','rejected','callback','before_accounting','between_projections'}
        fault=('second_rejected' if state=='rejected' else 'second_unknown' if family=='BULL_FLAG' else 'unknown') if uncertain else 'none'
        h,request,life,bar,contract=factory(reassessment,monkeypatch,tmp_path,capsys,fault=fault)
        engine=h.core.execution_engine
        if state=='before_dispatch':
            write=engine._storage_engine.store_execution_order_state
            def lost_commit(state_id,payload,**kwargs):
                write(state_id,payload,**kwargs)
                if payload['orders'][request.client_order_id].get('stop_price_revision'):
                    raise OSError('synthetic lost reservation commit acknowledgement')
            monkeypatch.setattr(engine._storage_engine,'store_execution_order_state',lost_commit)
        outcome=h.core.run_once();capsys.readouterr()
        assert outcome is (state=='confirmed')
        root=h.failure_owner['stop_price_revision']
        assert root['status']==('CONFIRMED' if state=='confirmed' else 'RESERVED')
        if state in {'callback','before_accounting','between_projections'}:
            identity=h.native_open_orders[0].orderId
            h.facts[identity]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=life.avg_fill_price,
                symbol='JPM',side='SELL',orderId=identity,parentId=71,orderRef='PROTECT|'+life.trade_id)
            h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=identity];h.native_quantity[0]-=1
            if state=='before_accounting':
                write=engine._storage_engine.store_execution_order_state
                def lost_pending_commit(state_id,payload,**kwargs):
                    write(state_id,payload,**kwargs)
                    if any(row.get('cached_update_in_progress') for row in payload['orders'].values()):
                        raise OSError('synthetic interrupted before accounting')
                monkeypatch.setattr(engine._storage_engine,'store_execution_order_state',lost_pending_commit)
            if state=='between_projections':
                def interrupted(results):raise OSError('synthetic interrupted Core projection')
                monkeypatch.setattr(h.core,'_apply_execution_results_to_trade_management',interrupted)
            if state!='callback':
                assert not h.core.run_once();capsys.readouterr()
                assert any(row.get('cached_update_in_progress') for row in engine._native_orders.values())
    engine=h.core.execution_engine
    assert len(h.registry_batches[0][1])==33 and not request.relationship_context
    database=tmp_path/'cold-retained.sqlite3'
    with sqlite3.connect(database) as target:engine._storage_engine._store.connection.backup(target)
    rows=[]
    for row in h.native_open_orders:
        rows.append(dict(orderId=row.orderId,
            contract=dict(symbol=row.contract.symbol,conId=row.contract.conId,exchange='SMART',currency='USD',secType='STK'),
            order={key:getattr(row.order,key,default) for key,default in dict(orderType='',parentId=71,orderRef='',action='SELL',totalQuantity=1,auxPrice=0.,tif='GTC',account='SYNTHETIC_TEST',clientId=71).items()},
            orderState=dict(status=row.orderState.status)))
    facts=dict(now=h.life.clock.current.isoformat(),account='SYNTHETIC_TEST',client_id=71,
        epoch=h.failure_owner['unit_connection_epoch'],root_id=request.client_order_id,
        positions=[dict(symbol='JPM',position=h.native_quantity[0],con_id=123,avgCost=life.avg_fill_price,account='SYNTHETIC_TEST')],
        open_orders=rows,callbacks=h.facts,cycles=2,
        candidate_observations=h.rows,source_timeframe_bars={key:[vars(bar) for bar in value] for key,value in h.streams.items()})
    path=tmp_path/'cold-external-facts.json';path.write_text(json.dumps(facts,default=str))
    return h,request,life,database,path


def assert_full_core_cold_refusal(report,*,expected_cycles=2):
    summary={key:report.get(key) for key in ('constructor_exception','harness_exception','supervisor','evidence_dir')}
    assert not report.get('harness_exception'),summary
    assert report['constructor_complete'] and report['cycle_attempted'],summary
    assert not report['sdk_attempts'] and not report['wire_attempts'] and not report['network_attempts'],summary
    assert report['native_before']==report['native_after_constructor']==report['native_after_cycle'],summary
    for phase in ('after_constructor','after_cycle'):
        state=report[phase]
        assert state['startup_recovery_state']=='RECOVERY_FAILED' and state['native_quarantined'],summary
        assert state['failsafe_block_new_entries'] and state['native_orders']=={},summary
        assert state['post_fill']=={},summary  # No generic aggregate STP/target promotion.
    assert report['registry']==[],summary
    assert len(report['cycles'])==expected_cycles and not report['cached_order_status_reads'],summary
    assert report['mutation_attempts']==dict(place=0,modify=0,cancel=0),summary
    assert not report['external_provider_calls'] and not report['external_history_calls'],summary
    available=report['external_fact_availability']
    assert available['scope']=='RAW_EXTERNAL_FACTS_ONLY_NO_ELIGIBILITY_PROOF',summary
    assert available['provider_boundary_installed'] and available['history_boundary_installed'],summary
    assert available['quotes']['JPM']['bid']>0 and all(available['bar_counts']['JPM'].values()),summary
    for cycle in report['cycles']:
        state=cycle['engine']
        assert state['native_quarantined'] and state['failsafe_block_new_entries'],summary
        for key in ('capital_recovery_failed','capital_reservations','capital_reserved','capital_used','allocation_reservations'):
            assert state[key]==report['after_constructor'][key],summary
        assert state['startup_recovery_state']=='RECOVERY_FAILED' and state['native_orders']=={} and state['post_fill']=={},summary
        assert cycle['native']==report['native_before'] and cycle['sdk_attempts_after']==0,summary
        assert cycle['cached_reads_before']==cycle['cached_reads_after']==0,summary
        assert {k:v for k,v in cycle['database'].items() if k!='runs'}=={k:v for k,v in report['database_before'].items() if k!='runs'},summary
        faults=cycle['fault_events']
        assert [(row['event_type'],row['payload']['message']) for row in faults]==[
            ('FAULT_DETECTED','NATIVE_ORDER_RECOVERY_REQUIRED'),
            ('FAULT_ACTION_TAKEN','NATIVE_ORDER_RECOVERY_REQUIRED')],summary
        assert faults[1]['payload']['recommended_action']=='ABORT_CYCLE',summary
    for phase in ('database_after_constructor','database_after_cycle','database_final'):
        assert {k:v for k,v in report[phase].items() if k!='runs'}=={k:v for k,v in report['database_before'].items() if k!='runs'},summary
    supervisor=report['supervisor']
    assert supervisor['reaped'] and not supervisor['timed_out'] and supervisor['distinct_process'],summary
    assert supervisor['child_pid_matched'] and supervisor['child_parent_matched'],summary
    assert supervisor['returncode']==0 and supervisor['pipes_closed'] and not supervisor['errors'],summary
    assert report['cleanup']['live_threads']==[],summary
    assert report['cleanup']['manager_disconnected'] and report['cleanup']['storage_closed'],summary


@pytest.mark.parametrize('progress_failure',['before_write','lost_write_ack'])
def test_native_canonical_commit_progress_interruption_retains_cold_quarantine(
        reassessment,monkeypatch,tmp_path,capsys,no_external_activity,progress_failure):
    """Canonical commit does not imply cross-owner native progress committed."""
    import json,sqlite3
    from datetime import timedelta
    from test_standalone_pmh_late_fill_protection import (
        late_pmh,acknowledge,deliver_native_execution,teardown_unsent_fixture)
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    h=late_pmh(reassessment,monkeypatch,tmp_path,fill_price=10.53)
    try:
        request=acknowledge(h,capsys)
        engine=h.core.execution_engine
        write=engine._storage_engine.store_execution_order_state
        attempts=[]
        def interrupted(state_id,payload,**kwargs):
            feedback=[feedback for order in payload['orders'].values()
                for feedback in order.get('canonical_feedback',[])]
            if any(row.get('applied_execution_ids') for row in feedback):
                attempts.append(progress_failure)
                if progress_failure=='lost_write_ack':write(state_id,payload,**kwargs)
                raise OSError('synthetic canonical-to-native progress '+progress_failure)
            return write(state_id,payload,**kwargs)
        monkeypatch.setattr(engine._storage_engine,'store_execution_order_state',interrupted)
        deliver_native_execution(h,native_id=71,execution_id='committed-before-progress',side='BOT',
            quantity=1,cumulative=1,price=10.53,average=10.53,
            timestamp=datetime(2026,10,20,13,35,42,tzinfo=timezone.utc))
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.53)
        h.native_quantity[0]=1;h.native_open_orders.clear()
        h.life.clock.current+=timedelta(seconds=1)
        assert not h.core.run_once();capsys.readouterr()
        life=engine.post_fill_lifecycle.get_trade(request.client_order_id)
        assert attempts and life.filled_qty==1 and life.avg_fill_price==10.53
        assert life.selected_stop_price==request.stop_loss_price and life.selected_target_price is None
        assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
        assert h.manager.snapshot_positions()['JPM'].quantity==1
        assert h.core.trade_registry.snapshot()[0].quantity==1
        assert len(h.sent_native)==len(h.stop_requests)==1 and len(h.registry_batches[0][1])==33
        canonical=h.core.trade_lifecycle_engine.get_trade(request.client_order_id)
        assert canonical.quantity_open==1 and canonical.entry_avg_price==10.53
        assert canonical.stop_price==request.stop_loss_price and canonical.target_price is None
        events=h.core.storage_engine.fetch_trade_lifecycle_events()
        assert len(events)==1 and events[0]['execution_id']=='committed-before-progress'
        assert engine._native_quarantined and engine._failsafe_block_new_entries
        parent=engine._native_orders[request.client_order_id]
        assert parent['cached_update_in_progress'] and parent['canonical_feedback'][0]['state']=='UNCERTAIN'
        assert not h.core.trade_lifecycle_engine.native_feedback_snapshot()['available']
        retained=engine._storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
        progress=retained['orders'][request.client_order_id]['canonical_feedback'][0]
        assert progress['state']=='IN_PROGRESS'
        assert progress['applied_execution_ids']==(
            ['committed-before-progress'] if progress_failure=='lost_write_ack' else [])
        monkeypatch.setattr(engine._storage_engine,'store_execution_order_state',write)
        before=deepcopy((engine.position_records,parent,engine.capital_authority.total_used_exposure,
            h.manager.snapshot_positions(),h.core.trade_registry.snapshot(),events))
        for _ in range(2):
            h.life.clock.current+=timedelta(seconds=1)
            assert not h.core.run_once();capsys.readouterr()
        assert before==deepcopy((engine.position_records,parent,engine.capital_authority.total_used_exposure,
            h.manager.snapshot_positions(),h.core.trade_registry.snapshot(),
            h.core.storage_engine.fetch_trade_lifecycle_events()))
        assert engine._native_quarantined and len(h.sent_native)==len(h.stop_requests)==1

        database=tmp_path/'canonical-progress-retained.sqlite3'
        with sqlite3.connect(database) as target:engine._storage_engine._store.connection.backup(target)
        inventory=[]
        for row in h.native_open_orders:
            inventory.append(dict(orderId=row.orderId,
                contract=dict(symbol=row.contract.symbol,conId=row.contract.conId,
                    exchange='SMART',currency='USD',secType='STK'),
                order={key:getattr(row.order,key,default) for key,default in dict(orderType='',
                    parentId=71,orderRef='',action='SELL',totalQuantity=1,auxPrice=0.,tif='GTC',
                    account='SYNTHETIC_TEST',clientId=h.native_client.client_id).items()},
                orderState=dict(status=row.orderState.status)))
        facts=dict(now=h.life.clock.current.isoformat(),account='SYNTHETIC_TEST',
            client_id=h.native_client.client_id,epoch=h.native_client._position_connection_epoch,
            root_id=request.client_order_id,
            positions=[dict(symbol='JPM',position=1,con_id=123,avgCost=10.53,account='SYNTHETIC_TEST')],
            open_orders=inventory,callbacks=h.facts,cycles=2,candidate_observations=h.rows,
            source_timeframe_bars={key:[vars(bar) for bar in value] for key,value in h.streams.items()})
        path=tmp_path/'canonical-progress-external-facts.json'
        path.write_text(json.dumps(facts,default=str))
        report=run_native_core_cold_start(database,path,tmp_path/'canonical-progress-child')
        assert_full_core_cold_refusal(report)
        # The unchanged actual tables include the committed canonical pair, not
        # just the retained native marker. Startup does not replay either owner.
        assert len(report['database_before']['trade_lifecycle_events'])==1
        assert report['database_before']['trade_lifecycle_events'][0]['execution_id']=='committed-before-progress'
    finally:teardown_unsent_fixture(h,no_external_activity)



def test_real_core_cold_start_cannot_rewrite_retained_bull_protection(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    h,request,life,database,facts=retained_native_cold_start_case(reassessment,monkeypatch,tmp_path,capsys)
    report=run_native_core_cold_start(database,facts,tmp_path/'child')
    assert not report.get('sdk_attempts'),report
    assert not report.get('wire_attempts'),report
    assert report['native_before']==report['native_after_constructor']==report['native_after_cycle'],report
    assert report['after_cycle']['native_quarantined'] and report['after_cycle']['failsafe_block_new_entries'],report
    assert report['supervisor']['reaped'] and not report['supervisor']['timed_out'],report


def test_real_core_cold_start_conflicting_flat_facts_cannot_clear_uncertainty(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    import json
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    h,request,life,database,path=retained_native_cold_start_case(reassessment,monkeypatch,tmp_path,capsys,state='mixed')
    facts=json.loads(path.read_text());facts.update(positions=[],open_orders=[]);path.write_text(json.dumps(facts))
    report=run_native_core_cold_start(database,path,tmp_path/'child-flat-conflict')
    assert report['constructor_complete'],report.get('constructor_exception')
    assert report['after_constructor']['startup_recovery_state']=='RECOVERY_FAILED',report['after_constructor']['startup_recovery_result']
    assert report['after_constructor']['native_quarantined'],report['after_constructor']['startup_recovery_result']
    assert not report['sdk_attempts'] and not report['wire_attempts']


@pytest.mark.parametrize('family,state',[
    ('BULL_FLAG','confirmed'),('MICRO_PULLBACK','confirmed'),
    ('BULL_FLAG','mixed'),('BULL_FLAG','rejected'),('MICRO_PULLBACK','mixed'),
    ('BULL_FLAG','before_dispatch'),('BULL_FLAG','pending_partial'),
    ('MICRO_PULLBACK','callback'),('BULL_FLAG','before_accounting'),('BULL_FLAG','between_projections')])
def test_full_core_cold_start_retained_transition_matrix(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family,state):
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    h,request,life,database,path=retained_native_cold_start_case(reassessment,monkeypatch,tmp_path,capsys,family=family,state=state)
    report=run_native_core_cold_start(database,path,tmp_path/'child-transition')
    assert_full_core_cold_refusal(report)
    if state=='pending_partial':
        orders=report['native_before']['orders']
        assert any(row.get('unit_amendment',{}).get('status')=='DISPATCH_UNCERTAIN' for row in orders.values())
        assert all(not row.get('stop_price_revision') for row in orders.values())



def test_real_core_corrupt_null_native_state_is_not_absent(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    import json,sqlite3
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    h,request,life,database,path=retained_native_cold_start_case(reassessment,monkeypatch,tmp_path,capsys,state='mixed')
    # Explicit CORRUPT-RECORD control, never positive lifecycle provenance.
    with sqlite3.connect(database) as db:
        db.execute("UPDATE position_lifecycle_transitions SET reason='null' WHERE transition_id='execution.native_orders.v1:PAPER'")
    facts=json.loads(path.read_text());facts.update(positions=[],open_orders=[]);path.write_text(json.dumps(facts))
    report=run_native_core_cold_start(database,path,tmp_path/'child-null-record')
    assert not report['constructor_complete'],report.get('after_constructor')
    assert not report['sdk_attempts'] and not report['wire_attempts']
    assert report['supervisor']['reaped'] and not report['supervisor']['timed_out']


def test_full_core_cold_start_external_disagreements_and_repeated_startup(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    import json
    from datetime import timedelta
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    h,request,life,database,path=retained_native_cold_start_case(reassessment,monkeypatch,tmp_path,capsys,state='mixed')
    baseline=json.loads(path.read_text());scenarios=[]
    for fault in ('account','client','epoch','native_identity','quantity','flat','positions_missing','orders_incomplete','stale','callbacks','reenrollment','repeat'):
        facts=deepcopy(baseline);boundary='none'
        if fault=='account':facts['account']='OTHER_ACCOUNT'
        if fault=='client':facts['client_id']+=1
        if fault=='epoch':facts['epoch']+=1
        if fault=='native_identity':facts['open_orders'][0]['orderId']+=1000
        if fault=='quantity':facts['positions'][0]['position']+=1
        if fault=='flat':facts.update(positions=[],open_orders=[])
        if fault in ('positions_missing','orders_incomplete'):boundary=fault
        if fault=='stale':facts['now']=(datetime.fromisoformat(facts['now'])+timedelta(days=1)).isoformat()
        if fault=='callbacks':
            identity=str(facts['open_orders'][0]['orderId'])
            filled={identity:dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.88,parentId=71,clientId=71)}
            older={identity:dict(status='Submitted',filled=0,remaining=1,avgFillPrice=0,parentId=71,clientId=71)}
            facts['callback_frames']=[filled,older,filled]
        if fault=='reenrollment':facts['config']=dict(ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=8,ROSS_SYNTHETIC_UNIT_STOPS=True,
            ROSS_SYNTHETIC_UNIT_MANAGEMENT=True,ROSS_SYNTHETIC_BULL_COST_TIGHTENING=True,
            ROSS_SYNTHETIC_MICRO_COST_FAILURE=True,ROSS_SYNTHETIC_MICRO_COST_TIGHTENING=True)
        if fault=='stale':
            stale_facts=tmp_path/'stale-facts.json';stale_facts.write_text(json.dumps(facts))
        else:
            scenarios.append(dict(facts,name=fault,fault=boundary))
    # Every variant still reaches two actual Core cycles. Native recovery stops
    # BEFORE these external facts are consumed; restarting for every unused
    # variant repeated import/constructor/snapshot work without new authority.
    batched=tmp_path/'batched-facts.json'
    batched.write_text(json.dumps(dict(baseline,cycle_scenarios=scenarios)))
    report=run_native_core_cold_start(database,batched,tmp_path/'child-adversity')
    assert_full_core_cold_refusal(report,expected_cycles=2*len(scenarios))
    assert report['constructor_count']==1
    assert report['scenario_scope']=='EXTERNAL_ADVERSITY_AFTER_ONE_FRESH_CONSTRUCTOR'
    assert [row['name'] for row in report['scenarios']]==[row['name'] for row in scenarios]
    for scenario,expected in zip(report['scenarios'],scenarios,strict=True):
        assert len(scenario['cycle_indices'])==2
        applied=scenario['applied_external_facts']
        assert applied['name']==scenario['name']
        for key in ('account','client_id','epoch','positions','open_orders','fault'):
            assert applied[key]==expected[key],(scenario['name'],key)
        assert [report['cycles'][index-1]['scenario'] for index in scenario['cycle_indices']]==[scenario['name']]*2
        for key,value in expected.get('config',{}).items():
            assert applied['config'][key]==value
    assert report['types']['core']=='src.core.orchestrator.CoreOrchestrator'
    assert report['types']['broker']=='src.brokers.ibkr_live_broker.IbkrLiveBroker'
    assert report['types']['engine']=='src.execution.execution_engine.ExecutionEngine'
    assert report['after_constructor']['startup_recovery_result']['reason']=='NATIVE_ORDER_RESTART_RECONCILIATION_REQUIRED'
    # A +1day clock change can legitimately make scheduled prep due in an
    # existing process. Keep that case fresh; never alter prep owner intervals.
    stale=run_native_core_cold_start(database,stale_facts,tmp_path/'child-stale')
    assert_full_core_cold_refusal(stale)
    # Separate fresh interpreter repeats startup against the very same durable
    # retained DB; batching is not labelled twelve independent cold starts.
    combined=deepcopy(baseline)
    combined.update(account='OTHER_ACCOUNT',client_id=baseline['client_id']+1,epoch=baseline['epoch']+1)
    combined['open_orders'][0]['orderId']+=1000;combined['positions'][0]['position']+=1
    combined_path=tmp_path/'repeat-disagreements.json';combined_path.write_text(json.dumps(combined))
    repeat=run_native_core_cold_start(database,combined_path,tmp_path/'child-fresh-repeat')
    assert_full_core_cold_refusal(repeat)
    assert repeat['pid']!=report['pid']
    assert repeat['initial_external_scope']=={key:combined[key] for key in ('account','client_id','epoch')}


@pytest.fixture(scope='module')
def cold_corrupt_seed_paths(tmp_path_factory):
    # Closed immutable seed only; every corruption child gets a private copy.
    root=tmp_path_factory.mktemp('cold-corrupt-seed')
    return root/'genuine.sqlite3',root/'external-facts.json'


@pytest.mark.parametrize('raw',['{not-json','null','[]','42','{}'])
def test_full_core_cold_start_corrupt_records_remain_unresolved(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,cold_corrupt_seed_paths,raw):
    import shutil,sqlite3
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    seed,seed_facts=cold_corrupt_seed_paths
    if not seed.exists():
        h,request,life,generated,generated_facts=retained_native_cold_start_case(reassessment,monkeypatch,tmp_path,capsys)
        shutil.copyfile(generated,seed);shutil.copyfile(generated_facts,seed_facts)
    original_seed=seed.read_bytes()
    database=tmp_path/'corrupt-copy.sqlite3';path=tmp_path/'corrupt-facts.json'
    shutil.copyfile(seed,database);shutil.copyfile(seed_facts,path)
    # Deliberate corruption AFTER genuine lifecycle generation; not a positive seed.
    with sqlite3.connect(database) as db:
        db.execute("UPDATE position_lifecycle_transitions SET reason=? WHERE transition_id='execution.native_orders.v1:PAPER'",(raw,))
    report=run_native_core_cold_start(database,path,tmp_path/'child-corrupt')
    assert not report['sdk_attempts'] and not report['wire_attempts'] and not report['network_attempts']
    assert report['database_before']['position_lifecycle_transitions']==report['database_final']['position_lifecycle_transitions']
    assert seed.read_bytes()==original_seed  # Corruption never mutates shared evidence.
    if raw=='{}':
        assert_full_core_cold_refusal(report)  # Existing opaque record is never absence.
    else:
        assert not report['constructor_complete'] and report['constructor_exception']
        assert not report['cycle_attempted']
    assert report['supervisor']['reaped'] and not report['supervisor']['timed_out']


def test_full_core_no_retained_native_state_preserves_real_startup_control(runtime_schema_template,tmp_path):
    import json,shutil
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    database=tmp_path/'empty-core.sqlite3';shutil.copyfile(runtime_schema_template,database)
    path=tmp_path/'empty-facts.json';path.write_text(json.dumps(dict(positions=[],open_orders=[],cycles=0)))
    report=run_native_core_cold_start(database,path,tmp_path/'empty-child')
    assert report['constructor_complete'],report.get('constructor_exception') or report.get('harness_exception')
    state=report['after_constructor']
    assert state['startup_recovery_state']=='RECOVERY_COMPLETE' and not state['native_quarantined']
    assert state['native_state'] is None and not report['sdk_attempts'] and not report['network_attempts']
    assert not report['cycle_attempted']  # Constructor control, NOT a new admission proof.
    assert report['supervisor']['reaped'] and report['cleanup']['live_threads']==[]


def test_full_core_child_failure_and_timeout_are_owned_and_reaped(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    import sqlite3
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    h,request,life,database,path=retained_native_cold_start_case(reassessment,monkeypatch,tmp_path,capsys)
    failed=run_native_core_cold_start(database,path,tmp_path/'failed-child',fault='constructor_failure')
    assert not failed['constructor_complete'] and 'SYNTHETIC_EXTERNAL_MANAGER_FACTORY_FAILURE' in str(failed['constructor_exception'])
    assert failed['supervisor']['reaped'] and failed['supervisor']['pipes_closed']
    timed=run_native_core_cold_start(database,path,tmp_path/'timed-child',fault='timeout',timeout=3)
    assert timed['supervisor']['timed_out'] and timed['supervisor']['reaped'] and timed['supervisor']['pipes_closed']
    assert timed['supervisor']['child_pid_matched'] and timed['supervisor']['child_parent_matched']
    assert not timed.get('sdk_attempts') and not timed.get('wire_attempts')
    # OS process exit releases the child's handles; verify the DB is unlocked.
    with sqlite3.connect(database,timeout=1) as db:
        db.execute('BEGIN IMMEDIATE');db.rollback()




def _pristine_native_quote_facts(h, monkeypatch, row):
    """Actual SDK encoders/callback owners; only read transport is synthetic."""
    from dataclasses import asdict
    from ibapi.message import OUT
    from src.adapters.brokers.ibkr import ibkr_client as native_module
    from src.ibkr import market_data_client as source_quote_module
    from test_news_catalyst_lifecycle_audit import CANDIDATE
    native = native_module.IbkrClient('offline.invalid', 1, 999, 1, 'LIVE', True)
    native.isConnected = lambda: True
    native.serverVersion = lambda: 180  # Supplied synthetic SDK handshake; no connection.
    native.managedAccounts('SYNTHETIC_TEST')
    native.nextValidId(1000)
    transport = []
    supplied = ContractDetails()
    supplied.contract = Contract()
    for key,value in dict(symbol='JPM',conId=123,exchange='SMART',currency='USD',secType='STK',localSymbol='JPM').items():
        setattr(supplied.contract,key,value)
    supplied.longName = CANDIDATE.company_name
    def read_transport(message):
        fields = message.split('\0')
        opcode = int(fields[0])
        transport.append(opcode)
        if opcode == OUT.REQ_CONTRACT_DATA:
            req_id = int(fields[2])
            native.contractDetails(req_id, supplied)
            native.contractDetailsEnd(req_id)
        elif opcode == OUT.REQ_MKT_DATA:
            req_id = int(fields[2])
            native.marketDataType(req_id,1)
            for kind,value in ((1,row['bid']),(2,row['ask']),(4,row['last_price']),
                    (9,row['prev_close'])):
                native.tickPrice(req_id,kind,value,None)
            native.tickSize(req_id,8,row['volume'])
            stamp = __import__('datetime').datetime.fromisoformat(row['quote_timestamp_utc'])
            native.tickString(req_id,45,str(int(stamp.timestamp())))
            native.tickSnapshotEnd(req_id)
        elif opcode not in (OUT.REQ_MARKET_DATA_TYPE, OUT.CANCEL_MKT_DATA):
            raise AssertionError('Unprovided or mutating source quote request: '+str(opcode))
    native.sendMsg = read_transport
    with monkeypatch.context() as context:
        context.setattr(native_module,'datetime',h.life.clock)
        context.setattr(source_quote_module,'datetime',h.life.clock)
        context.setattr(native,'reqContractDetails',_NATIVE_QUOTE_CONTRACT_ENCODER.__get__(native))
        context.setattr(EClient,'reqMktData',_NATIVE_QUOTE_MARKET_ENCODER)
        snapshot = native.get_market_snapshot('JPM')
    assert snapshot.returned_market_data_type == 'LIVE' and snapshot.market_data_type_confirmed
    assert snapshot.snapshot_complete and snapshot.market_timestamp_utc.isoformat() == row['quote_timestamp_utc']
    assert snapshot.last == 10.53 and snapshot.close == 9.4
    return asdict(snapshot), dict(company_name=supplied.longName,long_name=supplied.longName,
        aliases=CANDIDATE.aliases,con_id=supplied.contract.conId,exchange=supplied.contract.exchange,
        currency=supplied.contract.currency,instrument_type=supplied.contract.secType,
        local_symbol=supplied.contract.localSymbol), transport

def _pristine_native_cycle_facts(reassessment, monkeypatch, tmp_path):
    """Reuse raw PMH observations; child owners determine selection/admission."""
    import json
    from test_joined_core_pmh_readonly import pmh_joined
    h = pmh_joined(reassessment, monkeypatch, tmp_path / 'external-facts', position_case='complete_empty')
    from src.strategies.ross_momentum.patterns import pattern_trace
    from src.scanner import scanner_runner
    from test_ross_pr1051_readonly_catalyst_wiring import _RuntimeProvider
    from src.utils.time_utils import to_ny_time
    # These are independently supplied existing fixture facts, never inverted
    # from a desired percentage/RVOL score: PMH PAPER's previous9.4 and the
    # PR1051 external provider's explicit ADV200000/window20.
    external_rows = deepcopy(h.rows)
    raw_provider = _RuntimeProvider([dict(symbol='JPM',last=10.53,prev_close=9.4,
        bid=10.52,ask=10.54,volume=2_000_000,avg_volume=200_000,float_shares=8_000_000)])
    quote = h.c.provider.refresh_quote('JPM')
    row = external_rows['JPM']
    adv,window = raw_provider.get_average_daily_volume('JPM',20)
    stats = raw_provider.get_intraday_stats('JPM')
    row.update(prev_close=raw_provider.get_previous_rth_close('JPM'),
        ref_close_rth=raw_provider.get_previous_rth_close('JPM'),
        current_intraday_volume=stats.current_intraday_volume,
        average_daily_volume_20d=adv,average_daily_volume_window_days=window,
        historical_outcome=stats.historical_outcome,historical_end_received=stats.historical_end_received,
        quote_timestamp_utc=quote.timestamp_utc,quote_timestamp_source=quote.timestamp_source)
    snapshot,identity,quote_transport = _pristine_native_quote_facts(h,monkeypatch,row)
    row.update(identity)
    row.update(close=snapshot['close'],requested_market_data_type=snapshot['requested_market_data_type'],
        returned_market_data_type=snapshot['returned_market_data_type'],
        market_data_type_confirmed=snapshot['market_data_type_confirmed'],
        received_at_utc=snapshot['received_at_utc'],
        market_data_type_received_at_utc=snapshot['market_data_type_received_at_utc'],
        snapshot_complete=snapshot['snapshot_complete'],request_id=snapshot['request_id'])
    metadata = scanner_runner._news_symbol_metadata_for_contexts([dict(symbol='JPM',**identity)])
    candidates = scanner_runner._news_candidates_for_symbols(['JPM'],metadata)
    # Regenerate the receipt with the actual service and raw provider; do not
    # hand-author a profile matching the future consumer.
    h.life.service.get_news(candidates,h.life.request,h.life.policy)
    cache = json.loads(h.life.store.cache_path.read_text())
    bucket = cache['news_intelligence']['symbols']['JPM']
    local_clock = to_ny_time(h.life.clock.current)
    pre_limit = max(2,min(722,int((local_clock-local_clock.replace(hour=4,minute=0,second=0,microsecond=0)).total_seconds()//60)+2))
    history = {tf:pattern_trace.get_intraday_bars(symbol='JPM',timeframe=tf,
        limit=pre_limit if tf=='1m' else len(bars)) for tf,bars in h.streams.items()}
    facts = dict(observe_pristine_readonly_cycle=True,
        now=h.life.clock.current.isoformat(), account='SYNTHETIC_TEST', client_id=999,
        positions=[], open_orders=[], cycles=1,
        candidate_observations=external_rows,
        source_timeframe_bars={tf: [vars(bar) for bar in response.bars] for tf,response in history.items()},
        historical_source_responses={tf:dict(status=response.status,end_received=response.end_received,
            contract_identity=__import__('dataclasses').asdict(response.contract_identity)) for tf,response in history.items()},
        external_quote_snapshots={'JPM':snapshot},source_quote_transport=quote_transport,
        news_evidence={'JPM': bucket['evidence']},
        news_last_retrieval={'JPM': bucket['last_retrieval']},
        config=dict(RUN_MODE='READ_ONLY', RUN_MODE_EFFECTIVE='READ_ONLY',
            EXECUTION_ENABLED=False, IBKR_READONLY_ENABLED=True,
            IBKR_ORDER_SUBMISSION_ENABLED=False, IBKR_API_WRITE_ALLOWED=False,
            NEWS_ENABLED=True, ROSS_ISSUER_QUERY_ENABLED=True,
            SCANNER_DATA_SOURCE='IBKR', LIVE_EXECUTION_PROBE_MODE=False))
    return facts


def test_pristine_fresh_process_first_cycle_reaches_actual_readonly_risk(
        reassessment, monkeypatch, tmp_path, capsys, no_external_activity, runtime_schema_template):
    """New process proof; no retained native permission or prepared decision."""
    import json, shutil
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    facts = _pristine_native_cycle_facts(reassessment,monkeypatch,tmp_path)
    database = tmp_path / 'pristine-first-cycle.sqlite3'
    shutil.copyfile(runtime_schema_template,database)
    path = tmp_path / 'pristine-first-cycle-facts.json'
    path.write_text(json.dumps(facts, default=str))
    report = run_native_core_cold_start(database, path, tmp_path / 'pristine-first-cycle-child')
    summary = {key: report.get(key) for key in ('constructor_exception', 'harness_exception',
        'cycle_exception', 'stage', 'supervisor', 'evidence_dir')}
    assert report.get('constructor_complete') and report.get('cycle_attempted'), summary
    assert report['cycle_result'] is True and not report.get('cycle_exception'), summary
    assert not report.get('harness_exception'), summary
    assert report['native_before'] is report['native_after_constructor'] is report['native_after_cycle'] is None
    assert report['after_cycle']['capital_reservations'] == {}
    assert report['after_cycle']['allocation_reservations'] == {}
    assert not report['sdk_attempts'] and not any(row['mutation'] for row in report['wire_attempts']), summary
    assert report['native_read_requests'] and len(report['native_read_requests'])==len(report['wire_attempts']), summary
    assert not report['network_attempts'] and not report.get('native_curl_denials'), summary
    assert not report.get('capital_enrollment_attempts'), summary
    assert report.get('registry_evaluations') and all(row['result_count'] == 33
        for row in report['registry_evaluations']), summary
    assert report.get('decision_artifacts'), summary
    assert len(report.get('risk_evaluations', [])) == 1, summary
    assessed = report['risk_evaluations'][0]
    decision, intent = assessed['decision'], assessed['intent']
    artifact = report['decision_artifacts'][0]
    assert decision['reason_code'] == 'LIVE_READ_ONLY_BLOCK' and decision['allowed'] is False, summary
    assert decision['timestamp'] == intent['timestamp_utc'] == artifact['created_at'] == facts['now']
    assert decision['evaluated_limits']['session'] == 'RTH'
    assert decision['evaluated_limits']['prep_only'] is False
    assert artifact['session_phase'] == 'OPENING_0_30'
    assert decision['decision_id'] == intent['decision_id'] == artifact['decision_id']
    assert intent['take_profit_price'] is None
    assert report['supervisor']['reaped'] and not report['supervisor']['timed_out']
    assert report['cleanup']['live_threads'] == []
    assert report['cleanup']['core_shutdown_complete'] is True, report['cleanup']
    assert no_external_activity==[]


def _pristine_paper_child_function(name, namespace):
    """Compile only the actual fixture boundary, never run a Core child."""
    import ast
    from test_startup_recovery_and_stop_protection import _NATIVE_CORE_COLD_START_CHILD
    tree=ast.parse(_NATIVE_CORE_COLD_START_CHILD)
    node=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name==name)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),
        '<actual-pristine-paper-boundary>','exec'),namespace)
    return namespace[name]


def _pristine_positive_fee_boundary_case(monkeypatch):
    """Fake owners plus actual SDK packets; no Core or child application."""
    import os
    from threading import Event
    from decimal import Decimal
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    class Denied(BaseException):pass
    now=datetime(2026,10,20,13,35,34,tzinfo=timezone.utc)
    plan=dict(account='SYNTHETIC_TEST',client_id=999,epoch=0,symbol='JPM',con_id=123,
        currency='USD',fill_price=10.53,stop_fill_price=10.28)
    rows={native_id:[dict(orderId=native_id,execId=exec_id,account=plan['account'],clientId=999,
        connection_epoch=0,conId=123,symbol='JPM',secType='STK',side=side,shares=1,cumQty=1,
        price=Decimal(str(price)),avgPrice=Decimal(str(price)),timestamp_utc=now-timedelta(seconds=1))]
        for native_id,exec_id,side,price in ((71,'fee-entry','BOT',10.53),(72,'fee-stop','SLD',10.28))}
    client=NS(client_id=999,_position_connection_epoch=0,_managed_accounts=['SYNTHETIC_TEST'],
        _stop_event=Event(),_position_transport_available=True,isConnected=lambda:True,
        serverVersion=lambda:180,_request_id_conflicted=lambda rid:False)
    client.cached_native_executions=lambda native_id:tuple(rows[native_id])
    client.cached_native_execution_fees=lambda native_id:tuple(dict(execution=row,
        execution_currency='USD') for row in rows[native_id])
    parent=dict(account=plan['account'],native_client_id=999,native_connection_epoch=0,
        decision_id='risk-1',request=dict(client_order_id='ROOT',symbol='JPM',quantity=1,take_profit_price=None))
    candidate=dict(root_order_id='ROOT',source_client=client,account=plan['account'],
        entry_terminal=True,entry_status='FILLED',entry_requested_quantity=1,entry_filled_quantity=1,
        decision_id='risk-1')
    candidates={'ROOT':candidate}
    engine=NS(run_mode=NS(value='PAPER'),_native_scope=(plan['account'],client,now),
        _native_callback_client=lambda:client,_native_quarantined=False,startup_recovery_complete=lambda:True,
        capital_authority=NS(capital_scope=None,_capital_writer=None),_native_orders={'ROOT':parent},
        native_roundtrip_fee_candidates=lambda:candidates)
    core=NS(run_mode=NS(value='PAPER'),execution_engine=engine,
        connection_manager=NS(get_ibkr_client=lambda **kwargs:client if kwargs=={'ensure_connected':False} else None),
        _latest_position_truth_snapshot=NS(snapshot_status='HEALTHY',broker_positions={},system_positions={}))
    query=dict(status='PARTIAL',account=plan['account'],client_id=999,epoch=0,
        completed_at=None,currency=None,tags=set(),event=Event(),deadline=101.)
    context=dict(request_type='ACCOUNT_CURRENCY_STRICT',account_currency_query=query)
    client._request_context_by_req_id={91:context}
    client._request_type_by_req_id={91:'ACCOUNT_CURRENCY_STRICT'}
    packets=[];sdk=EClient(NS(error=lambda *args:pytest.fail('Unexpected synthetic SDK error')))
    sdk.isConnected=lambda:True;sdk.serverVersion_=180;sdk.sendMsg=packets.append
    _NATIVE_LEDGER_READ_ENCODER(sdk,91,'All','$LEDGER');_NATIVE_LEDGER_CANCEL_ENCODER(sdk,91)
    response=dict(account=plan['account'],end_received=True,rows=[
        dict(tag='CashBalance',value='123.45',currency='USD'),dict(tag='AccruedCash',value='0',currency='USD')])
    dispatches=[dict(role='entry',native_id=71,root_id='ROOT',order=dict(parentId=0)),
        dict(role='stop',native_id=72,root_id='ROOT',order=dict(parentId=71))]
    return NS(client=client,core=core,engine=engine,plan=plan,now=now,Denied=Denied,
        query=query,context=context,candidate=candidate,candidates=candidates,parent=parent,
        packets=packets,response=response,owned={},dispatches=dispatches,rows=rows,
        currency_guard=_pristine_paper_child_function('validate_pristine_paper_currency_read',
            dict(os=os,datetime=datetime,ForbiddenExternalIO=Denied)),
        fee_guard=_pristine_paper_child_function('validate_pristine_paper_fee_fact',
            dict(os=os,datetime=datetime,ForbiddenExternalIO=Denied)))


def _call_pristine_currency_guard(h,fields,*,actual_client=None):
    return h.currency_guard(actual_client=h.client if actual_client is None else actual_client,
        expected_client=h.client,core=h.core,plan=h.plan,fields=fields,owned_reads=h.owned,
        response=h.response,now=h.now,monotonic_now=100.,max_scope_age=15)


@pytest.mark.parametrize('fault',['none','other_client','mode','callback_owner','connection_owner',
    'boolean_client','boolean_epoch','epoch','account','multiple_accounts','stopped','disconnected','transport',
    'stale_scope','future_scope','quarantined','capital_writer','truth_unknown','truth_owned','no_candidate',
    'unfinished_entry','boolean_filled','candidate_client','candidate_account','candidate_decision',
    'unowned','context_kind','map_kind','conflict','repeat','query_status','query_account','query_client',
    'query_epoch','query_event','query_currency','query_tags','query_completion','deadline_equal','deadline_late',
    'packet_group','packet_tags','packet_version','packet_trailer','packet_extra','packet_id',
    'response_end','response_account','response_currency'])
def test_pristine_positive_fee_currency_read_requires_exact_owned_sdk_packet(monkeypatch,fault):
    h=_pristine_positive_fee_boundary_case(monkeypatch);fields=h.packets[0].split('\0')
    assert fields==['62','1','91','All','$LEDGER','']
    actual=h.client
    if fault=='other_client':actual=NS()
    elif fault=='mode':h.core.run_mode.value='LIVE_READ_ONLY'
    elif fault=='callback_owner':h.engine._native_callback_client=lambda:NS()
    elif fault=='connection_owner':h.core.connection_manager.get_ibkr_client=lambda **kwargs:NS()
    elif fault=='boolean_client':h.client.client_id=True
    elif fault=='boolean_epoch':h.client._position_connection_epoch=False
    elif fault=='epoch':h.client._position_connection_epoch=1
    elif fault=='account':h.client._managed_accounts=['OTHER']
    elif fault=='multiple_accounts':h.client._managed_accounts.append('OTHER')
    elif fault=='stopped':h.client._stop_event.set()
    elif fault=='disconnected':h.client.isConnected=lambda:False
    elif fault=='transport':h.client._position_transport_available=False
    elif fault=='stale_scope':h.engine._native_scope=(h.plan['account'],h.client,h.now-timedelta(seconds=16))
    elif fault=='future_scope':h.engine._native_scope=(h.plan['account'],h.client,h.now+timedelta(microseconds=1))
    elif fault=='quarantined':h.engine._native_quarantined=True
    elif fault=='capital_writer':h.engine.capital_authority._capital_writer=object()
    elif fault=='truth_unknown':h.core._latest_position_truth_snapshot.snapshot_status='UNKNOWN'
    elif fault=='truth_owned':h.core._latest_position_truth_snapshot.broker_positions={'JPM':NS(quantity=1)}
    elif fault=='no_candidate':h.candidates.clear()
    elif fault=='unfinished_entry':h.candidate['entry_terminal']=False
    elif fault=='boolean_filled':h.candidate['entry_filled_quantity']=True
    elif fault=='candidate_client':h.candidate['source_client']=NS()
    elif fault=='candidate_account':h.candidate['account']='OTHER'
    elif fault=='candidate_decision':h.candidate['decision_id']='OTHER'
    elif fault=='unowned':h.client._request_context_by_req_id.clear()
    elif fault=='context_kind':h.context['request_type']='ACCOUNT_SUMMARY'
    elif fault=='map_kind':h.client._request_type_by_req_id[91]='ACCOUNT_SUMMARY'
    elif fault=='conflict':h.client._request_id_conflicted=lambda rid:True
    elif fault=='repeat':h.owned[91]={}
    elif fault=='query_status':h.query['status']='COMPLETE'
    elif fault=='query_account':h.query['account']='OTHER'
    elif fault=='query_client':h.query['client_id']=True
    elif fault=='query_epoch':h.query['epoch']=False
    elif fault=='query_event':h.query['event'].set()
    elif fault=='query_currency':h.query['currency']='USD'
    elif fault=='query_tags':h.query['tags']={'CashBalance'}
    elif fault=='query_completion':h.query['completed_at']=h.now
    elif fault=='deadline_equal':h.query['deadline']=100.
    elif fault=='deadline_late':h.query['deadline']=99.
    elif fault=='packet_group':fields[3]='OTHER'
    elif fault=='packet_tags':fields[4]='AvailableFunds'
    elif fault=='packet_version':fields[1]='2'
    elif fault=='packet_trailer':fields[-1]='EXTRA'
    elif fault=='packet_extra':fields.append('')
    elif fault=='packet_id':fields[2]='0091'
    elif fault=='response_end':h.response['end_received']=False
    elif fault=='response_account':h.response['account']='OTHER'
    elif fault=='response_currency':h.response['rows'][0]['currency']='EUR'
    if fault!='none':
        with pytest.raises(h.Denied):_call_pristine_currency_guard(h,fields,actual_client=actual)
    else:
        request_id,role,context,query=_call_pristine_currency_guard(h,fields)
        assert (request_id,role)==(91,'REQUEST') and context is h.context and query is h.query
    assert h.owned==({91:{}} if fault=='repeat' else {})


@pytest.mark.parametrize('fault',['none','before_end','active_query','active_map','replaced_context','unowned',
    'repeat','epoch','account','query_account','query_client','query_epoch','query_currency','query_status',
    'query_tags','event_unset','future_completion','stale_completion','record_client','packet_id','packet_extra'])
def test_pristine_positive_fee_currency_cancel_requires_retired_end_complete_owner(monkeypatch,fault):
    h=_pristine_positive_fee_boundary_case(monkeypatch);fields=h.packets[1].split('\0')
    assert fields==['63','1','91','']
    h.query.update(status='COMPLETE',currency='USD',tags={'CashBalance','AccruedCash'},completed_at=h.now)
    h.query['event'].set();h.context.pop('account_currency_query');h.client._request_type_by_req_id.clear()
    record=dict(context=h.context,query=h.query,client=h.client,account=h.plan['account'],
        epoch=0,cancelled=False,end_observed=True);h.owned[91]=record
    if fault=='before_end':record['end_observed']=False
    elif fault=='active_query':h.context['account_currency_query']=h.query
    elif fault=='active_map':h.client._request_type_by_req_id[91]='ACCOUNT_CURRENCY_STRICT'
    elif fault=='replaced_context':h.client._request_context_by_req_id[91]=dict(h.context)
    elif fault=='unowned':h.owned.clear()
    elif fault=='repeat':record['cancelled']=True
    elif fault=='epoch':h.client._position_connection_epoch=1
    elif fault=='account':h.client._managed_accounts=['OTHER']
    elif fault=='query_account':h.query['account']='OTHER'
    elif fault=='query_client':h.query['client_id']=True
    elif fault=='query_epoch':h.query['epoch']=False
    elif fault=='query_currency':h.query['currency']='EUR'
    elif fault=='query_status':h.query['status']='TIMEOUT'
    elif fault=='query_tags':h.query['tags']={'CashBalance'}
    elif fault=='event_unset':h.query['event'].clear()
    elif fault=='future_completion':h.query['completed_at']=h.now+timedelta(microseconds=1)
    elif fault=='stale_completion':h.query['completed_at']=h.now-timedelta(seconds=16)
    elif fault=='record_client':record['client']=NS()
    elif fault=='packet_id':fields[2]='92'
    elif fault=='packet_extra':fields.append('')
    if fault!='none':
        with pytest.raises(h.Denied):_call_pristine_currency_guard(h,fields)
    else:
        request_id,role,context,query=_call_pristine_currency_guard(h,fields)
        assert (request_id,role)==(91,'CANCEL') and context is h.context and query is h.query
    assert record['cancelled'] is (fault=='repeat')  # Validation does not forge cleanup.


@pytest.mark.parametrize('leg',['entry','stop'])
@pytest.mark.parametrize('fault',['none','other_client','epoch','missing_execution','extra_execution',
    'wrong_execution','wrong_order','wrong_account','wrong_client','wrong_epoch','wrong_security',
    'wrong_side','wrong_quantity','wrong_price','future','repeat','amount','zero','negative','boolean',
    'currency','extra_field','unknown_leg','wrong_parent','raw_execution_currency'])
def test_pristine_positive_fee_callback_requires_exact_cached_execution(monkeypatch,leg,fault):
    h=_pristine_positive_fee_boundary_case(monkeypatch);native_id=71 if leg=='entry' else 72
    execution=h.rows[native_id][0]
    raw=dict(leg=leg,execId=execution['execId'],commission=.01 if leg=='entry' else .02,currency='USD')
    delivered=set();actual=h.client
    if fault=='other_client':actual=NS()
    elif fault=='epoch':h.client._position_connection_epoch=1
    elif fault=='missing_execution':h.rows[native_id].clear()
    elif fault=='extra_execution':h.rows[native_id].append(dict(execution,execId='EXTRA'))
    elif fault=='wrong_execution':raw['execId']='OTHER'
    elif fault=='wrong_order':execution['orderId']=73
    elif fault=='wrong_account':execution['account']='OTHER'
    elif fault=='wrong_client':execution['clientId']=1
    elif fault=='wrong_epoch':execution['connection_epoch']=False
    elif fault=='wrong_security':execution['conId']=124
    elif fault=='wrong_side':execution['side']='SLD' if leg=='entry' else 'BOT'
    elif fault=='wrong_quantity':execution['shares']=2
    elif fault=='wrong_price':execution['price']=10.54
    elif fault=='future':execution['timestamp_utc']=h.now+timedelta(microseconds=1)
    elif fault=='repeat':delivered.add(raw['execId'])
    elif fault=='amount':raw['commission']=.03
    elif fault=='zero':raw['commission']=0
    elif fault=='negative':raw['commission']=-.01
    elif fault=='boolean':raw['commission']=True
    elif fault=='currency':raw['currency']='EUR'
    elif fault=='extra_field':raw['unprovided']=True
    elif fault=='unknown_leg':raw['leg']='OTHER'
    elif fault=='wrong_parent':next(row for row in h.dispatches if row['role']==leg)['order']['parentId']=999
    elif fault=='raw_execution_currency':h.client.cached_native_execution_fees=lambda native_id:tuple(
        dict(execution=row,execution_currency='EUR') for row in h.rows[native_id])
    call=lambda:h.fee_guard(actual_client=actual,expected_client=h.client,core=h.core,plan=h.plan,
        dispatches=h.dispatches,raw=raw,delivered=delivered,now=h.now)
    if fault!='none':
        with pytest.raises(h.Denied):call()
    else:
        bound,row=call();assert bound['native_id']==native_id and row is execution


@pytest.mark.parametrize('opcode',['62','63'])
@pytest.mark.parametrize('opt_in',['absent','not_paper'])
def test_pristine_positive_fee_read_does_not_open_default_or_nonpaper_wire_routes(opcode,opt_in):
    from ibapi.message import OUT
    class Denied(BaseException):pass
    report=dict(wire_attempts=[]);underlying=[]
    facts=dict(observe_pristine_paper_cycle=opt_in!='not_paper')
    if opt_in=='not_paper':facts['observe_pristine_paper_positive_fee_feedback']=True
    boundary=_pristine_paper_child_function('send_message',dict(OUT=OUT,report=report,
        observe_pristine_cycle=True,facts=facts,ForbiddenExternalIO=Denied,SyntheticWriteBoundary=Denied,
        client=NS(sendMsg=lambda packet:underlying.append(packet))))
    with pytest.raises(Denied):boundary(opcode+'\0')
    assert underlying==[] and report['wire_attempts']==[dict(opcode=opcode,mutation=False)]


def test_pristine_positive_fee_boundary_uses_real_public_callbacks_and_sdk_ledger_owner(monkeypatch,tmp_path):
    """Native source component only: fake Core owners, no Core construction/run."""
    import time
    from decimal import Decimal
    from ibapi.execution import Execution
    from ibapi.message import OUT
    from src.adapters.brokers.ibkr import ibkr_client as native_module
    h=_pristine_positive_fee_boundary_case(monkeypatch)
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH',str(tmp_path/'native-fee-order-ids.json'))
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return cls.fromtimestamp(h.now.timestamp(),tz=tz)
    monkeypatch.setattr(native_module,'datetime',Clock)
    client=native_module.IbkrClient('offline.invalid',0,999,1,'LIVE',False)
    client.isConnected=lambda:True;client.serverVersion_=180
    client.nextValidId(71);client.managedAccounts('SYNTHETIC_TEST')
    h.client=client;h.engine._native_scope=(h.plan['account'],client,h.now)
    h.engine._native_callback_client=lambda:client;h.candidate['source_client']=client
    h.core.connection_manager.get_ibkr_client=lambda **kwargs:client if kwargs=={'ensure_connected':False} else None
    delivered=set()
    deliver=_pristine_paper_child_function('deliver_pristine_paper_fee_fact',
        dict(validate_pristine_paper_fee_fact=h.fee_guard))
    for leg,native_id,exec_id,side,price,amount in (
            ('entry',71,'fee-entry','BOT',10.53,.01),('stop',72,'fee-stop','SLD',10.28,.02)):
        contract=Contract();contract.symbol='JPM';contract.secType='STK';contract.conId=123;contract.currency='USD'
        execution=Execution();execution.orderId=native_id;execution.execId=exec_id
        execution.acctNumber='SYNTHETIC_TEST';execution.clientId=999;execution.side=side
        execution.shares=execution.cumQty=Decimal(1);execution.price=execution.avgPrice=price
        execution.time=(h.now-timedelta(seconds=1)).isoformat()
        client.execDetails(-1,contract,execution)
        observed=deliver(client=client,core=h.core,plan=h.plan,dispatches=h.dispatches,
            raw=dict(leg=leg,execId=exec_id,commission=amount,currency='USD'),delivered=delivered,now=h.now)
        assert observed['native_id']==native_id and observed['exec_id']==exec_id
    assert delivered=={'fee-entry','fee-stop'}
    views=[row for native_id in (71,72) for row in client.cached_native_execution_fees(native_id)]
    assert [row['amount'] for row in views]==[Decimal('.01'),Decimal('.02')]
    assert all(row['report_status']=='BOUND_API_REPORT' and row['net_status']=='UNAVAILABLE_FOR_NET'
        and row['first_report']['commission_presence_source']=='UNAVAILABLE' for row in views)
    report=dict(wire_attempts=[],native_read_requests=[]);owned={}
    facts=dict(observe_pristine_paper_cycle=True,observe_pristine_paper_positive_fee_feedback=True,
        paper_memory_plan=h.plan,paper_currency_response=h.response)
    boundary=_pristine_paper_child_function('send_message',dict(OUT=OUT,report=report,
        observe_pristine_cycle=True,facts=facts,ForbiddenExternalIO=h.Denied,SyntheticWriteBoundary=h.Denied,
        client=client,core=h.core,owned_currency_reads=owned,observed=h.now,real_elapsed_time=time,
        validate_pristine_paper_currency_read=h.currency_guard,
        plain=lambda value:value.isoformat() if isinstance(value,datetime) else value))
    client.sendMsg=boundary
    client.reqAccountSummary=lambda *args:_NATIVE_LEDGER_READ_ENCODER(client,*args)
    client.cancelAccountSummary=lambda *args:_NATIVE_LEDGER_CANCEL_ENCODER(client,*args)
    result=client.account_currency_snapshot(expected_account='SYNTHETIC_TEST',timeout_seconds=.5)
    assert result.status=='COMPLETE' and result.currency=='USD' and result.account=='SYNTHETIC_TEST'
    assert result.client_id==999 and result.connection_epoch==0 and result.completed_at==h.now
    assert result.cancellation_attempted and result.cleanup_complete
    assert [row['opcode'] for row in report['wire_attempts']]==['62','63']
    assert [row['request_type'] for row in report['native_read_requests']]==[
        'ACCOUNT_CURRENCY_STRICT','OWNED_ACCOUNT_CURRENCY_CANCEL']
    assert result.request_id not in client._request_type_by_req_id
    assert client._request_context_by_req_id[result.request_id].get('account_currency_query') is None
    assert owned[result.request_id]['cancelled'] and owned[result.request_id]['end_observed']
    # Exercise the exact report expression without constructing/running Core.
    # Immutable Mapping views must survive JSON, not become diagnostic strings.
    import ast,json
    from test_startup_recovery_and_stop_protection import _NATIVE_CORE_COLD_START_CHILD
    tree=ast.parse(_NATIVE_CORE_COLD_START_CHILD)
    assignment=next(node for node in ast.walk(tree) if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Subscript) and isinstance(target.slice,ast.Constant)
            and target.slice.value=='fee_source_observations' for target in node.targets))
    plain=_pristine_paper_child_function('plain',dict(datetime=datetime))
    copied=eval(compile(ast.Expression(assignment.value),'<actual-fee-source-observer>','eval'),
        dict(client=client,report=dict(synthetic_memory_dispatches=h.dispatches),plain=plain))
    serialized=json.loads(json.dumps(copied,default=str))
    assert len(serialized)==2 and all(isinstance(row,dict) for row in serialized)
    assert {row['execution']['execId'] for row in serialized}=={'fee-entry','fee-stop'}
    assert all(row['first_report']['currency']=='USD' and row['net_status']=='UNAVAILABLE_FOR_NET'
        for row in serialized)


@pytest.mark.parametrize('fault',['none','other_client','epoch','mode','size','boolean_size','side',
    'type','repeat','durable','target','risk','reservation','capital_order','allocation_order',
    'capital_symbol','allocation_symbol','capital_size','allocation_remaining','allocation_status',
    'capital_side','allocation_strategy','allocation_mode','allocation_missing','capital_decision_missing',
    'allocation_global_link','stop_none','stop_wrong_parent',
    'stop_wrong_price','stop_wrong_position','stop_wrong_progress','stop_missing_accounting',
    'stop_missing_execution','stop_wrong_execution'])
def test_pristine_paper_memory_boundary_rejects_unprovided_writes(monkeypatch,fault):
    """Pure fake-owner safety check: no Core/application or real transport."""
    import os
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    class Denied(BaseException):pass
    guard=_pristine_paper_child_function('validate_pristine_paper_memory_write',
        dict(os=os,ForbiddenExternalIO=Denied))
    now=datetime(2026,10,20,13,35,30,tzinfo=timezone.utc)
    plan=dict(account='SYNTHETIC_TEST',client_id=999,epoch=0,symbol='JPM',con_id=123,
        currency='USD',exchange='SMART',entry_price=10.3,stop_price=10.2897,fill_price=10.53)
    client=NS(client_id=999,_position_connection_epoch=0,readonly_enabled=False,isConnected=lambda:True)
    request=dict(client_order_id='root',symbol='JPM',quantity=1,setup_family_id='PREMARKET_HIGH_BREAK',
        relationship_context=None,setup_metadata=dict(occurrence='component-only'),stop_loss_price=10.2897,
        invalidation_level=10.3,take_profit_price=None,target_model='component descriptive objective',
        direction='LONG',strategy_name='RossMomentumStrategyV1')
    parent=dict(request=request,requested=1,account='SYNTHETIC_TEST',native_client_id=999,
        native_connection_epoch=0,decision_id='decision',status='DISPATCH_UNCERTAIN',
        broker_order_id=None,filled=0,terminal=False)
    state=dict(version=1,mode='PAPER',orders=dict(root=parent))
    capital_reservation=NS(decision_id='cap-component',order_id='root',symbol='JPM',side='LONG',
        strategy_id='RossMomentumStrategyV1',run_mode='PAPER',status='ACTIVE',quantity=1,
        remaining_quantity=1,filled_quantity=0,exposure_notional=0.,notional=10.3,remaining_notional=10.3)
    allocation_reservation=NS(**vars(capital_reservation))
    allocation_reservation.decision_id='strat-alloc-component'
    allocation_reservation.strategy_id='ROSSMOMENTUMSTRATEGYV1'
    allocation_reservation.global_capital_decision_id='cap-component'
    capital=NS(capital_scope=None,_capital_writer=None,total_reserved_capital=10.3,total_used_exposure=0,
        active_reservations=dict(r=capital_reservation))
    allocation=NS(active_reservations=dict(a=allocation_reservation))
    engine=NS(run_mode=NS(value='PAPER'),_native_scope=('SYNTHETIC_TEST',client,now),
        capital_authority=capital,strategy_allocation_authority=allocation,
        _native_quarantined=False,startup_recovery_complete=lambda:True,
        _native_state=state,_native_orders=state['orders'],position_records={},trade_registry=NS(snapshot=lambda:[]))
    core=NS(run_mode=NS(value='PAPER'),execution_engine=engine)
    contract=NS(symbol='JPM',secType='STK',currency='USD',exchange='SMART',conId=0)
    native=NS(action='BUY',orderType='MKT',totalQuantity=1,parentId=0,orderRef='')
    risk=[dict(decision=dict(decision_id='decision',allowed=True,max_position_size=1),
        intent=dict(entry_price=10.3,setup_metadata=deepcopy(request['setup_metadata']),target_model=request['target_model']))]
    args=dict(actual_client=client,expected_client=client,core=core,plan=plan,dispatches=[],native_id=1000,
        contract=contract,native=native,committed=deepcopy(state),risk_rows=risk,now=now,max_scope_age=15)
    if fault.startswith('stop_'):
        args['native_id']=1001
        args['dispatches']=[dict(native_id=1000,role='entry')]
        parent['broker_order_id']='1000'
        parent['cached_update_in_progress']=dict(filled=1,remaining=0,status='FILLED',average_price=10.53)
        capital.total_reserved_capital=0;capital.total_used_exposure=10.53
        engine.position_records=dict(root=dict(filled_qty=1,entry_price=10.53))
        life=NS(filled_qty=1,avg_fill_price=10.53,selected_stop_price=10.2897,stop=NS(status='PENDING_SUBMIT'))
        engine.post_fill_lifecycle=NS(get_trade=lambda key:life)
        external_position=NS(symbol='JPM',position=1,con_id=123,account='SYNTHETIC_TEST',avgCost=10.53)
        client.positions=lambda:[external_position]
        execution=dict(orderId=1000,account='SYNTHETIC_TEST',clientId=999,connection_epoch=0,
            conId=123,symbol='JPM',side='BOT',shares=1,cumQty=1,price=10.53,avgPrice=10.53,timestamp_utc=now)
        client.cached_native_executions=lambda native_id:[execution]
        native.action='SELL';native.orderType='STP';native.auxPrice=10.2897
        native.parentId=1000;native.orderRef='PROTECT|root'
        if fault=='stop_wrong_parent':native.parentId=999
        if fault=='stop_wrong_price':native.auxPrice=10.29
        if fault=='stop_wrong_position':external_position.position=2
        if fault=='stop_wrong_progress':parent['cached_update_in_progress']['filled']=2
        if fault=='stop_missing_accounting':engine.position_records={}
        if fault=='stop_missing_execution':client.cached_native_executions=lambda native_id:[]
        if fault=='stop_wrong_execution':execution['side']='SLD'
        args['committed']=deepcopy(state)
    if fault=='other_client':args['actual_client']=NS()
    if fault=='epoch':client._position_connection_epoch=1
    if fault=='mode':core.run_mode.value='READ_ONLY'
    if fault=='size':native.totalQuantity=2
    if fault=='boolean_size':native.totalQuantity=True
    if fault=='side':native.action='SELL'
    if fault=='type':native.orderType='LMT'
    if fault=='repeat':args['dispatches']=[dict(native_id=1000,role='entry')]
    if fault=='durable':args['committed']={}
    if fault=='target':
        request['target_model']=None
        args['committed']=deepcopy(state)
    if fault=='risk':risk[0]['decision']['allowed']=False
    if fault=='reservation':capital.total_reserved_capital=0
    if fault=='capital_order':capital_reservation.order_id='unrelated'
    if fault=='allocation_order':allocation_reservation.order_id='unrelated'
    if fault=='capital_symbol':capital_reservation.symbol='PEER'
    if fault=='allocation_symbol':allocation_reservation.symbol='PEER'
    if fault=='capital_size':capital_reservation.quantity=True
    if fault=='allocation_remaining':allocation_reservation.remaining_quantity=0
    if fault=='allocation_status':allocation_reservation.status='RELEASED'
    if fault=='capital_side':capital_reservation.side='SELL'
    if fault=='allocation_strategy':allocation_reservation.strategy_id='OTHER'
    if fault=='allocation_mode':allocation_reservation.run_mode='LIVE'
    if fault=='allocation_missing':allocation.active_reservations={}
    if fault=='capital_decision_missing':capital_reservation.decision_id=None
    if fault=='allocation_global_link':allocation_reservation.global_capital_decision_id=parent['decision_id']
    underlying=[]
    def fake_memory_transport():
        binding=guard(**args)
        underlying.append(binding)
    if fault in {'none','stop_none'}:
        fake_memory_transport()
        assert underlying==[('root','stop' if fault=='stop_none' else 'entry')]
    else:
        with pytest.raises(Denied):fake_memory_transport()
        assert underlying==[]


@pytest.mark.parametrize('opcode',['3','4','58','25','987654'])
def test_pristine_paper_global_wire_boundary_denies_mutations_and_unknown(opcode):
    """Actual child send boundary; fake underlying writer is never invoked."""
    from ibapi.message import OUT
    class Denied(BaseException):pass
    underlying=[];report=dict(wire_attempts=[])
    boundary=_pristine_paper_child_function('send_message',dict(OUT=OUT,report=report,
        observe_pristine_cycle=True,facts=dict(observe_pristine_paper_cycle=True),
        ForbiddenExternalIO=Denied,SyntheticWriteBoundary=Denied,
        client=NS(sendMsg=lambda message:underlying.append(message))))
    with pytest.raises(Denied):boundary(opcode+'\0')
    assert underlying==[] and report['wire_attempts']


@pytest.mark.parametrize('fault',['none','other_client','epoch','mode','unprotected','wrong_family',
    'wrong_timeframe','accounting_pending','root_account','root_client','root_epoch','root_security',
    'unowned','retired','late','repeat','conflict','not_sent',
    'packet_security','packet_timeframe','packet_duration','packet_end','packet_rth','packet_streaming',
    'packet_options','missing_end','missing_bars'])
def test_pristine_paper_history_boundary_uses_owned_sdk_request_and_original_bars(monkeypatch,fault):
    """Real read encoder, fake owners/underlying transport; no Core process."""
    import os
    from src.adapters.data.historical_bar_timeframes import resolve_intraday_timeframe_request
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    class Denied(BaseException):pass
    guard=_pristine_paper_child_function('validate_pristine_paper_history_read',
        dict(os=os,ForbiddenExternalIO=Denied))
    request=resolve_intraday_timeframe_request(timeframe='10s',requested_bars=10)
    packets=[];sdk=EClient(NS(error=lambda *args:pytest.fail('Unexpected synthetic SDK error')))
    sdk.isConnected=lambda:True;sdk.serverVersion_=180;sdk.sendMsg=packets.append
    contract=Contract();contract.symbol='JPM';contract.conId=123;contract.secType='STK'
    contract.exchange='SMART';contract.currency='USD';contract.localSymbol='JPM'
    _NATIVE_HISTORY_READ_ENCODER(sdk,1007,contract,'',str(request.duration_seconds)+' S',
        request.bar_size_setting,'TRADES',0,1,False,[])
    assert len(packets)==1
    fields=packets[0].split('\0')
    now=datetime(2026,10,20,13,35,31,tzinfo=timezone.utc)
    state=dict(status='PENDING',sent=True,end_received=False,streaming=False,deadline=10.)
    client=NS(client_id=999,_position_connection_epoch=0,isConnected=lambda:True,serverVersion=lambda:180,
        _request_context_by_req_id={1007:dict(request_type='HISTORICAL_DATA',symbol='JPM',con_id=123)},
        _request_type_by_req_id={1007:'HISTORICAL_DATA'},_historical_states={1007:state},
        _request_id_conflicted=lambda request_id:False)
    parent=dict(side='LONG',symbol='JPM',terminal=True,filled=1,requested=1,protection_confirmed=True,
        account='SYNTHETIC_TEST',native_client_id=999,native_connection_epoch=0,security_id=123,
        request=dict(client_order_id='root',symbol='JPM',setup_family_id='PREMARKET_HIGH_BREAK',
            relationship_context={},stop_loss_price=10.2897,invalidation_level=10.3,take_profit_price=None,
            setup_metadata=dict(execution_stream=dict(execution_trigger_timeframe='10s'))))
    engine=NS(run_mode=NS(value='PAPER'),_native_scope=('SYNTHETIC_TEST',client,now),
        _native_callback_client=lambda:client,_native_orders=dict(root=parent),_native_quarantined=False)
    core=NS(run_mode=NS(value='PAPER'),execution_engine=engine)
    plan=dict(account='SYNTHETIC_TEST',client_id=999,epoch=0,symbol='JPM',con_id=123,
        exchange='SMART',currency='USD',entry_price=10.3,stop_price=10.2897)
    bars=[NS(timestamp=datetime(2026,10,20,13,35,20,tzinfo=timezone.utc),
        open=10.31,high=10.55,low=10.30,close=10.53,volume=1500)]
    args=dict(actual_client=client,expected_client=client,core=core,plan=plan,fields=fields,
        owned_reads=set(),timeframe_request=request,source_response=dict(status='COMPLETE_BARS',end_received=True),
        supplied_bars=bars,now=now,monotonic_now=1.,max_scope_age=15.)
    if fault=='other_client':args['actual_client']=NS()
    if fault=='epoch':client._position_connection_epoch=1
    if fault=='mode':core.run_mode.value='READ_ONLY'
    if fault=='unprotected':parent['protection_confirmed']=False
    if fault=='wrong_family':parent['request']['setup_family_id']='KEY_LEVEL_BREAK'
    if fault=='wrong_timeframe':parent['request']['setup_metadata']['execution_stream']['execution_trigger_timeframe']='1m'
    if fault=='accounting_pending':parent['cached_update_in_progress']={'filled':1}
    if fault=='root_account':parent['account']='OTHER'
    if fault=='root_client':parent['native_client_id']=998
    if fault=='root_epoch':parent['native_connection_epoch']=1
    if fault=='root_security':parent['security_id']=456
    if fault=='unowned':client._request_context_by_req_id[1007]['con_id']=999
    if fault=='retired':client._historical_states={}
    if fault=='late':args['monotonic_now']=11.
    if fault=='repeat':args['owned_reads']={1007}
    if fault=='conflict':client._request_id_conflicted=lambda request_id:True
    if fault=='not_sent':state['sent']=False
    if fault=='packet_security':fields[2]='999'
    if fault=='packet_timeframe':fields[16]='1 min'
    if fault=='packet_duration':fields[17]='1 D'
    if fault=='packet_end':fields[15]='20261020 14:00:00 UTC'
    if fault=='packet_rth':fields[18]='1'
    if fault=='packet_streaming':fields[21]='1'
    if fault=='packet_options':fields[22]='unprovided=true;'
    if fault=='missing_end':args['source_response']['end_received']=False
    if fault=='missing_bars':args['supplied_bars']=[]
    underlying=[]
    def fake_response():
        request_id=guard(**args)
        underlying.append((request_id,[vars(bar).copy() for bar in args['supplied_bars']]))
    if fault=='none':
        original=[vars(bar).copy() for bar in bars]
        fake_response()
        assert underlying==[(1007,original)] and bars[-1].timestamp<now
    else:
        with pytest.raises(Denied):fake_response()
        assert underlying==[]


def test_pristine_paper_trade_exit_shutdown_observer_forwards_owned_hook():
    """Pure observer check; the real child hook is recorded and forwarded."""
    report=dict(trade_exit_shutdown_calls=[])
    engine=NS();underlying=[];sentinel=object()
    def actual_shutdown(actual_engine,*args,**kwargs):
        underlying.append((actual_engine,args,kwargs))
        return sentinel
    observer=_pristine_paper_child_function('observed_trade_exit_shutdown',dict(report=report,
        active_cycle=[4],core=NS(trade_exit_engine=engine),actual_trade_exit_shutdown=actual_shutdown))
    assert observer(engine,current_tick=4) is sentinel
    assert report['trade_exit_shutdown_calls']==[dict(cycle=4,core_owned=True)]
    assert underlying==[(engine,(),dict(current_tick=4))]


@pytest.mark.parametrize('fault',['none','client','epoch','account','security','currency','leg',
    'duplicate_leg','root','native_parent','native_ref','native_side','native_price','side','quantity',
    'boolean_quantity','cumulative','price','status','future','straddles_entry','missing_accounting',
    'target','injected_native_id','entry','entry_wrong_parent','entry_wrong_side'])
def test_pristine_paper_execution_fact_boundary_rejects_unbound_stop(monkeypatch,fault):
    """Pure fixture guard: no application constructor, process, or SDK write."""
    import os
    monkeypatch.setenv('EXECUTION_ENV','TEST')
    class Denied(BaseException):pass
    guard=_pristine_paper_child_function('validate_pristine_paper_execution_fact',
        dict(os=os,datetime=datetime,ForbiddenExternalIO=Denied))
    now=datetime(2026,10,20,13,35,33,tzinfo=timezone.utc)
    plan=dict(account='SYNTHETIC_TEST',client_id=999,epoch=0,symbol='JPM',con_id=123,
        currency='USD',exchange='SMART',fill_price=10.53,stop_price=10.2897,stop_fill_price=10.28)
    client=NS(client_id=999,_position_connection_epoch=0,isConnected=lambda:True)
    trade=NS(entry_avg_price=10.53,stop_price=10.2897,target_price=None,
        opened_at='2026-10-20T13:35:31+00:00')
    engine=NS(run_mode=NS(value='PAPER'),_native_callback_client=lambda:client,
        _native_orders={'root':{}},_trade_lifecycle_engine=NS(get_trade=lambda _:trade))
    core=NS(run_mode=NS(value='PAPER'),execution_engine=engine)
    dispatches=[dict(role='entry',root_id='root',native_id=1000,
        order=dict(action='BUY',orderType='MKT',parentId=0)),
        dict(role='stop',root_id='root',native_id=1001,
        order=dict(action='SELL',orderType='STP',parentId=1000,auxPrice=10.2897,orderRef='PROTECT|root'))]
    raw=dict(leg='stop',contract=dict(symbol='JPM',conId=123,exchange='SMART',currency='USD',secType='STK'),
        execution=dict(execId='synthetic-stop',acctNumber='SYNTHETIC_TEST',clientId=999,side='SLD',
            shares=1,cumQty=1,price=10.28,avgPrice=10.28,time=now.isoformat()),
        status=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.28))
    if fault.startswith('entry'):
        raw['leg']='entry'
        raw['execution'].update(side='BOT',price=10.53,avgPrice=10.53)
        raw['status']['avgFillPrice']=10.53
    if fault=='entry_wrong_parent':dispatches[0]['order']['parentId']=1001
    if fault=='entry_wrong_side':raw['execution']['side']='SLD'
    actual=client
    if fault=='client':actual=object()
    if fault=='epoch':client._position_connection_epoch=1
    if fault=='account':raw['execution']['acctNumber']='OTHER'
    if fault=='security':raw['contract']['conId']=124
    if fault=='currency':raw['contract']['currency']='EUR'
    if fault=='leg':raw['leg']='failure'
    if fault=='duplicate_leg':dispatches.append(deepcopy(dispatches[-1]))
    if fault=='root':dispatches[-1]['root_id']='other-root'
    if fault=='native_parent':dispatches[-1]['order']['parentId']=0
    if fault=='native_ref':dispatches[-1]['order']['orderRef']='PROTECT|other'
    if fault=='native_side':dispatches[-1]['order']['action']='BUY'
    if fault=='native_price':dispatches[-1]['order']['auxPrice']=10.28
    if fault=='side':raw['execution']['side']='BOT'
    if fault=='quantity':raw['execution']['shares']=2
    if fault=='boolean_quantity':raw['execution']['shares']=True
    if fault=='cumulative':raw['execution']['cumQty']=2
    if fault=='price':raw['execution']['price']=10.27
    if fault=='status':raw['status']['remaining']=1
    if fault=='future':raw['execution']['time']='2026-10-20T13:35:34+00:00'
    if fault=='straddles_entry':raw['execution']['time']='2026-10-20T13:35:30+00:00'
    if fault=='missing_accounting':trade=None
    if fault=='target':trade.target_price=11.
    if fault=='injected_native_id':raw['execution']['orderId']=9999
    invoke=lambda:guard(actual_client=actual,expected_client=client,core=core,plan=plan,
        dispatches=dispatches,raw=raw,now=now)
    if fault in {'none','entry'}:assert invoke() is dispatches[0 if fault=='entry' else -1]
    else:
        with pytest.raises(Denied):invoke()


@pytest.mark.parametrize('fault',['none','other_symbol','other_conid','extra_result','missing',
    'nan','boolean','negative','crossed','outside_spread','future','stale','naive','age_boundary'])
def test_pristine_paper_market_fact_boundary_accepts_only_raw_current_quotes(fault):
    """Pure raw-fact validation; source quote/decision owners are never replaced."""
    class Denied(BaseException):pass
    guard=_pristine_paper_child_function('validate_pristine_paper_market_fact',
        dict(datetime=datetime,ForbiddenExternalIO=Denied))
    now=datetime(2026,10,20,13,35,33,tzinfo=timezone.utc)
    plan=dict(symbol='JPM',con_id=123)
    quote=dict(symbol='JPM',con_id=123,bid=10.27,ask=10.29,last_price=10.28,
        quote_timestamp_utc=now.isoformat())
    if fault=='other_symbol':quote['symbol']='OTHER'
    if fault=='other_conid':quote['con_id']=124
    if fault=='extra_result':quote['risk_decision']={'allowed':True}
    if fault=='missing':quote.pop('bid')
    if fault=='nan':quote['bid']=float('nan')
    if fault=='boolean':quote['bid']=True
    if fault=='negative':quote['bid']=-1
    if fault=='crossed':quote.update(bid=10.29,ask=10.27)
    if fault=='outside_spread':quote['last_price']=10.3
    if fault=='future':quote['quote_timestamp_utc']='2026-10-20T13:35:34+00:00'
    if fault=='stale':quote['quote_timestamp_utc']='2026-10-20T13:35:17+00:00'
    if fault=='naive':quote['quote_timestamp_utc']='2026-10-20T13:35:33'
    if fault=='age_boundary':quote['quote_timestamp_utc']='2026-10-20T13:35:18+00:00'
    invoke=lambda:guard(plan=plan,quote=quote,now=now,max_age=15.)
    if fault in {'none','age_boundary'}:
        assert invoke()=={key:value for key,value in quote.items() if key not in {'symbol','con_id'}}
    else:
        with pytest.raises(Denied):invoke()


@pytest.mark.parametrize('authority',['capital','allocation'])
@pytest.mark.parametrize('failure',[False,True])
def test_pristine_paper_exposure_observer_forwards_real_method_once(authority,failure):
    """Pure observer control: preserve arguments, return identity and exception."""
    report=dict(exposure_release_calls=[]);owner=NS(total_used_exposure=10.53)
    owner.strategy_used_exposure=lambda strategy:owner.total_used_exposure
    calls=[];sentinel=object();error=RuntimeError('Synthetic actual release failure')
    def actual_release(*args,**kwargs):
        calls.append((args,kwargs))
        if failure:raise error
        owner.total_used_exposure=0.
        return sentinel
    observer=_pristine_paper_child_function('observed_pristine_paper_exposure_release',
        dict(report=report,active_cycle=[4],plain=lambda value:value,
            exception_record=lambda exc:dict(type=type(exc).__name__,message=str(exc))))
    kwargs=dict(strategy_id='RossMomentumStrategyV1',quantity=1,price=10.53,reason='EXIT_FILL')
    invoke=lambda:observer(actual_release,owner,authority,**kwargs)
    if failure:
        with pytest.raises(RuntimeError) as caught:invoke()
        assert caught.value is error
    else:assert invoke() is sentinel
    assert calls==[((),kwargs)] and len(report['exposure_release_calls'])==1
    row=report['exposure_release_calls'][0]
    assert row['authority']==authority and row['cycle']==4 and row['kwargs']==kwargs
    assert row['exposure_before']==10.53 and row['exposure_after']==(10.53 if failure else 0.)
    if failure:assert row['exception']['message']==str(error) and 'result' not in row
    else:assert row['result'] is sentinel and 'exception' not in row


def test_pristine_fresh_process_pmh_paper_ack_then_later_accounted_protected_fill(
        reassessment,monkeypatch,tmp_path,capsys,no_external_activity,runtime_schema_template):
    """Synthetic PAPER owns new state in one fresh process; no recovery grant."""
    import json,shutil
    from datetime import timedelta
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    facts=_pristine_native_cycle_facts(reassessment,monkeypatch,tmp_path)
    facts.pop('observe_pristine_readonly_cycle')
    facts['observe_pristine_paper_cycle']=True
    facts['config'].update(RUN_MODE='PAPER',RUN_MODE_EFFECTIVE='PAPER',EXECUTION_ENABLED=True,
        RISK_PROFILE='SMALL',IBKR_READONLY_ENABLED=False,IBKR_ORDER_SUBMISSION_ENABLED=True,
        IBKR_ORDER_TRANSLATION_ENABLED=True,IBKR_API_WRITE_ALLOWED=True,IBKR_KILL_SWITCH=False)
    facts['paper_memory_plan']=dict(account='SYNTHETIC_TEST',client_id=999,epoch=0,symbol='JPM',
        con_id=123,currency='USD',exchange='SMART',entry_price=10.3,stop_price=10.2897,fill_price=10.53)
    stamp=datetime.fromisoformat(facts['now'])
    contract=dict(symbol='JPM',conId=123,exchange='SMART',currency='USD',secType='STK')
    position=dict(symbol='JPM',position=1,con_id=123,avgCost=10.53,account='SYNTHETIC_TEST')
    stop=dict(leg='stop',contract=contract,
        order=dict(orderType='STP',parentId='$ENTRY_NATIVE_ID',orderRef='PROTECT|$RETAINED_ROOT',
            action='SELL',totalQuantity=1,auxPrice=10.2897,account='SYNTHETIC_TEST',clientId=999),
        orderState=dict(status='Submitted'))
    execution=dict(leg='entry',contract=contract,
        execution=dict(execId='pristine-paper-entry',acctNumber='SYNTHETIC_TEST',clientId=999,
            side='BOT',shares=1,cumQty=1,price=10.53,avgPrice=10.53,
            time=(stamp+timedelta(seconds=1)).isoformat()),
        status=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.53))
    facts['paper_cycle_steps']=[
        dict(name='ACK_ONLY',now=stamp.isoformat(),positions=[],open_orders=[]),
        dict(name='LATER_ENTRY_FILL',now=(stamp+timedelta(seconds=1)).isoformat(),
            positions=[position],open_orders=[],executions=[execution]),
        dict(name='PROTECTED_REPEAT_ONE',now=(stamp+timedelta(seconds=2)).isoformat(),
            positions=[position],open_orders=[stop]),
        dict(name='PROTECTED_REPEAT_TWO',now=(stamp+timedelta(seconds=3)).isoformat(),
            positions=[position],open_orders=[stop]),
    ]
    database=tmp_path/'pristine-paper-first-fill.sqlite3'
    shutil.copyfile(runtime_schema_template,database)
    path=tmp_path/'pristine-paper-facts.json';path.write_text(json.dumps(facts,default=str))
    report=run_native_core_cold_start(database,path,tmp_path/'pristine-paper-child')
    summary={key:report.get(key) for key in ('constructor_exception','harness_exception',
        'cycle_exception','stage','supervisor','evidence_dir')}
    assert report.get('constructor_complete') and report['constructor_count']==1,summary
    assert not report.get('harness_exception') and not report.get('cycle_exception'),summary
    assert len(report['cycles'])==4 and all(row['result'] is True and not row.get('exception')
        for row in report['cycles']),summary
    assert report['native_before'] is report['native_after_constructor'] is None
    assert report['after_constructor']['startup_recovery_state']=='RECOVERY_COMPLETE'
    assert report['offline_guard']['native_curl_checked']
    assert not report['network_attempts'] and not report.get('native_curl_denials'),summary
    assert not report['sdk_attempts'] and not any(row['mutation'] for row in report['wire_attempts']),summary
    assert not report.get('capital_enrollment_attempts'),summary
    assert report['registry_evaluations'] and all(row['result_count']==33 for row in report['registry_evaluations'])
    dispatches=report['synthetic_memory_dispatches']
    assert [row['role'] for row in dispatches]==['entry','stop'],summary
    root=dispatches[0]['root_id']
    assert dispatches[1]['root_id']==root and dispatches[0]['cycle']==1 and dispatches[1]['cycle']==2
    ack=report['cycles'][0]['engine'];retained=ack['native_orders'][root];request=retained['request']
    assert retained['filled']==0 and not retained['terminal'] and retained['broker_order_id']==str(dispatches[0]['native_id'])
    assert ack['capital_reserved']==10.3 and ack['capital_used']==0
    assert len(ack['capital_reservations'])==len(ack['allocation_reservations'])==1
    capital=next(iter(ack['capital_reservations'].values()))
    allocation=next(iter(ack['allocation_reservations'].values()))
    assert isinstance(capital['decision_id'],str) and capital['decision_id']
    assert isinstance(allocation['decision_id'],str) and allocation['decision_id']
    assert allocation['global_capital_decision_id']==capital['decision_id']
    for reservation in (capital,allocation):
        assert reservation['order_id']==root and reservation['symbol']==request['symbol']
        assert reservation['side']==request['direction'].upper()
        assert reservation['strategy_id'].upper()==request['strategy_name'].upper()
        assert reservation['run_mode']=='PAPER' and reservation['status']=='ACTIVE'
        assert type(reservation['quantity']) is int and reservation['quantity']==1
        assert type(reservation['remaining_quantity']) is int and reservation['remaining_quantity']==1
        assert reservation['filled_quantity']==0 and reservation['exposure_notional']==0
        assert reservation['notional']==reservation['remaining_notional']==10.3
    assert not ack['position_records'] and not ack['registry'] and not ack['managed_positions']
    assert not ack['post_fill'] and not ack['protection'] and ack['canonical_trades'][root] is None
    assert request['setup_family_id']=='PREMARKET_HIGH_BREAK' and request['quantity']==1
    assert request['stop_loss_price']==10.2897 and request['invalidation_level']==10.3
    assert request['take_profit_price'] is None and request['target_model'] and request['setup_metadata']
    artifacts=[row for row in report['decision_artifacts'] if row['decision_id']==retained['decision_id']]
    assessments=[row for row in report['risk_evaluations']
        if row['decision']['decision_id']==retained['decision_id']]
    assert len(artifacts)==len(assessments)==1
    artifact=artifacts[0];assessment=assessments[0];intent=assessment['intent']
    assert len(artifact['intents'])==1
    selected=artifact['intents'][0]
    assert assessment['decision']['allowed'] is True
    assert assessment['decision']['decision_id']==intent['decision_id']==artifact['decision_id']==retained['decision_id']
    assert artifact['session_phase']=='OPENING_0_30'
    assert assessment['decision']['evaluated_limits']['session']=='RTH'
    assert assessment['decision']['evaluated_limits']['prep_only'] is False
    assert artifact['created_at']==intent['timestamp_utc']==assessment['decision']['timestamp']==facts['now']
    assert request['client_order_id']==root
    for field in ('symbol','setup_family_id','trigger_id','target_model','stop_loss_price',
            'invalidation_level','take_profit_price','setup_metadata'):
        assert selected[field]==intent[field]==request[field],field
    assert selected['entry_price']==intent['entry_price']==facts['paper_memory_plan']['entry_price']
    assert len(report['execution_results'])==1
    result=report['execution_results'][0]
    assert result['filled_quantity']==0 and result['remaining_quantity']==1
    assert result['client_order_id']==root and str(result['ibkr_order_id'])==str(dispatches[0]['native_id'])
    for cycle in report['cycles'][1:]:
        state=cycle['engine'];parent=state['native_orders'][root];life=state['post_fill'][root]
        canonical=state['canonical_trades'][root]
        assert state['startup_recovery_state']=='RECOVERY_COMPLETE' and not state['native_quarantined']
        assert parent['decision_id']==retained['decision_id']
        assert parent['request']==request and parent['filled']==1 and parent['terminal']
        assert parent['protection_confirmed'] and not parent.get('cached_update_in_progress')
        assert not parent.get('pmh_failure_exit')
        assert len(parent['canonical_feedback'])==1
        assert parent['canonical_feedback'][0]['state']=='COMPLETE' and parent['canonical_feedback'][0]['accounting_complete']
        binding=parent['canonical_feedback'][0]['identity']
        assert binding['root_order_id']==root and binding['native_order_id']==str(dispatches[0]['native_id'])
        assert binding['account']=='SYNTHETIC_TEST' and binding['client_id']==999 and binding['connection_epoch']==0
        assert binding['symbol']=='JPM' and binding['con_id']==123
        assert canonical['lifecycle_trade_id']==life['trade_id']==root
        assert canonical['quantity_open']==1 and canonical['quantity_closed']==0
        assert canonical['entry_avg_price']==10.53 and canonical['stop_price']==10.2897 and canonical['target_price'] is None
        assert canonical['source_execution_ids']==['pristine-paper-entry']
        assert life['filled_qty']==1 and life['avg_fill_price']==10.53 and life['selected_stop_price']==10.2897
        assert life['target_model']==request['target_model'] and life['selected_target_price'] is None
        protective=life['stop']
        assert protective['broker_order_id']==str(dispatches[1]['native_id'])
        assert protective['entry_order_id']==str(dispatches[0]['native_id'])
        assert protective['lifecycle_trade_id']==protective['entry_intent_id']==root
        assert protective['order_type']=='STOP' and protective['side']=='SELL'
        assert protective['quantity']==life['filled_qty']==1 and protective['trigger_price']==request['stop_loss_price']
        assert protective['status'].upper() in {'SUBMITTED','PRESUBMITTED'}
        assert state['protection'][root]['protected']
        assert len(state['position_records'])==len(state['registry'])==len(state['managed_positions'])==1
        assert state['capital_scope'] is None and not state['capital_writer_present']
        assert state['capital_reserved']==0 and state['capital_used']==10.53
        assert not state['capital_reservations'] and not state['allocation_reservations']
    history=[row for row in report['native_read_requests'] if row['request_type']=='HISTORICAL_DATA']
    evaluations=report['selected_failure_evaluations']
    assert len(history)==len(evaluations)==3 and not report['native_history_pending_ids']
    original_bars=facts['source_timeframe_bars']['10s']
    original_dates=[row['timestamp'].isoformat() for row in original_bars]
    for read in history:
        assert read['timeframe']=='10s' and read['source_count']==len(original_bars)
        assert read['source_dates']==original_dates
    accounted_at=datetime.fromisoformat(report['cycles'][1]['engine']['native_orders'][root]['last_accounted_entry_fill_at'])
    assert accounted_at==datetime.fromisoformat(execution['execution']['time'])
    for evaluated in evaluations:
        assert evaluated['root_id']==root and evaluated['result'] is None
        assert [bar['date'] for bar in evaluated['bars']]==original_dates[-10:]
        assert all(datetime.fromisoformat(bar['date'])<accounted_at for bar in evaluated['bars'])
        for actual,original in zip(evaluated['bars'],original_bars[-10:]):
            assert all(actual[field]==original[field] for field in ('open','high','low','close','volume'))
    assert report['cleanup']['news_maintenance_closed'] and report['cleanup']['execution_resource_close_complete']
    assert report['trade_exit_shutdown_calls']==[]
    assert report['cleanup']['scanner_runtime_close_complete']
    assert report['cleanup']['paper_before_resource_close']==report['cleanup']['paper_after_resource_close']
    assert (report['database_after_cycle']['position_lifecycle_transitions']
        == report['database_final']['position_lifecycle_transitions'])
    assert report['cleanup']['live_threads']==[] and not report['cleanup'].get('paper_resource_close_exception')
    assert report['supervisor']['returncode']==0 and report['supervisor']['reaped'] and not report['supervisor']['timed_out']
    assert no_external_activity==[]


def _pristine_paper_loss_facts(reassessment,monkeypatch,tmp_path,*,loss_limit=.20):
    """Shared external five-step tape; every application owner remains real."""
    facts=_pristine_native_cycle_facts(reassessment,monkeypatch,tmp_path)
    facts.pop('observe_pristine_readonly_cycle')
    facts['observe_pristine_paper_cycle']=True
    facts['observe_pristine_paper_loss_feedback']=True
    facts['config'].update(RUN_MODE='PAPER',RUN_MODE_EFFECTIVE='PAPER',EXECUTION_ENABLED=True,
        RISK_PROFILE='SMALL',IBKR_READONLY_ENABLED=False,IBKR_ORDER_SUBMISSION_ENABLED=True,
        IBKR_ORDER_TRANSLATION_ENABLED=True,IBKR_API_WRITE_ALLOWED=True,IBKR_KILL_SWITCH=False,
        DAILY_RISK_GOVERNOR_ENABLED=True,DAILY_RISK_INCLUDE_UNREALIZED=False,
        DAILY_RISK_MAX_LOSS_AMOUNT=loss_limit)
    facts['paper_memory_plan']=dict(account='SYNTHETIC_TEST',client_id=999,epoch=0,symbol='JPM',
        con_id=123,currency='USD',exchange='SMART',entry_price=10.3,stop_price=10.2897,
        fill_price=10.53,stop_fill_price=10.28)
    stamp=datetime.fromisoformat(facts['now'])
    contract=dict(symbol='JPM',conId=123,exchange='SMART',currency='USD',secType='STK')
    position=dict(symbol='JPM',position=1,con_id=123,avgCost=10.53,account='SYNTHETIC_TEST')
    stop=dict(leg='stop',contract=contract,
        order=dict(orderType='STP',parentId='$ENTRY_NATIVE_ID',orderRef='PROTECT|$RETAINED_ROOT',
            action='SELL',totalQuantity=1,auxPrice=10.2897,account='SYNTHETIC_TEST',clientId=999),
        orderState=dict(status='Submitted'))
    def supplied_execution(leg,identifier,side,price,second):
        return dict(leg=leg,contract=contract,
            execution=dict(execId=identifier,acctNumber='SYNTHETIC_TEST',clientId=999,side=side,
                shares=1,cumQty=1,price=price,avgPrice=price,
                time=(stamp+timedelta(seconds=second)).isoformat()),
            status=dict(status='Filled',filled=1,remaining=0,avgFillPrice=price))
    entry=supplied_execution('entry','pristine-loss-entry','BOT',10.53,1)
    protective=supplied_execution('stop','pristine-loss-stop','SLD',10.28,3)
    def step(name,second,*,owned,open_orders,executions=(),last=10.53):
        now=(stamp+timedelta(seconds=second)).isoformat()
        return dict(name=name,now=now,positions=[position] if owned else [],open_orders=open_orders,
            executions=list(executions),market_quote=dict(symbol='JPM',con_id=123,
                bid=round(last-.01,2),ask=round(last+.01,2),last_price=last,quote_timestamp_utc=now))
    facts['paper_cycle_steps']=[
        step('ACK_ONLY',0,owned=False,open_orders=[]),
        step('LATER_ENTRY_FILL',1,owned=True,open_orders=[],executions=[entry]),
        step('PROTECTED_REPEAT',2,owned=True,open_orders=[stop]),
        step('LATER_PROTECTIVE_FILL',3,owned=False,open_orders=[],executions=[protective],last=10.28),
        # Exact authoritative execution identity/time is replayed; observation
        # time advances without renewing the economic fill timestamp.
        step('FLAT_DUPLICATE_REPLAY',4,owned=False,open_orders=[],executions=[protective],last=10.28),
    ]
    return facts


def test_pristine_fresh_process_pmh_protective_fill_reaches_canonical_daily_loss_veto(
        reassessment,monkeypatch,tmp_path,capsys,no_external_activity,runtime_schema_template):
    """One genuine startup, native STOP fill, canonical GROSS loss, then replay."""
    import json,shutil
    from datetime import timedelta
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    facts=_pristine_paper_loss_facts(reassessment,monkeypatch,tmp_path)
    protective=facts['paper_cycle_steps'][3]['executions'][0]
    database=tmp_path/'pristine-protective-loss.sqlite3'
    shutil.copyfile(runtime_schema_template,database)
    path=tmp_path/'pristine-protective-loss-facts.json';path.write_text(json.dumps(facts,default=str))
    report=run_native_core_cold_start(database,path,tmp_path/'pristine-protective-loss-child')
    summary={key:report.get(key) for key in ('constructor_exception','harness_exception',
        'cycle_exception','stage','supervisor','evidence_dir')}
    assert report.get('constructor_complete') and report['constructor_count']==1,summary
    assert not report.get('harness_exception') and not report.get('cycle_exception'),summary
    assert len(report['cycles'])==5 and all(row['result'] is True and not row.get('exception')
        for row in report['cycles']),summary
    assert report['native_before'] is report['native_after_constructor'] is None
    assert report['after_constructor']['startup_recovery_state']=='RECOVERY_COMPLETE'
    assert report['offline_guard']['native_curl_checked']
    assert not report['network_attempts'] and not report.get('native_curl_denials'),summary
    assert not report['sdk_attempts'] and not any(row['mutation'] for row in report['wire_attempts']),summary
    assert not report.get('capital_enrollment_attempts'),summary
    assert report['registry_evaluations'] and all(row['result_count']==33 for row in report['registry_evaluations'])
    dispatches=report['synthetic_memory_dispatches']
    assert [row['role'] for row in dispatches]==['entry','stop'],summary
    buy,selected_stop=dispatches;root=buy['root_id']
    assert buy['cycle']==1 and selected_stop['cycle']==2 and selected_stop['root_id']==root
    assert selected_stop['order']['parentId']==buy['native_id']
    assert selected_stop['order']['auxPrice']==10.2897
    ack,filled,protected,closed,replayed=report['cycles']
    request=ack['engine']['native_orders'][root]['request']
    assert request['quantity']==1 and request['setup_family_id']=='PREMARKET_HIGH_BREAK'
    assert request['invalidation_level']==10.3 and request['stop_loss_price']==10.2897
    assert request['take_profit_price'] is None and request['target_model'] and request['setup_metadata']
    assert ack['engine']['capital_reserved']==10.3 and ack['engine']['capital_used']==0
    assert not ack['engine']['position_records'] and not ack['engine']['post_fill']
    assert len(report['execution_results'])==1
    admitted=[row for row in report['risk_evaluations'] if row['decision']['allowed']]
    assert len(admitted)==1 and admitted[0]['decision']['max_position_size']==1
    assert all(row['decision']['reason_code'] in {'ROSS_BLOCK_COOLDOWN_ACTIVE','ROSS_BLOCK_MAX_ATTEMPTS'}
        for row in report['risk_evaluations'] if not row['decision']['allowed'])
    for cycle in (ack,filled,protected):
        decision=cycle['daily_risk']['decision']
        assert decision is not None and decision['status']=='ALLOW',cycle['daily_risk']
        assert decision['realized_pnl']==0 and decision['daily_trade_count']==0
        assert cycle['daily_risk']['state']['recovered']
    for cycle in (filled,protected):
        state=cycle['engine'];canonical=state['canonical_trades'][root]
        assert canonical['quantity_open']==1 and canonical['entry_avg_price']==10.53
        assert canonical['stop_price']==10.2897 and canonical['target_price'] is None
        assert state['protection'][root]['protected'] and state['capital_used']==10.53
        assert state['capital_reserved']==0 and state['post_fill'][root]['filled_qty']==1
    for cycle in (closed,replayed):
        state=cycle['engine'];canonical=state['canonical_trades'][root]
        assert state['startup_recovery_state']=='RECOVERY_COMPLETE' and not state['native_quarantined']
        assert state['native_orders'][root]['request']==request
        assert canonical['status']=='CLOSED' and canonical['quantity_open']==0 and canonical['quantity_closed']==1
        assert canonical['entry_avg_price']==10.53 and canonical['exit_avg_price']==10.28
        assert canonical['gross_realized_pnl']==pytest.approx(-.25)
        assert canonical['stop_price']==10.2897 and canonical['target_price'] is None
        assert canonical['closed_at']==protective['execution']['time']
        assert set(canonical['source_execution_ids'])=={'pristine-loss-entry','pristine-loss-stop'}
        assert state['post_fill'][root]['filled_qty']==0
        # position_records retains accounted cumulative progress, not current
        # ownership. Flatness comes from canonical/PostFill/registry owners;
        # these original progress records must survive to prevent replay.
        close_id=next(key for key,row in state['native_orders'].items()
            if row.get('protection_parent_order_id')==root)
        assert set(state['position_records'])=={root,close_id}
        assert all(row['filled_qty']==1 for row in state['position_records'].values())
        assert not state['registry'] and not state['managed_positions']
        assert state['capital_used']==state['capital_reserved']==0
        assert not state['capital_reservations'] and not state['allocation_reservations']
        assert state['capital_scope'] is None and not state['capital_writer_present']
        decision=cycle['daily_risk']['decision'];daily=cycle['daily_risk']['state']
        assert daily['recovered'] and daily['recovery_error'] is None,cycle['daily_risk']
        assert decision['status']=='MANAGED_ONLY' and decision['lock_status']=='LOCKED',cycle['daily_risk']
        assert decision['reason']=='MAX_DAILY_LOSS_AMOUNT' and decision['blocks_new_entries']
        assert decision['audit_payload']['source']=='CoreOrchestrator'
        assert decision['audit_payload']['stage']=='PRE_STRATEGY'
        assert decision['realized_pnl']==pytest.approx(-.25) and decision['unrealized_pnl']==0
        assert (decision['daily_trade_count'],decision['losing_trade_count'],decision['consecutive_losses'])==(1,1,1)
        rows=cycle['database']['trade_lifecycle_events']
        assert len(rows)==2 and {row['execution_id'] for row in rows}=={'pristine-loss-entry','pristine-loss-stop'}
        assert not any(event['event_type']=='TRADE_CLOSED' for event in cycle['events'])
    callbacks=report['paper_execution_callbacks']
    assert [row['leg'] for row in callbacks]==['entry','stop','stop']
    assert callbacks[0]['parent_id']==0
    assert all(row['native_id']==selected_stop['native_id'] and row['parent_id']==buy['native_id']
        and row['root_id']==root for row in callbacks[1:])
    assert callbacks[1]['execution']==callbacks[2]['execution']
    assert closed['database']['trade_lifecycle_events']==replayed['database']['trade_lifecycle_events']
    assert closed['engine']['position_records']==replayed['engine']['position_records']
    assert all(not row['positions'] and not row['open_orders'] for row in report['paper_external_steps'][-2:])
    releases=report['exposure_release_calls']
    assert len(releases)==2 and {row['authority'] for row in releases}=={'capital','allocation'}
    assert [cycle['exposure_release_calls_after'] for cycle in report['cycles']]==[0,0,0,2,2]
    for released in releases:
        assert released['cycle']==4 and not released['args'] and 'exception' not in released
        assert released['kwargs']['quantity']==1 and released['kwargs']['price']==10.53
        assert released['kwargs']['reason']=='EXIT_FILL'
        assert released['kwargs']['strategy_id']==request['strategy_name']
        assert released['exposure_before']==released['result']==10.53 and released['exposure_after']==0
    assert not any(row['opcode'] in {'62','63'} for row in report['wire_attempts'])
    assert report['trade_exit_shutdown_calls']==[] and report['cleanup']['live_threads']==[]
    assert report['cleanup']['paper_before_resource_close']==report['cleanup']['paper_after_resource_close']
    assert report['cleanup']['news_maintenance_closed'] and report['cleanup']['execution_resource_close_complete']
    assert report['cleanup']['scanner_runtime_close_complete']
    assert report['supervisor']['returncode']==0 and report['supervisor']['reaped'] and not report['supervisor']['timed_out']
    assert no_external_activity==[]


def test_pristine_fresh_process_pmh_positive_fees_reach_actual_core_net_veto(
        reassessment,monkeypatch,tmp_path,capsys,no_external_activity,runtime_schema_template):
    """Separate positive-fee proof; shares the actual five-cycle GROSS tape."""
    import json,shutil
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    facts=_pristine_paper_loss_facts(reassessment,monkeypatch,tmp_path,loss_limit=.26)
    facts['observe_pristine_paper_positive_fee_feedback']=True
    facts['paper_currency_response']=dict(account='SYNTHETIC_TEST',end_received=True,rows=[
        dict(tag='CashBalance',value='123.45',currency='USD'),
        dict(tag='AccruedCash',value='0',currency='USD')])
    steps=facts['paper_cycle_steps']
    steps[1]['commissions']=[dict(leg='entry',execId='pristine-loss-entry',commission=.01,currency='USD')]
    steps[3]['commissions']=[dict(leg='stop',execId='pristine-loss-stop',commission=.02,currency='USD')]
    database=tmp_path/'pristine-positive-fee-net.sqlite3'
    shutil.copyfile(runtime_schema_template,database)
    path=tmp_path/'pristine-positive-fee-net-facts.json';path.write_text(json.dumps(facts,default=str))
    report=run_native_core_cold_start(database,path,tmp_path/'pristine-positive-fee-net-child')
    summary={key:report.get(key) for key in ('constructor_exception','harness_exception',
        'cycle_exception','stage','supervisor','evidence_dir')}
    assert report.get('constructor_complete') and report['constructor_count']==1,summary
    assert not report.get('harness_exception') and not report.get('cycle_exception'),summary
    assert len(report['cycles'])==5 and all(row['result'] is True and not row.get('exception')
        for row in report['cycles']),summary
    assert report['native_before'] is report['native_after_constructor'] is None
    assert report['after_constructor']['startup_recovery_state']=='RECOVERY_COMPLETE'
    assert report['offline_guard']['native_curl_checked']
    assert not report['network_attempts'] and not report.get('native_curl_denials'),summary
    assert not report['sdk_attempts'] and not any(row['mutation'] for row in report['wire_attempts']),summary
    assert not report.get('capital_enrollment_attempts'),summary
    assert report['registry_evaluations'] and all(row['result_count']==33 for row in report['registry_evaluations'])
    dispatches=report['synthetic_memory_dispatches']
    assert [row['role'] for row in dispatches]==['entry','stop'],summary
    buy,selected_stop=dispatches;root=buy['root_id']
    assert buy['cycle']==1 and selected_stop['cycle']==2 and selected_stop['root_id']==root
    assert selected_stop['order']['parentId']==buy['native_id']
    ack,filled,protected,closed,replayed=report['cycles']
    retained=ack['engine']['native_orders'][root];request=retained['request']
    assert request['setup_family_id']=='PREMARKET_HIGH_BREAK' and request['quantity']==1
    assert request['invalidation_level']==10.3 and request['stop_loss_price']==10.2897
    assert request['take_profit_price'] is None and request['setup_metadata'] and request['target_model']
    artifacts=[row for row in report['decision_artifacts'] if row['decision_id']==retained['decision_id']]
    admitted=[row for row in report['risk_evaluations'] if row['decision']['allowed']]
    assert len(artifacts)==len(admitted)==len(report['execution_results'])==1
    intent=admitted[0]['intent'];artifact=artifacts[0]
    assert admitted[0]['decision']['decision_id']==artifact['decision_id']==retained['decision_id']==intent['decision_id']
    assert admitted[0]['decision']['max_position_size']==1 and artifact['session_phase']=='OPENING_0_30'
    assert artifact['intents'][0]['setup_metadata']==intent['setup_metadata']==request['setup_metadata']
    assert ack['engine']['capital_reserved']==10.3 and ack['engine']['capital_used']==0
    assert not ack['engine']['position_records'] and not ack['engine']['post_fill']
    for cycle in (ack,filled,protected):
        assert cycle['daily_risk']['state']['recovered'] and cycle['daily_risk']['decision']['status']=='ALLOW'
        assert cycle['daily_risk']['decision']['realized_pnl']==0
        assert not cycle['fee_feedback']['required'] and not cycle['fee_feedback']['covered_charges']
    for cycle in (filled,protected):
        canonical=cycle['engine']['canonical_trades'][root]
        assert canonical['quantity_open']==1 and canonical['entry_avg_price']==10.53
        assert canonical['stop_price']==10.2897 and canonical['target_price'] is None
        assert cycle['engine']['protection'][root]['protected']
        assert cycle['engine']['capital_used']==10.53 and cycle['engine']['capital_reserved']==0
    for cycle in (closed,replayed):
        state=cycle['engine'];canonical=state['canonical_trades'][root]
        assert state['startup_recovery_state']=='RECOVERY_COMPLETE' and not state['native_quarantined']
        assert state['native_orders'][root]['request']==request
        assert canonical['status']=='CLOSED' and canonical['quantity_open']==0 and canonical['quantity_closed']==1
        assert canonical['entry_avg_price']==10.53 and canonical['exit_avg_price']==10.28
        assert canonical['gross_realized_pnl']==pytest.approx(-.25)
        assert canonical['stop_price']==10.2897 and canonical['target_price'] is None
        assert canonical['closed_at']==steps[3]['executions'][0]['execution']['time']
        assert set(canonical['source_execution_ids'])=={'pristine-loss-entry','pristine-loss-stop'}
        assert state['post_fill'][root]['filled_qty']==0 and not state['registry'] and not state['managed_positions']
        assert state['capital_used']==state['capital_reserved']==0
        assert not state['capital_reservations'] and not state['allocation_reservations']
        assert state['capital_scope'] is None and not state['capital_writer_present']
        feedback=cycle['fee_feedback']
        assert feedback['required'] and feedback['available'] and not feedback['uncertain']
        assert feedback['states'][root]['state']=='COMPLETE'
        assert len(feedback['evidence'])==1 and feedback['evidence'][0]['matched_current_basis'] is True
        evidence=feedback['evidence'][0]
        assert evidence['root_order_id']==root and evidence['account']=='SYNTHETIC_TEST' and evidence['currency']=='USD'
        assert evidence['gross_realized_pnl']==pytest.approx(-.25) and evidence['total_commission']==pytest.approx(.03)
        assert set(evidence['execution_ids'])=={'pristine-loss-entry','pristine-loss-stop'}
        charges=feedback['covered_charges']
        assert len(charges)==2 and {row['execution_id'] for row in charges}==set(evidence['execution_ids'])
        assert sorted(float(row['amount']) for row in charges)==[.01,.02]
        assert all(row['currency']=='USD' and row['root_order_id']==root and 'zero_commission_witness' not in row
            for row in charges)
        source=cycle['fee_source_observations']
        assert len(source)==2 and all(row['report_status']=='BOUND_API_REPORT'
            and row['net_status']=='UNAVAILABLE_FOR_NET' and row['execution_currency']==row['report_currency']=='USD'
            for row in source)
        decision=cycle['daily_risk']['decision'];daily=cycle['daily_risk']['state']
        assert daily['recovered'] and daily['recovery_error'] is None,cycle['daily_risk']
        assert decision['status']=='MANAGED_ONLY' and decision['lock_status']=='LOCKED',cycle['daily_risk']
        assert decision['reason']=='MAX_DAILY_LOSS_AMOUNT' and decision['blocks_new_entries']
        assert decision['audit_payload']['source']=='CoreOrchestrator' and decision['audit_payload']['stage']=='PRE_STRATEGY'
        assert decision['realized_pnl']==pytest.approx(-.28) and decision['unrealized_pnl']==0
        assert (decision['daily_trade_count'],decision['losing_trade_count'],decision['consecutive_losses'])==(1,1,1)
        rows=cycle['database']['trade_lifecycle_events']
        financial=[row for row in rows if row['execution_id'] is not None]
        auxiliary=[row for row in rows if row['event_type']=='NATIVE_ROUNDTRIP_FEE']
        assert len(rows)==3 and len(financial)==2 and len(auxiliary)==1
        assert {row['execution_id'] for row in financial}==set(evidence['execution_ids'])
        audit=json.loads(auxiliary[0]['payload_json'])['native_roundtrip_fee']
        assert audit['account']=='SYNTHETIC_TEST' and audit['currency']=='USD'
        assert audit['total_commission']==pytest.approx(.03) and set(audit['basis_event_ids'])=={row['event_id'] for row in financial}
        assert audit['account_currency_observation']['source']=='IBKR_ACCOUNT_SUMMARY_LEDGER'
        assert audit['account_currency_observation']['client_id']==999 and audit['account_currency_observation']['connection_epoch']==0
        assert not any(event['event_type']=='TRADE_CLOSED' for event in cycle['events'])
    queries=[row for row in report['native_read_requests'] if row['request_type']=='ACCOUNT_CURRENCY_STRICT']
    cancels=[row for row in report['native_read_requests'] if row['request_type']=='OWNED_ACCOUNT_CURRENCY_CANCEL']
    assert len(queries)==len(cancels)==1 and queries[0]['request_id']==cancels[0]['request_id']
    assert queries[0]['status']=='COMPLETE' and queries[0]['end_observed'] and queries[0]['currency']=='USD'
    assert cancels[0]['active_type_absent'] and cancels[0]['query_retired']
    assert queries[0]['completed_at']==steps[3]['now']
    assert [row['opcode'] for row in report['wire_attempts'] if row['opcode'] in {'62','63'}]==['62','63']
    assert [(row['leg'],row['exec_id'],row['amount']) for row in report['positive_fee_callbacks']]==[
        ('entry','pristine-loss-entry',.01),('stop','pristine-loss-stop',.02)]
    assert closed['database']['trade_lifecycle_events']==replayed['database']['trade_lifecycle_events']
    assert closed['fee_feedback']==replayed['fee_feedback']
    assert closed['engine']['position_records']==replayed['engine']['position_records']
    releases=report['exposure_release_calls']
    assert len(releases)==2 and {row['authority'] for row in releases}=={'capital','allocation'}
    assert [cycle['exposure_release_calls_after'] for cycle in report['cycles']]==[0,0,0,2,2]
    assert all(row['cycle']==4 and row['result']==10.53 and row['exposure_after']==0 and 'exception' not in row for row in releases)
    assert report['trade_exit_shutdown_calls']==[] and report['cleanup']['live_threads']==[]
    assert report['cleanup']['paper_before_resource_close']==report['cleanup']['paper_after_resource_close']
    assert report['cleanup']['news_maintenance_closed'] and report['cleanup']['execution_resource_close_complete']
    assert report['cleanup']['scanner_runtime_close_complete']
    assert report['supervisor']['returncode']==0 and report['supervisor']['reaped'] and not report['supervisor']['timed_out']
    assert no_external_activity==[]


@pytest.mark.parametrize('fault',[
    'none','root','native_id','filled','terminal','protection','extra_stop','callback',
    'truth_position','missing_reservation','wrong_order','partial_remaining','allocation_link',
    'missing_working_order','working_id','working_ref','working_security','working_client',
    'protective_order','malformed_order','working_status','parent_client','parent_epoch',
])
def test_native_ack_graceful_shutdown_requires_real_unfilled_ownership(fault):
    """Pure fixture prerequisite: no Core, shutdown, provider or transport."""
    class Denied(BaseException):
        pass
    validate=_pristine_paper_child_function('validate_pristine_native_ack_shutdown_ownership',
        dict(ForbiddenExternalIO=Denied))
    root='decision-root-order'
    plan=dict(account='SYNTHETIC_TEST',symbol='JPM',entry_price=10.30,stop_price=10.2897,
        con_id=123,currency='USD',exchange='SMART',client_id=999,epoch=0)
    request=dict(client_order_id=root,symbol='JPM',direction='LONG',quantity=1,
        strategy_name='RossMomentumStrategyV1',setup_family_id='PREMARKET_HIGH_BREAK',
        stop_loss_price=10.2897,invalidation_level=10.30,take_profit_price=None,
        target_model='HOD / next resistance extension after PMH acceptance',
        setup_metadata=dict(canonical_result_index=4,execution_stream=dict(execution_trigger_timeframe='10s')),
        relationship_context=None)
    parent=dict(request=request,requested=1,filled=0,terminal=False,protection_confirmed=False,
        notional=0.,mode='PAPER',account='SYNTHETIC_TEST',symbol='JPM',side='LONG',
        decision_id='decision-root',broker_order_id='1001',native_client_id=999,native_connection_epoch=0)
    reservation=dict(order_id=root,symbol='JPM',side='LONG',strategy_id='ROSSMOMENTUMSTRATEGYV1',
        run_mode='PAPER',status='ACTIVE',quantity=1,remaining_quantity=1,filled_quantity=0,
        exposure_notional=0.,notional=10.30,remaining_notional=10.30)
    capital=dict(reservation,decision_id='capital-decision')
    allocation=dict(reservation,decision_id='allocation-decision',global_capital_decision_id='capital-decision')
    before=dict(capital_used=0.,capital_reserved=10.30,position_records={},registry=[],managed_positions={},
        post_fill={},protection={},canonical_trades={root:None},
        capital_reservations={'capital-reservation':capital},
        allocation_reservations={'allocation-reservation':allocation})
    dispatch=dict(role='entry',root_id=root,native_id=1001,
        contract=dict(symbol='JPM',conId=123,currency='USD',exchange='SMART',secType='STK'),
        order=dict(orderType='MKT',action='BUY',totalQuantity=1,parentId=0,orderRef=''))
    # The real memory ACK publishes a working entry: copy its supplied native
    # contract/order, then apply independent account/client callback facts.
    supplied_order=NS(**deepcopy(dispatch['order']))
    supplied_order.account=plan['account'];supplied_order.clientId=plan['client_id']
    working=NS(orderId=dispatch['native_id'],contract=NS(**deepcopy(dispatch['contract'])),
        order=supplied_order,orderState=NS(status='Submitted'))
    args=dict(before=before,parent=parent,root_id=root,plan=plan,provided_positions=[],provided_orders=[working],
        callbacks=[],dispatches=[dispatch],cycles=[dict(result=True)])
    if fault=='root':args['dispatches'][0]['root_id']='another-root'
    elif fault=='native_id':args['dispatches'][0]['native_id']=1002
    elif fault=='filled':parent['filled']=1
    elif fault=='terminal':parent['terminal']=True
    elif fault=='protection':parent['protection_confirmed']=True
    elif fault=='extra_stop':args['dispatches'].append(dict(role='stop',root_id=root,native_id=1002))
    elif fault=='callback':args['callbacks'].append(dict(status='Filled',filled=1,orderId=1001))
    elif fault=='truth_position':args['provided_positions'].append(dict(symbol='JPM',position=1,con_id=123))
    elif fault=='missing_reservation':before['capital_reservations']={}
    elif fault=='wrong_order':capital['order_id']='another-order'
    elif fault=='partial_remaining':capital['remaining_quantity']=0
    elif fault=='allocation_link':allocation['global_capital_decision_id']='unrelated-capital-decision'
    elif fault=='missing_working_order':args['provided_orders']=[]
    elif fault=='working_id':working.orderId=1002
    elif fault=='working_ref':working.order.orderRef='PROTECT|unrelated-root'
    elif fault=='working_security':working.contract.conId=124
    elif fault=='working_client':working.order.clientId=998
    elif fault=='protective_order':working.order.action='SELL';working.order.orderType='STP'
    elif fault=='malformed_order':del working.order
    elif fault=='working_status':working.orderState.status='PendingSubmit'
    elif fault=='parent_client':parent['native_client_id']=998
    elif fault=='parent_epoch':parent['native_connection_epoch']=1
    unchanged=deepcopy(args)
    if fault=='none':
        assert validate(**args) is None
    else:
        with pytest.raises(Denied,match='NATIVE_GRACEFUL_SHUTDOWN_ACK_PRECONDITION:'):
            validate(**args)
    assert args==unchanged  # Observation cannot manufacture ownership or repair the adverse facts.


@pytest.mark.parametrize('actual_result',[False,True])
def test_native_graceful_shutdown_verify_observer_preserves_actual_result(actual_result):
    """Pure observer check; no Core construction, shutdown or transport."""
    registry=[NS(symbol='JPM',quantity=1)]
    calls=[];probe=dict(verify_empty_calls=[])
    def actual_verify(*args,**kwargs):
        calls.append((args,kwargs))
        return actual_result
    plain=_pristine_paper_child_function('plain',dict(datetime=datetime))
    observer=_pristine_paper_child_function('observed_shutdown_verify_empty',
        dict(actual_verify_empty=actual_verify,probe=probe,plain=plain,
            core=NS(trade_registry=NS(snapshot=lambda:list(registry)))))
    assert observer('argument',label='supplied') is actual_result
    assert calls==[(('argument',),dict(label='supplied'))]
    assert probe['verify_empty_calls']==[dict(result=actual_result,registry=[dict(symbol='JPM',quantity=1)])]
    registry[0].quantity=0
    assert probe['verify_empty_calls'][0]['registry'][0]['quantity']==1


def test_pristine_native_paper_graceful_shutdown_preserves_accounted_owned_position(
        reassessment,monkeypatch,tmp_path,capsys,no_external_activity,runtime_schema_template):
    """Causal invariant: resource shutdown cannot stand in for a native fill."""
    import json,shutil
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    # Reuse the existing raw entry/protection tape and stop BEFORE any supplied
    # exit. No target, flat snapshot, cancellation or broker outcome is added.
    facts=_pristine_paper_loss_facts(reassessment,monkeypatch,tmp_path)
    facts.pop('observe_pristine_paper_loss_feedback')
    facts['config'].pop('DAILY_RISK_MAX_LOSS_AMOUNT')
    facts['paper_memory_plan'].pop('stop_fill_price')
    facts['paper_cycle_steps']=facts['paper_cycle_steps'][:3]
    facts['observe_pristine_native_graceful_shutdown']=True
    assert [row['name'] for row in facts['paper_cycle_steps']]==['ACK_ONLY','LATER_ENTRY_FILL','PROTECTED_REPEAT']
    assert all(raw['leg']=='entry' for step in facts['paper_cycle_steps'] for raw in step['executions'])
    database=tmp_path/'native-graceful-shutdown.sqlite3'
    shutil.copyfile(runtime_schema_template,database)
    path=tmp_path/'native-graceful-shutdown-facts.json';path.write_text(json.dumps(facts,default=str))
    report=run_native_core_cold_start(database,path,tmp_path/'native-graceful-shutdown-child')
    summary={key:report.get(key) for key in ('constructor_exception','harness_exception','cycle_exception',
        'stage','supervisor','evidence_dir','native_graceful_shutdown')}
    assert report.get('constructor_complete') and report['constructor_count']==1,summary
    assert not report.get('harness_exception') and not report.get('cycle_exception'),summary
    assert len(report['cycles'])==3 and all(row['result'] is True for row in report['cycles']),summary
    assert [row['role'] for row in report['synthetic_memory_dispatches']]==['entry','stop'],summary
    assert [row['leg'] for row in report['paper_execution_callbacks']]==['entry'],summary
    assert report['registry_evaluations'] and all(row['result_count']==33 for row in report['registry_evaluations'])
    assert not report['sdk_attempts'] and not any(row['mutation'] for row in report['wire_attempts'])
    assert not report['network_attempts'] and not report.get('native_curl_denials')
    assert not report.get('capital_enrollment_attempts') and no_external_activity==[]
    assert report['supervisor']['returncode']==0 and report['supervisor']['reaped'] and not report['supervisor']['timed_out']
    assert report['cleanup']['live_threads']==[]
    probe=report['native_graceful_shutdown']
    assert probe['attempted'] and not probe.get('exception'),summary
    assert len(report['trade_exit_shutdown_calls'])==1 and report['trade_exit_shutdown_calls'][0]['core_owned']
    before,after=probe['before'],probe['after']
    root=report['synthetic_memory_dispatches'][0]['root_id']
    assert before['manager_has_original_client'] and not after['manager_has_original_client']
    assert after['client_stop_event_set']
    assert before['supplied_positions']==after['supplied_positions']
    assert before['supplied_open_orders']==after['supplied_open_orders']
    assert before['supplied_positions'][0]['position']==1
    assert before['supplied_open_orders'][0]['order']['totalQuantity']==1
    assert probe['mutation_attempts_before']==probe['mutation_attempts_after']
    for field in ('native_state','native_orders','post_fill','canonical_trades','capital_used','capital_reserved',
            'capital_reservations','allocation_reservations','position_records','managed_positions','protection',
            'native_quarantined','startup_recovery_state','failsafe_block_new_entries'):
        assert before['engine'][field]==after['engine'][field],(field,summary)
    assert before['engine']['canonical_trades'][root]['quantity_open']==1
    assert before['engine']['capital_used']==10.53 and before['engine']['protection'][root]['protected']
    assert before['allocation_used_by_strategy']==after['allocation_used_by_strategy']
    for table in ('trade_lifecycle_events','trade_lifecycle_trades','trade_records','trades','trade_outcomes','capital_audit_events'):
        assert before['database'][table]==after['database'][table],(table,summary)
    assert not any(event['event_type']=='TRADE_CLOSED' for event in probe['events']),summary
    # Expected pre-repair failure: legacy shutdown mutates this real registry
    # before its later hook exception. Do not turn that exception into a pass or
    # infer a successful synthetic exit/PnL event which never occurred.
    assert after['engine']['registry']==before['engine']['registry'],summary
    assert len(after['engine']['registry'])==1
    assert len(probe['verify_empty_calls'])==1 and probe['verify_empty_calls'][0]['result'] is False,summary
    hooks=probe['shutdown_evidence']['hooks']
    verification=next(row for row in hooks if row['hook']=='active_trade_registry.verify_empty')
    assert verification['completed'] is False,summary


def test_pristine_native_paper_ack_shutdown_preserves_pending_request_and_reservations(
        reassessment,monkeypatch,tmp_path,capsys,no_external_activity,runtime_schema_template):
    """An empty filled registry does not erase an acknowledged native liability."""
    import json,shutil
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    facts=_pristine_paper_loss_facts(reassessment,monkeypatch,tmp_path)
    facts.pop('observe_pristine_paper_loss_feedback')
    facts['config'].pop('DAILY_RISK_MAX_LOSS_AMOUNT')
    facts['paper_memory_plan'].pop('stop_fill_price')
    facts['paper_cycle_steps']=facts['paper_cycle_steps'][:1]
    facts['observe_pristine_native_ack_graceful_shutdown']=True
    assert [row['name'] for row in facts['paper_cycle_steps']]==['ACK_ONLY']
    assert facts['paper_cycle_steps'][0]['executions']==[]
    assert facts['paper_cycle_steps'][0]['positions']==facts['paper_cycle_steps'][0]['open_orders']==[]
    database=tmp_path/'native-ack-graceful-shutdown.sqlite3'
    shutil.copyfile(runtime_schema_template,database)
    path=tmp_path/'native-ack-graceful-shutdown-facts.json';path.write_text(json.dumps(facts,default=str))
    report=run_native_core_cold_start(database,path,tmp_path/'native-ack-graceful-shutdown-child')
    summary={key:report.get(key) for key in ('constructor_exception','harness_exception','cycle_exception',
        'stage','supervisor','evidence_dir','native_graceful_shutdown')}
    assert report.get('constructor_complete') and report['constructor_count']==1,summary
    assert not report.get('harness_exception') and not report.get('cycle_exception'),summary
    assert len(report['cycles'])==1 and report['cycles'][0]['result'] is True,summary
    assert [row['role'] for row in report['synthetic_memory_dispatches']]==['entry'],summary
    assert report['paper_execution_callbacks']==[],summary
    assert report['registry_evaluations'] and all(row['result_count']==33 for row in report['registry_evaluations'])
    assert report['native_before'] is report['native_after_constructor'] is None
    assert not report['sdk_attempts'] and not any(row['mutation'] for row in report['wire_attempts'])
    assert not report['network_attempts'] and not report.get('native_curl_denials')
    assert not report.get('capital_enrollment_attempts') and no_external_activity==[]
    assert report['supervisor']['returncode']==0 and report['supervisor']['reaped'] and not report['supervisor']['timed_out']
    assert report['cleanup']['live_threads']==[]
    probe=report['native_graceful_shutdown']
    assert probe['attempted'] and not probe.get('exception'),summary
    assert len(report['trade_exit_shutdown_calls'])==1 and report['trade_exit_shutdown_calls'][0]['core_owned']
    before,after=probe['before'],probe['after']
    assert before['manager_has_original_client'] and not after['manager_has_original_client']
    assert after['client_stop_event_set']
    assert before['supplied_positions']==after['supplied_positions']==[]
    assert before['supplied_open_orders']==after['supplied_open_orders']
    assert len(before['supplied_open_orders'])==1
    assert probe['mutation_attempts_before']==probe['mutation_attempts_after']
    root=report['synthetic_memory_dispatches'][0]['root_id']
    retained=before['engine']['native_orders'][root];request=retained['request']
    assert retained['filled']==0 and retained['terminal'] is False
    assert retained['broker_order_id']==str(report['synthetic_memory_dispatches'][0]['native_id'])
    working=before['supplied_open_orders'][0]
    assert str(working['orderId'])==retained['broker_order_id']
    assert working['contract']['conId']==123 and working['contract']['symbol']=='JPM'
    assert working['order']['action']=='BUY' and working['order']['orderType']=='MKT'
    assert working['order']['totalQuantity']==1 and working['order']['parentId']==0
    assert working['order']['account']=='SYNTHETIC_TEST' and working['order']['clientId']==999
    assert working['orderState']['status']=='Submitted'
    assert request['quantity']==1 and request['setup_family_id']=='PREMARKET_HIGH_BREAK'
    assert request['invalidation_level']==10.3 and request['stop_loss_price']==10.2897
    assert request['take_profit_price'] is None and request['target_model'] and request['setup_metadata']
    allowed=[row for row in report['risk_evaluations'] if row['decision']['allowed']]
    assert len(allowed)==1 and allowed[0]['decision']['decision_id']==retained['decision_id']
    assert any(row['decision_id']==retained['decision_id'] for row in report['decision_artifacts'])
    for field in ('native_state','native_orders','post_fill','canonical_trades','capital_used','capital_reserved',
            'capital_reservations','allocation_reservations','position_records','managed_positions','protection',
            'registry','native_quarantined','startup_recovery_state','failsafe_block_new_entries'):
        assert before['engine'][field]==after['engine'][field],(field,summary)
    assert before['engine']['capital_reserved']==10.3 and before['engine']['capital_used']==0
    assert len(before['engine']['capital_reservations'])==len(before['engine']['allocation_reservations'])==1
    capital=next(iter(before['engine']['capital_reservations'].values()))
    allocation=next(iter(before['engine']['allocation_reservations'].values()))
    assert allocation['global_capital_decision_id']==capital['decision_id']
    for reservation in (capital,allocation):
        assert reservation['order_id']==root and reservation['status']=='ACTIVE'
        assert reservation['quantity']==reservation['remaining_quantity']==1
        assert reservation['filled_quantity']==0 and reservation['exposure_notional']==0
        assert reservation['notional']==reservation['remaining_notional']==10.3
    for field in ('post_fill','protection','position_records','registry','managed_positions'):
        assert not before['engine'][field]
    assert before['engine']['canonical_trades'][root] is None
    assert before['allocation_used_by_strategy']==after['allocation_used_by_strategy']
    assert all(value==0 for value in before['allocation_used_by_strategy'].values())
    for table in ('trade_lifecycle_events','trade_lifecycle_trades','trade_records','trades','trade_outcomes','capital_audit_events'):
        assert before['database'][table]==after['database'][table],(table,summary)
    assert not any(event['event_type']=='TRADE_CLOSED' for event in probe['events']),summary
    assert probe['verify_empty_calls']==[dict(result=True,registry=[])],summary
    hooks={row['hook']:row for row in probe['shutdown_evidence']['hooks']}
    assert hooks['active_trade_registry.verify_empty']['completed'] is True,summary
    assert hooks['trade_exit_engine.shutdown']['completed'] is False,summary
    assert hooks['trade_exit_engine.shutdown']['error_type']=='RuntimeError',summary
    assert all(row['completed'] for name,row in hooks.items() if name!='trade_exit_engine.shutdown'),summary
    completions=[row for row in probe['shutdown_evidence']['events'] if row['event']=='SHUTDOWN_COMPLETE']
    assert completions and completions[-1]['completed'] is False,summary


@pytest.mark.parametrize('prepared_result',[False,True])
def test_pristine_open_valuation_quote_remains_raw_external_evidence(prepared_result):
    """The new price tape supplies facts, never a mark or risk result."""
    class Denied(BaseException):pass
    guard=_pristine_paper_child_function('validate_pristine_paper_market_fact',
        dict(datetime=datetime,ForbiddenExternalIO=Denied))
    now=datetime(2026,10,20,13,35,32,tzinfo=timezone.utc)
    quote=dict(symbol='JPM',con_id=123,bid=10.31,ask=10.33,last_price=10.32,
        quote_timestamp_utc=now.isoformat())
    assert 10.2897<quote['last_price']<10.53
    if prepared_result:quote['native_valuation']=dict(price=10.32,unrealized_pnl=-.21)
    before=deepcopy(quote)
    if prepared_result:
        with pytest.raises(Denied,match='PRISTINE_PAPER_MARKET_CERTIFICATE:FIELDS'):
            guard(plan=dict(symbol='JPM',con_id=123),quote=quote,now=now,max_age=15.)
    else:
        result=guard(plan=dict(symbol='JPM',con_id=123),quote=quote,now=now,max_age=15.)
        assert result=={key:value for key,value in quote.items() if key not in {'symbol','con_id'}}
    assert quote==before


@pytest.mark.parametrize('include_unrealized,loss_limit,open_blocked',[
    pytest.param(True,.20,True,id='included-loss'),
    pytest.param(True,.22,False,id='included-below-limit'),
    pytest.param(False,.20,False,id='excluded-control'),
])
def test_pristine_fresh_process_native_open_valuation_reaches_actual_core_loss_gate(
        reassessment,monkeypatch,tmp_path,capsys,no_external_activity,runtime_schema_template,
        include_unrealized,loss_limit,open_blocked):
    """A real source LAST marks owned exposure before a later factual stop fill."""
    import json,shutil
    from test_startup_recovery_and_stop_protection import run_native_core_cold_start
    facts=_pristine_paper_loss_facts(reassessment,monkeypatch,tmp_path,loss_limit=loss_limit)
    facts['config']['DAILY_RISK_INCLUDE_UNREALIZED']=include_unrealized
    quote=facts['paper_cycle_steps'][2]['market_quote']
    quote.update(bid=10.31,ask=10.33,last_price=10.32)
    assert facts['paper_memory_plan']['stop_price']<quote['last_price']<facts['paper_memory_plan']['fill_price']
    assert facts['paper_cycle_steps'][2]['executions']==[]
    assert datetime.fromisoformat(quote['quote_timestamp_utc'])>datetime.fromisoformat(
        facts['paper_cycle_steps'][1]['executions'][0]['execution']['time'])
    database=tmp_path/'pristine-open-valuation.sqlite3'
    shutil.copyfile(runtime_schema_template,database)
    path=tmp_path/'pristine-open-valuation-facts.json';path.write_text(json.dumps(facts,default=str))
    report=run_native_core_cold_start(database,path,tmp_path/'pristine-open-valuation-child')
    summary={key:report.get(key) for key in ('constructor_exception','harness_exception','cycle_exception',
        'stage','supervisor','evidence_dir')}
    assert report.get('constructor_complete') and report['constructor_count']==1,summary
    assert not report.get('harness_exception') and not report.get('cycle_exception'),summary
    assert len(report['cycles'])==5 and all(row['result'] is True and not row.get('exception')
        for row in report['cycles']),summary
    assert report['native_before'] is report['native_after_constructor'] is None
    assert report['after_constructor']['startup_recovery_state']=='RECOVERY_COMPLETE'
    assert report['offline_guard']['native_curl_checked']
    assert not report['network_attempts'] and not report.get('native_curl_denials'),summary
    assert not report['sdk_attempts'] and not any(row['mutation'] for row in report['wire_attempts']),summary
    assert not report.get('capital_enrollment_attempts'),summary
    assert report['registry_evaluations'] and all(row['result_count']==33 for row in report['registry_evaluations'])
    dispatches=report['synthetic_memory_dispatches']
    assert [row['role'] for row in dispatches]==['entry','stop'],summary
    buy,stop=dispatches;root=buy['root_id']
    assert buy['cycle']==1 and stop['cycle']==2 and stop['root_id']==root
    assert stop['order']['parentId']==buy['native_id'] and stop['order']['auxPrice']==10.2897
    ack,filled,marked,closed,replayed=report['cycles']
    request=ack['engine']['native_orders'][root]['request']
    assert request['setup_family_id']=='PREMARKET_HIGH_BREAK' and request['quantity']==1
    assert request['stop_loss_price']==10.2897 and request['invalidation_level']==10.3
    assert request['take_profit_price'] is None and request['target_model'] and request['setup_metadata']
    assert ack['engine']['capital_reserved']==10.3 and ack['engine']['capital_used']==0
    assert not ack['engine']['post_fill'] and not ack['engine']['position_records']
    assert len(report['execution_results'])==1
    assert len([row for row in report['risk_evaluations'] if row['decision']['allowed']])==1
    for cycle in (filled,marked):
        state=cycle['engine'];canonical=state['canonical_trades'][root]
        assert state['native_orders'][root]['request']==request
        assert canonical['quantity_open']==state['post_fill'][root]['filled_qty']==1
        assert canonical['quantity_closed']==0 and canonical['entry_avg_price']==10.53
        assert canonical['stop_price']==10.2897 and canonical['target_price'] is None
        assert canonical['gross_realized_pnl']==0
        assert state['protection'][root]['protected'] and state['capital_used']==10.53
        assert len(state['registry'])==len(state['managed_positions'])==1
        assert not state['native_quarantined'] and state['startup_recovery_state']=='RECOVERY_COMPLETE'
    decision=marked['daily_risk']['decision'];canonical=marked['engine']['canonical_trades'][root]
    assert marked['daily_risk']['state']['recovered'],marked['daily_risk']
    assert decision['include_unrealized'] is include_unrealized
    assert decision['realized_pnl']==0 and decision['daily_trade_count']==0
    assert decision['unrealized_pnl']==pytest.approx(-.21 if include_unrealized else 0),marked['daily_risk']
    assert decision['blocks_new_entries'] is open_blocked,marked['daily_risk']
    assert decision['audit_payload']['source']=='CoreOrchestrator' and decision['audit_payload']['stage']=='PRE_STRATEGY'
    if open_blocked:
        assert decision['status']=='MANAGED_ONLY' and decision['lock_status']=='LOCKED'
        assert decision['reason']=='MAX_DAILY_LOSS_AMOUNT'
    if include_unrealized:
        assert canonical['last_mark_price']==10.32 and canonical['unrealized_pnl']==pytest.approx(-.21)
        entry=next(row for row in marked['database']['trade_lifecycle_events'] if row['execution_id']=='pristine-loss-entry')
        marks=[row for row in marked['database']['trade_lifecycle_events'] if row['source']=='native_valuation']
        assert marks
        selected=[row for row in marks if row['price']==10.32]
        assert selected  # No cache clearing or prepared mark may create this witness.
        for row in selected:
            assert row['quantity']==0 and row['execution_id'] is None and row['event_type']=='NATIVE_MARK'
            witness=json.loads(row['payload_json'])['native_valuation']
            assert witness['root_order_id']==root and witness['basis_event_ids']==[entry['event_id']]
            assert witness['account']=='SYNTHETIC_TEST' and witness['con_id']==123 and witness['client_id']==999
            assert witness['connection_epoch']==0 and witness['symbol']=='JPM'
            assert witness['quantity']==1 and witness['entry_avg_price']==10.53
            assert witness['market_timestamp']==quote['quote_timestamp_utc']
            assert witness['last_fill_timestamp']==facts['paper_cycle_steps'][1]['executions'][0]['execution']['time']
            assert witness['source']=='IBKR' and witness['market_data_type']=='LIVE' and witness['completed'] is True
            assert type(witness['request_id']) is int
    else:
        assert canonical['last_mark_price'] is None and canonical['unrealized_pnl']==0
        assert not any(row['source']=='native_valuation' for row in marked['database']['trade_lifecycle_events'])
    for cycle in (closed,replayed):
        state=cycle['engine'];canonical=state['canonical_trades'][root]
        assert canonical['status']=='CLOSED' and canonical['quantity_open']==state['post_fill'][root]['filled_qty']==0
        assert canonical['quantity_closed']==1 and canonical['gross_realized_pnl']==pytest.approx(-.25)
        assert canonical['unrealized_pnl']==0 and set(canonical['source_execution_ids'])=={'pristine-loss-entry','pristine-loss-stop'}
        assert state['capital_used']==state['capital_reserved']==0
        assert not state['registry'] and not state['managed_positions']
        assert not state['capital_reservations'] and not state['allocation_reservations']
        assert state['capital_scope'] is None and not state['capital_writer_present']
        daily=cycle['daily_risk']['decision']
        assert daily['status']=='MANAGED_ONLY' and daily['reason']=='MAX_DAILY_LOSS_AMOUNT'
        assert daily['realized_pnl']==pytest.approx(-.25) and daily['unrealized_pnl']==0
        assert daily['daily_trade_count']==daily['losing_trade_count']==daily['consecutive_losses']==1
        financial=[row for row in cycle['database']['trade_lifecycle_events'] if row['source']!='native_valuation']
        assert len(financial)==2 and {row['execution_id'] for row in financial}=={'pristine-loss-entry','pristine-loss-stop'}
        assert not any(event['event_type']=='TRADE_CLOSED' for event in cycle['events'])
    assert [row['leg'] for row in report['paper_execution_callbacks']]==['entry','stop','stop']
    assert report['paper_execution_callbacks'][1]['execution']==report['paper_execution_callbacks'][2]['execution']
    assert closed['database']['trade_lifecycle_events']==replayed['database']['trade_lifecycle_events']
    assert closed['engine']['position_records']==replayed['engine']['position_records']
    assert [row['exposure_release_calls_after'] for row in report['cycles']]==[0,0,0,2,2]
    assert len(report['exposure_release_calls'])==2
    assert {row['authority'] for row in report['exposure_release_calls']}=={'capital','allocation'}
    assert all(row['cycle']==4 and row['kwargs']['quantity']==1 and row['kwargs']['price']==10.53
        and row['result']==10.53 and 'exception' not in row for row in report['exposure_release_calls'])
    assert report['trade_exit_shutdown_calls']==[]
    assert report['cleanup']['live_threads']==[] and report['cleanup']['execution_resource_close_complete']
    assert report['supervisor']['returncode']==0 and report['supervisor']['reaped'] and not report['supervisor']['timed_out']
    assert no_external_activity==[]
