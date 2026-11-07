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


@pytest.mark.parametrize('fault',['missing','unrelated','wrong_owner','malformed'])
def test_first_callback_fault_cannot_create_position_or_protection(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,fault):
    h=late_first(reassessment,monkeypatch,tmp_path)
    try:
        acknowledge_first(h,capsys);engine=h.core.execution_engine
        facts=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.55)
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
        assert engine.capital_authority.total_reserved_capital==pytest.approx(10.42)
        assert engine.capital_authority.total_used_exposure==0
        if fault in {'wrong_owner','malformed'}:assert engine._native_quarantined
    finally:teardown_unsent_fixture(h,no_external_activity)


def test_first_interrupted_accounting_keeps_facts_and_blocks_replay(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity):
    h=late_first(reassessment,monkeypatch,tmp_path)
    try:
        request=acknowledge_first(h,capsys);engine=h.core.execution_engine
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.55)
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
        assert before==(1,1,10.55)
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


def test_first_uncertain_ack_keeps_reservation_without_resubmission(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity):
    h=late_first(reassessment,monkeypatch,tmp_path)
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
        assert h.evaluated[0][0].setup_family_id=='FIRST_PULLBACK' and h.evaluated[0][2].allowed
        assert not h.execution_results[0].submission_confirmed()
        for _ in range(2):
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
        assert len(h.sent_native)==1 and not h.stop_requests
        assert not engine.position_records and not h.manager.snapshot_positions()
        assert engine.capital_authority.total_reserved_capital==pytest.approx(10.42)
        assert engine.capital_authority.total_used_exposure==0
        assert engine.pending_book.due_orders(1000)==[]
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('position_case',['unknown','quantity_warning_larger','five'])
def test_first_paper_truth_veto_has_zero_admission_effects(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,position_case):
    from test_joined_core_first_pullback import first_joined
    h=paper_pmh(reassessment,monkeypatch,tmp_path,position_case,joined_factory=first_joined)
    try:
        assert h.core.run_once();capsys.readouterr()
        h.life.clock.current+=timedelta(seconds=11)
        assert h.core.run_once();capsys.readouterr()
        raw=[i for batch in h.batches for i in batch]
        assert len(raw)==1 and raw[0].setup_family_id=='FIRST_PULLBACK'
        assert raw[0].decision_id is None and h.truth[-1][1].block_new_entries
        assert h.artifacts==h.evaluated==h.execution_calls==h.boundaries==h.reserves==[]
        engine=h.core.execution_engine
        assert not engine.position_records and not engine.capital_authority.active_reservations
        assert not engine.strategy_allocation_authority.active_reservations
        assert engine.capital_authority.total_reserved_capital==engine.capital_authority.total_used_exposure==0
        snapshot,verdict=h.truth[-1]
        if position_case=='unknown':assert snapshot.snapshot_status=='UNKNOWN'
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
    assert request.setup_family_id==intent.setup_family_id=='FIRST_PULLBACK'
    assert decision.allowed and not decision.execution_blocked and decision.run_mode=='PAPER'
    assert intent.decision_id==decision.decision_id==artifact.decision_id
    assert request.client_order_id.startswith(intent.decision_id)
    assert request.quantity==decision.max_position_size==1
    assert request.trigger_id==intent.trigger_id==decision.trigger_id
    assert (intent.entry_price,intent.stop_loss_price,intent.invalidation_level)==(10.42,10.15,10.15)
    # Native request is a market order; measured entry belongs to intent/risk.
    assert request.order_type=='MKT'
    assert (request.stop_loss_price,request.invalidation_level)==(10.15,10.15)
    assert not request.relationship_context and not h.manager._relationship_plans
    source,results=h.registry_batches[-1]
    index=intent.setup_metadata['canonical_result_index'];selected=results[index]
    assert selected.setup_id=='P_FIRST_PULLBACK' and selected.detected
    assert (selected.trigger_level,selected.stop_level,selected.invalidation_level)==(10.42,10.15,10.15)
    assert request.target_model==intent.target_model==selected.target_suggestion
    assert request.take_profit_price is intent.take_profit_price is None
    payload,execution,trigger=h.first_triggers[-1]
    assert payload['canonical_result_index']==index and trigger['trigger_ready_now']
    assert execution['candles'][-1].close>10.42
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
    assert engine.capital_authority.total_reserved_capital==pytest.approx(10.42)
    assert engine.capital_authority.total_used_exposure==0
    assert engine.capital_authority.capital_scope is None
    assert engine.capital_authority._capital_writer is None
    return request


@pytest.mark.parametrize('market_fault',['none','forming_confirmation_source'])
def test_native_first_later_fill_reconciles_selected_initial_stop(reassessment,monkeypatch,tmp_path,
        capsys,no_external_activity,market_fault):
    h=late_first(reassessment,monkeypatch,tmp_path,market_fault=market_fault)
    try:
        request=acknowledge_first(h,capsys);engine=h.core.execution_engine
        metadata=deepcopy(h.evaluated[0][0].setup_metadata)
        retained=deepcopy(engine._native_orders[request.client_order_id]['request'])
        source=h.registry_batches[-1][0]
        assert all(b.timestamp+timedelta(minutes=1)<=source.observed_at_utc for b in source.candles[-6:-1])
        if market_fault=='forming_confirmation_source':
            assert source.candles[-1].timestamp<=source.observed_at_utc<source.candles[-1].timestamp+timedelta(minutes=1)
        # External callback and independent broker position/order facts only.
        h.facts[71]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.55)
        h.native_quantity[0]=1;h.native_open_orders.clear()
        h.life.clock.current+=timedelta(seconds=1)
        assert h.core.run_once();capsys.readouterr()
        assert h.reads_native==[71] and len(h.collect_calls[-1])==1
        assert len(engine.position_records)==len(h.core.trade_registry.snapshot())==1
        assert len(h.sent_native)==len(h.stop_requests)==1
        life=engine.post_fill_lifecycle.get_trade(request.client_order_id)
        assert life.filled_qty==1 and life.avg_fill_price==10.55
        assert life.selected_stop_price==10.15 and life.stop.trigger_price==10.15
        assert life.stop.quantity==1 and life.stop.broker_order_id=='72'
        assert life.target is life.selected_target_price is None
        assert engine.post_fill_lifecycle.assess_trade_stop_protection(request.client_order_id)['protected']
        order=engine._native_orders[request.client_order_id]
        assert order['protection_confirmed'] and order['request']==retained
        assert h.evaluated[0][0].setup_metadata==metadata
        assert h.truth[-1][1].healthy and not h.truth[-1][1].block_new_entries
        position=h.manager.snapshot_positions()['JPM']
        assert position.quantity==1 and position.setup_family=='FIRST_PULLBACK'
        assert position.entry_price==10.55 and position.reference_order_id==request.client_order_id
        assert position.target_type=='DESCRIPTIVE_ONLY' and not position.trailing_active
        assert position.stop_loss_price==10.15
        assert position.first_target_price is position.second_target_price is None
        assert not h.manager._relationship_plans
        assert engine.capital_authority.total_used_exposure==10.55
        assert engine.capital_authority.total_reserved_capital==0
        assert not engine.strategy_allocation_authority.active_reservations
        for _ in range(2):
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
            assert len(engine.position_records)==len(h.core.trade_registry.snapshot())==1
            assert len(h.sent_native)==len(h.stop_requests)==1 and h.collect_calls[-1]==[]
            assert engine.capital_authority.total_used_exposure==10.55
            assert engine.capital_authority.total_reserved_capital==0
            assert h.manager.snapshot_positions()['JPM'].quantity==1
            assert order['request']==retained and h.reserves==['allocation','capital']
    finally:teardown_unsent_fixture(h,no_external_activity)
