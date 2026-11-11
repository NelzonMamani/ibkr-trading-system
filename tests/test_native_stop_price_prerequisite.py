"""Explicit mechanism proof; no automatic BE/trailing policy is enrolled."""
from copy import deepcopy
from datetime import datetime, timezone
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
