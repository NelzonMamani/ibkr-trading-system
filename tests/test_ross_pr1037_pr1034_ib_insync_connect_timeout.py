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
    / "PR1037_PR1034_COLLECTOR_PYTHON314_IB_INSYNC_CONNECT_TIMEOUT_FIX.md"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("pr1034_collector_pr1037", _SCRIPT_PATH)
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
        client_id=1037,
        timeout_seconds=1.25,
        market_data_type="TEST_READ_ONLY",
    )


def _install_fake_ib_insync(monkeypatch, fake_ib_class) -> None:
    class FakeIBInsync(types.ModuleType):
        def __getattribute__(self, name):
            if name == "util":
                raise AssertionError("ib_insync.util should not be imported by default")
            return super().__getattribute__(name)

    fake_ib_insync = FakeIBInsync("ib_insync")
    fake_ib_insync.IB = fake_ib_class
    monkeypatch.setitem(sys.modules, "ib_insync", fake_ib_insync)


def test_pr1037_ib_connect_timeout_fails_closed_and_disconnects(monkeypatch) -> None:
    instances = []

    class TimeoutIB:
        def __init__(self) -> None:
            self.connect_kwargs = None
            self.disconnect_calls = 0
            instances.append(self)

        def connect(self, host, port, *, clientId, timeout, readonly) -> None:
            self.connect_kwargs = {
                "host": host,
                "port": port,
                "clientId": clientId,
                "timeout": timeout,
                "readonly": readonly,
            }
            raise TimeoutError("simulated Python 3.14 ib_insync timeout path")

        def disconnect(self) -> None:
            self.disconnect_calls += 1

    _install_fake_ib_insync(monkeypatch, TimeoutIB)

    provider = pr1034.IBInsyncReadOnlyProvider(_config())

    with pytest.raises(pr1034.CollectorValidationError, match="connection timed out"):
        provider.connect_readonly()

    assert provider._ib is None
    assert instances[0].disconnect_calls == 1
    assert instances[0].connect_kwargs == {
        "host": "127.0.0.1",
        "port": 7497,
        "clientId": 1037,
        "timeout": 1.25,
        "readonly": True,
    }


def test_pr1037_ib_connect_generic_failure_fails_closed_and_disconnects(monkeypatch) -> None:
    instances = []

    class FailingIB:
        def __init__(self) -> None:
            self.disconnect_calls = 0
            instances.append(self)

        def connect(self, host, port, *, clientId, timeout, readonly) -> None:
            raise RuntimeError("socket refused before broker audit")

        def disconnect(self) -> None:
            self.disconnect_calls += 1

    _install_fake_ib_insync(monkeypatch, FailingIB)

    provider = pr1034.IBInsyncReadOnlyProvider(_config())

    with pytest.raises(pr1034.CollectorValidationError, match="connection failed"):
        provider.connect_readonly()

    assert provider._ib is None
    assert instances[0].disconnect_calls == 1


def test_pr1037_disconnect_cleanup_preserves_original_connect_failure() -> None:
    class DisconnectAlsoFails:
        def disconnect(self) -> None:
            raise RuntimeError("disconnect cleanup failed")

    pr1034._disconnect_after_failed_connect(DisconnectAlsoFails())


def test_pr1037_report_documents_timeout_fix_and_keeps_paper_blocked() -> None:
    report = _REPORT_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "PAPER_READY: NO",
        "PR1034_IB_INSYNC_CONNECT_TIMEOUT_FAILS_CLOSED: YES",
        "PYTHON314_CONNECT_TIMEOUT_PATH_GUARDED: YES",
        "PARTIAL_IB_OBJECT_DISCONNECTED_ON_CONNECT_FAILURE: YES",
        "DEFAULT_PATCH_ASYNCIO_NEST_ASYNCIO_PATH_ENABLED: NO",
        "CI_CONNECTS_TO_IBKR: NO",
        "ORDER_MUTATION_ALLOWED: NO",
        "PAPER_READINESS_GATE: FAIL",
        "Connect timeout exceptions now abort as `CollectorValidationError` before broker audit begins.",
        "The default `patchAsyncio()`/`nest_asyncio` route is not used.",
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
