"""Offline synthetic wire controls; none reconstruct the captured live receipt."""
import json
import logging
import socket
import threading
from types import SimpleNamespace as NS

import pytest
from ibapi import client as sdk, comm
from ibapi.contract import Contract
from ibapi.connection import Connection
from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.ibkr.transport_diagnostic import TransportDiagnostic, _Socket, _message


class MemorySocket:
    def __init__(self, chunks=(), short=False):
        self.chunks = list(chunks)
        self.sent = []
        self.short = short
        self.closed = False
    def send(self, data, *args, **kwargs):
        self.sent.append((data, args, kwargs))
        return 3 if self.short else len(data)
    def recv(self, size, *args, **kwargs):
        value = self.chunks.pop(0) if self.chunks else b''
        if isinstance(value, BaseException):
            raise value
        return value
    def close(self):
        self.closed = True


def frame(values):
    return comm.make_msg(''.join(comm.make_field(v) for v in values))


def contract():
    c = Contract()
    c.symbol, c.conId, c.secType, c.exchange, c.currency = 'SYNTH', 123, 'STK', 'SMART', 'USD'
    return c


@pytest.fixture
def prepared(monkeypatch):
    c = IbkrClient('127.0.0.1', 7497, 71, 5, 'DELAYED', True)
    # No connect() call; replace the SDK connection's socket creation only.
    raw = MemorySocket()
    monkeypatch.setattr(Connection, 'connect', lambda conn: setattr(conn, 'socket', raw))
    original_connection, original_decoder, original_reader = sdk.Connection, sdk.decoder.Decoder, sdk.reader.EReader
    original_read = comm.read_msg
    d = TransportDiagnostic(c)
    d.__enter__()
    c.conn = sdk.Connection('unused', 0)
    c.conn.connect()
    c.serverVersion_ = 151  # Explicit synthetic negotiated-version fixture.
    c.setConnState(sdk.EClient.CONNECTED)
    c._req_id = 363
    c.decoder = sdk.decoder.Decoder(c, 151)
    yield c, d, raw
    c.disconnect()
    d.close()
    assert sdk.Connection is original_connection and sdk.decoder.Decoder is original_decoder
    assert sdk.reader.EReader is original_reader and comm.read_msg is original_read
    assert 'put' not in vars(c.msg_queue) and '_emit' not in vars(c._quote_trace)


def test_serialized_send_and_cleanup(prepared):
    c, d, raw = prepared
    ticker = c.reqMktData(contract(), genericTickList='', snapshot=True, regulatorySnapshot=False)
    assert len(raw.sent) == 1
    wire = next(r for r in d.records if r['event'] == 'serialized_quote')
    assert wire['schema_verified'] and wire['server_version'] == 151
    assert wire['fields']['request_id'] == str(ticker.reqId)
    assert wire['fields']['symbol'] == 'SYNTH' and wire['fields']['snapshot'] == '1'
    assert wire['fields']['regulatory_snapshot'] == '0' and wire['fields']['options'] == ''
    send = next(r for r in d.records if r['event'] == 'socket_send')
    assert send['requested'] == send['returned'] == len(raw.sent[0][0])
    c.record_quote_completion(ticker.reqId, 'timeout'); c.cancelMktData(ticker.reqId)
    assert not c._active_market_req_ids
    assert any(r['event'] == 'wrapper_cleanup' for r in d.records)
    c.disconnect(); d.close()
    assert d.snapshot()['absence_claims_valid']
    assert len(d.hashes) == 6 and all(len(v) == 64 for v in d.hashes.values())


def test_reader_queue_decoder_wrapper_success_without_prices(prepared):
    c, d, raw = prepared
    ticker = c.reqMktData(contract(), snapshot=True)
    data = b''.join([frame([58, 1, 364, 1]), frame([1, 3, 364, 68, 4.05, 100, 0]),
                    frame([2, 6, 364, 74, 1000]), frame([57, 1, 364])])
    raw.chunks = [data[:2], data[2:7], data[7:21], data[21:], b'']
    reader = sdk.reader.EReader(c.conn, c.msg_queue)
    reader.start(); reader.join(2)
    assert not reader.is_alive()
    assert c.msg_queue.qsize() == 4
    # Consume exactly SDK queued messages, using its run/decoder dispatch path.
    sdk.EClient.run(c)
    assert ticker.snapshotEnd and ticker.last == 4.05 and ticker.volume == 1000
    assert ticker.marketDataTypeConfirmed
    assert d.counters['queue_put'] == d.counters['queue_get'] == 4
    assert d.counters['decoder_entry'] == d.counters['decoder_return'] == 4
    assert d.counters['partial_frames'] >= 1 and d.counters['recv_bytes'] == len(data)
    assert any(r['event'] == 'wrapper_callback' and r['reason'] == 'accepted' for r in d.records)
    assert '4.05' not in json.dumps(d.snapshot())


def test_short_send_no_retry_or_sendall(prepared):
    c, d, raw = prepared; raw.short = True
    c.reqMktData(contract(), snapshot=True)
    assert len(raw.sent) == 1 and d.counters['short_sends'] == 1
    assert d.counters['send_returned'] == 3
    assert c._quote_trace.requests[364]['send_outcome'] == 'SDK_RETURNED_NOT_BROKER_ACK'


def test_actual_recv_distinguished_from_recvmsg_timeout(prepared):
    c, d, raw = prepared
    raw.chunks = [b'x'*4096, socket.timeout('DO_NOT_RETAIN')]
    assert c.conn.recvMsg() == b''
    assert d.counters['recv_bytes'] == 4096 and d.counters['recv_full_chunks'] == 1
    assert d.counters['recv_calls'] == 2 and d.counters['recv_timeouts'] == 1
    assert d.counters['recvmsg_bytes'] == 0 and d.counters['recvmsg_empty'] == 1
    assert c.conn.socket.original is raw  # Socket behavior/timeout is unchanged.
    assert 'DO_NOT_RETAIN' not in json.dumps(d.snapshot())


@pytest.mark.parametrize('mode', ['wrong_owner', 'late', 'missing'])
def test_owner_late_missing_stay_unavailable(prepared, mode):
    c, d, raw = prepared
    ticker = c.reqMktData(contract(), snapshot=True)
    if mode == 'late':
        c.cancelMktData(ticker.reqId)
    if mode == 'wrong_owner':
        c._request_type_by_req_id[ticker.reqId] = 'HISTORICAL_DATA'
    if mode != 'missing':
        c.decoder.interpret(comm.read_fields(frame([58, 1, ticker.reqId, 1])[4:]))
        c.decoder.interpret(comm.read_fields(frame([57, 1, ticker.reqId])[4:]))
    assert not ticker.snapshotEnd and not ticker.marketDataTypeConfirmed
    if mode != 'missing':
        reason = 'wrong_owner' if mode == 'wrong_owner' else 'inactive'
        assert c._quote_trace.requests[364]['callbacks']['marketDataType:'+reason] == 1
    else:
        assert c._quote_trace.requests[364]['callbacks'] == {}


def test_arity_exception_class_and_sdk_log_privacy(prepared, caplog):
    c, d, raw = prepared
    c.reqMktData(contract(), snapshot=True)
    c.decoder.interpret(comm.read_fields(frame([58, 1, 364, 1, 'SECRET_PRICE_OR_ACCOUNT'])[4:]))
    assert any(r['event'] == 'decoder_entry' and r.get('arity_ok') is False for r in d.records)
    assert not c._ticker_by_req_id[364].marketDataTypeConfirmed
    with pytest.raises(ValueError):
        c.decoder.interpret([b'58', b'1', b'364', b'ARBITRARY_ERROR_TEXT'])
    assert d.counters['decoder_exception'] == 1
    assert any(r.get('exception_class') == 'ValueError' for r in d.records)
    assert 'SECRET_PRICE_OR_ACCOUNT' not in caplog.text
    assert 'ARBITRARY_ERROR_TEXT' not in json.dumps(d.snapshot())


def test_unknown_message_does_not_expose_inbound_identifiers(prepared):
    c, d, raw = prepared
    secret = b'UNRETAINED_ACCOUNT_ORDER_PRICE'
    c.decoder.interpret([b'999999', b'1', b'123456', secret])
    assert d.counters['other_messages'] == 1
    assert secret.decode() not in json.dumps(d.snapshot())
    assert _message(b'999999\0' + secret) == {'kind': 'OTHER'}


def test_instrumentation_failure_preserves_send(prepared, monkeypatch):
    c, d, raw = prepared
    def fail(*args):
        raise RuntimeError('private details')
    monkeypatch.setattr(d, '_wire', fail)
    c.reqMktData(contract(), snapshot=True)
    assert len(raw.sent) == 1 and d.counters['hook_errors'] == 1
    assert c._quote_trace.requests[364]['send_outcome'] == 'SDK_RETURNED_NOT_BROKER_ACK'


def test_incomplete_install_never_valid_absence(monkeypatch):
    import src.ibkr.transport_diagnostic as module
    c = IbkrClient('127.0.0.1', 7497, 71, 5, 'DELAYED', True)
    d = TransportDiagnostic(c)
    monkeypatch.setattr(module.metadata, 'version', lambda *a: (_ for _ in ()).throw(RuntimeError()))
    with pytest.raises(RuntimeError):
        d.__enter__()
    assert d.snapshot()['hooks_restored'] and not d.snapshot()['absence_claims_valid']


def test_caps_and_overlong_values(prepared):
    c, d, raw = prepared
    co = contract(); co.localSymbol = 'x'*65
    c.reqMktData(co, snapshot=True)
    wire = next(r for r in d.records if r['event'] == 'serialized_quote')
    assert wire['fields']['local_symbol'] == 'OMITTED_UNSAFE_OR_OVERLONG'
    for i in range(100):
        d.record('bounded', n=i)
    d.record('oversize', text='x'*5000)
    assert len(d.records) == 56  # Eight slots remain reserved for finalization.
    c.record_quote_completion(364, 'timeout'); c.cancelMktData(364)
    assert any(r['event'] == 'wrapper_cleanup' for r in d.records)
    assert all(len(json.dumps(r, ensure_ascii=True).encode()) <= 4096 for r in d.records)
    assert d.counters['records_dropped'] and d.counters['oversize'] == 1
    c.disconnect(); d.close()
    assert not d.snapshot()['absence_claims_valid']


def test_socket_exception_class_and_cleanup_identity():
    class BadSocket:
        def send(self, data, *args, **kwargs):
            raise OSError('DONT_PERSIST')
    raw = BadSocket(); d = TransportDiagnostic(NS())
    with pytest.raises(OSError, match='DONT_PERSIST'):
        _Socket(raw, d).send(b'private')
    assert d.counters['send_exceptions'] == 1
    assert 'DONT_PERSIST' not in json.dumps(d.snapshot())


def test_decoder_observer_failure_cannot_block_original(prepared, monkeypatch):
    import src.ibkr.transport_diagnostic as module
    c, d, raw = prepared
    ticker = c.reqMktData(contract(), snapshot=True)
    monkeypatch.setattr(module, '_message', lambda *args: (_ for _ in ()).throw(RuntimeError()))
    c.decoder.interpret(comm.read_fields(frame([58, 1, 364, 1])[4:]))
    assert ticker.marketDataTypeConfirmed and d.counters['hook_errors'] == 1


def test_partial_patch_failure_restores_every_prior_hook(monkeypatch):
    c = IbkrClient('127.0.0.1', 7497, 71, 5, 'DELAYED', True)
    d = TransportDiagnostic(c)
    original = (sdk.Connection, sdk.decoder.Decoder, sdk.reader.EReader, comm.read_msg)
    patch = d.patch
    def fail_on_queue(obj, name, value):
        if name == 'put':
            raise RuntimeError('fixture partial install')
        return patch(obj, name, value)
    monkeypatch.setattr(d, 'patch', fail_on_queue)
    with pytest.raises(RuntimeError, match='fixture partial install'):
        d.__enter__()
    assert original == (sdk.Connection, sdk.decoder.Decoder, sdk.reader.EReader, comm.read_msg)
    assert not d.patches and not d.snapshot()['coverage_verified']
    assert all(d.log_filter not in logger.filters for logger in d.loggers)


def test_live_reader_invalidates_final_evidence(prepared):
    c, d, raw = prepared
    calls = []
    d.reader = NS(ident=123, join=lambda timeout: calls.append(timeout), is_alive=lambda: True)
    c.disconnect(); d.close()
    assert calls == [2] and not d.snapshot()['reader_stopped']
    assert not d.snapshot()['coverage_verified']
    d.reader = None  # Fixture teardown must not model another pending join.


def test_startup_burst_full_target_lifecycle_preserves_budget(prepared):
    c, d, raw = prepared
    # Real queue and SDK dispatch: global farm errors before the normal scan,
    # then non-target scanner errors. No socket connection/acquisition is made.
    def dispatch(values):
        payload = frame(values)[4:]
        c.msg_queue.put(payload)
        c.decoder.interpret(comm.read_fields(c.msg_queue.get()))
    for _ in range(80):
        dispatch([4, 2, -1, 2104, 'PRIVATE_GLOBAL_TEXT'])
    for _ in range(10):
        dispatch([4, 2, 363, 162, 'PRIVATE_SCANNER_TEXT'])
    ticker = c.reqMktData(contract(), snapshot=True)
    messages = [[58, 1, 364, 1]]
    messages += [[1, 3, 364, tick, value, 100, 0] for tick, value in
                 [(1, -1), (2, -1), (4, 4.05), (6, 4.1), (7, 3.9), (9, 4.0), (14, 4.0)]]
    messages += [[2, 6, 364, tick, 1000] for tick in (0, 3, 5, 8)]
    messages += [[46, 6, 364, 45, '1793027024'], [57, 1, 364]]
    for values in messages:
        data = frame(values)
        raw.chunks = [data]
        received = c.conn.recvMsg()
        _, payload, remaining = comm.read_msg(received)
        assert not remaining
        c.msg_queue.put(payload)
        c.decoder.interpret(comm.read_fields(c.msg_queue.get()))
    c.record_quote_completion(364, 'snapshot_end')
    c.cancelMktData(364)
    assert ticker.snapshotEnd and ticker.marketDataTypeConfirmed
    assert ticker.bid <= 0 and ticker.ask <= 0  # SDK sentinels remain unusable.
    assert not c._market_events and not c._ticker_by_req_id and not c._active_market_req_ids
    c.disconnect(); d.close()
    result = d.snapshot()
    assert result['coverage_verified'] and result['absence_claims_valid']
    assert result['counters']['records_dropped'] == 0
    assert result['counters']['background_records_omitted'] > 300
    assert result['counters']['repeated_details_omitted'] > 20
    assert result['counters']['queue_put'] == result['counters']['queue_get'] == 104
    assert result['counters']['decoder_entry'] == result['counters']['decoder_return'] == 104
    assert result['counters']['quote_socket_calls'] == 1 and len(raw.sent) == 1
    assert len(result['records']) <= 64
    assert all(len(json.dumps(row, ensure_ascii=True).encode()) <= 4096 for row in result['records'])
    events = {row['event'] for row in result['records']}
    assert {'serialized_quote', 'wrapper_send', 'wrapper_completion', 'wrapper_cleanup',
            'quote_window_end', 'decoder_return'} <= events
    assert 'PRIVATE_' not in json.dumps(result) and '4.05' not in json.dumps(result)
