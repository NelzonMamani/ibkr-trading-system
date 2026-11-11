from __future__ import annotations

import threading
import time
import dataclasses
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from ibapi.client import EClient
from ibapi.contract import Contract, ContractDetails

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.market_data.market_snapshot_enricher import MarketSnapshotEnricher


_NATIVE_REQ_EXECUTIONS = EClient.reqExecutions


class DummyConnectionManager:
    def __init__(self, client):
        self._client = client

    def get_client(self):
        return self._client


def _build_client() -> IbkrClient:
    return IbkrClient(
        host="127.0.0.1",
        port=4001,
        client_id=1,
        snapshot_timeout_seconds=1,
        market_data_type="DELAYED",
        readonly_enabled=True,
    )


def test_qualify_contracts_compatibility(monkeypatch):
    client = _build_client()

    def fake_resolve(symbol: str, exchange: str = "SMART", currency: str = "USD"):
        resolved = Contract()
        resolved.symbol = symbol
        resolved.secType = "STK"
        resolved.exchange = exchange
        resolved.currency = currency
        resolved.conId = 12345
        resolved.primaryExchange = "NASDAQ"
        resolved.tradingClass = symbol
        resolved.localSymbol = symbol

        details = ContractDetails()
        details.contract = resolved
        return details

    monkeypatch.setattr(client, "resolve_contract", fake_resolve)

    requested = Contract()
    requested.symbol = "AAPL"
    requested.secType = "STK"
    requested.exchange = "SMART"
    requested.currency = "USD"

    qualified = client.qualifyContracts(requested)

    assert len(qualified) == 1
    assert qualified[0].symbol == "AAPL"
    assert qualified[0].conId == 12345
    assert qualified[0].primaryExchange == "NASDAQ"


def test_req_mkt_data_compatibility_wrapper(monkeypatch):
    client = _build_client()
    captured = {}

    def fake_req_mkt_data(self, req_id, contract, generic_tick_list, snapshot, regulatory_snapshot, options):
        captured["args"] = (req_id, contract.symbol, generic_tick_list, snapshot, regulatory_snapshot, options)

    def fake_cancel_mkt_data(self, req_id):
        captured["cancel_req_id"] = req_id

    monkeypatch.setattr(EClient, "reqMktData", fake_req_mkt_data)
    monkeypatch.setattr(EClient, "cancelMktData", fake_cancel_mkt_data)

    contract = Contract()
    contract.symbol = "MSFT"
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"

    ticker = client.reqMktData(contract, genericTickList="", snapshot=True, regulatorySnapshot=False)
    req_id = captured["args"][0]

    client.tickPrice(req_id, 1, 100.5, None)
    client.tickPrice(req_id, 2, 101.0, None)
    client.tickPrice(req_id, 4, 100.8, None)
    client.tickSize(req_id, 8, 500)

    assert captured["args"][1:] == ("MSFT", "", True, False, [])
    assert client.waitOnUpdate(timeout=0.01) is True
    assert ticker.bid == 100.5
    assert ticker.ask == 101.0
    assert ticker.last == 100.8
    assert ticker.volume == 500.0

    client.cancelMktData(contract)
    assert captured["cancel_req_id"] == req_id


def test_snapshot_enricher_uses_ib_style_req_mkt_data_without_signature_error(monkeypatch):
    client = _build_client()

    def fake_resolve(symbol: str, exchange: str = "SMART", currency: str = "USD"):
        resolved = Contract()
        resolved.symbol = symbol
        resolved.secType = "STK"
        resolved.exchange = exchange
        resolved.currency = currency
        resolved.conId = 555
        details = ContractDetails()
        details.contract = resolved
        return details

    def fake_req_mkt_data(self, req_id, contract, generic_tick_list, snapshot, regulatory_snapshot, options):
        self.tickPrice(req_id, 4, 123.45, None)
        self.tickPrice(req_id, 1, 123.4, None)
        self.tickPrice(req_id, 2, 123.5, None)
        self.tickSize(req_id, 8, 2000)

    monkeypatch.setattr(client, "resolve_contract", fake_resolve)
    monkeypatch.setattr(EClient, "reqMktData", fake_req_mkt_data)
    monkeypatch.setattr(EClient, "cancelMktData", lambda self, req_id: None)

    enricher = MarketSnapshotEnricher(connection_manager=DummyConnectionManager(client), batch_timeout_seconds=0.5)
    snapshots = enricher.fetch_snapshots(["AAPL"])
    diag = enricher.last_fetch_diagnostics["AAPL"]

    assert diag["qualified_ok"] is True
    assert diag["snapshot_received"] is True
    assert "reqMktData:" not in str(diag.get("exception") or "")
    assert snapshots["AAPL"]["last_price"] == 123.45
    assert snapshots["AAPL"]["bid"] == 123.4
    assert snapshots["AAPL"]["ask"] == 123.5
    assert snapshots["AAPL"]["volume"] == 2000.0


def test_req_historical_data_requires_end_after_bar_arrival(monkeypatch):
    client = _build_client()
    client.snapshot_timeout_seconds = 0.2
    monkeypatch.setattr(client, "isConnected", lambda: True)

    contract = Contract()
    contract.symbol = "AAPL"
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"

    def fake_req_historical_data(
        self,
        req_id,
        _contract,
        end_date_time,
        duration_str,
        bar_size_setting,
        what_to_show,
        use_rth,
        format_date,
        keep_up_to_date,
        chart_options,
    ):
        def deliver():
            time.sleep(0.05)
            client.historicalData(req_id, {"close": 123.45})
            client.historicalDataEnd(req_id, "", "")

        threading.Thread(target=deliver, daemon=True).start()

    monkeypatch.setattr(EClient, "reqHistoricalData", fake_req_historical_data)

    bars = client.reqHistoricalData(contract)

    assert bars.completed and bars.end_received
    assert list(bars) == [{"close": 123.45}]
    assert not client._historical_data and not client._historical_events


def test_disconnect_skips_join_when_called_from_network_thread(monkeypatch):
    client = _build_client()
    client._thread = threading.current_thread()

    monkeypatch.setattr(EClient, "disconnect", lambda self: None)

    client.disconnect()


def test_run_loop_treats_shutdown_self_join_error_as_normal_exit(monkeypatch, capsys):
    client = _build_client()
    client._stop_event.set()

    def raise_self_join(_self):
        raise RuntimeError("cannot join current thread")

    monkeypatch.setattr(EClient, "run", raise_self_join)

    client._run_loop()

    assert "Network loop error" not in capsys.readouterr().out

# Strict history uses the existing request/callback owner, never transport or a
# prepared result. The ordinary legacy tests above retain their own fixtures.
@pytest.fixture
def strict_execution_client(monkeypatch, tmp_path):
    import socket
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH', str(tmp_path / 'order_ids.json'))
    def forbidden(*args, **kwargs):
        raise AssertionError('strict execution tests must remain offline')
    for name in ('connect', 'placeOrder', 'cancelOrder', 'reqGlobalCancel', 'reqExecutions'):
        monkeypatch.setattr(EClient, name, forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    client = _build_client()
    monkeypatch.setattr(client, 'is_connected', lambda: True)
    monkeypatch.setattr(client, 'serverVersion', lambda: 180)
    client.nextValidId(71)
    client.managedAccounts('SYNTHETIC_TEST')
    return client


def _execution_scope(**changes):
    scope = dict(account='SYNTHETIC_TEST', order_id=70, con_id=901,
                 symbol='SYNTH', side='SELL', timeout_seconds=1)
    scope.update(changes)
    return scope


def _execution_fact(**changes):
    fields = dict(orderId=70, clientId=1, acctNumber='SYNTHETIC_TEST', side='SLD',
                  execId='synthetic.1', time='20261110 10:00:00 UTC', shares=Decimal('1'),
                  price=10.4, cumQty=Decimal('1'), avgPrice=10.4)
    fields.update(changes)
    return NS(**fields)


def _execution_contract(**changes):
    fields = dict(conId=901, symbol='SYNTH', secType='STK')
    fields.update(changes)
    return NS(**fields)


def test_strict_execution_complete_is_immutable_request_evidence_only(strict_execution_client, monkeypatch):
    client = strict_execution_client
    requests = []
    callbacks = []
    monkeypatch.setattr(client, '_emit_execution_callback', callbacks.append)
    execution = _execution_fact(shares=Decimal('.5'), cumQty=Decimal('.5'))
    def request(req_id, native_filter):
        requests.append((req_id, native_filter))
        client.execDetails(req_id, _execution_contract(), execution)
        client.execDetails(req_id, _execution_contract(), execution)  # exact duplicate
        client.execDetailsEnd(req_id)
    monkeypatch.setattr(client, 'reqExecutions', request)
    result = client.execution_snapshot(**_execution_scope())
    assert result.status == 'COMPLETE' and result.completed_at is not None
    assert result.connection_epoch == client._position_connection_epoch
    assert result.request_id == requests[0][0] > 70
    assert (result.account, result.client_id, result.order_id, result.con_id,
            result.symbol, result.side) == ('SYNTHETIC_TEST', 1, 70, 901, 'SYNTH', 'SELL')
    assert result.completion_scope == 'REQUEST_ONLY' and result.filter_time == ''
    assert len(result.rows) == 1 and result.rows[0].quantity == Decimal('.5')
    native_filter = requests[0][1]
    assert (native_filter.clientId, native_filter.acctCode, native_filter.symbol,
            native_filter.secType, native_filter.time) == (1, 'SYNTHETIC_TEST', 'SYNTH', 'STK', '')
    execution.price = 999
    client.execDetails(result.request_id, _execution_contract(), execution)
    client.execDetailsEnd(result.request_id)
    assert result.rows[0].price == Decimal('10.4')
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.rows[0].price = Decimal('2')
    assert callbacks == [] and client._exec_details_by_order == {}
    assert client._executions_snapshot == [] and not client._executions_event.is_set()
    assert 'execution_query' not in client._request_context_by_req_id[result.request_id]
    assert result.request_id not in client._request_type_by_req_id
    # Late history after bounded metadata eviction cannot become a live callback.
    client._request_context_by_req_id.pop(result.request_id)
    client.execDetails(result.request_id, _execution_contract(), execution)
    assert callbacks == []


@pytest.mark.parametrize('outcome', ['empty', 'timeout', 'error', 'disconnected', 'epoch', 'scope', 'conflict', 'evicted', 'send_error'])
def test_strict_execution_completion_states(strict_execution_client, monkeypatch, outcome):
    client = strict_execution_client
    def request(req_id, native_filter):
        if outcome == 'empty':
            client.execDetailsEnd(req_id)
        elif outcome == 'error':
            client.error(req_id, 321, 'synthetic request rejection')
            client.execDetailsEnd(req_id)
        elif outcome in ('disconnected', 'epoch'):
            client._invalidate_position_queries()
            if outcome == 'epoch':
                client._position_transport_available = True
                client.managedAccounts('SYNTHETIC_TEST')
            client.execDetailsEnd(req_id)
        elif outcome == 'scope':
            client.managedAccounts('OTHER_SYNTHETIC')
            client.managedAccounts('SYNTHETIC_TEST')
            client.execDetailsEnd(req_id)
        elif outcome == 'conflict':
            client._observe_order_id(req_id)
            client.execDetailsEnd(req_id)
        elif outcome == 'evicted':
            client._request_context_by_req_id.pop(req_id)
        elif outcome == 'send_error':
            raise RuntimeError('synthetic SDK failure')
    monkeypatch.setattr(client, 'reqExecutions', request)
    # Zero timeout deterministically prevents dispatch; use a bounded real wait
    # only for the timeout/eviction cases, never sleep to force callback ordering.
    result = client.execution_snapshot(**_execution_scope(timeout_seconds=.02 if outcome in ('timeout', 'evicted') else 1))
    expected = dict(empty='COMPLETE', timeout='TIMEOUT', error='ERROR', disconnected='DISCONNECTED',
                    epoch='DISCONNECTED', scope='SCOPE_CHANGED', conflict='IDENTITY_CONFLICT',
                    evicted='OWNERSHIP_LOST', send_error='ERROR')[outcome]
    assert result.status == expected and result.rows == ()
    assert (result.completed_at is not None) == (outcome == 'empty')


@pytest.mark.parametrize('changes,contract_changes', [
    ({'acctNumber': 'OTHER'}, {}), ({'clientId': 2}, {}), ({'side': 'BOT'}, {}),
    ({}, {'conId': 902}), ({}, {'symbol': 'OTHER'}), ({}, {'secType': 'OPT'}),
    ({'shares': float('nan')}, {}), ({'price': float('inf')}, {}), ({'shares': True}, {}),
    ({'cumQty': Decimal('.5')}, {}), ({'execId': ''}, {}), ({'time': ''}, {}),
])
def test_strict_execution_rejects_scope_and_malformed_facts(strict_execution_client, monkeypatch, changes, contract_changes):
    client = strict_execution_client
    def request(req_id, native_filter):
        client.execDetails(req_id, _execution_contract(**contract_changes), _execution_fact(**changes))
        client.execDetailsEnd(req_id)
    monkeypatch.setattr(client, 'reqExecutions', request)
    result = client.execution_snapshot(**_execution_scope())
    assert result.status == 'INVALID' and result.completed_at is None


def test_strict_execution_conflicting_duplicate_cannot_complete(strict_execution_client, monkeypatch):
    client = strict_execution_client
    def request(req_id, native_filter):
        client.execDetails(req_id, _execution_contract(), _execution_fact())
        client.execDetails(req_id, _execution_contract(), _execution_fact(price=10.5))
        client.execDetailsEnd(req_id)
    monkeypatch.setattr(client, 'reqExecutions', request)
    result = client.execution_snapshot(**_execution_scope())
    assert result.status == 'INVALID' and len(result.rows) == 1


def test_strict_execution_interleaved_queries_and_legacy_event_are_isolated(strict_execution_client, monkeypatch):
    client = strict_execution_client
    admitted = threading.Event()
    requests = {}
    results = {}
    errors = []
    def request(req_id, native_filter):
        # The SDK send seam returns; callbacks arrive independently below.
        requests[req_id] = native_filter
        if len(requests) == 2:
            admitted.set()
    monkeypatch.setattr(client, 'reqExecutions', request)
    def query(order_id):
        try:
            results[order_id] = client.execution_snapshot(**_execution_scope(order_id=order_id, timeout_seconds=3))
        except BaseException as exc:
            errors.append(exc)
    workers = [threading.Thread(target=query, args=(order_id,)) for order_id in (69, 70)]
    # Reserve both retained native identities before allocating any query ID.
    client._observe_order_id(69)
    client._observe_order_id(70)
    try:
        for worker in workers:
            worker.start()
        assert admitted.wait(2)
        by_order = {context['execution_query']['order_id']: req_id
                    for req_id, context in client._request_context_by_req_id.items()
                    if 'execution_query' in context}
        a, b = by_order[69], by_order[70]
        client.execDetailsEnd(999999)  # no owner: cannot complete either request
        client.execDetails(a, _execution_contract(), _execution_fact(orderId=70))  # local filter
        client.execDetails(b, _execution_contract(), _execution_fact(orderId=70))
        client.execDetailsEnd(b)
        assert not client._executions_event.is_set()
        client.execDetails(a, _execution_contract(), _execution_fact(orderId=69, execId='synthetic.2'))
        client.execDetailsEnd(a)
    finally:
        for req_id in tuple(requests):
            client.execDetailsEnd(req_id)
        for worker in workers:
            worker.join(4)
    assert not errors and all(not worker.is_alive() for worker in workers)
    assert set(results) == {69, 70}
    assert all(result.status == 'COMPLETE' and len(result.rows) == 1 for result in results.values())
    assert results[69].rows[0].order_id == 69 and results[70].rows[0].order_id == 70


def test_strict_execution_disconnected_and_zero_budget_do_not_dispatch(strict_execution_client, monkeypatch):
    client = strict_execution_client
    def forbidden(*args):
        raise AssertionError('must not dispatch')
    monkeypatch.setattr(client, 'reqExecutions', forbidden)
    assert client.execution_snapshot(**_execution_scope(timeout_seconds=0)).status == 'TIMEOUT'
    client._invalidate_position_queries()
    assert client.execution_snapshot(**_execution_scope()).status == 'DISCONNECTED'


def test_strict_execution_client_zero_filter_and_unsolicited_fills(strict_execution_client, monkeypatch):
    client = strict_execution_client
    client.client_id = 0
    callbacks = []
    monkeypatch.setattr(client, '_emit_execution_callback', callbacks.append)
    def request(req_id, native_filter):
        assert native_filter.clientId == 0
        client.execDetails(req_id, _execution_contract(), _execution_fact(clientId=1))
        client.execDetails(req_id, _execution_contract(), _execution_fact(clientId=0))
        # Independent live callback still reaches the old accounting owner.
        client.execDetails(-1, _execution_contract(), _execution_fact(clientId=0, execId='live'))
        client.execDetailsEnd(req_id)
    monkeypatch.setattr(client, 'reqExecutions', request)
    result = client.execution_snapshot(**_execution_scope())
    assert result.status == 'COMPLETE' and len(result.rows) == 1
    assert result.rows[0].client_id == 0
    assert len(callbacks) == 1 and callbacks[0]['execution'].execId == 'live'


def test_strict_execution_evicted_active_owner_drops_history(strict_execution_client, monkeypatch):
    client = strict_execution_client
    callbacks = []
    monkeypatch.setattr(client, '_emit_execution_callback', callbacks.append)
    def request(req_id, native_filter):
        client._request_context_by_req_id.pop(req_id)
        client.execDetails(req_id, _execution_contract(), _execution_fact())
        client.execDetailsEnd(req_id)
    monkeypatch.setattr(client, 'reqExecutions', request)
    result = client.execution_snapshot(**_execution_scope(timeout_seconds=.02))
    assert result.status == 'OWNERSHIP_LOST' and not result.rows and not callbacks


def test_legacy_execution_interface_remains_list_based(strict_execution_client, monkeypatch):
    client = strict_execution_client
    def request(req_id, native_filter):
        client.execDetails(req_id, _execution_contract(), _execution_fact())
        client.execDetailsEnd(req_id)
    monkeypatch.setattr(client, 'reqExecutions', request)
    assert len(client.executions(timeout_seconds=1)) == 1


@pytest.mark.parametrize('invalidator', ['disconnect', 'scope', 'error', 'collision'])
def test_strict_execution_end_does_not_survive_local_invalidation(strict_execution_client, monkeypatch, invalidator):
    client = strict_execution_client
    def request(req_id, native_filter):
        client.execDetailsEnd(req_id)
        if invalidator == 'disconnect':
            client._invalidate_position_queries()
        elif invalidator == 'scope':
            client.managedAccounts('OTHER_SYNTHETIC')
        elif invalidator == 'error':
            client.error(req_id, 321, 'synthetic post-end rejection')
        else:
            client._observe_order_id(req_id)
    monkeypatch.setattr(client, 'reqExecutions', request)
    result = client.execution_snapshot(**_execution_scope())
    assert result.status != 'COMPLETE' and result.completed_at is None
    assert result.attempt_id == (result.connection_epoch, result.request_id)


def test_strict_execution_end_at_expired_deadline_cannot_complete(strict_execution_client, monkeypatch):
    client = strict_execution_client
    # Expire ONLY this request's owned deadline at the external callback seam.
    # Shared clocks and scheduler behavior stay real.
    def request(req_id, native_filter):
        client._request_context_by_req_id[req_id]['execution_query']['deadline'] = 0
        client.execDetails(req_id, _execution_contract(), _execution_fact())
        client.execDetailsEnd(req_id)
    monkeypatch.setattr(client, 'reqExecutions', request)
    result = client.execution_snapshot(**_execution_scope())
    assert result.status == 'TIMEOUT' and not result.rows


def test_strict_execution_actual_sdk_request_and_late_live_fill_are_not_finality(strict_execution_client, monkeypatch):
    client = strict_execution_client
    messages = []
    callbacks = []
    monkeypatch.setattr(client, 'isConnected', lambda: True)
    monkeypatch.setattr(client, '_emit_execution_callback', callbacks.append)
    def send(message):
        messages.append(message)
        req_id = next(key for key, value in client._request_context_by_req_id.items()
                      if 'execution_query' in value)
        client.execDetailsEnd(req_id)
    monkeypatch.setattr(client, 'sendMsg', send)
    monkeypatch.setattr(client, 'reqExecutions', lambda req_id, filt: _NATIVE_REQ_EXECUTIONS(client, req_id, filt))
    # A cancellation observation followed by empty history is NOT a late-fill barrier.
    client.orderStatus(70, 'Cancelled', 0, 1, 0, 0, 0, 0, 1, '', 0)
    result = client.execution_snapshot(**_execution_scope())
    assert result.status == 'COMPLETE' and result.rows == ()
    assert len(messages) == 1
    fields = messages[0].split('\0')
    assert fields[2:8] == [str(result.request_id), '1', 'SYNTHETIC_TEST', '', 'SYNTH', 'STK']
    client.execDetails(-1, _execution_contract(), _execution_fact(execId='late.live'))
    assert [event['event_type'] for event in callbacks] == ['orderStatus', 'execDetails']
    assert callbacks[1]['execution'].execId == 'late.live'
    assert result.rows == () and result.completion_scope == 'REQUEST_ONLY'


def test_strict_execution_requires_server_request_correlation(strict_execution_client, monkeypatch):
    client = strict_execution_client
    monkeypatch.setattr(client, 'serverVersion', lambda: 1)
    assert client.execution_snapshot(**_execution_scope()).status == 'REQUEST_CORRELATION_UNAVAILABLE'


@pytest.mark.parametrize('kind', ['cancelled', 'deadline'])
def test_strict_execution_control_flow_retires_callback_ownership(strict_execution_client, monkeypatch, kind):
    from src.core.acquisition import AcquisitionCancelled, AcquisitionDeadlineExceeded
    client = strict_execution_client
    requests = []
    error = AcquisitionCancelled if kind == 'cancelled' else AcquisitionDeadlineExceeded
    def request(req_id, native_filter):
        requests.append(req_id)
        raise error()
    monkeypatch.setattr(client, 'reqExecutions', request)
    with pytest.raises(error):
        client.execution_snapshot(**_execution_scope())
    req_id = requests[0]
    assert req_id not in client._request_type_by_req_id
    assert 'execution_query' not in client._request_context_by_req_id[req_id]
    client.execDetails(req_id, _execution_contract(), _execution_fact())
    client.execDetailsEnd(req_id)
    assert not client._executions_snapshot and not client._executions_event.is_set()


def test_strict_execution_partial_rows_are_not_successful_completion(strict_execution_client, monkeypatch):
    client = strict_execution_client
    def request(req_id, native_filter):
        client.execDetails(req_id, _execution_contract(), _execution_fact())
        client.error(req_id, 321, 'synthetic incomplete response')
    monkeypatch.setattr(client, 'reqExecutions', request)
    result = client.execution_snapshot(**_execution_scope())
    assert result.status == 'ERROR' and len(result.rows) == 1
    assert result.completed_at is None and result.completion_scope == 'REQUEST_ONLY'


def test_strict_execution_retired_id_cannot_leak_via_another_request_kind(strict_execution_client, monkeypatch):
    client = strict_execution_client
    callbacks = []
    monkeypatch.setattr(client, '_emit_execution_callback', callbacks.append)
    def request(req_id, native_filter):
        client.execDetailsEnd(req_id)
    monkeypatch.setattr(client, 'reqExecutions', request)
    result = client.execution_snapshot(**_execution_scope())
    assert result.status == 'COMPLETE'
    # Raw compatibility owners can register their own ID. Such a different
    # request kind still cannot acquire ownership of an execution-history stream.
    client._register_request(result.request_id, 'MARKET_DATA')
    client.execDetails(result.request_id, _execution_contract(), _execution_fact())
    assert callbacks == [] and client._exec_details_by_order == {}


@pytest.mark.parametrize('req_id', [0, 999999, -2])
def test_execution_history_without_request_owner_is_not_a_live_fill(strict_execution_client, monkeypatch, req_id):
    client = strict_execution_client
    callbacks = []
    monkeypatch.setattr(client, '_emit_execution_callback', callbacks.append)
    client.execDetails(req_id, _execution_contract(), _execution_fact())
    assert not callbacks and not client._executions_snapshot and not client._exec_details_by_order


# A currency observation is an end-confirmed source fact only. It grants no fee,
# NET, equity conversion, capital, risk or order authority.
_NATIVE_REQ_ACCOUNT_SUMMARY = EClient.reqAccountSummary
_NATIVE_CANCEL_ACCOUNT_SUMMARY = EClient.cancelAccountSummary


@pytest.fixture
def account_currency_client(strict_execution_client, monkeypatch):
    from src.adapters.brokers.ibkr import ibkr_client as native_module
    from datetime import datetime, timezone
    client = strict_execution_client
    monkeypatch.setattr(client, 'isConnected', lambda: True)
    clock = NS(monotonic=100.0, now=datetime(2026, 11, 11, 16, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(native_module, 'time', NS(monotonic=lambda: clock.monotonic))
    class CallbackClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now if tz is None else clock.now.astimezone(tz)
    monkeypatch.setattr(native_module, 'datetime', CallbackClock)
    facts = NS(client=client, clock=clock, requests=[], cancels=[], on_request=None, on_cancel=None)
    def send(message):
        fields = message.split('\0')
        if fields[0] == '62':
            req_id = int(fields[2])
            facts.requests.append((req_id, fields[3], fields[4]))
            if facts.on_request is not None:
                facts.on_request(req_id)
        elif fields[0] == '63':
            req_id = int(fields[2])
            facts.cancels.append(req_id)
            if facts.on_cancel is not None:
                facts.on_cancel(req_id)
        else:
            pytest.fail('Unexpected native SDK message: ' + fields[0])
    monkeypatch.setattr(client, 'sendMsg', send)
    # Exercise the installed request encoders, with sendMsg as external boundary.
    monkeypatch.setattr(client, 'reqAccountSummary',
        lambda *args: _NATIVE_REQ_ACCOUNT_SUMMARY(client, *args))
    monkeypatch.setattr(client, 'cancelAccountSummary',
        lambda *args: _NATIVE_CANCEL_ACCOUNT_SUMMARY(client, *args))
    return facts


def _currency_rows(client, req_id, currency='USD', account='SYNTHETIC_TEST', *, end=True):
    client.accountSummary(req_id, account, 'CashBalance', '123.45', currency)
    client.accountSummary(req_id, account, 'AccruedCash', '0', currency)
    if end:
        client.accountSummaryEnd(req_id)


def _assert_currency_retired(client, req_id):
    assert req_id not in client._request_type_by_req_id
    assert req_id not in client._account_summary_events
    assert req_id not in client._account_summary_rows
    assert 'account_currency_query' not in client._request_context_by_req_id.get(req_id, {})


@pytest.mark.parametrize('currency', ['USD', 'EUR'])
def test_strict_account_currency_uses_actual_ledger_encoder_and_owned_end(account_currency_client, currency):
    facts = account_currency_client
    client = facts.client
    facts.on_request = lambda req_id: _currency_rows(client, req_id, currency)
    # Synchronous callbacks during native cancellation cannot mutate the result.
    facts.on_cancel = lambda req_id: _currency_rows(client, req_id, 'GBP')
    result = client.account_currency_snapshot(expected_account='SYNTHETIC_TEST', timeout_seconds=1)
    assert result.status == 'COMPLETE' and result.currency == currency
    assert result.account == 'SYNTHETIC_TEST' and result.client_id == client.client_id
    assert result.connection_epoch == client._position_connection_epoch
    assert result.completed_at == facts.clock.now
    assert result.completed_at.tzinfo is not None
    assert result.source == 'IBKR_ACCOUNT_SUMMARY_LEDGER'
    assert result.tags == ('AccruedCash', 'CashBalance')
    assert facts.requests == [(result.request_id, 'All', '$LEDGER')]
    assert facts.cancels == [result.request_id]
    assert result.cancellation_attempted and result.cleanup_complete
    _assert_currency_retired(client, result.request_id)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.currency = 'GBP'
    client.accountSummary(result.request_id, 'SYNTHETIC_TEST', 'CashBalance', '0', 'JPY')
    client.accountSummaryEnd(result.request_id)
    _assert_currency_retired(client, result.request_id)
    assert result.currency == currency


@pytest.mark.parametrize('currency', ['', 'BASE', 'usd', ' USD', 'USD ', 'US', 'USDT', '???', None])
def test_strict_account_currency_has_no_default_for_unusable_currency(account_currency_client, currency):
    facts = account_currency_client
    facts.on_request = lambda req_id: _currency_rows(facts.client, req_id, currency)
    result = facts.client.account_currency_snapshot(expected_account='SYNTHETIC_TEST', timeout_seconds=1)
    assert result.status == 'INVALID' and result.currency is None and result.completed_at is None
    assert facts.cancels == [result.request_id]
    _assert_currency_retired(facts.client, result.request_id)


@pytest.mark.parametrize('outcome,expected,cancel', [
    ('empty', 'MISSING_CURRENCY', True), ('partial', 'TIMEOUT', True),
    ('unowned_end', 'TIMEOUT', True), ('wrong_account', 'WRONG_ACCOUNT', True),
    ('ambiguous', 'AMBIGUOUS_CURRENCY', True), ('error', 'ERROR', True),
    ('error_after_end', 'ERROR', True), ('disconnected', 'DISCONNECTED', False),
    ('epoch', 'DISCONNECTED', False), ('stopped', 'DISCONNECTED', False),
    ('account_scope', 'SCOPE_CHANGED', True), ('client_id', 'SCOPE_CHANGED', False),
    ('client_bool', 'SCOPE_CHANGED', False), ('epoch_bool', 'DISCONNECTED', False),
    ('conflict', 'IDENTITY_CONFLICT', False), ('evicted', 'OWNERSHIP_LOST', False),
    ('send_error', 'ERROR', True), ('cleanup_error', 'CLEANUP_UNCONFIRMED', True),
    ('deadline_end', 'TIMEOUT', True), ('stale', 'STALE', True),
    ('future', 'STALE', True),
])
def test_strict_account_currency_unavailable_states_do_not_publish_currency(
        account_currency_client, outcome, expected, cancel):
    from datetime import timedelta
    from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
    facts = account_currency_client
    client = facts.client
    def request(req_id):
        if outcome == 'send_error':
            raise OSError('synthetic query send uncertainty')
        if outcome == 'empty':
            client.accountSummaryEnd(req_id)
            return
        _currency_rows(client, req_id, end=False)
        if outcome == 'partial':
            facts.clock.monotonic += 1
        elif outcome == 'unowned_end':
            client.accountSummaryEnd(req_id + 999999)
            facts.clock.monotonic += 1
        elif outcome == 'wrong_account':
            _currency_rows(client, req_id, account='UNRELATED')
        elif outcome == 'ambiguous':
            _currency_rows(client, req_id, 'EUR')
        elif outcome == 'error':
            client.error(req_id, 321, 'synthetic summary rejection')
        elif outcome == 'error_after_end':
            client.accountSummaryEnd(req_id)
            client.error(req_id, 321, 'synthetic owned stream error')
        elif outcome == 'disconnected':
            client.connectionClosed()
        elif outcome == 'epoch':
            client._position_connection_epoch += 1
            client.accountSummaryEnd(req_id)
        elif outcome == 'stopped':
            client._stop_event.set()
            client.accountSummaryEnd(req_id)
        elif outcome == 'account_scope':
            client.managedAccounts('UNRELATED')
            client.accountSummaryEnd(req_id)
        elif outcome in {'client_id', 'client_bool'}:
            client.client_id = True if outcome == 'client_bool' else 2
            client.accountSummaryEnd(req_id)
        elif outcome == 'epoch_bool':
            assert client._position_connection_epoch == 0
            client._position_connection_epoch = False
            client.accountSummaryEnd(req_id)
        elif outcome == 'conflict':
            client.openOrder(req_id, _execution_contract(), NS(), NS())
            client.accountSummaryEnd(req_id)
        elif outcome == 'evicted':
            client._request_context_by_req_id.pop(req_id)
            client.accountSummaryEnd(req_id)
            facts.clock.monotonic += 1
        elif outcome == 'deadline_end':
            facts.clock.monotonic += 1
            client.accountSummaryEnd(req_id)
        else:
            client.accountSummaryEnd(req_id)
            if outcome == 'stale':
                facts.clock.now += timedelta(seconds=get_ibkr_snapshot_max_age_seconds(), microseconds=1)
            elif outcome == 'future':
                facts.clock.now -= timedelta(microseconds=1)
    facts.on_request = request
    if outcome == 'cleanup_error':
        def failed_cancel(req_id):
            raise OSError('synthetic cancellation uncertainty')
        facts.on_cancel = failed_cancel
    result = client.account_currency_snapshot(expected_account='SYNTHETIC_TEST', timeout_seconds=1)
    assert result.status == expected, result
    assert result.currency is None and result.completed_at is None
    assert result.cleanup_complete and result.cancellation_attempted is cancel
    assert facts.cancels == ([result.request_id] if cancel else [])
    _assert_currency_retired(client, result.request_id)
    client.accountSummary(result.request_id, 'SYNTHETIC_TEST', 'CashBalance', '0', 'USD')
    client.accountSummaryEnd(result.request_id)
    _assert_currency_retired(client, result.request_id)


@pytest.mark.parametrize('scope', ['disconnected', 'stopped', 'multiple_accounts', 'wrong_account', 'no_account', 'zero_budget'])
def test_strict_account_currency_requires_existing_exact_native_scope_without_dispatch(account_currency_client, scope, monkeypatch):
    facts = account_currency_client
    client = facts.client
    if scope == 'disconnected':
        monkeypatch.setattr(client, 'is_connected', lambda: False)
    elif scope == 'stopped':
        client._stop_event.set()
    elif scope == 'multiple_accounts':
        client.managedAccounts('SYNTHETIC_TEST,OTHER')
    elif scope == 'wrong_account':
        client.managedAccounts('OTHER')
    elif scope == 'no_account':
        client.managedAccounts('')
    result = client.account_currency_snapshot(expected_account='SYNTHETIC_TEST',
        timeout_seconds=0 if scope == 'zero_budget' else 1)
    assert result.status in {'DISCONNECTED', 'ACCOUNT_SCOPE_UNAVAILABLE', 'TIMEOUT'}
    assert result.request_id is None and result.currency is None and result.completed_at is None
    assert result.cleanup_complete and not result.cancellation_attempted
    assert not facts.requests and not facts.cancels


@pytest.mark.parametrize('account,timeout', [('', 1), (' TEST', 1), ('TEST ', 1), (None, 1),
    ('SYNTHETIC_TEST', True), ('SYNTHETIC_TEST', -1), ('SYNTHETIC_TEST', float('inf')),
    ('SYNTHETIC_TEST', float('nan')), ('SYNTHETIC_TEST', '1')])
def test_strict_account_currency_rejects_incomplete_call_scope(account_currency_client, account, timeout):
    facts = account_currency_client
    with pytest.raises(ValueError):
        facts.client.account_currency_snapshot(expected_account=account, timeout_seconds=timeout)
    assert not facts.requests and not facts.cancels


def test_strict_account_currency_end_freezes_initial_rows_and_preserves_legacy_summary(account_currency_client):
    facts = account_currency_client
    client = facts.client
    facts.on_request = lambda req_id: _currency_rows(client, req_id)
    result = client.account_currency_snapshot(expected_account='SYNTHETIC_TEST')
    assert result.status == 'COMPLETE' and result.currency == 'USD'
    def legacy(req_id):
        assert facts.requests[-1][2] == 'AvailableFunds,NetLiquidation,BuyingPower'
        client.accountSummary(result.request_id, 'SYNTHETIC_TEST', 'AvailableFunds', 'BAD', 'EUR')
        client.accountSummaryEnd(result.request_id)
        client.accountSummary(req_id, 'SYNTHETIC_TEST', 'AvailableFunds', '100', 'BASE')
        client.accountSummary(req_id, 'SYNTHETIC_TEST', 'NetLiquidation', '200', 'BASE')
        client.accountSummary(req_id, 'SYNTHETIC_TEST', 'BuyingPower', '300', 'BASE')
        client.accountSummaryEnd(req_id)
    facts.on_request = legacy
    assert client.get_account_summary() == {'AvailableFunds': '100', 'NetLiquidation': '200', 'BuyingPower': '300'}
    assert result.currency == 'USD'
    _assert_currency_retired(client, result.request_id)
    # Evict bounded diagnostics: late strict data has no active legacy owner.
    client._request_context_by_req_id.pop(result.request_id)
    _currency_rows(client, result.request_id, 'GBP')
    _assert_currency_retired(client, result.request_id)


@pytest.mark.parametrize('kind', ['cancelled', 'deadline'])
def test_strict_account_currency_control_flow_always_retires_and_cancels_owned_query(account_currency_client, kind):
    from src.core.acquisition import AcquisitionCancelled, AcquisitionDeadlineExceeded
    facts = account_currency_client
    error = AcquisitionCancelled if kind == 'cancelled' else AcquisitionDeadlineExceeded
    def interrupted(req_id):
        raise error()
    facts.on_request = interrupted
    with pytest.raises(error):
        facts.client.account_currency_snapshot(expected_account='SYNTHETIC_TEST')
    req_id, _, _ = facts.requests[0]
    assert facts.cancels == [req_id]
    _assert_currency_retired(facts.client, req_id)


@pytest.mark.parametrize('tag', ['', ' CashBalance', 'CashBalance ', None])
def test_strict_account_currency_requires_actual_tagged_ledger_rows(account_currency_client, tag):
    facts = account_currency_client
    def request(req_id):
        facts.client.accountSummary(req_id, 'SYNTHETIC_TEST', tag, '0', 'USD')
        facts.client.accountSummaryEnd(req_id)
    facts.on_request = request
    result = facts.client.account_currency_snapshot(expected_account='SYNTHETIC_TEST')
    assert result.status == 'INVALID' and result.currency is None and result.completed_at is None
    _assert_currency_retired(facts.client, result.request_id)


def test_strict_account_currency_retains_original_end_clock_at_inclusive_freshness_boundary(account_currency_client):
    from datetime import timedelta
    from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
    facts = account_currency_client
    ended_at = facts.clock.now
    def request(req_id):
        _currency_rows(facts.client, req_id)
        facts.clock.now += timedelta(seconds=get_ibkr_snapshot_max_age_seconds())
    facts.on_request = request
    result = facts.client.account_currency_snapshot(expected_account='SYNTHETIC_TEST')
    assert result.status == 'COMPLETE' and result.currency == 'USD'
    assert result.completed_at == ended_at and result.completed_at != facts.clock.now
    _assert_currency_retired(facts.client, result.request_id)


def test_strict_account_currency_interleaved_requests_are_isolated_and_workers_finish(account_currency_client):
    facts = account_currency_client
    client = facts.client
    admitted = threading.Event()
    results = {}
    errors = []
    def request(req_id):
        if len(facts.requests) == 2:
            admitted.set()
    facts.on_request = request
    def query(label):
        try:
            results[label] = client.account_currency_snapshot(expected_account='SYNTHETIC_TEST', timeout_seconds=3)
        except BaseException as exc:
            errors.append(exc)
    workers = [threading.Thread(target=query, args=(label,)) for label in ('a', 'b')]
    try:
        for worker in workers:
            worker.start()
        assert admitted.wait(2)
        a, b = [item[0] for item in facts.requests]
        client.accountSummaryEnd(999999)  # No request can inherit this End.
        _currency_rows(client, b)
        client.accountSummary(a, 'SYNTHETIC_TEST', 'CashBalance', '0', 'USD')
        client.accountSummaryEnd(a)
    finally:
        # Always release any admitted synthetic waiter through its real End owner.
        for req_id, _, _ in tuple(facts.requests):
            client.accountSummaryEnd(req_id)
        for worker in workers:
            worker.join(4)
    assert not errors and all(not worker.is_alive() for worker in workers)
    assert set(results) == {'a', 'b'}
    assert all(result.status == 'COMPLETE' and result.currency == 'USD' for result in results.values())
    assert len({result.request_id for result in results.values()}) == 2
    assert sorted(facts.cancels) == sorted(item[0] for item in facts.requests)
    for result in results.values():
        _assert_currency_retired(client, result.request_id)
