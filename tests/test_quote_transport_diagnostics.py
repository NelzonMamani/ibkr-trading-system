"""Native quote diagnostics with fake SDK sends; no connection or acquisition."""
import json

import pytest
from ibapi.client import EClient

from src.ibkr.quote_diagnostics import QuoteDiagnostics
from test_post_pr1090_market_data_authority import native, contract, client_for, native_ticks


def rows(capsys):
    return [json.loads(line.split('] ', 1)[1]) for line in capsys.readouterr().out.splitlines()
            if line.startswith('[IBKR][QUOTE_TRACE] ')]


def test_success_flags_owner_callbacks_completion_cleanup(native, monkeypatch, capsys):
    def send(self, req, *args):
        native_ticks(self, req, returned=1)
    monkeypatch.setattr(EClient, 'reqMktData', send)
    native.reqMarketDataType(3)
    result = client_for(native).snapshot_stock(contract())
    row = native._quote_trace.requests[result.request_id]
    assert row['requested_type'] == 3 and row['returned_type'] == 1
    assert row['owner'] == 'MARKET_DATA'
    assert row['snapshot'] and not row['regulatory_snapshot']
    assert row['generic_ticks'] == '' and row['option_count'] == 0
    assert row['send_outcome'] == 'SDK_RETURNED_NOT_BROKER_ACK'
    assert row['completion'] == 'snapshot_end'
    assert row['callbacks']['tickPrice:accepted'] == 4
    assert row['tick_counts']['68:accepted'] == 1
    assert row['callbacks']['tickSnapshotEnd:accepted'] == 1
    assert row['cleanup'] == dict(cancel_outcome='NOT_SENT_ALREADY_COMPLETE',
        active_after=False, ticker_present_after=False, event_present_after=False,
        broker_cancel_acknowledged=False)
    logs = rows(capsys)
    assert {'request', 'send', 'callback', 'completion', 'cleanup'} <= {r['event'] for r in logs}
    assert next(r for r in logs if r['event'] == 'send')['broker_receipt_verified'] is False


def test_missing_callbacks_timeout_and_cancel_cleanup(native, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr('src.ibkr.market_data_client.time.monotonic', lambda: clock[0])
    monkeypatch.setattr(native, 'waitOnUpdate', lambda **kw: clock.__setitem__(0, clock[0] + .2))
    result = client_for(native).snapshot_stock(contract())
    assert result.last is None and not result.snapshot_complete
    assert result.returned_market_data_type == 'UNKNOWN'
    assert len(result.snapshot_attempts) == 2
    for attempt in result.snapshot_attempts:
        row = native._quote_trace.requests[attempt['request_id']]
        assert row['callbacks'] == {} and row['returned_type'] is None
        assert row['completion'] == 'timeout'
        assert row['cleanup']['cancel_outcome'] == 'SDK_CANCEL_RETURNED_NOT_BROKER_ACK'
        assert not row['cleanup']['active_after']
    assert not native._market_events and not native._ticker_by_req_id


@pytest.mark.parametrize('reason', ['wrong_owner', 'inactive', 'conflicted', 'missing_ticker'])
def test_rejected_callbacks_cannot_supply_prices_type_or_end(native, reason):
    ticker = native.reqMktData(contract(), snapshot=True)
    req = ticker.reqId
    event = native._market_events[req]
    if reason == 'wrong_owner':
        native._request_type_by_req_id[req] = 'HISTORICAL_DATA'
    elif reason == 'inactive':
        native.cancelMktData(req)
    elif reason == 'conflicted':
        native._order_state_registry[req] = {'request_id_conflict': True}
    else:
        native._ticker_by_req_id.pop(req)
    native_ticks(native, req)
    assert ticker.bid is None and ticker.last is None
    assert not ticker.snapshotEnd and not ticker.marketDataTypeConfirmed
    assert not event.is_set()
    counters = native._quote_trace.requests[req]['callbacks']
    assert counters['tickPrice:' + reason] == 4
    assert counters['marketDataType:' + reason] == 1
    assert counters['tickSnapshotEnd:' + reason] == 1


def test_unknown_unsupported_and_invalid_callbacks_are_counted(native):
    native.tickPrice(999, 4, 12, None)
    assert native._quote_trace.unknown_callbacks['tickPrice:unknown_request'] == 1
    t = native.reqMktData(contract())
    native.tickPrice(t.reqId, 9999, 12, None)
    native.tickString(t.reqId, 88, 'invalid')
    assert native._quote_trace.requests[t.reqId]['callbacks'] == {
        'tickPrice:unsupported_tick': 1, 'tickString:invalid_value': 1}
    assert native._quote_trace.requests[t.reqId]['tick_counts']['OTHER:rejected'] == 1
    assert t.last is None and t.lastTime is None


def test_late_old_request_cannot_mutate_replacement(native):
    old = native.reqMktData(contract())
    native.cancelMktData(old.reqId)
    new = native.reqMktData(contract())
    native_ticks(native, old.reqId)
    assert new.reqId != old.reqId and new.last is None and not new.snapshotEnd
    assert native._quote_trace.requests[old.reqId]['callbacks']['tickPrice:inactive'] == 4
    assert native._quote_trace.requests[new.reqId]['callbacks'] == {}


def test_send_and_cancel_failures_preserve_original_and_release_ownership(native, monkeypatch):
    def send(*args, **kw):
        raise ValueError('send fixture')
    def cancel(*args, **kw):
        raise RuntimeError('cancel fixture')
    monkeypatch.setattr(EClient, 'reqMktData', send)
    monkeypatch.setattr(EClient, 'cancelMktData', cancel)
    with pytest.raises(ValueError, match='send fixture'):
        native.reqMktData(contract())
    row = next(iter(native._quote_trace.requests.values()))
    assert row['send_outcome'] == 'SDK_RAISED'
    assert row['cleanup']['cancel_outcome'] == 'SDK_CANCEL_RAISED'
    assert not native._active_market_req_ids and not native._ticker_by_req_id


def test_bounded_private_logs_and_fixed_callback_buckets(capsys):
    diag = QuoteDiagnostics(71)
    diag.MAX_REQUESTS, diag.MAX_LOGS = 3, 10
    c = contract()
    c.symbol = 'DU123456789'
    for req in range(30):
        diag.start(req, c, 3, 'U123456789', True, False, [])
        for tick in range(100):
            diag.callback(req, 'tickPrice', 'unsupported_tick', tick_type=10000 + tick)
        diag.sent(req, 'SDK_RETURNED_NOT_BROKER_ACK')
    logs = rows(capsys)
    assert len(logs) == 10 and diag.suppressed_logs > 0
    assert len(diag.requests) == 3 and diag.evicted_requests == 27
    assert all(len(r['tick_counts']) == 1 for r in diag.requests.values())
    assert 'DU123456789' not in json.dumps(logs) and 'U123456789' not in json.dumps(logs)
    assert all(len(json.dumps(r).encode()) <= diag.MAX_LOG_BYTES for r in logs)


def test_logging_failure_does_not_change_callback_authority(native, monkeypatch):
    import builtins
    def broken(*a, **kw):
        raise OSError('disk/console fixture')
    monkeypatch.setattr(builtins, 'print', broken)
    ticker = native.reqMktData(contract())
    native.tickPrice(ticker.reqId, 4, 5.0, None)
    native.tickSnapshotEnd(ticker.reqId)
    native.cancelMktData(ticker.reqId)
    assert ticker.last == 5.0 and ticker.snapshotEnd
    assert native._quote_trace.suppressed_logs > 0


def test_interrupted_attempt_is_not_reported_as_timeout(native, monkeypatch):
    from src.core.acquisition import AcquisitionCancelled
    def stop(**kwargs):
        raise AcquisitionCancelled()
    monkeypatch.setattr(native, 'waitOnUpdate', stop)
    with pytest.raises(AcquisitionCancelled):
        client_for(native).snapshot_stock(contract())
    row = next(iter(native._quote_trace.requests.values()))
    assert row['completion'] == 'interrupted'
    assert not row['cleanup']['active_after']
    assert not native._market_events


def test_broker_error_arrival_retains_owner_but_not_message_in_trace(native, capsys):
    ticker = native.reqMktData(contract())
    native.error(ticker.reqId, 354, 'Not subscribed: DU123456789')
    trace = rows(capsys)
    row = native._quote_trace.requests[ticker.reqId]
    assert row['callbacks']['error:accepted'] == 1
    assert 'Not subscribed' not in json.dumps(trace)
    assert 'DU123456789' not in json.dumps(trace)
    assert ticker.brokerErrors[0]['code'] == 354  # Existing sanitized error evidence remains.
