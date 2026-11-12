"""Offline regressions for the three reviewed PR1090 P1 findings."""
from io import StringIO
import json
import subprocess
import threading
from types import SimpleNamespace

import pytest

from scripts.certification import pr1090_terminal_observation_supervisor as supervisor
from src.ibkr import evidence_safety as privacy
from src.ibkr import shutdown_evidence as shutdown

HEAD = "a" * 40


def mock_git(monkeypatch, *, head=HEAD, status=""):
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        assert command[:2] in (["git", "rev-parse"], ["git", "status"])
        return SimpleNamespace(stdout=head + "\n" if command[1] == "rev-parse" else status)
    monkeypatch.setattr(supervisor.subprocess, "run", run)
    return commands


def test_clean_expected_head_preflight_is_read_only(monkeypatch):
    commands = mock_git(monkeypatch)
    assert supervisor.require_clean_certification_worktree(HEAD) == HEAD
    assert commands[-1] == ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none"]


@pytest.mark.parametrize("head,status", [("b" * 40, ""), (HEAD, " M src/main.py\0"),
    (HEAD, "M  src/main.py\0"), (HEAD, "?? src/injected.py\0"),
    (HEAD, " M TRADING_OS_MASTER_CATALOGUE/generated.md\0")])
def test_preflight_failure_creates_no_child_audit_or_artifacts(monkeypatch, tmp_path, head, status):
    commands = mock_git(monkeypatch, head=head, status=status)
    drift = tmp_path / "preserved.txt"
    drift.write_text("user drift")
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *a, **k: pytest.fail("child created"))
    monkeypatch.setattr(supervisor, "final_broker_audit", lambda: pytest.fail("audit reached"))
    output = tmp_path / "evidence"
    with pytest.raises(SystemExit) as exc:
        supervisor.main(["--seconds", "1", "--output", str(output), "--expected-commit", HEAD])
    assert exc.value.code != 0
    assert not output.exists()
    assert drift.read_text() == "user drift"
    assert all(command[1] in {"rev-parse", "status"} for command in commands)


def test_dirty_filename_is_redacted(monkeypatch):
    token = "DU" + "987654321"
    mock_git(monkeypatch, status="?? src/" + token + ".py\0")
    with pytest.raises(RuntimeError) as exc:
        supervisor.require_clean_certification_worktree(HEAD)
    assert token not in str(exc.value)
    assert "REDACTED.py" in str(exc.value)
    assert '"status": "??"' in str(exc.value)


def test_second_preflight_catches_change_during_preparation(monkeypatch, tmp_path):
    from scripts.certification import pr1040_real_readonly_runtime_observation_adapter as adapter
    calls = []
    def preflight(head):
        calls.append("preflight")
        if len(calls) > 1:
            raise RuntimeError("worktree changed")
    monkeypatch.setattr(supervisor, "require_clean_certification_worktree", preflight)
    monkeypatch.setattr(supervisor, "install_console_protection", lambda: None)
    monkeypatch.setattr(adapter, "build_safe_readonly_env", lambda: {})
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *a, **k: pytest.fail("child created"))
    output = tmp_path / "evidence"
    with pytest.raises(SystemExit):
        supervisor.main(["--seconds", "1", "--output", str(output), "--expected-commit", HEAD])
    assert calls == ["preflight", "preflight"]
    assert not output.exists()


def fake_orchestrator(monkeypatch, nonessential=None, execution=None):
    from src.core.orchestrator import CoreOrchestrator
    from src.core.stop_controller import StopController
    instance = object.__new__(CoreOrchestrator)
    instance.stop_controller = StopController()
    instance._stop_payload = lambda mode: {}
    called = []
    def hook(name):
        def invoke(**kwargs):
            called.append(name)
            if nonessential is not None:
                return nonessential()
        return invoke
    instance._emit_ops_summary = hook("ops_summary")
    instance.learning_scheduler = SimpleNamespace(on_shutdown=hook("learning_scheduler"))
    instance.execution_engine = SimpleNamespace(shutdown=execution or (lambda: called.append("execution_engine.shutdown")))
    instance.trade_exit_engine = SimpleNamespace(shutdown=hook("trade_exit_engine.shutdown"))
    instance.storage_engine = SimpleNamespace(shutdown=hook("storage_engine.shutdown"))
    instance.trade_registry = SimpleNamespace(verify_empty=hook("active_trade_registry.verify_empty"))
    instance.event_collector = SimpleNamespace(emit=lambda **kwargs: None, flush_summary=hook("event_collector.flush_summary"))
    monkeypatch.setattr(shutdown, "reset_scanner", hook("scanner_reset"))
    monkeypatch.setattr(shutdown, "disconnect_manager", hook("manager_disconnect"))
    monkeypatch.setattr(privacy, "finish_console_protection", hook("console_flush"))
    monkeypatch.delenv("PR1090_EVIDENCE_DIR", raising=False)
    return instance, called


def test_graceful_keeps_all_ordered_hooks_and_flush(monkeypatch, tmp_path):
    from src.core.stop_controller import StopMode
    instance, called = fake_orchestrator(monkeypatch)
    monkeypatch.setenv("PR1090_EVIDENCE_DIR", str(tmp_path))
    instance._shutdown(StopMode.GRACEFUL)
    assert called == list(shutdown.REQUIRED_HOOKS)
    proof = json.loads((tmp_path / "shutdown_evidence.json").read_text())
    assert proof["events"][-1]["event"] == "TERMINAL_FLUSHED"
    instance._shutdown(StopMode.GRACEFUL)
    assert called == list(shutdown.REQUIRED_HOOKS)


def test_graceful_hook_failure_is_isolated(monkeypatch):
    from src.core.stop_controller import StopMode
    instance, called = fake_orchestrator(monkeypatch)
    instance._emit_ops_summary = lambda: (_ for _ in ()).throw(ValueError("failure"))
    instance._shutdown(StopMode.GRACEFUL)
    assert called == list(shutdown.REQUIRED_HOOKS)[1:]
    assert instance.shutdown_evidence.hooks[0]["completed"] is False


def _shutdown_ownership_owner(mode, provider_kind="native"):
    """Build existing owners without a Core constructor or external clients."""
    from src.core.active_trade_registry import ActiveTradeRegistry
    from src.core.orchestrator import CoreOrchestrator
    from src.execution.execution_engine import ExecutionEngine
    from src.execution.execution_providers import IbkrExecutionProvider, PaperExecutionProvider
    from src.execution.order_models import PendingOrderBook
    from src.sim.price_feed import DeterministicPriceFeed

    core = object.__new__(CoreOrchestrator)
    core.run_mode = mode
    engine = object.__new__(ExecutionEngine)
    engine.run_mode = mode
    engine.execution_enabled = True
    engine._native_orders = {}
    engine._native_state = None
    engine._native_quarantined = False
    engine.position_records = {}
    engine.pending_book = PendingOrderBook()
    engine.capital_authority = SimpleNamespace(capital_scope=None, active_reservations={})
    engine.strategy_allocation_authority = SimpleNamespace(active_reservations={})
    if provider_kind == "native":
        engine._provider = IbkrExecutionProvider(
            broker=SimpleNamespace(connected=True), trade_registry=ActiveTradeRegistry(), run_mode=mode)
    elif provider_kind == "simulator":
        engine._provider = PaperExecutionProvider(
            price_feed=DeterministicPriceFeed(), trade_registry=ActiveTradeRegistry(),
            event_collector=SimpleNamespace(), run_mode=mode)
    elif provider_kind == "disabled":
        engine._provider = None
        engine.execution_enabled = False
    else:
        engine._provider = SimpleNamespace(is_live=lambda: False)
    core.execution_engine = engine
    return core, engine


@pytest.mark.parametrize("provider_kind,mode,simulator", [
    ("native", "PAPER", False), ("native", "LIVE", False),
    ("simulator", "PAPER", True), ("simulator", "SIM", True),
    ("disabled", "SIM", True), ("disabled", "READ_ONLY", False),
])
def test_shutdown_context_uses_resolved_provider_not_connection(provider_kind, mode, simulator):
    from src.config.runtime_config import RunMode

    core, engine = _shutdown_ownership_owner(RunMode(mode), provider_kind)
    if provider_kind == "native":
        engine._provider.broker.connected = False
    context = core._trade_exit_shutdown_context()
    assert context.run_mode == RunMode(mode)
    assert context.simulator_backed is simulator
    assert context.retained_native_ownership is False


@pytest.mark.parametrize("retained", [
    "protected", "ack_only", "partial", "historical_state", "quarantined",
    "position_record", "pending", "capital_reservation", "allocation_reservation", "capital_scope",
])
@pytest.mark.parametrize("provider_kind", ["native", "simulator"])
def test_shutdown_context_distinguishes_native_from_generic_simulator_ownership(retained, provider_kind):
    from src.config.runtime_config import RunMode

    core, engine = _shutdown_ownership_owner(RunMode.PAPER, provider_kind)
    if retained in {"protected", "ack_only", "partial"}:
        engine._native_orders["root"] = {"requested": 1,
            "filled": {"protected": 1, "ack_only": 0, "partial": .5}[retained],
            "terminal": retained == "protected"}
        if retained != "ack_only":
            engine.position_records["root"] = {"quantity": engine._native_orders["root"]["filled"]}
    elif retained == "historical_state":
        engine._native_state = {"orders": {}}
    elif retained == "quarantined":
        engine._native_quarantined = True
    elif retained == "position_record":
        engine.position_records["root"] = {"filled_qty": 1}
    elif retained == "pending":
        engine.pending_book.add(SimpleNamespace(client_order_id="pending"))
    elif retained == "capital_reservation":
        engine.capital_authority.active_reservations["cap"] = object()
    elif retained == "allocation_reservation":
        engine.strategy_allocation_authority.active_reservations["allocation"] = object()
    else:
        engine.capital_authority.capital_scope = object()
    context = core._trade_exit_shutdown_context()
    assert context.simulator_backed is (provider_kind == "simulator")
    assert context.retained_native_ownership is (provider_kind == "native" or retained in {
        "protected", "ack_only", "partial", "historical_state", "quarantined", "capital_scope"})
    assert core._trade_exit_shutdown_context() == context


def test_shutdown_real_simulator_fill_keeps_generic_position_record_and_teaching_close():
    from src.brokers.base_broker import BrokerOrderRequest
    from src.brokers.sim_broker import SimBroker
    from src.config.config_resolver import clear_config_overrides, set_config_overrides
    from src.config.runtime_config import RunMode
    from src.core.orchestrator import CoreOrchestrator
    from src.execution.execution_engine import ExecutionEngine
    from src.execution.execution_providers import PaperExecutionProvider
    from src.execution.trade_exit_engine import TradeExitEngine

    class Price:
        def price_for(self, *args):
            return 10.75

    set_config_overrides({"RUN_MODE": "PAPER", "RUN_MODE_EFFECTIVE": "PAPER",
        "EXECUTION_ENABLED": True, "EXECUTION_ENABLED_EFFECTIVE": True,
        "IBKR_READONLY_ENABLED": False})
    try:
        engine = ExecutionEngine(price_feed=Price())
        assert isinstance(engine._provider, PaperExecutionProvider)
        assert isinstance(engine._provider.broker, SimBroker)
        assert engine.capital_authority.capital_scope is None
        request = BrokerOrderRequest(client_order_id="sim-shutdown-entry", symbol="ABC",
            direction="LONG", quantity=1, trader_type="SCALPER", strategy_name="TestStrategy",
            created_tick=0, stop_loss_price=10.30, take_profit_price=None)
        result = engine._provider.place_order(request)
        assert result.filled_quantity == 1
        engine._record_fill_and_position(request, result)
        assert engine.position_records[request.client_order_id]["filled_qty"] == 1
        assert len(engine.trade_registry.snapshot()) == 1
        assert engine._selected_order_records() == {} and engine._native_state is None
        core = object.__new__(CoreOrchestrator)
        core.run_mode = RunMode.PAPER
        core.execution_engine = engine
        context = core._trade_exit_shutdown_context()
        assert context.simulator_backed is True
        assert context.retained_native_ownership is False
        before_positions = dict(engine.position_records)
        used_capital = engine.capital_authority.total_used_exposure
        used_allocation = engine.strategy_allocation_authority.strategy_used_exposure("TestStrategy")
        exit_owner = TradeExitEngine(engine.trade_registry, engine.event_collector, Price())
        assert exit_owner.shutdown(current_tick=7, execution_context=context) is True
        assert engine.trade_registry.snapshot() == []
        assert len(engine.event_collector.filter_by_type("TRADE_CLOSED")) == 1
        assert engine.event_collector.filter_by_type("TRADE_CLOSED")[0].payload["mode"] == "PAPER"
        # Shutdown preserves the simulator's existing accounting semantics; it
        # neither clears generic records nor claims a factual capital release.
        assert engine.position_records == before_positions
        assert engine.capital_authority.total_used_exposure == used_capital
        assert engine.strategy_allocation_authority.strategy_used_exposure("TestStrategy") == used_allocation
    finally:
        clear_config_overrides()


@pytest.mark.parametrize("uncertainty", [
    "foreign_provider", "mode_mismatch", "missing_mode", "missing_native_state",
    "malformed_records", "malformed_pending", "malformed_quarantine", "missing_capital",
    "provider_mode_mismatch", "broker_mode_mismatch", "provider_live_contradiction",
    "unknown_capital_reservations", "unknown_allocation_reservations",
])
def test_shutdown_context_never_converts_missing_or_inconsistent_facts_to_flat(uncertainty):
    from src.config.runtime_config import RunMode

    core, engine = _shutdown_ownership_owner(RunMode.PAPER, "simulator")
    if uncertainty == "foreign_provider":
        engine._provider = SimpleNamespace(is_live=lambda: False)
    elif uncertainty == "mode_mismatch":
        engine.run_mode = RunMode.SIM
    elif uncertainty == "missing_mode":
        del core.run_mode
    elif uncertainty == "missing_native_state":
        del engine._native_state
    elif uncertainty == "malformed_records":
        engine._native_orders = None
    elif uncertainty == "malformed_pending":
        engine.pending_book = SimpleNamespace(count=lambda: False)
    elif uncertainty == "malformed_quarantine":
        engine._native_quarantined = None
    elif uncertainty == "missing_capital":
        del engine.capital_authority
    elif uncertainty == "provider_mode_mismatch":
        engine._provider.run_mode = RunMode.LIVE
    elif uncertainty == "broker_mode_mismatch":
        engine._provider.broker.run_mode = RunMode.LIVE
    elif uncertainty == "unknown_capital_reservations":
        engine.capital_authority.active_reservations = None
    elif uncertainty == "unknown_allocation_reservations":
        engine.strategy_allocation_authority.active_reservations = None
    else:
        engine._provider.is_live = lambda: True
    context = core._trade_exit_shutdown_context()
    assert context.run_mode is None
    assert context.simulator_backed is False
    assert context.retained_native_ownership is None


@pytest.mark.parametrize("ownership", ["protected", "ack_only", "partial"])
def test_graceful_native_ownership_context_precedes_disconnect_and_other_hooks_continue(monkeypatch, ownership):
    from src.config.runtime_config import RunMode
    from src.core.active_trade_registry import ActiveTrade
    from src.core.event_collector import EventCollector
    from src.core.stop_controller import StopMode
    from src.execution.trade_exit_engine import TradeExitEngine

    instance, called = fake_orchestrator(monkeypatch)
    owner, engine = _shutdown_ownership_owner(RunMode.PAPER)
    instance.run_mode = owner.run_mode
    quantity = {"protected": 1, "ack_only": 0, "partial": .5}[ownership]
    engine._native_orders["root"] = {"requested": 1, "filled": quantity,
        "terminal": ownership == "protected"}
    instance.execution_engine = engine
    registry = engine._provider.trade_registry
    trade = ActiveTrade(symbol="JPM", trader_type="SCALPER", entry_tick=1,
        entry_price=10.53, direction="LONG", quantity=quantity, strategy_name="ross_momentum",
        stop_loss_price=10.2897)
    if quantity:
        registry.register_trade(trade)
    else:
        engine.capital_authority.active_reservations["cap"] = {"remaining_qty": 1}
    expected_registry = [trade] if quantity else []
    instance.trade_registry = registry
    collector = EventCollector()
    instance.trade_exit_engine = TradeExitEngine(registry, collector,
        price_feed=SimpleNamespace(price_for=lambda *a: pytest.fail("native teaching price")))
    original_capture = instance._trade_exit_shutdown_context
    captures = []
    def capture():
        captures.append(engine._provider.broker.connected)
        return original_capture()
    instance._trade_exit_shutdown_context = capture
    def disconnect():
        called.append("execution_engine.shutdown")
        engine._provider.broker.connected = False
    engine.shutdown = disconnect
    instance._shutdown(StopMode.GRACEFUL)
    assert captures == [True]
    assert registry.snapshot() == expected_registry
    if quantity:
        assert trade.state.value == "OPEN"
    else:
        assert engine.capital_authority.active_reservations == {"cap": {"remaining_qty": 1}}
    assert not collector.filter_by_type("TRADE_CLOSED")
    hooks = {row["hook"]: row for row in instance.shutdown_evidence.hooks}
    assert hooks["trade_exit_engine.shutdown"]["completed"] is False
    assert hooks["active_trade_registry.verify_empty"]["completed"] is (not bool(quantity))
    assert all(hooks[name]["completed"] for name in (
        "storage_engine.shutdown", "scanner_reset", "manager_disconnect",
        "event_collector.flush_summary", "console_flush"))
    instance._shutdown(StopMode.GRACEFUL)
    assert captures == [True]
    assert registry.snapshot() == expected_registry


@pytest.mark.parametrize("execution_fails", [False, True])
def test_panic_minimal_truthful_idempotent_and_never_certifies(monkeypatch, execution_fails):
    from src.core.stop_controller import StopMode
    attempts = []
    def execution():
        attempts.append("execution")
        if execution_fails:
            raise RuntimeError("essential failure")
    def forbidden():
        pytest.fail("PANIC entered a nonessential hook")
    instance, called = fake_orchestrator(monkeypatch, forbidden, execution)
    monkeypatch.setattr(shutdown.ShutdownEvidence, "flush", lambda *a: pytest.fail("PANIC flushed evidence"))
    instance._shutdown(StopMode.PANIC)
    instance._shutdown(StopMode.PANIC)
    assert attempts == ["execution"]
    assert called == []
    proof = instance.shutdown_evidence.payload()
    assert "GRACEFUL_STOP_REQUESTED" not in [row["event"] for row in proof["events"]]
    assert proof["events"][0]["mode"] == "PANIC"
    assert proof["hooks"][0]["completed"] is (not execution_fails)
    assert all(row["skipped"] and row["reason"] == "PANIC" and not row["attempted"] for row in proof["hooks"][1:])
    assert not shutdown.validate_terminal(proof)["passed"]


def test_blocked_nonessential_hook_cannot_delay_panic(monkeypatch):
    from src.core.stop_controller import StopMode
    release = threading.Event()
    instance, called = fake_orchestrator(monkeypatch, lambda: release.wait(timeout=5))
    worker = threading.Thread(target=instance._shutdown, args=(StopMode.PANIC,), daemon=True)
    try:
        worker.start()
        worker.join(timeout=1)
        assert not worker.is_alive()
        assert called == ["execution_engine.shutdown"]
    finally:
        release.set()
        worker.join(timeout=1)


class Process:
    pid = 999999
    runtime_identity = {"pid": pid, "parent_pid": 1, "creation_token": "windows-filetime:100", "argv": ["python", "-m", "src.main"]}
    launcher_identity = runtime_identity
    identity_verified = True
    lineage = [runtime_identity]
    def bind(self):
        pass
    def close(self):
        pass
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []
        self.returncode = None
        self.stdout, self.stderr = StringIO(), StringIO()
    def wait(self, timeout):
        self.calls.append(("wait", timeout))
        outcome = next(self.outcomes)
        if outcome == "timeout":
            raise subprocess.TimeoutExpired("account " + "DU" + "987654321", timeout)
        self.returncode = outcome
        return outcome
    def poll(self):
        return self.returncode
    def terminate(self):
        self.calls.append(("terminate",))
    def kill(self):
        self.calls.append(("kill",))


def prepare_child_proof(tmp_path):
    proof = shutdown.ShutdownEvidence()
    proof.record("GRACEFUL_STOP_REQUESTED", completed=True)
    proof.record("SHUTDOWN_STARTED", completed=True)
    for name in shutdown.REQUIRED_HOOKS:
        proof.attempt(name, lambda: None)
    proof.record("SHUTDOWN_COMPLETE", completed=True)
    proof.record("TERMINAL_FLUSHED", completed=True)
    payload = proof.payload()
    payload["pid"] = Process.pid
    payload["process_identity"] = Process.runtime_identity
    privacy.write_json(tmp_path / "shutdown_evidence.json", payload)


@pytest.mark.parametrize("outcomes,forced,terminated,killed,exited", [
    ([0], False, False, False, True),
    (["timeout", 0], True, True, False, True),
    (["timeout", "timeout", 0], True, True, True, True),
    (["timeout", "timeout", "timeout"], True, True, True, False),
])
def test_escalation_finalizes_every_path(monkeypatch, tmp_path, outcomes, forced, terminated, killed, exited):
    prepare_child_proof(tmp_path)
    process = Process(outcomes)
    joined, audits = [], []
    readers = [SimpleNamespace(ident=1, join=lambda timeout: joined.append(timeout), is_alive=lambda: False) for _ in range(2)]
    monkeypatch.setattr(supervisor, "no_ross_runtime_remains", lambda *args: True)
    def audit():
        audits.append("audit")
        return {"query_completed": True, "disconnected": True}
    monkeypatch.setattr(supervisor, "final_broker_audit", audit)
    result = supervisor.stop_and_finalize(process, readers, [], tmp_path)
    assert result == (2 if forced else 0)
    assert process.calls.count(("terminate",)) == int(terminated)
    assert process.calls.count(("kill",)) == int(killed)
    assert [call[1] for call in process.calls if call[0] == "wait"] == [60, 15, 15][:len(outcomes)]
    assert joined == [15, 15]
    assert process.stdout.closed and process.stderr.closed
    state = json.loads((tmp_path / "supervisor_shutdown.json").read_text())
    assert state["forced"] is forced
    assert state["runtime_process_exited"] is exited
    assert audits == ["audit"]
    assert (tmp_path / "FINAL_REPORT.md").exists()
    if forced:
        assert "certification: FAIL" in (tmp_path / "FINAL_REPORT.md").read_text()
    if not exited:
        terminal = json.loads((tmp_path / "terminal_evidence.json").read_text())
        assert not next(e["completed"] for e in terminal["events"] if e["event"] == "RUNTIME_PROCESS_EXITED")
        assert next(e["completed"] for e in terminal["events"] if e["event"] == "NO_ROSS_RUNTIME")
        assert state["surviving_pid"] == process.pid
    assert "DU" + "987654321" not in (tmp_path / "supervisor_shutdown.json").read_text()


@pytest.mark.parametrize("failure", ["capture", "join", "alive"])
def test_reader_failure_keeps_callbacks_and_blocks_certification(monkeypatch, tmp_path, failure):
    prepare_child_proof(tmp_path)
    process = Process([0])
    joined = []
    def join(timeout):
        if failure == "join":
            raise OSError("private detail")
    readers = [SimpleNamespace(ident=1, join=join, is_alive=lambda: failure == "alive"),
               SimpleNamespace(ident=2, join=lambda timeout: joined.append(True), is_alive=lambda: False)]
    monkeypatch.setattr(supervisor, "no_ross_runtime_remains", lambda *args: True)
    audits = []
    monkeypatch.setattr(supervisor, "final_broker_audit", lambda: audits.append(True) or {"query_completed": True, "disconnected": True})
    assert supervisor.stop_and_finalize(process, readers, ["capture failed"] if failure == "capture" else [], tmp_path) == 2
    assert joined == [True]
    assert audits == [True]
    assert "certification: FAIL" in (tmp_path / "FINAL_REPORT.md").read_text()


def test_remaining_runtime_keeps_audit_and_blocks_certification(monkeypatch, tmp_path):
    prepare_child_proof(tmp_path)
    monkeypatch.setattr(supervisor, "no_ross_runtime_remains", lambda *args: False)
    audits = []
    monkeypatch.setattr(supervisor, "final_broker_audit", lambda: audits.append(True) or {"query_completed": True, "disconnected": True})
    assert supervisor.stop_and_finalize(Process([0]), [], [], tmp_path) == 2
    assert audits == [True]


def test_clean_preflight_reaches_mock_child_and_finalization(monkeypatch, tmp_path):
    from scripts.certification import pr1040_real_readonly_runtime_observation_adapter as adapter
    mock_git(monkeypatch)
    monkeypatch.setattr(supervisor, "install_console_protection", lambda: None)
    monkeypatch.setattr(adapter, "build_safe_readonly_env", lambda: {})
    # Restore environment keys set by main after the mocked child exits.
    monkeypatch.setenv("PR1090_EVIDENCE_DIR", "")
    monkeypatch.setenv("PR1090_STOP_FILE", "")
    output = tmp_path / "evidence"
    created = []
    def popen(*args, **kwargs):
        created.append(True)
        prepare_child_proof(output)
        return Process([0, 0])
    monkeypatch.setattr(supervisor.subprocess, "Popen", popen)
    monkeypatch.setattr(supervisor, "SupervisedProcess", lambda launcher, *args, **kwargs: launcher)
    monkeypatch.setattr(supervisor, "no_ross_runtime_remains", lambda *args: True)
    monkeypatch.setattr(supervisor, "final_broker_audit", lambda: {"query_completed": True, "disconnected": True})
    assert supervisor.main(["--seconds", "1", "--output", str(output), "--expected-commit", HEAD]) == 0
    assert created == [True]
    assert "certification: PASS" in (output / "FINAL_REPORT.md").read_text()


def test_terminal_writer_failure_still_attempts_failed_report(monkeypatch, tmp_path):
    process = Process(["timeout", "timeout", "timeout"])
    monkeypatch.setattr(supervisor, "complete_after_process_exit", lambda *args: (_ for _ in ()).throw(OSError("private error")))
    assert supervisor.stop_and_finalize(process, [], [], tmp_path) == 2
    assert "certification: FAIL" in (tmp_path / "FINAL_REPORT.md").read_text()
    state = json.loads((tmp_path / "supervisor_shutdown.json").read_text())
    assert state["errors"][-1] == {"stage": "terminal_finalization", "type": "OSError"}


def test_hook_ordinary_exception_is_recorded_and_next_hook_runs():
    proof = shutdown.ShutdownEvidence()
    failure = ValueError("ordinary hook failure")
    def fail():
        raise failure
    assert proof.attempt("failed", fail) is None
    assert proof.hooks[0] == {
        "hook": "failed", "attempted": True, "completed": False,
        "error_type": "ValueError", "error": "ordinary hook failure",
    }
    assert proof.events[0]["error_type"] == "ValueError"
    assert proof.attempt("next", lambda: "completed") == "completed"
    assert proof.hooks[1]["completed"] is True


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_hook_process_control_exception_propagates_without_failure_conversion(exception_type):
    proof = shutdown.ShutdownEvidence()
    interrupt = exception_type()
    def stop():
        raise interrupt
    with pytest.raises(exception_type) as caught:
        proof.attempt("interrupted", stop)
    assert caught.value is interrupt
    assert proof.hooks == [{"hook": "interrupted", "attempted": True, "completed": False}]
    assert proof.events[0]["completed"] is False
    assert "error_type" not in proof.events[0]
    assert "error" not in proof.events[0]


@pytest.mark.parametrize("second_interrupt", [False, True])
def test_run_loop_first_interrupt_graceful_second_interrupt_panic(monkeypatch, tmp_path, second_interrupt):
    from src.core.stop_controller import StopMode

    instance, called = fake_orchestrator(monkeypatch)
    instance._clean_start_ready_for_trading = True
    instance._pipeline_runtime_counts = {}
    monkeypatch.delenv("PR1090_STOP_FILE", raising=False)
    monkeypatch.setenv("PR1090_EVIDENCE_DIR", str(tmp_path))
    emitted = []
    instance.event_collector.emit = lambda **kwargs: emitted.append(kwargs["event_type"])

    # Inject the first interrupt inside the real loop's try boundary, before
    # market/session work. The real handler and stop controller remain in use.
    original_is_stopping = instance.stop_controller.is_stop_requested
    boundary_calls = []
    def first_interrupt():
        boundary_calls.append(True)
        if len(boundary_calls) == 1:
            raise KeyboardInterrupt
        return original_is_stopping()
    monkeypatch.setattr(instance.stop_controller, "is_stop_requested", first_interrupt)

    interrupted_proofs = []
    if second_interrupt:
        def interrupt_hook():
            called.append("ops_summary")
            assert instance.stop_controller.stop_mode() == StopMode.GRACEFUL
            interrupted_proofs.append(instance.shutdown_evidence)
            raise KeyboardInterrupt
        instance._emit_ops_summary = interrupt_hook

    instance.run_forever(cycle_sleep_seconds=0, max_cycles=0)

    assert instance._shutdown_finished is True
    proof = instance.shutdown_evidence.payload()
    if second_interrupt:
        assert instance.stop_controller.stop_mode() == StopMode.PANIC
        assert instance.stop_controller.stop_reason() == "KeyboardInterrupt (escalation)"
        assert called == ["ops_summary", "execution_engine.shutdown"]
        assert emitted == ["SHUTDOWN_REQUESTED", "SHUTDOWN_STARTED", "PANIC_STOP_TRIGGERED"]
        abandoned = interrupted_proofs[0]
        assert abandoned.hooks == [{"hook": "ops_summary", "attempted": True, "completed": False}]
        assert not any(row["event"] in {"SHUTDOWN_COMPLETE", "TERMINAL_FLUSHED"} for row in abandoned.events)
        assert not any(row["event"] in {"GRACEFUL_STOP_REQUESTED", "TERMINAL_FLUSHED"} for row in proof["events"])
        assert next(row for row in proof["events"] if row["event"] == "SHUTDOWN_COMPLETE")["mode"] == "PANIC"
        assert not (tmp_path / "shutdown_evidence.json").exists()
        # Even an observed zero exit cannot certify the missing graceful proof.
        result = shutdown.complete_after_process_exit(
            tmp_path, SimpleNamespace(pid=999999, poll=lambda: 0),
            lambda: True, lambda: {"query_completed": True, "disconnected": True})
        assert result["passed"] is False
        assert "certification: FAIL" in (tmp_path / "FINAL_REPORT.md").read_text()
    else:
        assert instance.stop_controller.stop_mode() == StopMode.GRACEFUL
        assert instance.stop_controller.stop_reason() == "KeyboardInterrupt"
        assert called == list(shutdown.REQUIRED_HOOKS)
        assert "PANIC_STOP_TRIGGERED" not in emitted
        saved = json.loads((tmp_path / "shutdown_evidence.json").read_text())
        assert saved["events"][-1]["event"] == "TERMINAL_FLUSHED"
        assert all(row["completed"] for row in saved["hooks"])


@pytest.mark.parametrize("failure", [RuntimeError, OSError])
def test_shutdown_event_failure_is_truthful_and_cleanup_continues(monkeypatch, tmp_path, failure):
    from src.core.stop_controller import StopMode
    instance, called = fake_orchestrator(monkeypatch)
    monkeypatch.setenv("PR1090_EVIDENCE_DIR", str(tmp_path))
    def emit(**kwargs):
        raise failure("sink unavailable")
    instance.event_collector.emit = emit
    instance._shutdown(StopMode.GRACEFUL)
    assert called == list(shutdown.REQUIRED_HOOKS)
    proof = json.loads((tmp_path / "shutdown_evidence.json").read_text())
    failures = [row for row in proof["hooks"] if row["hook"].startswith("event_collector.SHUTDOWN_")]
    assert failures and all(row["attempted"] and not row["completed"] and row["error_type"] == failure.__name__ for row in failures)
    assert next(row for row in proof["events"] if row["event"] == "SHUTDOWN_COMPLETE")["completed"] is False
    assert not shutdown.validate_terminal(proof)["passed"]


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_event_sink_control_exceptions_propagate(monkeypatch, exception_type):
    from src.core.stop_controller import StopMode
    instance, called = fake_orchestrator(monkeypatch)
    def emit(**kwargs):
        raise exception_type
    instance.event_collector.emit = emit
    with pytest.raises(exception_type):
        instance._shutdown(StopMode.GRACEFUL)
    assert called == []
    assert instance.shutdown_evidence.hooks == []
    assert not getattr(instance, "_shutdown_finished", False)


@pytest.mark.parametrize("event", ["SHUTDOWN_STARTED", "SHUTDOWN_HOOK_FAILED", "SHUTDOWN_COMPLETE"])
@pytest.mark.parametrize("boundary", ["inner", "bounded", "finalizer"])
def test_event_interrupt_reaches_panic_at_each_shutdown_boundary(monkeypatch, tmp_path, event, boundary):
    from src.core.stop_controller import StopMode
    instance, called = fake_orchestrator(monkeypatch)
    instance._clean_start_ready_for_trading = True
    instance._pipeline_runtime_counts = {}
    monkeypatch.delenv("PR1090_STOP_FILE", raising=False)
    monkeypatch.setenv("PR1090_EVIDENCE_DIR", str(tmp_path))
    if boundary == "inner":
        instance.stop_controller.transition_keyboard_interrupt()
    elif boundary == "finalizer":
        instance._run_forever_inner = lambda *args: None
    if event == "SHUTDOWN_HOOK_FAILED":
        instance._emit_ops_summary = lambda: (_ for _ in ()).throw(RuntimeError("hook failure"))
    seen, interrupted = [], []
    def emit(**kwargs):
        if kwargs["event_type"] == event and not interrupted:
            interrupted.append(instance.shutdown_evidence)
            raise KeyboardInterrupt
        seen.append(kwargs["event_type"])
    instance.event_collector.emit = emit
    instance.run_forever(cycle_sleep_seconds=0, max_cycles=0)
    assert interrupted
    assert instance.stop_controller.stop_mode() == StopMode.PANIC
    assert "PANIC_STOP_TRIGGERED" in seen
    assert "SHUTDOWN_COMPLETE" not in seen
    assert not (tmp_path / "shutdown_evidence.json").exists()
    assert not any(row["event"] == "TERMINAL_FLUSHED" for row in interrupted[0].events)
    assert instance.shutdown_evidence.events[0]["event"] == "PANIC_STOP_REQUESTED"
    assert not shutdown.validate_terminal(instance.shutdown_evidence.payload())["passed"]


@pytest.mark.parametrize("args", [
    ["python", "src/main.py"], ["python3", "/work/project/src/main.py"],
    ["/opt/venv/bin/python3.12", "-u", "-B", "src/main.py"],
    ["python", "-W", "ignore", "-X", "utf8", "-Iu", "-m", "src.main"],
    ["python", "--", "./src/main.py"],
    ["python3", "-um", "src.main"],
    ["python", "src/../src/main.py"],
    ["PYTHON.EXE", r"C:\repo\SRC\MAIN.PY"],
    [r"C:\Program Files\Python\python.exe", "-u", "-m", "src.main"],
    [r"C:\venv\pythonw.exe", r"C:\repo\src\main.py"],
    ["python", "scripts/certification/pr1040_real_readonly_runtime_observation_adapter.py"],
    ["python", "-m", "scripts.certification.pr1040_real_readonly_runtime_observation_adapter"],
])
def test_structured_runtime_entrypoints(args):
    assert supervisor.is_ross_runtime(args)


@pytest.mark.parametrize("args", [
    ["pytest", "src/main.py"], ["python", "-m", "pytest", "src/main.py"],
    ["python", "pytest.py", "src/main.py"], ["code", "src/main.py"],
    ["bash", "-c", "python src/main.py"], ["python", "-c", "print('src/main.py')"],
    ["python", "log_reader.py", "--text", "src.main"],
    ["python", "scripts/certification/pr1090_terminal_observation_supervisor.py", "--output", "src/main.py"],
    ["python", "-m", "scripts.certification.pr1090_terminal_observation_supervisor"],
    ["python", "-uc", "print(123)"], ["python", "src/main.py.log"], ["python", "-W", "src/main.py", "unrelated.py"],
])
def test_textual_mentions_and_supervisor_are_not_runtime(args):
    assert not supervisor.is_ross_runtime(args)


@pytest.mark.parametrize("args", [
    [r"C:\Program Files\Python\python.exe", "-u", r"C:\a b\src\main.py"],
    ["python.exe", "-m", "src.main", 'quoted "argument"', "trailing\\"],
    ["python.exe", "-c", 'print("src/main.py")'],
])
def test_windows_argv_roundtrip_is_platform_independent(args):
    assert supervisor.split_windows_command_line(subprocess.list2cmdline(args)) == args


def write_proc_entry(root, pid, args):
    path = root / str(pid)
    path.mkdir()
    (path / "cmdline").write_bytes(b"\0".join(arg.encode() for arg in args) + b"\0")
    return path


@pytest.mark.parametrize("runtime", [True, False])
def test_posix_inventory_preserves_pid_and_redacted_argv(monkeypatch, tmp_path, runtime):
    monkeypatch.setattr(supervisor.os, "getpid", lambda: 100)
    write_proc_entry(tmp_path, 100, ["python", "scripts/certification/pr1090_terminal_observation_supervisor.py"])
    args = ["python3", "-u", "/repo/src/main.py", "DU" + "987654321"] if runtime else ["python", "-m", "pytest", "src/main.py"]
    write_proc_entry(tmp_path, 200, args)
    evidence = supervisor.runtime_inventory(platform="posix", proc_root=tmp_path)
    assert evidence["completed"]
    assert len(evidence["runtimes"]) == int(runtime)
    if runtime:
        assert evidence["runtimes"][0]["pid"] == 200
        assert evidence["runtimes"][0]["argv"][-1] == "REDACTED"


@pytest.mark.parametrize("problem", ["missing_root", "empty", "missing_self", "missing_cmdline"])
def test_posix_incomplete_inventory_fails_closed(monkeypatch, tmp_path, problem):
    monkeypatch.setattr(supervisor.os, "getpid", lambda: 100)
    root = tmp_path
    if problem == "missing_root":
        root = tmp_path / "absent"
    elif problem == "missing_self":
        write_proc_entry(root, 200, ["python", "other.py"])
    elif problem == "missing_cmdline":
        write_proc_entry(root, 100, ["python", "supervisor.py"])
        (root / "200").mkdir()
    result = supervisor.runtime_inventory(platform="posix", proc_root=root)
    assert result["completed"] is False
    assert result["error_type"]


def test_windows_inventory_uses_structured_commands(monkeypatch):
    monkeypatch.setattr(supervisor.os, "getpid", lambda: 100)
    rows = [
        {"ProcessId": 100, "CommandLine": "python.exe scripts/certification/pr1090_terminal_observation_supervisor.py"},
        {"ProcessId": 200, "CommandLine": '"C:\\Program Files\\Python\\python.exe" -u "C:\\repo\\src\\main.py"'},
        {"ProcessId": 300, "CommandLine": 'python.exe -m pytest src/main.py'},
    ]
    monkeypatch.setattr(supervisor.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps(rows)))
    evidence = supervisor.runtime_inventory(platform="nt")
    assert evidence["completed"]
    assert [row["pid"] for row in evidence["runtimes"]] == [200]


@pytest.mark.parametrize("stdout", ["", "null", "[]", "{}", '[{"ProcessId":100,"CommandLine":null}]'])
def test_windows_unreadable_inventory_fails_closed(monkeypatch, stdout):
    monkeypatch.setattr(supervisor.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=stdout))
    assert supervisor.runtime_inventory(platform="nt")["completed"] is False


@pytest.mark.parametrize("completed,runtimes", [(False, []), (True, [{"pid": 200, "argv": ["python", "src/main.py"]}])])
def test_inventory_failure_keeps_audit_and_persists_evidence(monkeypatch, tmp_path, completed, runtimes):
    prepare_child_proof(tmp_path)
    evidence = {"completed": completed, "runtimes": runtimes}
    monkeypatch.setattr(supervisor, "runtime_inventory", lambda: evidence)
    audits = []
    monkeypatch.setattr(supervisor, "final_broker_audit", lambda: audits.append(True) or {"query_completed": True, "disconnected": True})
    assert supervisor.stop_and_finalize(Process([0]), [], [], tmp_path) == 2
    assert audits == [True]
    assert json.loads((tmp_path / "runtime_inventory.json").read_text()) == evidence
    assert "certification: FAIL" in (tmp_path / "FINAL_REPORT.md").read_text()


def test_panic_marker_rejects_otherwise_complete_terminal_proof(tmp_path):
    prepare_child_proof(tmp_path)
    payload = json.loads((tmp_path / "shutdown_evidence.json").read_text())
    payload["events"][0]["mode"] = "PANIC"
    privacy.write_json(tmp_path / "shutdown_evidence.json", payload)
    result = shutdown.complete_after_process_exit(tmp_path, SimpleNamespace(pid=Process.pid, poll=lambda: 0),
        lambda: True, lambda: {"query_completed": True, "disconnected": True})
    assert not result["passed"]
    assert "PANIC cannot certify graceful shutdown" in result["blockers"]


@pytest.mark.parametrize("seconds", ["nan", "inf", "-inf"])
def test_nonfinite_observation_duration_rejected(monkeypatch, tmp_path, seconds):
    monkeypatch.setattr(supervisor, "require_clean_certification_worktree", lambda *args: pytest.fail("preflight reached"))
    with pytest.raises(SystemExit):
        supervisor.main(["--seconds=" + seconds, "--output", str(tmp_path), "--expected-commit", HEAD])


@pytest.mark.parametrize("mode", ["GRACEFUL", "PANIC"])
def test_entrypoint_panic_exit_is_nonzero_and_never_claims_graceful(mode, capsys):
    from src.main import _report_shutdown
    if mode == "PANIC":
        with pytest.raises(SystemExit) as caught:
            _report_shutdown(mode)
        assert caught.value.code == 2
        assert "gracefully" not in capsys.readouterr().out
    else:
        _report_shutdown(mode)
        assert "Exiting gracefully" in capsys.readouterr().out


def test_panic_exit_rejects_preexisting_graceful_proof(tmp_path):
    prepare_child_proof(tmp_path)
    result = shutdown.complete_after_process_exit(tmp_path, SimpleNamespace(pid=Process.pid, poll=lambda: 2),
        lambda: True, lambda: {"query_completed": True, "disconnected": True})
    assert not result["passed"]
    assert "Runtime did not exit successfully" in result["blockers"]


def test_supervisor_error_rejects_otherwise_complete_terminal_proof(tmp_path):
    prepare_child_proof(tmp_path)
    payload = json.loads((tmp_path / "shutdown_evidence.json").read_text())
    payload["supervisor_error"] = "KeyboardInterrupt"
    privacy.write_json(tmp_path / "shutdown_evidence.json", payload)
    result = shutdown.complete_after_process_exit(tmp_path, SimpleNamespace(pid=Process.pid, poll=lambda: 0),
        lambda: True, lambda: {"query_completed": True, "disconnected": True})
    assert not result["passed"]
    assert "Supervisor finalization failed" in result["blockers"]


@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_partial_final_query_failure_clears_success_and_disconnects(monkeypatch, failure):
    from src.adapters.brokers.ibkr import ibkr_client
    from src.config import runtime_config
    calls = []
    class Orders:
        def __len__(self):
            raise failure("query result unavailable")
    class Client:
        def __init__(self, **kwargs):
            self.connected = False
            self._thread = SimpleNamespace(is_alive=lambda: self.connected)
            self._open_orders_event = SimpleNamespace(clear=lambda: None, wait=lambda timeout: True)
        def connect(self):
            self.connected = True
        def reqAllOpenOrders(self):
            self._open_orders_snapshot = Orders()
        def disconnect(self):
            calls.append("disconnect")
            self.connected = False
        def is_connected(self):
            return self.connected
    monkeypatch.setattr(ibkr_client, "IbkrClient", Client)
    monkeypatch.setattr(runtime_config, "resolve_ibkr_connection", lambda: ("fake", 0, 123, "READ_ONLY"))
    result = supervisor.final_broker_audit()
    assert result["query_completed"] is False
    assert result["error"] == failure.__name__ + ": query result unavailable"
    assert result["disconnected"] is True
    assert calls == ["disconnect"]


@pytest.mark.parametrize("boundary", ["inner", "outer", "finalizer"])
@pytest.mark.parametrize("stage", [
    "before_publication", "publication", "after_transition", "event",
    "format", "print", "strategy", "hook", "selection", "shutdown",
    "evidence", "terminal",
])
def test_shutdown_transaction_injection_matrix(monkeypatch, tmp_path, boundary, stage):
    import builtins
    from src.core import stop_controller
    from src import main as entrypoint

    instance, called = fake_orchestrator(monkeypatch)
    controller = instance.stop_controller
    instance._clean_start_ready_for_trading = True
    monkeypatch.delenv("PR1090_STOP_FILE", raising=False)
    monkeypatch.setenv("PR1090_EVIDENCE_DIR", str(tmp_path))
    injected, summaries, invocations = [], [], []
    def inject(point):
        if point == stage and not injected:
            injected.append(point)
            raise KeyboardInterrupt

    real_transition = controller.transition_keyboard_interrupt
    def transition():
        inject("before_publication")
        mode = real_transition()
        inject("after_transition")
        return mode
    monkeypatch.setattr(controller, "transition_keyboard_interrupt", transition)
    real_state = stop_controller._StopState
    def state(*args, **kwargs):
        inject("publication")
        return real_state(*args, **kwargs)
    monkeypatch.setattr(stop_controller, "_StopState", state)

    class Counts(dict):
        def get(self, *args):
            inject("format")
            return super().get(*args)
    instance._pipeline_runtime_counts = Counts()
    real_print = builtins.print
    def printing(*args, **kwargs):
        if args and str(args[0]).startswith("[SUMMARY]"):
            summaries.append("print")
            inject("print")
        return real_print(*args, **kwargs)
    monkeypatch.setattr(builtins, "print", printing)
    def strategy():
        summaries.append("strategy")
        inject("strategy")
    instance.strategy_runner = SimpleNamespace(emit_shutdown_summary=strategy)
    def emit(**kwargs):
        if kwargs["event_type"] == "SHUTDOWN_REQUESTED":
            inject("event")
        elif kwargs["event_type"] == "SHUTDOWN_STARTED":
            inject("shutdown")
    instance.event_collector.emit = emit
    real_hook = instance.learning_scheduler.on_shutdown
    def hook():
        inject("hook")
        real_hook()
    instance.learning_scheduler.on_shutdown = hook
    real_shutdown = instance._shutdown
    def finish(mode):
        inject("selection")
        invocations.append(mode)
        real_shutdown(mode)
    instance._shutdown = finish
    real_flush = shutdown.ShutdownEvidence.flush
    def flush(proof, directory):
        inject("evidence")
        return real_flush(proof, directory)
    monkeypatch.setattr(shutdown.ShutdownEvidence, "flush", flush)
    real_report = entrypoint._report_shutdown
    def report(mode):
        inject("terminal")
        real_report(mode)
    monkeypatch.setattr(entrypoint, "_report_shutdown", report)

    first = []
    def interrupt_once():
        if not first:
            first.append(True)
            raise KeyboardInterrupt
    if boundary == "outer":
        instance._run_forever_inner = lambda *args: interrupt_once()
    elif boundary == "finalizer":
        instance._run_forever_inner = lambda *args: None
        real_request = instance._request_stop
        def request(*args, **kwargs):
            interrupt_once()
            return real_request(*args, **kwargs)
        instance._request_stop = request
    else:
        real_predicate = controller.is_stop_requested
        def predicate():
            interrupt_once()
            return real_predicate()
        monkeypatch.setattr(controller, "is_stop_requested", predicate)

    with pytest.raises(SystemExit) as result:
        entrypoint._run_and_report(instance, 0)
    assert result.value.code == 2
    assert injected == [stage]
    assert controller.stop_mode() == stop_controller.StopMode.PANIC
    assert invocations[-1] == stop_controller.StopMode.PANIC
    assert summaries.count("print") <= 1
    assert summaries.count("strategy") <= 1
    assert instance.shutdown_evidence.events[0]["event"] == "PANIC_STOP_REQUESTED"
    assert not shutdown.validate_terminal(instance.shutdown_evidence.payload())["passed"]
    controller.request_stop(stop_controller.StopMode.GRACEFUL, "late", "test")
    assert controller.stop_mode() == stop_controller.StopMode.PANIC
    # Completed PANIC handling is idempotent and never restarts graceful work.
    completed_calls = list(called)
    instance._handle_keyboard_interrupt()
    assert called == completed_calls
    assert invocations[-1] == stop_controller.StopMode.PANIC


@pytest.mark.parametrize("interrupt", [False, True])
def test_shutdown_transaction_normal_completion(monkeypatch, tmp_path, interrupt):
    from src.core.stop_controller import StopMode
    from src.main import _run_and_report
    instance, called = fake_orchestrator(monkeypatch)
    instance._clean_start_ready_for_trading = True
    instance._pipeline_runtime_counts = {}
    monkeypatch.delenv("PR1090_STOP_FILE", raising=False)
    monkeypatch.setenv("PR1090_EVIDENCE_DIR", str(tmp_path))
    if interrupt:
        def first(*args):
            raise KeyboardInterrupt
        instance._run_forever_inner = first
    _run_and_report(instance, 0)
    assert instance.stop_controller.stop_mode() == StopMode.GRACEFUL
    assert called == list(shutdown.REQUIRED_HOOKS)
    assert instance.stop_controller.stop_reason() == ("KeyboardInterrupt" if interrupt else "Run loop complete")
    assert instance.shutdown_evidence.events[-1]["event"] == "TERMINAL_FLUSHED"


def test_shutdown_transaction_rejects_stale_graceful_selection(monkeypatch):
    from src.core.stop_controller import StopMode
    instance, called = fake_orchestrator(monkeypatch)
    instance.stop_controller.request_stop(StopMode.PANIC, "existing panic", "Risk")
    instance._shutdown(StopMode.GRACEFUL)
    assert instance.stop_controller.stop_mode() == StopMode.PANIC
    assert instance.stop_controller.stop_reason() == "existing panic"
    assert called == ["execution_engine.shutdown"]
    assert instance.shutdown_evidence.events[0]["event"] == "PANIC_STOP_REQUESTED"
    instance._shutdown(StopMode.GRACEFUL)
    assert called == ["execution_engine.shutdown"]


def test_structural_transition_is_monotonic_and_reentrant(monkeypatch):
    from src.core.stop_controller import StopController, StopMode

    controller = StopController()
    monkeypatch.setattr(controller, "is_stop_requested", lambda: pytest.fail("pre-latch predicate"))
    monkeypatch.setattr(controller, "stop_mode", lambda: pytest.fail("pre-latch mode query"))
    assert controller._lock.acquire(blocking=False)
    acquired_again = controller._lock.acquire(blocking=False)
    try:
        assert acquired_again, "controller lock must support reentry"
        assert controller.transition_keyboard_interrupt() == StopMode.GRACEFUL
        assert controller.stop_reason() == "KeyboardInterrupt"
        assert controller.stop_source() == "Main"
        assert controller.transition_keyboard_interrupt() == StopMode.PANIC
        controller.request_stop(StopMode.GRACEFUL, "late", "test")
        assert controller.transition_keyboard_interrupt() == StopMode.PANIC
        assert controller.stop_reason() == "KeyboardInterrupt (escalation)"
    finally:
        if acquired_again:
            controller._lock.release()
        controller._lock.release()


@pytest.mark.parametrize("prior", ["GRACEFUL", "PANIC"])
def test_structural_existing_stop_precedence(prior):
    from src.core.stop_controller import StopController, StopMode

    controller = StopController()
    controller.request_stop(StopMode(prior), "risk stop", "Risk")
    assert controller.transition_keyboard_interrupt() == StopMode.PANIC
    expected = ("risk stop", "Risk") if prior == "PANIC" else ("KeyboardInterrupt (escalation)", "Main")
    assert (controller.stop_reason(), controller.stop_source()) == expected
    controller.request_stop(StopMode.GRACEFUL, "late", "test")
    assert controller.stop_mode() == StopMode.PANIC
    assert (controller.stop_reason(), controller.stop_source()) == expected


@pytest.mark.parametrize("stage", ["before", "publication", "after"])
def test_structural_interrupted_transition_panics(monkeypatch, tmp_path, stage):
    from src.core import stop_controller
    from src.main import _report_shutdown

    instance, called = fake_orchestrator(monkeypatch)
    controller = instance.stop_controller
    monkeypatch.setenv("PR1090_EVIDENCE_DIR", str(tmp_path))
    real_transition = controller.transition_keyboard_interrupt
    real_predicate = controller.is_stop_requested
    monkeypatch.setattr(controller, "is_stop_requested", lambda: pytest.fail("pre-latch predicate"))
    emitted = []
    instance.event_collector.emit = lambda **kwargs: emitted.append(kwargs["event_type"])
    class NoSummary(dict):
        def get(self, *args):
            pytest.fail("PANIC must skip summaries")
    instance._pipeline_runtime_counts = NoSummary()
    instance.strategy_runner = SimpleNamespace(emit_shutdown_summary=lambda: pytest.fail("PANIC summary callback"))
    if stage == "publication":
        real_state = stop_controller._StopState
        injected = []
        def state(*args, **kwargs):
            if not injected:
                injected.append(True)
                raise KeyboardInterrupt
            return real_state(*args, **kwargs)
        monkeypatch.setattr(stop_controller, "_StopState", state)
    else:
        def transition():
            if stage == "after":
                real_transition()
            raise KeyboardInterrupt
        monkeypatch.setattr(controller, "transition_keyboard_interrupt", transition)
    instance._handle_keyboard_interrupt()
    assert controller.stop_mode() == stop_controller.StopMode.PANIC
    assert controller.stop_reason() == "KeyboardInterrupt (escalation)"
    assert controller.stop_source() == "Main"
    assert emitted == ["PANIC_STOP_TRIGGERED"]
    monkeypatch.setattr(controller, "is_stop_requested", real_predicate)
    instance._shutdown(controller.stop_mode())
    assert called == ["execution_engine.shutdown"]
    controller.request_stop(stop_controller.StopMode.GRACEFUL, "late", "test")
    with pytest.raises(SystemExit) as result:
        _report_shutdown(controller.stop_mode())
    assert result.value.code == 2
    assert not shutdown.validate_terminal(instance.shutdown_evidence.payload())["passed"]
    assert not (tmp_path / "shutdown_evidence.json").exists()


@pytest.mark.parametrize("interrupt_at", [None, "format", "print", "strategy", "evidence"])
def test_interrupt_latched_before_summary_and_reentrant_interrupt_panics(monkeypatch, tmp_path, interrupt_at):
    import builtins
    from src.core.stop_controller import StopMode
    from src.main import _report_shutdown

    instance, called = fake_orchestrator(monkeypatch)
    instance._clean_start_ready_for_trading = True
    monkeypatch.delenv("PR1090_STOP_FILE", raising=False)
    monkeypatch.setenv("PR1090_EVIDENCE_DIR", str(tmp_path))
    order, injected, emitted = [], [], []
    real_request = instance.stop_controller.request_stop
    def request(mode, reason, source):
        real_request(mode, reason, source)
        order.append(("latched", instance.stop_controller.stop_mode(), reason))
    monkeypatch.setattr(instance.stop_controller, "request_stop", request)

    def summary_work(stage):
        assert instance.stop_controller.is_stop_requested()
        assert instance.stop_controller.stop_mode() == StopMode.GRACEFUL
        assert instance.stop_controller.stop_reason() == "KeyboardInterrupt"
        assert instance.stop_controller.stop_source() == "Main"
        order.append((stage, StopMode.GRACEFUL))
        if stage == interrupt_at and not injected:
            injected.append(stage)
            raise KeyboardInterrupt

    class Counts(dict):
        def get(self, *args):
            summary_work("format")
            return super().get(*args)
    instance._pipeline_runtime_counts = Counts()
    instance.strategy_runner = SimpleNamespace(emit_shutdown_summary=lambda: summary_work("strategy"))
    real_print = builtins.print
    def printing(*args, **kwargs):
        if args and str(args[0]).startswith("[SUMMARY]"):
            summary_work("print")
        return real_print(*args, **kwargs)
    monkeypatch.setattr(builtins, "print", printing)
    def emit(**kwargs):
        mode = instance.stop_controller.stop_mode()
        emitted.append((kwargs["event_type"], mode, instance.stop_controller.stop_reason()))
        if kwargs["event_type"] == "SHUTDOWN_REQUESTED":
            summary_work("evidence")
    instance.event_collector.emit = emit

    # First Ctrl-C enters the real inner-loop handler before any cycle work.
    real_is_stopping = instance.stop_controller.is_stop_requested
    first = []
    def boundary():
        if not first:
            first.append(True)
            raise KeyboardInterrupt
        return real_is_stopping()
    monkeypatch.setattr(instance.stop_controller, "is_stop_requested", boundary)
    instance.run_forever(cycle_sleep_seconds=0, max_cycles=0)

    assert order[0] == ("latched", StopMode.GRACEFUL, "KeyboardInterrupt")
    assert emitted[0] == ("SHUTDOWN_REQUESTED", StopMode.GRACEFUL, "KeyboardInterrupt")
    if interrupt_at is None:
        assert not injected
        assert instance.stop_controller.stop_mode() == StopMode.GRACEFUL
        assert called == list(shutdown.REQUIRED_HOOKS)
        _report_shutdown(instance.stop_controller.stop_mode())
        saved = json.loads((tmp_path / "shutdown_evidence.json").read_text())
        assert saved["events"][-1]["event"] == "TERMINAL_FLUSHED"
        assert all(row["completed"] for row in saved["hooks"])
    else:
        assert injected == [interrupt_at]
        assert instance.stop_controller.stop_mode() == StopMode.PANIC
        assert instance.stop_controller.stop_reason() == "KeyboardInterrupt (escalation)"
        assert called == ["execution_engine.shutdown"]
        assert ("PANIC_STOP_TRIGGERED", StopMode.PANIC, "KeyboardInterrupt (escalation)") in emitted
        instance._request_stop(StopMode.GRACEFUL, reason="late graceful request", source="test")
        assert instance.stop_controller.stop_mode() == StopMode.PANIC
        assert instance.stop_controller.stop_reason() == "KeyboardInterrupt (escalation)"
        with pytest.raises(SystemExit) as exit_result:
            _report_shutdown(instance.stop_controller.stop_mode())
        assert exit_result.value.code == 2
        assert instance.shutdown_evidence.events[0]["event"] == "PANIC_STOP_REQUESTED"
        assert not (tmp_path / "shutdown_evidence.json").exists()
        assert not shutdown.validate_terminal(instance.shutdown_evidence.payload())["passed"]
        # Further interrupts retain PANIC without repeating nonessential summaries.
        summary_count = len([row for row in order if row[0] in {"format", "print", "strategy"}])
        instance._handle_keyboard_interrupt()
        assert instance.stop_controller.stop_mode() == StopMode.PANIC
        assert len([row for row in order if row[0] in {"format", "print", "strategy"}]) == summary_count
