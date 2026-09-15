"""Thread-safe process-lifetime SDK mutation attempt evidence, before guards."""
from __future__ import annotations
from functools import wraps
import inspect
import threading
import weakref
from src.ibkr.evidence_safety import register_account, register_payload

_lock = threading.RLock()
_counts = {"place": 0, "modify": 0, "cancel": 0}
_seen = weakref.WeakKeyDictionary()
_local = threading.local()


def snapshot():
    with _lock:
        return dict(_counts)


def _category(client, method, args):
    if method in {"cancelOrder", "reqGlobalCancel"}:
        return "cancel"
    if method == "submit_order":
        return "place"
    order_id = args[0] if args else None
    with _lock:
        seen = _seen.setdefault(client, set())
        known = order_id in seen or order_id in getattr(client, "_open_orders_snapshot", {})
        wrapper = getattr(client, "wrapper", None)
        known = known or any(getattr(getattr(t, "order", None), "orderId", None) == order_id for t in getattr(wrapper, "trades", {}).values())
        seen.add(order_id)
    return "modify" if known else "place"


def instrument_mutation(cls, method):
    original = getattr(cls, method, None)
    if original is None or getattr(original, "_mutation_audited", False):
        return
    @wraps(original)
    def audited(self, *args, **kwargs):
        active = getattr(_local, "active", ())
        outer = not (method == "placeOrder" and (id(self), "submit_order") in active)
        if outer:
            bound = inspect.signature(original).bind(self, *args, **kwargs)
            values = list(bound.arguments.values())[1:]
            category = _category(self, method, values)
            with _lock:
                _counts[category] += 1
        _local.active = (*active, (id(self), method))
        try:
            from src.ibkr.read_only_guard import assert_read_only_allows
            assert_read_only_allows({"place": "PLACE_ORDER", "modify": "MODIFY_ORDER", "cancel": "CANCEL_ORDER"}[category] if outer else "PLACE_ORDER")
            if getattr(self, "readonly_enabled", False):
                raise RuntimeError("IBKR instance read-only: blocking mutation")
            return original(self, *args, **kwargs)
        finally:
            _local.active = active
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
    for method in ("placeOrder", "cancelOrder", "reqGlobalCancel"):
        instrument_mutation(client_class, method)
    instrument_accounts(wrapper_class)


def require_zero_attempts(counts):
    """Reject absent/malformed evidence as well as any attempted mutation."""
    if not isinstance(counts, dict) or set(counts) != {"place", "modify", "cancel"}:
        raise RuntimeError("Independent mutation attempt evidence missing")
    if any(type(value) is not int or value != 0 for value in counts.values()):
        raise RuntimeError("READ_ONLY mutation attempt certification failed")
