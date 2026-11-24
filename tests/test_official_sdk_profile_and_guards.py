"""An attested official SDK still requires the explicit exclusive PAPER scope."""
from importlib import metadata
from types import SimpleNamespace

import pytest

from src.ibkr import sdk_profile as profile


def test_unknown_sdk_and_version_only_claim_cannot_enable_profile(monkeypatch, tmp_path):
    monkeypatch.setattr(profile, "metadata", SimpleNamespace(version=lambda name: "UNKNOWN"))
    with pytest.raises(RuntimeError, match="IBKR_SDK_PROFILE_UNVERIFIED"):
        profile.require_supported_sdk()
    monkeypatch.setattr(profile, "metadata", SimpleNamespace(version=lambda name:
        profile.OFFICIAL_SDK_VERSION if name == "ibapi" else profile.OFFICIAL_PROTOBUF_VERSION))
    fake = tmp_path / "unverified"; fake.mkdir(); (fake / "__init__.py").write_text("# not the SDK")
    monkeypatch.setattr(profile.importlib.util, "find_spec", lambda name:
        SimpleNamespace(origin=str(fake / "__init__.py")))
    with pytest.raises(RuntimeError, match="IBKR_SDK_PROFILE_UNVERIFIED"):
        profile.require_supported_sdk()


def test_sdk_source_facts_detect_changed_extra_and_linked_python_sources(tmp_path):
    root = tmp_path / "source"; root.mkdir()
    source = root / "a.py"; source.write_text("value = 1\n")
    original = profile.sdk_source_facts(root)
    source.write_text("value = 2\n")
    assert profile.sdk_source_facts(root) != original
    source.write_text("value = 1\n"); (root / "extra.py").write_text("# unexpected")
    assert profile.sdk_source_facts(root) != original
    (root / "extra.py").unlink()
    try:
        (root / "linked.py").symlink_to(source)
    except OSError:
        return  # Windows CI may lack symlink privilege; other source checks ran.
    with pytest.raises(RuntimeError, match="SOURCE_UNVERIFIED"):
        profile.sdk_source_facts(root)


@pytest.mark.skipif(metadata.version("ibapi") != profile.OFFICIAL_SDK_VERSION,
                    reason="requires the isolated pinned official SDK profile")
def test_official_profile_all_public_mutation_entries_refuse_even_with_execution_flags(monkeypatch):
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    from ibapi.order_cancel import OrderCancel
    from ibapi.protobuf.PlaceOrderRequest_pb2 import PlaceOrderRequest
    from ibapi.protobuf.CancelOrderRequest_pb2 import CancelOrderRequest
    from ibapi.protobuf.GlobalCancelRequest_pb2 import GlobalCancelRequest
    from src.ibkr import mutation_audit, read_only_guard
    assert profile.require_supported_sdk() == profile.OFFICIAL_SDK_VERSION
    mutation_audit.install_sdk(EClient, EWrapper)
    client = EClient(EWrapper())
    client.readonly_enabled = False
    monkeypatch.setattr(read_only_guard, "assert_read_only_allows", lambda *args: None)
    client.conn = SimpleNamespace(sendMsg=lambda *args: pytest.fail("No SDK mutation may reach the socket"))
    calls = [
        (lambda: client.placeOrder(101, Contract(), Order()), "place"),
        (lambda: client.placeOrder(101, Contract(), Order()), "modify"),
        (lambda: client.cancelOrder(101, OrderCancel()), "cancel"),
        (lambda: client.reqGlobalCancel(OrderCancel()), "cancel"),
        (lambda: client.placeOrderProtoBuf(PlaceOrderRequest(orderId=102)), "place"),
        (lambda: client.placeOrderProtoBuf(PlaceOrderRequest(orderId=102)), "modify"),
        (lambda: client.cancelOrderProtoBuf(CancelOrderRequest(orderId=102)), "cancel"),
        (lambda: client.reqGlobalCancelProtoBuf(GlobalCancelRequest()), "cancel"),
    ]
    for call, category in calls:
        before = mutation_audit.snapshot()
        with pytest.raises(RuntimeError, match="OFFICIAL_SDK_PAPER_SCOPE_UNVERIFIED"):
            call()
        expected = dict(before); expected[category] += 1
        assert mutation_audit.snapshot() == expected


@pytest.mark.parametrize("mode,host,port", [
    ("LIVE", "127.0.0.1", 7497), ("SIM", "127.0.0.1", 7497),
    ("READ_ONLY", "127.0.0.1", 7497), ("PAPER", "localhost", 7497),
    ("PAPER", "127.0.0.1", 7496), ("PAPER", "127.0.0.1", "7497"),
    ("PAPER", "192.0.2.1", 7497),
])
def test_modern_paper_construction_rejects_other_modes_and_endpoints(monkeypatch, mode, host, port):
    from src.config import runtime_config
    monkeypatch.setattr(profile, "require_supported_sdk", lambda: profile.OFFICIAL_SDK_VERSION)
    monkeypatch.setattr(runtime_config, "_resolve_runtime_authority", lambda: (mode, True))
    with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
        profile.require_sdk_paper_connection(host, port)


def test_modern_paper_construction_does_not_require_or_grant_order_execution(monkeypatch):
    from src.config import runtime_config
    monkeypatch.setattr(profile, "require_supported_sdk", lambda: profile.OFFICIAL_SDK_VERSION)
    monkeypatch.setattr(runtime_config, "_resolve_runtime_authority", lambda: ("PAPER", False))
    profile.require_sdk_paper_connection("127.0.0.1", 7497)
    with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
        profile.require_sdk_execution_profile()


@pytest.mark.parametrize("accounts,complete,connected,transport,order_account", [
    ([], True, True, True, ""), (["U10001"], True, True, True, ""),
    (["DU10001", "DU10002"], True, True, True, ""),
    (["DU10001", "DU10001"], True, True, True, ""),
    (["DU10001"], False, True, True, ""), (["DU10001"], True, False, True, ""),
    (["DU10001"], True, True, False, ""), (["DU10001"], True, True, True, "U10001"),
    (["DU10001"], True, True, True, "DU10002"), ([" DU10001"], True, True, True, ""),
])
def test_modern_paper_mutation_requires_current_exclusive_owned_account_scope(
        monkeypatch, accounts, complete, connected, transport, order_account):
    import threading
    from src.config import runtime_config
    monkeypatch.setattr(profile, "require_supported_sdk", lambda: profile.OFFICIAL_SDK_VERSION)
    monkeypatch.setattr(runtime_config, "_resolve_runtime_authority", lambda: ("PAPER", True))
    event = threading.Event()
    if complete:
        event.set()
    client = SimpleNamespace(host="127.0.0.1", port=7497, _managed_accounts=accounts,
        _managed_accounts_event=event, isConnected=lambda: connected,
        _position_transport_available=transport, _stop_event=threading.Event(), readonly_enabled=False)
    with pytest.raises(RuntimeError, match="PAPER_SCOPE_UNVERIFIED"):
        profile.require_sdk_execution_profile(client, order_account=order_account)


def test_legacy_profile_retains_existing_execution_contract(monkeypatch):
    monkeypatch.setattr(profile, "require_supported_sdk", lambda: profile.LEGACY_SDK_VERSION)
    profile.require_sdk_paper_connection("legacy-existing-host", 4002)
    profile.require_sdk_execution_profile()
