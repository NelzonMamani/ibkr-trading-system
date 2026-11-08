"""Joined native PMH callback investigation. No production changes or real I/O."""
from copy import deepcopy
from datetime import timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from src.execution.execution_engine import ExecutionEngine
from src.execution.execution_providers import IbkrExecutionProvider
from src.ibkr.position_snapshot import BrokerPositionResult
from src.ibkr.mutation_audit import snapshot as mutations
from src.models.execution_result import ExecutionResult
from test_joined_core_pmh_paper_assessment import (
    paper_pmh, reassessment, lifecycle, _reset_config, forbid_io, no_external_activity,
)


def late_pmh(reassessment,monkeypatch,tmp_path,*,paper_factory=paper_pmh,position_case='complete_empty',
             fill_price=10.31,stop_price=10.3-max(.01,10.3*.001),expected_stop_quantity=1):
    facts={};reads=[];sent=[];stops=[];open_orders=[];quantity=[0]
    def cached(order_id):
        reads.append(order_id)
        return deepcopy(facts.get(order_id,{}))
    def positions():
        return [NS(symbol='JPM',position=quantity[0],con_id=123,avgCost=fill_price,account='SYNTHETIC_TEST')] if quantity[0] else []
    def place_stop(**kw):
        stops.append(deepcopy(kw))
        assert (expected_stop_quantity is None or kw['quantity']==expected_stop_quantity) and kw['stop_price']==stop_price
        open_orders.append(NS(orderId=72,contract=NS(symbol='JPM',conId=123),
            order=NS(orderType='STP',parentId=71,orderRef='PROTECT|'+str(kw['trade_id']),action='SELL',totalQuantity=kw['quantity'],auxPrice=kw['stop_price']),
            orderState=NS(status='Submitted')))
        return dict(broker_order_id='72',status='Submitted',order_type='STP')
    from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionManager, IbkrConnectionConfig
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    native_client=IbkrClient('offline',0,999,5,'LIVE',True)
    # External connection state and callback facts only; the manager accessor,
    # provider and all internal decisions remain real.
    monkeypatch.setattr(native_client,'isConnected',lambda:True)
    monkeypatch.setattr(native_client,'cached_order_status',cached)
    connection=IbkrConnectionManager(IbkrConnectionConfig('offline',0,999,5,'LIVE',True,'PAPER'))
    connection._client=native_client
    for method in ('connect','ensure_connected','get_client','_connect_locked'):
        monkeypatch.setattr(connection,method,lambda *a,**k:pytest.fail('Implicit provider connection forbidden'))
    broker=NS(positions=positions,open_orders=lambda:list(open_orders),
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


def acknowledge(h,capsys):
    assert h.core.run_once();capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();out=capsys.readouterr().out
    assert len(h.sent_native)==len(h.artifacts)==len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0];request=h.sent_native[0]
    assert intent.setup_family_id==request.setup_family_id=='PREMARKET_HIGH_BREAK'
    assert not intent.relationship_context and not request.relationship_context
    assert not h.manager._relationship_plans and not h.manager.snapshot_positions()
    assert request.quantity==decision.max_position_size==1 and decision.allowed
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
    assert h.core.execution_engine.capital_authority.total_reserved_capital==pytest.approx(10.3)
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


@pytest.mark.parametrize('family',['FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK','VWAP_RECLAIM_CONTINUATION','MICRO_PULLBACK','CUP_HANDLE'])
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


@pytest.mark.parametrize('family',['FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK','VWAP_RECLAIM_CONTINUATION','MICRO_PULLBACK','CUP_HANDLE'])
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


@pytest.mark.parametrize('family',['FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK','VWAP_RECLAIM_CONTINUATION','MICRO_PULLBACK','CUP_HANDLE'])
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
    (family,case) for family in ('FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT',
        'FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK','VWAP_RECLAIM_CONTINUATION','MICRO_PULLBACK','CUP_HANDLE') for case in ('unknown','quantity_warning_larger','five')
] + [('OPENING_RANGE_BREAKOUT','partial'),('HOD_BREAK','partial'),('VWAP_RECLAIM_CONTINUATION','partial'),('MICRO_PULLBACK','partial'),('CUP_HANDLE','partial')])
def test_canonical_paper_truth_veto_has_zero_admission_effects(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,position_case,family):
    from test_joined_core_first_pullback import first_joined
    from test_abcd_production_handoff import abcd_joined
    from test_joined_core_pmh_readonly import key_joined, consolidation_joined, flat_top_joined, orb_joined, hod_joined, momentum_joined, micro_joined, cup_joined
    factories={'FIRST_PULLBACK':first_joined,'ABCD':abcd_joined,'KEY_LEVEL_BREAK':key_joined,
               'CONSOLIDATION_BREAKOUT':consolidation_joined,'FLAT_TOP_BREAKOUT':flat_top_joined,
               'OPENING_RANGE_BREAKOUT':orb_joined,'HOD_BREAK':hod_joined,'VWAP_RECLAIM_CONTINUATION':momentum_joined,'MICRO_PULLBACK':micro_joined,'CUP_HANDLE':cup_joined}
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


def confirm_selected_fill(h,request,capsys,*,family,fill_price,stop_price):
    engine=h.core.execution_engine
    metadata=deepcopy(h.evaluated[0][0].setup_metadata)
    retained=deepcopy(engine._native_orders[request.client_order_id]['request'])
    # External callback and independent broker position/order facts only.
    h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=fill_price)
    h.native_quantity[0]=1;h.native_open_orders.clear()
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
    assert life.filled_qty==1 and life.avg_fill_price==fill_price
    assert life.selected_stop_price==stop_price and life.stop.trigger_price==stop_price
    assert life.stop.quantity==1 and life.stop.broker_order_id=='72'
    assert life.target is life.selected_target_price is None
    assert engine.post_fill_lifecycle.assess_trade_stop_protection(request.client_order_id)['protected']
    order=engine._native_orders[request.client_order_id]
    assert order['protection_confirmed'] and order['request']==retained
    assert h.evaluated[0][0].setup_metadata==metadata
    assert h.truth[-1][1].healthy and not h.truth[-1][1].block_new_entries
    position=h.manager.snapshot_positions()['JPM']
    assert position.quantity==1 and position.setup_family==family
    assert position.entry_price==fill_price and position.reference_order_id==request.client_order_id
    assert position.target_type=='DESCRIPTIVE_ONLY' and not position.trailing_active
    assert position.stop_loss_price==stop_price
    assert position.first_target_price is position.second_target_price is None
    assert not h.manager._relationship_plans
    assert engine.capital_authority.total_used_exposure==fill_price
    assert engine.capital_authority.total_reserved_capital==0
    assert not engine.strategy_allocation_authority.active_reservations
    for _ in range(2):
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
        assert len(engine.position_records)==len(h.core.trade_registry.snapshot())==1
        assert len(h.sent_native)==len(h.stop_requests)==1 and h.collect_calls[-1]==[]
        assert engine.capital_authority.total_used_exposure==fill_price
        assert engine.capital_authority.total_reserved_capital==0
        assert h.manager.snapshot_positions()['JPM'].quantity==1
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


STOP_FAMILIES=['PREMARKET_HIGH_BREAK','FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK',
    'CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT','HOD_BREAK',
    'VWAP_RECLAIM_CONTINUATION','MICRO_PULLBACK','CUP_HANDLE']


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
        kwargs['runtime_options']['config_overrides'].update(RISK_PROFILE='SMALL',RISK_MAX_POSITION_SIZE=2)
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


def late_cup(reassessment,monkeypatch,tmp_path):
    from test_joined_core_pmh_readonly import cup_joined
    def paper_cup(*args,**kwargs):return paper_pmh(*args,joined_factory=cup_joined,**kwargs)
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
