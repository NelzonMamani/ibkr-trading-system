"""Real pinned SDK serialization into an in-memory connection, never a socket."""
from decimal import Decimal
from importlib import metadata
import socket
import threading

import pytest

from src.ibkr import mutation_audit as audit, sdk_profile as profile

pytestmark = pytest.mark.skipif(metadata.version("ibapi") != profile.OFFICIAL_SDK_VERSION,
    reason="requires the isolated pinned official SDK profile")


@pytest.fixture
def paper_sdk(monkeypatch):
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from src.config.config_resolver import set_config_overrides

    def no_socket(*args, **kwargs):
        pytest.fail("Offline PAPER serialization must never create a socket")
    set_config_overrides(dict(RUN_MODE="PAPER", RUN_MODE_EFFECTIVE="PAPER",
        EXECUTION_ENABLED=True, EXECUTION_ENABLED_EFFECTIVE=True, IBKR_READONLY_ENABLED=False))
    monkeypatch.setattr(socket, "socket", no_socket)
    assert profile.require_supported_sdk() == profile.OFFICIAL_SDK_VERSION
    audit.install_sdk(EClient, EWrapper)

    class Connection:
        def __init__(self):
            self.messages = []
            self.connected = True
        def isConnected(self):
            return self.connected
        def sendMsg(self, message):
            self.messages.append(message)
        def disconnect(self):
            self.connected = False

    class Wrapper(EWrapper):
        def error(self, *args):
            pytest.fail("SDK rejected an offline serialization fixture")

    client = EClient(Wrapper())
    client.conn = Connection()
    client.connState = EClient.CONNECTED
    client.host, client.port = "127.0.0.1", 7497
    client.serverVersion_ = 222
    client.readonly_enabled = False
    client._managed_accounts = ["DU10001"]
    client._managed_accounts_event = threading.Event()
    client._managed_accounts_event.set()
    client._position_transport_available = True
    client._stop_event = threading.Event()
    try:
        yield client
    finally:
        set_config_overrides(None)
        assert getattr(audit._local, "delegations", ()) == ()


def _arguments(account="DU10001"):
    from ibapi.contract import Contract
    from ibapi.order import Order
    contract = Contract()
    contract.conId, contract.symbol, contract.secType = 12345, "ABCD", "STK"
    contract.exchange, contract.primaryExchange, contract.currency = "SMART", "NASDAQ", "USD"
    order = Order()
    order.account, order.action, order.totalQuantity = account, "BUY", Decimal("1")
    order.orderType, order.lmtPrice, order.tif = "LMT", 2.75, "DAY"
    order.transmit, order.outsideRth, order.whatIf = False, True, False
    order.orderRef = "offline-paper-wire-proof"
    return contract, order


def _decode(frame, message_type, expected_id):
    from ibapi.common import PROTOBUF_MSG_ID
    assert int.from_bytes(frame[:4], "big") == len(frame) - 4
    assert int.from_bytes(frame[4:8], "big") == expected_id + PROTOBUF_MSG_ID
    message = message_type()
    message.ParseFromString(frame[8:])
    return message


def test_legacy_sdk_entries_serialize_place_modify_cancel_exactly_once(paper_sdk):
    from ibapi.message import OUT
    from ibapi.order_cancel import OrderCancel
    from ibapi.protobuf.PlaceOrderRequest_pb2 import PlaceOrderRequest
    from ibapi.protobuf.CancelOrderRequest_pb2 import CancelOrderRequest
    from ibapi.protobuf.GlobalCancelRequest_pb2 import GlobalCancelRequest
    client = paper_sdk
    contract, order = _arguments()
    client.placeOrder(71, contract, order)
    order.totalQuantity, order.lmtPrice, order.transmit = Decimal("2"), 2.8, True
    client.placeOrder(71, contract, order)
    cancel = OrderCancel()
    cancel.manualOrderCancelTime = "20261124-12:00:00"
    client.cancelOrder(71, cancel)
    client.reqGlobalCancel(OrderCancel())
    assert audit.snapshot() == dict(place=1, modify=1, cancel=2)
    assert len(client.conn.messages) == 4
    first = _decode(client.conn.messages[0], PlaceOrderRequest, OUT.PLACE_ORDER)
    second = _decode(client.conn.messages[1], PlaceOrderRequest, OUT.PLACE_ORDER)
    assert first.orderId == second.orderId == 71
    assert first.contract.symbol == "ABCD" and first.contract.conId == 12345
    assert first.contract.exchange == "SMART" and first.contract.currency == "USD"
    assert first.order.account == second.order.account == "DU10001"
    assert (first.order.action, first.order.orderType, first.order.tif) == ("BUY", "LMT", "DAY")
    assert first.order.totalQuantity == "1" and second.order.totalQuantity == "2"
    assert first.order.lmtPrice == 2.75 and second.order.lmtPrice == 2.8
    assert first.order.transmit is False and second.order.transmit is True
    assert first.order.outsideRth is True and first.order.whatIf is False
    assert first.order.orderRef == "offline-paper-wire-proof"
    cancelled = _decode(client.conn.messages[2], CancelOrderRequest, OUT.CANCEL_ORDER)
    assert cancelled.orderId == 71
    assert cancelled.orderCancel.manualOrderCancelTime == cancel.manualOrderCancelTime
    _decode(client.conn.messages[3], GlobalCancelRequest, OUT.REQ_GLOBAL_CANCEL)


def test_direct_protobuf_entries_and_replayed_request_are_separate_attempts(paper_sdk):
    from ibapi.client_utils import createPlaceOrderRequestProto, createCancelOrderRequestProto, createGlobalCancelRequestProto
    from ibapi.order_cancel import OrderCancel
    client = paper_sdk
    contract, order = _arguments()
    request = createPlaceOrderRequestProto(71, contract, order)
    client.placeOrderProtoBuf(request)
    client.placeOrderProtoBuf(request)
    client.cancelOrderProtoBuf(createCancelOrderRequestProto(71, OrderCancel()))
    client.reqGlobalCancelProtoBuf(createGlobalCancelRequestProto(OrderCancel()))
    assert audit.snapshot() == dict(place=1, modify=1, cancel=2)
    assert len(client.conn.messages) == 4


@pytest.mark.parametrize("entry", ["legacy", "protobuf"])
@pytest.mark.parametrize("account,field,value", [
    ("U10001", None, None), ("DU10002", None, None),
    ("DU10001", "faGroup", "UnverifiedGroup"), ("DU10001", "modelCode", "UnverifiedModel"),
])
def test_order_scope_cannot_redirect_outside_exclusive_paper_account(paper_sdk, entry, account, field, value):
    from ibapi.client_utils import createPlaceOrderRequestProto
    contract, order = _arguments(account)
    if field:
        setattr(order, field, value)
    with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
        if entry == "legacy":
            paper_sdk.placeOrder(71, contract, order)
        else:
            paper_sdk.placeOrderProtoBuf(createPlaceOrderRequestProto(71, contract, order))
    assert audit.snapshot() == dict(place=1, modify=0, cancel=0)
    assert paper_sdk.conn.messages == []


@pytest.mark.parametrize("case", ["instance_readonly", "execution_off", "read_only_mode", "live_mode", "sim_mode"])
def test_profile_never_replaces_existing_execution_guards(paper_sdk, case):
    from src.config.config_resolver import set_config_overrides
    if case == "instance_readonly":
        paper_sdk.readonly_enabled = True
    else:
        mode = {"read_only_mode": "READ_ONLY", "live_mode": "LIVE", "sim_mode": "SIM"}.get(case, "PAPER")
        enabled = case != "execution_off"
        set_config_overrides(dict(RUN_MODE=mode, RUN_MODE_EFFECTIVE=mode, EXECUTION_ENABLED=enabled,
            EXECUTION_ENABLED_EFFECTIVE=enabled, IBKR_READONLY_ENABLED=False))
    with pytest.raises(RuntimeError):
        paper_sdk.placeOrder(71, *_arguments())
    assert paper_sdk.conn.messages == []
    assert audit.snapshot() == dict(place=1, modify=0, cancel=0)


@pytest.mark.parametrize("case", ["callback", "callback_same", "twice", "raw_reentry", "cross_client", "altered_id", "altered_quantity"])
def test_sdk_projection_receipt_cannot_hide_distinct_or_altered_requests(paper_sdk, monkeypatch, case):
    import ibapi.client as client_module
    from ibapi.client_utils import createPlaceOrderRequestProto
    client = paper_sdk
    contract, order = _arguments()
    if case.startswith("altered"):
        original_creator = client_module.createPlaceOrderRequestProto
        def changed_creator(*args):
            request = original_creator(*args)
            if case == "altered_id":
                request.orderId = 72
            else:
                request.order.totalQuantity = "999"
            return request
        monkeypatch.setattr(client_module, "createPlaceOrderRequestProto", changed_creator)
        client.placeOrder(71, contract, order)
        assert audit.snapshot() == (dict(place=2, modify=0, cancel=0) if case == "altered_id"
            else dict(place=1, modify=1, cancel=0))
        return
    entered = False
    original_use_proto = client.useProtoBuf
    def callback(message_id):
        nonlocal entered
        if not entered:
            entered = True
            if case == "raw_reentry":
                type(client).placeOrder.__wrapped__(client, 72, contract, order)
            elif case == "cross_client":
                other = type(client)(client.wrapper)
                other.__dict__.update(client.__dict__)
                other.placeOrderProtoBuf(createPlaceOrderRequestProto(72, contract, order))
            else:
                client.placeOrderProtoBuf(createPlaceOrderRequestProto(71 if case == "callback_same" else 72, contract, order))
                if case == "twice":
                    client.placeOrderProtoBuf(createPlaceOrderRequestProto(72, contract, order))
        return original_use_proto(message_id)
    monkeypatch.setattr(client, "useProtoBuf", callback)
    client.placeOrder(71, contract, order)
    assert audit.snapshot() == dict(place=1 if case == "callback_same" else 2,
        modify=int(case in {"twice", "callback_same"}), cancel=0)
    assert len(client.conn.messages) == (3 if case == "twice" else 2)


@pytest.mark.parametrize("changed_guard", ["readonly", "account", "disconnected"])
def test_exact_internal_delegation_still_rechecks_current_guards(paper_sdk, monkeypatch, changed_guard):
    client = paper_sdk
    original_use_proto = client.useProtoBuf
    def change_guard(message_id):
        if changed_guard == "readonly":
            client.readonly_enabled = True
        elif changed_guard == "account":
            client._managed_accounts = ["U10001"]
        else:
            client.connState = type(client).DISCONNECTED
        return original_use_proto(message_id)
    monkeypatch.setattr(client, "useProtoBuf", change_guard)
    with pytest.raises(RuntimeError):
        client.placeOrder(71, *_arguments())
    assert audit.snapshot() == dict(place=1, modify=0, cancel=0)
    assert client.conn.messages == []


@pytest.mark.parametrize("changed_field", ["quantity", "contract", "account"])
def test_sdk_projection_compares_payload_after_snapshot_without_factory_changes(paper_sdk, monkeypatch, changed_field):
    client = paper_sdk
    contract, order = _arguments()
    original_use_proto = client.useProtoBuf
    def change_payload(message_id):
        if changed_field == "quantity":
            order.totalQuantity = Decimal("999")
        elif changed_field == "contract":
            contract.symbol = "CHANGED"
        else:
            order.account = "U10001"
        return original_use_proto(message_id)
    monkeypatch.setattr(client, "useProtoBuf", change_payload)
    if changed_field == "account":
        with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
            client.placeOrder(71, contract, order)
        assert client.conn.messages == []
    else:
        client.placeOrder(71, contract, order)
        assert len(client.conn.messages) == 1
    assert audit.snapshot() == dict(place=1, modify=1, cancel=0)


@pytest.mark.parametrize("method", ["cancelOrder", "reqGlobalCancel"])
@pytest.mark.parametrize("changed_payload", [False, True])
def test_sdk_cancellation_projection_does_not_hide_reentry_or_changed_fields(paper_sdk, monkeypatch, method, changed_payload):
    from ibapi.order_cancel import OrderCancel
    from ibapi.client_utils import createCancelOrderRequestProto, createGlobalCancelRequestProto
    client = paper_sdk
    cancel = OrderCancel()
    original_use_proto = client.useProtoBuf
    entered = False
    def callback(message_id):
        nonlocal entered
        if not entered:
            entered = True
            if changed_payload:
                cancel.manualOrderCancelTime = "20261124-12:00:00"
            elif method == "cancelOrder":
                client.cancelOrderProtoBuf(createCancelOrderRequestProto(71, cancel))
            else:
                client.reqGlobalCancelProtoBuf(createGlobalCancelRequestProto(cancel))
        return original_use_proto(message_id)
    monkeypatch.setattr(client, "useProtoBuf", callback)
    if method == "cancelOrder":
        client.cancelOrder(71, cancel)
    else:
        client.reqGlobalCancel(cancel)
    assert audit.snapshot() == dict(place=0, modify=0, cancel=2)
    assert len(client.conn.messages) == (1 if changed_payload else 2)


@pytest.mark.parametrize("method", ["placeOrderProtoBuf", "cancelOrderProtoBuf", "reqGlobalCancelProtoBuf"])
def test_duck_typed_protobuf_cannot_report_one_scope_and_serialize_another(paper_sdk, method):
    from ibapi.client_utils import createPlaceOrderRequestProto, createCancelOrderRequestProto, createGlobalCancelRequestProto
    from ibapi.order_cancel import OrderCancel
    allowed = createPlaceOrderRequestProto(71, *_arguments())
    redirected = createPlaceOrderRequestProto(71, *_arguments("U10001"))
    if method == "cancelOrderProtoBuf":
        allowed = createCancelOrderRequestProto(71, OrderCancel())
    elif method == "reqGlobalCancelProtoBuf":
        allowed = createGlobalCancelRequestProto(OrderCancel())
    class Proxy:
        def __getattr__(self, name):
            return getattr(allowed, name)
        def SerializeToString(self, *args, **kwargs):
            return redirected.SerializeToString(*args, **kwargs)
    with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
        getattr(paper_sdk, method)(Proxy())
    assert paper_sdk.conn.messages == []
    assert audit.snapshot() == dict(place=int(method == "placeOrderProtoBuf"),
        modify=0, cancel=int(method != "placeOrderProtoBuf"))


def test_order_subclass_cannot_redirect_older_wire_transport(paper_sdk):
    from ibapi.order import Order
    class ProxyOrder(Order):
        pass
    contract, original = _arguments()
    proxy = ProxyOrder()
    proxy.__dict__.update(original.__dict__)
    paper_sdk.serverVersion_ = 180
    with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
        paper_sdk.placeOrder(71, contract, proxy)
    assert paper_sdk.conn.messages == []
    assert audit.snapshot() == dict(place=1, modify=0, cancel=0)


def test_real_native_cancellation_bridges_preserve_dto_fields_and_one_count(paper_sdk):
    from ibapi.message import OUT
    from ibapi.order_cancel import OrderCancel
    from ibapi.protobuf.CancelOrderRequest_pb2 import CancelOrderRequest
    from ibapi.protobuf.GlobalCancelRequest_pb2 import GlobalCancelRequest
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    client = IbkrClient("127.0.0.1", 7497, 9012, 5, "LIVE", False)
    client.conn, client.connState, client.serverVersion_ = paper_sdk.conn, IbkrClient.CONNECTED, 222
    client.nextValidId(71)
    client.managedAccounts("DU10001")
    client.cancelOrder(71)
    client.reqGlobalCancel()
    supplied = OrderCancel()
    supplied.manualOrderCancelTime, supplied.extOperator, supplied.manualOrderIndicator = "20261124-12:00:00", "offline", 1
    client.cancelOrder(72, supplied)
    client.reqGlobalCancel(supplied)
    client.cancelOrder(73, "20261124-12:01:00")
    assert audit.snapshot() == dict(place=0, modify=0, cancel=5)
    assert len(client.conn.messages) == 5
    first = _decode(client.conn.messages[0], CancelOrderRequest, OUT.CANCEL_ORDER)
    assert first.orderId == 71 and first.orderCancel.manualOrderCancelTime == ""
    _decode(client.conn.messages[1], GlobalCancelRequest, OUT.REQ_GLOBAL_CANCEL)
    preserved = _decode(client.conn.messages[2], CancelOrderRequest, OUT.CANCEL_ORDER)
    global_preserved = _decode(client.conn.messages[3], GlobalCancelRequest, OUT.REQ_GLOBAL_CANCEL)
    for message in (preserved, global_preserved):
        assert message.orderCancel.manualOrderCancelTime == supplied.manualOrderCancelTime
        assert message.orderCancel.extOperator == "offline"
        assert message.orderCancel.manualOrderIndicator == 1
    manual = _decode(client.conn.messages[4], CancelOrderRequest, OUT.CANCEL_ORDER)
    assert manual.orderId == 73 and manual.orderCancel.manualOrderCancelTime == "20261124-12:01:00"


@pytest.mark.parametrize("missing", ["_position_transport_available", "_stop_event", "readonly_enabled"])
def test_raw_sdk_without_owned_transport_evidence_cannot_mutate(paper_sdk, missing):
    delattr(paper_sdk, missing)
    with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
        paper_sdk.placeOrder(71, *_arguments())
    assert paper_sdk.conn.messages == []
    assert audit.snapshot() == dict(place=1, modify=0, cancel=0)


def test_native_stopping_and_reconnect_require_current_account_scope(paper_sdk):
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    client = IbkrClient("127.0.0.1", 7497, 9012, 5, "LIVE", False)
    client.conn, client.connState, client.serverVersion_ = paper_sdk.conn, IbkrClient.CONNECTED, 222
    client.nextValidId(71)
    client.managedAccounts("DU10001")
    profile.require_sdk_execution_profile(client)
    # Disconnect marks stopping before its slower request invalidation begins.
    client._stop_event.set()
    with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
        client.cancelOrder(71)
    assert client.conn.messages == []
    client.disconnect()
    assert client._managed_accounts == [] and client._position_transport_available is False
    client.conn = type(paper_sdk.conn)()
    client.host, client.port, client.connState, client.serverVersion_ = "127.0.0.1", 7497, IbkrClient.CONNECTED, 222
    client._stop_event.clear()
    client._position_upstream_lost = False
    client.nextValidId(72)
    assert client._position_transport_available is True
    # A new connected handshake cannot inherit the previous DU account receipt.
    with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
        client.cancelOrder(72)
    assert client.conn.messages == []
    client.managedAccounts("DU10001")
    client.cancelOrder(72)
    assert len(client.conn.messages) == 1
    assert audit.snapshot() == dict(place=0, modify=0, cancel=3)


@pytest.mark.parametrize("field", ["account", "faGroup"])
def test_account_scope_rejects_custom_string_equality_on_older_wire(paper_sdk, field):
    class MisleadingString(str):
        def __eq__(self, other):
            return True
    contract, order = _arguments()
    setattr(order, field, MisleadingString("U10001"))
    paper_sdk.serverVersion_ = 180
    with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
        paper_sdk.placeOrder(71, contract, order)
    assert paper_sdk.conn.messages == []
    assert audit.snapshot() == dict(place=1, modify=0, cancel=0)


@pytest.mark.parametrize("nested", [False, True])
def test_direct_protobuf_rejects_fields_outside_pinned_reviewed_schema(paper_sdk, nested):
    from ibapi.client_utils import createPlaceOrderRequestProto
    request = createPlaceOrderRequestProto(71, *_arguments())
    # A valid protobuf field9999, length-delimited, absent from the pinned schema.
    (request.order if nested else request).MergeFromString(b"\xfa\xf0\x04\x01x")
    with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
        paper_sdk.placeOrderProtoBuf(request)
    assert paper_sdk.conn.messages == []
    assert audit.snapshot() == dict(place=1, modify=0, cancel=0)
