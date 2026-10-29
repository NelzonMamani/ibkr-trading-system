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


def test_target_overflow_keeps_final_capacity_and_invalidates_coverage(prepared):
    c, d, raw = prepared
    c.reqMktData(contract(), snapshot=True)
    for i in range(100):
        d.record('target_detail', request_id=364, ordinal=i)
    # Global traffic arriving after target saturation must not consume the
    # final reservation, even if its own eight samples were not yet used.
    for i in range(100):
        d.record('global_detail', request_id=-1)
    c.record_quote_completion(364, 'timeout'); c.cancelMktData(364)
    c.disconnect(); d.close()
    result = d.snapshot()
    assert not result['coverage_verified'] and not result['absence_claims_valid']
    assert result['counters']['records_dropped'] > 0
    assert {'wrapper_completion', 'quote_window_end', 'wrapper_cleanup'} <= {
        row['event'] for row in result['records']}
    assert len(result['records']) <= 64


def test_aggregate_dispatch_states_and_oversize_remain_explicit(prepared):
    c, d, raw = prepared
    c.reqMktData(contract(), snapshot=True)
    for arity in (True, True, False, False):
        d.record('decoder_entry', request_id=364, message_id=58, arity_ok=arity)
    entries = [r for r in d.records if r['event'] == 'decoder_entry']
    assert len(entries) == 2 and all(r['observations'] == 2 for r in entries)
    d.record('decoder_entry', request_id=364, message_id=58, arity_ok=True, text='x'*5000)
    assert d.counters['oversize'] == 1
    c.disconnect(); d.close()
    assert not d.snapshot()['coverage_verified']


@pytest.fixture
def orders_prepared(monkeypatch):
    """Actual SDK wire methods, only an in-memory socket; real connects forbidden."""
    violations = []
    def forbidden(*a, **kw):
        violations.append(True)
        raise AssertionError('No network, acquisition, mutation or execution')
    monkeypatch.setattr(sdk.EClient, 'connect', forbidden)
    for name in ('reqMktData','reqScannerSubscription','reqHistoricalData','reqPositions',
                 'reqPositionsMulti','placeOrder','cancelOrder','reqGlobalCancel'):
        monkeypatch.setattr(sdk.EClient, name, forbidden)
    c = IbkrClient('offline', 0, 71, 10, 'DELAYED', True)
    raw = MemorySocket()
    monkeypatch.setattr(Connection, 'connect', lambda conn:setattr(conn, 'socket', raw))
    original = (sdk.Connection, sdk.decoder.Decoder, sdk.reader.EReader, comm.read_msg)
    d = TransportDiagnostic(c, profile='final-orders'); d.__enter__()
    c.conn = sdk.Connection('offline', 0); c.conn.connect()
    c.setConnState(sdk.EClient.CONNECTED); c.serverVersion_ = 151
    c.decoder = sdk.decoder.Decoder(c, 151)
    yield c,d,raw
    c.disconnect(); d.close()
    assert original == (sdk.Connection,sdk.decoder.Decoder,sdk.reader.EReader,comm.read_msg)
    assert not violations
    assert 'reqAllOpenOrders' not in vars(c) and 'openOrderEnd' not in vars(c)


def drain_orders(c,d,raw,data):
    raw.chunks = [data[:2],data[2:5],data[5:],b'']
    reader = sdk.reader.EReader(c.conn,c.msg_queue)
    reader.start(); reader.join(2)
    assert not reader.is_alive()
    c._run_loop()  # Actual native callback loop -> SDK decoder -> original callback.
    d.close()
    return d.snapshot()


def test_orders_actual_serializer_fragmented_end_and_complete_stage_chain(orders_prepared):
    c,d,raw = orders_prepared
    c.reqAllOpenOrders()
    assert len(raw.sent)==1 and raw.sent[0][0] == frame([16,1])
    proof = drain_orders(c,d,raw,frame([53,1]))
    assert c._open_orders_event.is_set()
    assert proof['coverage_verified'] and proof['absence_claims_valid']
    assert proof['last_positive_stage']=='end_callback'
    for stage in ('frame','put','get','decode','decoded'):
        assert proof['counters'][stage+'_ORDER_END']==1
    assert proof['counters']['order_full_send']==1
    assert proof['reader_stopped'] and proof['callback_loop_stopped'] and proof['hooks_restored']


@pytest.mark.parametrize('outcome',['short','exception','no_end','partial_frame','unknown','bad_end','bad_order','bad_error'])
def test_order_wire_and_schema_failures_are_honest(orders_prepared,outcome):
    c,d,raw = orders_prepared
    if outcome=='short':raw.short=True
    if outcome=='exception':
        raw.send=lambda *a,**kw:(_ for _ in ()).throw(OSError('PRIVATE_PAYLOAD'))
        with pytest.raises(OSError):c.reqAllOpenOrders()
    else:c.reqAllOpenOrders()
    data = {'partial_frame':frame([53,1])[:5], 'unknown':frame([999,'PRIVATE_PAYLOAD']),
            'bad_end':frame([53,1,'PRIVATE_PAYLOAD']), 'bad_order':frame([5]),
            'bad_error':frame([4,2])}.get(outcome,b'')
    proof=drain_orders(c,d,raw,data)
    if outcome=='bad_order':
        assert d.counters['decoder_exception']==1
    if outcome=='no_end':
        assert proof['coverage_verified'] and proof['absence_claims_valid']
    elif outcome in ('short','exception'):
        assert not proof['absence_claims_valid']
        assert proof['last_positive_stage'] != 'local_socket_accepted'
    else:assert not proof['coverage_verified'] and not proof['absence_claims_valid']
    assert not c._open_orders_event.is_set()
    assert d.counters['order_query_calls']==1


@pytest.mark.parametrize('broken',['record','count','_facts','_wire','_order_stage'])
def test_order_observer_failure_cannot_change_sdk_dispatch(orders_prepared,monkeypatch,broken):
    c,d,raw=orders_prepared
    def fail(*a,**kw):raise RuntimeError('PRIVATE_PAYLOAD')
    monkeypatch.setattr(d,broken,fail)
    c.reqAllOpenOrders()
    assert len(raw.sent)==1
    drain_orders(c,d,raw,frame([53,1]))
    assert c._open_orders_event.is_set()  # Observer is never completion authority.
    assert not d.snapshot()['coverage_verified']


def test_order_privacy_caps_aggregation_and_final_reservation(orders_prepared,tmp_path):
    c,d,raw=orders_prepared
    secret='PRIVATE_PAYLOAD_ACCOUNT_ORDER_SYMBOL'
    for _ in range(200):d.record('socket_send',requested=1,returned=1)
    c.reqAllOpenOrders()
    for _ in range(1000):d.record('order_callback',symbol=secret,orderId=secret,errorString=secret)
    for _ in range(100):
        d.record('decoder_entry',kind='ORDER',message_id=5,field_count=8,handler_known=True)
    # Force distinct allowed detail records beyond target budget, no evidence eviction.
    for i in range(70):d.record('socket_send',requested=i,returned=i)
    d.record('end_callback');d.record('order_cleanup',counters=dict(d.counters))
    proof=drain_orders(c,d,raw,frame([53,1]))
    assert len(proof['records'])<=64
    assert all(len(json.dumps(r,ensure_ascii=True).encode())<=4096 for r in proof['records'])
    assert d.counters['background_records_omitted']>0 and d.counters['repeated_details_omitted']>0
    assert d.counters['records_dropped']>0 and not proof['coverage_verified']
    assert any(r['event']=='order_cleanup' for r in proof['records'])
    from src.ibkr.evidence_safety import write_json,scan_artifacts
    write_json(tmp_path/'proof.json',proof)
    assert secret not in (tmp_path/'proof.json').read_text()
    assert scan_artifacts(tmp_path)['passed']


@pytest.mark.parametrize('gap',['frame','put','get','decode'])
def test_order_end_processing_gaps_report_last_positive_stage(orders_prepared,gap):
    c,d,raw=orders_prepared;c.reqAllOpenOrders()
    body=comm.read_fields(comm.read_msg(frame([53,1]))[1])
    if gap in ('put','get','decode'):c.msg_queue.put(b'53\0' + b'1\0')
    if gap in ('get','decode'):
        fields=comm.read_fields(c.msg_queue.get())
    if gap=='decode':c.decoder.interpret(fields)
    c.disconnect();d.close();proof=d.snapshot()
    expected={'frame':'end_frame','put':'end_queued','get':'end_dequeued','decode':'end_callback'}[gap]
    assert proof['last_positive_stage']==expected
    assert not proof['coverage_verified']  # These intentionally bypass reader/loop lifecycle.
    assert ('end_callback_not_observed' in proof['unknowns'])==(gap!='decode')


def test_order_reader_exception_logs_no_payload_and_invalidates_absence(orders_prepared,caplog,tmp_path):
    c,d,raw=orders_prepared;c.reqAllOpenOrders()
    secret='PRIVATE_PAYLOAD_ACCOUNT_ORDER_SYMBOL'
    raw.chunks=[RuntimeError(secret)]
    reader=sdk.reader.EReader(c.conn,c.msg_queue);reader.start();reader.join(2)
    assert not reader.is_alive()
    c.disconnect();d.close();proof=d.snapshot()
    assert d.counters['reader_logged_exception']==1 and not proof['coverage_verified']
    assert secret not in caplog.text and secret not in json.dumps(proof)
    from src.ibkr.evidence_safety import write_json,scan_artifacts
    write_json(tmp_path/'evidence.json',proof)
    assert scan_artifacts(tmp_path)['passed']


def test_order_successful_nonempty_error_provenance_never_exports_payload(orders_prepared):
    c,d,raw=orders_prepared;c.reqAllOpenOrders()
    secret='PRIVATE_PAYLOAD_ACCOUNT_ORDER_SYMBOL'
    # Error transport through actual SDK signature handler, with original text
    # processed privately by native owner. No error text or request/order ID retained.
    proof=drain_orders(c,d,raw,frame([4,2,987654,321,secret])+frame([53,1]))
    assert proof['counters']['error_callback_return']==1
    assert proof['counters']['get_ERROR']==proof['counters']['decode_ERROR']==1
    assert secret not in json.dumps(proof) and '987654' not in json.dumps(proof)
    assert proof['coverage_verified']


def test_order_startup_burst_and_many_rows_do_not_consume_final_budget(orders_prepared):
    c,d,raw=orders_prepared
    for _ in range(500):d.record('socket_send',requested=1,returned=1)
    c.reqAllOpenOrders()
    # Equivalent callback/detail bursts have first-sample detail plus counts.
    for _ in range(1000):
        d.record('order_callback')
        for event in ('frame_progress','queue_put','queue_get','decoder_entry','decoder_return'):
            d.record(event,kind='ORDER',message_id=5,field_count=100,complete=True)
    proof=drain_orders(c,d,raw,frame([53,1]))
    assert proof['coverage_verified'] and d.counters['records_dropped']==0
    assert d.counters['background_records_omitted'] and d.counters['repeated_details_omitted']
    assert len(d.records)<56 and any(r['event']=='order_cleanup' for r in d.records)


def test_order_queue_observer_failure_preserves_item_and_return(orders_prepared,monkeypatch):
    c,d,raw=orders_prepared;c.reqAllOpenOrders()
    def fail(*a,**kw):raise RuntimeError('PRIVATE_PAYLOAD')
    monkeypatch.setattr(c.msg_queue,'qsize',fail)
    item=b'53\0' + b'1\0'
    assert c.msg_queue.put(item) is None
    assert c.msg_queue.get() is item
    assert not d.snapshot()['coverage_verified'] and d.observation_failed


@pytest.mark.parametrize('kind',['status','order'])
@pytest.mark.parametrize('trailing',[False,True])
def test_order_custom_sdk_schema_consumption_and_nonempty_native_callback(orders_prepared,kind,trailing):
    c,d,raw=orders_prepared;c.reqAllOpenOrders()
    if kind=='status':
        values=[3,123,'Submitted',0,1,0,0,0,0,71,'',0]
    else:
        # Explicitly synthetic minimal SDK151 OPEN_ORDER shape: no optional legs,
        # conditions or algorithms. Actual pinned SDK must consume all130 fields.
        values=[5]+[0]*129
        values[3]='PRIVATE_SYMBOL_CANARY';values[20]='PRIVATE_ACCOUNT_CANARY'
    if trailing:values+=['PRIVATE_TRAILING_CANARY']
    proof=drain_orders(c,d,raw,frame(values)+frame([53,1]))
    assert c._open_orders_event.is_set()  # Original callback/authority unaffected.
    if kind=='order':assert len(c._open_orders_snapshot)==1 and d.counters['order_callback_return']==1
    else:assert c._order_status[123]['status']=='Submitted'
    assert proof['coverage_verified']==(not trailing)
    assert proof['absence_claims_valid']==(not trailing)
    assert 'PRIVATE_' not in json.dumps(proof)


def test_order_old_decoder_and_callbacks_cannot_complete_new_instance(orders_prepared,monkeypatch):
    old,diagnostic,raw=orders_prepared
    old.reqAllOpenOrders();old_decoder=old.decoder
    drain_orders(old,diagnostic,raw,b'')
    fresh=IbkrClient('offline',0,71,10,'DELAYED',True);socket2=MemorySocket()
    monkeypatch.setattr(Connection,'connect',lambda conn:setattr(conn,'socket',socket2))
    observer=TransportDiagnostic(fresh,profile='final-orders');observer.__enter__()
    try:
        fresh.conn=sdk.Connection('offline',0);fresh.conn.connect()
        fresh.setConnState(sdk.EClient.CONNECTED);fresh.serverVersion_=151
        fresh.decoder=sdk.decoder.Decoder(fresh,151);fresh.reqAllOpenOrders()
        old_decoder.interpret([b'53',b'1']);old.openOrderEnd()
        assert not fresh._open_orders_event.is_set() and observer.counters['end_callback_entry']==0
        proof=drain_orders(fresh,observer,socket2,b'')
        assert proof['coverage_verified'] and proof['absence_claims_valid']
    finally:fresh.disconnect();observer.close()


def test_order_partial_install_and_restoration_failure_never_valid_absence(monkeypatch):
    c=IbkrClient('offline',0,71,10,'DELAYED',True)
    originals=(sdk.Connection,sdk.decoder.Decoder,sdk.reader.EReader,comm.read_msg)
    d=TransportDiagnostic(c,profile='final-orders');patch=d.patch
    def fail(obj,name,value):
        if name=='reqAllOpenOrders':raise RuntimeError('PRIVATE_PAYLOAD')
        return patch(obj,name,value)
    monkeypatch.setattr(d,'patch',fail)
    with pytest.raises(RuntimeError):d.__enter__()
    assert originals==(sdk.Connection,sdk.decoder.Decoder,sdk.reader.EReader,comm.read_msg)
    assert d.restored and not d.snapshot()['absence_claims_valid']


def test_order_restore_retry_is_still_incomplete_after_any_failure(orders_prepared,monkeypatch):
    c,d,raw=orders_prepared;c.reqAllOpenOrders()
    from types import SimpleNamespace
    class RestoreTripwire(SimpleNamespace):
        blocked=True
        def __setattr__(self,name,value):
            if name=='value' and self.blocked:raise RuntimeError('PRIVATE_PAYLOAD')
            return super().__setattr__(name,value)
    obj=RestoreTripwire();obj.blocked=False;obj.value='patched';obj.blocked=True
    d.patches.append((obj,'value',True,'original'))
    c.disconnect();d.close()
    assert not d.restored and not d.snapshot()['coverage_verified']
    obj.blocked=False;d.close()
    assert d.restored and obj.value=='original' and not d.snapshot()['absence_claims_valid']


def test_order_reader_join_failure_still_restores_all_hooks(orders_prepared):
    c,d,raw=orders_prepared;c.reqAllOpenOrders()
    class Reader:
        ident=123
        def join(self,timeout):
            assert timeout==2
            raise RuntimeError('PRIVATE_PAYLOAD')
        def is_alive(self):return True
    d.reader=Reader();c.disconnect();d.close()
    assert 'reqAllOpenOrders' not in vars(c) and 'get' not in vars(c.msg_queue)
    assert not d.reader_stopped and not d.snapshot()['coverage_verified']
    d.reader=None;d.close()  # Retire only this synthetic failing-reader fixture.


@pytest.mark.parametrize('failure',['missing','none','decoder'])
def test_order_missing_handler_and_decoder_failure_are_incomplete(orders_prepared,failure):
    c,d,raw=orders_prepared;c.reqAllOpenOrders()
    if failure=='missing':c.decoder.msgId2handleInfo.pop(53)
    else:
        def process(*args):
            if failure=='decoder':raise RuntimeError('PRIVATE_PAYLOAD')
        c.decoder.msgId2handleInfo[53]=NS(wrapperMeth=None,wrapperParams=None,
            processMeth=process if failure=='decoder' else None)
    proof=drain_orders(c,d,raw,frame([53,1]))
    assert not proof['coverage_verified'] and not proof['absence_claims_valid']
    assert not c._open_orders_event.is_set()
