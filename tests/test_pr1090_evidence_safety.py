from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from types import SimpleNamespace
import json

import pytest

from src.ibkr import evidence_safety as privacy
from src.ibkr import mutation_audit as audit
from src.ibkr.shutdown_evidence import ShutdownEvidence, REQUIRED_HOOKS, validate_terminal, complete_after_process_exit


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    monkeypatch.setattr(privacy, "_tokens", set())
    monkeypatch.setattr(audit, "_counts", {"place": 0, "modify": 0, "cancel": 0})


def test_freeform_siblings_objects_and_prewrite(tmp_path):
    token = "synthetic-account-alpha"
    payload = {"message": "connection " + token, "position": SimpleNamespace(account=token, symbol="XYZ")}
    protected = privacy.sanitize(payload)
    assert protected["message"] == "connection REDACTED"
    assert payload["position"].account == token
    assert protected["position"].account == "REDACTED"
    privacy.write_json(tmp_path / "raw.json", payload)
    privacy.write_text(tmp_path / "report.md", token)
    assert token not in (tmp_path / "raw.json").read_text()
    assert (tmp_path / "report.md").read_text() == "REDACTED"
    assert privacy.scan_artifacts(tmp_path)["passed"]


def test_unknown_account_shape_is_redacted():
    token = "DU" + "987654321"
    assert privacy.scrub_text("session=" + token) == "session=REDACTED"


def test_split_console_writes_and_flush_never_expose_prefix():
    token = "synthetic-account-alpha"
    privacy.register_account(token)
    target = StringIO()
    stream = privacy.SafeTextStream(target)
    stream.write(token[:10])
    stream.flush()
    assert target.getvalue() == ""
    stream.write(token[10:] + "\n")
    stream.write(token)
    stream.finish()
    assert target.getvalue() == "REDACTED\nREDACTED"


def test_console_capture_exception_finalizes_both_streams(tmp_path):
    import sys
    privacy.register_account("synthetic-account-alpha")
    with pytest.raises(ValueError), privacy.capture_console(tmp_path):
        sys.stdout.write("synthetic-account-alpha")
        sys.stderr.write("synthetic-account-alpha")
        raise ValueError("stop")
    assert (tmp_path / "stdout.log").read_text() == "REDACTED"
    assert (tmp_path / "stderr.log").read_text() == "REDACTED"


def test_scan_returns_only_paths_and_counts(tmp_path):
    token = "synthetic-account-alpha"
    privacy.register_account(token)
    (tmp_path / "bad.txt").write_text(token + token)
    result = privacy.scan_artifacts(tmp_path)
    assert result == {"passed": False, "occurrences": 2, "files": {"bad.txt": 2}}
    assert token not in json.dumps(result)


def test_attempts_count_before_guard_and_across_threads(monkeypatch):
    from src.ibkr import read_only_guard
    def blocked(*args):
        raise RuntimeError("blocked")
    monkeypatch.setattr(read_only_guard, "assert_read_only_allows", blocked)
    class Client:
        def placeOrder(self, orderId, contract, order):
            pytest.fail("guard bypassed")
        def cancelOrder(self, orderId):
            pytest.fail("guard bypassed")
    audit.install_sdk(Client, type("Wrapper", (), {}))
    client = Client()
    def attempt(index):
        with pytest.raises(RuntimeError):
            client.placeOrder(orderId=index, contract=None, order=None)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(attempt, range(100)))
    with pytest.raises(RuntimeError):
        client.placeOrder(0, None, None)
    with pytest.raises(RuntimeError):
        client.cancelOrder(0)
    assert audit.snapshot() == {"place": 100, "modify": 1, "cancel": 1}
    with pytest.raises(RuntimeError):
        audit.require_zero_attempts(audit.snapshot())


def terminal_payload():
    proof = ShutdownEvidence()
    proof.record("GRACEFUL_STOP_REQUESTED", completed=True)
    proof.record("SHUTDOWN_STARTED", completed=True)
    for name in REQUIRED_HOOKS:
        proof.attempt(name, lambda: None)
    proof.record("SHUTDOWN_COMPLETE", completed=True)
    proof.record("TERMINAL_FLUSHED", completed=True)
    return proof


def test_hook_failures_do_not_prevent_later_hooks():
    proof = ShutdownEvidence()
    proof.attempt("broken", lambda: (_ for _ in ()).throw(RuntimeError()))
    proof.attempt("next", lambda: None)
    assert not proof.hooks[0]["completed"]
    assert proof.hooks[1]["completed"]


def test_missing_terminal_evidence_fails_closed():
    assert not validate_terminal({})["passed"]


def verified_process(poll):
    identity = {"pid": 999999, "parent_pid": 1, "creation_token": "windows-filetime:100", "argv": ["python", "-m", "src.main"]}
    return SimpleNamespace(pid=999999, poll=poll, runtime_identity=identity,
                           launcher_identity=identity, identity_verified=True, launcher_exit_code=0)


def test_supervisor_orders_audit_after_exit_and_writes_report(tmp_path):
    proof = terminal_payload()
    payload = proof.payload()
    payload["pid"] = 999999
    payload["process_identity"] = verified_process(lambda: 0).runtime_identity
    privacy.write_json(tmp_path / "shutdown_evidence.json", payload)
    order = []
    process = verified_process(lambda: order.append("poll") or 0)
    def quiet():
        order.append("inventory")
        return True
    def final_audit():
        order.append("audit")
        return {"query_completed": True, "disconnected": True}
    result = complete_after_process_exit(tmp_path, process, quiet, final_audit)
    assert result["passed"], result
    assert order == ["poll", "inventory", "audit"]
    assert (tmp_path / "FINAL_REPORT.md").exists()


def test_live_process_keeps_callbacks_and_blocks_certification(tmp_path):
    proof = terminal_payload()
    payload = proof.payload()
    payload["pid"] = 999999
    payload["process_identity"] = verified_process(lambda: 0).runtime_identity
    privacy.write_json(tmp_path / "shutdown_evidence.json", payload)
    process = verified_process(lambda: None)
    calls = []
    result = complete_after_process_exit(tmp_path, process, lambda: calls.append("inventory") or False, lambda: calls.append("audit") or {"query_completed": True, "disconnected": True})
    assert not result["passed"]
    assert calls == ["inventory", "audit"]


@pytest.mark.parametrize("bad", [None, {}, {"place": False, "modify": 0, "cancel": 0}, {"place": -1, "modify": 0, "cancel": 0}])
def test_invalid_counter_evidence_fails_closed(bad):
    with pytest.raises(RuntimeError):
        audit.require_zero_attempts(bad)


def test_observable_callback_redacts_but_reconciliation_retains_account():
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    client = object.__new__(IbkrClient)
    client._execution_callbacks = []
    visible, internal = [], []
    client.register_execution_callback(visible.append)
    client.register_reconciliation_callback(internal.append)
    payload = {"account": "synthetic-account-alpha", "message": "synthetic-account-alpha"}
    client._emit_execution_callback(payload)
    assert visible[0]["account"] == "REDACTED"
    assert internal[0]["account"] == "synthetic-account-alpha"


def test_adapter_rejects_attempt_even_when_events_and_orders_are_empty(monkeypatch):
    from scripts.certification import pr1040_real_readonly_runtime_observation_adapter as adapter
    monkeypatch.setitem(audit._counts, "cancel", 1)
    evidence = SimpleNamespace(execution_events=[], broker_before={"open_orders": []}, broker_after={"open_orders": []})
    assert adapter._order_mutation_count(evidence) == 1


def test_failing_audit_disconnect_fails_report(tmp_path):
    proof = terminal_payload()
    payload = proof.payload()
    payload["pid"] = 999999
    payload["process_identity"] = verified_process(lambda: 0).runtime_identity
    privacy.write_json(tmp_path / "shutdown_evidence.json", payload)
    result = complete_after_process_exit(tmp_path, verified_process(lambda: 0), lambda: True,
                                        lambda: {"query_completed": True, "disconnected": False})
    assert not result["passed"]
    assert "FAIL" in (tmp_path / "FINAL_REPORT.md").read_text()


def test_logging_exception_is_protected_before_file_handler(tmp_path, monkeypatch):
    import logging
    import sys
    monkeypatch.setattr(sys, "stdout", StringIO())
    monkeypatch.setattr(sys, "stderr", StringIO())
    original_factory = logging.getLogRecordFactory()
    privacy.register_account("synthetic-account-alpha")
    logger = logging.getLogger("pr1090.offline.test")
    handler = logging.FileHandler(tmp_path / "application.log")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        privacy.install_console_protection()
        try:
            raise ValueError("synthetic-account-alpha")
        except ValueError:
            logger.exception("account %s", "synthetic-account-alpha")
    finally:
        logger.removeHandler(handler)
        handler.close()
        logging.setLogRecordFactory(original_factory)
    assert "synthetic-account-alpha" not in (tmp_path / "application.log").read_text()


@pytest.mark.parametrize("query_ok", [True, False])
def test_final_audit_always_disconnects_without_real_broker(monkeypatch, query_ok):
    from scripts.certification import pr1090_terminal_observation_supervisor as supervisor
    from src.adapters.brokers.ibkr import ibkr_client
    from src.config import runtime_config
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["readonly_enabled"] is True
            self.connected = False
            self._thread = None
            self._open_orders_snapshot = {}
            self._open_orders_event = SimpleNamespace(clear=lambda: None, wait=lambda timeout: query_ok)
        def connect(self):
            calls.append("connect")
            self.connected = True
        def reqAllOpenOrders(self):
            calls.append("query")
        def disconnect(self):
            calls.append("disconnect")
            self.connected = False
        def is_connected(self):
            return self.connected
    monkeypatch.setattr(ibkr_client, "IbkrClient", Client)
    monkeypatch.setattr(runtime_config, "resolve_ibkr_connection", lambda: ("fake", 0, 123, "READ_ONLY"))
    result = supervisor.final_broker_audit()
    assert result["query_completed"] is query_ok
    assert result["disconnected"] is True
    assert calls == ["connect", "query", "disconnect"]


def test_counter_nested_submit_does_not_double_count(monkeypatch):
    from src.ibkr import read_only_guard
    monkeypatch.setattr(read_only_guard, "assert_read_only_allows", lambda *args: None)
    class Client:
        def submit_order(self, contract, order):
            self.placeOrder(1, contract, order)
        def placeOrder(self, orderId, contract, order):
            pass
    audit.install_sdk(Client, type("Wrapper", (), {}))
    audit.instrument_mutation(Client, "submit_order")
    Client().submit_order(None, None)
    assert audit.snapshot() == {"place": 1, "modify": 0, "cancel": 0}


def test_shutdown_event_failure_does_not_skip_cleanup(monkeypatch):
    from src.core.orchestrator import CoreOrchestrator
    from src.core.stop_controller import StopMode
    from src.ibkr import shutdown_evidence
    called = []
    engine = SimpleNamespace(shutdown=lambda: called.append("engine"))
    instance = object.__new__(CoreOrchestrator)
    from src.core.stop_controller import StopController
    instance.stop_controller = StopController()
    instance.stop_controller.request_stop(StopMode.GRACEFUL, reason="test shutdown", source="test")
    instance._stop_payload = lambda mode: {}
    instance._emit_ops_summary = lambda: called.append("ops")
    instance.learning_scheduler = SimpleNamespace(on_shutdown=lambda: called.append("learning"))
    instance.execution_engine = instance.trade_exit_engine = instance.storage_engine = engine
    instance.trade_registry = SimpleNamespace(verify_empty=lambda: True)
    def failed_emit(**kwargs):
        raise OSError("event writer unavailable")
    instance.event_collector = SimpleNamespace(emit=failed_emit, flush_summary=lambda: called.append("flush"))
    monkeypatch.setattr(shutdown_evidence, "reset_scanner", lambda: called.append("scanner"))
    monkeypatch.setattr(shutdown_evidence, "disconnect_manager", lambda: called.append("disconnect"))
    instance._shutdown(StopMode.GRACEFUL)
    assert called == ["ops", "learning", "engine", "engine", "engine", "scanner", "disconnect", "flush"]
    assert instance.shutdown_evidence.events[-1]["completed"] is False


def test_supervisor_capture_io_failure_is_recorded(tmp_path):
    from scripts.certification import pr1090_terminal_observation_supervisor as supervisor
    errors = []
    supervisor._capture(StringIO("line"), tmp_path / "missing" / "output.log", errors)
    assert errors == ["FileNotFoundError"]
