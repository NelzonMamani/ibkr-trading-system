"""Offline identity and independent-finalization regressions; no broker or runtime."""
from __future__ import annotations

from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.certification import pr1090_terminal_observation_supervisor as supervisor
from src.ibkr import evidence_safety, mutation_audit, shutdown_evidence as shutdown
from src.runtime import process_identity as identity


COMMAND = [sys.executable, "-u", "-m", "src.main"]
CALLBACKS = {"process_inventory", "broker_audit", "artifact_validation", "mutation_validation", "terminal_verdict"}


def process_row(pid, parent, started, *, argv=None):
    return {"pid": pid, "parent_pid": parent, "creation_token": f"windows-filetime:{started}",
            "argv": list(COMMAND if argv is None else argv)}


class Launcher:
    pid = 810001
    _handle = 123

    def __init__(self):
        self.stdout, self.stderr = StringIO(), StringIO()
        self.returncode = None
        self.signals = []

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.returncode = 0
        return 0

    def terminate(self):
        self.signals.append("terminate")

    def kill(self):
        self.signals.append("kill")


class RuntimeHandle:
    def __init__(self, pid, creation, *, allow_terminate):
        self.pid, self.creation = pid, creation
        assert allow_terminate is True
        self.returncode = None
        self.signals = []
        self.closed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.returncode = 0
        return 0

    def terminate(self):
        self.signals.append("terminate")

    def kill(self):
        self.signals.append("kill")

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def isolated_counters(monkeypatch):
    monkeypatch.setattr(mutation_audit, "_counts", {"place": 0, "modify": 0, "cancel": 0})


@pytest.fixture
def owned(tmp_path, monkeypatch):
    launcher = Launcher()
    rows = {launcher.pid: process_row(launcher.pid, 1, 100),
            810002: process_row(810002, launcher.pid, 200,
                                argv=[getattr(sys, "_base_executable", sys.executable), *COMMAND[1:]])}
    path = tmp_path / "handshake.json"
    ack = tmp_path / "ack.json"
    path.write_text(json.dumps({"nonce": "unique-test-launch", "identity": rows[810002]}))
    monkeypatch.setattr(identity, "_kernel32", lambda: None)
    monkeypatch.setattr(identity, "_creation_token", lambda api, handle: "windows-filetime:100")
    reader = lambda pid, **kwargs: deepcopy(rows[pid])
    process = identity.SupervisedProcess(launcher, COMMAND, "unique-test-launch", path,
        read_identity=reader, handle_factory=RuntimeHandle, platform="nt", acknowledgement_path=ack)
    return process, rows, path, ack


def write_child_proof(tmp_path, runtime):
    proof = shutdown.ShutdownEvidence()
    proof.record("GRACEFUL_STOP_REQUESTED", completed=True)
    proof.record("SHUTDOWN_STARTED", completed=True)
    for name in shutdown.REQUIRED_HOOKS:
        proof.attempt(name, lambda: None)
    proof.record("SHUTDOWN_COMPLETE", completed=True)
    proof.record("TERMINAL_FLUSHED", completed=True)
    payload = proof.payload()
    payload.update(pid=runtime["pid"], process_identity=runtime)
    evidence_safety.write_json(tmp_path / "shutdown_evidence.json", payload)


def witnessed_process(tmp_path):
    runtime = process_row(810002, 810001, 200)
    write_child_proof(tmp_path, runtime)
    return SimpleNamespace(pid=runtime["pid"], runtime_identity=runtime, identity_verified=True,
        launcher_identity=process_row(810001, 1, 100), launcher_exit_code=0,
        lineage=[runtime], poll=lambda: 0)


def test_separate_runtime_identity_owns_exit_and_acknowledgement(owned):
    process, rows, path, ack = owned
    process.bind()
    assert process.pid == rows[810002]["pid"] != process.launcher.pid
    assert process.identity_verified is True
    assert process.runtime_identity == rows[810002]
    assert process.lineage == [rows[810002], rows[810001]]
    assert json.loads(ack.read_text()) == json.loads(path.read_text())
    process.launcher.returncode = 0
    assert process.poll() is None  # An exited launcher proves nothing about runtime exit.
    process.runtime_handle.returncode = 7
    assert process.poll() == 7
    process.close()
    assert process.runtime_handle.closed


@pytest.mark.parametrize("fault", ["wrong_nonce", "wrong_pid", "reused_runtime", "wrong_argv", "reused_launcher", "unrelated_parent", "malformed"])
def test_handshake_rejects_untrusted_or_reused_identity(owned, fault):
    process, rows, path, ack = owned
    handshake = json.loads(path.read_text())
    if fault == "wrong_nonce":
        handshake["nonce"] = "other-launch"
    elif fault == "wrong_pid":
        handshake["identity"]["pid"] = 42
    elif fault == "reused_runtime":
        rows[810002]["creation_token"] = "windows-filetime:201"
    elif fault == "wrong_argv":
        rows[810002]["argv"] = [sys.executable, "-m", "pytest", "src.main"]
        handshake["identity"] = deepcopy(rows[810002])
    elif fault == "reused_launcher":
        rows[810001]["creation_token"] = "windows-filetime:300"
    elif fault == "unrelated_parent":
        rows[810002]["parent_pid"] = 1
        handshake["identity"] = deepcopy(rows[810002])
        rows[1] = process_row(1, 0, 50)
    elif fault == "malformed":
        handshake = []
    path.write_text(json.dumps(handshake))
    with pytest.raises((RuntimeError, KeyError)):
        process.bind()
    assert not process.identity_verified
    assert not ack.exists()
    with pytest.raises(RuntimeError, match="without bound runtime identity"):
        process.terminate()
    assert process.launcher.signals == []


def test_constructor_failure_clears_partial_launcher_authority(tmp_path, monkeypatch):
    launcher = Launcher()
    def read(pid, **kwargs):
        launcher.returncode = 1
        return process_row(pid, 1, 100)
    process = identity.SupervisedProcess(launcher, COMMAND, "nonce", tmp_path / "none",
                                        read_identity=read, platform="posix")
    assert process.launcher_identity is None
    with pytest.raises(RuntimeError, match="Launcher identity unavailable"):
        process.bind()
    with pytest.raises(RuntimeError):
        process.kill()
    assert launcher.signals == []


def test_binding_budget_covers_every_lineage_read(owned, monkeypatch):
    process, rows, _, _ = owned
    clock, budgets = [0.0], []
    monkeypatch.setattr(identity.time, "monotonic", lambda: clock[0])
    def read(pid, *, timeout):
        budgets.append(timeout)
        clock[0] = 25.0 if pid == 810002 else 29.0
        return deepcopy(rows[pid])
    process.read_identity = read
    process.bind(timeout=30)
    assert budgets == [15, 5]
    assert process.identity_verified


def test_expired_metadata_read_never_acknowledges_runtime(owned, monkeypatch):
    process, rows, _, ack = owned
    clock = [0.0]
    monkeypatch.setattr(identity.time, "monotonic", lambda: clock[0])
    def read(pid, *, timeout):
        assert timeout == 1
        clock[0] = 1.1
        return deepcopy(rows[pid])
    process.read_identity = read
    with pytest.raises(RuntimeError, match="timed out"):
        process.bind(timeout=1)
    assert not process.identity_verified and not ack.exists()


def test_windows_identity_retains_handle_before_pid_metadata(monkeypatch):
    calls = []
    class Handle:
        creation_token = "windows-filetime:100"
        def __init__(self, pid):
            calls.append("open")
        def poll(self):
            calls.append("poll")
            return None
        def close(self):
            calls.append("close")
    def run(command, **kwargs):
        assert kwargs["timeout"] == 0.25
        calls.append("metadata")
        return SimpleNamespace(stdout=json.dumps({"ProcessId": 55, "ParentProcessId": 12,
                                                  "CommandLine": '"C:\\Python\\python.exe" -u -m src.main'}))
    monkeypatch.setattr(identity, "WindowsProcessHandle", Handle)
    monkeypatch.setattr(identity.subprocess, "run", run)
    result = identity.read_process_identity(55, platform="nt", timeout=0.25)
    assert calls == ["open", "poll", "metadata", "poll", "close"]
    assert result["argv"] == [r"C:\Python\python.exe", "-u", "-m", "src.main"]


def test_posix_direct_child_uses_owned_waitpid_handle(owned):
    process, rows, path, ack = owned
    process.platform = "posix"
    path.write_text(json.dumps({"nonce": process.nonce, "identity": rows[810001]}))
    process.bind()
    assert process.runtime_handle is process.launcher
    assert process.wait(timeout=1) == 0


def test_posix_indirect_exit_authority_fails_closed(owned):
    process, rows, path, ack = owned
    process.platform = "posix"
    with pytest.raises(RuntimeError, match="independent exit witness"):
        process.bind()
    assert not process.identity_verified and not ack.exists()


def test_posix_creation_token_binds_boot_and_start_ticks(tmp_path):
    entry = tmp_path / "55"
    entry.mkdir()
    fields = ["S", "12", *("0" for _ in range(18))]
    fields[19] = "999"
    (entry / "stat").write_text("55 (python command) " + " ".join(fields))
    (entry / "cmdline").write_bytes(b"/usr/bin/python\0-m\0src.main\0")
    boot = tmp_path / "sys/kernel/random/boot_id"
    boot.parent.mkdir(parents=True)
    boot.write_text("boot-test-identity")
    result = identity.read_process_identity(55, platform="posix", proc_root=tmp_path)
    assert result == {"pid": 55, "parent_pid": 12, "creation_token": "linux-start:boot-test-identity:999",
                      "argv": ["/usr/bin/python", "-m", "src.main"]}


@pytest.mark.parametrize("command", [
    'python.exe -c "print(\\\"python src/main.py\\\")"',
    'python.exe -m pytest src/main.py',
    'python.exe editor.py "src/main.py"',
    'Code.exe "python src/main.py"',
    'python.exe -m unrelated --description "src.main"',
])
def test_runtime_inventory_rejects_quoted_and_unrelated_commands(command):
    assert supervisor.is_ross_runtime(identity.split_windows_command_line(command)) is False


def test_owned_cleanup_signals_runtime_handle_only(owned):
    process, _, _, _ = owned
    process.bind()
    process.terminate()
    process.kill()
    assert process.runtime_handle.signals == ["terminate", "kill"]
    assert process.launcher.signals == []


def test_runtime_exit_code_and_distinct_pids_persist_in_supervisor_evidence(owned, tmp_path, monkeypatch):
    process, rows, _, _ = owned
    process.bind()
    write_child_proof(tmp_path, rows[810002])
    monkeypatch.setattr(supervisor, "no_ross_runtime_remains", lambda *args: True)
    monkeypatch.setattr(supervisor, "final_broker_audit", lambda: {"query_completed": True, "disconnected": True})
    assert supervisor.stop_and_finalize(process, [], [], tmp_path,
        graceful_timeout=0.1, terminate_timeout=0.1, kill_timeout=0.1, reader_timeout=0.1) == 0
    state = json.loads((tmp_path / "supervisor_shutdown.json").read_text())
    assert state["launcher_pid"] == 810001 and state["runtime_pid"] == 810002
    assert state["runtime_identity_verified"] is True
    assert state["runtime_exit_code"] == state["launcher_exit_code"] == 0
    assert process.launcher.signals == []


@pytest.mark.parametrize("failure", sorted(CALLBACKS))
def test_every_final_callback_runs_despite_any_other_failure(tmp_path, monkeypatch, failure):
    process = witnessed_process(tmp_path)
    calls = []
    def fail():
        raise OSError("offline injected failure")
    def inventory():
        calls.append("process_inventory")
        return fail() if failure == "process_inventory" else True
    def audit():
        calls.append("broker_audit")
        return fail() if failure == "broker_audit" else {"query_completed": True, "disconnected": True}
    real_scan, real_snapshot, real_verdict = shutdown.scan_artifacts, shutdown.snapshot, shutdown.validate_terminal
    def artifacts(directory):
        calls.append("artifact_validation")
        return fail() if failure == "artifact_validation" else real_scan(directory)
    def mutations():
        calls.append("mutation_validation")
        return fail() if failure == "mutation_validation" else real_snapshot()
    def verdict(evidence):
        calls.append("terminal_verdict")
        return fail() if failure == "terminal_verdict" else real_verdict(evidence)
    monkeypatch.setattr(shutdown, "scan_artifacts", artifacts)
    monkeypatch.setattr(shutdown, "snapshot", mutations)
    monkeypatch.setattr(shutdown, "validate_terminal", verdict)
    result = shutdown.complete_after_process_exit(tmp_path, process, inventory, audit)
    saved = json.loads((tmp_path / "terminal_evidence.json").read_text())
    assert set(calls) == CALLBACKS
    assert set(saved["final_callbacks"]) == CALLBACKS
    assert all(row["attempted"] is True for row in saved["final_callbacks"].values())
    assert saved["final_callbacks"][failure]["failed"] is True
    assert saved["final_callbacks"][failure]["completed"] is False
    assert saved["final_callbacks"]["terminal_verdict"]["failed"] is True
    assert result["passed"] is False
    assert "certification: FAIL" in (tmp_path / "FINAL_REPORT.md").read_text()


@pytest.mark.parametrize("payload", [[], {"events": None, "hooks": []}, {"events": [None], "hooks": []}, {"events": [], "hooks": "bad"}])
def test_malformed_child_evidence_cannot_suppress_final_checks(tmp_path, payload):
    process = witnessed_process(tmp_path)
    (tmp_path / "shutdown_evidence.json").write_text(json.dumps(payload))
    calls = []
    result = shutdown.complete_after_process_exit(tmp_path, process,
        lambda: calls.append("inventory") or True,
        lambda: calls.append("audit") or {"query_completed": True, "disconnected": True})
    saved = json.loads((tmp_path / "terminal_evidence.json").read_text())
    assert calls == ["inventory", "audit"]
    assert set(saved["final_callbacks"]) == CALLBACKS
    assert all(row["attempted"] for row in saved["final_callbacks"].values())
    assert result["passed"] is False


def test_pid_mismatch_does_not_suppress_any_final_callback(tmp_path):
    process = witnessed_process(tmp_path)
    process.runtime_identity = dict(process.runtime_identity, creation_token="windows-filetime:201")
    result = shutdown.complete_after_process_exit(tmp_path, process, lambda: True,
        lambda: {"query_completed": True, "disconnected": True})
    saved = json.loads((tmp_path / "terminal_evidence.json").read_text())
    assert saved["runtime_identity_verified"] is False
    assert all(row["attempted"] for row in saved["final_callbacks"].values())
    assert saved["final_callbacks"]["broker_audit"]["succeeded"] is True
    assert result["passed"] is False


def test_mutation_attempt_blocks_verdict_without_suppressing_other_checks(tmp_path, monkeypatch):
    process = witnessed_process(tmp_path)
    monkeypatch.setitem(mutation_audit._counts, "cancel", 1)
    result = shutdown.complete_after_process_exit(tmp_path, process, lambda: True,
        lambda: {"query_completed": True, "disconnected": True})
    saved = json.loads((tmp_path / "terminal_evidence.json").read_text())
    assert saved["audit_mutation_attempts"] == {"place": 0, "modify": 0, "cancel": 1}
    assert saved["final_callbacks"]["mutation_validation"]["failed"] is True
    assert all(row["attempted"] for row in saved["final_callbacks"].values())
    assert result["passed"] is False


def test_artifact_writer_failure_still_checks_mutations_and_terminal_verdict(tmp_path, monkeypatch):
    process = witnessed_process(tmp_path)
    writes, mutation_checks = [], []
    real_write, real_snapshot = shutdown.write_json, shutdown.snapshot
    def write(path, payload):
        writes.append(Path(path).name)
        if len(writes) == 1:
            raise OSError("first persistence failed")
        return real_write(path, payload)
    monkeypatch.setattr(shutdown, "write_json", write)
    monkeypatch.setattr(shutdown, "snapshot", lambda: mutation_checks.append(True) or real_snapshot())
    result = shutdown.complete_after_process_exit(tmp_path, process, lambda: True,
        lambda: {"query_completed": True, "disconnected": True})
    saved = json.loads((tmp_path / "terminal_evidence.json").read_text())
    assert mutation_checks == [True]
    assert all(row["attempted"] for row in saved["final_callbacks"].values())
    assert saved["final_callbacks"]["artifact_validation"]["failed"] is True
    assert result["passed"] is False

def test_ack_write_failure_clears_all_provisional_runtime_state(owned, monkeypatch):
    process, _, _, ack = owned
    opened = []
    def factory(*args, **kwargs):
        handle = RuntimeHandle(*args, **kwargs)
        opened.append(handle)
        return handle
    process.handle_factory = factory
    def fail(*args):
        raise OSError("ack write failed")
    monkeypatch.setattr(identity, "write_json", fail)
    with pytest.raises(OSError):
        process.bind()
    assert process.runtime_identity is None
    assert process.runtime_handle is None
    assert process.lineage == []
    assert process.identity_verified is False
    assert opened[0].closed is True
    with pytest.raises(RuntimeError):
        process.terminate()


@pytest.mark.parametrize("content", [None, "null", "{truncated", "\ufffd"])
def test_missing_or_truncated_child_evidence_attempts_all_callbacks(tmp_path, content):
    process = witnessed_process(tmp_path)
    path = tmp_path / "shutdown_evidence.json"
    if content is None:
        path.unlink()
    else:
        path.write_text(content, encoding="utf-8")
    result = shutdown.complete_after_process_exit(tmp_path, process, lambda: True,
        lambda: {"query_completed": True, "disconnected": True})
    saved = json.loads((tmp_path / "terminal_evidence.json").read_text())
    assert all(row["attempted"] for row in saved["final_callbacks"].values())
    assert set(saved["final_callbacks"]) == CALLBACKS
    assert result["passed"] is False
