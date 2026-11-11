"""Joined native PMH callback investigation. No production changes or real I/O."""
from copy import deepcopy
from datetime import timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from ibapi.client import EClient

# Capture the existing audited SDK owner before function-scoped transport guards.
# The single real-encoder test below stubs sendMsg, never the guard itself.
_AUDITED_SDK_PLACE_ORDER = EClient.placeOrder

from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import IbkrExecutionProvider
from src.ibkr.position_snapshot import BrokerPositionResult
from src.ibkr.mutation_audit import snapshot as mutations
from src.models.execution_result import ExecutionResult
from test_joined_core_pmh_paper_assessment import (
    paper_pmh, reassessment, lifecycle, _reset_config, forbid_io, no_external_activity,
)


def late_pmh(reassessment,monkeypatch,tmp_path,*,paper_factory=paper_pmh,position_case='complete_empty',
             fill_price=10.31,stop_price=10.3-max(.01,10.3*.001),expected_stop_quantity=1,unit_stops=False,unit_fault=None):
    facts={};reads=[];sent=[];stops=[];open_orders=[];quantity=[0]
    def cached(order_id):
        reads.append(order_id)
        return deepcopy(facts.get(order_id,{}))
    def positions():
        return [NS(symbol='JPM',position=quantity[0],con_id=123,avgCost=fill_price,account='SYNTHETIC_TEST')] if quantity[0] else []
    def place_stop(**kw):
        broker_id=72+len(stops) if unit_stops else 72
        if unit_stops and 'before_submit' in kw:
            native=NS(orderType='STP',parentId=71,orderRef='PROTECT|'+str(kw['trade_id']),action='SELL',totalQuantity=kw['quantity'],auxPrice=kw['stop_price'])
            kw['before_submit'](broker_id,NS(symbol='JPM',conId=kw['con_id']),native)
        stops.append(deepcopy({key:value for key,value in kw.items() if key!='before_submit'}))
        assert (expected_stop_quantity is None or kw['quantity']==expected_stop_quantity) and kw['stop_price']==stop_price
        open_orders.append(NS(orderId=broker_id,contract=NS(symbol='JPM',conId=123),
            order=NS(orderType='STP',parentId=71,orderRef='PROTECT|'+str(kw['trade_id']),action='SELL',totalQuantity=kw['quantity'],auxPrice=kw['stop_price']),
            orderState=NS(status='Submitted')))
        if unit_stops and unit_fault==len(stops):raise OSError('synthetic ambiguous unit stop write')
        return dict(broker_order_id=str(broker_id),status='Submitted',order_type='STP')
    from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionManager, IbkrConnectionConfig
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    native_client=IbkrClient('offline',0,999,5,'LIVE',not unit_stops)
    # External connection state and callback facts only; the manager accessor,
    # provider and all internal decisions remain real.
    monkeypatch.setattr(native_client,'isConnected',lambda:True)
    monkeypatch.setattr(native_client,'cached_order_status',cached)
    connection=IbkrConnectionManager(IbkrConnectionConfig('offline',0,999,5,'LIVE',True,'PAPER'))
    connection._client=native_client
    for method in ('connect','ensure_connected','get_client','_connect_locked'):
        monkeypatch.setattr(connection,method,lambda *a,**k:pytest.fail('Implicit provider connection forbidden'))
    broker=NS(positions=positions,open_orders=lambda **kw:list(open_orders),
        connection_manager=connection,place_stop_order=place_stop)
    def provider_factory(**kw):
        return IbkrExecutionProvider(broker=broker,trade_registry=kw['trade_registry'],run_mode=kw['run_mode'])
    h=paper_factory(reassessment,monkeypatch,tmp_path,position_case,provider_factory=provider_factory)
    engine=h.core.execution_engine
    # Restore actual existing route owner; ONLY native broker transport is fake.
    monkeypatch.setattr(engine,'_route_order',ExecutionEngine._route_order.__get__(engine))
    def transport(request):
        assert not sent,'repeat or unexpected synthetic routing'
        sent.append(deepcopy(request))
        open_orders.append(NS(orderId=71,contract=NS(symbol=request.symbol,conId=123),
            order=NS(orderType='MKT',parentId=0,orderRef=request.client_order_id,action='BUY',totalQuantity=request.quantity),
            orderState=NS(status='Submitted')))
        return ExecutionResult(symbol=request.symbol,trader_type=request.trader_type,attempted=True,
            status='Submitted',rationale='synthetic external acknowledgement',direction=request.direction,
            quantity=request.quantity,requested_quantity=request.quantity,filled_quantity=0,remaining_quantity=request.quantity,
            client_order_id=request.client_order_id,ibkr_order_id=71,acknowledged_at=h.life.clock.current.isoformat())
    broker.place_order=transport
    def snapshot():
        return BrokerPositionResult(tuple(positions()),'COMPLETE','SYNTHETIC_TEST',h.life.clock.now(timezone.utc))
    native_client.position_snapshot=snapshot
    h.core.connection_manager._ibkr_connection_manager.existing_client=native_client
    h.native_manager=connection;h.native_client=native_client
    h.facts=facts;h.reads_native=reads;h.sent_native=sent;h.stop_requests=stops
    h.native_open_orders=open_orders;h.native_quantity=quantity
    h.collect_calls=[];collect=engine.collect_relationship_updates
    def observed_collect(**kw):
        out=collect(**kw)
        h.collect_calls.append(deepcopy(out))
        return out
    monkeypatch.setattr(engine,'collect_relationship_updates',observed_collect)
    return h


def acknowledge(h,capsys,*,expected_quantity=1):
    assert h.core.run_once();capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();out=capsys.readouterr().out
    assert len(h.sent_native)==len(h.artifacts)==len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0];request=h.sent_native[0]
    assert intent.setup_family_id==request.setup_family_id=='PREMARKET_HIGH_BREAK'
    assert not intent.relationship_context and not request.relationship_context
    assert not h.manager._relationship_plans and not h.manager.snapshot_positions()
    assert request.quantity==decision.max_position_size==expected_quantity and decision.allowed
    assert request.client_order_id.startswith(intent.decision_id)
    assert intent.decision_id==decision.decision_id==h.artifacts[0][0].decision_id
    assert received['entry_price']==intent.entry_price==intent.invalidation_level==request.invalidation_level==10.3
    assert intent.stop_loss_price==request.stop_loss_price==10.3-max(.01,10.3*.001)
    assert request.take_profit_price is None and request.target_model==intent.target_model
    result=h.execution_results[0]
    assert result.submission_confirmed() and result.filled_quantity==0
    assert result.ibkr_order_id==71 and result.client_order_id==request.client_order_id
    assert not h.core.trade_registry.snapshot() and not h.core.execution_engine.position_records
    assert h.core.execution_engine.post_fill_lifecycle.get_trade(request.client_order_id) is None
    assert h.stop_requests==[] and h.reads_native==[]
    assert h.core.execution_engine.capital_authority.total_reserved_capital==pytest.approx(expected_quantity*10.3)
    assert h.core.execution_engine.capital_authority.total_used_exposure==0
    return request


def teardown_unsent_fixture(h,attempts):
    # Destruction of a wholly synthetic test scope, NOT production terminal
    # resolution. Assert ownership retention before here; never clear recovery.
    for owner in (h.core.execution_engine.capital_authority,h.core.execution_engine.strategy_allocation_authority):
        for r in list(owner.active_reservations.values()):
            owner.release_reservation(decision_id=r.decision_id,reason='SYNTHETIC_FIXTURE_TEARDOWN_ONLY')
        assert not owner.active_reservations
    assert attempts==[] and mutations()==dict(place=0,modify=0,cancel=0)


def test_native_pmh_later_fill_reaches_initial_protection(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge(h,capsys)
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        h.native_quantity[0]=1
        h.native_open_orders.clear()
        h.life.clock.current+=timedelta(seconds=1)
        cycle=h.core.run_once();capsys.readouterr()
        engine=h.core.execution_engine
        print('NATIVE_PMH_LATE_FILL',dict(cycle=cycle,sent=len(h.sent_native),cache_reads=h.reads_native,
            collectors=len(h.collect_calls),collected=[len(r) for r in h.collect_calls],
            registry=len(h.core.trade_registry.snapshot()),records=len(engine.position_records),
            stops=len(h.stop_requests),reserved=engine.capital_authority.total_reserved_capital,
            used=engine.capital_authority.total_used_exposure,
            truth_block=h.truth[-1][1].block_new_entries,truth_mismatches=[m.mismatch_type for m in h.truth[-1][0].mismatches]))
        assert len(h.sent_native)==1 and not h.manager._relationship_plans
        assert no_external_activity==[] and mutations()==dict(place=0,modify=0,cancel=0)
        # First lifecycle requirement. No direct processor call/manual fill state.
        assert h.reads_native==[71]
        assert len(engine.position_records)==len(h.stop_requests)==1
        life=engine.post_fill_lifecycle.get_trade(request.client_order_id)
        assert life.filled_qty==1 and life.avg_fill_price==10.31 and life.selected_stop_price==request.stop_loss_price
        assert life.target is None and life.selected_target_price is None
        assert engine.post_fill_lifecycle.assess_trade_stop_protection(request.client_order_id)['protected']
        assert engine._native_orders[request.client_order_id]['protection_confirmed']
        assert h.truth[-1][1].healthy and not h.truth[-1][1].block_new_entries
        assert h.manager.snapshot_positions()['JPM'].quantity==1
        for _ in range(2):
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
            assert len(engine.position_records)==len(h.stop_requests)==len(h.sent_native)==1
            assert engine.capital_authority.total_used_exposure==10.31 and engine.capital_authority.total_reserved_capital==0
            assert h.manager.snapshot_positions()['JPM'].quantity==1
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('family',['BULL_FLAG','FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK','VWAP_RECLAIM_CONTINUATION','MICRO_PULLBACK','CUP_HANDLE','OPENING_DRIVE','EMA_PULLBACK','VWAP_PULLBACK','TREND_CONTINUATION_STAIR_STEP'])
@pytest.mark.parametrize('fault',['missing','unrelated','wrong_owner','malformed'])
def test_canonical_callback_fault_cannot_create_position_or_protection(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,fault,family):
    h,acknowledge_case,entry,fill_price=standalone_case(reassessment,monkeypatch,tmp_path,family)
    try:
        acknowledge_case(h,capsys);engine=h.core.execution_engine
        facts=dict(status='Filled',filled=1,remaining=0,avgFillPrice=fill_price)
        if fault=='unrelated':h.facts[999]=facts
        if fault=='wrong_owner':h.facts[71]=dict(facts,client_order_id='UNRELATED')
        if fault=='malformed':h.facts[71]=dict(facts,filled=float('nan'))
        h.life.clock.current+=timedelta(seconds=1)
        cycle=h.core.run_once();capsys.readouterr()
        assert cycle is (fault in {'missing','unrelated'})
        assert h.reads_native==[71]
        assert len(h.sent_native)==1 and not h.stop_requests
        assert not engine.position_records and not h.manager.snapshot_positions()
        assert not h.core.trade_registry.snapshot()
        assert engine.capital_authority.total_reserved_capital==pytest.approx(entry(h.registry_batches[-1][0]) if callable(entry) else entry)
        assert engine.capital_authority.total_used_exposure==0
        if fault in {'wrong_owner','malformed'}:assert engine._native_quarantined
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('family',['BULL_FLAG','FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK','VWAP_RECLAIM_CONTINUATION','MICRO_PULLBACK','CUP_HANDLE','OPENING_DRIVE','EMA_PULLBACK','VWAP_PULLBACK','TREND_CONTINUATION_STAIR_STEP'])
def test_canonical_interrupted_accounting_keeps_facts_and_blocks_replay(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,family):
    h,acknowledge_case,entry,fill_price=standalone_case(reassessment,monkeypatch,tmp_path,family)
    try:
        request=acknowledge_case(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=fill_price)
        h.native_quantity[0]=1;h.native_open_orders.clear()
        original=engine._record_fill_and_position
        def interrupted(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('synthetic interruption after actual accounting')
        monkeypatch.setattr(engine,'_record_fill_and_position',interrupted)
        truth_count=len(h.truth)
        h.life.clock.current+=timedelta(seconds=1)
        assert not h.core.run_once();capsys.readouterr()
        before=(len(engine.position_records),len(h.stop_requests),engine.capital_authority.total_used_exposure)
        # Accounting also invokes selected-stop lifecycle before Core projection.
        # Applied effects survive the interruption; quarantine forbids replay.
        assert before==(1,1,fill_price)
        assert engine._native_quarantined
        assert engine._native_orders[request.client_order_id]['cached_update_in_progress']
        assert not h.manager.snapshot_positions()  # Core processor not reached.
        # Ingestion aborts before a new reconciliation; old healthy truth is
        # historical only, while the failed cycle and native latch block work.
        assert len(h.truth)==truth_count
        h.life.clock.current+=timedelta(seconds=1)
        assert not h.core.run_once();capsys.readouterr()
        assert before==(len(engine.position_records),len(h.stop_requests),engine.capital_authority.total_used_exposure)
        assert len(h.sent_native)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('family',['BULL_FLAG','FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK','VWAP_RECLAIM_CONTINUATION','MICRO_PULLBACK','CUP_HANDLE','OPENING_DRIVE','EMA_PULLBACK','VWAP_PULLBACK','TREND_CONTINUATION_STAIR_STEP'])
def test_canonical_uncertain_ack_keeps_reservation_without_resubmission(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,family):
    h,acknowledge_case,entry,fill_price=standalone_case(reassessment,monkeypatch,tmp_path,family)
    try:
        broker=h.core.execution_engine._provider.broker;original=broker.place_order
        def uncertain(request):
            result=original(request)
            result.status='TIMED_OUT';result.ibkr_order_id=None
            result.retry_scheduled=True;result.next_retry_tick=100
            return result
        monkeypatch.setattr(broker,'place_order',uncertain)
        assert h.core.run_once();capsys.readouterr()
        h.life.clock.current+=timedelta(seconds=11)
        assert h.core.run_once();capsys.readouterr()
        engine=h.core.execution_engine
        assert h.evaluated[0][0].setup_family_id==family and h.evaluated[0][2].allowed
        assert not h.execution_results[0].submission_confirmed()
        for _ in range(2):
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
        assert len(h.sent_native)==1 and not h.stop_requests
        assert not engine.position_records and not h.manager.snapshot_positions()
        assert engine.capital_authority.total_reserved_capital==pytest.approx(entry(h.registry_batches[-1][0]) if callable(entry) else entry)
        assert engine.capital_authority.total_used_exposure==0
        assert engine.pending_book.due_orders(1000)==[]
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('family,position_case', [
    (family,case) for family in ('BULL_FLAG','FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT',
        'FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK','VWAP_RECLAIM_CONTINUATION','MICRO_PULLBACK','CUP_HANDLE','OPENING_DRIVE','EMA_PULLBACK','VWAP_PULLBACK','TREND_CONTINUATION_STAIR_STEP') for case in ('unknown','quantity_warning_larger','five')
] + [('BULL_FLAG','partial'),('OPENING_RANGE_BREAKOUT','partial'),('HOD_BREAK','partial'),('VWAP_RECLAIM_CONTINUATION','partial'),('MICRO_PULLBACK','partial'),('CUP_HANDLE','partial'),('OPENING_DRIVE','partial'),('EMA_PULLBACK','partial'),('VWAP_PULLBACK','partial'),('TREND_CONTINUATION_STAIR_STEP','partial')])
def test_canonical_paper_truth_veto_has_zero_admission_effects(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,position_case,family):
    from test_joined_core_first_pullback import first_joined
    from test_abcd_production_handoff import abcd_joined
    from test_joined_core_pmh_readonly import standalone_bull_joined, key_joined, consolidation_joined, flat_top_joined, orb_joined, hod_joined, momentum_joined, micro_joined, cup_joined, opening_drive_joined, indicator_pullback_joined, vwap_pullback_joined, stair_step_joined
    factories={'BULL_FLAG':standalone_bull_joined,'FIRST_PULLBACK':first_joined,'ABCD':abcd_joined,'KEY_LEVEL_BREAK':key_joined,
               'CONSOLIDATION_BREAKOUT':consolidation_joined,'FLAT_TOP_BREAKOUT':flat_top_joined,
               'OPENING_RANGE_BREAKOUT':orb_joined,'HOD_BREAK':hod_joined,'VWAP_RECLAIM_CONTINUATION':momentum_joined,'MICRO_PULLBACK':micro_joined,'CUP_HANDLE':cup_joined,'OPENING_DRIVE':opening_drive_joined,'EMA_PULLBACK':indicator_pullback_joined,'VWAP_PULLBACK':vwap_pullback_joined,'TREND_CONTINUATION_STAIR_STEP':stair_step_joined}
    h=paper_pmh(reassessment,monkeypatch,tmp_path,position_case,joined_factory=factories[family])
    try:
        assert h.core.run_once();capsys.readouterr()
        h.life.clock.current+=timedelta(seconds=11)
        assert h.core.run_once();capsys.readouterr()
        raw=[i for batch in h.batches for i in batch]
        assert len(raw)==1 and raw[0].setup_family_id==family
        assert raw[0].decision_id is None and h.truth[-1][1].block_new_entries
        assert h.artifacts==h.evaluated==h.execution_calls==h.boundaries==h.reserves==[]
        engine=h.core.execution_engine
        assert not engine.position_records and not engine.capital_authority.active_reservations
        assert not engine.strategy_allocation_authority.active_reservations
        assert engine.capital_authority.total_reserved_capital==engine.capital_authority.total_used_exposure==0
        snapshot,verdict=h.truth[-1]
        if position_case in {'unknown','partial'}:assert snapshot.snapshot_status=='UNKNOWN'
        elif position_case=='five':assert verdict.critical_mismatch_count==5
        else:
            assert snapshot.broker_positions['SYNTH_MATCH'].quantity==3
            assert snapshot.system_positions['SYNTH_MATCH'].quantity==2 and not verdict.block_exits
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('evidence',['missing','pending','malformed','unrelated'])
def test_cache_evidence_does_not_manufacture_fill_or_release_ownership(reassessment,monkeypatch,
        tmp_path,capsys,no_external_activity,evidence):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        acknowledge(h,capsys)
        if evidence=='pending':h.facts[71]=dict(status='PendingSubmit',filled=0,remaining=1)
        if evidence=='malformed':h.facts[71]=dict(status='Filled',filled=float('nan'),remaining=-1,avgFillPrice='bad')
        if evidence=='unrelated':h.facts[999]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        h.life.clock.current+=timedelta(seconds=1)
        if evidence=='malformed':
            assert not h.core.run_once()
            assert h.core.execution_engine._native_quarantined
        else:assert h.core.run_once()
        capsys.readouterr()
        assert len(h.sent_native)==1 and not h.manager._relationship_plans
        assert h.reads_native==[71]
        assert not h.core.trade_registry.snapshot() and not h.core.execution_engine.position_records
        assert not h.manager.snapshot_positions() and h.stop_requests==[]
        assert h.core.execution_engine.capital_authority.total_reserved_capital==pytest.approx(10.3)
        assert h.core.execution_engine.capital_authority.total_used_exposure==0
        assert h.core.execution_engine.capital_authority.capital_scope is None
        assert no_external_activity==[] and mutations()==dict(place=0,modify=0,cancel=0)
    finally:teardown_unsent_fixture(h,no_external_activity)


def late_first(reassessment,monkeypatch,tmp_path,*,position_case='complete_empty',market_fault='none'):
    from test_joined_core_first_pullback import first_joined
    def first_factory(*args,**kwargs):
        return first_joined(*args,market_fault=market_fault,**kwargs)
    def paper_first(*args,**kwargs):
        h=paper_pmh(*args,joined_factory=first_factory,**kwargs)
        # Coherent synthetic scanner facts; keep measured candle entry distinct
        # from the current quote and later external fill, both 10.55.
        for row in h.rows.values():
            gap=(row['last_price']/row['prev_close']-1)*100
            row.update(gap_pct=gap,pct_change=gap)
        return h
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_first,
        position_case=position_case,fill_price=10.55,stop_price=10.15)


def acknowledge_first(h,capsys):
    return acknowledge_selected(h,capsys,family='FIRST_PULLBACK',entry=10.42,stop=10.15,
        invalidation=10.15,triggers=h.first_triggers)


def acknowledge_selected(h,capsys,*,family,entry,stop,invalidation,triggers,
                         pattern_id=None,allow_execution_touch=False,execution_high_touch=False):
    from test_joined_core_bull_micro import _cadence
    from src.scanner import scanner_runner as ross
    assert h.core.run_once();capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();out=capsys.readouterr().out
    assert len(h.sent_native)==len(h.artifacts)==len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0];request=h.sent_native[0]
    if callable(entry):entry=entry(h.registry_batches[-1][0])
    raw=[i for batch in h.batches for i in batch]
    artifact,built=h.artifacts[0]
    assert raw==[intent] and artifact.intents==[intent] and built==h.raw_snapshots
    assert built[0]['decision_id'] is None
    assert received==dict(built[0],decision_id=artifact.decision_id)==vars(intent)
    assert request.setup_family_id==intent.setup_family_id==family
    assert decision.allowed and not decision.execution_blocked and decision.run_mode=='PAPER'
    assert intent.decision_id==decision.decision_id==artifact.decision_id
    assert request.client_order_id.startswith(intent.decision_id)
    assert request.quantity==decision.max_position_size==1
    assert request.trigger_id==intent.trigger_id==decision.trigger_id
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(entry,stop,invalidation)
    assert (decision.stop_loss_price,decision.invalidation_level)==(stop,invalidation)
    # Native request is a market order; measured entry belongs to intent/risk.
    assert request.order_type=='MKT'
    assert (request.stop_loss_price,request.invalidation_level)==(stop,invalidation)
    assert not request.relationship_context and not h.manager._relationship_plans
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    assert selected.setup_id==(pattern_id if pattern_id is not None else 'P_'+family) and selected.detected
    assert (selected.trigger_level,selected.stop_level,selected.invalidation_level)==(entry,stop,invalidation)
    assert request.target_model==intent.target_model==selected.target_suggestion
    assert request.take_profit_price is intent.take_profit_price is None
    payload,execution,trigger=triggers[-1]
    assert payload['canonical_result_index']==index and trigger['trigger_ready_now']
    if execution_high_touch:
        assert execution['candles'][-1].high==entry and execution['candles'][-1].close<entry
        assert source.candles[-1].close>entry  # Native structure already confirmed strictly.
    elif allow_execution_touch:assert execution['candles'][-1].close>=entry
    else:assert execution['candles'][-1].close>entry
    assert received['setup_metadata']==intent.setup_metadata
    assert _cadence(h.core).focus.symbols==['JPM'] and h.focus_calls
    news=ross._ross_news_contexts_from_news_intelligence_result(h.reads[-1])
    assert news['JPM']['ross_catalyst_valid']
    assert h.reads[-1].evidence_for_symbol('JPM')[0].evidence_id==h.article.evidence_id
    assert all(v.healthy and not v.block_new_entries for _,v in h.truth)
    for name,method in h.real_core_methods.items():assert getattr(h.core,name).__func__ is method
    result=h.execution_results[0]
    assert result.submission_confirmed() and result.filled_quantity==0
    assert result.ibkr_order_id==71 and result.client_order_id==request.client_order_id
    assert not h.core.trade_registry.snapshot() and not h.core.execution_engine.position_records
    assert not h.manager.snapshot_positions() and not h.stop_requests and not h.reads_native
    engine=h.core.execution_engine
    assert engine.post_fill_lifecycle.get_trade(request.client_order_id) is None
    assert h.reserves==['allocation','capital']
    assert engine.capital_authority.total_reserved_capital==pytest.approx(entry)
    assert engine.capital_authority.total_used_exposure==0
    assert engine.capital_authority.capital_scope is None
    assert engine.capital_authority._capital_writer is None
    return request


@pytest.mark.parametrize('market_fault',['none','forming_confirmation_source'])
def test_native_first_later_fill_reconciles_selected_initial_stop(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,market_fault):
    h=late_first(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    try:
        request=acknowledge_first(h,capsys)
        source=h.registry_batches[-1][0]
        assert all(b.timestamp+timedelta(minutes=1)<=source.observed_at_utc for b in source.candles[-6:-1])
        if market_fault=='forming_confirmation_source':
            assert source.candles[-1].timestamp<=source.observed_at_utc<source.candles[-1].timestamp+timedelta(minutes=1)
        confirm_selected_fill(h,request,capsys,family='FIRST_PULLBACK',fill_price=10.55,stop_price=10.15)
    finally:teardown_unsent_fixture(h,no_external_activity)


def confirm_selected_fill(h,request,capsys,*,family,fill_price,stop_price,expected_quantity=1):
    engine=h.core.execution_engine
    metadata=deepcopy(h.evaluated[0][0].setup_metadata)
    retained=deepcopy(engine._native_orders[request.client_order_id]['request'])
    # External callback and independent broker position/order facts only.
    h.facts[71]=dict(status='Filled',filled=expected_quantity,remaining=0,avgFillPrice=fill_price)
    h.native_quantity[0]=expected_quantity;h.native_open_orders.clear()
    h.life.clock.current+=timedelta(seconds=1)
    assert h.core.run_once();capsys.readouterr()
    assert h.reads_native==[71] and len(h.collect_calls[-1])==1
    filled=h.collect_calls[-1][0]
    assert filled.setup_family_id==family and filled.trigger_id==request.trigger_id
    assert filled.client_order_id==request.client_order_id and filled.ibkr_order_id=='71'
    assert filled.stop_loss_price==stop_price and filled.take_profit_price is None
    assert filled.target_model==request.target_model and not filled.relationship_context
    assert len(engine.position_records)==len(h.core.trade_registry.snapshot())==1
    assert len(h.sent_native)==len(h.stop_requests)==1
    life=engine.post_fill_lifecycle.get_trade(request.client_order_id)
    assert life.filled_qty==expected_quantity and life.avg_fill_price==fill_price
    assert life.selected_stop_price==stop_price and life.stop.trigger_price==stop_price
    assert life.stop.quantity==expected_quantity and life.stop.broker_order_id=='72'
    assert life.target is life.selected_target_price is None
    assert engine.post_fill_lifecycle.assess_trade_stop_protection(request.client_order_id)['protected']
    order=engine._native_orders[request.client_order_id]
    assert order['protection_confirmed'] and order['request']==retained
    assert h.evaluated[0][0].setup_metadata==metadata
    assert h.truth[-1][1].healthy and not h.truth[-1][1].block_new_entries
    position=h.manager.snapshot_positions()['JPM']
    assert position.quantity==expected_quantity and position.setup_family==family
    assert position.entry_price==fill_price and position.reference_order_id==request.client_order_id
    assert position.target_type=='DESCRIPTIVE_ONLY' and not position.trailing_active
    assert position.stop_loss_price==stop_price
    assert position.first_target_price is position.second_target_price is None
    assert not h.manager._relationship_plans
    assert engine.capital_authority.total_used_exposure==expected_quantity*fill_price
    assert engine.capital_authority.total_reserved_capital==0
    assert not engine.strategy_allocation_authority.active_reservations
    for _ in range(2):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
        assert len(engine.position_records)==len(h.core.trade_registry.snapshot())==1
        assert len(h.sent_native)==len(h.stop_requests)==1 and h.collect_calls[-1]==[]
        assert engine.capital_authority.total_used_exposure==expected_quantity*fill_price
        assert engine.capital_authority.total_reserved_capital==0
        assert h.manager.snapshot_positions()['JPM'].quantity==expected_quantity
        assert order['request']==retained and h.reserves==['allocation','capital']
        assert h.evaluated[0][0].setup_metadata==metadata
    return life


def late_abcd(reassessment,monkeypatch,tmp_path,*,market_fault='none'):
    from test_abcd_production_handoff import abcd_joined
    def joined_factory(*args,**kwargs):
        return abcd_joined(*args,market_fault=market_fault,**kwargs)
    def paper_abcd(*args,**kwargs):
        return paper_pmh(*args,joined_factory=joined_factory,**kwargs)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_abcd,
        fill_price=11.02,stop_price=10.35)


def acknowledge_abcd(h,capsys):
    from test_abcd_production_handoff import FACTS
    request=acknowledge_selected(h,capsys,family='ABCD',entry=11.,stop=10.35,
        invalidation=10.35,triggers=h.abcd_triggers)
    intent,received,_=h.evaluated[0]
    source,results=h.registry_batches[-1]
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert (selected.anchor_a_price,selected.anchor_b_price,selected.anchor_c_price)==(9.9,11.,10.35)
    assert (selected.anchor_a_index,selected.anchor_b_index,selected.anchor_c_index)==(43,45,47)
    assert selected.d_projection==pytest.approx(11.45)
    assert selected.risk_reference_level==10.35
    payload,_,_=h.abcd_triggers[-1]
    for key in FACTS:
        assert intent.setup_metadata[key]==received['setup_metadata'][key]==payload[key]==getattr(selected,key)
    assert intent.setup_metadata['source_metadata']==selected.setup_metadata
    assert selected.setup_metadata['source_candle_timestamps']==[b.timestamp.isoformat() for b in source.candles]
    assert selected.setup_metadata['observed_at_utc']==source.observed_at_utc.isoformat()
    assert source.observed_at_utc==h.life.clock.current
    witness=source.candles[selected.anchor_c_index+1]
    assert witness.timestamp+timedelta(minutes=1)<=source.observed_at_utc
    assert request.target_model=='AB measured move projection from C'
    assert h.rows['JPM']['last_price']==11.02
    assert h.rows['JPM']['gap_pct']==pytest.approx((11.02/9.8-1)*100)
    return request


def standalone_case(reassessment,monkeypatch,tmp_path,family):
    if family=='BULL_FLAG':
        return late_bull(reassessment,monkeypatch,tmp_path),acknowledge_bull,10.79,10.88
    if family=='FIRST_PULLBACK':
        return late_first(reassessment,monkeypatch,tmp_path),acknowledge_first,10.42,10.55
    if family=='ABCD':
        return late_abcd(reassessment,monkeypatch,tmp_path),acknowledge_abcd,11.,11.02
    if family=='CONSOLIDATION_BREAKOUT':
        return late_consolidation(reassessment,monkeypatch,tmp_path),acknowledge_consolidation,10.3,10.43
    if family=='FLAT_TOP_BREAKOUT':
        return late_flat_top(reassessment,monkeypatch,tmp_path),acknowledge_flat_top,10.2,10.27
    if family=='OPENING_RANGE_BREAKOUT':
        return late_orb(reassessment,monkeypatch,tmp_path),acknowledge_orb,10.3,10.42
    if family=='TREND_CONTINUATION_STAIR_STEP':
        return late_stair_step(reassessment,monkeypatch,tmp_path),acknowledge_stair_step,10.64,10.68
    if family=='VWAP_PULLBACK':
        return late_vwap_pullback(reassessment,monkeypatch,tmp_path),acknowledge_vwap_pullback,10.76,10.8
    if family=='EMA_PULLBACK':
        return late_ema_pullback(reassessment,monkeypatch,tmp_path),acknowledge_ema_pullback,10.5,10.53
    if family=='OPENING_DRIVE':
        return late_opening_drive(reassessment,monkeypatch,tmp_path),acknowledge_opening_drive,10.60,10.62
    if family=='CUP_HANDLE':
        return late_cup(reassessment,monkeypatch,tmp_path),acknowledge_cup,10.54,10.55
    if family=='MICRO_PULLBACK':
        return late_micro(reassessment,monkeypatch,tmp_path),acknowledge_micro,10.78,10.88
    if family=='VWAP_RECLAIM_CONTINUATION':
        return late_momentum(reassessment,monkeypatch,tmp_path),acknowledge_momentum,lambda source:max(source.indicators.ema9,source.indicators.vwap),10.34
    if family=='HOD_BREAK':
        return late_hod(reassessment,monkeypatch,tmp_path),acknowledge_hod,10.3,10.34
    assert family=='KEY_LEVEL_BREAK'
    return late_key(reassessment,monkeypatch,tmp_path),acknowledge_key,11.,11.02


@pytest.mark.parametrize('market_fault',['none','witness_boundary_source'])
def test_native_abcd_later_fill_reconciles_selected_initial_c_stop(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,market_fault):
    h=late_abcd(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    try:
        request=acknowledge_abcd(h,capsys)
        intent,received,_=h.evaluated[0]
        serialized=deepcopy(received)
        if market_fault=='witness_boundary_source':
            source=h.registry_batches[-1][0]
            assert source.candles[-2].timestamp+timedelta(minutes=1)==source.observed_at_utc
            assert source.candles[-1].timestamp<=source.observed_at_utc<source.candles[-1].timestamp+timedelta(minutes=1)
        life=confirm_selected_fill(h,request,capsys,family='ABCD',fill_price=11.02,stop_price=10.35)
        assert vars(intent)==serialized and received==serialized
        assert life.avg_fill_price!=intent.entry_price!=intent.setup_metadata['d_projection']
        assert life.avg_fill_price!=intent.setup_metadata['d_projection']
        assert life.target_model==intent.target_model and life.preserve_selected_protection
        assert life.selected_target_price is None
    finally:teardown_unsent_fixture(h,no_external_activity)


def late_key(reassessment,monkeypatch,tmp_path,*,market_fault='none'):
    from test_joined_core_pmh_readonly import key_joined
    def joined_factory(*args,**kwargs):
        return key_joined(*args,market_fault=market_fault,**kwargs)
    def paper_key(*args,**kwargs):
        return paper_pmh(*args,joined_factory=joined_factory,**kwargs)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_key,
        fill_price=11.02,stop_price=10.88)


def acknowledge_key(h,capsys):
    request=acknowledge_selected(h,capsys,family='KEY_LEVEL_BREAK',entry=11.,stop=10.88,
        invalidation=11.,triggers=h.key_triggers)
    intent,received,decision=h.evaluated[0]
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    assert index>0 and selected.setup_id=='P_KEY_LEVEL_BREAK'
    assert selected.stop_level!=selected.invalidation_level
    assert selected.stop_level==min(source.candles[-1].low,selected.trigger_level-.01)==10.88
    assert selected.setup_metadata['level_type']=='WHOLE_DOLLAR'
    assert selected.setup_metadata['selected_level_source']=='round_number'
    assert intent.setup_metadata['source_metadata']==selected.setup_metadata
    for key in ('trigger_level','stop_level','invalidation_level'):
        assert intent.setup_metadata[key]==received['setup_metadata'][key]==getattr(selected,key)
    payload,execution,trigger=h.key_triggers[-1]
    assert payload['stop_level']==trigger['stop_level']==request.stop_loss_price==decision.stop_loss_price==10.88
    assert payload['invalidation_level']==trigger['invalidation_price_reference']==request.invalidation_level==decision.invalidation_level==11.
    assert execution['candles'][-2].close<=11.<execution['candles'][-1].close
    assert execution['candles'][-1].volume>=execution['candles'][-2].volume
    assert source.observed_at_utc==h.life.clock.current
    assert received['setup_metadata']['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    assert request.target_model=='Expansion to next overhead key level'
    assert h.rows['JPM']['last_price']==11.02
    assert h.rows['JPM']['gap_pct']==pytest.approx((11.02/9.8-1)*100)
    retained=h.core.execution_engine._native_orders[request.client_order_id]['request']
    assert (retained['stop_loss_price'],retained['invalidation_level'])==(10.88,11.)
    return request


@pytest.mark.parametrize('market_fault',['none','forming_source','forming_execution'])
def test_native_key_later_fill_reconciles_distinct_selected_stop(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,market_fault):
    h=late_key(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    try:
        request=acknowledge_key(h,capsys)
        intent,received,decision=h.evaluated[0]
        serialized=deepcopy(received)
        source=h.registry_batches[-1][0]
        if market_fault=='forming_source':
            assert source.candles[-1].timestamp<=source.observed_at_utc<source.candles[-1].timestamp+timedelta(minutes=1)
        if market_fault=='forming_execution':
            candles=h.key_triggers[-1][1]['candles']
            assert candles[-1].timestamp<=source.observed_at_utc<candles[-1].timestamp+timedelta(seconds=10)
        life=confirm_selected_fill(h,request,capsys,family='KEY_LEVEL_BREAK',fill_price=11.02,stop_price=10.88)
        assert vars(intent)==serialized and received==serialized
        assert intent.entry_price==11. and life.avg_fill_price==11.02
        assert request.stop_loss_price==life.selected_stop_price==10.88
        assert intent.invalidation_level==decision.invalidation_level==request.invalidation_level==11.
        retained=h.core.execution_engine._native_orders[request.client_order_id]['request']
        assert (retained['stop_loss_price'],retained['invalidation_level'])==(10.88,11.)
        # Invalidation belongs to intent/risk/request contracts. Cached results,
        # managed positions and lifecycle expose selected protection, not a new
        # acceptance-invalidation field fabricated by this fixture.
        assert life.target_model==intent.target_model and life.preserve_selected_protection
        assert life.selected_target_price is None and not h.manager._relationship_plans
    finally:teardown_unsent_fixture(h,no_external_activity)


def late_consolidation(reassessment,monkeypatch,tmp_path,*,market_fault='none'):
    from test_joined_core_pmh_readonly import consolidation_joined
    def joined_factory(*args,**kwargs):
        return consolidation_joined(*args,market_fault=market_fault,**kwargs)
    def paper_consolidation(*args,**kwargs):
        return paper_pmh(*args,joined_factory=joined_factory,**kwargs)
    # Actual synthetic fill10.43 matches the existing10.42/10.44 quote; it is
    # distinct from the measured range-high entry10.30 of this market request.
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_consolidation,
        fill_price=10.43,stop_price=10.21)


def acknowledge_consolidation(h,capsys):
    from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
    request=acknowledge_selected(h,capsys,family='CONSOLIDATION_BREAKOUT',entry=10.3,
        stop=10.21,invalidation=10.21,triggers=h.consolidation_triggers,
        pattern_id='P_CONSOLIDATION_BREAK',allow_execution_touch=True)
    intent,received,decision=h.evaluated[0]
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    assert index>0 and [p.pattern_id for p in h.strategy._pattern_registry._patterns]==[
        p.pattern_id for p in RossPatternRegistry()._patterns]
    completed=[b for b in source.candles if b.timestamp+timedelta(minutes=1)<=source.observed_at_utc]
    assert len(completed)==50 and source.primary_timeframe=='1m'
    assert selected.trigger_level==max(b.high for b in completed[-6:-1])==10.3
    assert selected.stop_level==selected.invalidation_level==min(b.low for b in completed[-6:-1])==10.21
    assert completed[-1].close>10.3 and selected.setup_metadata['breakout_volume_confirmed']
    assert intent.setup_metadata['source_metadata']==selected.setup_metadata
    payload,execution,trigger=h.consolidation_triggers[-1]
    for key in ('trigger_level','stop_level','invalidation_level'):
        assert intent.setup_metadata[key]==received['setup_metadata'][key]==payload[key]==getattr(selected,key)
    assert trigger['trigger_reason']=='consolidation_breakout_confirmed'
    assert trigger['trigger_price_reference']==10.3 and trigger['invalidation_price_reference']==10.21
    assert execution['candles'][-1].volume>=sum(b.volume for b in execution['candles'][-5:-1])/4
    assert source.observed_at_utc==h.life.clock.current
    assert received['setup_metadata']['execution_stream']==payload['execution_stream']
    assert payload['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    assert request.target_model=='Range expansion'
    assert h.rows['JPM']['last_price']==10.43 and h.rows['JPM']['gap_pct']==pytest.approx((10.43/9.3-1)*100)
    retained=h.core.execution_engine._native_orders[request.client_order_id]['request']
    assert (retained['stop_loss_price'],retained['invalidation_level'])==(10.21,10.21)
    assert (decision.stop_loss_price,decision.invalidation_level)==(10.21,10.21)
    return request


@pytest.mark.parametrize('market_fault',['none','touch_execution','equal_volume_execution',
                                       'previous_above_execution','forming_execution'])
def test_native_consolidation_later_fill_reconciles_initial_range_stop(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,market_fault):
    h=late_consolidation(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    try:
        request=acknowledge_consolidation(h,capsys)
        intent,received,decision=h.evaluated[0];serialized=deepcopy(received)
        source=h.registry_batches[-1][0];candles=h.consolidation_triggers[-1][1]['candles']
        if market_fault=='touch_execution':assert candles[-1].close==intent.entry_price==10.3
        if market_fault=='equal_volume_execution':assert candles[-1].volume==sum(b.volume for b in candles[-5:-1])/4==100
        if market_fault=='previous_above_execution':assert candles[-2].close>10.3
        if market_fault=='forming_execution':
            assert candles[-1].timestamp<=source.observed_at_utc<candles[-1].timestamp+timedelta(seconds=10)
        life=confirm_selected_fill(h,request,capsys,family='CONSOLIDATION_BREAKOUT',fill_price=10.43,stop_price=10.21)
        assert vars(intent)==serialized and received==serialized
        assert intent.entry_price==10.3 and life.avg_fill_price==10.43
        assert request.stop_loss_price==life.selected_stop_price==10.21
        assert intent.invalidation_level==decision.invalidation_level==request.invalidation_level==10.21
        assert life.target_model==intent.target_model=='Range expansion' and life.preserve_selected_protection
        assert life.selected_target_price is None and not h.manager._relationship_plans
        retained=h.core.execution_engine._native_orders[request.client_order_id]['request']
        assert (retained['stop_loss_price'],retained['invalidation_level'])==(10.21,10.21)
    finally:teardown_unsent_fixture(h,no_external_activity)


def late_flat_top(reassessment,monkeypatch,tmp_path,*,market_fault='none'):
    from test_joined_core_pmh_readonly import flat_top_joined
    def joined_factory(*args,**kwargs):
        return flat_top_joined(*args,market_fault=market_fault,**kwargs)
    def paper_flat_top(*args,**kwargs):
        return paper_pmh(*args,joined_factory=joined_factory,**kwargs)
    # Actual synthetic fill10.27 is coherent with quote10.26/10.28, distinct
    # from measured resistance10.20 on this native market-order request.
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_flat_top,
        fill_price=10.27,stop_price=9.99)


def acknowledge_flat_top(h,capsys):
    from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
    request=acknowledge_selected(h,capsys,family='FLAT_TOP_BREAKOUT',entry=10.2,stop=9.99,
        invalidation=9.99,triggers=h.flat_top_triggers,allow_execution_touch=True)
    intent,received,decision=h.evaluated[0]
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    assert index>0 and [p.pattern_id for p in h.strategy._pattern_registry._patterns]==[
        p.pattern_id for p in RossPatternRegistry()._patterns]
    completed=[b for b in source.candles if b.timestamp+timedelta(minutes=1)<=source.observed_at_utc]
    pre=completed[-5:-1]
    assert len(completed)==50 and source.primary_timeframe=='1m' and len(pre)==4
    assert selected.trigger_level==max(b.high for b in pre)==10.2
    assert selected.stop_level==selected.invalidation_level==min(b.low for b in pre)==9.99
    tolerance=max(.02,selected.trigger_level*.003)
    assert sum(abs(b.high-selected.trigger_level)<=tolerance for b in pre)>=3
    assert completed[-1].close>=selected.trigger_level+tolerance*.25
    assert completed[-1].volume>sum(b.volume for b in pre)/4
    assert intent.setup_metadata['source_metadata']==selected.setup_metadata
    payload,execution,trigger=h.flat_top_triggers[-1]
    for key in ('trigger_level','stop_level','invalidation_level'):
        assert intent.setup_metadata[key]==received['setup_metadata'][key]==payload[key]==getattr(selected,key)
    assert trigger['trigger_reason']=='breakout_already_through_level'
    assert trigger['trigger_price_reference']==10.2 and trigger['invalidation_price_reference']==9.99
    assert source.observed_at_utc==h.life.clock.current
    assert received['setup_metadata']['execution_stream']==payload['execution_stream']
    assert payload['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    assert request.target_model=='Measured range expansion above flat-top resistance'
    assert h.rows['JPM']['last_price']==10.27 and h.rows['JPM']['gap_pct']==pytest.approx((10.27/9.2-1)*100)
    retained=h.core.execution_engine._native_orders[request.client_order_id]['request']
    assert (retained['stop_loss_price'],retained['invalidation_level'])==(9.99,9.99)
    assert (decision.stop_loss_price,decision.invalidation_level)==(9.99,9.99)
    return request


@pytest.mark.parametrize('market_fault',['none','touch_execution','forming_execution','zero_volume_execution'])
def test_native_flat_top_later_fill_reconciles_initial_resistance_stop(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,market_fault):
    h=late_flat_top(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    try:
        request=acknowledge_flat_top(h,capsys)
        intent,received,decision=h.evaluated[0];serialized=deepcopy(received)
        source=h.registry_batches[-1][0];candles=h.flat_top_triggers[-1][1]['candles']
        if market_fault=='touch_execution':assert candles[-1].close==intent.entry_price==10.2
        if market_fault=='forming_execution':
            assert candles[-1].timestamp<=source.observed_at_utc<candles[-1].timestamp+timedelta(seconds=10)
        if market_fault=='zero_volume_execution':assert candles[-1].volume==0.
        life=confirm_selected_fill(h,request,capsys,family='FLAT_TOP_BREAKOUT',fill_price=10.27,stop_price=9.99)
        assert vars(intent)==serialized and received==serialized
        assert intent.entry_price==10.2 and life.avg_fill_price==10.27
        assert request.stop_loss_price==life.selected_stop_price==9.99
        assert intent.invalidation_level==decision.invalidation_level==request.invalidation_level==9.99
        assert life.target_model==intent.target_model and life.preserve_selected_protection
        assert life.selected_target_price is None and not h.manager._relationship_plans
        retained=h.core.execution_engine._native_orders[request.client_order_id]['request']
        assert (retained['stop_loss_price'],retained['invalidation_level'])==(9.99,9.99)
    finally:teardown_unsent_fixture(h,no_external_activity)


def late_orb(reassessment,monkeypatch,tmp_path,*,market_fault='none'):
    from test_joined_core_pmh_readonly import orb_joined
    def joined_factory(*args,**kwargs):
        return orb_joined(*args,market_fault=market_fault,**kwargs)
    def paper_orb(*args,**kwargs):
        return paper_pmh(*args,joined_factory=joined_factory,**kwargs)
    # Existing market-order intent measures ORH10.30; external fill10.42 is
    # inside the coherent10.4175/10.4225 quote, not a changed entry anchor.
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_orb,
        fill_price=10.42,stop_price=9.95)


def acknowledge_orb(h,capsys):
    from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
    request=acknowledge_selected(h,capsys,family='OPENING_RANGE_BREAKOUT',entry=10.3,
        stop=9.95,invalidation=9.95,triggers=h.orb_triggers,pattern_id='P_ORB')
    intent,received,decision=h.evaluated[0]
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    assert index>0 and len(h.strategy._pattern_registry.patterns)==33
    assert [p.pattern_id for p in h.strategy._pattern_registry.patterns]==[
        p.pattern_id for p in RossPatternRegistry().patterns]
    opening=[b for b in source.candles if b.timestamp.hour==14 and 30<=b.timestamp.minute<=34]
    assert len(opening)==5 and source.primary_timeframe=='1m'
    assert all(b.timestamp+timedelta(minutes=1)<=source.observed_at_utc for b in opening)
    assert (max(b.high for b in opening),min(b.low for b in opening))==(10.3,9.95)
    assert source.candles[-1].close>10.3 and source.candles[-1].high>10.3
    assert source.candles[-1].volume>sum(b.volume for b in source.candles[:5])/5
    assert source.indicators.macd_line>0 and 'macd' not in source.news_context and 'macd_hist' not in source.news_context
    assert intent.setup_metadata['source_metadata']==selected.setup_metadata
    payload,execution,trigger=h.orb_triggers[-1]
    assert payload['source']=='canonical_pattern_result'
    assert trigger['trigger_reason']=='break_and_hold_above_orh'
    assert execution['candles'][-1].high>10.3 and execution['candles'][-1].close>10.3
    for key in ('trigger_level','stop_level','invalidation_level'):
        assert intent.setup_metadata[key]==received['setup_metadata'][key]==payload[key]==getattr(selected,key)
    assert received['setup_metadata']['execution_stream']==payload['execution_stream']
    assert payload['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    assert payload['execution_stream']['execution_trigger_timeframe']=='10s'
    assert payload['execution_stream']['timeframe_substitution'] is False
    assert source.observed_at_utc==h.life.clock.current
    assert request.target_model=='Continuation above the completed opening-range high.'
    assert h.rows['JPM']['last_price']==10.42 and h.rows['JPM']['gap_pct']==pytest.approx((10.42/9.3-1)*100)
    retained=h.core.execution_engine._native_orders[request.client_order_id]['request']
    assert (retained['stop_loss_price'],retained['invalidation_level'])==(9.95,9.95)
    assert (decision.stop_loss_price,decision.invalidation_level)==(9.95,9.95)
    return request


@pytest.mark.parametrize('market_fault',['none','forming_execution','zero_volume_execution'])
def test_native_orb_later_fill_reconciles_initial_opening_range_stop(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,market_fault):
    h=late_orb(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    try:
        request=acknowledge_orb(h,capsys)
        intent,received,decision=h.evaluated[0];serialized=deepcopy(received)
        source=h.registry_batches[-1][0];candles=h.orb_triggers[-1][1]['candles']
        if market_fault=='forming_execution':
            assert candles[-1].timestamp<=source.observed_at_utc<candles[-1].timestamp+timedelta(seconds=10)
        if market_fault=='zero_volume_execution':assert candles[-1].volume==0.
        life=confirm_selected_fill(h,request,capsys,family='OPENING_RANGE_BREAKOUT',fill_price=10.42,stop_price=9.95)
        assert vars(intent)==serialized and received==serialized
        assert intent.entry_price==10.3 and life.avg_fill_price==10.42
        assert request.stop_loss_price==life.selected_stop_price==9.95
        assert intent.invalidation_level==decision.invalidation_level==request.invalidation_level==9.95
        assert life.target_model==intent.target_model and life.preserve_selected_protection
        assert life.selected_target_price is None and not h.manager._relationship_plans
        retained=h.core.execution_engine._native_orders[request.client_order_id]['request']
        assert (retained['stop_loss_price'],retained['invalidation_level'])==(9.95,9.95)
        assert len(h.native_open_orders)==1 and h.native_open_orders[0].order.auxPrice==9.95
        assert h.native_open_orders[0].orderState.status=='Submitted'
    finally:teardown_unsent_fixture(h,no_external_activity)


def late_hod(reassessment,monkeypatch,tmp_path,*,market_fault='none'):
    from test_joined_core_pmh_readonly import hod_joined
    def joined_factory(*args,**kwargs):
        return hod_joined(*args,market_fault=market_fault,**kwargs)
    def paper_hod(*args,**kwargs):
        return paper_pmh(*args,joined_factory=joined_factory,**kwargs)
    # Actual later fill10.34 is inside quote10.33/10.35; measured HOD entry
    # remains10.30 and protection belongs to the selected source stop10.20.
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_hod,
        fill_price=10.34,stop_price=10.22 if market_fault=='forming_source' else 10.2)


def acknowledge_hod(h,capsys):
    from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
    from src.utils.time_utils import to_ny_time
    request=acknowledge_selected(h,capsys,family='HOD_BREAK',entry=10.3,stop=10.2,
        invalidation=10.2,triggers=h.hod_triggers)
    intent,received,decision=h.evaluated[0]
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    assert len(h.strategy._pattern_registry.patterns)==33 and index>0
    assert [p.pattern_id for p in h.strategy._pattern_registry.patterns]==[
        p.pattern_id for p in RossPatternRegistry().patterns]
    assert h.hod_decisions[-1]['selected_pattern_id']=='P_HOD_BREAK'
    assert h.hod_decisions[-1]['selected_candidate_index']==index
    assert source.levels.established_rth_hod==selected.trigger_level==10.3
    assert source.levels.hod==source.levels.key_levels['HOD']==source.levels.premarket_high==12.
    regular=[c for c in source.candles if to_ny_time(c.timestamp).time().hour>=9
        and (to_ny_time(c.timestamp).hour>9 or to_ny_time(c.timestamp).minute>=30)]
    assert len(regular)==40 and max(c.high for c in regular)==10.3
    assert all(c.timestamp+timedelta(minutes=1)<=source.observed_at_utc for c in regular)
    assert selected.setup_metadata['level_source']=='RTH'
    assert selected.stop_level==selected.invalidation_level==min(c.low for c in source.candles[-5:-1])==10.2
    assert intent.setup_metadata['source_metadata']==selected.setup_metadata
    payload,execution,trigger=h.hod_triggers[-1]
    assert payload['source']=='canonical_pattern_result' and payload['canonical_result_index']==index
    assert trigger['trigger_ready_now'] and trigger['trigger_reason']=='hod_break_confirmed'
    assert execution['candles'][-2].close<=10.3 and execution['candles'][-1].close>10.3*1.001
    assert execution['candles'][-1].timestamp>=source.candles[-1].timestamp+timedelta(minutes=1)
    for bar in source.candles[-5:]:
        parts=[c for c in execution['candles'] if bar.timestamp<=c.timestamp<bar.timestamp+timedelta(minutes=1)]
        assert len(parts)==6
        assert (parts[0].open,max(c.high for c in parts),min(c.low for c in parts),parts[-1].close,sum(c.volume for c in parts))==(bar.open,bar.high,bar.low,bar.close,bar.volume)
    for key in ('trigger_level','stop_level','invalidation_level'):
        assert intent.setup_metadata[key]==received['setup_metadata'][key]==payload[key]==getattr(selected,key)
    assert received['setup_metadata']['execution_stream']==payload['execution_stream']
    assert payload['execution_stream']['observed_at_utc']==source.observed_at_utc.isoformat()
    assert payload['execution_stream']['execution_trigger_timeframe']=='10s'
    assert payload['execution_stream']['timeframe_substitution'] is False
    assert source.observed_at_utc==h.life.clock.current
    assert request.target_model=='Continuation above the established regular-session high of day.'
    assert h.rows['JPM']['last_price']==10.34 and h.rows['JPM']['gap_pct']==pytest.approx((10.34/9.2-1)*100)
    retained=h.core.execution_engine._native_orders[request.client_order_id]['request']
    assert (retained['stop_loss_price'],retained['invalidation_level'])==(10.2,10.2)
    assert (decision.stop_loss_price,decision.invalidation_level)==(10.2,10.2)
    return request


@pytest.mark.parametrize('market_fault',['none','forming_execution','zero_volume_execution',
    'above_threshold_execution','previous_at_level_execution'])
def test_native_hod_later_fill_reconciles_initial_selected_stop(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,market_fault):
    h=late_hod(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    try:
        request=acknowledge_hod(h,capsys)
        intent,received,decision=h.evaluated[0];serialized=deepcopy(received)
        source=h.registry_batches[-1][0];execution=h.hod_triggers[-1][1]['candles']
        if market_fault=='forming_execution':
            assert execution[-1].timestamp<=source.observed_at_utc<execution[-1].timestamp+timedelta(seconds=10)
        if market_fault=='zero_volume_execution':assert execution[-1].volume==0.
        if market_fault=='above_threshold_execution':assert execution[-1].close==10.3*1.001+1e-9
        if market_fault=='previous_at_level_execution':assert execution[-2].close==10.3
        life=confirm_selected_fill(h,request,capsys,family='HOD_BREAK',fill_price=10.34,stop_price=10.2)
        assert vars(intent)==serialized and received==serialized
        assert intent.entry_price==10.3 and life.avg_fill_price==10.34
        assert request.stop_loss_price==life.selected_stop_price==10.2
        assert intent.invalidation_level==decision.invalidation_level==request.invalidation_level==10.2
        assert life.target_model==intent.target_model and life.preserve_selected_protection
        assert life.selected_target_price is None and not h.manager._relationship_plans
        retained=h.core.execution_engine._native_orders[request.client_order_id]['request']
        assert (retained['stop_loss_price'],retained['invalidation_level'])==(10.2,10.2)
        assert len(h.native_open_orders)==1 and h.native_open_orders[0].order.auxPrice==10.2
        assert h.native_open_orders[0].orderState.status=='Submitted'
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('market_fault',['late_window_source','opening_gap_source','at_threshold_execution',
    'previous_above_execution','invalidated_execution','future_execution'])
def test_hod_paper_reference_confirmation_and_arbitration_blocks(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,market_fault):
    h=late_hod(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    try:
        assert h.core.run_once();capsys.readouterr()
        h.life.clock.current+=timedelta(seconds=11)
        assert h.core.run_once();out=capsys.readouterr().out
        assert not [i for batch in h.batches for i in batch],out
        assert h.artifacts==h.evaluated==h.execution_calls==h.reserves==h.sent_native==h.stop_requests==[]
        source,results=h.registry_batches[-1]
        hod=next(r for r in results if r.setup_id=='P_HOD_BREAK')
        if market_fault in {'late_window_source','opening_gap_source'}:
            assert source.levels.established_rth_hod is None and not hod.detected
            assert hod.rejection_reason=='invalid_hod_source'
        else:
            assert hod.detected
            index=results.index(hod)
            blocked=[t for t in h.hod_engine_outputs if t.get('canonical_result_index')==index]
            assert len(blocked)==1 and not blocked[0]['trigger_ready_now']
            expected={'at_threshold_execution':'breakout_shape_invalid','previous_above_execution':'awaiting_hod_break',
                'invalidated_execution':'at_or_below_invalidation','future_execution':'hod_future_candle_data'}
            assert blocked[0]['trigger_reason']==expected[market_fault]
        engine=h.core.execution_engine
        assert not engine.position_records and not h.core.trade_registry.snapshot() and not h.manager.snapshot_positions()
        assert engine.capital_authority.total_reserved_capital==engine.capital_authority.total_used_exposure==0
        assert not engine.capital_authority.active_reservations and not engine.strategy_allocation_authority.active_reservations
    finally:teardown_unsent_fixture(h,no_external_activity)


def late_momentum(reassessment,monkeypatch,tmp_path):
    from test_joined_core_pmh_readonly import momentum_joined
    def paper_momentum(*args,**kwargs):
        return paper_pmh(*args,joined_factory=momentum_joined,**kwargs)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_momentum,
        fill_price=10.34,stop_price=10.23)


def acknowledge_momentum(h,capsys):
    request=acknowledge_selected(h,capsys,family='VWAP_RECLAIM_CONTINUATION',
        entry=lambda source:max(source.indicators.ema9,source.indicators.vwap),
        stop=10.23,invalidation=10.23,
        triggers=h.momentum_triggers,pattern_id='P_MOMENTUM_RECLAIM')
    return request


def test_momentum_later_fill_and_selected_shakeout_protection(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity):
    h=late_momentum(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge_momentum(h,capsys)
        confirm_selected_fill(h,request,capsys,family='VWAP_RECLAIM_CONTINUATION',
            fill_price=10.34,stop_price=10.23)
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_hod_paper_ready_fallback_when_momentum_has_no_fresh_cross(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity):
    h=late_hod(reassessment,monkeypatch,tmp_path,market_fault='forming_source')
    try:
        request=acknowledge_selected(h,capsys,family='HOD_BREAK',entry=10.3,stop=10.22,
            invalidation=10.22,triggers=h.hod_triggers)
        assert h.hod_decisions[-1]['selected_pattern_id']=='P_HOD_BREAK'
        assert any(r['pattern_id']=='P_MOMENTUM_RECLAIM' and r['reason']=='awaiting_reclaim_confirmation'
            for r in h.hod_decisions[-1]['rejected_candidates'])
        confirm_selected_fill(h,request,capsys,family='HOD_BREAK',fill_price=10.34,stop_price=10.22)
    finally:teardown_unsent_fixture(h,no_external_activity)



def late_micro(reassessment,monkeypatch,tmp_path,*,market_fault='none'):
    from test_joined_core_pmh_readonly import micro_joined
    def joined_factory(*args,**kwargs):return micro_joined(*args,market_fault=market_fault,**kwargs)
    def paper_micro(*args,**kwargs):return paper_pmh(*args,joined_factory=joined_factory,**kwargs)
    h=late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_micro,
        fill_price=10.88,stop_price=10.6)
    h.micro_fault=market_fault
    return h


def acknowledge_micro(h,capsys):
    request=acknowledge_selected(h,capsys,family='MICRO_PULLBACK',entry=10.78,stop=10.6,
        invalidation=10.6,triggers=h.micro_triggers,execution_high_touch=h.micro_fault=='touch_execution')
    intent=h.evaluated[0][0];source,results=h.registry_batches[-1]
    selected=results[intent.setup_metadata['canonical_result_index']]
    assert len(results)==len(h.strategy._pattern_registry.patterns)==33
    assert not intent.relationship_context and not h.manager._relationship_plans
    assert selected.target_suggestion==intent.target_model=='Prior high / HOD'
    assert intent.setup_metadata['source_metadata']==selected.setup_metadata
    if h.micro_fault!='red_pause':assert selected.setup_metadata['pullback_variant']=='SINGLE_GREEN_LOWER_WICK'
    return request


@pytest.mark.parametrize('market_fault',['none','red_pause','touch_execution'])
def test_micro_standalone_paper_later_fill_and_selected_initial_stop(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,market_fault):
    h=late_micro(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    try:
        request=acknowledge_micro(h,capsys)
        confirm_selected_fill(h,request,capsys,family='MICRO_PULLBACK',fill_price=10.88,stop_price=10.6)
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_standalone_selected_stop_later_fill_reaches_actual_core_flat(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity):
    h=late_momentum(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge_momentum(h,capsys)
        life=confirm_selected_fill(h,request,capsys,family='VWAP_RECLAIM_CONTINUATION',
            fill_price=10.34,stop_price=10.23)
        assert str(life.stop.broker_order_id)=='72' and life.filled_qty==1
        h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.23,
            symbol='JPM',side='SELL',orderId=72)
        h.native_quantity[0]=0;h.native_open_orders.clear()
        h.life.clock.current+=timedelta(seconds=1)
        h.core.run_once();out=capsys.readouterr().out
        positions=h.manager.snapshot_positions()
        observed=dict(stop_callback_read=72 in h.reads_native,lifecycle_quantity=life.filled_qty,
            managed_quantity=positions['JPM'].quantity if 'JPM' in positions else 0,
            registry_count=len(h.core.trade_registry.snapshot()),
            capital_used=h.core.execution_engine.capital_authority.total_used_exposure,
            truth_block=h.truth[-1][1].block_new_entries)
        assert observed['stop_callback_read'] and observed['lifecycle_quantity']==observed['managed_quantity']==observed['registry_count']==0,observed
        assert observed['capital_used']==0 and not observed['truth_block'],observed
        assert len(h.sent_native)==1 and len(h.stop_requests)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_selected_native_stop_keeps_actual_broker_parent_order_identity(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity):
    h=late_momentum(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge_momentum(h,capsys)
        confirm_selected_fill(h,request,capsys,family='VWAP_RECLAIM_CONTINUATION',fill_price=10.34,stop_price=10.23)
        assert h.stop_requests[0]['parent_order_id']==str(h.execution_results[0].ibkr_order_id)
    finally:teardown_unsent_fixture(h,no_external_activity)


STOP_FAMILIES=['BULL_FLAG','PREMARKET_HIGH_BREAK','FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK',
    'CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK',
    'VWAP_RECLAIM_CONTINUATION','MICRO_PULLBACK','CUP_HANDLE','OPENING_DRIVE','EMA_PULLBACK','VWAP_PULLBACK','TREND_CONTINUATION_STAIR_STEP']


def filled_standalone(reassessment,monkeypatch,tmp_path,capsys,family):
    if family=='PREMARKET_HIGH_BREAK':
        h=late_pmh(reassessment,monkeypatch,tmp_path,fill_price=10.53)
        ack=acknowledge;price=10.53
    else:h,ack,_,price=standalone_case(reassessment,monkeypatch,tmp_path,family)
    request=ack(h,capsys)
    life=confirm_selected_fill(h,request,capsys,family=family,fill_price=price,
        stop_price=request.stop_loss_price)
    return h,request,life


def external_stop_facts(h,life,*,status='Filled',filled=1,remaining=0):
    from dataclasses import replace
    price=round(life.selected_stop_price-.01,2)
    h.facts[72]=dict(status=status,filled=filled,remaining=remaining,avgFillPrice=price,
        symbol='JPM',side='SELL',orderId=72,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=remaining
    if not remaining:h.native_open_orders.clear()
    for row in h.rows.values():row.update(last_price=price,bid=price-.01,ask=price+.01,
        spread_pct=100*.02/price,gap_pct=100*(price/9.8-1))
    original=h.core.market_data_snapshot_manager.batch_snapshots
    def snapshots(symbols):
        values,errors=original(symbols)
        return {key:replace(value,last=price,bid=price-.01,ask=price+.01) for key,value in values.items()},errors
    h.core.market_data_snapshot_manager.batch_snapshots=snapshots
    h.life.clock.current+=timedelta(seconds=10)
    last=h.streams['10s'][-1]
    h.streams['10s'].append(replace(last,timestamp=h.life.clock.current-timedelta(seconds=10),
        open=last.close,high=max(last.close,price)+.01,low=price-.01,close=price,volume=400))
    # Update only still-forming external source/context bars; closed history
    # remains unchanged. Their OHLC/volume include this later execution decline.
    decline=h.streams['10s'][-1]
    for timeframe,seconds in (('1m',60),('5m',300)):
        if not h.streams.get(timeframe):continue
        bar=h.streams[timeframe][-1]
        if bar.timestamp<=h.life.clock.current<bar.timestamp+timedelta(seconds=seconds):
            h.streams[timeframe][-1]=replace(bar,high=max(bar.high,decline.high),low=min(bar.low,decline.low),
                close=price,volume=bar.volume+decline.volume)
    return price


@pytest.mark.parametrize('family',STOP_FAMILIES)
def test_selected_stop_fill_full_core_once_across_families(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,family):
    h,request,life=filled_standalone(reassessment,monkeypatch,tmp_path,capsys,family)
    try:
        engine=h.core.execution_engine;retained=deepcopy(engine._native_orders[request.client_order_id]['request'])
        metadata=deepcopy(h.evaluated[0][0].setup_metadata)
        price=external_stop_facts(h,life)
        assert h.core.run_once();capsys.readouterr()
        assert 72 in h.reads_native and life.filled_qty==0 and life.exited_qty==1
        assert life.realized_pnl==pytest.approx(price-life.avg_fill_price)
        assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
        assert engine.capital_authority.total_used_exposure==0
        assert engine.capital_authority.total_reserved_capital==0
        assert not engine.strategy_allocation_authority.active_reservations
        assert h.truth[-1][1].healthy and not h.truth[-1][1].block_new_entries
        assert len(engine.position_records)==2 # Historical entry and exit, not two open positions.
        for _ in range(3):
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
            assert life.exited_qty==1 and life.realized_pnl==pytest.approx(price-life.avg_fill_price)
            assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
            assert engine.capital_authority.total_used_exposure==0
            assert len(engine.position_records)==2 and len(h.sent_native)==len(h.stop_requests)==1
            assert h.collect_calls[-1]==[]
        assert engine._native_orders[request.client_order_id]['request']==retained
        assert h.evaluated[0][0].setup_metadata==metadata
        assert request.take_profit_price is life.selected_target_price is None
        assert life.target_model==request.target_model
        assert h.stop_requests[0]['parent_order_id']=='71'
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('fault',['symbol','side','account','client_order_id','orderId','decision_id',
    'parentId','orderRef','missing_counts','negative','fractional','oversize','nan_price','missing_price',
    'unknown_status','retained_parent','retained_mode','retained_decision'])
def test_selected_stop_bad_facts_quarantine_without_exit(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,fault):
    h,request,life=filled_standalone(reassessment,monkeypatch,tmp_path,capsys,'VWAP_RECLAIM_CONTINUATION')
    try:
        engine=h.core.execution_engine
        external_stop_facts(h,life)
        if fault in {'symbol','side','account','client_order_id','orderId','decision_id','parentId','orderRef'}:
            h.facts[72][fault]='UNRELATED'
        if fault=='missing_counts':h.facts[72].pop('filled')
        if fault=='negative':h.facts[72]['filled']=-1
        if fault=='fractional':h.facts[72]['filled']=.5
        if fault=='oversize':h.facts[72]['filled']=2
        if fault=='nan_price':h.facts[72]['avgFillPrice']=float('nan')
        if fault=='missing_price':h.facts[72].pop('avgFillPrice')
        if fault=='unknown_status':h.facts[72]['status']='UNKNOWN'
        if fault.startswith('retained_'):
            child=next(o for o in engine._native_orders.values() if o.get('protection_parent_order_id'))
            key={'retained_parent':'protection_parent_order_id','retained_mode':'mode','retained_decision':'decision_id'}[fault]
            child[key]='CHANGED'
        assert not h.core.run_once();capsys.readouterr()
        assert engine._native_quarantined and life.filled_qty==1 and life.exited_qty==0
        assert h.manager.snapshot_positions()['JPM'].quantity==1 and len(h.core.trade_registry.snapshot())==1
        assert engine.capital_authority.total_used_exposure==life.avg_fill_price
        assert len(engine.position_records)==1 and len(h.sent_native)==len(h.stop_requests)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('evidence',['missing','unrelated','Submitted','PendingSubmit','Cancelled','Inactive'])
def test_stop_zero_or_missing_is_not_an_exit_and_late_fill_is_accounted(reassessment,monkeypatch,
        tmp_path,capsys,no_external_activity,evidence):
    h,request,life=filled_standalone(reassessment,monkeypatch,tmp_path,capsys,'VWAP_RECLAIM_CONTINUATION')
    try:
        engine=h.core.execution_engine
        if evidence=='unrelated':h.facts[999]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.22)
        elif evidence!='missing':h.facts[72]=dict(status=evidence,filled=0,remaining=1)
        h.life.clock.current+=timedelta(seconds=1)
        h.core.run_once();capsys.readouterr()
        assert life.filled_qty==1 and life.exited_qty==0
        assert h.manager.snapshot_positions()['JPM'].quantity==1
        assert engine.capital_authority.total_used_exposure==life.avg_fill_price
        assert len(h.sent_native)==len(h.stop_requests)==1
        external_stop_facts(h,life)
        assert h.core.run_once();capsys.readouterr()
        assert life.filled_qty==0 and life.exited_qty==1
        assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
        assert engine.capital_authority.total_used_exposure==0
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('stage',['after_accounting','after_processor'])
def test_selected_stop_interruption_quarantines_completed_effects_and_blocks_replay(reassessment,
        monkeypatch,tmp_path,capsys,no_external_activity,stage):
    h,request,life=filled_standalone(reassessment,monkeypatch,tmp_path,capsys,'VWAP_RECLAIM_CONTINUATION')
    try:
        engine=h.core.execution_engine;external_stop_facts(h,life)
        name='_record_fill_and_position' if stage=='after_accounting' else None
        def fail():raise RuntimeError('synthetic stop-fill interruption')
        if name:
            original=getattr(engine,name)
            def interrupted(*a,**kw):original(*a,**kw);fail()
            monkeypatch.setattr(engine,name,interrupted)
            process=lambda r:h.core._apply_execution_results_to_trade_management([r])
        else:
            def process(r):h.core._apply_execution_results_to_trade_management([r]);fail()
        with pytest.raises(RuntimeError,match='synthetic stop-fill interruption'):
            engine.collect_relationship_updates(result_processor=process)
        child=next(o for o in engine._native_orders.values() if o.get('protection_parent_order_id'))
        assert child['cached_update_in_progress'] and child['quarantine']
        assert engine._native_quarantined and engine._failsafe_block_new_entries
        assert life.filled_qty==0 and life.exited_qty==1 and engine.capital_authority.total_used_exposure==0
        assert not h.core.trade_registry.snapshot()
        assert ('JPM' in h.manager.snapshot_positions()) is (stage=='after_accounting')
        counts=(life.exited_qty,life.realized_pnl,len(engine.position_records),len(h.sent_native),len(h.stop_requests))
        with pytest.raises(RuntimeError):engine.collect_relationship_updates(result_processor=process)
        assert counts==(life.exited_qty,life.realized_pnl,len(engine.position_records),len(h.sent_native),len(h.stop_requests))
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_stop_fill_does_not_clear_independent_broker_position_mismatch(reassessment,monkeypatch,
        tmp_path,capsys,no_external_activity):
    h,request,life=filled_standalone(reassessment,monkeypatch,tmp_path,capsys,'VWAP_RECLAIM_CONTINUATION')
    try:
        external_stop_facts(h,life)
        h.native_quantity[0]=1 # Independent external position facts contradict the completed fill.
        h.core.run_once();capsys.readouterr()
        assert life.filled_qty==0 and not h.manager.snapshot_positions()
        assert h.truth[-1][1].block_new_entries and h.truth[-1][0].mismatches
        assert len(h.sent_native)==len(h.stop_requests)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('protection_fault',['none','missing','wrong_quantity','lost_on_repeat','missing_update'])
def test_native_stop_partial_then_terminal_cumulative_core_accounting(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,protection_fault):
    from test_joined_core_pmh_readonly import pmh_joined
    monkeypatch.setenv('TRADING_DEFAULT_CAPITAL','400') # Isolated existing synthetic sizing scope.
    def small_joined(*args,**kwargs):
        # Existing approved SMALL sizing, scoped to synthetic facts; MICRO defaults stay one share.
        kwargs['runtime_options']['config_overrides'].update(RISK_PROFILE='SMALL',RISK_MAX_POSITION_SIZE=2,ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=8)
        return pmh_joined(*args,**kwargs)
    def small_paper(*args,**kwargs):return paper_pmh(*args,joined_factory=small_joined,**kwargs)
    h=late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=small_paper,
        fill_price=10.53,expected_stop_quantity=None)
    try:
        assert h.core.run_once();capsys.readouterr()
        h.life.clock.current+=timedelta(seconds=11)
        assert h.core.run_once();capsys.readouterr()
        request=h.sent_native[0];qty=request.quantity
        d=h.evaluated[0][2]
        assert qty>1,(d.evaluated_limits.get('profile'),d.evaluated_limits.get('max_position_size'),d.evaluated_limits.get('available_capital'),getattr(d.strategy_allocation_decision,'approved_quantity',None),getattr(d.capital_decision,'approved_quantity',None))
        h.facts[71]=dict(status='Filled',filled=qty,remaining=0,avgFillPrice=10.53)
        h.native_quantity[0]=qty;h.native_open_orders.clear()
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
        engine=h.core.execution_engine;life=engine.post_fill_lifecycle.get_trade(request.client_order_id)
        assert life.filled_qty==qty and life.stop.quantity==qty
        price=external_stop_facts(h,life,status='Submitted',filled=1,remaining=qty-1)
        if protection_fault=='missing':h.native_open_orders.clear()
        if protection_fault=='wrong_quantity':h.native_open_orders[0].order.totalQuantity=qty-1
        cycle=h.core.run_once();capsys.readouterr()
        assert life.filled_qty==qty-1 and life.exited_qty==1
        assert h.manager.snapshot_positions()['JPM'].quantity==qty-1
        assert h.core.trade_registry.snapshot()[0].quantity==qty-1
        assert engine.capital_authority.total_used_exposure==pytest.approx((qty-1)*10.53)
        assert life.realized_pnl==pytest.approx(price-10.53)
        if protection_fault in {'missing','wrong_quantity'}:
            assert not cycle and engine._native_quarantined
            before=(life.exited_qty,life.realized_pnl,engine.capital_authority.total_used_exposure)
            h.life.clock.current+=timedelta(seconds=1)
            assert not h.core.run_once();capsys.readouterr()
            assert before==(life.exited_qty,life.realized_pnl,engine.capital_authority.total_used_exposure)
            assert len(h.sent_native)==len(h.stop_requests)==1
            return
        assert cycle and h.truth[-1][1].healthy
        assert engine._confirmed_stop_quantity(symbol='JPM',life=life,
            orders=list(engine._provider.get_open_orders()),stop_filled=1)==qty
        if protection_fault in {'lost_on_repeat','missing_update'}:
            h.native_open_orders.clear()
            if protection_fault=='missing_update':h.facts.pop(72)
            h.life.clock.current+=timedelta(seconds=1)
            assert not h.core.run_once();capsys.readouterr()
            assert engine._native_quarantined and life.exited_qty==1
            assert len(h.sent_native)==len(h.stop_requests)==1
            return
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
        assert life.exited_qty==1
        # Cumulative average encodes a distinct later execution price; normalization must apply only delta.
        final_price=price-.02;average=(price+(qty-1)*final_price)/qty
        h.facts[72].update(status='Filled',filled=qty,remaining=0,avgFillPrice=average)
        h.native_quantity[0]=0;h.native_open_orders.clear()
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
        assert life.filled_qty==0 and life.exited_qty==qty
        assert life.realized_pnl==pytest.approx(price+(qty-1)*final_price-qty*10.53)
        assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
        assert engine.capital_authority.total_used_exposure==pytest.approx(0)
        assert len(h.sent_native)==len(h.stop_requests)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('owner',['manager','registry','lifecycle'])
def test_selected_stop_conflicting_owned_quantity_rejects_before_accounting(reassessment,monkeypatch,
        tmp_path,capsys,no_external_activity,owner):
    h,request,life=filled_standalone(reassessment,monkeypatch,tmp_path,capsys,'VWAP_RECLAIM_CONTINUATION')
    try:
        engine=h.core.execution_engine;external_stop_facts(h,life)
        # Deliberately corrupt one projection to exercise ownership rejection, not to manufacture a passing flat.
        if owner=='manager':h.manager.snapshot_positions()['JPM'].quantity=0
        elif owner=='registry':h.core.trade_registry.snapshot()[0].quantity=0
        else:life.filled_qty=0
        assert not h.core.run_once();capsys.readouterr()
        assert engine._native_quarantined and life.exited_qty==0
        assert len(engine.position_records)==1 and engine.capital_authority.total_used_exposure==10.34
        assert len(h.sent_native)==len(h.stop_requests)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


def late_pullback_variant(reassessment,monkeypatch,tmp_path,*,family):
    from test_joined_core_pmh_readonly import pullback_variant_joined
    def joined_factory(*args,**kwargs):return pullback_variant_joined(*args,family=family,**kwargs)
    def paper_variant(*args,**kwargs):return paper_pmh(*args,joined_factory=joined_factory,**kwargs)
    fill,stop=(10.48,10.08) if family=='THREE_BAR_PULLBACK' else (10.62,10.35)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_variant,fill_price=fill,stop_price=stop)


@pytest.mark.parametrize('family',['THREE_BAR_PULLBACK','SECOND_PULLBACK'])
def test_pullback_variant_native_paper_preserves_confidence_admission_veto(reassessment,monkeypatch,
        tmp_path,capsys,no_external_activity,family):
    from src.strategies.ross_momentum.decision_policy import validate_entry_contract
    from src.strategies.ross_momentum.strategy_policy import (
        THREE_BAR_PULLBACK_DESCRIPTIVE_OBJECTIVE,SECOND_PULLBACK_DESCRIPTIVE_OBJECTIVE)
    h=late_pullback_variant(reassessment,monkeypatch,tmp_path,family=family)
    try:
        assert h.core.run_once();capsys.readouterr()
        h.life.clock.current+=timedelta(seconds=11)
        assert h.core.run_once();capsys.readouterr()
        source,results=h.registry_batches[-1]
        native=next(r for r in results if r.setup_family_id==family)
        objective=THREE_BAR_PULLBACK_DESCRIPTIVE_OBJECTIVE if family=='THREE_BAR_PULLBACK' else SECOND_PULLBACK_DESCRIPTIVE_OBJECTIVE
        assert len(results)==33 and native.detected and native.confidence==.58
        assert native.target_suggestion==objective and validate_entry_contract(native)[0]
        assert h.pullback_triggers[-1][2]['trigger_ready_now']
        terminal=h.strategy.last_symbol_terminal_outcomes['JPM']
        assert terminal['reason']=='CONFIDENCE_BELOW_ORDERABLE_THRESHOLD'
        assert h.sent_native==h.stop_requests==h.artifacts==h.evaluated==[]
        engine=h.core.execution_engine
        assert not engine.position_records and not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
        assert not engine.capital_authority.active_reservations and not engine.strategy_allocation_authority.active_reservations
        assert engine.capital_authority.total_used_exposure==engine.capital_authority.total_reserved_capital==0
    finally:teardown_unsent_fixture(h,no_external_activity)


def late_cup(reassessment,monkeypatch,tmp_path,*,clock_time=None):
    from test_joined_core_pmh_readonly import cup_joined
    def selected_cup(*args,**kwargs):
        if clock_time is not None:kwargs['clock_time']=clock_time
        return cup_joined(*args,**kwargs)
    def paper_cup(*args,**kwargs):return paper_pmh(*args,joined_factory=selected_cup,**kwargs)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_cup,fill_price=10.55,stop_price=10.3)


def acknowledge_cup(h,capsys):
    return acknowledge_selected(h,capsys,family='CUP_HANDLE',entry=10.54,stop=10.3,invalidation=10.3,
        triggers=h.cup_triggers)


def test_native_cup_paper_later_fill_initial_stop_and_confirmed_flat(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity):
    from src.strategies.ross_momentum.strategy_policy import CUP_HANDLE_DESCRIPTIVE_OBJECTIVE
    h=late_cup(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge_cup(h,capsys)
        life=confirm_selected_fill(h,request,capsys,family='CUP_HANDLE',fill_price=10.55,stop_price=10.3)
        assert request.target_model==life.target_model==CUP_HANDLE_DESCRIPTIVE_OBJECTIVE
        assert request.take_profit_price is life.selected_target_price is None
        price=external_stop_facts(h,life)
        assert h.core.run_once();capsys.readouterr()
        engine=h.core.execution_engine
        assert life.exited_qty==1 and life.filled_qty==0 and life.realized_pnl==pytest.approx(price-10.55)
        assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
        assert engine.capital_authority.total_used_exposure==0
        for _ in range(3):
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
            assert life.exited_qty==1 and life.filled_qty==0
            assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
            assert len(engine.position_records)==2 and len(h.sent_native)==len(h.stop_requests)==1
            assert engine.capital_authority.total_used_exposure==engine.capital_authority.total_reserved_capital==0
        assert h.truth[-1][1].healthy and not h.truth[-1][1].block_new_entries
    finally:teardown_unsent_fixture(h,no_external_activity)


def late_opening_drive(reassessment,monkeypatch,tmp_path):
    from test_joined_core_pmh_readonly import opening_drive_joined
    def paper_drive(*args,**kwargs):return paper_pmh(*args,joined_factory=opening_drive_joined,**kwargs)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_drive,fill_price=10.62,stop_price=10.47)


def acknowledge_opening_drive(h,capsys):
    from src.strategies.ross_momentum.strategy_policy import OPENING_DRIVE_DESCRIPTIVE_OBJECTIVE
    request=acknowledge_selected(h,capsys,family='OPENING_DRIVE',entry=10.60,stop=10.47,invalidation=10.47,
        triggers=h.opening_drive_triggers)
    assert request.target_model==OPENING_DRIVE_DESCRIPTIVE_OBJECTIVE and request.take_profit_price is None
    return request


def late_ema_pullback(reassessment,monkeypatch,tmp_path):
    from test_joined_core_pmh_readonly import indicator_pullback_joined
    def paper_ema(*args,**kwargs):return paper_pmh(*args,joined_factory=indicator_pullback_joined,**kwargs)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_ema,fill_price=10.53,stop_price=10.29)


def acknowledge_ema_pullback(h,capsys):
    from src.strategies.ross_momentum.strategy_policy import EMA_PULLBACK_DESCRIPTIVE_OBJECTIVE
    request=acknowledge_selected(h,capsys,family='EMA_PULLBACK',entry=10.5,stop=10.29,invalidation=10.29,
        triggers=h.indicator_triggers)
    assert request.target_model==EMA_PULLBACK_DESCRIPTIVE_OBJECTIVE and request.take_profit_price is None
    return request


def late_vwap_pullback(reassessment,monkeypatch,tmp_path):
    from test_joined_core_pmh_readonly import vwap_pullback_joined
    def paper_vwap(*args,**kwargs):return paper_pmh(*args,joined_factory=vwap_pullback_joined,**kwargs)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_vwap,fill_price=10.8,stop_price=10.23)


def acknowledge_vwap_pullback(h,capsys):
    from src.strategies.ross_momentum.strategy_policy import VWAP_PULLBACK_DESCRIPTIVE_OBJECTIVE
    request=acknowledge_selected(h,capsys,family='VWAP_PULLBACK',entry=10.76,stop=10.23,invalidation=10.23,
        triggers=h.indicator_triggers)
    assert request.target_model==VWAP_PULLBACK_DESCRIPTIVE_OBJECTIVE and request.take_profit_price is None
    return request


def late_stair_step(reassessment,monkeypatch,tmp_path):
    from test_joined_core_pmh_readonly import stair_step_joined
    def paper_stair(*args,**kwargs):return paper_pmh(*args,joined_factory=stair_step_joined,**kwargs)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_stair,fill_price=10.68,stop_price=10.34)


def acknowledge_stair_step(h,capsys):
    from src.strategies.ross_momentum.strategy_policy import TREND_CONTINUATION_STAIR_STEP_DESCRIPTIVE_OBJECTIVE
    request=acknowledge_selected(h,capsys,family='TREND_CONTINUATION_STAIR_STEP',entry=10.64,stop=10.34,invalidation=10.24,
        triggers=h.indicator_triggers)
    assert request.target_model==TREND_CONTINUATION_STAIR_STEP_DESCRIPTIVE_OBJECTIVE and request.take_profit_price is None
    return request



@pytest.mark.parametrize('family',['RANGE_BREAK','ASCENDING_TRIANGLE','PENNANT'])
def test_native_measured_structural_paper_retains_confidence_veto(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,family):
    from test_joined_core_pmh_readonly import range_joined,triangle_joined,pennant_joined
    factory={'RANGE_BREAK':range_joined,'ASCENDING_TRIANGLE':triangle_joined,'PENNANT':pennant_joined}[family]
    def paper_range(*args,**kwargs):return paper_pmh(*args,joined_factory=factory,**kwargs)
    h=late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_range,
        fill_price=10.64 if family=='PENNANT' else 10.49,
        stop_price={'RANGE_BREAK':10.04,'ASCENDING_TRIANGLE':10.20,'PENNANT':10.40}[family])
    try:
        assert h.core.run_once();capsys.readouterr()
        h.life.clock.current+=timedelta(seconds=11)
        assert h.core.run_once();capsys.readouterr()
        _,results=h.registry_batches[-1]
        own=next(r for r in results if r.setup_family_id==family)
        from src.strategies.ross_momentum.decision_policy import validate_entry_contract
        assert len(results)==33 and own.detected and own.confidence==.58
        assert validate_entry_contract(own)==(True,'ok')
        assert h.range_triggers and h.range_triggers[-1][2]['trigger_ready_now']
        assert h.strategy.last_symbol_terminal_outcomes['JPM']['reason']=='CONFIDENCE_BELOW_ORDERABLE_THRESHOLD'
        assert h.sent_native==h.stop_requests==h.artifacts==h.evaluated==[]
        assert not h.core.execution_engine.position_records and not h.manager.snapshot_positions()
        assert not h.core.trade_registry.snapshot()
        assert h.core.execution_engine.capital_authority.total_used_exposure==h.core.execution_engine.capital_authority.total_reserved_capital==0
        assert not h.core.execution_engine.capital_authority.active_reservations
        assert not h.core.execution_engine.strategy_allocation_authority.active_reservations
    finally:teardown_unsent_fixture(h,no_external_activity)


def coherent_pmh_failure_entry(*args,**kwargs):
    from test_joined_core_pmh_readonly import pmh_joined, _coherent_profile_streams
    h=pmh_joined(*args,**kwargs)
    _coherent_profile_streams(h,[(10.31,10.31,10.31,10.31,50)]*4+[
        (10.31,10.32,10.30,10.30,100),(10.30,10.55,10.30,10.53,1200)])
    return h


def append_external_management_bar(h,timeframe,bar):
    from src.strategies.common.candles.candle_types import Candle
    h.streams[timeframe].append(bar)
    if timeframe=='10s':
        for target,period in (('1m',60),('5m',300)):
            by_start={}
            for item in h.streams['10s']:
                key=item.timestamp.replace(second=(item.timestamp.second//period)*period,microsecond=0) if period==60 else item.timestamp.replace(minute=(item.timestamp.minute//5)*5,second=0,microsecond=0)
                if key>h.streams[target][-1].timestamp:
                    by_start.setdefault(key,[]).append(item)
            for key,items in sorted(by_start.items()):
                h.streams[target].append(Candle(items[0].open,max(x.high for x in items),min(x.low for x in items),
                    items[-1].close,sum(x.volume for x in items),timestamp=key))


def pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,*,fault='none',conversion='confirmed',prepared=None,clock_step=1):
    from dataclasses import replace
    from src.ibkr.market_data_client import HistoricalDataResult
    from src.strategies.common.candles.candle_types import Candle
    if prepared is None:
        def coherent_paper(*args,**kwargs):return paper_pmh(*args,joined_factory=coherent_pmh_failure_entry,**kwargs)
        h=late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=coherent_paper,fill_price=10.53)
        request=acknowledge(h,capsys)
        life=confirm_selected_fill(h,request,capsys,family='PREMARKET_HIGH_BREAK',fill_price=10.53,stop_price=request.stop_loss_price)
    else:h,request,life=prepared
    engine=h.core.execution_engine;owner=engine._native_orders[request.client_order_id]
    h.failure_conversions=[];h.failure_bars=[];h.failure_history_reads=[]
    def history(*args,**kw):
        h.failure_history_reads.append(deepcopy(kw))
        return HistoricalDataResult('UNVERIFIED' if fault=='partial_history' else 'COMPLETE_BARS',tuple(h.failure_bars),fault!='partial_history')
    monkeypatch.setattr(h.core.connection_manager,'_client',NS(intraday_bars_from_history=history))
    def convert(**binding):
        assert binding.pop('expected_client') is h.native_client
        assert binding.pop('scope_as_of') == engine._native_scope[2]
        guard=binding.pop('authorization_guard',None)
        assert binding==dict(broker_order_id='72',parent_order_id='71',symbol='JPM',con_id=123,
            total_quantity=life.intended_qty,trade_id=life.trade_id,stop_price=life.selected_stop_price)
        h.life.clock.current+=timedelta(seconds=getattr(h,'profit_precommit_delay',0))
        if guard is not None and not guard(h.life.clock.current):
            raise RuntimeError('synthetic final authorization expired')
        h.failure_conversions.append(deepcopy(binding))
        assert len(h.failure_conversions)==1
        if conversion=='stop_race':
            external_stop_facts(h,life)
            raise TimeoutError('stop fill arrived before amendment')
        if conversion!='rejected':
            native=next(row for row in h.native_open_orders if row.orderId==72)
            native.order.orderType='MKT';native.order.auxPrice=0.
        if conversion=='unknown':
            h.native_open_orders[0].orderState.status='PendingSubmit'
        if conversion in {'uncertain','rejected'}:
            raise TimeoutError('synthetic lost reply')
        return {'status':'Submitted'}
    monkeypatch.setattr(engine._provider.broker,'convert_selected_stop_to_market',convert,raising=False)
    stamp=h.life.clock.current.replace(microsecond=0)
    # Real provider bars align to their retained execution grid. The first
    # eligible bar starts after the last accounted fill, never straddles it.
    offset=(-int(stamp.timestamp())) % {'10s':10,'1m':60}[request.setup_metadata['execution_stream']['execution_trigger_timeframe']]
    stamp+=timedelta(seconds=offset)
    # Let the bar complete through real bounded cycles, preserving the existing
    # account-scope freshness law rather than jumping past its deadline.
    from src.strategies.ross_momentum.policy.pattern_input_policy import PatternInputPolicy
    timeframe=request.setup_metadata['execution_stream']['execution_trigger_timeframe']
    seconds={'10s':10,'1m':60}[timeframe]
    wait_cycles=offset+((PatternInputPolicy.from_policy_v2().candle_freshness_seconds[timeframe]+seconds+2) if fault=='stale' else seconds+2)
    assert 1<=clock_step<=10 # Below the existing15s scope freshness limit; never relax authority.
    remaining=wait_cycles
    while remaining:
        step=min(clock_step,remaining)
        h.life.clock.current+=timedelta(seconds=step)
        assert h.core.run_once();capsys.readouterr()
        remaining-=step
    standalone=request.setup_family_id in SELECTED_FAILURE_FAMILIES
    level=request.setup_metadata['trigger_level']
    close=round((level+request.stop_loss_price)/2,2) if standalone else 10.295
    bid,ask=(round(close-.01,2),round(close+.01,2)) if standalone else (10.29,10.30)
    if fault=='equality':close=level
    if fault=='wick':close=level+.01
    bar=Candle(level+.01,level+.02,bid,close,500,timestamp=stamp)
    h.failure_bars=[bar]
    if fault in {'none','equality','wick','stale'}:
        # Same external tape for registry and management; append only new bars.
        previous=h.streams[timeframe][-1]
        cursor=previous.timestamp+timedelta(seconds=seconds)
        while cursor<stamp:
            h.streams[timeframe].append(Candle(previous.close,max(previous.close,level+.02),level,level+.01,200,timestamp=cursor) if standalone else Candle(previous.close,max(previous.close,10.54),min(previous.close,10.30),10.31,200,timestamp=cursor))
            previous=h.streams[timeframe][-1];cursor+=timedelta(seconds=seconds)
        append_external_management_bar(h,timeframe,bar)
        h.failure_bars=list(h.streams[timeframe][-10:])
    if fault=='forming':h.failure_bars=[replace(bar,timestamp=h.life.clock.current-timedelta(seconds=5))]
    if fault=='straddling':h.failure_bars=[replace(bar,timestamp=__import__('datetime').datetime.fromisoformat(owner['last_accounted_entry_fill_at'])-timedelta(seconds=1))]
    if fault=='future':h.failure_bars=[replace(bar,timestamp=h.life.clock.current+timedelta(seconds=1))]
    if fault=='missing':h.failure_bars=[]
    if fault=='invalid':h.failure_bars=[replace(bar,low=float('nan'))]
    if fault=='missing_bar_timestamp':h.failure_bars=[replace(bar,timestamp=None)]
    if fault=='naive_timestamp':h.failure_bars=[replace(bar,timestamp=stamp.replace(tzinfo=None))]
    # Independent contemporaneous quote facts. SELL fill10.29 is a cent tick
    # above selected stop10.2897; completed management close10.295 is mid-spread.
    for row in h.rows.values():
        row.update(last_price=close,bid=bid,ask=ask,spread_pct=100*(ask-bid)/close)
    original_snapshots=h.core.market_data_snapshot_manager.batch_snapshots
    def quotes(symbols):
        values,errors=original_snapshots(symbols)
        return {key:replace(value,last=close,bid=bid,ask=ask) for key,value in values.items()},errors
    h.core.market_data_snapshot_manager.batch_snapshots=quotes
    h.failure_exit_price=bid
    h.failure_owner=owner
    return h,request,life


def test_pmh_completed_failure_actual_core_owned_exit(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine
    assert h.core.run_once()
    out=capsys.readouterr().out
    assert len(h.failure_conversions)==1,out
    assert h.failure_owner['pmh_failure_exit']['status']=='MKT'
    assert life.selected_stop_price==request.stop_loss_price and life.target is None
    assert engine.capital_authority.total_used_exposure==10.53
    assert not engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert life.selected_exit_pending and life.filled_qty==1
    h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.29,
        symbol='JPM',side='SELL',orderId=72,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=0;h.native_open_orders.clear()
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert len(h.failure_conversions)==1 and len(h.sent_native)==1 and len(h.stop_requests)==1
    assert life.filled_qty==0 and life.exited_qty==1
    assert engine.capital_authority.total_used_exposure==0
    assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert life.realized_pnl==pytest.approx(10.29-10.53)


@pytest.mark.parametrize('fault',['equality','wick','forming','straddling','future','stale','missing','invalid','partial_history','missing_bar_timestamp','naive_timestamp'])
def test_pmh_completed_failure_actual_core_boundary_holds(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,fault=fault)
    assert h.core.run_once();capsys.readouterr()
    assert h.failure_conversions==[] and not h.failure_owner.get('pmh_failure_exit')
    assert life.filled_qty==1 and life.stop.trigger_price==request.stop_loss_price
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']


@pytest.mark.parametrize('conversion',['uncertain','rejected','stop_race'])
def test_pmh_failure_uncertain_reply_and_stop_race_no_retry(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,conversion):
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,conversion=conversion)
    assert h.core.run_once();capsys.readouterr()
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert len(h.failure_conversions)==1 and len(h.sent_native)==len(h.stop_requests)==1
    if conversion=='stop_race':
        assert life.filled_qty==0 and life.exited_qty==1
        assert h.core.execution_engine.capital_authority.total_used_exposure==0
    else:
        assert life.filled_qty==1 and life.exited_qty==0
        assert h.failure_owner['pmh_failure_exit']['status']==('MKT' if conversion=='uncertain' else 'STP')
        assert h.core.execution_engine.capital_authority.total_used_exposure==10.53


def small_pmh_owned(reassessment,monkeypatch,tmp_path,capsys,*,partial=False):
    from test_joined_core_pmh_readonly import pmh_joined
    monkeypatch.setenv('TRADING_DEFAULT_CAPITAL','400') # Existing isolated SMALL synthetic scope.
    def small_joined(*args,**kwargs):
        kwargs['runtime_options']['config_overrides'].update(RISK_PROFILE='SMALL',RISK_MAX_POSITION_SIZE=2,ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=8)
        return coherent_pmh_failure_entry(*args,**kwargs)
    def small_paper(*args,**kwargs):return paper_pmh(*args,joined_factory=small_joined,**kwargs)
    h=late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=small_paper,
        fill_price=10.53,expected_stop_quantity=None)
    assert h.core.run_once();capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();capsys.readouterr()
    request=h.sent_native[0];qty=request.quantity
    assert qty==2
    fill=1 if partial else qty
    h.facts[71]=dict(status='Submitted' if partial else 'Filled',filled=fill,remaining=qty-fill,avgFillPrice=10.53)
    h.native_quantity[0]=fill;h.native_open_orders.clear()
    h.life.clock.current+=timedelta(seconds=1)
    assert h.core.run_once();capsys.readouterr()
    life=h.core.execution_engine.post_fill_lifecycle.get_trade(request.client_order_id)
    assert life.filled_qty==fill and life.stop.quantity==fill
    return h,request,life


def test_pmh_failure_partial_entry_stays_protected_outside_enrollment(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    prepared=small_pmh_owned(reassessment,monkeypatch,tmp_path,capsys,partial=True)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    assert h.core.run_once();capsys.readouterr()
    assert not h.failure_owner['terminal'] and h.failure_owner['filled']==1
    assert h.failure_conversions==[] and not h.failure_owner.get('pmh_failure_exit')
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert h.manager.snapshot_positions()['JPM'].quantity==1 and life.stop.quantity==1


@pytest.mark.parametrize('terminal_average',[10.30,10.295])
def test_pmh_failure_partial_exit_owned_remainder_and_accounting_once(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,terminal_average):
    prepared=small_pmh_owned(reassessment,monkeypatch,tmp_path,capsys)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    engine=h.core.execution_engine
    assert h.core.run_once();capsys.readouterr()
    h.facts[72]=dict(status='Submitted',filled=1,remaining=1,avgFillPrice=10.29,
        symbol='JPM',side='SELL',orderId=72,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=1
    for _ in range(2):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==1 and life.exited_qty==1
    assert h.manager.snapshot_positions()['JPM'].quantity==1
    assert not h.manager.snapshot_positions()['JPM'].partial_taken
    assert h.manager.snapshot_positions()['JPM'].stop_loss_price==request.stop_loss_price
    assert h.core.trade_registry.snapshot()[0].quantity==1
    assert engine.capital_authority.total_used_exposure==pytest.approx(10.53)
    assert h.native_open_orders[0].order.orderType=='MKT' and h.native_open_orders[0].order.totalQuantity==2
    assert life.stop.trigger_price==request.stop_loss_price and not life.trailing_active
    h.facts[72].update(status='Filled',filled=2,remaining=0,avgFillPrice=terminal_average)
    h.native_quantity[0]=0;h.native_open_orders.clear()
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==0 and life.exited_qty==2
    assert life.realized_pnl==pytest.approx(2*terminal_average-2*10.53)
    assert engine.capital_authority.total_used_exposure==0
    assert len(h.failure_conversions)==1 and len(h.sent_native)==len(h.stop_requests)==1


@pytest.mark.parametrize('fault',['security','broker_larger','partial_truth','wrong_reference','wrong_parent','wrong_total','pending_order','pending_cancel'])
def test_pmh_failure_actual_core_truth_and_order_binding_veto(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys)
    if fault=='security':h.native_client.position_snapshot=lambda:BrokerPositionResult((NS(symbol='JPM',position=1,con_id=456,avgCost=10.53,account='SYNTHETIC_TEST'),),'COMPLETE','SYNTHETIC_TEST',h.life.clock.now(timezone.utc))
    if fault=='broker_larger':h.native_quantity[0]=2
    if fault=='partial_truth':h.native_client.position_snapshot=lambda:BrokerPositionResult((),'PARTIAL','SYNTHETIC_TEST',h.life.clock.now(timezone.utc))
    if fault=='wrong_reference':h.native_open_orders[0].order.orderRef='PROTECT|UNRELATED'
    if fault=='wrong_parent':h.native_open_orders[0].order.parentId=999
    if fault=='wrong_total':h.native_open_orders[0].order.totalQuantity=2
    if fault=='pending_order':
        other=deepcopy(h.native_open_orders[0]);other.orderId=73;other.order.orderRef='OTHER';h.native_open_orders.append(other)
    if fault=='pending_cancel':h.native_open_orders[0].orderState.status='PendingCancel'
    h.core.run_once();capsys.readouterr()
    assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit')
    assert life.filled_qty==1 and life.stop.trigger_price==request.stop_loss_price
    assert len(h.sent_native)==len(h.stop_requests)==1


def test_pmh_failure_confirmed_stop_fill_precedes_discretionary_evaluation(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys)
    external_stop_facts(h,life)
    assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==0 and life.exited_qty==1
    assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit')
    assert h.core.execution_engine.capital_authority.total_used_exposure==0


@pytest.mark.parametrize('stage',['after_accounting','after_projection'])
def test_pmh_failure_accounting_interruption_quarantines_without_replay(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,stage):
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine
    assert h.core.run_once();capsys.readouterr()
    h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.29,
        symbol='JPM',side='SELL',orderId=72,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=0;h.native_open_orders.clear()
    def fail():raise RuntimeError('synthetic PMH exit interruption')
    process=lambda r:h.core._apply_execution_results_to_trade_management([r])
    if stage=='after_accounting':
        original=engine._record_fill_and_position
        def interrupted(*a,**kw):original(*a,**kw);fail()
        monkeypatch.setattr(engine,'_record_fill_and_position',interrupted)
    else:
        def process(r):h.core._apply_execution_results_to_trade_management([r]);fail()
    with pytest.raises(RuntimeError,match='synthetic PMH exit interruption'):
        engine.collect_relationship_updates(result_processor=process)
    child=next(o for o in engine._native_orders.values() if o.get('protection_parent_order_id'))
    assert child['cached_update_in_progress'] and child['quarantine'] and engine._native_quarantined
    assert life.filled_qty==0 and life.exited_qty==1 and engine.capital_authority.total_used_exposure==0
    before=(life.exited_qty,life.realized_pnl,len(engine.position_records),len(h.failure_conversions))
    with pytest.raises(RuntimeError):engine.collect_relationship_updates(result_processor=process)
    assert before==(life.exited_qty,life.realized_pnl,len(engine.position_records),len(h.failure_conversions))


def test_pmh_failure_rule_missing_timestamp_and_occurrence_unit_controls(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys)
    manager=h.manager;owner=h.failure_owner;plan=request.management_session_plan;now=h.life.clock.current
    evaluate=lambda value:manager.evaluate_pmh_completed_failure(value,h.failure_bars,observed_at=now,session_plan=plan)
    assert evaluate(owner)
    for key in ('last_accounted_entry_fill_at',):
        missing=deepcopy(owner);missing.pop(key)
        assert evaluate(missing) is None
    for value in (None,-1,True):
        invalid=deepcopy(owner);invalid['request']['setup_metadata']['canonical_result_index']=value
        assert evaluate(invalid) is None
    wrong=deepcopy(owner);wrong['request']['management_session_plan']='OTHER_PHASE'
    assert evaluate(wrong) is None
    assert manager.evaluate_pmh_completed_failure(owner,h.failure_bars,observed_at=now+timedelta(days=1),session_plan=plan) is None
    assert not h.failure_conversions


@pytest.mark.parametrize('fault',['none','con_id','parent','reference','quantity','kind','inactive','readonly','write_disabled','live','missing_client','authority_changed','scope_expired'])
def test_pmh_native_adapter_amendment_preserves_one_order_and_contract(monkeypatch,fault):
    from src.brokers import ibkr_live_broker as broker_module
    from src.config.runtime_config import RunMode
    contract=NS(symbol='JPM',conId=123,exchange='SMART',primaryExchange='NYSE',currency='USD',secType='STK')
    order=NS(action='SELL',totalQuantity=2,orderType='STP',auxPrice=10.28,
        parentId=71,orderRef='PROTECT|owned',tif='GTC',outsideRth=True,transmit=True)
    row=NS(orderId=72,contract=contract,order=order,orderState=NS(status='Submitted'))
    if fault=='con_id':contract.conId=456
    if fault=='parent':order.parentId=99
    if fault=='reference':order.orderRef='PROTECT|wrong'
    if fault=='quantity':order.totalQuantity=3
    if fault=='kind':order.orderType='MKT'
    if fault=='inactive':row.orderState.status='Cancelled'
    sent=[]
    authority_changed=[False]
    def inventory(**kwargs):
        assert kwargs == {"require_complete": True}
        if fault in {'authority_changed','scope_expired'}:authority_changed[0]=True
        return [row]
    client=NS(isConnected=lambda:True,openOrders=inventory,placeOrder=lambda *args:sent.append(deepcopy(args)))
    def forbidden(*a,**k):pytest.fail('Implicit connection forbidden')
    broker=object.__new__(broker_module.IbkrLiveBroker)
    broker.run_mode=RunMode.LIVE if fault=='live' else RunMode.PAPER
    broker.connection_manager=NS(existing_client=None if fault=='missing_client' else client,get_client=forbidden)
    for name,value in {'is_execution_enabled':True,'get_ibkr_kill_switch':False,
        'get_ibkr_readonly_enabled':fault=='readonly','get_ibkr_api_write_allowed':fault!='write_disabled',
        'get_ibkr_order_submission_enabled':True,'get_ibkr_order_translation_enabled':True}.items():
        monkeypatch.setattr(broker_module,name,lambda _value=value:_value)
    monkeypatch.setattr(broker_module,'get_ibkr_readonly_enabled',lambda:fault=='readonly' or (fault=='authority_changed' and authority_changed[0]))
    monkeypatch.setattr('src.config.runtime_config.get_ibkr_snapshot_max_age_seconds',
        lambda:0 if fault=='scope_expired' and authority_changed[0] else 10)
    call=lambda:broker.convert_selected_stop_to_market(broker_order_id='72',parent_order_id='71',
        symbol='JPM',con_id=123,total_quantity=2,trade_id='owned',stop_price=10.28,expected_client=client,scope_as_of=__import__('datetime').datetime.now(timezone.utc))
    if fault!='none':
        with pytest.raises(RuntimeError):call()
        assert sent==[]
    else:
        response=call()
        assert response['status']=='DISPATCHED_UNCONFIRMED' and len(sent)==1
        native_id,amended_contract,amended=sent[0]
        assert native_id==72 and vars(amended_contract)==vars(contract)
        assert amended.orderType=='MKT' and amended.totalQuantity==2 and amended.parentId==71
        assert amended.orderRef==order.orderRef and amended.tif==order.tif and amended.outsideRth
        assert order.orderType=='STP' and order.auxPrice==10.28 # Only copied native mutation payload changes.


def test_pmh_failure_later_qualifying_bar_no_elapsed_cutoff_and_phase_expiry(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from dataclasses import replace
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys)
    manager=h.manager;now=h.life.clock.current;owner=h.failure_owner
    first=replace(h.failure_bars[-1],close=10.31,timestamp=now)
    later=replace(h.failure_bars[-1],timestamp=now+timedelta(seconds=10))
    out=manager.evaluate_pmh_completed_failure(owner,[first,later],observed_at=now+timedelta(seconds=21),
        session_plan=request.management_session_plan)
    assert out and out['bar_start']==later.timestamp.isoformat()
    distant=replace(later,timestamp=now+timedelta(minutes=10))
    assert manager.evaluate_pmh_completed_failure(owner,[distant],observed_at=distant.timestamp+timedelta(seconds=11),
        session_plan=request.management_session_plan)
    h.core._expire_pmh_failure_enrollment(now,'OTHER_PHASE') # Transition observer is independent of exit gates.
    assert owner['pmh_management_expired'] and not h.failure_conversions
    assert h.core.run_once();capsys.readouterr() # Returning to prior label cannot resume enrollment.
    assert not h.failure_conversions and life.stop.trigger_price==request.stop_loss_price


def steady_pmh_external(reassessment,monkeypatch,tmp_path,*,acceptance_gap=False):
    from dataclasses import replace
    from test_joined_core_pmh_readonly import pmh_joined
    def steady_joined(*args,**kwargs):
        h=pmh_joined(*args,clock_time=(16,35,30),**kwargs)
        h.pre_reference_fault="missing" # Original accepted fixture omitted authoritative PRE facts.
        for row in h.rows.values():row['session']='RTH_MID'
        if acceptance_gap:
            # Genuine completed gap above PMH AND round10.50: Key's own
            # open-at/below-level rule fails; PMH's own prior-close break holds.
            h.streams['1m'][-1]=replace(h.streams['1m'][-1],open=10.51,low=10.51)
            recent=h.streams['1m'][-5:]
            h.streams['5m'][-1]=replace(h.streams['5m'][-1],open=recent[0].open,
                high=max(c.high for c in recent),low=min(c.low for c in recent),
                close=recent[-1].close,volume=sum(c.volume for c in recent))
        return h
    def steady_paper(*args,**kwargs):return paper_pmh(*args,joined_factory=steady_joined,**kwargs)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=steady_paper,fill_price=10.53)


def test_pmh_failure_steady_session_preserves_genuine_competing_key(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=steady_pmh_external(reassessment,monkeypatch,tmp_path)
    assert h.core.run_once();capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();capsys.readouterr()
    assert len(h.evaluated)==1 and h.evaluated[0][0].setup_family_id=='KEY_LEVEL_BREAK'
    assert len(h.strategy._pattern_registry.patterns)==33
    assert h.registry_batches[-1][0].execution_refinement_timeframe=='1m'
    from src.storage.serialization import to_jsonable
    from src.strategies.ross_momentum.strategy_policy import (
        selected_completed_failure_profile, BREAKOUT_STANDALONE_FAILURE_PROFILE, PMH_COMPLETED_BAR_FAILURE_PROFILE,
    )
    request=h.sent_native[0]
    assert request.setup_metadata==to_jsonable(h.evaluated[0][0].setup_metadata)
    profile=selected_completed_failure_profile(vars(request))
    assert profile==BREAKOUT_STANDALONE_FAILURE_PROFILE and profile!=PMH_COMPLETED_BAR_FAILURE_PROFILE
    owner=h.core.execution_engine._native_orders[request.client_order_id]
    assert not owner.get('last_accounted_entry_fill_at') and not owner.get('pmh_failure_exit')
    assert not h.manager.snapshot_positions() and not h.stop_requests # Ack only; no PMH or filled-Key enrollment.


def test_pmh_failure_steady_reference_gap_is_recorded_blocked_not_a_passing_pmh_route(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=steady_pmh_external(reassessment,monkeypatch,tmp_path,acceptance_gap=True)
    assert h.core.run_once();capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();capsys.readouterr()
    inputs,results=h.registry_batches[-1]
    assert len(results)==33 and inputs.execution_refinement_timeframe=='1m'
    pmh=next(r for r in results if r.setup_id=='P_PREMARKET_HIGH_BREAK')
    assert not pmh.detected and pmh.rejection_reason=='missing_premarket_reference'
    assert inputs.levels.premarket_reference['status']=='PARTIAL'
    assert inputs.levels.key_levels['PREMARKET_HIGH']>inputs.candles[-1].close # Legacy anchor preserved, not PMH authority.
    assert not h.sent_native and not h.evaluated # BLOCKED outcome, no 1m PMH filled/management proof.


def test_pmh_completed_failure_retained_one_minute_rule_component(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from dataclasses import replace
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys)
    # Format/period rule control only; not fabricated native1m entry evidence.
    owner=deepcopy(h.failure_owner)
    owner['request']['setup_metadata']['execution_stream']['execution_trigger_timeframe']='1m'
    bar=replace(h.failure_bars[-1],timestamp=h.life.clock.current)
    rule=lambda observed:h.manager.evaluate_pmh_completed_failure(owner,[bar],observed_at=observed,
        session_plan=request.management_session_plan)
    assert rule(bar.timestamp+timedelta(seconds=59)) is None
    assert rule(bar.timestamp+timedelta(seconds=60))['close']==bar.close
    assert not h.failure_conversions


@pytest.mark.parametrize('case',['complete','timeout','disconnect','overlap','changed_client'])
def test_pmh_native_amendment_requires_real_completed_order_stream(monkeypatch,case):
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    from src.brokers import ibkr_live_broker as module
    from src.config.runtime_config import RunMode
    client=IbkrClient('offline',0,999,5,'LIVE',True)
    connected=[True];queries=[];sent=[]
    monkeypatch.setattr(client,'isConnected',lambda:connected[0])
    contract=NS(symbol='JPM',conId=123)
    order=NS(action='SELL',totalQuantity=2,orderType='STP',auxPrice=10.28,parentId=71,orderRef='PROTECT|owned')
    broker=object.__new__(module.IbkrLiveBroker);broker.run_mode=RunMode.PAPER
    manager=NS(existing_client=client);broker.connection_manager=manager
    def query():
        queries.append(True)
        client.openOrder(72,contract,order,NS(status='Submitted'))
        if case=='overlap':client.openOrder(73,contract,order,NS(status='PendingSubmit'))
        if case!='timeout':client.openOrderEnd()
        if case=='disconnect':connected[0]=False
        if case=='changed_client':manager.existing_client=object()
    monkeypatch.setattr(client,'reqOpenOrders',query)
    # Bounded external event delivery: exercise the real query/completion owner
    # without sleeping, fabricating completion or replacing its classification.
    monkeypatch.setattr(client._open_orders_event,'wait',lambda timeout:client._open_orders_event.is_set())
    monkeypatch.setattr(client,'placeOrder',lambda *args:sent.append(args))
    for name,value in {'is_execution_enabled':True,'get_ibkr_kill_switch':False,
        'get_ibkr_readonly_enabled':False,'get_ibkr_api_write_allowed':True,
        'get_ibkr_order_submission_enabled':True,'get_ibkr_order_translation_enabled':True}.items():
        monkeypatch.setattr(module,name,lambda _value=value:_value)
    call=lambda:broker.convert_selected_stop_to_market(broker_order_id='72',parent_order_id='71',
        symbol='JPM',con_id=123,total_quantity=2,trade_id='owned',stop_price=10.28,expected_client=client,scope_as_of=__import__('datetime').datetime.now(timezone.utc))
    if case=='complete':
        call();assert len(sent)==1
    else:
        with pytest.raises(RuntimeError):call()
        assert not sent
        if case=='timeout':
            client.openOrderEnd() # A late uncorrelated end cannot certify a new query.
            with pytest.raises(RuntimeError,match='COMPLETION_UNRESOLVED'):call()
            assert len(queries)==1 and not sent


def test_pmh_phase_transition_expires_while_execution_is_gated(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys)
    original=h.life.clock.current;h.core.execution_enabled=False
    h.life.clock.current+=timedelta(hours=2)
    h.core.run_once();capsys.readouterr()
    assert h.failure_owner['pmh_management_expired'] and not h.failure_conversions
    h.life.clock.current=original;h.core.execution_enabled=True
    h.core.run_once();capsys.readouterr()
    assert not h.failure_conversions and life.filled_qty==1


def test_pmh_incomplete_post_amendment_inventory_cannot_certify_pending_close(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys)
    broker=h.core.execution_engine._provider.broker;original=broker.open_orders
    def inventory(**kw):
        if kw.get('require_complete') and h.failure_conversions:
            raise RuntimeError('synthetic incomplete post-amendment order stream')
        return original(**kw)
    monkeypatch.setattr(broker,'open_orders',inventory)
    assert not h.core.run_once() # Existing Core converts owner failure to a stopped cycle.
    capsys.readouterr()
    assert len(h.failure_conversions)==1 and h.failure_owner['pmh_failure_exit']['status']=='DISPATCH_UNCERTAIN'
    assert not h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert not h.core.run_once()
    capsys.readouterr()
    assert len(h.failure_conversions)==1 and life.filled_qty==1
    assert h.core.execution_engine._native_quarantined



def trusted_steady_pmh(reassessment,monkeypatch,tmp_path,*,two_shares=False,entry_position_limit=None,unit_stops=False):
    from dataclasses import replace
    from src.strategies.common.candles.candle_types import Candle
    from test_joined_core_pmh_readonly import pmh_joined
    if two_shares:monkeypatch.setenv('TRADING_DEFAULT_CAPITAL','400') # Existing isolated SMALL synthetic scope only.
    def joined_factory(*args,**kwargs):
        if two_shares:kwargs['runtime_options']['config_overrides'].update(RISK_PROFILE='SMALL',RISK_MAX_POSITION_SIZE=2,ROSS_SYNTHETIC_REQUESTED_BASE_SIZE=8)
        if unit_stops:kwargs['runtime_options']['config_overrides']['ROSS_SYNTHETIC_UNIT_STOPS']=True
        if entry_position_limit is not None:kwargs['runtime_options']['config_overrides']['RISK_MAX_OPEN_POSITIONS']=entry_position_limit
        h=pmh_joined(*args,clock_time=(16,35,30),**kwargs)
        h.trusted_pre_scenario=True
        for row in h.rows.values():row['session']='RTH_MID'
        # Genuine gap above round10.50; PMH own prior-close break still holds.
        h.streams['1m'][-1]=replace(h.streams['1m'][-1],open=10.51,low=10.51)
        fast=[];groups={}
        for bar in h.streams['1m']:
            fast.extend(Candle(bar.open,bar.open,bar.open,bar.open,bar.volume/10,
                timestamp=bar.timestamp+timedelta(seconds=10*i)) for i in range(5))
            fast.append(Candle(bar.open,bar.high,bar.low,bar.close,bar.volume/2,
                timestamp=bar.timestamp+timedelta(seconds=50)))
            key=bar.timestamp.replace(minute=(bar.timestamp.minute//5)*5,second=0)
            groups.setdefault(key,[]).append(bar)
        h.streams['10s']=fast
        h.streams['5m']=[Candle(items[0].open,max(x.high for x in items),min(x.low for x in items),
            items[-1].close,sum(x.volume for x in items),timestamp=key) for key,items in sorted(groups.items()) if len(items)==5]
        return h
    def paper_factory(*args,**kwargs):return paper_pmh(*args,joined_factory=joined_factory,**kwargs)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_factory,fill_price=10.53,
        expected_stop_quantity=None if two_shares else 1,unit_stops=unit_stops)


def test_trusted_premarket_one_minute_full_core_failure_to_flat(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=trusted_steady_pmh(reassessment,monkeypatch,tmp_path)
    request=acknowledge(h,capsys)
    intent,serialized,decision=h.evaluated[0]
    receipt=intent.setup_metadata['source_metadata']['premarket_reference']
    assert len(h.strategy._pattern_registry.patterns)==33
    assert receipt['status']=='COMPLETE_PRE' and receipt['completed_count']==receipt['expected_count']==330
    assert receipt['high']==10.3 and receipt['identity']==dict(symbol='JPM',con_id=123)
    assert intent.setup_metadata['execution_stream']['execution_trigger_timeframe']=='1m'
    assert receipt==request.setup_metadata['source_metadata']['premarket_reference']
    assert h.registry_batches[-1][0].levels.key_levels['PREMARKET_HIGH']==10.55 # Original legacy anchor unchanged.
    life=confirm_selected_fill(h,request,capsys,family='PREMARKET_HIGH_BREAK',fill_price=10.53,stop_price=request.stop_loss_price)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life))
    assert h.core.run_once();capsys.readouterr()
    assert len(h.failure_conversions)==1 and h.failure_owner['pmh_failure_exit']['status']=='MKT'
    assert all(x['timeframe']=='1m' for x in h.failure_history_reads)
    h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.29,
        symbol='JPM',side='SELL',orderId=72,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=0;h.native_open_orders.clear()
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert life.exited_qty==1 and life.filled_qty==0 and life.realized_pnl==pytest.approx(10.29-10.53)
    assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert h.core.execution_engine.capital_authority.total_used_exposure==0
    assert len(h.failure_conversions)==len(h.sent_native)==len(h.stop_requests)==1
    assert serialized==vars(intent) and request.take_profit_price is None
    assert life.selected_stop_price==10.2897
    assert sum(tf=='1m' and limit>400 for _,tf,limit in h.pre_history_queries)==1 # One PRE bootstrap; ordinary RTH owner unchanged.


@pytest.mark.parametrize('fault',['equality','wick','forming','straddling','missing','stale','future'])
def test_trusted_one_minute_pmh_core_failure_boundaries(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h=trusted_steady_pmh(reassessment,monkeypatch,tmp_path)
    request=acknowledge(h,capsys)
    life=confirm_selected_fill(h,request,capsys,family='PREMARKET_HIGH_BREAK',fill_price=10.53,stop_price=request.stop_loss_price)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life),fault=fault)
    assert h.core.run_once();capsys.readouterr()
    assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit')
    assert life.filled_qty==1 and life.selected_stop_price==request.stop_loss_price
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']



def terminal_one_minute_pmh(reassessment,monkeypatch,tmp_path,capsys,*,two_shares=False):
    h=trusted_steady_pmh(reassessment,monkeypatch,tmp_path,two_shares=two_shares)
    request=acknowledge(h,capsys,expected_quantity=2 if two_shares else 1)
    life=confirm_selected_fill(h,request,capsys,family='PREMARKET_HIGH_BREAK',fill_price=10.53,stop_price=request.stop_loss_price,expected_quantity=2 if two_shares else 1)
    return h,request,life


@pytest.mark.parametrize('conversion',['confirmed','uncertain','rejected','stop_race'])
def test_one_minute_pmh_uncertain_native_close_identity_no_retry(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,conversion):
    prepared=terminal_one_minute_pmh(reassessment,monkeypatch,tmp_path,capsys)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared,conversion=conversion,clock_step=10)
    assert h.core.run_once();capsys.readouterr()
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert len(h.failure_conversions)==len(h.sent_native)==len(h.stop_requests)==1
    if conversion=='stop_race':
        assert life.filled_qty==0 and life.exited_qty==1
        assert h.core.execution_engine.capital_authority.total_used_exposure==0
    else:
        expected='STP' if conversion=='rejected' else 'MKT'
        assert h.failure_owner['pmh_failure_exit']['status']==expected
        assert life.selected_exit_pending['native_order_id']=='72'
        assert life.filled_qty==1 and life.exited_qty==0
        protected=h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
        assert protected is (expected=='STP') # MKT is pending closure, not STP protection.
        assert life.selected_stop_price==request.stop_loss_price and request.take_profit_price is None


@pytest.mark.parametrize('average',[10.30,10.295])
def test_one_minute_pmh_partial_close_and_duplicate_callbacks_preserve_accounting(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,average):
    prepared=terminal_one_minute_pmh(reassessment,monkeypatch,tmp_path,capsys,two_shares=True)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared,clock_step=10)
    engine=h.core.execution_engine
    assert h.core.run_once();capsys.readouterr()
    h.facts[72]=dict(status='Submitted',filled=1,remaining=1,avgFillPrice=10.29,symbol='JPM',side='SELL',orderId=72,
        parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=1
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==life.exited_qty==1
    assert h.manager.snapshot_positions()['JPM'].quantity==h.core.trade_registry.snapshot()[0].quantity==1
    assert not h.manager.snapshot_positions()['JPM'].partial_taken and not life.trailing_active
    assert h.manager.snapshot_positions()['JPM'].stop_loss_price==life.selected_stop_price==request.stop_loss_price
    assert engine.capital_authority.total_used_exposure==pytest.approx(10.53)
    assert h.native_open_orders[0].order.orderType=='MKT' and h.native_open_orders[0].order.totalQuantity==2
    assert not engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    h.facts[72].update(status='Filled',filled=2,remaining=0,avgFillPrice=average)
    h.native_quantity[0]=0;h.native_open_orders.clear()
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==0 and life.exited_qty==2
    assert life.realized_pnl==pytest.approx(2*average-2*10.53)
    assert engine.capital_authority.total_used_exposure==engine.capital_authority.total_reserved_capital==0
    assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert len(h.failure_conversions)==len(h.sent_native)==len(h.stop_requests)==1


@pytest.mark.parametrize('fault',['scope_expiry','client_replaced','unknown_remainder','disconnect_reconnect'])
def test_one_minute_pmh_actual_core_authority_faults_hold_or_quarantine(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    prepared=terminal_one_minute_pmh(reassessment,monkeypatch,tmp_path,capsys)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared,clock_step=10)
    engine=h.core.execution_engine;broker=engine._provider.broker
    if fault in {'scope_expiry','client_replaced'}:
        original=broker.open_orders;delivered=[]
        def orders(**kw):
            rows=original(**kw)
            if kw.get('require_complete') and not delivered:
                delivered.append(True)
                if fault=='scope_expiry':h.life.clock.current+=timedelta(seconds=16)
                else:
                    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
                    replacement=IbkrClient('offline',0,999,5,'LIVE',True)
                    monkeypatch.setattr(replacement,'isConnected',lambda:True)
                    h.native_manager._client=replacement # Synthetic external connection replacement, never connect.
            return rows
        monkeypatch.setattr(broker,'open_orders',orders)
        assert not h.core.run_once();capsys.readouterr()
        assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit')
        assert h.native_open_orders[0].order.orderType=='STP'
    else:
        assert h.core.run_once();capsys.readouterr()
        before=deepcopy(engine._storage_engine.fetch_management_state('execution.native_orders.v1:PAPER'))
        if fault=='unknown_remainder':h.native_open_orders[0].orderState.status='PendingCancel'
        else:
            from src.brokers.ibkr_live_broker import IbkrLiveBroker
            original=broker.open_orders
            def disconnected_inventory(**kw):
                if kw.get('require_complete') and not h.native_client.isConnected():
                    return IbkrLiveBroker.open_orders(broker,**kw) # Real strict-owner disconnected guard.
                return original(**kw)
            monkeypatch.setattr(broker,'open_orders',disconnected_inventory)
            monkeypatch.setattr(h.native_client,'isConnected',lambda:False)
        h.life.clock.current+=timedelta(seconds=1)
        assert not h.core.run_once();capsys.readouterr()
        assert engine._native_quarantined and len(h.failure_conversions)==1
        if fault=='disconnect_reconnect':monkeypatch.setattr(h.native_client,'isConnected',lambda:True)
        h.life.clock.current+=timedelta(seconds=1)
        assert not h.core.run_once();capsys.readouterr()
        assert len(h.failure_conversions)==1 and before['orders'][request.client_order_id]['pmh_failure_exit']['native_order_id']=='72'
    assert life.filled_qty==1 and life.exited_qty==0
    assert engine.capital_authority.total_used_exposure==pytest.approx(10.53)
    assert len(h.sent_native)==len(h.stop_requests)==1



def test_one_minute_pmh_first_later_qualifying_bar_survives_full_entry_quota(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from dataclasses import replace
    h=trusted_steady_pmh(reassessment,monkeypatch,tmp_path,entry_position_limit=1)
    request=acknowledge(h,capsys)
    life=confirm_selected_fill(h,request,capsys,family='PREMARKET_HIGH_BREAK',fill_price=10.53,stop_price=request.stop_loss_price)
    from src.config.config_resolver import get_config
    assert get_config('RISK_MAX_OPEN_POSITIONS')==h.core.trade_registry.count_active()==1
    # New external discovery cache has no qualifying event. Keep the actual
    # service/store/qualification owners; never inject a Focus/risk decision.
    from src.news.evidence_store import CanonicalNewsEvidenceStore
    from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
    empty=CanonicalNewsEvidenceStore(tmp_path/'empty-news.json',prep_artifact_loader=lambda:{})
    h.life.service=CanonicalNewsIntelligenceService(evidence_store=empty,retrieval_provider=h.life.provider)
    empty_result=h.life.service.get_news(h.reads[-1].candidates,h.life.request,
        replace(h.life.policy,network_allowed=False,refresh_mode="cache_only",allow_cache_write=False))
    assert not empty_result.evidence_for_symbol('JPM')
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life),fault='wick',clock_step=10)
    for _ in range(3):
        assert h.core.run_once();capsys.readouterr()
        h.life.clock.current+=timedelta(seconds=1)
    assert not h.failure_conversions and life.filled_qty==1
    above=h.failure_bars[-1]
    below=replace(above,timestamp=above.timestamp+timedelta(minutes=1),close=10.295)
    h.failure_bars.append(below);h.streams['1m'].append(below)
    # The later bar is initially forming, then genuinely completes through Core.
    assert h.core.run_once();capsys.readouterr()
    assert not h.failure_conversions
    while h.life.clock.current<below.timestamp+timedelta(seconds=61):
        h.life.clock.current+=min(timedelta(seconds=10),below.timestamp+timedelta(seconds=61)-h.life.clock.current)
        assert h.core.run_once();capsys.readouterr()
    assert len(h.failure_conversions)==1 and h.failure_owner['pmh_failure_exit']['bar_start']==below.timestamp.isoformat()
    h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.29,symbol='JPM',side='SELL',orderId=72,
        parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=0;h.native_open_orders.clear()
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==0 and life.exited_qty==1 and life.realized_pnl==pytest.approx(-.24)
    assert h.core.execution_engine.capital_authority.total_used_exposure==0
    assert len(h.failure_conversions)==len(h.sent_native)==len(h.stop_requests)==1
    assert len(h.core.execution_engine.position_records)==2


def test_one_minute_pmh_unknown_dispatch_is_not_protection_or_retry_permission(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    prepared=terminal_one_minute_pmh(reassessment,monkeypatch,tmp_path,capsys)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared,conversion='unknown',clock_step=10)
    assert h.core.run_once();capsys.readouterr()
    assert h.failure_owner['pmh_failure_exit']['status']=='UNKNOWN'
    assert life.selected_exit_pending['status']=='UNKNOWN'
    assert not h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert not h.core.run_once();capsys.readouterr()
    assert h.core.execution_engine._native_quarantined and len(h.failure_conversions)==1
    assert life.filled_qty==1 and life.exited_qty==0
    assert h.core.execution_engine.capital_authority.total_used_exposure==10.53


def assert_readonly_selected_dispatch_restart(h,request,*,timeframe,profile):
    import os,subprocess,sys
    storage=h.core.storage_engine;namespace='execution.native_orders.v1:PAPER'
    before=storage.fetch_management_state(namespace)
    script="""
import socket,sqlite3,sys
socket.socket.connect=lambda *a,**k:(_ for _ in ()).throw(AssertionError('transport forbidden'))
from types import SimpleNamespace as NS
from src.storage.storage_engine import StorageEngine
from src.execution.execution_engine import ExecutionEngine
from src.config.runtime_config import RunMode
s=StorageEngine.__new__(StorageEngine);s.enabled=True;s.backend='sqlite'
s._store=NS(connection=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True))
before=s.fetch_management_state('execution.native_orders.v1:PAPER')
o=before['orders'][sys.argv[2]]
if sys.argv[4]=='UNIT_MANAGEMENT':
    children=[v for v in before['orders'].values() if v.get('protection_parent_order_id')==sys.argv[2]]
    assert o['unit_profit_exit']['reserved_quantity'] and children
    assert all(c['requested']==1 for c in children)
    assert any(c.get('unit_amendment',{}).get('status')=='MKT_CONFIRMED' for c in children)
elif sys.argv[4]=='UNIT_STOPS':
    children=[v for v in before['orders'].values() if v.get('protection_parent_order_id')==sys.argv[2]]
    assert o['request']['selected_stop_units'] and children
    assert all(c['requested']==1 and c['close_role']=='PROTECTION' for c in children)
else:
    assert o['pmh_failure_exit']['native_order_id']=='72' and o['pmh_failure_exit']['status']=='MKT'
    assert o['pmh_failure_exit']['occurrence']==o['request']['setup_metadata']
    assert o['pmh_failure_exit']['profile']==sys.argv[4]
assert o['request']['setup_metadata']['execution_stream']['execution_trigger_timeframe']==sys.argv[3]
e=ExecutionEngine.__new__(ExecutionEngine);e._storage_engine=s;e.run_mode=RunMode.PAPER
e._native_loaded=False;e._native_state=None;e._native_orders={};e._native_quarantined=False
try:e._load_native_orders()
except RuntimeError as exc:assert str(exc)=='NATIVE_ORDER_RESTART_RECONCILIATION_REQUIRED'
else:raise AssertionError('persisted dispatch resumed')
assert e._native_quarantined and e._failsafe_block_new_entries and e._native_state==before
assert s.fetch_management_state('execution.native_orders.v1:PAPER')==before
s._store.connection.close()
print('READ_ONLY_PMH_DISPATCH_RESTART_QUARANTINED')
"""
    result=subprocess.run([sys.executable,'-c',script,storage.sqlite_path,request.client_order_id,timeframe,profile],
        env=dict(os.environ),capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert 'READ_ONLY_PMH_DISPATCH_RESTART_QUARANTINED' in result.stdout
    assert storage.fetch_management_state(namespace)==before


def test_one_minute_pmh_dispatch_identity_restores_readonly_and_quarantines_in_fresh_process(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    prepared=terminal_one_minute_pmh(reassessment,monkeypatch,tmp_path,capsys)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared,clock_step=10)
    assert h.core.run_once();capsys.readouterr()
    from src.strategies.ross_momentum.strategy_policy import PMH_COMPLETED_BAR_FAILURE_PROFILE
    assert_readonly_selected_dispatch_restart(h,request,timeframe='1m',profile=PMH_COMPLETED_BAR_FAILURE_PROFILE)
    assert len(h.failure_conversions)==1 and life.filled_qty==1 and life.exited_qty==0
    assert h.core.execution_engine.capital_authority.total_used_exposure==10.53


def late_bull(reassessment,monkeypatch,tmp_path):
    from test_joined_core_pmh_readonly import standalone_bull_joined
    def paper_bull(*args,**kwargs):return paper_pmh(*args,joined_factory=standalone_bull_joined,**kwargs)
    return late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_bull,fill_price=10.88,stop_price=10.63)


def acknowledge_bull(h,capsys):
    request=acknowledge_selected(h,capsys,family='BULL_FLAG',entry=10.79,stop=10.63,
        invalidation=10.63,triggers=h.bull_triggers)
    assert request.target_model=='Measured move' and not request.relationship_context
    source,results=h.registry_batches[-1]
    assert len(results)==33
    assert h.evaluated[0][0].setup_metadata['source_metadata']==results[h.evaluated[0][0].setup_metadata['canonical_result_index']].setup_metadata
    return request


def test_standalone_bull_native_core_paper_fill_initial_protection(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=late_bull(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge_bull(h,capsys)
        life=confirm_selected_fill(h,request,capsys,family='BULL_FLAG',fill_price=10.88,stop_price=10.63)
        assert life.avg_fill_price!=h.evaluated[0][0].entry_price
        assert not h.manager._relationship_plans and life.selected_target_price is None
    finally:teardown_unsent_fixture(h,no_external_activity)


CENTRAL_FAMILIES=['BULL_FLAG','FIRST_PULLBACK','MICRO_PULLBACK']
BREAKOUT_FAMILIES=['KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK']
CANONICAL_FAMILIES=['ABCD','VWAP_RECLAIM_CONTINUATION','CUP_HANDLE','OPENING_DRIVE','EMA_PULLBACK','VWAP_PULLBACK','TREND_CONTINUATION_STAIR_STEP']
SELECTED_FAILURE_FAMILIES=CENTRAL_FAMILIES+BREAKOUT_FAMILIES+CANONICAL_FAMILIES


def central_failure_case(reassessment,monkeypatch,tmp_path,capsys,family,*,fault='none',conversion='confirmed'):
    if family=='CUP_HANDLE':
        h=late_cup(reassessment,monkeypatch,tmp_path,clock_time=(13,55,30));ack=acknowledge_cup;price=10.55
    else:h,ack,_,price=standalone_case(reassessment,monkeypatch,tmp_path,family)
    request=ack(h,capsys)
    life=confirm_selected_fill(h,request,capsys,family=family,fill_price=price,stop_price=request.stop_loss_price)
    retained=deepcopy(h.core.execution_engine._native_orders[request.client_order_id]['request'])
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life),
        fault=fault,conversion=conversion,clock_step=10)
    assert retained==h.core.execution_engine._native_orders[request.client_order_id]['request']
    return h,request,life


def finish_failure_fill(h,life,capsys,*,quantity=1):
    h.facts[72]=dict(status='Filled',filled=quantity,remaining=0,avgFillPrice=h.failure_exit_price,
        symbol='JPM',side='SELL',orderId=72,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=0;h.native_open_orders.clear() # Independent external position/order facts, not internal flat mutation.
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()


@pytest.mark.parametrize('family',SELECTED_FAILURE_FAMILIES)
def test_central_failure_full_registry_core_exit_above_stop_to_flat(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family):
    from src.strategies.ross_momentum.strategy_policy import CENTRAL_STANDALONE_FAILURE_PROFILE, BREAKOUT_STANDALONE_FAILURE_PROFILE, CANONICAL_STANDALONE_FAILURE_PROFILE
    h,request,life=central_failure_case(reassessment,monkeypatch,tmp_path,capsys,family)
    intent,serialized,decision=h.evaluated[0]
    owner=h.failure_owner;metadata=deepcopy(request.setup_metadata)
    from src.storage.serialization import to_jsonable
    assert metadata==to_jsonable(intent.setup_metadata) and metadata['trigger_level']==intent.entry_price
    saved=h.core.execution_engine._storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
    assert saved['orders'][request.client_order_id]['request']['setup_metadata']==metadata
    assert len(h.registry_batches[0][1])==33 and not request.relationship_context
    assert h.failure_bars[-1].timestamp>=__import__('datetime').datetime.fromisoformat(owner['last_accounted_entry_fill_at'])
    assert request.stop_loss_price<h.failure_exit_price<h.failure_bars[-1].close<metadata['trigger_level']
    assert h.core.run_once();capsys.readouterr()
    latch=owner['pmh_failure_exit'] # Existing durable transport latch, explicit new profile.
    expected_profile=(CENTRAL_STANDALONE_FAILURE_PROFILE if family in CENTRAL_FAMILIES else
        BREAKOUT_STANDALONE_FAILURE_PROFILE if family in BREAKOUT_FAMILIES else CANONICAL_STANDALONE_FAILURE_PROFILE)
    assert latch['profile']==expected_profile and latch['selected_entry']==metadata['trigger_level']
    if family=='KEY_LEVEL_BREAK':assert request.stop_loss_price==10.88 and request.invalidation_level==11. and latch['selected_entry']==11.
    if family=='TREND_CONTINUATION_STAIR_STEP':assert request.stop_loss_price==10.34 and request.invalidation_level==10.24 and latch['selected_entry']==10.64
    if family=='ABCD':assert latch['selected_entry']==metadata['anchor_b_price'] and latch['selected_entry']!=metadata['d_projection']
    assert latch['occurrence']==metadata and latch['status']=='MKT'
    assert len(h.failure_conversions)==1 and life.filled_qty==1
    assert not h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    finish_failure_fill(h,life,capsys)
    assert life.filled_qty==0 and life.exited_qty==1
    assert life.realized_pnl==pytest.approx(h.failure_exit_price-life.avg_fill_price)
    assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    engine=h.core.execution_engine
    assert engine.capital_authority.total_used_exposure==engine.capital_authority.total_reserved_capital==0
    assert len(h.failure_conversions)==len(h.sent_native)==len(h.stop_requests)==1
    assert len(engine.position_records)==2 and request.setup_metadata==metadata
    assert serialized==vars(intent) and request.take_profit_price is None


@pytest.mark.parametrize('family',SELECTED_FAILURE_FAMILIES)
def test_central_failure_completed_bar_boundaries(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family):
    from dataclasses import replace
    from datetime import datetime
    # One actual admission/accounting/protection lifecycle per family. All seven
    # external-history cases still pass through actual Core, without resetting
    # owner state, clearing quarantine or weakening a clock/gate.
    h,request,life=central_failure_case(reassessment,monkeypatch,tmp_path,capsys,family,fault='stale')
    old=deepcopy(h.failure_bars)
    now=h.life.clock.current;level=request.setup_metadata['trigger_level']
    timeframe=request.setup_metadata['execution_stream']['execution_trigger_timeframe']
    seconds={'10s':10,'1m':60}[timeframe]
    end=now.replace(microsecond=0)-timedelta(seconds=int(now.timestamp())%seconds)
    fresh=replace(old[-1],timestamp=end-timedelta(seconds=seconds))
    assert fresh.timestamp>=datetime.fromisoformat(h.failure_owner['last_accounted_entry_fill_at'])
    equality=replace(fresh,timestamp=end-timedelta(seconds=2*seconds),close=level)
    wick=replace(fresh,close=level+.01)
    assert equality.timestamp>=__import__('datetime').datetime.fromisoformat(h.failure_owner['last_accounted_entry_fill_at'])
    cases={
        'stale':old,
        'missing':[],
        'forming':[replace(fresh,timestamp=now-timedelta(seconds=5))],
        'future':[replace(fresh,timestamp=now+timedelta(seconds=1))],
        'straddling':[replace(fresh,timestamp=datetime.fromisoformat(h.failure_owner['last_accounted_entry_fill_at'])-timedelta(seconds=1))],
        'equality':[equality],
        'wick':[equality,wick],
    }
    for fault,bars in cases.items():
        h.failure_bars=bars # Synthetic external history response only.
        assert h.core.run_once(),fault
        capsys.readouterr()
        assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit'),fault
        assert life.filled_qty==1 and life.selected_stop_price==request.stop_loss_price,fault
        assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected'],fault
    # Same unchanged owned occurrence then accepts genuinely qualifying evidence:
    # none of the negatives consumed applicability or merely hid an entry gate.
    # Preserve each already-observed completed bar; never revise its close to
    # manufacture failure. A distinct next bar genuinely completes in real Core.
    candidate=replace(fresh,timestamp=end)
    for _ in range(seconds//5+1):
        h.life.clock.current+=timedelta(seconds=5)
        assert h.core.run_once();capsys.readouterr()
        assert not h.failure_conversions
    h.failure_bars=[equality,wick,candidate]
    assert candidate.low>request.stop_loss_price and candidate.close<level
    assert h.core.run_once();capsys.readouterr()
    assert len(h.failure_conversions)==1 and h.failure_owner['pmh_failure_exit']['status']=='MKT'


@pytest.mark.parametrize('family',SELECTED_FAILURE_FAMILIES)
@pytest.mark.parametrize('conversion',['uncertain','rejected','stop_race','unknown'])
def test_central_failure_uncertainty_and_race_do_not_retry(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family,conversion):
    h,request,life=central_failure_case(reassessment,monkeypatch,tmp_path,capsys,family,conversion=conversion)
    assert h.core.run_once();capsys.readouterr()
    if conversion=='unknown':
        assert not h.core.run_once();capsys.readouterr()
        assert h.core.execution_engine._native_quarantined
    else:
        for _ in range(3):
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
    assert len(h.failure_conversions)==len(h.sent_native)==len(h.stop_requests)==1
    if conversion=='stop_race':assert life.filled_qty==0 and life.exited_qty==1
    else:
        assert life.filled_qty==1 and life.exited_qty==0
        assert h.failure_owner['pmh_failure_exit']['status']=={'uncertain':'MKT','rejected':'STP','unknown':'UNKNOWN'}[conversion]
        assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected'] is (conversion=='rejected')


def install_selected_truth_fault(h,monkeypatch,fault):
    if fault=='broker_larger':h.native_quantity[0]=2
    if fault in {'unknown','partial_truth'}:
        h.native_client.position_snapshot=lambda:BrokerPositionResult((),'UNKNOWN' if fault=='unknown' else 'PARTIAL','SYNTHETIC_TEST',h.life.clock.now(timezone.utc))
    if fault=='wrong_reference':h.native_open_orders[0].order.orderRef='PROTECT|OTHER'
    if fault=='pending_order':
        extra=deepcopy(h.native_open_orders[0]);extra.orderId=73;h.native_open_orders.append(extra)
    if fault=='incomplete_inventory':
        original=h.core.execution_engine._provider.broker.open_orders
        def incomplete(**kw):
            if kw.get('require_complete'):raise RuntimeError('synthetic incomplete native inventory')
            return original(**kw)
        monkeypatch.setattr(h.core.execution_engine._provider.broker,'open_orders',incomplete)


@pytest.mark.parametrize('family',SELECTED_FAILURE_FAMILIES)
@pytest.mark.parametrize('fault',['broker_larger','unknown','partial_truth','wrong_reference','pending_order','incomplete_inventory'])
def test_central_failure_actual_truth_and_inventory_veto(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family,fault):
    h,request,life=central_failure_case(reassessment,monkeypatch,tmp_path,capsys,family)
    install_selected_truth_fault(h,monkeypatch,fault)
    h.core.run_once();capsys.readouterr()
    assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit')
    assert life.filled_qty==1 and life.selected_stop_price==request.stop_loss_price


@pytest.mark.parametrize('family',SELECTED_FAILURE_FAMILIES)
@pytest.mark.parametrize('transition',['phase','date'])
def test_central_failure_transition_expires_even_when_execution_gated(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family,transition):
    h,request,life=central_failure_case(reassessment,monkeypatch,tmp_path,capsys,family)
    original=h.life.clock.current;h.core.execution_enabled=False
    h.life.clock.current+=timedelta(hours=4) if transition=='phase' else timedelta(days=1)
    h.core.run_once();capsys.readouterr()
    assert h.failure_owner['pmh_management_expired'] and not h.failure_conversions
    h.life.clock.current=original;h.core.execution_enabled=True
    h.core.run_once();capsys.readouterr()
    assert not h.failure_conversions and life.filled_qty==1


@pytest.mark.parametrize('family',SELECTED_FAILURE_FAMILIES)
def test_central_failure_later_bar_and_missing_timestamp_or_relationship_hold(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family):
    from dataclasses import replace
    h,request,life=central_failure_case(reassessment,monkeypatch,tmp_path,capsys,family,fault='wick')
    assert h.core.run_once();capsys.readouterr()
    assert not h.failure_conversions
    owner=h.failure_owner;now=h.life.clock.current
    first=h.failure_bars[-1];seconds={'10s':10,'1m':60}[request.setup_metadata['execution_stream']['execution_trigger_timeframe']]
    later=replace(first,timestamp=first.timestamp+timedelta(seconds=seconds),close=round((request.setup_metadata['trigger_level']+request.stop_loss_price)/2,2))
    h.failure_bars.append(later);h.streams[request.setup_metadata['execution_stream']['execution_trigger_timeframe']].append(later)
    for delta in range(seconds//5+1):
        h.life.clock.current+=timedelta(seconds=5)
        assert h.core.run_once();capsys.readouterr()
    assert len(h.failure_conversions)==1 and owner['pmh_failure_exit']['bar_start']==later.timestamp.isoformat()
    evaluate=lambda row:h.manager.evaluate_selected_completed_failure(row,[later],observed_at=h.life.clock.current,session_plan=request.management_session_plan)
    assert evaluate(owner)
    for change in ('missing_stamp','relationship','other_family','wrong_stop','wrong_invalidation','bad_occurrence'):
        row=deepcopy(owner)
        if change=='missing_stamp':row.pop('last_accounted_entry_fill_at')
        if change=='relationship':row['request']['relationship_context']={'profile':'BULL_FLAG_MICRO_2R_V1'}
        if change=='other_family':row['request']['setup_family_id']='RANGE_BREAK'
        if change=='wrong_stop':row['request']['stop_loss_price']+=.01
        if change=='wrong_invalidation':row['request']['invalidation_level']+=.01
        if change=='bad_occurrence':row['request']['setup_metadata']['canonical_result_index']=-1
        assert evaluate(row) is None,change


def small_central_owned(reassessment,monkeypatch,tmp_path,capsys,family,*,partial=False,requested_base=8,risk_cap=2,synthetic_capital=400,fill=True,expected_admitted=None,quantity_fault=None,unit_stops=False,unit_fault=None,micro_fault=None,micro_clock=None,bull_clock=None):
    from test_joined_core_pmh_readonly import pmh_joined,standalone_bull_joined,micro_joined,key_joined,consolidation_joined,flat_top_joined,orb_joined,hod_joined,momentum_joined,cup_joined,opening_drive_joined,indicator_pullback_joined,vwap_pullback_joined,stair_step_joined
    from test_abcd_production_handoff import abcd_joined
    from test_joined_core_first_pullback import first_joined
    factory={'PREMARKET_HIGH_BREAK':pmh_joined,'BULL_FLAG':standalone_bull_joined,'FIRST_PULLBACK':first_joined,'MICRO_PULLBACK':micro_joined,'KEY_LEVEL_BREAK':key_joined,'CONSOLIDATION_BREAKOUT':consolidation_joined,'FLAT_TOP_BREAKOUT':flat_top_joined,'OPENING_RANGE_BREAKOUT':orb_joined,'HOD_BREAK':hod_joined,'ABCD':abcd_joined,'VWAP_RECLAIM_CONTINUATION':momentum_joined,'CUP_HANDLE':cup_joined,'OPENING_DRIVE':opening_drive_joined,'EMA_PULLBACK':indicator_pullback_joined,'VWAP_PULLBACK':vwap_pullback_joined,'TREND_CONTINUATION_STAIR_STEP':stair_step_joined}[family]
    prices={'PREMARKET_HIGH_BREAK':(10.53,10.3-max(.01,10.3*.001)),'BULL_FLAG':(10.88,10.63),'FIRST_PULLBACK':(10.55,10.15),'MICRO_PULLBACK':(10.88,10.6),'KEY_LEVEL_BREAK':(11.02,10.88),'CONSOLIDATION_BREAKOUT':(10.43,10.21),'FLAT_TOP_BREAKOUT':(10.27,9.99),'OPENING_RANGE_BREAKOUT':(10.42,9.95),'HOD_BREAK':(10.34,10.2),'ABCD':(11.02,10.35),'VWAP_RECLAIM_CONTINUATION':(10.34,10.23),'CUP_HANDLE':(10.55,10.3),'OPENING_DRIVE':(10.62,10.47),'EMA_PULLBACK':(10.53,10.29),'VWAP_PULLBACK':(10.8,10.23),'TREND_CONTINUATION_STAIR_STEP':(10.68,10.34)}
    price,stop=prices[family]
    monkeypatch.setenv('TRADING_DEFAULT_CAPITAL',str(synthetic_capital))
    def small_joined(*args,**kwargs):
        kwargs['runtime_options']['config_overrides'].update(RISK_PROFILE='SMALL',RISK_MAX_POSITION_SIZE=risk_cap)
        if requested_base is not None:
            kwargs['runtime_options']['config_overrides']['ROSS_SYNTHETIC_REQUESTED_BASE_SIZE']=requested_base
        if unit_stops:kwargs['runtime_options']['config_overrides']['ROSS_SYNTHETIC_UNIT_STOPS']=True
        if family=='CUP_HANDLE':kwargs['clock_time']=(13,55,30)
        if family=='MICRO_PULLBACK' and micro_fault is not None:kwargs['market_fault']=micro_fault
        if family=='MICRO_PULLBACK' and micro_clock is not None:kwargs.update(clock_time=micro_clock,real_session=True)
        if family=='BULL_FLAG' and bull_clock is not None:kwargs.update(clock_time=bull_clock,real_session=True)
        h=factory(*args,**kwargs)
        for row in h.rows.values():
            gap=(row['last_price']/row['prev_close']-1)*100;row.update(gap_pct=gap,pct_change=gap)
        return h
    def paper_small(*args,**kwargs):return paper_pmh(*args,joined_factory=small_joined,**kwargs)
    h=late_pmh(reassessment,monkeypatch,tmp_path,paper_factory=paper_small,fill_price=price,stop_price=stop,expected_stop_quantity=None,unit_stops=unit_stops,unit_fault=unit_fault)
    if quantity_fault is not None:
        evaluate=h.core.risk_engine.evaluate_trade_intent
        def malformed(intent,**kwargs):
            # Negative corruption at the real risk boundary; no prepared success.
            if quantity_fault=='missing':delattr(intent,'quantity')
            elif quantity_fault=='bool':intent.quantity=True
            else:intent.quantity=9
            return evaluate(intent,**kwargs)
        monkeypatch.setattr(h.core.risk_engine,'evaluate_trade_intent',malformed)
    assert h.core.run_once();capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();capsys.readouterr()
    if quantity_fault is not None:
        assert not h.sent_native and not h.stop_requests and not h.manager.snapshot_positions()
        return h,None,None
    request=h.sent_native[0]
    approved=expected_admitted if expected_admitted is not None else min(risk_cap,h.evaluated[0][0].quantity)
    assert request.quantity==approved and not h.stop_requests and not h.manager.snapshot_positions()
    assert request.management_session_plan and request.setup_metadata and not request.relationship_context
    if not fill:return h,request,None
    count=1 if partial else approved
    h.facts[71]=dict(status='Submitted' if partial else 'Filled',filled=count,remaining=approved-count,avgFillPrice=price)
    h.native_quantity[0]=count
    if not (unit_stops and partial):h.native_open_orders.clear()
    h.life.clock.current+=timedelta(seconds=1)
    completed=h.core.run_once();capsys.readouterr()
    life=h.core.execution_engine.post_fill_lifecycle.get_trade(request.client_order_id)
    if unit_fault is not None:
        assert not completed
    else:
        assert completed
        assert life.filled_qty==count
        assert (sum(leg.quantity for leg in life.stop_legs) if request.selected_stop_units else life.stop.quantity)==count
    return h,request,life


@pytest.mark.parametrize('family',SELECTED_FAILURE_FAMILIES)
@pytest.mark.parametrize('partial_entry',[False,True])
def test_central_failure_partial_entry_exclusion_and_partial_exit_accounting(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family,partial_entry):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,family,partial=partial_entry)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared,clock_step=10)
    assert h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine
    if partial_entry:
        assert not h.failure_conversions and not h.failure_owner['terminal']
        assert life.filled_qty==1 and engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
        return
    assert len(h.failure_conversions)==1
    h.facts[72]=dict(status='Submitted',filled=1,remaining=1,avgFillPrice=h.failure_exit_price,
        symbol='JPM',side='SELL',orderId=72,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=1
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==life.exited_qty==h.manager.snapshot_positions()['JPM'].quantity==1
    assert not h.manager.snapshot_positions()['JPM'].partial_taken and not life.trailing_active
    assert life.selected_stop_price==request.stop_loss_price
    assert h.native_open_orders[0].order.totalQuantity==2 and h.native_open_orders[0].order.orderType=='MKT'
    assert not engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    finish_failure_fill(h,life,capsys,quantity=2)
    assert life.filled_qty==0 and life.exited_qty==2
    assert life.realized_pnl==pytest.approx(2*(h.failure_exit_price-life.avg_fill_price))
    assert engine.capital_authority.total_used_exposure==0 and len(h.failure_conversions)==1


@pytest.mark.parametrize('family',SELECTED_FAILURE_FAMILIES)
def test_central_failure_accounting_interruption_retains_quarantine_no_replay(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family):
    h,request,life=central_failure_case(reassessment,monkeypatch,tmp_path,capsys,family)
    assert h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine
    h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=h.failure_exit_price,
        symbol='JPM',side='SELL',orderId=72,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=0;h.native_open_orders.clear()
    original=engine._record_fill_and_position
    def interrupted(*a,**kw):original(*a,**kw);raise RuntimeError('synthetic central interruption')
    monkeypatch.setattr(engine,'_record_fill_and_position',interrupted)
    with pytest.raises(RuntimeError,match='synthetic central interruption'):
        engine.collect_relationship_updates(result_processor=lambda r:h.core._apply_execution_results_to_trade_management([r]))
    assert engine._native_quarantined and life.filled_qty==0 and life.exited_qty==1
    before=(len(engine.position_records),life.realized_pnl,engine.capital_authority.total_used_exposure)
    with pytest.raises(RuntimeError):engine.collect_relationship_updates()
    assert before==(len(engine.position_records),life.realized_pnl,engine.capital_authority.total_used_exposure)
    assert len(h.failure_conversions)==1


@pytest.mark.parametrize('family',SELECTED_FAILURE_FAMILIES)
def test_central_confirmed_stop_fill_is_processed_before_discretionary_exit(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family):
    h,request,life=central_failure_case(reassessment,monkeypatch,tmp_path,capsys,family)
    external_stop_facts(h,life)
    assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==0 and life.exited_qty==1
    assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit')
    assert h.core.execution_engine.capital_authority.total_used_exposure==0


def test_cup_original_entry_clock_correctly_expires_before_failure_bar(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=late_cup(reassessment,monkeypatch,tmp_path)
    request=acknowledge_cup(h,capsys)
    life=confirm_selected_fill(h,request,capsys,family='CUP_HANDLE',fill_price=10.55,stop_price=request.stop_loss_price)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life),clock_step=10)
    assert h.core.run_once();capsys.readouterr()
    assert h.failure_owner['pmh_management_expired'] and not h.failure_conversions
    assert life.filled_qty==1 and life.selected_stop_price==10.3


PROFIT_FAMILIES=('PREMARKET_HIGH_BREAK',*SELECTED_FAILURE_FAMILIES)


def one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,*,family='BULL_FLAG',fault='none',conversion='confirmed',prepared=None):
    """Existing genuine entry/fill/protection; only later external bar/quote facts."""
    import math
    from dataclasses import replace
    from src.strategies.common.candles.candle_types import Candle
    if prepared and prepared[1].relationship_context:
        h,request,life=prepared  # Initial relationship ownership already proved; reuse only bar/quote preparation below.
    elif prepared:
        h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared,fault='equality',clock_step=5,conversion=conversion)
    elif family=='PREMARKET_HIGH_BREAK':
        h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,fault='equality',clock_step=5,conversion=conversion)
    else:
        h,request,life=central_failure_case(reassessment,monkeypatch,tmp_path,capsys,family,fault='equality',conversion=conversion)
    if fault=='phase_at_commit':
        # Retain the genuine ordinary Cup occurrence, then HOLD through real
        # bounded cycles until a later fresh observation near the phase edge.
        target=h.life.clock.current.replace(hour=13,minute=59,second=32,microsecond=0)
        while h.life.clock.current<target:
            h.life.clock.current+=min(timedelta(seconds=5),target-h.life.clock.current)
            assert h.core.run_once();capsys.readouterr()
            assert not h.failure_conversions
    from decimal import Decimal
    entry,stop=Decimal(str(life.avg_fill_price)),Decimal(str(life.selected_stop_price))
    level=float(entry+2*(entry-stop))
    bid=math.ceil(level*100)/100;close=bid+.01;ask=bid+.02
    if fault=='equality':bid=close=level;ask=level+.02
    if fault in {'below','wick'}:close=level-.01
    seconds={'10s':10,'1m':60}[request.setup_metadata['execution_stream']['execution_trigger_timeframe']]
    now=h.life.clock.current
    start=now.replace(microsecond=0)+timedelta(seconds=(-int(now.timestamp()))%seconds)
    bar=Candle(close, max(ask,close+.01), min(bid-.01,close-.01),close,1000,timestamp=start)
    if fault=='wick':bar=replace(bar,high=level+.03)
    if fault=='straddling':bar=replace(bar,timestamp=__import__('datetime').datetime.fromisoformat(h.failure_owner['last_accounted_entry_fill_at'])-timedelta(seconds=1))
    if fault=='forming':bar=replace(bar,timestamp=start+timedelta(seconds=seconds-5))
    if fault=='future':bar=replace(bar,timestamp=start+timedelta(seconds=seconds+1))
    if fault=='stale':bar=replace(bar,timestamp=start-timedelta(hours=1))
    if fault in {'none','equality','below','wick','quote_latency','bar_aging'}:
        timeframe=request.setup_metadata['execution_stream']['execution_trigger_timeframe']
        previous=h.streams[timeframe][-1]
        cursor=previous.timestamp+timedelta(seconds=seconds)
        while cursor<bar.timestamp:
            # New above-entry/below-profit holds, never a revised completed bar.
            hold=replace(previous,timestamp=cursor)
            h.streams[timeframe].append(hold)
            previous=hold;cursor+=timedelta(seconds=seconds)
        append_external_management_bar(h,timeframe,bar)
    h.failure_bars=[bar] if fault in {'straddling','stale'} else [*h.failure_bars,bar]
    if fault=='missing':h.failure_bars=[]
    original=h.core.market_data_snapshot_manager.batch_snapshots
    def quotes(symbols):
        values,errors=original(symbols)
        result={}
        if fault=='quote_latency':h.life.clock.current+=timedelta(seconds=1)
        for symbol,value in values.items():
            stamp=h.life.clock.current
            current=replace(value,last=close,bid=bid,ask=ask,asof_utc=stamp,market_timestamp_utc=stamp,
                timestamp_source='LAST_TRADE',snapshot_complete=True,market_data_type='LIVE',
                returned_market_data_type='LIVE',market_data_type_confirmed=True,data_quality_flags=())
            if fault=='bar_aging' and not getattr(h,'profit_quote_confirmed',False):current=replace(current,market_data_type_confirmed=False)
            if fault=='quote_missing':continue
            if fault=='quote_aging':current=replace(current,market_timestamp_utc=stamp-timedelta(seconds=14))
            if fault=='quote_stale':current=replace(current,market_timestamp_utc=stamp-timedelta(hours=1))
            if fault=='quote_future':current=replace(current,market_timestamp_utc=stamp+timedelta(seconds=1))
            if fault=='quote_unconfirmed':current=replace(current,market_data_type_confirmed=False)
            if fault=='quote_incomplete':current=replace(current,snapshot_complete=False)
            if fault=='quote_wrong_symbol':current=replace(current,symbol='UNRELATED')
            if fault=='quote_crossed':current=replace(current,ask=bid-.01)
            if fault=='quote_below':current=replace(current,bid=level-.01)
            if fault=='quote_flag':current=replace(current,data_quality_flags=('MD_STALE',))
            result[symbol]=current
        return result,errors
    h.core.market_data_snapshot_manager.batch_snapshots=quotes
    # No completed close is revised. Forming/future facts stay non-actionable;
    # the new observation completes by actual bounded Core cycles/scope refresh.
    h.profit_precommit_delay=2 if fault in {'quote_aging','bar_aging'} else 11 if fault=='phase_at_commit' else 0
    if fault in {'quote_aging','bar_aging','phase_at_commit','real_final_valid'}:install_real_profit_amendment(h,monkeypatch)
    end=start+timedelta(seconds=seconds)
    h.profit_observations=[]
    while h.life.clock.current<end:
        h.life.clock.current+=min(timedelta(seconds=5),end-h.life.clock.current)
        assert h.core.run_once();h.profit_observations.append(capsys.readouterr().out)
        if h.life.clock.current<end:assert not h.failure_conversions
    if fault=='quote_latency':
        # Discovery may acquire a quote after management saw the forming bar.
        # Observe the now-completed immutable bar in another real Core cycle.
        assert h.core.run_once();h.profit_observations.append(capsys.readouterr().out)
    if fault=='bar_aging':
        from src.strategies.ross_momentum.policy.pattern_input_policy import PatternInputPolicy
        fresh=PatternInputPolicy.from_policy_v2().candle_freshness_seconds[request.setup_metadata['execution_stream']['execution_trigger_timeframe']]
        target=bar.timestamp+timedelta(seconds=fresh-1)
        while h.life.clock.current<target:
            h.life.clock.current+=min(timedelta(seconds=5),target-h.life.clock.current)
            assert h.core.run_once();capsys.readouterr()
            assert not h.failure_conversions
        h.profit_quote_confirmed=True  # New independent external type confirmation.
        assert h.core.run_once();h.profit_observations.append(capsys.readouterr().out)
    h.profit_level=level;h.failure_exit_price=bid
    return h,request,life


@pytest.mark.parametrize('family',PROFIT_FAMILIES)
def test_standalone_one_share_profit_full_registry_core_to_flat(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family):
    from src.strategies.ross_momentum.strategy_policy import STANDALONE_ONE_SHARE_PROFIT_PROFILE
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,family=family)
    owner=h.failure_owner;metadata=deepcopy(request.setup_metadata)
    assert len(h.registry_batches[0][1])==33 and not request.relationship_context
    assert len(h.failure_conversions)==1 and life.filled_qty==1, h.profit_observations[-1]
    latch=owner['pmh_failure_exit'] # Existing schema-compatible once-only selected exit latch.
    assert latch['profile']==STANDALONE_ONE_SHARE_PROFIT_PROFILE and latch['status']=='MKT'
    assert latch['entry_fill_price']==life.avg_fill_price and latch['original_stop']==request.stop_loss_price
    assert latch['entry_fill_price']!=metadata['trigger_level']
    assert latch['milestone']==h.profit_level
    assert h.profit_level==pytest.approx(life.avg_fill_price+2*(life.avg_fill_price-request.stop_loss_price))
    if family=='HOD_BREAK':assert h.profit_level==10.62
    assert latch['close']>=h.profit_level and latch['profit_quote']['bid']>=h.profit_level
    assert latch['occurrence']==metadata and request.take_profit_price is life.target is None
    assert request.target_model==h.evaluated[0][0].target_model
    assert h.evaluated[0][1]==vars(h.evaluated[0][0])
    persisted=h.core.storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
    assert persisted['orders'][request.client_order_id]['pmh_failure_exit']==latch
    if family=='TREND_CONTINUATION_STAIR_STEP':assert request.stop_loss_price==10.34 and request.invalidation_level==10.24
    assert not h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    finish_failure_fill(h,life,capsys)
    assert life.filled_qty==0 and life.exited_qty==1 and not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    engine=h.core.execution_engine
    assert engine.capital_authority.total_used_exposure==engine.capital_authority.total_reserved_capital==0
    assert engine.strategy_allocation_authority.strategy_used_exposure('RossMomentumStrategyV1')==0
    assert len(h.failure_conversions)==len(h.sent_native)==len(h.stop_requests)==1
    assert len(engine.position_records)==2 and request.setup_metadata==metadata
    assert life.realized_pnl==pytest.approx(h.failure_exit_price-life.avg_fill_price)


@pytest.mark.parametrize('fault',['below','wick','forming','straddling','missing','stale','future',
    'quote_missing','quote_stale','quote_future','quote_unconfirmed','quote_incomplete','quote_wrong_symbol','quote_crossed','quote_below','quote_flag'])
def test_standalone_profit_actual_core_adverse_holds(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,fault=fault)
    assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit')
    assert life.filled_qty==1 and life.stop.quantity==1 and life.selected_stop_price==request.stop_loss_price
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert len(h.core.execution_engine.position_records)==1


def test_standalone_profit_completed_milestone_equality_qualifies(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,fault='equality')
    assert len(h.failure_conversions)==1 and h.failure_owner['pmh_failure_exit']['close']==h.profit_level
    finish_failure_fill(h,life,capsys)
    assert life.filled_qty==0


def test_standalone_profit_quote_acquired_after_cycle_start_is_current(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,fault='quote_latency')
    assert len(h.failure_conversions)==1, h.profit_observations[-1]
    finish_failure_fill(h,life,capsys)
    assert life.filled_qty==0 and life.exited_qty==1


@pytest.mark.parametrize('partial',[False,True])
def test_standalone_profit_real_two_share_request_and_partial_remain_excluded(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,partial):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',partial=partial)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    assert request.quantity==2 and life.filled_qty==(1 if partial else 2)
    assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit')
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']


def confirm_external_profit_quote(h):
    from dataclasses import replace
    original=h.core.market_data_snapshot_manager.batch_snapshots
    def quotes(symbols):
        values,errors=original(symbols)
        return {key:replace(value,market_data_type_confirmed=True) for key,value in values.items()},errors
    h.core.market_data_snapshot_manager.batch_snapshots=quotes


@pytest.mark.parametrize('conversion',['uncertain','rejected','stop_race','unknown'])
def test_standalone_profit_same_id_uncertainty_and_stop_race_no_retry(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,conversion):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,conversion=conversion)
    if conversion=='unknown':
        assert not h.core.run_once();capsys.readouterr()
        assert h.core.execution_engine._native_quarantined
    else:
        for _ in range(3):
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
    assert len(h.failure_conversions)==len(h.sent_native)==len(h.stop_requests)==1
    if conversion=='stop_race':
        assert life.filled_qty==0 and life.exited_qty==1
        assert h.core.execution_engine.capital_authority.total_used_exposure==0
    else:
        assert life.filled_qty==1 and life.exited_qty==0
        assert h.failure_owner['pmh_failure_exit']['status']=={'uncertain':'MKT','rejected':'STP','unknown':'UNKNOWN'}[conversion]
        assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected'] is (conversion=='rejected')
        assert h.core.execution_engine.capital_authority.total_used_exposure==life.avg_fill_price


@pytest.mark.parametrize('fault',['broker_larger','unknown','partial_truth','wrong_reference','pending_order','incomplete_inventory'])
def test_standalone_profit_actual_truth_and_inventory_veto(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,fault='quote_unconfirmed')
    confirm_external_profit_quote(h)
    install_selected_truth_fault(h,monkeypatch,fault)
    h.life.clock.current+=timedelta(seconds=1)
    h.core.run_once();capsys.readouterr()
    assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit')
    assert life.filled_qty==1 and life.selected_stop_price==request.stop_loss_price


@pytest.mark.parametrize('transition',['phase','date'])
def test_standalone_profit_phase_expiry_while_gated(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,transition):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,fault='quote_unconfirmed')
    confirm_external_profit_quote(h);h.core.execution_enabled=False
    h.life.clock.current+=timedelta(hours=4) if transition=='phase' else timedelta(days=1)
    h.core.run_once();capsys.readouterr()
    assert h.failure_owner['pmh_management_expired'] and not h.failure_conversions
    assert life.filled_qty==1


def test_standalone_profit_authoritative_stop_fill_precedes_discretionary_close(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,fault='quote_unconfirmed')
    confirm_external_profit_quote(h);external_stop_facts(h,life)
    assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==0 and life.exited_qty==1 and not h.failure_conversions
    assert not h.failure_owner.get('pmh_failure_exit')
    assert h.core.execution_engine.capital_authority.total_used_exposure==0


def test_standalone_profit_exit_accounting_interruption_quarantines_no_replay(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys)
    engine=h.core.execution_engine
    h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=h.failure_exit_price,
        symbol='JPM',side='SELL',orderId=72,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=0;h.native_open_orders.clear()
    original=engine._record_fill_and_position
    def interrupted(*a,**kw):original(*a,**kw);raise RuntimeError('synthetic profit accounting interruption')
    monkeypatch.setattr(engine,'_record_fill_and_position',interrupted)
    with pytest.raises(RuntimeError,match='synthetic profit accounting interruption'):
        engine.collect_relationship_updates(result_processor=lambda r:h.core._apply_execution_results_to_trade_management([r]))
    assert engine._native_quarantined and life.filled_qty==0 and life.exited_qty==1
    before=(len(engine.position_records),life.realized_pnl,engine.capital_authority.total_used_exposure)
    with pytest.raises(RuntimeError):engine.collect_relationship_updates()
    assert before==(len(engine.position_records),life.realized_pnl,engine.capital_authority.total_used_exposure)
    assert len(h.failure_conversions)==1


def test_standalone_profit_real_risk_and_execution_paper_only_backstops(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from dataclasses import replace
    from src.config import config_resolver
    from src.config.runtime_config import RunMode
    from src.strategies.ross_momentum.strategy_policy import standalone_profit_quote_evidence
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,fault='quote_unconfirmed')
    quote=replace(h.core.market_data_snapshot_manager.batch_snapshots(['JPM'])[0]['JPM'],market_data_type_confirmed=True)
    kwargs=dict(order_id=request.client_order_id,order=h.failure_owner,position=h.manager.snapshot_positions()['JPM'],
        registered=h.core.trade_registry.get_trade('JPM',request.trader_type),life=life,
        snapshot=h.core._latest_position_truth_snapshot,observed_at=h.life.clock.current,profit=True,quote=quote)
    allowed=h.core.risk_engine.evaluate_selected_failure_exit(**kwargs)
    assert allowed.allowed and allowed.max_position_size==1
    overrides=dict(config_resolver._CONFIG_OVERRIDES)
    try:
        config_resolver.set_config_overrides(dict(overrides,RUN_MODE='READ_ONLY',RUN_MODE_EFFECTIVE='READ_ONLY'))
        assert not h.core.risk_engine.evaluate_selected_failure_exit(**kwargs).allowed
    finally:config_resolver.set_config_overrides(overrides)
    rule=h.manager.evaluate_selected_completed_profit(h.failure_owner,h.failure_bars,observed_at=h.life.clock.current,
        session_plan=request.management_session_plan,entry_fill_price=life.avg_fill_price)
    rule['profit_quote']=standalone_profit_quote_evidence(quote,symbol='JPM',milestone=h.profit_level,observed_at=h.life.clock.current)
    assert not h.core.execution_engine.request_selected_failure_exit(request.client_order_id,rule,decision=allowed)
    assert not h.failure_owner.get('pmh_failure_exit')  # Profit requires the final-commit guard.
    monkeypatch.setattr(h.core.execution_engine,'run_mode',RunMode.READ_ONLY)
    assert not h.core.execution_engine.request_selected_failure_exit(request.client_order_id,rule,decision=allowed)
    assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit')


def test_standalone_profit_common_contract_and_basis_missing_data_holds(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,fault='quote_unconfirmed')
    evaluate=lambda row,price=life.avg_fill_price:h.manager.evaluate_selected_completed_profit(row,h.failure_bars,
        observed_at=h.life.clock.current,session_plan=request.management_session_plan,entry_fill_price=price)
    assert evaluate(h.failure_owner)
    for change in ('missing_stamp','relationship','other_family','wrong_stop','wrong_invalidation','bad_occurrence','expired'):
        row=deepcopy(h.failure_owner)
        if change=='missing_stamp':row.pop('last_accounted_entry_fill_at')
        if change=='relationship':row['request']['relationship_context']={'profile':'BULL_FLAG_MICRO_2R_V1'}
        if change=='other_family':row['request']['setup_family_id']='RANGE_BREAK'
        if change=='wrong_stop':row['request']['stop_loss_price']+=.01
        if change=='wrong_invalidation':row['request']['invalidation_level']+=.01
        if change=='bad_occurrence':row['request']['setup_metadata']['canonical_result_index']=-1
        if change=='expired':row['pmh_management_expired']=True
        assert evaluate(row) is None
    for price in (None,True,float('nan'),float('inf'),0,request.stop_loss_price):
        assert evaluate(h.failure_owner,price) is None
    from dataclasses import asdict, replace
    from src.strategies.ross_momentum.strategy_policy import standalone_profit_quote_evidence
    quote=replace(h.core.market_data_snapshot_manager.batch_snapshots(['JPM'])[0]['JPM'],market_data_type_confirmed=True)
    facts=asdict(quote)
    assert standalone_profit_quote_evidence(facts,symbol='JPM',milestone=h.profit_level,observed_at=h.life.clock.current)
    facts.pop('data_quality_flags')
    assert standalone_profit_quote_evidence(facts,symbol='JPM',milestone=h.profit_level,observed_at=h.life.clock.current) is None


def test_standalone_failed_entry_preempts_unsubmitted_profit(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from dataclasses import replace
    from src.strategies.common.candles.candle_types import Candle
    from src.strategies.ross_momentum.strategy_policy import CENTRAL_STANDALONE_FAILURE_PROFILE
    h,request,life=central_failure_case(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG')
    failed=h.failure_bars[-1]
    milestone=life.avg_fill_price+2*(life.avg_fill_price-life.selected_stop_price)
    bid=milestone+.02;close=bid+.01
    later=Candle(bid,close+.01,bid-.01,close,1000,timestamp=failed.timestamp+timedelta(seconds=10))
    # Both immutable post-fill observations are completed on the next cycle;
    # bounded eight-second external advance retains existing scope freshness.
    delta=later.timestamp+timedelta(seconds=10)-h.life.clock.current
    assert timedelta(0)<delta<=timedelta(seconds=10)
    h.life.clock.current+=delta
    append_external_management_bar(h,'10s',later);h.failure_bars.append(later)
    original=h.core.market_data_snapshot_manager.batch_snapshots
    def quotes(symbols):
        values,errors=original(symbols)
        return {key:replace(value,last=close,bid=bid,ask=close+.01,market_timestamp_utc=h.life.clock.current,
            snapshot_complete=True,market_data_type='LIVE',returned_market_data_type='LIVE',market_data_type_confirmed=True)
            for key,value in values.items()},errors
    h.core.market_data_snapshot_manager.batch_snapshots=quotes
    assert h.core.run_once();capsys.readouterr()
    latch=h.failure_owner['pmh_failure_exit']
    assert latch['profile']==CENTRAL_STANDALONE_FAILURE_PROFILE and latch['bar_start']==failed.timestamp.isoformat()
    assert len(h.failure_conversions)==1 and 'milestone' not in latch
    h.failure_exit_price=bid;finish_failure_fill(h,life,capsys)
    assert life.filled_qty==0 and life.exited_qty==1



def test_standalone_profit_dispatch_restores_readonly_and_quarantines_in_fresh_process(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from src.strategies.ross_momentum.strategy_policy import STANDALONE_ONE_SHARE_PROFIT_PROFILE
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys)
    assert_readonly_selected_dispatch_restart(h,request,
        timeframe=request.setup_metadata['execution_stream']['execution_trigger_timeframe'],profile=STANDALONE_ONE_SHARE_PROFIT_PROFILE)
    assert len(h.failure_conversions)==1 and life.filled_qty==1 and life.exited_qty==0
    assert h.core.execution_engine.capital_authority.total_used_exposure==life.avg_fill_price


def test_standalone_profit_quote_expires_during_final_inventory_no_dispatch(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,fault='quote_aging')
    assert not h.failure_conversions
    assert h.failure_owner['pmh_failure_exit']['status']=='STP'
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert not h.failure_conversions and life.filled_qty==1
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert h.core.execution_engine.capital_authority.total_used_exposure==life.avg_fill_price


def test_standalone_profit_phase_expires_during_final_inventory_no_dispatch(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=late_cup(reassessment,monkeypatch,tmp_path,clock_time=(13,55,30))
    request=acknowledge_cup(h,capsys)
    life=confirm_selected_fill(h,request,capsys,family='CUP_HANDLE',fill_price=10.55,stop_price=10.3)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,family='CUP_HANDLE',
        prepared=(h,request,life),fault='phase_at_commit')
    assert not h.failure_conversions and h.failure_owner['pmh_management_expired']
    assert h.failure_owner['pmh_failure_exit']['status']=='STP'
    assert life.filled_qty==1 and h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']


def install_real_profit_amendment(h,monkeypatch):
    """Real amendment adapter; only SDK inventory/write transport is synthetic."""
    from src.brokers import ibkr_live_broker as broker_module
    from src.config import config_resolver
    from src.config.runtime_config import RunMode
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,IBKR_KILL_SWITCH=False))
    monkeypatch.setattr(broker_module,'datetime',h.life.clock)
    broker=object.__new__(broker_module.IbkrLiveBroker)
    broker.run_mode=RunMode.PAPER;broker.connection_manager=h.native_manager
    def inventory(**kwargs):
        assert kwargs=={'require_complete':True}
        h.life.clock.current+=timedelta(seconds=getattr(h,'profit_precommit_delay',0))
        return h.native_open_orders
    def dispatch(native_id,contract,order):
        assert native_id==72 and contract.symbol=='JPM' and contract.conId==123
        assert order.action=='SELL' and order.orderType=='MKT' and order.totalQuantity==1
        assert order.parentId==71 and order.orderRef=='PROTECT|'+h.failure_owner['request']['client_order_id']
        h.failure_conversions.append((native_id,deepcopy(contract),deepcopy(order)))
        assert len(h.failure_conversions)==1
        next(row for row in h.native_open_orders if row.orderId==72).order=deepcopy(order)
    monkeypatch.setattr(h.native_client,'openOrders',inventory)
    monkeypatch.setattr(h.native_client,'placeOrder',dispatch)
    monkeypatch.setattr(h.core.execution_engine._provider.broker,'convert_selected_stop_to_market',broker.convert_selected_stop_to_market)


def test_standalone_profit_real_adapter_final_guard_valid_writes_same_id(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,fault='real_final_valid')
    assert len(h.failure_conversions)==1 and h.failure_owner['pmh_failure_exit']['status']=='MKT'
    finish_failure_fill(h,life,capsys)
    assert life.filled_qty==0 and life.exited_qty==1 and len(h.failure_conversions)==1


def test_standalone_profit_bar_expires_during_final_inventory_no_dispatch(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,fault='bar_aging')
    assert not h.failure_conversions and h.failure_owner['pmh_failure_exit']['status']=='STP'
    assert life.filled_qty==1 and h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    before=(life.realized_pnl,len(h.core.execution_engine.position_records),h.core.execution_engine.capital_authority.total_used_exposure)
    for _ in range(3):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert not h.failure_conversions
    assert before==(life.realized_pnl,len(h.core.execution_engine.position_records),h.core.execution_engine.capital_authority.total_used_exposure)


@pytest.mark.parametrize('base,produced,cap',[(2,1,4),(3,2,4),(4,2,4),(6,3,4),(8,4,4),(8,4,1)])
def test_native_synthetic_requested_size_is_not_risk_ceiling(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,base,produced,cap):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=base,risk_cap=cap,synthetic_capital=800)
    intent,received,decision=h.evaluated[0]
    # Real producer, all native competition and actual downstream request.
    assert intent.position_size==base*.5
    assert intent.quantity==produced
    assert received['quantity']==produced
    assert len(h.registry_batches[-1][1])==33
    assert request.quantity==decision.max_position_size==min(produced,cap)
    assert life.filled_qty==life.stop.quantity==min(produced,cap)
    assert life.stop.trigger_price==10.63 and life.target is None
    assert request.take_profit_price is None and not request.relationship_context
    assert len(h.sent_native)==len(h.stop_requests)==1
    assert len(h.core.trade_registry.snapshot())==len(h.manager.snapshot_positions())==1
    h.life.clock.current+=timedelta(seconds=1)
    assert h.core.run_once();capsys.readouterr()
    assert len(h.sent_native)==len(h.stop_requests)==1
    assert life.filled_qty==min(produced,cap)


@pytest.mark.parametrize('base,partial',[(4,False),(6,False),(8,False),(6,True)])
def test_native_requested_multi_share_profit_stays_closed_until_coordination(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,base,partial):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=base,risk_cap=4,partial=partial,synthetic_capital=800)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    assert request.quantity==round(base*.5)
    assert life.filled_qty==(1 if partial else request.quantity)
    assert not h.failure_conversions and not h.failure_owner.get('pmh_failure_exit')
    assert len(h.stop_requests)==1
    assert h.stop_requests[0]['quantity']==life.filled_qty
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert request.take_profit_price is None and life.target is None


@pytest.mark.parametrize('base,filled',[(None,1),(4,2)])
def test_native_requested_size_oversized_fill_quarantines_before_ownership(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,base,filled):
    h,request,_=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=base,risk_cap=2,fill=False)
    assert request.quantity==h.evaluated[0][0].quantity==filled
    assert not h.stop_requests and not h.core.trade_registry.snapshot()
    h.facts[71]=dict(status='Filled',filled=filled+1,remaining=0,avgFillPrice=10.88)
    h.native_quantity[0]=filled+1
    h.life.clock.current+=timedelta(seconds=1)
    h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine
    assert engine._native_quarantined and engine._native_orders[request.client_order_id]['quarantine']
    assert not engine.position_records and not h.core.trade_registry.snapshot() and not h.manager.snapshot_positions()
    assert engine.post_fill_lifecycle.get_trade(request.client_order_id) is None
    assert not h.stop_requests and len(h.sent_native)==1


def test_native_default_request_one_ignores_larger_risk_ceiling(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=None,risk_cap=2)
    intent,received,decision=h.evaluated[0]
    assert intent.quantity==received['quantity']==request.quantity==decision.max_position_size==life.filled_qty==life.stop.quantity==1
    assert h.core.execution_engine.max_shares_per_order is None
    assert len(h.registry_batches[-1][1])==33



def test_native_requested_size_remains_subject_to_capital_clamp(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=8,risk_cap=4,synthetic_capital=400,expected_admitted=3)
    intent,received,decision=h.evaluated[0]
    assert intent.quantity==received['quantity']==4
    assert request.quantity==decision.max_position_size==life.filled_qty==life.stop.quantity==3
    assert h.core.execution_engine.max_shares_per_order is None
    assert len(h.sent_native)==len(h.stop_requests)==1


@pytest.mark.parametrize('fault',['missing','bool','over_base'])
def test_native_requested_size_malformed_quantity_is_denied(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,_,_=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=4,risk_cap=4,quantity_fault=fault)
    decision=h.evaluated[0][2]
    assert not decision.allowed and decision.execution_blocked and decision.max_position_size==0
    assert decision.reason_code=='INVALID_NATIVE_REQUESTED_QUANTITY'
    assert decision.overall_action=='BLOCK' and decision.decision_code=='REJECT'
    assert not h.core.execution_engine.position_records and not h.core.trade_registry.snapshot()


@pytest.mark.parametrize('base,quantity',[(4,2),(6,3),(8,4)])
def test_native_unit_stop_initial_ownership_and_each_stop_to_flat(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,base,quantity):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=base,risk_cap=4,synthetic_capital=800,unit_stops=True)
    engine=h.core.execution_engine
    assert request.selected_stop_units and life.selected_stop_units
    assert life.filled_qty==quantity and len(life.stop_legs)==len(h.stop_requests)==quantity
    assert len(h.registry_batches[-1][1])==33
    assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    children=[o for o in engine._native_orders.values() if o.get('protection_parent_order_id')]
    assert all(o['requested']==1 and o['close_role']=='PROTECTION' for o in children)
    assert sum(o['requested']-o['filled'] for o in children)==quantity
    state=h.core.storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
    assert all(leg.leg_id in state['orders'] for leg in life.stop_legs)
    for index,leg in enumerate(life.stop_legs):
        broker_id=int(leg.broker_order_id)
        h.facts[broker_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.63)
        h.native_quantity[0]-=1
        h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=broker_id]
        h.life.clock.current+=timedelta(seconds=1)
        completed=h.core.run_once();capsys.readouterr()
        assert completed, (life.filled_qty,[(x.broker_order_id,x.filled_quantity,x.status) for x in life.stop_legs],[(x.orderId,x.order.totalQuantity) for x in h.native_open_orders])
        assert life.filled_qty==quantity-index-1 and life.exited_qty==index+1
        assert sum(o['requested']-o['filled'] for o in children)==life.filled_qty
        if life.filled_qty:
            assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
        before=(len(engine.position_records),life.realized_pnl,engine.capital_authority.total_used_exposure)
        assert h.core.run_once();capsys.readouterr()
        assert before==(len(engine.position_records),life.realized_pnl,engine.capital_authority.total_used_exposure)
    assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert engine.capital_authority.total_used_exposure==0
    assert len(h.sent_native)==1 and len(h.stop_requests)==quantity


@pytest.mark.parametrize('fault',[1,2])
def test_native_unit_stop_unknown_submission_quarantines_without_retry(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True,unit_fault=fault)
    engine=h.core.execution_engine
    assert engine._native_quarantined and engine._failsafe_block_new_entries
    assert len(h.stop_requests)==fault
    state=h.core.storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
    children=[o for o in state['orders'].values() if o.get('protection_parent_order_id')]
    assert len(children)==fault and sum(o['requested'] for o in children)<=request.quantity
    assert all(o['status']=='DISPATCH_UNCERTAIN' for o in children)
    assert not engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    for _ in range(2):assert not h.core.run_once();capsys.readouterr()
    assert len(h.stop_requests)==fault and len(h.sent_native)==1



def test_native_unit_stop_partial_entry_then_terminal_fill_preserves_earlier_legs(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True,partial=True)
    engine=h.core.execution_engine
    assert life.filled_qty==len(life.stop_legs)==1 and request.quantity==4
    first=life.stop_legs[0]
    assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    h.facts[71]=dict(status='Filled',filled=4,remaining=0,avgFillPrice=10.88)
    h.native_quantity[0]=4
    h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=71]
    h.life.clock.current+=timedelta(seconds=1)
    assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==len(life.stop_legs)==len(h.stop_requests)==4
    assert life.stop_legs[0] is first and first.broker_order_id=='72'
    assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert not engine._native_orders[request.client_order_id].get('pmh_failure_exit')
    assert all(leg.trigger_price==request.stop_loss_price==10.63 for leg in life.stop_legs)


@pytest.mark.parametrize('fault',['missing','quantity','security','price','parent','ref','mkt','unknown','foreign'])
def test_native_unit_stop_remainder_inventory_fault_quarantines_without_repair(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=6,risk_cap=4,synthetic_capital=800,unit_stops=True)
    row=h.native_open_orders[-1]
    if fault=='missing':h.native_open_orders.pop()
    elif fault=='quantity':row.order.totalQuantity=2
    elif fault=='security':row.contract.conId=456
    elif fault=='price':row.order.auxPrice=10.62
    elif fault=='parent':row.order.parentId=99
    elif fault=='ref':row.order.orderRef='PROTECT|unrelated'
    elif fault=='mkt':row.order.orderType='MKT'
    elif fault=='unknown':row.orderState.status='UNKNOWN'
    else:
        foreign=deepcopy(row);foreign.orderId=99;h.native_open_orders.append(foreign)
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine
    assert engine._native_quarantined and engine._failsafe_block_new_entries
    assert not engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert len(h.stop_requests)==3 and life.filled_qty==3
    assert not h.core.run_once();capsys.readouterr()
    assert len(h.sent_native)==1 and len(h.stop_requests)==3


def test_native_unit_stop_simultaneous_authoritative_fills_account_before_remainder_check(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    for leg in life.stop_legs[:2]:
        h.facts[int(leg.broker_order_id)]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.63)
    h.native_quantity[0]=2
    h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId not in {72,73}]
    assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==life.exited_qty==2
    engine=h.core.execution_engine
    assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    before=(len(engine.position_records),life.realized_pnl,engine.capital_authority.total_used_exposure)
    assert h.core.run_once();capsys.readouterr()
    assert before==(len(engine.position_records),life.realized_pnl,engine.capital_authority.total_used_exposure)


def test_native_unit_stop_interrupted_exit_accounting_quarantines_without_replay(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    engine=h.core.execution_engine
    h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.63)
    h.native_quantity[0]=3
    h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=72]
    record=engine._record_fill_and_position
    def interrupt(*args,**kwargs):
        record(*args,**kwargs)
        raise RuntimeError('synthetic interruption after unit accounting')
    monkeypatch.setattr(engine,'_record_fill_and_position',interrupt)
    assert not h.core.run_once();capsys.readouterr()
    assert engine._native_quarantined
    before=(life.filled_qty,life.exited_qty,life.realized_pnl,len(engine.position_records),engine.capital_authority.total_used_exposure)
    for _ in range(2):assert not h.core.run_once();capsys.readouterr()
    assert before==(life.filled_qty,life.exited_qty,life.realized_pnl,len(engine.position_records),engine.capital_authority.total_used_exposure)
    assert len(h.stop_requests)==4



def test_native_unit_stop_cap_one_keeps_accepted_one_share_profit(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=8,risk_cap=1,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    assert request.quantity==1 and not request.selected_stop_units and not life.stop_legs
    assert len(h.failure_conversions)==1
    finish_failure_fill(h,life,capsys)
    assert life.filled_qty==0 and life.exited_qty==1
    assert h.core.execution_engine.capital_authority.total_used_exposure==0


@pytest.mark.parametrize('commit_change',['none','time','readonly_mode','execution','instance_readonly'])
def test_native_unit_stop_real_adapter_client_binds_before_sdk_write(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,commit_change):
    from src.brokers.ibkr_live_broker import IbkrLiveBroker
    from src.config.runtime_config import RunMode
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH',str(tmp_path/'unit-order-ids.json'))
    h,request,_=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=6,risk_cap=4,synthetic_capital=800,unit_stops=True,fill=False)
    engine=h.core.execution_engine;client=h.native_client
    from src.brokers import ibkr_live_broker as broker_module
    monkeypatch.setattr(broker_module,'datetime',h.life.clock)
    broker=object.__new__(IbkrLiveBroker);broker.run_mode=RunMode.PAPER;broker.connection_manager=h.native_manager
    monkeypatch.setattr(broker,'ensure_connection',lambda:pytest.fail('Implicit connection forbidden'))
    monkeypatch.setattr(engine._provider.broker,'place_stop_order',broker.place_stop_order)
    client.nextValidId(72)
    writes=[]
    def sdk_write(broker_id,contract,native):
        state=h.core.storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
        children=[v for v in state['orders'].values() if v.get('protection_parent_order_id')==request.client_order_id]
        assert any(v['broker_order_id']==str(broker_id) and v['requested']==1 and v['status']=='DISPATCH_UNCERTAIN' for v in children)
        assert native.orderType=='STP' and native.totalQuantity==1 and native.auxPrice==10.63
        writes.append(broker_id)
        h.stop_requests.append(dict(quantity=1,stop_price=native.auxPrice))
        external_contract=deepcopy(contract);external_contract.conId=123
        h.native_open_orders.append(NS(orderId=broker_id,contract=external_contract,order=deepcopy(native),orderState=NS(status='Submitted')))
    # Keep the actual SDK mutation audit AND encoder. Stub only the transport;
    # append independent synthetic inventory after a successful SDK call.
    from ibapi.client import EClient
    actual_sdk=_AUDITED_SDK_PLACE_ORDER
    assert getattr(actual_sdk,'_mutation_audited',False)
    wire=[]
    monkeypatch.setattr(client,'serverVersion_',180)
    monkeypatch.setattr(client,'sendMsg',lambda message:wire.append(message))
    def sdk_boundary(self,broker_id,contract,native):
        actual_sdk(self,broker_id,contract,native)
        sdk_write(broker_id,contract,native)
    monkeypatch.setattr(EClient,'placeOrder',sdk_boundary)
    if commit_change!='none':
        store=h.core.storage_engine.store_execution_order_state
        delayed=[False]
        def persist(*args,**kwargs):
            store(*args,**kwargs)
            if not delayed[0] and any(v.get('protection_parent_order_id') for v in args[1]['orders'].values()):
                delayed[0]=True
                if commit_change=='time':h.life.clock.current+=timedelta(seconds=16)
                elif commit_change=='instance_readonly':client.readonly_enabled=True
                else:
                    from src.config import config_resolver
                    change={'readonly_mode':('RUN_MODE','READ_ONLY'),'execution':('EXECUTION_ENABLED',False)}[commit_change]
                    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,**{change[0]:change[1]}))
        monkeypatch.setattr(h.core.storage_engine,'store_execution_order_state',persist)
    h.facts[71]=dict(status='Filled',filled=3,remaining=0,avgFillPrice=10.88)
    h.native_quantity[0]=3;h.native_open_orders.clear()
    completed=h.core.run_once();observed=capsys.readouterr().out
    if commit_change!='none':
        assert not completed and not writes and not wire and engine._native_quarantined
        assert delayed[0]
        if commit_change=='time':assert 'NATIVE_ORDER_SCOPE_STALE_OR_CHANGED' in observed
        elif commit_change=='execution':assert 'IBKR read-only enabled' in observed
        elif commit_change=='instance_readonly':assert 'IBKR instance read-only' in observed
        else:assert 'IBKR read-only enabled' in observed
        assert not h.core.run_once();capsys.readouterr()
        assert not writes
    else:
        assert completed and writes==[72,73,74] and len(wire)==3, observed[-2500:]
        life=engine.post_fill_lifecycle.get_trade(request.client_order_id)
        assert life.filled_qty==3 and engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
        assert_readonly_selected_dispatch_restart(h,request,timeframe='10s',profile='UNIT_STOPS')


@pytest.mark.parametrize('facet,value',[('symbol','OTHER'),('side','BUY'),('parentId',99),('orderRef','PROTECT|unrelated'),('filled',2),('filled',True),('remaining',float('nan'))])
def test_native_unit_stop_wrong_callback_binding_quarantines(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,facet,value):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=6,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.63)
    h.facts[72][facet]=value
    assert not h.core.run_once();capsys.readouterr()
    assert h.core.execution_engine._native_quarantined
    assert life.filled_qty==3 and life.exited_qty==0
    assert len(h.stop_requests)==3


def test_native_unit_stop_batch_cannot_recommit_mutated_request(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=6,risk_cap=4,synthetic_capital=800,unit_stops=True)
    engine=h.core.execution_engine
    child=engine._native_orders[life.stop_legs[0].leg_id]
    child['request']['target_model']='mutated after retention'
    assert not h.core.run_once();out=capsys.readouterr().out
    assert engine._native_quarantined and 'NATIVE_ORDER_RETAINED_BINDING_CHANGED' in out
    assert len(h.stop_requests)==3 and life.filled_qty==3



def test_native_unit_stop_late_original_entry_fill_after_stop_flat_is_separately_protected(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,old=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True,partial=True)
    h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.63)
    h.native_quantity[0]=0
    h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=72]
    assert h.core.run_once();capsys.readouterr()
    assert old.filled_qty==0 and old.exited_qty==1
    h.facts[71]=dict(status='Filled',filled=4,remaining=0,avgFillPrice=10.88)
    h.native_quantity[0]=3
    h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=71]
    h.life.clock.current+=timedelta(seconds=1)
    assert h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine;parent=engine._native_orders[request.client_order_id]
    life=engine.post_fill_lifecycle.get_trade(parent['protection_trade_id'])
    assert life is not old and old.filled_qty==0 and old.exited_qty==1
    assert life.filled_qty==len(life.stop_legs)==3
    assert {leg.broker_order_id for leg in life.stop_legs}=={'73','74','75'}
    assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert len(h.sent_native)==1 and len(h.stop_requests)==4
    assert not parent.get('pmh_failure_exit')


@pytest.mark.parametrize('family',PROFIT_FAMILIES)
def test_native_unit_stop_all_eligible_families_preserve_full_registry_contract(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,family,requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    intent,serialized,decision=h.evaluated[0]
    engine=h.core.execution_engine
    assert intent.setup_family_id==request.setup_family_id==family
    assert len(h.registry_batches[-1][1])==33
    from src.storage.serialization import to_jsonable
    assert serialized==vars(intent)
    assert request.setup_metadata==to_jsonable(intent.setup_metadata)
    assert 2<=request.quantity==life.filled_qty==decision.max_position_size<=min(intent.quantity,4)
    assert request.selected_stop_units and len(life.stop_legs)==request.quantity
    assert all(leg.quantity==1 and leg.trigger_price==request.stop_loss_price for leg in life.stop_legs)
    assert request.invalidation_level==intent.invalidation_level
    assert request.target_model==intent.target_model and request.take_profit_price is None and life.target is None
    assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert not engine._native_orders[request.client_order_id].get('pmh_failure_exit')
    before=(len(h.sent_native),len(h.stop_requests),len(engine.position_records),engine.capital_authority.total_used_exposure)
    assert h.core.run_once();capsys.readouterr()
    assert before==(len(h.sent_native),len(h.stop_requests),len(engine.position_records),engine.capital_authority.total_used_exposure)



def test_native_unit_stop_rejects_generic_whole_stop_mutation_and_repair(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=6,risk_cap=4,synthetic_capital=800,unit_stops=True)
    owner=h.core.execution_engine.post_fill_lifecycle
    replacement=owner.replace_stop(trade_id=life.trade_id,requested_by_strategy=life.strategy_id,new_stop_price=10.7,risk_authorized_override=True,override_reason='synthetic control')
    cancellation=owner.cancel_stop(trade_id=life.trade_id,requested_by_strategy=life.strategy_id,risk_authorized_override=True,reason='synthetic control')
    assert replacement==cancellation==dict(allowed=False,reason_code='SELECTED_UNIT_COORDINATION_REQUIRED')
    assert owner.evaluate_trailing(life.trade_id,11.5)==dict(updated=False,reason='SELECTED_UNIT_COORDINATION_REQUIRED')
    assert not owner._repair_missing_stop(life,'synthetic control')
    assert not owner._repair_missing_target(life,'synthetic control')
    assert len(h.stop_requests)==3 and all(leg.trigger_price==10.63 for leg in life.stop_legs)
    assert owner.assess_trade_stop_protection(life.trade_id)['protected']


@pytest.mark.parametrize('partial',[False,True])
def test_native_unit_stop_completed_two_r_keeps_discretionary_admission_closed(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,partial):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True,partial=partial)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    assert request.selected_stop_units and not h.failure_conversions
    assert not h.failure_owner.get('pmh_failure_exit')
    assert life.filled_qty==(1 if partial else 4) and life.exited_qty==0
    assert len(h.stop_requests)==life.filled_qty
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']


@pytest.mark.parametrize('terminal',['Rejected','Cancelled'])
@pytest.mark.parametrize('still_in_inventory',[False,True])
def test_native_unit_stop_terminal_unfilled_is_not_recertified_or_replaced(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,terminal,still_in_inventory):
    h,request,life=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=6,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h.facts[72]=dict(status=terminal,filled=0,remaining=1,avgFillPrice=0)
    if not still_in_inventory:h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=72]
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine
    child=engine._native_orders[life.stop_legs[0].leg_id]
    assert child['terminal'] and child['status']==terminal.upper() and child['filled']==0
    assert engine._native_quarantined and life.filled_qty==3 and life.exited_qty==0
    assert not engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert len(h.stop_requests)==3
    assert not h.core.run_once();capsys.readouterr()
    assert len(h.stop_requests)==3


@pytest.mark.parametrize('fault',['unknown','missing','smaller','larger','foreign','stale','future','account','side'])
def test_native_unit_stop_prewrite_truth_or_overlap_veto_sends_no_stop(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,_=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',requested_base=6,risk_cap=4,synthetic_capital=800,unit_stops=True,fill=False)
    h.facts[71]=dict(status='Filled',filled=3,remaining=0,avgFillPrice=10.88)
    h.native_quantity[0]={'missing':0,'smaller':2,'larger':4}.get(fault,3)
    h.native_open_orders.clear()
    if fault in {'foreign','side'}:
        h.native_open_orders.append(NS(orderId=99,contract=NS(symbol='JPM',conId=123),
            order=NS(orderType='STP',parentId=0,orderRef='unrelated',action='SELL' if fault=='foreign' else 'UNKNOWN',totalQuantity=1,auxPrice=10.63),orderState=NS(status='Submitted')))
    original=h.native_client.position_snapshot
    if fault=='unknown':monkeypatch.setattr(h.native_client,'position_snapshot',lambda:BrokerPositionResult(status='TIMEOUT'))
    if fault in {'stale','future','account'}:
        def malformed():
            result=original()
            return BrokerPositionResult(result.rows,'COMPLETE','OTHER' if fault=='account' else result.account,
                result.completed_at+timedelta(seconds=-16 if fault=='stale' else 1 if fault=='future' else 0))
        monkeypatch.setattr(h.native_client,'position_snapshot',malformed)
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine
    assert engine._native_quarantined and engine._failsafe_block_new_entries
    assert not h.stop_requests and len(h.sent_native)==1
    assert not h.core.run_once();capsys.readouterr()
    assert not h.stop_requests


def enroll_unit_management(h, monkeypatch, *, fault='none', relationship=False, price_revision=False):
    """Real adapter + audited SDK encoder; synthetic external inventory/wire only."""
    from src.config import config_resolver
    from src.brokers import ibkr_live_broker as bm
    from src.config.runtime_config import RunMode
    from ibapi.order import Order
    from ibapi.contract import Contract
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,
        **({'ROSS_SYNTHETIC_RELATIONSHIP_UNIT_PROFIT':True} if relationship else {'ROSS_SYNTHETIC_UNIT_MANAGEMENT':True}),
        IBKR_KILL_SWITCH=False))
    monkeypatch.setattr(bm, 'datetime', h.life.clock)
    broker=object.__new__(bm.IbkrLiveBroker);broker.run_mode=RunMode.PAPER;broker.connection_manager=h.native_manager
    client=h.native_client;engine=h.core.execution_engine
    monkeypatch.setattr(client,'serverVersion_',180)
    h.unit_wires=getattr(h,'unit_wires',[]);h.unit_writes=getattr(h,'unit_writes',[])
    for row in h.native_open_orders:
        native=Order()
        for key,value in vars(row.order).items():setattr(native,key,value)
        native.account='SYNTHETIC_TEST';native.clientId=999
        row.order=native
        contract=Contract();contract.symbol='JPM';contract.conId=123
        contract.secType='STK';contract.currency='USD';contract.exchange='SMART'
        row.contract=contract
    def inventory(**kwargs):
        assert kwargs=={'require_complete':True}
        if fault=='stale':h.life.clock.current+=timedelta(seconds=16)
        if fault=='guard_age':h.life.clock.current+=timedelta(seconds=2)
        if fault=='incomplete':raise RuntimeError('synthetic incomplete inventory')
        if relationship and fault=='optout':
            config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,
                ROSS_SYNTHETIC_RELATIONSHIP_UNIT_PROFIT=False))
        if relationship and fault=='epoch':client._position_connection_epoch+=1
        result=deepcopy(h.native_open_orders)
        if relationship and fault=='account':
            for row in result:row.order.account='UNRELATED_ACCOUNT'
        return result
    monkeypatch.setattr(client,'openOrders',inventory)
    monkeypatch.setattr(client,'sendMsg',h.unit_wires.append)
    def sdk(self,broker_id,contract,native):
        plan=engine._selected_order_plan(h.failure_owner['request']['client_order_id']) if relationship else None
        if plan is not None:
            persisted=h.core.storage_engine.fetch_management_state(h.manager._state_namespace)
            orders=persisted['plans'][plan.relationship_id]['orders']
        else:
            persisted=h.core.storage_engine.fetch_management_state('execution.native_orders.v1:PAPER')
            orders=persisted['orders']
        children=[row for row in orders.values() if row.get('broker_order_id')==str(broker_id)]
        key='stop_price_revision' if price_revision and native.orderType=='STP' else 'unit_amendment'
        assert len(children)==1 and children[0][key]['status']=='DISPATCH_UNCERTAIN'
        assert children[0]['requested']==native.totalQuantity==1
        assert native.orderType in ({'STP','MKT'} if price_revision else {'MKT'})
        if key=='stop_price_revision':assert native.auxPrice==children[0][key]['proposed_price']
        assert contract.conId==123 and native.parentId==71 and native.action=='SELL'
        _AUDITED_SDK_PLACE_ORDER(self,broker_id,contract,native)
        h.unit_writes.append((broker_id,deepcopy(native)))
        row=next(row for row in h.native_open_orders if row.orderId==broker_id)
        revision_count=sum(order.orderType=='STP' for _,order in h.unit_writes) if price_revision else 0
        if fault=='rejected' or (price_revision and fault=='second_rejected' and revision_count==2):
            raise RuntimeError('synthetic amendment329 rejected; original stop retained')
        row.order=deepcopy(native)
        if fault=='unknown' or (relationship and fault=='second_unknown' and len(h.unit_writes)==2) or (price_revision and fault=='second_unknown' and revision_count==2):
            row.orderState.status='PendingSubmit'
    monkeypatch.setattr(EClient,'placeOrder',sdk)
    monkeypatch.setattr(engine._provider.broker,'convert_selected_stop_to_market',broker.convert_selected_stop_to_market,raising=not relationship)
    if price_revision:
        monkeypatch.setattr(engine._provider.broker,'revise_selected_stop_price',broker.revise_selected_stop_price,raising=False)


def fill_unit_ids(h, life, capsys, ids, *, price=None):
    price=life.selected_stop_price if price is None else price
    for native_id in ids:
        h.facts[native_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=price,
            symbol='JPM',side='SELL',orderId=native_id,parentId=71,orderRef='PROTECT|'+life.trade_id)
        h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=native_id]
    h.native_quantity[0]-=len(ids)
    h.life.clock.current+=timedelta(seconds=1)
    # New external price facts may gap to S0; never revise completed bars.
    from dataclasses import replace
    quotes=h.core.market_data_snapshot_manager.batch_snapshots
    def current_quotes(symbols):
        values,errors=quotes(symbols)
        return {key:replace(value,last=price,bid=price,ask=price+.01,
            market_timestamp_utc=h.life.clock.current,asof_utc=h.life.clock.current)
            for key,value in values.items()},errors
    h.core.market_data_snapshot_manager.batch_snapshots=current_quotes
    for row in h.rows.values():row.update(last_price=price,bid=price,ask=price+.01)
    result=h.core.run_once();out=capsys.readouterr().out
    assert result,out[-5000:]


@pytest.mark.parametrize('family',PROFIT_FAMILIES)
def test_unit_coordination_failure_existing_ids_to_flat(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,family,
        requested_base=6 if family=='BULL_FLAG' else 8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared,clock_step=5)
    quantity=life.filled_qty
    assert h.failure_exit_price>life.selected_stop_price
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once(),capsys.readouterr().out[-5000:]
    capsys.readouterr()
    assert [identity for identity,_ in h.unit_writes]==list(range(72,72+quantity))
    assert len(h.unit_wires)==quantity and len(h.stop_requests)==quantity
    assert life.filled_qty==quantity and all(leg.close_role=='FAILURE' for leg in life.stop_legs)
    assert not h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    fill_unit_ids(h,life,capsys,list(range(72,72+quantity)),price=h.failure_exit_price)
    assert life.filled_qty==0 and life.exited_qty==quantity
    assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    assert h.core.execution_engine.capital_authority.total_used_exposure==0


@pytest.mark.parametrize('family',PROFIT_FAMILIES)
def test_unit_coordination_joined_partial_remainder_and_stop_to_flat(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,family):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,family,
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    original_quantity=life.filled_qty
    assert original_quantity>=2 and not h.failure_conversions
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once(),capsys.readouterr().out[-5000:]
    capsys.readouterr()
    action=h.failure_owner['unit_profit_exit']
    selected=[identity for identity,_ in h.unit_writes]
    assert len(selected)==original_quantity//2==action['reserved_quantity']
    assert len(h.unit_wires)==len(selected) and len(h.registry_batches[0][1])==33
    assert h.core.execution_engine.capital_authority.total_used_exposure==pytest.approx(original_quantity*life.avg_fill_price)
    assert action['entry_fill_price']==life.avg_fill_price and action['original_stop']==request.stop_loss_price
    assert action['occurrence']==request.setup_metadata and request.take_profit_price is life.target is None
    before=h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)
    assert not before['protected'] and before['confirmed_stop_quantity']==original_quantity-len(selected)
    # One unit execution is a real partial reduction of the aggregate action.
    fill_unit_ids(h,life,capsys,selected[:1],price=h.failure_exit_price)
    assert life.exited_qty==1 and life.filled_qty==original_quantity-1
    if len(selected)>1:
        assert action['status']=='MKT' and not action.get('last_accounted_fill_at')
        fill_unit_ids(h,life,capsys,selected[1:],price=h.failure_exit_price)
    children=[h.core.execution_engine._native_orders[leg_id] for leg_id in action['leg_ids']]
    assert action['accounted_fill_quantity']==len(selected)
    assert action['last_accounted_fill_at']==max(child['last_accounted_exit_fill_at'] for child in children)
    from decimal import Decimal
    assert Decimal(action['accounted_fill_notional'])==sum(Decimal(str(child['notional'])) for child in children)
    frozen_accounting=deepcopy(action)
    remainder=original_quantity-len(selected)
    assert life.filled_qty==h.manager.snapshot_positions()['JPM'].quantity==remainder
    assert h.core.execution_engine.capital_authority.total_used_exposure==pytest.approx(remainder*life.avg_fill_price)
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert all(row.order.orderType=='STP' and row.order.auxPrice==request.stop_loss_price for row in h.native_open_orders)
    for _ in range(2):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert len(h.unit_writes)==len(selected) and len(h.stop_requests)==original_quantity
    assert action==frozen_accounting  # Repeated Core cycles cannot renew the accounting clock.
    remaining_ids=[row.orderId for row in h.native_open_orders]
    fill_unit_ids(h,life,capsys,remaining_ids)
    assert life.filled_qty==0 and life.exited_qty==original_quantity
    assert h.core.execution_engine.capital_authority.total_used_exposure==0
    assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()


@pytest.mark.parametrize('fault',['rejected','unknown','stale','incomplete'])
def test_unit_coordination_uncertainty_keeps_latch_and_quarantine(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch,fault=fault)
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine
    assert engine._native_quarantined and h.failure_owner['quarantine']
    assert h.failure_owner['unit_profit_exit']['reserved_quantity']==2
    count=len(h.unit_writes)
    assert count==(1 if fault in {'rejected','unknown'} else 0)
    assert not h.core.run_once();capsys.readouterr()
    assert len(h.unit_writes)==count and life.filled_qty==4


def test_unit_coordination_odd_partial_then_actual_failure_to_flat(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=6,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    assert [item[0] for item in h.unit_writes]==[72]
    fill_unit_ids(h,life,capsys,[72],price=h.failure_exit_price)
    assert life.filled_qty==2 and h.failure_owner['protection_confirmed']
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life),clock_step=5)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    assert [item[0] for item in h.unit_writes]==[72,73,74]
    assert h.failure_owner['pmh_failure_exit']['reserved_quantity']==2
    fill_unit_ids(h,life,capsys,[73,74],price=h.failure_exit_price)
    assert life.filled_qty==0 and life.exited_qty==3
    assert h.core.execution_engine.capital_authority.total_used_exposure==0


def test_unit_coordination_failure_preempts_remaining_without_repeating_pending_profit(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    fill_unit_ids(h,life,capsys,[72],price=h.failure_exit_price)
    assert life.filled_qty==3 and not h.failure_owner['protection_confirmed']
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life),clock_step=5)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    assert [item[0] for item in h.unit_writes]==[72,73,74,75]
    assert h.failure_owner['pmh_failure_exit']['reserved_quantity']==2
    fill_unit_ids(h,life,capsys,[73,74,75],price=h.failure_exit_price)
    assert life.filled_qty==0 and life.exited_qty==4


def test_unit_coordination_partial_entry_is_protected_and_not_managed(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True,partial=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    assert not h.unit_writes and not h.failure_owner.get('unit_profit_exit')
    assert life.filled_qty==1 and h.failure_owner['protection_confirmed']


def test_unit_coordination_prior_stop_is_accounted_before_partial_reservation(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    # Callback/independent position and inventory arrive before the management cycle.
    h.facts[75]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=life.selected_stop_price,
        symbol='JPM',side='SELL',orderId=75,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=3;h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=75]
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    assert life.filled_qty==3 and life.exited_qty==1
    assert h.failure_owner['unit_profit_exit']['owned_quantity']==3
    assert h.failure_owner['unit_profit_exit']['reserved_quantity']==1
    assert [item[0] for item in h.unit_writes]==[72]


@pytest.mark.parametrize('fault',['persist','readonly','execution','readonly_mode','epoch','wrong_account','wrong_client','wrong_total','unexpected_sibling_kind','position','partial_positions','callback'])
def test_unit_coordination_commit_and_final_inventory_changes_veto(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch)
    engine=h.core.execution_engine
    store=h.core.storage_engine.store_execution_order_state
    changed=[False]
    def commit(*args,**kwargs):
        result=store(*args,**kwargs)
        if not changed[0] and any(row.get('unit_amendment',{}).get('status')=='DISPATCH_UNCERTAIN'
                for row in args[1]['orders'].values()):
            changed[0]=True
            if fault=='persist':raise OSError('synthetic commit reply lost')
            elif fault=='readonly':h.native_client.readonly_enabled=True
            elif fault in {'execution','readonly_mode'}:
                from src.config import config_resolver
                change={'EXECUTION_ENABLED':False} if fault=='execution' else {'RUN_MODE':'READ_ONLY'}
                config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,**change))
            elif fault=='epoch':h.native_client._invalidate_position_queries()
            elif fault=='wrong_account':h.native_open_orders[-1].order.account='OTHER'
            elif fault=='wrong_client':h.native_open_orders[-1].order.clientId=998
            elif fault=='wrong_total':h.native_open_orders[-1].order.totalQuantity=2
            elif fault=='unexpected_sibling_kind':h.native_open_orders[-1].order.orderType='MKT'
            elif fault=='position':h.native_quantity[0]=3
            elif fault=='partial_positions':h.native_client.position_snapshot=lambda:BrokerPositionResult(status='PARTIAL')
            elif fault=='callback':
                h.facts[75]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=life.selected_stop_price,
                    symbol='JPM',side='SELL',orderId=75,parentId=71,orderRef='PROTECT|'+life.trade_id)
        return result
    monkeypatch.setattr(h.core.storage_engine,'store_execution_order_state',commit)
    assert not h.core.run_once();capsys.readouterr()
    assert changed[0] and not h.unit_wires and not h.unit_writes
    assert engine._native_quarantined and h.failure_owner['unit_profit_exit']
    assert not h.core.run_once();capsys.readouterr()
    assert not h.unit_wires


@pytest.mark.parametrize('fault',['missing','straddling','forming','future','stale','wick','quote_missing','quote_stale','quote_future','quote_incomplete','quote_below'])
def test_unit_coordination_completed_bar_and_quote_boundary_holds(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared,fault=fault)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    assert not h.unit_writes and not h.failure_owner.get('unit_profit_exit')
    assert h.failure_owner['protection_confirmed'] and life.filled_qty==4


def test_unit_coordination_dispatch_restart_is_readonly_quarantined(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    assert_readonly_selected_dispatch_restart(h,request,timeframe='10s',profile='UNIT_MANAGEMENT')
    assert life.filled_qty==4 and len(h.unit_writes)==2


def test_unit_coordination_reduction_accounting_interruption_has_no_replay(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine
    h.facts[72]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=h.failure_exit_price,
        symbol='JPM',side='SELL',orderId=72,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=3;h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=72]
    apply=engine._record_fill_and_position
    def interrupted(*args,**kwargs):
        apply(*args,**kwargs)
        raise RuntimeError('synthetic unit reduction accounting interrupted')
    monkeypatch.setattr(engine,'_record_fill_and_position',interrupted)
    with pytest.raises(RuntimeError,match='synthetic unit reduction accounting interrupted'):
        engine.collect_relationship_updates(result_processor=lambda r:h.core._apply_execution_results_to_trade_management([r]))
    assert engine._native_quarantined and life.exited_qty==1
    before=(life.realized_pnl,len(engine.position_records),engine.capital_authority.total_used_exposure,len(h.unit_writes))
    with pytest.raises(RuntimeError):engine.collect_relationship_updates()
    assert before==(life.realized_pnl,len(engine.position_records),engine.capital_authority.total_used_exposure,len(h.unit_writes))


@pytest.mark.parametrize('fault',['late_fill','error_callback','malformed_cumulative'])
def test_unit_coordination_post_write_callback_changes_never_replace_or_retry(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch)
    sdk=EClient.placeOrder
    def callback(self,native_id,contract,order):
        sdk(self,native_id,contract,order)
        if fault=='late_fill':
            h.facts[native_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=h.failure_exit_price,
                symbol='JPM',side='SELL',orderId=native_id,parentId=71,orderRef='PROTECT|'+life.trade_id)
            h.native_quantity[0]-=1
            h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=native_id]
        elif fault=='error_callback':
            # Actual callback owner records the rejection. Read its real facts,
            # retaining other fixture callbacks as independent external inputs.
            self._observe_order_id(native_id)
            self.error(native_id,329,'synthetic unsupported amendment')
            old=self.cached_order_status
            monkeypatch.setattr(self,'cached_order_status',lambda oid:IbkrClient.cached_order_status(self,oid) or old(oid))
        else:
            h.facts[native_id]=dict(status='Submitted',filled=0,remaining=1,avgFillPrice=0)
            h.facts[native_id+1]=dict(status='Submitted',filled=True,remaining=0,avgFillPrice=h.failure_exit_price)
    monkeypatch.setattr(EClient,'placeOrder',callback)
    assert not h.core.run_once();capsys.readouterr()
    assert h.core.execution_engine._native_quarantined
    assert len(h.unit_wires)==1 and len(h.stop_requests)==4
    assert life.filled_qty==4 and life.exited_qty==0 # No fabricated accounting/flat.
    assert not h.core.run_once();capsys.readouterr()
    assert len(h.unit_wires)==1


def test_unit_coordination_duplicate_then_regressing_fill_cannot_repeat_accounting(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    fill_unit_ids(h,life,capsys,[72],price=h.failure_exit_price)
    engine=h.core.execution_engine
    before=(life.filled_qty,life.exited_qty,life.realized_pnl,len(engine.position_records),engine.capital_authority.total_used_exposure)
    assert h.core.run_once();capsys.readouterr()
    assert before==(life.filled_qty,life.exited_qty,life.realized_pnl,len(engine.position_records),engine.capital_authority.total_used_exposure)
    h.facts[72].update(status='Submitted',filled=0,remaining=1,avgFillPrice=0)
    assert h.core.run_once();capsys.readouterr()
    assert not engine._native_quarantined
    child=next(row for row in engine._native_orders.values() if row.get('broker_order_id')=='72')
    assert child['terminal'] and child['filled']==1
    assert before==(life.filled_qty,life.exited_qty,life.realized_pnl,len(engine.position_records),engine.capital_authority.total_used_exposure)
    assert len(h.unit_writes)==2


def test_unit_coordination_retained_one_minute_pmh_to_protected_remainder_and_failure_flat(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h=trusted_steady_pmh(reassessment,monkeypatch,tmp_path,two_shares=True,unit_stops=True)
    request=acknowledge(h,capsys,expected_quantity=2)
    assert request.selected_stop_units and request.setup_metadata['execution_stream']['execution_trigger_timeframe']=='1m'
    assert request.setup_metadata['source_metadata']['premarket_reference']['status']=='COMPLETE_PRE'
    h.facts[71]=dict(status='Filled',filled=2,remaining=0,avgFillPrice=10.53)
    h.native_quantity[0]=2;h.native_open_orders.clear();h.life.clock.current+=timedelta(seconds=1)
    assert h.core.run_once();capsys.readouterr()
    life=h.core.execution_engine.post_fill_lifecycle.get_trade(request.client_order_id)
    assert life.filled_qty==2 and len(life.stop_legs)==2
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life))
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    assert len(h.unit_writes)==1 and h.failure_owner['unit_profit_exit']['reserved_quantity']==1
    fill_unit_ids(h,life,capsys,[72],price=h.failure_exit_price)
    assert life.filled_qty==1 and h.failure_owner['protection_confirmed']
    h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=(h,request,life),clock_step=5)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    assert [row[0] for row in h.unit_writes]==[72,73]
    fill_unit_ids(h,life,capsys,[73],price=h.failure_exit_price)
    assert life.filled_qty==0 and life.exited_qty==2
    assert h.core.execution_engine.capital_authority.total_used_exposure==0


@pytest.mark.parametrize('quantity_type',[float,__import__('decimal').Decimal])
def test_unit_coordination_actual_callback_owner_preserves_whole_sdk_quantity_types(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,quantity_type):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch)
    client=h.native_client
    client.orderStatus(71,'Filled',quantity_type(4),quantity_type(0),life.avg_fill_price,1,0,life.avg_fill_price,999,'',0)
    for native_id in (72,73,74,75):
        client.orderStatus(native_id,'Submitted',quantity_type(0),quantity_type(1),0,2,71,0,999,'',0)
    monkeypatch.setattr(client,'cached_order_status',lambda oid:IbkrClient.cached_order_status(client,oid))
    assert h.core.run_once();capsys.readouterr()
    assert [row[0] for row in h.unit_writes]==[72,73] and life.filled_qty==4


def test_unit_coordination_fresh_position_read_cannot_renew_expired_profit_quote(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from dataclasses import replace
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    quotes=h.core.market_data_snapshot_manager.batch_snapshots
    def aged_quote(symbols):
        values,errors=quotes(symbols)
        return {key:replace(value,market_timestamp_utc=h.life.clock.current-timedelta(seconds=14))
            for key,value in values.items()},errors
    h.core.market_data_snapshot_manager.batch_snapshots=aged_quote
    enroll_unit_management(h,monkeypatch,fault='guard_age')
    assert not h.core.run_once()
    out=capsys.readouterr().out
    assert 'SELECTED_EXIT_AUTHORIZATION_EXPIRED' in out
    assert h.core.execution_engine._native_quarantined
    assert not h.unit_wires and not h.unit_writes and life.filled_qty==4


@pytest.mark.parametrize('action',['profit','failure'])
def test_unit_coordination_confirmed_market_cannot_regress_to_stop_coverage(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,action):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True)
    if action=='profit':h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    else:h,request,life=pmh_failure_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared,clock_step=5)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine
    child=next(row for row in engine._native_orders.values() if row.get('broker_order_id')=='72')
    assert child['unit_amendment']['status']=='MKT_CONFIRMED'
    native=next(row for row in h.native_open_orders if row.orderId==72)
    native.order.orderType='STP';native.order.auxPrice=life.selected_stop_price
    before=(life.filled_qty,life.exited_qty,engine.capital_authority.total_used_exposure,len(h.unit_wires))
    h.life.clock.current+=timedelta(seconds=1)
    assert not h.core.run_once();capsys.readouterr()
    assert engine._native_quarantined and h.failure_owner['quarantine']
    assert child['unit_amendment']['status']=='MKT_CONFIRMED'
    assert before==(life.filled_qty,life.exited_qty,engine.capital_authority.total_used_exposure,len(h.unit_wires))
    assert not h.core.run_once();capsys.readouterr()
    assert len(h.unit_wires)==before[-1]


@pytest.mark.parametrize('facet',['account','client','epoch'])
def test_unit_coordination_post_write_confirmation_retains_original_scope(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,facet):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=4,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    assert life.filled_qty==2
    enroll_unit_management(h,monkeypatch)
    sdk=EClient.placeOrder
    def changed(self,native_id,contract,native):
        sdk(self,native_id,contract,native)
        row=next(row for row in h.native_open_orders if row.orderId==native_id)
        if facet=='account':row.order.account='OTHER'
        elif facet=='client':row.order.clientId=998
        else:client=h.native_client;client._invalidate_position_queries()
    monkeypatch.setattr(EClient,'placeOrder',changed)
    assert not h.core.run_once();capsys.readouterr()
    assert h.core.execution_engine._native_quarantined and len(h.unit_wires)==1
    assert life.filled_qty==2 and life.exited_qty==0
    assert h.failure_owner['unit_profit_exit']['status']=='RESERVED'
    assert not h.core.run_once();capsys.readouterr()
    assert len(h.unit_wires)==1


@pytest.mark.parametrize('status',['PendingSubmit','PendingCancel','Filled'])
def test_unit_coordination_post_write_callback_cannot_be_overwritten_by_inventory(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,status):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=4,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch)
    sdk=EClient.placeOrder
    def changed(self,native_id,contract,native):
        sdk(self,native_id,contract,native)
        count=1 if status=='Filled' else 0
        self.orderStatus(native_id,status,float(count),float(1-count),h.failure_exit_price if count else 0,
            2,71,h.failure_exit_price if count else 0,999,'',0)
        old=self.cached_order_status
        monkeypatch.setattr(self,'cached_order_status',lambda oid:IbkrClient.cached_order_status(self,oid) or old(oid))
        if count:h.native_quantity[0]=1
    monkeypatch.setattr(EClient,'placeOrder',changed)
    assert not h.core.run_once();capsys.readouterr()
    assert h.core.execution_engine._native_quarantined and len(h.unit_wires)==1
    assert life.filled_qty==2 and life.exited_qty==0 # No fabricated accounting.
    assert not h.core.run_once();capsys.readouterr()
    assert len(h.unit_wires)==1


@pytest.mark.parametrize('origin',['profit_remainder','prior_stop_remainder'])
def test_unit_single_remainder_never_requests_unactionable_profit_quotes(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,origin):
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'BULL_FLAG',
        requested_base=4,risk_cap=4,synthetic_capital=800,unit_stops=True)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    if origin=='profit_remainder':
        enroll_unit_management(h,monkeypatch)
        assert h.core.run_once();capsys.readouterr()
        fill_unit_ids(h,life,capsys,[72],price=h.failure_exit_price)
        assert h.failure_owner['unit_profit_exit']['status']=='FILLED'
    else:
        fill_unit_ids(h,life,capsys,[72])
        enroll_unit_management(h,monkeypatch)
        assert not h.failure_owner.get('unit_profit_exit')
    assert life.filled_qty==1 and h.failure_owner['protection_confirmed']
    active=[False];requests=[]
    manage=h.core._run_selected_failure_management
    def management(*args,**kwargs):
        active[0]=True
        try:return manage(*args,**kwargs)
        finally:active[0]=False
    quotes=h.core.market_data_snapshot_manager.batch_snapshots
    def snapshots(symbols):
        if active[0]:requests.append(tuple(symbols))
        return quotes(symbols)
    monkeypatch.setattr(h.core,'_run_selected_failure_management',management)
    monkeypatch.setattr(h.core.market_data_snapshot_manager,'batch_snapshots',snapshots)
    before=(life.filled_qty,life.exited_qty,len(h.unit_writes),len(h.stop_requests),
        h.core.execution_engine.capital_authority.total_used_exposure)
    for _ in range(2):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert requests==[]
    assert before==(life.filled_qty,life.exited_qty,len(h.unit_writes),len(h.stop_requests),
        h.core.execution_engine.capital_authority.total_used_exposure)


def micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys,*,family='MICRO_PULLBACK',fill_price=None,micro_fault=None,micro_clock=None,bull_clock=None):
    """Genuine all-registry native entry and accounted same-ID partial first."""
    prepared=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,family,
        requested_base=8,risk_cap=4,synthetic_capital=800,unit_stops=True,micro_fault=micro_fault,micro_clock=micro_clock,bull_clock=bull_clock)
    h,request,life=one_share_profit_case(reassessment,monkeypatch,tmp_path,capsys,prepared=prepared)
    enroll_unit_management(h,monkeypatch)
    assert h.core.run_once(),capsys.readouterr().out[-5000:]
    capsys.readouterr()
    partial_ids=[identity for identity,_ in h.unit_writes]
    fill_unit_ids(h,life,capsys,partial_ids,price=h.failure_exit_price if fill_price is None else fill_price)
    assert h.failure_owner['unit_profit_exit']['status']=='FILLED'
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    return h,request,life


def append_micro_cost_bar(h,request,life,capsys,*,fault='none',external_price=None):
    """New external completed history/quote facts, no prepared internal rule."""
    from dataclasses import replace
    from datetime import datetime
    from src.strategies.common.candles.candle_types import Candle
    seconds={'10s':10,'1m':60}[request.setup_metadata['execution_stream']['execution_trigger_timeframe']]
    now=h.life.clock.current
    start=now.replace(microsecond=0)+timedelta(seconds=(-int(now.timestamp()))%seconds)
    price=life.avg_fill_price-.02
    if fault=='equality':price=life.avg_fill_price
    if fault=='wick':price=life.avg_fill_price+.01
    if fault=='family_failure':price=request.setup_metadata['trigger_level']-.01
    if external_price is not None:price=external_price
    bar=Candle(price+.005,price+.02,price-.02,price,1000,timestamp=start)
    if fault=='straddling':bar=replace(bar,timestamp=datetime.fromisoformat(h.failure_owner['unit_profit_exit']['last_accounted_fill_at'])-timedelta(seconds=1))
    if fault=='stale':bar=replace(bar,timestamp=start-timedelta(hours=1))
    if fault=='future':bar=replace(bar,timestamp=start+timedelta(seconds=seconds+1))
    if fault=='forming':bar=replace(bar,timestamp=start+timedelta(seconds=5))
    if fault not in {'straddling','stale','future','forming','missing'}:
        append_external_management_bar(h,request.setup_metadata['execution_stream']['execution_trigger_timeframe'],bar)
    h.failure_bars=[] if fault=='missing' else [bar]
    quotes=h.core.market_data_snapshot_manager.batch_snapshots
    def current_quotes(symbols):
        values,errors=quotes(symbols)
        bid=life.avg_fill_price if fault=='quote_equality' else life.avg_fill_price+.01 if fault=='quote_reclaim' else price
        stamp=h.life.clock.current
        if fault=='quote_stale':stamp-=timedelta(hours=1)
        if fault=='quote_future':stamp+=timedelta(seconds=1)
        return {key:replace(value,last=price,bid=bid,ask=bid+.02,
            market_timestamp_utc=stamp,asof_utc=stamp,
            market_data_type_confirmed=fault!='quote_unconfirmed') for key,value in values.items()},errors
    h.core.market_data_snapshot_manager.batch_snapshots=current_quotes
    for row in h.rows.values():row.update(last_price=price,bid=price,ask=price+.02)
    end=start+timedelta(seconds=seconds)
    while h.life.clock.current<end:
        h.life.clock.current+=min(timedelta(seconds=5),end-h.life.clock.current)
        assert h.core.run_once(),capsys.readouterr().out[-5000:]
        capsys.readouterr()
    return bar,price


def enroll_micro_cost_failure():
    from src.config import config_resolver
    config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,
        ROSS_SYNTHETIC_MICRO_COST_FAILURE=True))


@pytest.mark.parametrize('clock_time',[pytest.param((14,5,30),id='RTH_OPEN_10s'),pytest.param((16,35,30),id='RTH_MID_1m')])
@pytest.mark.parametrize('variant',['none','red_pause'])
def test_micro_post_partial_cost_failure_native_core_to_flat(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,variant,clock_time):
    from src.strategies.ross_momentum.strategy_policy import STANDALONE_MICRO_COST_FAILURE_PROFILE
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys,micro_fault=variant,micro_clock=clock_time)
    assert request.management_session_plan==('RTH_MID' if clock_time[0]==16 else 'MORNING')
    assert request.setup_metadata['execution_stream']['execution_trigger_timeframe']==('1m' if clock_time[0]==16 else '10s')
    from src.market_data.session_pct_change import resolve_market_session_label
    expected_context=resolve_market_session_label(h.life.clock.current)
    assert h.focus_calls and all(row['session']==expected_context for row in h.focus_calls[0][0])
    original_quantity=life.filled_qty+life.exited_qty
    partial=deepcopy(h.failure_owner['unit_profit_exit'])
    assert partial['accounted_fill_quantity']==len(partial['leg_ids'])
    assert __import__('decimal').Decimal(partial['accounted_fill_notional'])>partial['accounted_fill_quantity']*__import__('decimal').Decimal(str(life.avg_fill_price))
    assert len(h.registry_batches[0][1])==33
    assert all(row.order.orderType=='STP' and row.order.auxPrice==request.stop_loss_price for row in h.native_open_orders)
    enroll_micro_cost_failure()
    bar,price=append_micro_cost_bar(h,request,life,capsys)
    assert request.setup_metadata['trigger_level']<bar.close<life.avg_fill_price
    latch=h.failure_owner.get('pmh_failure_exit')
    assert latch and latch['profile']==STANDALONE_MICRO_COST_FAILURE_PROFILE
    assert latch['entry_fill_price']==life.avg_fill_price and latch['original_stop']==request.stop_loss_price
    assert latch['occurrence']==request.setup_metadata and latch['last_accounted_profit_fill_at']==partial['last_accounted_fill_at']
    assert request.take_profit_price is life.target is None
    assert len(h.unit_writes)==original_quantity and len({identity for identity,_ in h.unit_writes})==original_quantity
    remaining=[row.orderId for row in h.native_open_orders]
    fill_unit_ids(h,life,capsys,remaining,price=price)
    assert life.filled_qty==0 and life.exited_qty==original_quantity
    assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
    engine=h.core.execution_engine
    assert engine.capital_authority.total_used_exposure==engine.capital_authority.total_reserved_capital==0
    for _ in range(2):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
    assert len(h.unit_writes)==original_quantity and len(h.stop_requests)==original_quantity
    assert h.failure_owner['unit_profit_exit']==partial


@pytest.mark.parametrize('fault',['equality','wick','straddling','forming','missing','stale','future',
    'quote_equality','quote_reclaim','quote_stale','quote_future','quote_unconfirmed'])
def test_micro_post_partial_cost_failure_external_boundaries_hold(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys)
    quantity=life.filled_qty;writes=len(h.unit_writes)
    enroll_micro_cost_failure()
    append_micro_cost_bar(h,request,life,capsys,fault=fault)
    assert not h.failure_owner.get('pmh_failure_exit'),fault
    assert len(h.unit_writes)==writes and life.filled_qty==quantity
    assert h.core.execution_engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
    assert all(row.order.auxPrice==request.stop_loss_price for row in h.native_open_orders)


@pytest.mark.parametrize('scope',['default_off','other_family','nonprofitable_partial'])
def test_micro_post_partial_cost_failure_enrollment_stays_closed(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,scope):
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys,
        family='BULL_FLAG' if scope=='other_family' else 'MICRO_PULLBACK',
        fill_price=10.88 if scope=='nonprofitable_partial' else None)
    if scope!='default_off':enroll_micro_cost_failure()
    writes=len(h.unit_writes);quantity=life.filled_qty
    append_micro_cost_bar(h,request,life,capsys)
    assert not h.failure_owner.get('pmh_failure_exit')
    assert len(h.unit_writes)==writes and life.filled_qty==quantity
    if scope=='nonprofitable_partial':
        action=h.failure_owner['unit_profit_exit']
        assert __import__('decimal').Decimal(action['accounted_fill_notional'])==action['accounted_fill_quantity']*__import__('decimal').Decimal(str(life.avg_fill_price))


def test_micro_post_partial_cost_failure_missing_accounting_and_binding_facts_hold(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from datetime import datetime
    from src.strategies.ross_momentum.strategy_policy import standalone_micro_cost_failure_basis
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys)
    enroll_micro_cost_failure()
    assert standalone_micro_cost_failure_basis(h.failure_owner,life.avg_fill_price)
    # Missing/tampered copies test pure policy only; retained owners stay intact.
    for key in ['last_accounted_fill_at','accounted_fill_notional','accounted_fill_quantity','occurrence','leg_ids']:
        owner=deepcopy(h.failure_owner);owner['unit_profit_exit'].pop(key)
        assert standalone_micro_cost_failure_basis(owner,life.avg_fill_price) is None,key
    for key,value in [('status','MKT'),('accounted_fill_notional',float('nan')),
            ('last_accounted_fill_at',datetime.now().isoformat()),('reserved_quantity',True)]:
        owner=deepcopy(h.failure_owner);owner['unit_profit_exit'][key]=value
        assert standalone_micro_cost_failure_basis(owner,life.avg_fill_price) is None,key
    owner=deepcopy(h.failure_owner);owner['request']['setup_family_id']='BULL_FLAG'
    assert standalone_micro_cost_failure_basis(owner,life.avg_fill_price) is None


def test_micro_post_partial_cost_failure_stop_fill_precedes_discretionary_exit(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys)
    # Qualifying history already exists with enrollment OFF. The next cycle
    # drains authoritative stops to flat before evaluating the new policy.
    append_micro_cost_bar(h,request,life,capsys)
    writes=len(h.unit_writes)
    enroll_micro_cost_failure()
    remaining=[row.orderId for row in h.native_open_orders]
    fill_unit_ids(h,life,capsys,remaining)
    assert life.filled_qty==0 and not h.failure_owner.get('pmh_failure_exit')
    assert len(h.unit_writes)==writes


def test_micro_post_partial_cost_failure_preserves_family_failure_priority(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from src.strategies.ross_momentum.strategy_policy import selected_completed_failure_profile
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys)
    enroll_micro_cost_failure()
    append_micro_cost_bar(h,request,life,capsys,fault='family_failure')
    assert h.failure_owner['pmh_failure_exit']['profile']==selected_completed_failure_profile(vars(request))


@pytest.mark.parametrize('fault',['rejected','unknown','guard_age'])
def test_micro_post_partial_cost_failure_uncertain_or_aged_write_never_retries(reassessment,monkeypatch,tmp_path,capsys,no_external_activity,fault):
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys)
    writes=len(h.unit_writes)
    # External bar arrives with enrollment OFF, then the real final-write path
    # encounters adverse inventory/SDK ordering at the next Core cycle.
    append_micro_cost_bar(h,request,life,capsys)
    enroll_micro_cost_failure();enroll_unit_management(h,monkeypatch,fault=fault)
    if fault=='guard_age':
        from dataclasses import replace
        quotes=h.core.market_data_snapshot_manager.batch_snapshots
        def aged_quotes(symbols):
            values,errors=quotes(symbols)
            return {key:replace(value,market_timestamp_utc=h.life.clock.current-timedelta(seconds=14)) for key,value in values.items()},errors
        h.core.market_data_snapshot_manager.batch_snapshots=aged_quotes
    assert not h.core.run_once();capsys.readouterr()
    engine=h.core.execution_engine
    assert engine._native_quarantined and engine._failsafe_block_new_entries
    assert h.failure_owner['pmh_failure_exit']['status']=='RESERVED'
    assert len(h.unit_writes)==writes+(0 if fault=='guard_age' else 1)
    assert not h.core.run_once();capsys.readouterr()
    assert len(h.unit_writes)==writes+(0 if fault=='guard_age' else 1)


def test_micro_post_partial_cost_failure_restart_retains_once_only_latch(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys)
    enroll_micro_cost_failure()
    append_micro_cost_bar(h,request,life,capsys)
    assert h.failure_owner['pmh_failure_exit']['status']=='MKT'
    assert_readonly_selected_dispatch_restart(h,request,timeframe='10s',profile='UNIT_MANAGEMENT')
    assert len(h.unit_writes)==life.filled_qty+life.exited_qty


def test_micro_post_partial_cost_failure_accounting_interruption_has_no_replay(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys)
    enroll_micro_cost_failure()
    _,price=append_micro_cost_bar(h,request,life,capsys)
    remaining=h.native_open_orders[0].orderId
    h.facts[remaining]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=price,
        symbol='JPM',side='SELL',orderId=remaining,parentId=71,orderRef='PROTECT|'+life.trade_id)
    h.native_quantity[0]=0;h.native_open_orders.clear()
    engine=h.core.execution_engine
    apply=engine._record_fill_and_position
    def interrupted(*args,**kwargs):
        apply(*args,**kwargs)
        raise RuntimeError('synthetic Micro cost failure accounting interrupted')
    monkeypatch.setattr(engine,'_record_fill_and_position',interrupted)
    with pytest.raises(RuntimeError,match='Micro cost failure accounting interrupted'):
        engine.collect_relationship_updates(result_processor=lambda r:h.core._apply_execution_results_to_trade_management([r]))
    assert engine._native_quarantined
    child=next(row for row in engine._native_orders.values() if row.get('broker_order_id')==str(remaining))
    assert not child.get('last_accounted_exit_fill_at')
    before=(life.realized_pnl,len(engine.position_records),engine.capital_authority.total_used_exposure,len(h.unit_writes))
    with pytest.raises(RuntimeError):engine.collect_relationship_updates()
    assert before==(life.realized_pnl,len(engine.position_records),engine.capital_authority.total_used_exposure,len(h.unit_writes))


def test_micro_post_partial_cost_failure_authoritative_partial_clock_and_entry_terminal_boundaries(reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    h,request,life=micro_post_partial_case(reassessment,monkeypatch,tmp_path,capsys)
    # Actual eligible external facts arrive while the separate enrollment is OFF.
    bar,_=append_micro_cost_bar(h,request,life,capsys)
    enroll_micro_cost_failure()
    evaluate=lambda owner:h.manager.evaluate_selected_micro_cost_failure(owner,[bar],
        observed_at=h.life.clock.current,session_plan=request.management_session_plan,entry_fill_price=life.avg_fill_price)
    assert evaluate(h.failure_owner)
    for stamp in [None,(h.life.clock.current+timedelta(seconds=1)).isoformat(),
            (bar.timestamp+timedelta(seconds=1)).isoformat()]:
        owner=deepcopy(h.failure_owner)
        owner['unit_profit_exit']['last_accounted_fill_at']=stamp
        assert evaluate(owner) is None
    for key,value in [('terminal',False),('filled',1),('protection_confirmed',False),('pmh_management_expired',True)]:
        owner=deepcopy(h.failure_owner);owner[key]=value
        assert evaluate(owner) is None,key
    assert not h.failure_owner.get('pmh_failure_exit')


def deliver_native_execution(h, *, native_id, execution_id, side, quantity, cumulative, price, average, timestamp,
        account='SYNTHETIC_TEST', client_id=None, con_id=123):
    """Independent synthetic broker execution, delivered to the real callback/cache."""
    from decimal import Decimal
    from ibapi.contract import Contract
    from ibapi.execution import Execution
    contract=Contract();contract.symbol='JPM';contract.conId=con_id;contract.secType='STK'
    contract.exchange='SMART';contract.currency='USD'
    execution=Execution();execution.orderId=native_id;execution.execId=execution_id
    execution.acctNumber=account;execution.clientId=h.native_client.client_id if client_id is None else client_id
    execution.side=side;execution.shares=Decimal(str(quantity));execution.cumQty=Decimal(str(cumulative))
    execution.price=price;execution.avgPrice=average;execution.time=timestamp.isoformat()
    h.native_client.execDetails(-1,contract,execution)


@pytest.mark.parametrize('limit,blocked',[(.24,True),(.25,True),(.26,False)])
def test_native_accounted_loss_reaches_actual_canonical_daily_limit(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,limit,blocked):
    import json
    from datetime import datetime
    from src.config import config_resolver
    h=late_pmh(reassessment,monkeypatch,tmp_path,fill_price=10.53)
    try:
        request=acknowledge(h,capsys)
        # Broker execution time is independently specified, not callback-read or
        # accounting wall-clock time. Existing source/confirmation fixtures stay real.
        entry_time=datetime(2026,10,20,13,35,42,tzinfo=timezone.utc)
        exit_time=datetime(2026,10,20,13,35,53,tzinfo=timezone.utc)
        deliver_native_execution(h,native_id=71,execution_id='loss-entry',side='BOT',quantity=1,
            cumulative=1,price=10.53,average=10.53,timestamp=entry_time)
        life=confirm_selected_fill(h,request,capsys,family='PREMARKET_HIGH_BREAK',fill_price=10.53,
            stop_price=request.stop_loss_price)
        core=h.core;engine=core.execution_engine
        assert len(h.registry_batches[0][1])==33
        for name,method in h.real_core_methods.items():assert getattr(core,name).__func__ is method
        canonical=core.trade_lifecycle_engine.get_trade(request.client_order_id)
        assert canonical is not None and canonical.quantity_open==1 and canonical.entry_avg_price==10.53
        assert canonical.stop_price==request.stop_loss_price and canonical.target_price is None
        assert canonical.opened_at==entry_time.isoformat()
        overrides=dict(config_resolver._CONFIG_OVERRIDES)
        overrides.update(DAILY_RISK_GOVERNOR_ENABLED=True,DAILY_RISK_MAX_LOSS_AMOUNT=limit,DAILY_RISK_INCLUDE_UNREALIZED=False)
        config_resolver.set_config_overrides(overrides)
        price=external_stop_facts(h,life)
        assert price==10.28
        deliver_native_execution(h,native_id=72,execution_id='loss-stop',side='SLD',quantity=1,
            cumulative=1,price=10.28,average=10.28,timestamp=exit_time)
        assert core.run_once();capsys.readouterr()
        canonical=core.trade_lifecycle_engine.get_trade(request.client_order_id)
        assert canonical.quantity_open==0 and canonical.quantity_closed==1
        assert canonical.side=='LONG' and canonical.gross_realized_pnl==pytest.approx(-.25)
        assert canonical.closed_at==exit_time.isoformat() and canonical.target_price is None
        assert life.filled_qty==0 and life.realized_pnl==pytest.approx(-.25)
        assert not core.trade_registry.snapshot() and not core.trade_management_engine.snapshot_positions()
        assert engine.capital_authority.total_reserved_capital==engine.capital_authority.total_used_exposure==0
        for _ in range(2):
            h.life.clock.current+=timedelta(seconds=1)
            assert core.run_once();capsys.readouterr()
        allowed=core._daily_risk_allows_new_entries(cycle_started_at=h.life.clock.current);capsys.readouterr()
        decision=core.daily_risk_governor.last_decision
        assert allowed is not blocked
        assert decision.realized_pnl==pytest.approx(-.25)
        assert (decision.daily_trade_count,decision.losing_trade_count,decision.consecutive_losses)==(1,1,1)
        assert decision.status.value==('MANAGED_ONLY' if blocked else 'ALLOW')
        assert decision.lock_status.value==('LOCKED' if blocked else 'UNLOCKED')
        assert len(h.sent_native)==len(h.stop_requests)==1
        assert not any(e.event_type=='TRADE_CLOSED' for e in core.event_collector.snapshot_all())
        events=core.storage_engine.fetch_trade_lifecycle_events()
        assert len(events)==2 and {e['execution_id'] for e in events}=={'loss-entry','loss-stop'}
        payloads=[json.loads(e['payload_json']) for e in events]
        assert all(p['native_identity']['account']=='SYNTHETIC_TEST' for p in payloads)
        assert all(p['native_identity']['root_order_id']==request.client_order_id for p in payloads)
        assert all(r['state']=='COMPLETE' for o in engine._native_orders.values() for r in o.get('canonical_feedback',[]))
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('details_order',['entry_late','exit_late','both_late'])
def test_native_missing_execution_details_veto_entries_but_keep_factual_stop_accounting(
        reassessment,monkeypatch,tmp_path,capsys,no_external_activity,details_order):
    from datetime import datetime
    from src.config import config_resolver
    h=late_pmh(reassessment,monkeypatch,tmp_path,fill_price=10.53)
    try:
        request=acknowledge(h,capsys)
        entry_time=datetime(2026,10,20,13,35,42,tzinfo=timezone.utc)
        exit_time=datetime(2026,10,20,13,35,53,tzinfo=timezone.utc)
        if details_order=='exit_late':
            deliver_native_execution(h,native_id=71,execution_id='delayed-entry',side='BOT',quantity=1,
                cumulative=1,price=10.53,average=10.53,timestamp=entry_time)
        life=confirm_selected_fill(h,request,capsys,family='PREMARKET_HIGH_BREAK',fill_price=10.53,
            stop_price=request.stop_loss_price)
        engine=h.core.execution_engine
        config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,
            DAILY_RISK_MAX_LOSS_AMOUNT=.26,DAILY_RISK_INCLUDE_UNREALIZED=False))
        if details_order!='exit_late':
            assert not h.core._daily_risk_allows_new_entries(cycle_started_at=h.life.clock.current);capsys.readouterr()
            decision=h.core.daily_risk_governor.last_decision
            assert decision.status.value=='MANAGED_ONLY' and decision.allows_existing_position_management
            assert not h.core.daily_risk_governor.state.recovered and not engine._native_quarantined
        external_stop_facts(h,life)
        if details_order=='entry_late':
            deliver_native_execution(h,native_id=72,execution_id='delayed-stop',side='SLD',quantity=1,
                cumulative=1,price=10.28,average=10.28,timestamp=exit_time)
        assert h.core.run_once();capsys.readouterr()
        # Known native stop facts remain authoritative even without canonical
        # execution details. This is no replay or guessed daily loss.
        assert life.filled_qty==0 and life.realized_pnl==pytest.approx(-.25)
        assert not h.manager.snapshot_positions() and not h.core.trade_registry.snapshot()
        assert engine.capital_authority.total_used_exposure==0 and not engine._native_quarantined
        assert not h.core._daily_risk_allows_new_entries(cycle_started_at=h.life.clock.current);capsys.readouterr()
        assert not h.core.daily_risk_governor.state.recovered
        if details_order!='exit_late':
            deliver_native_execution(h,native_id=71,execution_id='delayed-entry',side='BOT',quantity=1,
                cumulative=1,price=10.53,average=10.53,timestamp=entry_time)
        if details_order!='entry_late':
            deliver_native_execution(h,native_id=72,execution_id='delayed-stop',side='SLD',quantity=1,
                cumulative=1,price=10.28,average=10.28,timestamp=exit_time)
        for _ in range(2):
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
        canonical=h.core.trade_lifecycle_engine.get_trade(request.client_order_id)
        assert canonical.quantity_open==0 and canonical.gross_realized_pnl==pytest.approx(-.25)
        assert canonical.opened_at==entry_time.isoformat() and canonical.closed_at==exit_time.isoformat()
        assert h.core._daily_risk_allows_new_entries(cycle_started_at=h.life.clock.current);capsys.readouterr()
        assert h.core.daily_risk_governor.last_decision.realized_pnl==pytest.approx(-.25)
        assert h.core.daily_risk_governor.last_decision.daily_trade_count==1
        assert not engine._native_feedback_blocks_new_entries()
        assert len(h.core.storage_engine.fetch_trade_lifecycle_events())==2
        assert len(h.sent_native)==len(h.stop_requests)==1 and life.exited_qty==1
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('stage',['before_pair','lost_pair_ack'])
def test_native_uncertain_canonical_write_keeps_entry_veto_and_factual_exit(
        reassessment,monkeypatch,tmp_path,capsys,no_external_activity,stage):
    from datetime import datetime
    h=late_pmh(reassessment,monkeypatch,tmp_path,fill_price=10.53)
    try:
        request=acknowledge(h,capsys)
        actual=h.core.storage_engine.persist_native_lifecycle_feedback
        calls=[]
        def interrupted(*args,**kwargs):
            calls.append(stage)
            if stage=='lost_pair_ack':actual(*args,**kwargs)
            raise OSError('synthetic canonical '+stage)
        monkeypatch.setattr(h.core.storage_engine,'persist_native_lifecycle_feedback',interrupted)
        deliver_native_execution(h,native_id=71,execution_id='uncertain-entry',side='BOT',quantity=1,
            cumulative=1,price=10.53,average=10.53,timestamp=datetime(2026,10,20,13,35,42,tzinfo=timezone.utc))
        life=confirm_selected_fill(h,request,capsys,family='PREMARKET_HIGH_BREAK',fill_price=10.53,
            stop_price=request.stop_loss_price)
        engine=h.core.execution_engine
        assert len(calls)==1 and not engine._native_quarantined
        assert engine._native_orders[request.client_order_id]['canonical_feedback'][0]['state']=='UNCERTAIN'
        assert not h.core._daily_risk_allows_new_entries(cycle_started_at=h.life.clock.current);capsys.readouterr()
        assert h.core.daily_risk_governor.last_decision.allows_existing_position_management
        # Restoring storage is not recovery authority or permission to retry.
        monkeypatch.setattr(h.core.storage_engine,'persist_native_lifecycle_feedback',actual)
        external_stop_facts(h,life)
        deliver_native_execution(h,native_id=72,execution_id='uncertain-stop',side='SLD',quantity=1,
            cumulative=1,price=10.28,average=10.28,timestamp=datetime(2026,10,20,13,35,53,tzinfo=timezone.utc))
        for _ in range(3):
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
        assert life.filled_qty==0 and life.exited_qty==1 and life.realized_pnl==pytest.approx(-.25)
        assert engine.capital_authority.total_used_exposure==0 and not h.manager.snapshot_positions()
        assert not h.core.trade_registry.snapshot() and not engine._native_quarantined
        assert not h.core._daily_risk_allows_new_entries(cycle_started_at=h.life.clock.current);capsys.readouterr()
        assert not h.core.daily_risk_governor.state.recovered and engine._native_feedback_blocks_new_entries()
        assert len(calls)==1 and len(h.sent_native)==len(h.stop_requests)==1
        assert len(h.core.storage_engine.fetch_trade_lifecycle_events())==(1 if stage=='lost_pair_ack' else 0)
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_native_partial_stop_loss_reaches_daily_limit_before_final_flat(
        reassessment,monkeypatch,tmp_path,capsys,no_external_activity):
    from datetime import datetime
    from src.config import config_resolver
    h,request,_=small_central_owned(reassessment,monkeypatch,tmp_path,capsys,'PREMARKET_HIGH_BREAK',
        risk_cap=2,unit_stops=True,fill=False)
    try:
        deliver_native_execution(h,native_id=71,execution_id='two-entry',side='BOT',quantity=2,
            cumulative=2,price=10.53,average=10.53,timestamp=datetime(2026,10,20,13,35,42,tzinfo=timezone.utc))
        h.facts[71]=dict(status='Filled',filled=2,remaining=0,avgFillPrice=10.53)
        h.native_quantity[0]=2;h.native_open_orders.clear();h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
        engine=h.core.execution_engine;life=engine.post_fill_lifecycle.get_trade(request.client_order_id)
        assert life.filled_qty==2 and len(h.stop_requests)==2
        config_resolver.set_config_overrides(dict(config_resolver._CONFIG_OVERRIDES,
            DAILY_RISK_MAX_LOSS_AMOUNT=.20,DAILY_RISK_INCLUDE_UNREALIZED=False))
        for index,(native_id,price) in enumerate(((72,10.28),(73,10.23))):
            h.facts[native_id]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=price,
                symbol='JPM',side='SELL',orderId=native_id,parentId=71,orderRef='PROTECT|'+life.trade_id)
            h.native_quantity[0]-=1
            h.native_open_orders[:]=[row for row in h.native_open_orders if row.orderId!=native_id]
            deliver_native_execution(h,native_id=native_id,execution_id='two-stop-'+str(native_id),side='SLD',quantity=1,
                cumulative=1,price=price,average=price,timestamp=datetime(2026,10,20,13,35,43+index,tzinfo=timezone.utc))
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
            canonical=h.core.trade_lifecycle_engine.get_trade(request.client_order_id)
            assert canonical.quantity_open==life.filled_qty==1-index
            assert not h.core._daily_risk_allows_new_entries(cycle_started_at=h.life.clock.current);capsys.readouterr()
            decision=h.core.daily_risk_governor.last_decision
            assert decision.realized_pnl==pytest.approx(-.25 if index==0 else -.55)
            assert decision.daily_trade_count==decision.losing_trade_count==index
            if index==0:
                assert engine.post_fill_lifecycle.assess_trade_stop_protection(life.trade_id)['protected']
                assert engine.capital_authority.total_used_exposure==10.53
        for _ in range(2):
            h.life.clock.current+=timedelta(seconds=1);assert h.core.run_once();capsys.readouterr()
        assert life.exited_qty==2 and len(h.core.storage_engine.fetch_trade_lifecycle_events())==3
        assert engine.capital_authority.total_used_exposure==0 and not h.manager.snapshot_positions()
    finally:teardown_unsent_fixture(h,no_external_activity)
