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


def late_pmh(reassessment,monkeypatch,tmp_path):
    facts={};reads=[];sent=[];stops=[];open_orders=[];quantity=[0]
    def cached(order_id):
        reads.append(order_id)
        return deepcopy(facts.get(order_id,{}))
    def positions():
        return [NS(symbol='JPM',position=quantity[0],con_id=123,avgCost=10.31,account='SYNTHETIC_TEST')] if quantity[0] else []
    def place_stop(**kw):
        stops.append(deepcopy(kw))
        assert kw['quantity']==1 and kw['stop_price']==10.3-max(.01,10.3*.001)
        open_orders.append(NS(orderId=72,contract=NS(symbol='JPM',conId=123),
            order=NS(orderType='STP',parentId=71,orderRef='PROTECT|'+str(kw['trade_id']),action='SELL',totalQuantity=1,auxPrice=kw['stop_price']),
            orderState=NS(status='Submitted')))
        return dict(broker_order_id='72',status='Submitted',order_type='STP')
    broker=NS(positions=positions,open_orders=lambda:list(open_orders),
        connection_manager=NS(optional_client=NS(cached_order_status=cached)),place_stop_order=place_stop)
    def provider_factory(**kw):
        return IbkrExecutionProvider(broker=broker,trade_registry=kw['trade_registry'],run_mode=kw['run_mode'])
    h=paper_pmh(reassessment,monkeypatch,tmp_path,'complete_empty',provider_factory=provider_factory)
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
    h.core.connection_manager._ibkr_connection_manager.existing_client.position_snapshot=snapshot
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


class NativePmhCachedUpdateNotIngested(AssertionError):
    """Precise retained owner-wiring blocker, not any other assertion failure."""


@pytest.mark.xfail(strict=True,raises=NativePmhCachedUpdateNotIngested,
    reason='active cached collector enumerates relationship plans only; standalone PMH has none')
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
        if h.reads_native!=[71]:
            assert h.reads_native==[] and h.facts[71]==dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
            assert len(h.collect_calls)==3 and all(r==[] for r in h.collect_calls)
            assert engine.position_records=={} and h.stop_requests==[]
            assert engine.capital_authority.total_reserved_capital==pytest.approx(10.3)
            assert engine.capital_authority.total_used_exposure==0
            snapshot,verdict=h.truth[-1]
            assert verdict.block_new_entries and verdict.critical_mismatch_count==1
            assert [m.mismatch_type for m in snapshot.mismatches]==['BROKER_ONLY_POSITION']
            assert snapshot.broker_positions['JPM'].quantity==1
            raise NativePmhCachedUpdateNotIngested('owned standalone native order71 callback never read')
        assert len(engine.position_records)==len(h.stop_requests)==1
    finally:teardown_unsent_fixture(h,no_external_activity)


@pytest.mark.parametrize('evidence',['missing','pending','malformed','unrelated'])
def test_unconsumed_cache_evidence_never_manufactures_fill_or_releases_ownership(reassessment,monkeypatch,
        tmp_path,capsys,no_external_activity,evidence):
    h=late_pmh(reassessment,monkeypatch,tmp_path)
    try:
        acknowledge(h,capsys)
        if evidence=='pending':h.facts[71]=dict(status='PendingSubmit',filled=0,remaining=1)
        if evidence=='malformed':h.facts[71]=dict(status='Filled',filled=float('nan'),remaining=-1,avgFillPrice='bad')
        if evidence=='unrelated':h.facts[999]=dict(status='Filled',filled=1,remaining=0,avgFillPrice=10.31)
        for _ in range(2):
            h.life.clock.current+=timedelta(seconds=1)
            assert h.core.run_once();capsys.readouterr()
            assert len(h.sent_native)==1 and not h.manager._relationship_plans
            assert h.reads_native==[] and all(r==[] for r in h.collect_calls)
            assert not h.core.trade_registry.snapshot() and not h.core.execution_engine.position_records
            assert not h.manager.snapshot_positions() and h.stop_requests==[]
            assert h.core.execution_engine.capital_authority.total_reserved_capital==pytest.approx(10.3)
            assert h.core.execution_engine.capital_authority.total_used_exposure==0
            assert all(v.healthy and not v.block_new_entries for _,v in h.truth)
        assert h.core.execution_engine.capital_authority.capital_scope is None
        assert h.core.execution_engine.capital_authority._capital_writer is None
        assert no_external_activity==[] and mutations()==dict(place=0,modify=0,cancel=0)
    finally:teardown_unsent_fixture(h,no_external_activity)
