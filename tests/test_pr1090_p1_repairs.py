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
        def invoke():
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
        assert process.poll() is not None
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
    assert audits == ([] if forced else ["audit"])
    assert (tmp_path / "FINAL_REPORT.md").exists()
    if forced:
        assert "certification: FAIL" in (tmp_path / "FINAL_REPORT.md").read_text()
    if not exited:
        terminal = json.loads((tmp_path / "terminal_evidence.json").read_text())
        assert not next(e["completed"] for e in terminal["events"] if e["event"] == "RUNTIME_PROCESS_EXITED")
        assert not next(e["completed"] for e in terminal["events"] if e["event"] == "NO_ROSS_RUNTIME")
        assert state["surviving_pid"] == process.pid
    assert "DU" + "987654321" not in (tmp_path / "supervisor_shutdown.json").read_text()


@pytest.mark.parametrize("failure", ["capture", "join", "alive"])
def test_reader_failure_keeps_cleanup_and_blocks_audit(monkeypatch, tmp_path, failure):
    prepare_child_proof(tmp_path)
    process = Process([0])
    joined = []
    def join(timeout):
        if failure == "join":
            raise OSError("private detail")
    readers = [SimpleNamespace(ident=1, join=join, is_alive=lambda: failure == "alive"),
               SimpleNamespace(ident=2, join=lambda timeout: joined.append(True), is_alive=lambda: False)]
    monkeypatch.setattr(supervisor, "no_ross_runtime_remains", lambda *args: True)
    monkeypatch.setattr(supervisor, "final_broker_audit", lambda: pytest.fail("audit after reader failure"))
    assert supervisor.stop_and_finalize(process, readers, ["capture failed"] if failure == "capture" else [], tmp_path) == 2
    assert joined == [True]
    assert "certification: FAIL" in (tmp_path / "FINAL_REPORT.md").read_text()


def test_remaining_runtime_blocks_audit(monkeypatch, tmp_path):
    prepare_child_proof(tmp_path)
    monkeypatch.setattr(supervisor, "no_ross_runtime_remains", lambda *args: False)
    monkeypatch.setattr(supervisor, "final_broker_audit", lambda: pytest.fail("audit while runtime remains"))
    assert supervisor.stop_and_finalize(Process([0]), [], [], tmp_path) == 2


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
            lambda: True, lambda: pytest.fail("audit without child exit proof"))
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
        instance._handle_keyboard_interrupt()
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
def test_inventory_blocks_audit_and_persists_evidence(monkeypatch, tmp_path, completed, runtimes):
    prepare_child_proof(tmp_path)
    evidence = {"completed": completed, "runtimes": runtimes}
    monkeypatch.setattr(supervisor, "runtime_inventory", lambda: evidence)
    monkeypatch.setattr(supervisor, "final_broker_audit", lambda: pytest.fail("audit with unsafe inventory"))
    assert supervisor.stop_and_finalize(Process([0]), [], [], tmp_path) == 2
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
            self._thread = None
            self._open_orders_event = SimpleNamespace(clear=lambda: None, wait=lambda timeout: True)
        def connect(self):
            pass
        def reqAllOpenOrders(self):
            self._open_orders_snapshot = Orders()
        def disconnect(self):
            calls.append("disconnect")
        def is_connected(self):
            return False
    monkeypatch.setattr(ibkr_client, "IbkrClient", Client)
    monkeypatch.setattr(runtime_config, "resolve_ibkr_connection", lambda: ("fake", 0, 123, "READ_ONLY"))
    result = supervisor.final_broker_audit()
    assert result["query_completed"] is False
    assert result["disconnected"] is True
    assert calls == ["disconnect"]


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
