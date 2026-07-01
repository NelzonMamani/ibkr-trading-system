from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _ROOT / "scripts" / "certification" / "pr1034_readonly_broker_connected_artifact_collector.py"
_REPORT_PATH = (
    _ROOT
    / "docs"
    / "certification"
    / "PR1036_PR1034_COLLECTOR_IB_INSYNC_IMPORT_ORDER_BOOTSTRAP_FIX.md"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("pr1034_collector_pr1036", _SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pr1034 = _load_script_module()


def _config():
    return pr1034.BrokerConnectionConfig(
        host="127.0.0.1",
        port=7497,
        client_id=1036,
        timeout_seconds=3.0,
        market_data_type="TEST_READ_ONLY",
    )


def test_pr1036_asyncio_loop_exists_before_any_ib_insync_symbol_is_loaded(monkeypatch) -> None:
    calls: list[object] = []
    current_loop: dict[str, object | None] = {"value": None}

    def fake_get_event_loop():
        calls.append("get_event_loop")
        if current_loop["value"] is None:
            raise RuntimeError("no current event loop")
        return current_loop["value"]

    def fake_new_event_loop():
        loop = object()
        calls.append("new_event_loop")
        return loop

    def fake_set_event_loop(loop) -> None:
        current_loop["value"] = loop
        calls.append("set_event_loop")

    monkeypatch.setattr(pr1034.asyncio, "get_event_loop", fake_get_event_loop)
    monkeypatch.setattr(pr1034.asyncio, "new_event_loop", fake_new_event_loop)
    monkeypatch.setattr(pr1034.asyncio, "set_event_loop", fake_set_event_loop)

    class FakeUtil:
        def patchAsyncio(self) -> None:
            calls.append("patchAsyncio")

    class FakeIB:
        def __init__(self) -> None:
            calls.append("IB")
            self.connected = False

        def connect(self, host, port, *, clientId, timeout, readonly) -> None:
            calls.append(("connect", host, port, clientId, timeout, readonly))
            self.connected = True

        def isConnected(self) -> bool:
            return self.connected

    class OrderedFakeIBInsync(types.ModuleType):
        def __getattribute__(self, name):
            if name == "util":
                calls.append("get_util")
                if "set_event_loop" not in calls:
                    raise AssertionError("util was imported before asyncio event loop setup")
                return fake_util
            if name == "IB":
                calls.append("get_IB")
                if "patchAsyncio" not in calls:
                    raise AssertionError("IB was imported before util bootstrap")
                return FakeIB
            return super().__getattribute__(name)

    fake_util = FakeUtil()
    fake_ib_insync = OrderedFakeIBInsync("ib_insync")
    monkeypatch.setitem(sys.modules, "ib_insync", fake_ib_insync)

    provider = pr1034.IBInsyncReadOnlyProvider(_config())
    provider.connect_readonly()

    assert calls.index("set_event_loop") < calls.index("get_util")
    assert calls.index("get_util") < calls.index("patchAsyncio")
    assert calls.index("patchAsyncio") < calls.index("get_IB")
    assert calls.index("get_IB") < calls.index("IB")
    assert calls[-1] == ("connect", "127.0.0.1", 7497, 1036, 3.0, True)


def test_pr1036_bootstrap_loader_aborts_if_ib_symbol_is_unavailable_after_util(monkeypatch) -> None:
    class FakeUtil:
        def patchAsyncio(self) -> None:
            return None

    class MissingIBFakeModule(types.ModuleType):
        def __getattribute__(self, name):
            if name == "util":
                return FakeUtil()
            if name == "IB":
                raise ImportError("missing IB")
            return super().__getattribute__(name)

    monkeypatch.setitem(sys.modules, "ib_insync", MissingIBFakeModule("ib_insync"))

    with pytest.raises(pr1034.CollectorValidationError, match="ib_insync IB is required"):
        pr1034.load_ib_insync_ib_after_bootstrap()


def test_pr1036_report_documents_import_order_fix_and_keeps_paper_blocked() -> None:
    report = _REPORT_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "PAPER_READY: NO",
        "PR1034_IB_INSYNC_IMPORT_ORDER_BOOTSTRAP_FIXED: YES",
        "ASYNCIO_EVENT_LOOP_BEFORE_IB_INSYNC_IMPORT: YES",
        "UTIL_BOOTSTRAP_BEFORE_IB_SYMBOL_LOAD: YES",
        "CI_CONNECTS_TO_IBKR: NO",
        "ORDER_MUTATION_ALLOWED: NO",
        "PAPER_READINESS_GATE: FAIL",
        "The collector creates or confirms an asyncio event loop before any `ib_insync` import.",
        "Broker-connected runtime artifact captured by this PR: NO",
    )
    forbidden_fragments = (
        "PAPER_READY: YES",
        "CI_CONNECTS_TO_IBKR: YES",
        "ORDER_MUTATION_ALLOWED: YES",
        "PAPER_READINESS_GATE: PASS",
    )

    for fragment in required_fragments:
        assert fragment in report
    for fragment in forbidden_fragments:
        assert fragment not in report
