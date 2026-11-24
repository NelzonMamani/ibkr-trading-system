"""Pinned SDK profiles and the narrow official-SDK PAPER transport boundary."""
from __future__ import annotations

import hashlib
import importlib.util
from importlib import metadata
from pathlib import Path
import re
import threading

LEGACY_SDK_VERSION = "9.81.1.post1"
OFFICIAL_SDK_VERSION = "10.50.2"
OFFICIAL_PROTOBUF_VERSION = "5.29.5"
SUPPORTED_DIAGNOSTIC_SDKS = frozenset((LEGACY_SDK_VERSION, OFFICIAL_SDK_VERSION))
OFFICIAL_SDK_ARCHIVE_URL = "https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip"
OFFICIAL_SDK_ARCHIVE_SHA256 = "673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3"
OFFICIAL_SDK_ARCHIVE_BYTES = 11412955
OFFICIAL_SDK_SOURCE_COUNT = 235
OFFICIAL_SDK_SOURCE_SHA256 = "72dccfacba1295b3e4c45d5c97cf160cdb2e86d95b92de2ff408610f570b208b"


def sdk_source_facts(package_root):
    """Hash installed Python sources exactly as the pinned official ZIP contains them."""
    root = Path(package_root)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
    files = sorted(root.rglob("*.py"), key=lambda item: item.relative_to(root).as_posix())
    if len(files) > 500:
        raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
    digest, size = hashlib.sha256(), 0
    for item in files:
        if item.is_symlink() or item.stat().st_size > 2 * 1024 * 1024:
            raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
        value = item.read_bytes()
        size += len(value)
        if size > 16 * 1024 * 1024:
            raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
        digest.update((item.relative_to(root).as_posix() + "\0"
                       + hashlib.sha256(value).hexdigest() + "\n").encode("utf-8"))
    return {"source_count": len(files), "source_sha256": digest.hexdigest()}


def require_supported_sdk():
    """Return a verified profile version; perform no client import or acquisition."""
    try:
        version = metadata.version("ibapi")
        if version == LEGACY_SDK_VERSION:
            return version  # Existing legacy observer/commission checks stay authoritative.
        if version != OFFICIAL_SDK_VERSION or metadata.version("protobuf") != OFFICIAL_PROTOBUF_VERSION:
            raise RuntimeError("IBKR_SDK_PROFILE_UNSUPPORTED")
        spec = importlib.util.find_spec("ibapi")
        if spec is None or not spec.origin:
            raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
        facts = sdk_source_facts(Path(spec.origin).parent)
        if facts != {"source_count": OFFICIAL_SDK_SOURCE_COUNT,
                      "source_sha256": OFFICIAL_SDK_SOURCE_SHA256}:
            raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
        return version
    except Exception:
        # Package/file errors may contain local paths. Never export their text.
        raise RuntimeError("IBKR_SDK_PROFILE_UNVERIFIED") from None


def _require_paper_endpoint(host, port):
    from src.config.runtime_config import _resolve_runtime_authority

    mode, _ = _resolve_runtime_authority()
    if mode != "PAPER" or host != "127.0.0.1" or type(host) is not str or type(port) is not int or port != 7497:
        raise RuntimeError("IBKR_OFFICIAL_SDK_PAPER_SCOPE_UNVERIFIED")


def require_sdk_paper_connection(host, port):
    """Allow modern mutable construction only for the explicit local PAPER endpoint.

    Account identity arrives after connection and is checked again on every
    mutation. This check grants neither connection nor strategy-entry authority.
    """
    if require_supported_sdk() != LEGACY_SDK_VERSION:
        _require_paper_endpoint(host, port)


def require_sdk_execution_profile(client=None, *, order_account=None, order=None,
        method=None, request=None, contract=None, cancel=None):
    """Retain legacy behavior; require current exclusive PAPER scope for modern SDK.

    Runtime execution, read-only, kill, ownership and strategy-entry guards remain
    independent. An empty order account uses only the verified sole PAPER account.
    """
    if require_supported_sdk() == LEGACY_SDK_VERSION:
        return
    _require_paper_endpoint(getattr(client, "host", None), getattr(client, "port", None))
    # The SDK sends SerializeToString() output. A proxy that exposes one order
    # for inspection but serializes another cannot supply account evidence.
    if method is not None or order is not None:
        from ibapi.contract import Contract
        from ibapi.order import Order
        from ibapi.order_cancel import OrderCancel
        from ibapi.protobuf.Order_pb2 import Order as ProtoOrder
        from ibapi.protobuf.PlaceOrderRequest_pb2 import PlaceOrderRequest
        from ibapi.protobuf.CancelOrderRequest_pb2 import CancelOrderRequest
        from ibapi.protobuf.GlobalCancelRequest_pb2 import GlobalCancelRequest
        request_type = {"placeOrderProtoBuf": PlaceOrderRequest,
            "cancelOrderProtoBuf": CancelOrderRequest,
            "reqGlobalCancelProtoBuf": GlobalCancelRequest}.get(method)
        if ((request_type is not None and type(request) is not request_type)
                or (order is not None and type(order) not in (Order, ProtoOrder))
                or (method in ("placeOrder", "submit_order") and type(contract) is not Contract)
                or (method in ("cancelOrder", "reqGlobalCancel") and type(cancel) is not OrderCancel)):
            raise RuntimeError("IBKR_OFFICIAL_SDK_PAPER_SCOPE_UNVERIFIED")
        if request_type is not None:
            reviewed = request_type()
            reviewed.CopyFrom(request)
            reviewed.DiscardUnknownFields()  # Includes unknown nested order/contract fields.
            if reviewed.SerializeToString(deterministic=True) != request.SerializeToString(deterministic=True):
                raise RuntimeError("IBKR_OFFICIAL_SDK_PAPER_SCOPE_UNVERIFIED")
    try:
        accounts = client._managed_accounts
        completed = client._managed_accounts_event
        stopping = client._stop_event
        allocations = [getattr(order, field, "") for field in (
            "faGroup", "faProfile", "faMethod", "faPercentage", "modelCode",
            "clearingAccount", "deltaNeutralClearingAccount", "customerAccount")]
        valid = (
            isinstance(accounts, (list, tuple)) and len(accounts) == 1
            and type(accounts[0]) is str and re.fullmatch(r"DU[A-Z0-9]{1,32}", accounts[0]) is not None
            and isinstance(completed, threading.Event) and completed.is_set()
            and isinstance(stopping, threading.Event) and not stopping.is_set()
            and getattr(client, "readonly_enabled", None) is False
            and client.isConnected() is True
            and getattr(client, "_position_transport_available", False) is True
            and (order_account is None
                 or (type(order_account) is str and order_account in ("", accounts[0])))
            and all(value is None or (type(value) is str and value == "") for value in allocations)
        )
    except Exception:
        valid = False
    if not valid:
        raise RuntimeError("IBKR_OFFICIAL_SDK_PAPER_SCOPE_UNVERIFIED")
