"""Official-SDK observer controls. In-memory sockets only; no TWS acquisition."""
from importlib import import_module, metadata
import json
import threading

import pytest

pytestmark = pytest.mark.skipif(metadata.version('ibapi') != '10.50.2', reason='official SDK profile')


def proto_frame(message_id, name, **values):
    from ibapi import comm
    message = getattr(import_module('ibapi.protobuf.' + name + '_pb2'), name)(**values)
    return comm.make_msg_proto(message_id + 200, message.SerializeToString())


class MemorySocket:
    def __init__(self):
        self.sent, self.chunks = [], []
        self.closed = False
    def send(self, data, *args, **kwargs):
        self.sent.append(bytes(data))
        return len(data)
    def recv(self, size, *args, **kwargs):
        return self.chunks.pop(0) if self.chunks else b''
    def close(self):
        self.closed = True


@pytest.fixture
def prepare(monkeypatch):
    from ibapi import client as sdk, comm
    from ibapi.wrapper import EWrapper
    from ibapi.connection import Connection
    from src.ibkr.quote_diagnostics import QuoteDiagnostics
    from src.ibkr.transport_diagnostic import TransportDiagnostic
    created = []
    class Client(sdk.EClient, EWrapper):
        def __init__(self):
            sdk.EClient.__init__(self, self)
            self._quote_trace = QuoteDiagnostics(71)
            self._stop_event = threading.Event()
            self._thread = None
            self.events = []
        def _run_loop(self):
            return sdk.EClient.run(self)
        def tickPrice(self, request, tick, value, attributes):
            self.events.append(('price', request, tick))
            self._quote_trace.callback(request, 'tickPrice', 'accepted', owner='MARKET_DATA', tick_type=tick)
        def tickSize(self, request, tick, value):
            self.events.append(('size', request, tick))
            self._quote_trace.callback(request, 'tickSize', 'accepted', owner='MARKET_DATA', tick_type=tick)
        def marketDataType(self, request, returned):
            self.events.append(('type', request, returned))
            self._quote_trace.callback(request, 'marketDataType', 'accepted', owner='MARKET_DATA', returned_type=returned)
        def tickSnapshotEnd(self, request):
            self.events.append(('end', request))
            self._quote_trace.callback(request, 'tickSnapshotEnd', 'accepted', owner='MARKET_DATA')
        def openOrderEnd(self):
            self.events.append(('orders_end',))
        def error(self, request, error_time, code, text, advanced_json=''):
            self.events.append(('error', request, code))
    def factory(profile='quotes', server_version=219):
        client = Client()
        raw = MemorySocket()
        monkeypatch.setattr(Connection, 'connect', lambda connection: setattr(connection, 'socket', raw))
        owner = TransportDiagnostic(client, profile=profile)
        original = (sdk.Connection, sdk.decoder.Decoder, sdk.reader.EReader, comm.read_msg)
        owner.__enter__()
        client.conn = sdk.Connection('unused', 0)
        client.conn.connect()
        client.serverVersion_ = server_version
        client.setConnState(sdk.EClient.CONNECTED)
        client.decoder = sdk.decoder.Decoder(client, server_version)
        created.append((client, owner, original))
        return client, owner, raw
    yield factory
    for client, owner, original in reversed(created):
        client.disconnect()
        owner.close()
        assert (sdk.Connection, sdk.decoder.Decoder, sdk.reader.EReader, comm.read_msg) == original
        assert 'put' not in vars(client.msg_queue) and '_emit' not in vars(client._quote_trace)


def request_quote(client):
    from ibapi.contract import Contract
    contract = Contract()
    contract.conId, contract.symbol, contract.secType = 123, 'SYNTH', 'STK'
    contract.exchange, contract.primaryExchange, contract.currency = 'SMART', 'NASDAQ', 'USD'
    client._quote_trace.start(41, contract, 'LIVE', '', True, False, [])
    client.reqMktData(41, contract, '', True, False, [])
    return contract


def drain(client, raw, payload):
    from ibapi import client as sdk
    raw.chunks = [payload[:2], payload[2:7], payload[7:], b'']
    reader = sdk.reader.EReader(client.conn, client.msg_queue)
    reader.start()
    reader.join(2)
    assert not reader.is_alive()
    client._run_loop()


def test_actual_protobuf_send_reader_queue_decoder_and_callbacks(prepare):
    client, owner, raw = prepare()
    contract = request_quote(client)
    assert len(raw.sent) == 1
    # Compare the observed bytes with an untouched SDK sender, not a second
    # serializer or an observer-generated frame. No socket is opened.
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from types import SimpleNamespace
    baseline = EClient(EWrapper())
    direct = []
    baseline.conn = SimpleNamespace(isConnected=lambda: True, sendMsg=direct.append)
    baseline.serverVersion_ = 219
    baseline.setConnState(EClient.CONNECTED)
    baseline.reqMktData(41, contract, '', True, False, [])
    assert direct == raw.sent
    serialized = next(row for row in owner.records if row['event'] == 'serialized_quote')
    assert serialized['schema_verified'] and serialized['fields']['request_id'] == '41'
    assert serialized['fields']['snapshot'] == '1' and serialized['fields']['regulatory_snapshot'] == '0'
    assert serialized['bytes'] == len(raw.sent[0])
    data = b''.join([
        proto_frame(58, 'MarketDataType', reqId=41, marketDataType=1),
        proto_frame(1, 'TickPrice', reqId=41, tickType=4, price=4.051234, size='0.5', attrMask=0),
        proto_frame(2, 'TickSize', reqId=41, tickType=8, size='1000000.25'),
        proto_frame(57, 'TickSnapshotEnd', reqId=41),
    ])
    drain(client, raw, data)
    assert ('end', 41) in client.events and ('size', 41, 8) in client.events
    assert owner.counters['decoder_entry'] == owner.counters['decoder_return'] == 4
    assert owner.counters['queue_put'] == owner.counters['queue_get'] == 4
    assert owner.counters['quote_socket_calls'] == owner.counters['serialized_quotes_verified'] == 1
    assert owner.counters['quote_send_requested'] == owner.counters['quote_send_returned'] == len(raw.sent[0])
    owner.close()
    snapshot = owner.snapshot()
    assert snapshot['coverage_verified'] and snapshot['absence_claims_valid']
    from src.ibkr.sdk_profile import OFFICIAL_SDK_SOURCE_SHA256
    assert snapshot['source_hashes']['official_sdk_source_tree'] == OFFICIAL_SDK_SOURCE_SHA256
    text = json.dumps(snapshot)
    assert '4.051234' not in text and '1000000.25' not in text
    assert '"size":' not in text and '"price":' not in text


def test_modern_sdk_legacy_decoder_branch_is_observed_without_replacing_dispatch(prepare):
    from ibapi import comm
    client, owner, raw = prepare(server_version=190)
    request_quote(client)
    wire = next(row for row in owner.records if row['event'] == 'serialized_quote')
    assert wire['schema_verified'] and wire['bytes'] == len(raw.sent[0])
    client.decoder.interpret([b'1', b'41', b'1'], 58)
    client.decoder.interpret([b'1', b'41'], 57)
    assert ('type', 41, 1) in client.events and ('end', 41) in client.events
    assert owner.counters['decoder_entry'] == owner.counters['decoder_return'] == 2
    assert owner.counters['hook_errors'] == 0


def test_modern_binary_nonprotobuf_frame_uses_physical_size(prepare):
    from ibapi import comm
    client, owner, raw = prepare(server_version=201)
    # Market-data protobuf starts at206, so201 still serializes legacy fields
    # under the modern raw-int message-ID envelope.
    request_quote(client)
    wire = next(row for row in owner.records if row['event'] == 'serialized_quote')
    assert wire['schema_verified'] and wire['bytes'] == len(raw.sent[0])
    assert int.from_bytes(raw.sent[0][4:8], 'big') == 1
    assert owner.counters['serialized_quotes_verified'] == 1


def test_unknown_or_malformed_protobuf_invalidates_coverage_without_private_text(prepare):
    from src.ibkr.transport_diagnostic import _modern_message
    client, owner, raw = prepare()
    request_quote(client)
    valid = proto_frame(57, 'TickSnapshotEnd', reqId=41)[4:]
    unknown = valid + b'\xf8\x07\x01'  # Unknown field127, not a guessed supported schema.
    facts = owner._facts(unknown)
    assert facts['schema_known'] is False
    assert owner.counters['unverified_quote_schema'] == 1
    invalid = owner._facts((257).to_bytes(4, 'big') + b'PRIVATE_BROKER_ACCOUNT_PRICE')
    assert invalid['schema_known'] is False
    assert _modern_message((999).to_bytes(4, 'big') + b'PRIVATE_BROKER_ACCOUNT_PRICE') == {'kind': 'OTHER'}
    client.disconnect(); owner.close()
    assert not owner.snapshot()['coverage_verified']
    assert 'PRIVATE' not in json.dumps(owner.snapshot())


def test_actual_protobuf_order_end_coverage_and_error_code_position(prepare):
    client, owner, raw = prepare(profile='final-orders')
    client.reqAllOpenOrders()
    assert len(raw.sent) == 1
    assert owner.counters['order_serialized'] == owner.counters['order_socket_calls'] == 1
    data = b''.join([
        proto_frame(4, 'ErrorMessage', id=-1, errorTime=1234567890, errorCode=2104,
                    errorMsg='PRIVATE_ACCOUNT_ORDER_ERROR'),
        proto_frame(53, 'OpenOrdersEnd'),
    ])
    drain(client, raw, data)
    owner.close()
    result = owner.snapshot()
    assert result['coverage_verified'] and result['absence_claims_valid']
    assert result['end_last_positive_stage'] == 'end_callback'
    assert result['counters']['reader_start'] == result['counters']['reader_exit'] == 1
    assert result['counters']['loop_start'] == result['counters']['loop_exit'] == 1
    identity = next(row for row in result['records'] if row['event'] == 'sdk_identity')
    assert identity['sdk_distribution'] == '10.50.2' and identity['sdk_source_count'] == 235
    error = next(row for row in result['records'] if row['event'] == 'error_callback')
    assert error['error_code'] == 2104  # errorTime must never be mistaken for code.
    assert 'PRIVATE' not in json.dumps(result) and '1234567890' not in json.dumps(result)


def test_unknown_outgoing_protobuf_fields_do_not_verify_serialization(prepare):
    client, owner, raw = prepare()
    request_quote(client)
    body = raw.sent[0][8:] + b'\xf8\x07\x01'
    assert owner._wire_proto(body, 1, len(body) + 8) is None
    assert owner.counters['unverified_quote_schema'] == 1
    client.disconnect(); owner.close()
    assert not owner.snapshot()['coverage_verified']
