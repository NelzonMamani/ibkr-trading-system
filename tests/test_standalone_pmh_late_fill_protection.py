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
             fill_price=10.31,stop_price=10.3-max(.01,10.3*.001)):
    facts={};reads=[];sent=[];stops=[];open_orders=[];quantity=[0]
    def cached(order_id):
        reads.append(order_id)
        return deepcopy(facts.get(order_id,{}))
    def positions():
        return [NS(symbol='JPM',position=quantity[0],con_id=123,avgCost=fill_price,account='SYNTHETIC_TEST')] if quantity[0] else []
    def place_stop(**kw):
        stops.append(deepcopy(kw))
        assert kw['quantity']==1 and kw['stop_price']==stop_price
        open_orders.append(NS(orderId=72,contract=NS(symbol='JPM',conId=123),
            order=NS(orderType='STP',parentId=71,orderRef='PROTECT|'+str(kw['trade_id']),action='SELL',totalQuantity=1,auxPrice=kw['stop_price']),
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
            order=NS(orderType='MKT',parentId=0,orderRef=request.client_order_id,action='BUY',totalQuantity=1),
            orderState=NS(status='Submitted')))
        return ExecutionResult(symbol=request.symbol,trader_type=request.trader_type,attempted=True,
            status='Submitted',rationale='synthetic external acknowledgement',direction=request.direction,
            quantity=1,requested_quantity=1,filled_quantity=0,remaining_quantity=1,
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


@pytest.mark.parametrize('family',['FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT'])
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
        assert engine.capital_authority.total_reserved_capital==pytest.approx(entry)
        assert engine.capital_authority.total_used_exposure==0
        if fault in {'wrong_owner','malformed'}:assert engine._native_quarantined
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('family',['FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT'])
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


@pytest.mark.parametrize('family',['FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT','FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT'])
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
        assert engine.capital_authority.total_reserved_capital==pytest.approx(entry)
        assert engine.capital_authority.total_used_exposure==0
        assert engine.pending_book.due_orders(1000)==[]
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('family,position_case', [
    (family,case) for family in ('FIRST_PULLBACK','ABCD','KEY_LEVEL_BREAK','CONSOLIDATION_BREAKOUT',
        'FLAT_TOP_BREAKOUT','OPENING_RANGE_BREAKOUT') for case in ('unknown','quantity_warning_larger','five')
] + [('OPENING_RANGE_BREAKOUT','partial')])
def test_canonical_paper_truth_veto_has_zero_admission_effects(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,position_case,family):
    from test_joined_core_first_pullback import first_joined
    from test_abcd_production_handoff import abcd_joined
    from test_joined_core_pmh_readonly import key_joined, consolidation_joined, flat_top_joined, orb_joined
    factories={'FIRST_PULLBACK':first_joined,'ABCD':abcd_joined,'KEY_LEVEL_BREAK':key_joined,
               'CONSOLIDATION_BREAKOUT':consolidation_joined,'FLAT_TOP_BREAKOUT':flat_top_joined,
               'OPENING_RANGE_BREAKOUT':orb_joined}
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
                         pattern_id=None,allow_execution_touch=False):
    from test_joined_core_bull_micro import _cadence
    from src.scanner import scanner_runner as ross
    assert h.core.run_once();capsys.readouterr()
    h.life.clock.current+=timedelta(seconds=11)
    assert h.core.run_once();out=capsys.readouterr().out
    assert len(h.sent_native)==len(h.artifacts)==len(h.evaluated)==1,out
    intent,received,decision=h.evaluated[0];request=h.sent_native[0]
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
    if allow_execution_touch:assert execution['candles'][-1].close>=entry
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
