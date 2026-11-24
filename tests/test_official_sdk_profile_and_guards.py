"""The official data profile cannot acquire execution authority from runtime flags."""
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
        with pytest.raises(RuntimeError, match="OFFICIAL_SDK_EXECUTION_NOT_CERTIFIED"):
            call()
        expected = dict(before); expected[category] += 1
        assert mutation_audit.snapshot() == expected
