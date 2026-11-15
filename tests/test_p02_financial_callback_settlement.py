"""Actual callback/retained-owner settlement; never P02 entry permission."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from ibapi.contract import Contract
from ibapi.execution import Execution
from ibapi.order import Order
from ibapi.order_state import OrderState
from ibapi.commission_report import CommissionReport

from src.brokers.base_broker import BrokerOrderRequest
from src.core.active_trade_registry import ActiveTradeRegistry
from src.core.capital_management_authority import CapitalManagementAuthority
from src.core.strategy_capital_allocation_authority import StrategyCapitalAllocationAuthority
from src.core.event_collector import EventCollector
from src.core.orchestrator import CoreOrchestrator
from src.execution.post_fill_lifecycle_engine import PostFillLifecycleEngine
from src.execution.trade_management_engine import TradeManagementEngine
from src.models.execution_result import ExecutionResult
from src.core.engines.trade_lifecycle_engine import NativeRoundtripFeeObservation
from src.ibkr.mutation_audit import snapshot as mutations
from test_p02_observable_local_cooldown import (
    local_component, NOW, ACCOUNT, _observe, _settle,
    native_execution_client, no_external_activity, forbid_io, _reset_config,
)
from test_p02_local_native_guard import _source_request_encoder


@pytest.fixture
def financial_component(local_component, monkeypatch, request):
    """Controlled retained Ross request; no Core construction, RiskDecision or BUY."""
    from src.execution import execution_engine as execution_module
    from src.execution import post_fill_lifecycle_engine as protection_module
    from src.execution import trade_management_engine as management_module
    from src.adapters.brokers.ibkr import ibkr_client as native_module
    class ClockMeta(type):
        def __instancecheck__(cls, value):
            return isinstance(value, datetime)
    class Clock(datetime, metaclass=ClockMeta):
        current = NOW
        @classmethod
        def now(cls, tz=None):
            return cls.current if tz is None else cls.current.astimezone(tz)
    for module in (execution_module, protection_module, management_module, native_module):
        monkeypatch.setattr(module, 'datetime', Clock)
    requested_quantity = getattr(request, 'param', 1)
    assert requested_quantity in {1, 2}  # Explicit controlled owner fixture, not sizing/admission.
    h = local_component()
    h.clock = Clock
    engine, client, broker = h.engine, h.client, h.engine._provider.broker
    engine.trade_registry = ActiveTradeRegistry()
    engine._provider.trade_registry = engine.trade_registry
    engine.post_fill_lifecycle = PostFillLifecycleEngine(run_mode='PAPER',
        execution_provider=engine._provider, storage_engine=h.storage)
    engine._p02_bind_financial_owners()
    engine.relationship_manager = TradeManagementEngine(persistence_adapter=h.storage,
        state_namespace='PAPER')
    engine.capital_authority = CapitalManagementAuthority(run_mode='PAPER', storage_engine=h.storage)
    engine.strategy_allocation_authority = StrategyCapitalAllocationAuthority(run_mode='PAPER', storage_engine=h.storage)
    assert engine.capital_authority.capital_scope is None
    engine.execution_enabled = True
    engine.current_tick = 1
    engine.event_collector = EventCollector()
    engine.position_records = {}
    engine._order_trace_stages = {}
    engine._require_exit_stage = set()
    engine._prospective_decisions_by_order_id = {}
    engine._capital_decisions_by_order_id = {}
    engine._strategy_allocation_decisions_by_order_id = {}
    engine._native_processing_results = set()
    engine.execution_integrity_flag = False
    engine._native_scope = None
    core = CoreOrchestrator.__new__(CoreOrchestrator)
    core.execution_engine = engine
    core.trade_management_engine = engine.relationship_manager
    h.factual_core = core
    h.contract = Contract(); h.contract.conId = 123; h.contract.symbol = 'JPM'
    h.contract.secType = 'STK'; h.contract.currency = 'USD'; h.contract.exchange = 'SMART'
    h.orders = {}; h.transport_acks = []; h.stop_acks = []; h.quantity = 0

    def ack(native_id, request, *, parent=0, stop=None, quantity=None):
        order = Order(); order.orderId = native_id; order.action = 'SELL' if stop is not None else 'BUY'
        order.orderType = 'STP' if stop is not None else request.order_type
        order.totalQuantity = request.quantity if quantity is None else quantity; order.parentId = parent
        order.orderRef = 'PROTECT|' + request.client_order_id if stop is not None else request.client_order_id
        order.account = ACCOUNT; order.clientId = client.client_id
        order.tif = 'GTC' if stop is not None else 'DAY'; order.outsideRth = True
        order.transmit = True
        if stop is not None: order.auxPrice = stop
        state = OrderState(); state.status = 'Submitted'
        h.orders[native_id] = (h.contract, order, state)
        client.openOrder(native_id, h.contract, order, state)
        client.orderStatus(native_id, 'Submitted', 0, order.totalQuantity, 0., 0, parent, 0., client.client_id, '', 0.)

    def transport(request):
        # External synthetic ACK only.  The actual Native BUY guard stays closed.
        h.transport_acks.append(request)
        assert request.strategy_name == 'RossMomentum' and len(h.transport_acks) == 1
        ack(71, request)
        return ExecutionResult(symbol=request.symbol, trader_type=request.trader_type, attempted=True,
            status='Submitted', rationale='controlled retained-request external ACK', direction=request.direction,
            quantity=request.quantity, requested_quantity=request.quantity, filled_quantity=0,
            remaining_quantity=request.quantity, client_order_id=request.client_order_id, ibkr_order_id=71)

    def stop_ack(**values):
        h.stop_acks.append(values)
        assert len(h.stop_acks) == 1 and values['quantity'] == min(requested_quantity, h.quantity) and values['stop_price'] == 10.2897
        original = h.transport_acks[0]
        ack(72, original, parent=71, stop=values['stop_price'], quantity=values['quantity'])
        return dict(broker_order_id='72', status='Submitted', order_type='STP')

    broker.place_order = transport
    broker.place_stop_order = stop_ack
    broker.open_orders = lambda **unused: [NS(orderId=key, contract=c, order=o, orderState=s)
        for key, (c, o, s) in h.orders.items()
        if str(client.cached_order_status(key).get('status', '')).upper() != 'FILLED']
    broker.positions = lambda: [NS(symbol='JPM', position=h.quantity, con_id=123,
        account=ACCOUNT, avgCost=10.53)] if h.quantity else []

    def requested(kind, request_id):
        if kind == 74:
            client.positionMulti(request_id, ACCOUNT, '', h.contract, Decimal(h.quantity), 10.53 if h.quantity else 0.)
            client.positionMultiEnd(request_id)
        else:
            assert kind == 62
            client.accountSummary(request_id, ACCOUNT, 'CashBalance', '1000', 'USD')
            client.accountSummary(request_id, ACCOUNT, 'AccruedCash', '0', 'USD')
            client.accountSummaryEnd(request_id)
    h.cancel_hook = None
    def cancelled(kind, request_id):
        if h.cancel_hook is not None:
            h.cancel_hook(kind, request_id)
    h.requests, h.cancels = _source_request_encoder(h, monkeypatch, requested, cancelled)
    h.request = BrokerOrderRequest(client_order_id='controlled-original-decision-ross-standalone', symbol='JPM',
        direction='LONG', quantity=requested_quantity, order_type='MKT', trader_type='ROSS', strategy_name='RossMomentum',
        stop_loss_price=10.2897, take_profit_price=None, setup_family_id='PREMARKET_HIGH_BREAK',
        invalidation_level=10.30, target_model='HOD / next resistance extension after PMH acceptance',
        setup_metadata={'occurrence_id': 'controlled-retained-pmh', 'trigger_level': 10.30,
            'execution_stream': {'observed_at_utc': (NOW-timedelta(seconds=40)).isoformat(),
                'execution_trigger_timeframe': '1m'}})
    engine.bind_native_order_scope(account=ACCOUNT, client=client, as_of=NOW)
    engine._prospective_decisions_by_order_id[h.request.client_order_id] = 'controlled-original-decision'
    result = engine._route_order(h.request)
    assert result.ibkr_order_id == 71 and result.filled_quantity == 0
    assert engine.post_fill_lifecycle._p02_local_supported, 'actual post-route OrderSnapshot reconciliation must remain supported'
    assert engine._native_orders[h.request.client_order_id]['request']['strategy_name'] == 'RossMomentum'
    h.collect = lambda: engine.collect_relationship_updates(result_processor=lambda result:
        core._apply_execution_results_to_trade_management([result]))
    yield h
    assert mutations() == dict(place=0, modify=0, cancel=0)


def _execution(h, *, native_id, execution_id, side, quantity, cumulative, price, at):
    execution = Execution(); execution.orderId = native_id; execution.execId = execution_id
    execution.acctNumber = ACCOUNT; execution.clientId = h.client.client_id; execution.side = side
    execution.shares = Decimal(quantity); execution.cumQty = Decimal(cumulative)
    execution.price = price; execution.avgPrice = price; execution.time = at.isoformat()
    h.client.execDetails(-1, h.contract, execution)
    return execution


def _report(h, execution_id, amount):
    report = CommissionReport(); report.execId = execution_id; report.commission = amount; report.currency = 'USD'
    h.client.commissionReport(report)
    return report


def _closed_roundtrip(h, *, report_first=False, status_first=False, fees=True, fee_fault=None, monkeypatch=None):
    h.quantity = 1
    if report_first and fees:
        _report(h, 'controlled-entry', .01)
    if status_first:
        h.client.orderStatus(71, 'Filled', 1, 0, 10.53, 0, 0, 10.53, h.client.client_id, '', 0.)
        h.collect()
        assert not _observe(h)['available']
    _execution(h, native_id=71, execution_id='controlled-entry', side='BOT', quantity=1,
        cumulative=1, price=10.53, at=NOW-timedelta(seconds=30))
    h.client.orderStatus(71, 'Filled', 1, 0, 10.53, 0, 0, 10.53, h.client.client_id, '', 0.)
    h.collect()
    assert len(h.stop_acks) == 1
    assert h.lifecycle.get_trade(h.request.client_order_id) is not None, h.engine._native_orders[h.request.client_order_id]['canonical_feedback']
    assert h.lifecycle.get_trade(h.request.client_order_id).quantity_open == 1
    h.quantity = 0
    _execution(h, native_id=72, execution_id='controlled-stop', side='SLD', quantity=1,
        cumulative=1, price=10.28, at=NOW-timedelta(seconds=20))
    h.client.orderStatus(72, 'Filled', 1, 0, 10.28, 0, 71, 10.28, h.client.client_id, '', 0.)
    h.collect()
    assert h.lifecycle.get_trade(h.request.client_order_id).quantity_open == 0
    assert h.engine.post_fill_lifecycle.get_trade(h.request.client_order_id).filled_qty == 0
    if not fees:
        positions = h.client.position_snapshot(timeout_seconds=.1)
        assert positions.status == 'COMPLETE'
        return h
    if not report_first:
        _report(h, 'controlled-entry', .01)
    _report(h, 'controlled-stop', .02)
    candidates = h.engine.native_roundtrip_fee_candidates()
    assert set(candidates) == {h.request.client_order_id}
    candidate = dict(candidates[h.request.client_order_id]); source = candidate.pop('source_client')
    candidate.pop('account'); candidate.pop('decision_id')
    currency = h.client.account_currency_snapshot(expected_account=ACCOUNT, timeout_seconds=.1)
    if fee_fault:
        original = h.storage.persist_native_lifecycle_feedback
        h.fee_write_calls = []
        def write(*args, **kwargs):
            h.fee_write_calls.append(1)
            if fee_fault == 'lost_ack':
                original(*args, **kwargs)
            raise OSError('controlled fee write ' + fee_fault)
        monkeypatch.setattr(h.storage, 'persist_native_lifecycle_feedback', write)
    apply = lambda: h.lifecycle.apply_native_roundtrip_fees(NativeRoundtripFeeObservation(**candidate,
        account_currency_result=currency), source_client=source, now=NOW, max_age_seconds=15,
        trading_day_for=h.engine.daily_risk_governor.trading_day_for)
    if fee_fault:
        with pytest.raises(OSError, match='controlled fee write'):
            apply()
    else:
        apply()
    positions = h.client.position_snapshot(timeout_seconds=.1)
    assert positions.status == 'COMPLETE' and positions.rows[0].position == 0
    return h


def test_actual_retained_roundtrip_settles_financial_occurrences_without_emptying_caches(financial_component):
    h = _closed_roundtrip(financial_component)
    before = h.client.local_financial_cache_snapshot()
    assert before['executions_snapshot'] and before['order_status'] and before['open_orders_snapshot']
    assert h.client.local_intake_snapshot().dirty
    h.collect()
    value = _observe(h)
    assert h.engine._p02_runtime_scope_valid(), (h.engine._p02_local.get('uncertain'), h.engine.post_fill_lifecycle._p02_local_supported, h.engine.trade_registry._p02_local_supported)
    assert value['available'] and value.local_condition_satisfied, (value['findings'], h.engine._p02_local.get('settlement_unavailable'))
    assert value['timing'] == 'EMPTY_LOCAL' and value['entries'] == ()
    assert not h.client.local_intake_snapshot().dirty
    assert h.client.local_financial_cache_snapshot()['executions_snapshot'] == before['executions_snapshot']
    assert value.admission_authorized is False
    for stage in ('PROPOSAL', 'RISK', 'RESERVATION', 'FINAL_NATIVE_ENTRY'):
        assert not h.engine.revalidate_p02_local_cooldown(value, assessed_at=NOW, stage=stage)
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3


def test_actual_capital_scope_inspection_closes_its_owned_sql_cursor(local_component):
    h = local_component()
    assert h.storage.capital_scopes_present() is False
    _settle(h)
    value = _observe(h)
    assert value['available'] and value.local_condition_satisfied


def test_actual_retained_request_cas_closes_its_owned_select_before_fence(local_component):
    h = local_component()
    h.engine._load_native_orders()
    h.engine._save_native_orders()
    h.engine._save_native_orders()
    _settle(h)
    value = _observe(h)
    assert value['available'] and value.local_condition_satisfied


def test_identical_source_duplicates_reuse_effects_without_query_or_time_renewal(financial_component):
    h = _closed_roundtrip(financial_component)
    h.collect()
    first = _observe(h)
    assert first['available'] and first.local_condition_satisfied
    events = h.storage.fetch_trade_lifecycle_events()
    request_count = len(h.requests)
    _execution(h, native_id=71, execution_id='controlled-entry', side='BOT', quantity=1,
        cumulative=1, price=10.53, at=NOW-timedelta(seconds=30))
    _report(h, 'controlled-entry', .01)
    assert not _observe(h)['available']
    h.collect()
    after = _observe(h)
    assert after['available'] and after.local_condition_satisfied, (after['findings'], h.engine._p02_local.get('settlement_unavailable'))
    for _ in range(2):
        h.collect()
        assert _observe(h)['available']
    assert h.storage.fetch_trade_lifecycle_events() == events
    assert len(h.requests) == request_count  # Settlement never requests source facts.
    assert len(h.stop_acks) == len(h.transport_acks) == 1
    assert not h.client.local_intake_snapshot().dirty
    assert h.lifecycle.get_trade(h.request.client_order_id).opened_at == (NOW-timedelta(seconds=30)).isoformat()


def test_changed_protective_order_ref_cannot_settle_as_an_old_ack(financial_component):
    from copy import deepcopy
    h = _closed_roundtrip(financial_component)
    h.collect()
    assert _observe(h)['available']
    contract, order, state = h.orders[72]
    changed = deepcopy(order); changed.orderRef = 'PROTECT|unrelated-owned-root'
    h.client.openOrder(72, contract, changed, state)
    h.collect()
    value = _observe(h)
    assert not value['available'] and not value.local_condition_satisfied
    assert h.client.local_intake_snapshot().dirty
    assert h.lifecycle.get_trade(h.request.client_order_id).gross_realized_pnl == pytest.approx(-.25)


@pytest.mark.parametrize('ordering', ['status_before_exec', 'report_before_exec'])
def test_actual_callback_ordering_waits_for_its_completed_effect(financial_component, ordering):
    h = _closed_roundtrip(financial_component,
        status_first=ordering == 'status_before_exec', report_first=ordering == 'report_before_exec')
    h.collect()
    value = _observe(h)
    assert value['available'] and value.local_condition_satisfied, value['findings']
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3
    assert len(h.stop_acks) == len(h.transport_acks) == 1
    assert h.lifecycle.get_trade(h.request.client_order_id).opened_at == (NOW-timedelta(seconds=30)).isoformat()


@pytest.mark.parametrize('age,available', [(15, True), (15.000001, False)])
def test_position_and_retained_scope_exact_existing_freshness_boundary(financial_component, age, available):
    h = _closed_roundtrip(financial_component)
    h.clock.current += timedelta(seconds=age)
    if available:
        h.collect()
    else:
        # The older actual retained-scope clock legitimately vetoes first.
        # Do not renew it merely to isolate the later position predicate.
        with pytest.raises(ValueError, match='NATIVE_ORDER_SCOPE_STALE_OR_CHANGED'):
            h.collect()
    value = _observe(h, at=h.clock.current)
    assert value['available'] is available, value['findings']
    assert value.local_condition_satisfied is available
    assert value.admission_authorized is False
    assert len(h.requests) == 2  # One currency and one position query, no reader acquisition.


@pytest.mark.parametrize('fee_fault', ['before_write', 'lost_ack'])
def test_fee_write_uncertainty_keeps_financial_callbacks_dirty_without_retry(
        financial_component, monkeypatch, fee_fault):
    h = _closed_roundtrip(financial_component, fee_fault=fee_fault, monkeypatch=monkeypatch)
    canonical = h.lifecycle.get_trade(h.request.client_order_id)
    assert canonical.quantity_open == 0 and canonical.gross_realized_pnl == pytest.approx(-.25)
    for _ in range(2):
        h.collect()
        value = _observe(h)
        assert not value['available'] and not value.local_condition_satisfied
    assert h.fee_write_calls == [1]
    assert h.client.local_intake_snapshot().dirty
    fees = h.lifecycle.native_fee_feedback_snapshot(now=NOW, max_age_seconds=15, expected_source_client=h.client)
    assert fees['required'] and not fees['available']
    assert len(h.requests) == 2 and len(h.stop_acks) == 1


def test_missing_reports_preserve_gross_unknown_but_cannot_settle_bundle(financial_component):
    h = _closed_roundtrip(financial_component, fees=False)
    h.collect()
    value = _observe(h)
    assert not value['available'] and not value.local_condition_satisfied
    assert h.client.local_intake_snapshot().dirty
    canonical = h.lifecycle.get_trade(h.request.client_order_id)
    assert canonical.quantity_open == 0 and canonical.gross_realized_pnl == pytest.approx(-.25)
    assert len(h.storage.fetch_trade_lifecycle_events()) == 2
    assert not h.lifecycle.native_fee_feedback_snapshot(now=NOW, max_age_seconds=15)['required']
    assert all(kind == 74 for kind, _ in h.requests)  # No fee/currency acquisition.


@pytest.mark.parametrize('correction', ['execution', 'fee', 'legacy_sdk_object'])
def test_corrected_or_mutated_source_facts_never_reuse_old_settlement(financial_component, correction):
    h = _closed_roundtrip(financial_component)
    h.collect()
    original = _observe(h)
    assert original['available']
    if correction == 'execution':
        _execution(h, native_id=71, execution_id='controlled-entry', side='BOT', quantity=1,
            cumulative=1, price=10.54, at=NOW-timedelta(seconds=30))
    elif correction == 'fee':
        _report(h, 'controlled-entry', .04)
    else:
        h.client._executions_snapshot[0].execution.price = 10.54
    assert not h.engine.revalidate_p02_local_cooldown(original, assessed_at=NOW)
    value = _observe(h)
    assert not value['available'] and not value.local_condition_satisfied
    assert h.lifecycle.get_trade(h.request.client_order_id).gross_realized_pnl == pytest.approx(-.25)
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3


@pytest.mark.parametrize('missing', ['entry_event', 'snapshot_conflict', 'native_state'])
def test_missing_durable_effect_cannot_reuse_runtime_settlement(financial_component, missing):
    h = _closed_roundtrip(financial_component)
    h.collect()
    original = _observe(h)
    assert original['available']
    connection = h.storage._store.connection
    if missing == 'entry_event':
        connection.execute("DELETE FROM trade_lifecycle_events WHERE event_type='ENTRY_FILL'")
    elif missing == 'snapshot_conflict':
        connection.execute('UPDATE trade_lifecycle_trades SET quantity_open=1')
    else:
        connection.execute("DELETE FROM position_lifecycle_transitions WHERE intent='NATIVE_ORDER_STATE'")
    connection.commit()
    assert not h.engine.revalidate_p02_local_cooldown(original, assessed_at=NOW)
    value = _observe(h)
    assert not value['available'] and not value.local_condition_satisfied, value['findings']
    assert h.lifecycle.get_trade(h.request.client_order_id).gross_realized_pnl == pytest.approx(-.25)


def test_receipt_is_owner_issued_and_cannot_be_forged_or_reused(financial_component, monkeypatch):
    from dataclasses import replace
    import copy
    h = _closed_roundtrip(financial_component)
    actual = h.client.settle_local_intake
    seen = []
    def observe(ticket, receipt):
        if ticket.kind == 'execDetails':
            forged = replace(receipt)
            with pytest.raises(RuntimeError, match='RECEIPT_UNVERIFIED'):
                actual(ticket, forged)
            with pytest.raises(TypeError, match='NOT_TRANSFERABLE'):
                copy.copy(receipt)
            seen.append((ticket, receipt))
        return actual(ticket, receipt)
    monkeypatch.setattr(h.client, 'settle_local_intake', observe)
    h.collect()
    assert _observe(h)['available']
    assert len(seen) == 2
    with pytest.raises(RuntimeError, match='NOT_SETTLEABLE'):
        actual(*seen[0])
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3


def test_callback_between_receipt_issue_and_consume_revokes_it(financial_component, monkeypatch):
    h = _closed_roundtrip(financial_component)
    actual = h.client.settle_local_intake
    injected = []
    def changed(ticket, receipt):
        if ticket.kind == 'execDetails' and not injected:
            injected.append(ticket.ticket_id)
            h.client.orderStatus(71, 'Filled', 1, 0, 10.53, 0, 0, 10.53, h.client.client_id, '', 0.)
        return actual(ticket, receipt)
    monkeypatch.setattr(h.client, 'settle_local_intake', changed)
    h.collect()
    assert injected and h.client.local_intake_snapshot().dirty
    assert not _observe(h)['available']
    h.collect()  # A new actual completed owner read can classify the duplicate.
    assert _observe(h)['available']
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3


def test_connection_epoch_change_cannot_restore_prior_financial_observation(financial_component):
    h = _closed_roundtrip(financial_component)
    h.collect()
    original = _observe(h)
    assert original['available']
    h.client.connectionClosed()
    value = _observe(h)
    assert not value['available'] and not value.local_condition_satisfied
    assert not h.engine.revalidate_p02_local_cooldown(original, assessed_at=NOW)
    assert h.lifecycle.get_trade(h.request.client_order_id).gross_realized_pnl == pytest.approx(-.25)


@pytest.mark.parametrize('financial_component', [2], indirect=True)
def test_actual_partial_stop_stays_blocked_until_terminal_effects_complete(financial_component):
    h = financial_component
    h.quantity = 2
    _execution(h, native_id=71, execution_id='partial-entry', side='BOT', quantity=2,
        cumulative=2, price=10.53, at=NOW-timedelta(seconds=30))
    h.client.orderStatus(71, 'Filled', 2, 0, 10.53, 0, 0, 10.53, h.client.client_id, '', 0.)
    h.collect()
    assert h.lifecycle.get_trade(h.request.client_order_id).quantity_open == 2
    h.quantity = 1
    _execution(h, native_id=72, execution_id='partial-stop-first', side='SLD', quantity=1,
        cumulative=1, price=10.28, at=NOW-timedelta(seconds=20))
    h.client.orderStatus(72, 'Submitted', 1, 1, 10.28, 0, 71, 10.28, h.client.client_id, '', 0.)
    h.collect()
    canonical = h.lifecycle.get_trade(h.request.client_order_id)
    assert canonical.quantity_open == 1 and canonical.gross_realized_pnl == pytest.approx(-.25)
    assert h.engine.post_fill_lifecycle.assess_trade_stop_protection(h.request.client_order_id)['protected']
    assert h.engine.capital_authority.total_used_exposure == pytest.approx(10.53)
    value = _observe(h)
    assert not value['available'] and not value.local_condition_satisfied
    assert h.client.local_intake_snapshot().dirty
    assert len(h.storage.fetch_trade_lifecycle_events()) == 2
    h.collect()
    assert len(h.storage.fetch_trade_lifecycle_events()) == 2
    h.quantity = 0
    _execution(h, native_id=72, execution_id='partial-stop-final', side='SLD', quantity=1,
        cumulative=2, price=10.28, at=NOW-timedelta(seconds=10))
    h.client.orderStatus(72, 'Filled', 2, 0, 10.28, 0, 71, 10.28, h.client.client_id, '', 0.)
    h.collect()
    for execution_id, amount in [('partial-entry', .01), ('partial-stop-first', .01), ('partial-stop-final', .02)]:
        _report(h, execution_id, amount)
    candidate = dict(h.engine.native_roundtrip_fee_candidates()[h.request.client_order_id])
    client = candidate.pop('source_client'); candidate.pop('account'); candidate.pop('decision_id')
    currency = h.client.account_currency_snapshot(expected_account=ACCOUNT, timeout_seconds=.1)
    h.lifecycle.apply_native_roundtrip_fees(NativeRoundtripFeeObservation(**candidate,
        account_currency_result=currency), source_client=client, now=NOW, max_age_seconds=15,
        trading_day_for=h.engine.daily_risk_governor.trading_day_for)
    assert h.client.position_snapshot(timeout_seconds=.1).status == 'COMPLETE'
    h.collect()
    value = _observe(h)
    assert value['available'] and value.local_condition_satisfied, (value['findings'], h.engine._p02_local.get('settlement_unavailable'))
    assert h.lifecycle.get_trade(h.request.client_order_id).quantity_open == 0
    assert h.lifecycle.get_trade(h.request.client_order_id).gross_realized_pnl == pytest.approx(-.50)
    assert h.engine.capital_authority.total_used_exposure == 0
    assert len(h.storage.fetch_trade_lifecycle_events()) == 4
    assert len(h.stop_acks) == len(h.transport_acks) == 1
    assert not h.client.local_intake_snapshot().dirty
    assert value.admission_authorized is False and value['timing'] == 'EMPTY_LOCAL'


@pytest.mark.parametrize('scope', ['order', 'account', 'client', 'security', 'side'])
def test_unrelated_execution_occurrence_keeps_selected_financial_facts_but_blocks_local(
        financial_component, scope):
    from copy import deepcopy
    h = _closed_roundtrip(financial_component)
    h.collect()
    assert _observe(h)['available']
    contract = deepcopy(h.contract)
    execution = Execution(); execution.orderId = 73 if scope == 'order' else 71
    execution.execId = 'unrelated-source-execution'; execution.acctNumber = 'OTHER' if scope == 'account' else ACCOUNT
    execution.clientId = 888 if scope == 'client' else h.client.client_id
    execution.side = 'SLD' if scope == 'side' else 'BOT'
    execution.shares = Decimal(1); execution.cumQty = Decimal(1)
    execution.price = execution.avgPrice = 10.53; execution.time = (NOW-timedelta(seconds=30)).isoformat()
    if scope == 'security': contract.conId = 456
    h.client.execDetails(-1, contract, execution)
    value = _observe(h)
    assert not value['available'] and not value.local_condition_satisfied
    assert h.client.local_intake_snapshot().dirty
    assert h.lifecycle.get_trade(h.request.client_order_id).gross_realized_pnl == pytest.approx(-.25)
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3


def test_ignored_history_callback_cannot_settle_because_latest_caches_are_unchanged(financial_component):
    h = _closed_roundtrip(financial_component)
    h.collect()
    assert _observe(h)['available']
    before = h.client.local_financial_cache_snapshot()
    source = h.client._executions_snapshot[0]
    h.client.execDetails(444, source.contract, source.execution)
    assert h.client.local_financial_cache_snapshot()['executions_snapshot'] == before['executions_snapshot']
    h.collect()
    assert not _observe(h)['available']
    assert any(ticket.kind == 'execDetails' and ticket.publication is None
        for ticket in h.client.local_intake_snapshot().dirty)
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3


def test_rebound_decision_cannot_use_matching_current_and_durable_request_records(financial_component):
    h = _closed_roundtrip(financial_component)
    h.collect()
    assert _observe(h)['available']
    root = h.engine._native_orders[h.request.client_order_id]
    assert root['decision_id'] == 'controlled-original-decision'
    # This alternate prefix passes the old startswith check, but contradicts
    # the original actual owner construction/handoff slot retained in process.
    for owned in h.engine._native_orders.values():
        owned['decision_id'] = 'controlled-original'
    h.engine._save_native_orders()
    h.collect()
    value = _observe(h)
    assert not value['available'] and not value.local_condition_satisfied
    assert h.lifecycle.get_trade(h.request.client_order_id).gross_realized_pnl == pytest.approx(-.25)


@pytest.mark.parametrize('financial_component', [2], indirect=True)
def test_partial_entry_temporary_flat_does_not_terminalize_pending_entry(financial_component):
    h = financial_component
    h.quantity = 1
    _execution(h, native_id=71, execution_id='unfinished-entry', side='BOT', quantity=1,
        cumulative=1, price=10.53, at=NOW-timedelta(seconds=30))
    h.client.orderStatus(71, 'Submitted', 1, 1, 10.53, 0, 0, 10.53, h.client.client_id, '', 0.)
    h.collect()
    root = h.engine._native_orders[h.request.client_order_id]
    assert root['filled'] == 1 and root['requested'] == 2 and not root['terminal']
    assert h.lifecycle.get_trade(h.request.client_order_id).quantity_open == 1
    assert h.engine.post_fill_lifecycle.assess_trade_stop_protection(h.request.client_order_id)['protected']
    assert h.stop_acks[0]['quantity'] == 1
    assert not _observe(h)['available']
    h.quantity = 0
    _execution(h, native_id=72, execution_id='unfinished-stop', side='SLD', quantity=1,
        cumulative=1, price=10.28, at=NOW-timedelta(seconds=20))
    h.client.orderStatus(72, 'Filled', 1, 0, 10.28, 0, 71, 10.28, h.client.client_id, '', 0.)
    h.collect()
    canonical = h.lifecycle.get_trade(h.request.client_order_id)
    assert canonical.quantity_open == 0 and canonical.gross_realized_pnl == pytest.approx(-.25)
    assert root['filled'] == 1 and root['requested'] == 2 and not root['terminal']
    assert h.engine.native_roundtrip_fee_candidates() == {}
    for _ in range(2):
        h.collect()
        assert not _observe(h)['available']
    assert len(h.storage.fetch_trade_lifecycle_events()) == 2
    assert h.requests == []
    assert h.client.local_intake_snapshot().dirty
    assert len(h.stop_acks) == len(h.transport_acks) == 1


def test_actual_position_cleanup_exception_cannot_be_replaced_by_complete_result(financial_component):
    h = financial_component
    def cancel(kind, request_id):
        if kind == 75:
            raise OSError('controlled position cancellation uncertainty')
    h.cancel_hook = cancel
    _closed_roundtrip(h)
    for _ in range(2):
        h.collect()
        assert not _observe(h)['available']
    assert len(h.requests) == 2 and len(h.cancels) == 2
    assert h.client.local_intake_snapshot().dirty
    assert h.lifecycle.native_fee_feedback_snapshot(now=NOW, max_age_seconds=15)['available']
    assert h.lifecycle.get_trade(h.request.client_order_id).gross_realized_pnl == pytest.approx(-.25)
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3


def test_failed_actual_callback_stays_dirty_after_prior_success(financial_component):
    h = _closed_roundtrip(financial_component)
    h.collect()
    original = _observe(h)
    assert original['available']
    with pytest.raises(TypeError):
        h.client.orderStatus(None, 'Filled', 1, 0, 10.53, 0, 0, 10.53, h.client.client_id, '', 0.)
    h.collect()
    assert not _observe(h)['available']
    assert not h.engine.revalidate_p02_local_cooldown(original, assessed_at=NOW)
    assert any(ticket.failed for ticket in h.client.local_intake_snapshot().dirty)
    assert h.lifecycle.get_trade(h.request.client_order_id).gross_realized_pnl == pytest.approx(-.25)
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3


def test_external_active_read_vm_is_not_silently_closed_by_settlement(financial_component):
    h = _closed_roundtrip(financial_component)
    h.collect()
    original = _observe(h)
    assert original['available']
    cursor = h.storage._store.connection.execute('SELECT * FROM trade_lifecycle_events')
    try:
        assert cursor.fetchone() is not None
        h.collect()
        with pytest.raises(RuntimeError, match='LOCAL_SQLITE_FENCE_UNAVAILABLE'):
            _observe(h)
        assert cursor.fetchone() is not None  # Original caller still owns its live VM.
    finally:
        cursor.close()
    h.collect()
    assert _observe(h)['available']
    assert not h.engine.revalidate_p02_local_cooldown(original, assessed_at=NOW)
    assert len(h.storage.fetch_trade_lifecycle_events()) == 3
