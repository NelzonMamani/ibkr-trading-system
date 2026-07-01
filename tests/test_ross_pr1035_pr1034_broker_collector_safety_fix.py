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
    / "PR1035_PR1034_IB_INSYNC_EVENT_LOOP_AND_FAIL_CLOSED_BROKER_COLLECTOR_FIX.md"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("pr1034_collector_pr1035", _SCRIPT_PATH)
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
        client_id=1035,
        timeout_seconds=3.0,
        market_data_type="TEST_READ_ONLY",
    )


def _broker_snapshot(**overrides):
    snapshot = {
        "provider_name": "PR1035_TEST_PROVIDER",
        "connected": True,
        "host": "127.0.0.1",
        "port": 7497,
        "client_id": 1035,
        "market_data_type": "TEST_READ_ONLY",
        "account_id_redacted": "REDACTED",
        "submitted_orders_count": 0,
        "cancelled_orders_count": 0,
        "modified_orders_count": 0,
        "open_orders_before": [],
        "open_orders_after": [],
    }
    snapshot.update(overrides)
    return snapshot


def test_pr1035_ib_insync_provider_bootstraps_event_loop_before_connect(monkeypatch) -> None:
    calls: list[object] = []

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

    fake_ib_insync = types.ModuleType("ib_insync")
    fake_ib_insync.IB = FakeIB
    fake_ib_insync.util = FakeUtil()
    monkeypatch.setitem(sys.modules, "ib_insync", fake_ib_insync)

    provider = pr1034.IBInsyncReadOnlyProvider(_config())
    provider.connect_readonly()

    assert calls[0] == "patchAsyncio"
    assert calls[1] == "IB"
    assert calls[2] == ("connect", "127.0.0.1", 7497, 1035, 3.0, True)


def test_pr1035_ib_insync_bootstrap_failure_aborts_before_connection() -> None:
    class FailingUtil:
        def patchAsyncio(self) -> None:
            raise RuntimeError("loop patch failed")

    with pytest.raises(pr1034.CollectorValidationError, match="event-loop bootstrap failed"):
        pr1034.bootstrap_ib_insync_event_loop(FailingUtil())


def test_pr1035_open_order_request_failure_aborts_capture() -> None:
    class RequestFailIB:
        def reqOpenOrders(self) -> None:
            raise RuntimeError("request failed")

    provider = pr1034.IBInsyncReadOnlyProvider(_config())
    provider._ib = RequestFailIB()

    with pytest.raises(pr1034.CollectorValidationError, match="open-order request failed"):
        provider._open_orders_snapshot()


def test_pr1035_open_order_read_failure_aborts_capture() -> None:
    class ReadFailIB:
        def reqOpenOrders(self) -> None:
            return None

        def openOrders(self):
            raise RuntimeError("read failed")

    provider = pr1034.IBInsyncReadOnlyProvider(_config())
    provider._ib = ReadFailIB()

    with pytest.raises(pr1034.CollectorValidationError, match="open-order read failed"):
        provider._open_orders_snapshot()


def test_pr1035_managed_account_read_failure_aborts_capture() -> None:
    class AccountFailIB:
        def isConnected(self) -> bool:
            return True

        def reqOpenOrders(self) -> None:
            return None

        def openOrders(self):
            return []

        def managedAccounts(self):
            raise RuntimeError("account read failed")

    provider = pr1034.IBInsyncReadOnlyProvider(_config())
    provider._ib = AccountFailIB()

    with pytest.raises(pr1034.CollectorValidationError, match="managed-account read failed"):
        provider.collect_snapshot()


def test_pr1035_broker_snapshot_rejects_open_order_failure_marker() -> None:
    failure_row = {"status": "OPEN_ORDER_REQUEST_FAILED"}
    snapshot = _broker_snapshot(
        open_orders_before=[failure_row],
        open_orders_after=[failure_row],
    )

    with pytest.raises(pr1034.CollectorValidationError, match="open-order audit failure status"):
        pr1034.assert_broker_snapshot_safe(snapshot)


def test_pr1035_broker_snapshot_requires_complete_connection_evidence() -> None:
    snapshot = _broker_snapshot()
    snapshot.pop("account_id_redacted")

    with pytest.raises(pr1034.CollectorValidationError, match="missing required field"):
        pr1034.assert_broker_snapshot_safe(snapshot)


def test_pr1035_report_documents_safety_fix_and_keeps_paper_blocked() -> None:
    report = _REPORT_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "PAPER_READY: NO",
        "PR1034_EVENT_LOOP_BOOTSTRAP_FIXED: YES",
        "PR1034_FAIL_CLOSED_BROKER_EVIDENCE: YES",
        "OPEN_ORDER_REQUEST_FAILURE_ABORTS_CAPTURE: YES",
        "OPEN_ORDER_READ_FAILURE_ABORTS_CAPTURE: YES",
        "MANAGED_ACCOUNT_READ_FAILURE_ABORTS_CAPTURE: YES",
        "CI_CONNECTS_TO_IBKR: NO",
        "ORDER_MUTATION_ALLOWED: NO",
        "PAPER_READINESS_GATE: FAIL",
        "ib_insync event-loop bootstrap runs before the `IB()` object is created",
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
