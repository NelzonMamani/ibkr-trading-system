"""Thread-safe process-lifetime SDK mutation attempt evidence, before guards."""
from __future__ import annotations
from functools import wraps
import inspect
import sys
import threading
import weakref
from src.ibkr.evidence_safety import register_account, register_payload

_lock = threading.RLock()
_counts = {"place": 0, "modify": 0, "cancel": 0}
_seen = weakref.WeakKeyDictionary()
_local = threading.local()

_SDK_PROTO_DELEGATIONS = {
    "placeOrder": ("placeOrderProtoBuf", "createPlaceOrderRequestProto"),
    "cancelOrder": ("cancelOrderProtoBuf", "createCancelOrderRequestProto"),
    "reqGlobalCancel": ("reqGlobalCancelProtoBuf", "createGlobalCancelRequestProto"),
}


def _sdk_projection(cls, method, original):
    """Capture only the owned SDK's immediate legacy -> protobuf projection."""
    module = sys.modules.get("ibapi.client")
    utilities = sys.modules.get("ibapi.client_utils")
    mapping = _SDK_PROTO_DELEGATIONS.get(method)
    if (mapping is None or module is None or utilities is None
            or getattr(module, "EClient", None) is not cls
            or getattr(original, "__globals__", None) is not vars(module)
            or original.__qualname__ != "EClient." + method):
        return None
    child, name = mapping
    creator = getattr(utilities, name, None)
    if creator is None or original.__globals__.get(name) is not creator:
        return None
    return child, name, creator


def _prepare_sdk_projection(projection, original, values):
    if projection is None:
        return None
    child, name, creator = projection
    if original.__globals__.get(name) is not creator:
        return None
    try:
        expected = creator(*values)
        order_id = values[0] if child != "reqGlobalCancelProtoBuf" else None
        if order_id is not None and (type(order_id) is not int
                or not expected.HasField("orderId") or expected.orderId != order_id):
            return None
        return dict(method=child, creator=creator, creator_name=name,
            source_globals=original.__globals__, message_type=type(expected),
            payload=expected.SerializeToString(deterministic=True), order_id=order_id, used=False)
    except Exception:
        # An unprojectable request receives no accounting exemption. The SDK's
        # normal validation still owns malformed argument behavior.
        return None


def _matches_sdk_projection(parent, cls, method, client, values, caller):
    proof = parent.get("proto_projection") if parent is not None else None
    if (proof is None or proof["used"] or proof["method"] != method
            or parent["class"] is not cls or parent["client"] != id(client)
            or caller.f_code is not parent["source_code"] or caller.f_back is None
            or id(caller.f_back) != parent["audit_frame"] or len(values) != 1
            or proof["source_globals"].get(proof["creator_name"]) is not proof["creator"]):
        return False
    try:
        message = values[0]
        matches = (type(message) is proof["message_type"]
            and message.SerializeToString(deterministic=True) == proof["payload"])
        if proof["order_id"] is not None:
            matches = matches and message.HasField("orderId") and message.orderId == proof["order_id"]
        if matches:
            proof["used"] = True
        return matches
    except Exception:
        return False


def _mutation_order(method, values):
    if method == "placeOrder" and len(values) >= 3:
        return values[2]
    if method == "submit_order" and len(values) >= 2:
        return values[1]
    if method == "placeOrderProtoBuf" and values:
        return getattr(values[0], "order", None)
    return None


def snapshot():
    with _lock:
        return dict(_counts)


def _category(client, method, args):
    if method in {"cancelOrder", "reqGlobalCancel", "cancelOrderProtoBuf", "reqGlobalCancelProtoBuf"}:
        return "cancel"
    if method == "submit_order":
        return "place"
    order_id = args[0] if args else None
    if method == "placeOrderProtoBuf":
        order_id = getattr(order_id, "orderId", None)
    with _lock:
        seen = _seen.setdefault(client, set())
        known = order_id in seen or order_id in getattr(client, "_open_orders_snapshot", {})
        wrapper = getattr(client, "wrapper", None)
        known = known or any(getattr(getattr(t, "order", None), "orderId", None) == order_id for t in getattr(wrapper, "trades", {}).values())
        seen.add(order_id)
    return "modify" if known else "place"


def delegate_sdk_place_order(client, audited_sdk, delegate, order_id, contract, order):
    """Account for one exact Native -> SDK call, including one selected shim.

    This conveys no permission and never bypasses an audited/read-only boundary.
    The receipt exists only while this function invokes the selected delegate.
    """
    frames = getattr(_local, "delegations", ())
    parent = frames[-1] if frames else None
    caller = sys._getframe(1)
    delegate_function = getattr(delegate, "__func__", delegate)
    if (parent is None or parent["client"] != id(client) or parent["method"] != "placeOrder"
            or parent["delegated"] or caller.f_code is not parent["source_code"]
            or not getattr(audited_sdk, "_mutation_audited", False)):
        return delegate(order_id, contract, order)
    receipt = dict(target=audited_sdk, client=client, order_id=order_id,
        contract=contract, order=order, helper_frame=id(sys._getframe()),
        delegate_code=getattr(delegate_function, "__code__", None), used=False)
    previous = parent.get("sdk_receipt")
    parent["sdk_receipt"] = receipt
    try:
        return delegate(order_id, contract, order)
    finally:
        # A failed/unused delegation cannot escape this invocation or rearm.
        receipt["used"] = True
        if parent.get("sdk_receipt") is receipt:
            if previous is None:
                parent.pop("sdk_receipt", None)
            else:
                parent["sdk_receipt"] = previous


def instrument_mutation(cls, method):
    original = getattr(cls, method, None)
    if original is None or getattr(original, "_mutation_audited", False):
        return
    projection = _sdk_projection(cls, method, original)
    @wraps(original)
    def audited(self, *args, **kwargs):
        active = getattr(_local, "active", ())
        frames = getattr(_local, "delegations", ())
        parent = frames[-1] if frames else None
        outer = True
        receipt = parent.get("sdk_receipt") if parent is not None else None
        caller = sys._getframe(1)
        bound = inspect.signature(original).bind(self, *args, **kwargs)
        values = list(bound.arguments.values())[1:]
        if (method == "placeOrder" and receipt is not None and not receipt["used"]
                and receipt["target"] is audited and receipt["client"] is self
                and not parent["delegated"] and parent["class"] is not cls
                and issubclass(parent["class"], cls)
                and (id(caller) == receipt["helper_frame"]
                     or (caller.f_code is receipt["delegate_code"] and caller.f_back is not None
                         and id(caller.f_back) == receipt["helper_frame"]))):
            if (len(values) == 3 and type(values[0]) is int
                    and type(receipt["order_id"]) is int and values[0] == receipt["order_id"]
                    and values[1] is receipt["contract"] and values[2] is receipt["order"]):
                receipt["used"] = True
                parent["delegated"] = True
                outer = False
        if (outer and method == "placeOrder" and parent is not None
                and parent["client"] == id(self) and not parent["delegated"]
                and sys._getframe(1).f_code is parent["source_code"]
                and (parent["method"] == "submit_order"
                     or (parent["method"] == "placeOrder" and parent["class"] is not cls
                         and issubclass(parent["class"], cls)))):
            # Suppress only one immediate owner -> SDK delegation. A distinct
            # reentrant Native invocation or a second SDK call is a new attempt.
            parent["delegated"] = True
            outer = False
        if outer and _matches_sdk_projection(parent, cls, method, self, values, caller):
            outer = False
        if outer:
            category = _category(self, method, values)
            with _lock:
                _counts[category] += 1
        else:
            category = parent["category"]
        _local.active = (*active, (id(self), method))
        frame = {"client": id(self), "method": method, "class": cls,
            "source_code": getattr(original, "__code__", None), "delegated": False,
            "audit_frame": id(sys._getframe()), "category": category}
        _local.delegations = (*frames, frame)
        try:
            from src.ibkr.read_only_guard import assert_read_only_allows
            assert_read_only_allows({"place": "PLACE_ORDER", "modify": "MODIFY_ORDER", "cancel": "CANCEL_ORDER"}[category])
            from src.ibkr.sdk_profile import require_sdk_execution_profile
            order = _mutation_order(method, values)
            require_sdk_execution_profile(self, order_account=getattr(order, "account", None), order=order,
                method=method, request=values[0] if values else None,
                contract=(values[1] if method == "placeOrder" and len(values) > 1 else
                    values[0] if method == "submit_order" and values else None),
                cancel=(values[1] if method == "cancelOrder" and len(values) > 1 else
                    values[0] if method == "reqGlobalCancel" and values else None))
            if getattr(self, "readonly_enabled", False):
                raise RuntimeError("IBKR instance read-only: blocking mutation")
            frame["proto_projection"] = _prepare_sdk_projection(projection, original, values)
            return original(self, *args, **kwargs)
        finally:
            _local.active = active
            _local.delegations = frames
    audited._mutation_audited = True
    setattr(cls, method, audited)


def instrument_accounts(cls):
    for name in ("managedAccounts", "accountSummary", "updateAccountValue", "position", "positionMulti", "openOrder", "completedOrder", "execDetails"):
        original = getattr(cls, name, None)
        if original is None or getattr(original, "_accounts_registered", False):
            continue
        def wrap(fn):
            @wraps(fn)
            def callback(self, *args, **kwargs):
                bound = inspect.signature(fn).bind(self, *args, **kwargs)
                for key, value in bound.arguments.items():
                    if key == "self":
                        continue
                    if key.lower() in {"account", "accountlist", "accountslist", "acctcode"}:
                        register_account(value)
                    else:
                        register_payload(value)
                return fn(self, *args, **kwargs)
            callback._accounts_registered = True
            return callback
        setattr(cls, name, wrap(original))


def install_sdk(client_class, wrapper_class):
    for method in ("placeOrder", "cancelOrder", "reqGlobalCancel",
                   "placeOrderProtoBuf", "cancelOrderProtoBuf", "reqGlobalCancelProtoBuf"):
        instrument_mutation(client_class, method)
    instrument_accounts(wrapper_class)


def require_zero_attempts(counts):
    """Reject absent/malformed evidence as well as any attempted mutation."""
    if not isinstance(counts, dict) or set(counts) != {"place", "modify", "cancel"}:
        raise RuntimeError("Independent mutation attempt evidence missing")
    if any(type(value) is not int or value != 0 for value in counts.values()):
        raise RuntimeError("READ_ONLY mutation attempt certification failed")
