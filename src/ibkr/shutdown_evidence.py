"""Ordered shutdown evidence; process exit must be witnessed by a supervisor."""
from __future__ import annotations

import os
import time
from pathlib import Path

from src.ibkr.evidence_safety import finish_console_protection, sanitize, scan_artifacts, write_json, write_text
from src.ibkr.mutation_audit import require_zero_attempts, snapshot

REQUIRED_HOOKS = (
    "ops_summary", "learning_scheduler", "execution_engine.shutdown",
    "trade_exit_engine.shutdown", "storage_engine.shutdown",
    "active_trade_registry.verify_empty", "scanner_reset", "manager_disconnect",
    "event_collector.flush_summary", "console_flush",
)


class ShutdownEvidence:
    def __init__(self):
        self.events = []
        self.hooks = []

    def record(self, event, **detail):
        self.events.append(sanitize({"event": event, "sequence": len(self.events), "monotonic_ns": time.monotonic_ns(), **detail}))

    def attempt(self, name, function):
        row = {"hook": name, "attempted": True, "completed": False}
        self.hooks.append(row)
        try:
            result = function()
            if result is False:
                raise RuntimeError("Hook reported incomplete cleanup")
            row["completed"] = True
            return result
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            row["error"] = sanitize(str(exc))
        finally:
            self.record("SHUTDOWN_HOOK", **row)

    def payload(self):
        from src.runtime.process_identity import runtime_identity_for_evidence
        return {"schema": "PR1090.shutdown.v1", "pid": os.getpid(),
                "process_identity": runtime_identity_for_evidence(),
                "events": self.events, "hooks": self.hooks, "mutation_attempts": snapshot()}

    def flush(self, directory):
        write_json(Path(directory) / "shutdown_evidence.json", self.payload())


def reset_scanner():
    from src.scanner.scanner_runner import reset_scanner_runtime_state
    reset_scanner_runtime_state(clear_persistent_provider=True, suppress_disconnect_errors=False)


def disconnect_manager():
    from src.adapters.brokers.ibkr import ibkr_connection_manager as module
    manager = getattr(module, "_default_manager", None)
    if manager is None:
        return True
    client = getattr(manager, "_client", None)
    manager.disconnect(reason="pr1090_shutdown")
    thread = getattr(client, "_thread", None)
    return not manager.is_connected() and not (thread is not None and thread.is_alive())


def validate_terminal(evidence):
    blockers = []
    if evidence.get("supervisor_error"):
        blockers.append("Supervisor finalization failed")
    callbacks = evidence.get("final_callbacks", {})
    for name in ("process_inventory", "broker_audit", "artifact_validation", "mutation_validation"):
        row = callbacks.get(name, {})
        if row.get("attempted") is not True or row.get("completed") is not True:
            blockers.append("Incomplete final callback: " + name)
    try:
        require_zero_attempts(evidence.get("mutation_attempts"))
    except RuntimeError as exc:
        blockers.append(str(exc))
    if evidence.get("runtime_identity_verified") is not True:
        blockers.append("Runtime process identity was not verified")
    if evidence.get("launcher_exit_code") != 0:
        blockers.append("Launcher did not exit successfully")
    if evidence.get("runtime_exit_code") != 0:
        blockers.append("Runtime did not exit successfully")
    try:
        require_zero_attempts(evidence.get("audit_mutation_attempts"))
    except RuntimeError:
        blockers.append("Final audit mutation evidence missing or unsafe")
    events = evidence.get("events", [])
    if any(row.get("sequence") != index for index, row in enumerate(events)):
        blockers.append("Contradictory event sequence")
    times = [row.get("monotonic_ns") for row in events]
    if any(type(value) is not int for value in times) or times != sorted(times):
        blockers.append("Contradictory event timestamps")
    names = [row.get("event") for row in events]
    if any(row.get("mode") == "PANIC" or row.get("event") in {"PANIC_STOP_REQUESTED", "PANIC_STOP_TRIGGERED"} for row in events):
        blockers.append("PANIC cannot certify graceful shutdown")
    required = ("GRACEFUL_STOP_REQUESTED", "SHUTDOWN_STARTED", "SHUTDOWN_COMPLETE", "TERMINAL_FLUSHED", "RUNTIME_PROCESS_EXITED", "NO_ROSS_RUNTIME", "FINAL_BROKER_QUERY", "FINAL_AUDIT_DISCONNECTED", "FINAL_EVIDENCE_FLUSHED")
    positions = []
    for name in required:
        if names.count(name) != 1:
            blockers.append("Missing or duplicate " + name)
        else:
            positions.append(names.index(name))
    if positions != sorted(positions):
        blockers.append("Contradictory shutdown ordering")
    if "SHUTDOWN_STARTED" in names and "SHUTDOWN_COMPLETE" in names:
        start, end = names.index("SHUTDOWN_STARTED"), names.index("SHUTDOWN_COMPLETE")
        if any(not start < index < end for index, name in enumerate(names) if name == "SHUTDOWN_HOOK"):
            blockers.append("Hook recorded outside shutdown interval")
    hooks = evidence.get("hooks", [])
    for name in REQUIRED_HOOKS:
        matching = [row for row in hooks if row.get("hook") == name]
        if len(matching) != 1 or matching[0].get("attempted") is not True or matching[0].get("completed") is not True:
            blockers.append("Incomplete hook: " + name)
    for event in events:
        if event.get("event") in required and event.get("completed") is not True:
            blockers.append("Unconfirmed " + event["event"])
    return {"passed": not blockers, "blockers": blockers}


def _attempt_final_callback(callbacks, name, function, successful=lambda result: result is True):
    """Supervisor-only boundary: a failed check cannot suppress the next check."""
    row = {"attempted": True, "completed": False, "succeeded": False,
           "failed": False, "status": "RUNNING"}
    callbacks[name] = row
    try:
        value = function()
        passed = successful(value) is True
        row.update(completed=passed, succeeded=passed, failed=not passed,
                   status="SUCCEEDED" if passed else "FAILED")
        if not passed:
            row["diagnostic"] = sanitize(value.get("blockers", "Required evidence unavailable")
                                         if isinstance(value, dict) else "Required evidence unavailable")
        return value
    except BaseException as exc:
        # This boundary owns final collection, not application shutdown. Retain
        # even process-control failures and attempt every other final check.
        row.update(failed=True, status="FAILED", error_type=type(exc).__name__,
                   diagnostic=type(exc).__name__)
        return None


def finalize_report(directory, evidence):
    """Attempt all final checks, recording failures before returning a verdict."""
    directory = Path(directory)
    callbacks = evidence.setdefault("final_callbacks", {})
    flush = next(row for row in evidence["events"] if row["event"] == "FINAL_EVIDENCE_FLUSHED")

    def artifacts():
        # This event becomes authoritative only if the terminal file was synced.
        flush["completed"] = True
        write_json(directory / "terminal_evidence.json", evidence)
        scan = scan_artifacts(directory)
        write_json(directory / "sensitive_token_scan.json", scan)
        return scan["passed"] is True

    _attempt_final_callback(callbacks, "artifact_validation", artifacts)
    if not callbacks["artifact_validation"]["completed"]:
        flush["completed"] = False

    def mutations():
        # Runtime and supervisor audit counters have distinct process owners.
        evidence["audit_mutation_attempts"] = snapshot()
        require_zero_attempts(evidence.get("mutation_attempts"))
        require_zero_attempts(evidence["audit_mutation_attempts"])
        return True

    _attempt_final_callback(callbacks, "mutation_validation", mutations)
    result = _attempt_final_callback(callbacks, "terminal_verdict", lambda: validate_terminal(evidence),
                                     lambda value: isinstance(value, dict) and value.get("passed") is True)
    if not isinstance(result, dict) or not isinstance(result.get("blockers"), list):
        result = {"passed": False, "blockers": ["Terminal verdict unavailable"]}
    # A malformed/replaced verdict implementation cannot erase failed checks.
    for name, row in callbacks.items():
        if row.get("completed") is not True:
            blocker = "Incomplete final callback: " + name
            if blocker not in result["blockers"]:
                result["blockers"].append(blocker)
            result["passed"] = False

    def persistence_failed(stage, exc):
        diagnostic = stage + ": " + type(exc).__name__
        callbacks["artifact_validation"].update(completed=False, succeeded=False, failed=True,
                                                status="FAILED", diagnostic=diagnostic)
        callbacks["terminal_verdict"].update(completed=False, succeeded=False, failed=True,
                                             status="FAILED", diagnostic="Final artifact validation failed")
        result["passed"] = False
        result["blockers"].append(diagnostic)

    def report_text():
        return ("PR1090 terminal certification: " + ("PASS" if result["passed"] else "FAIL")
                + "\nPAPER_READY=NO\nPAPER_READINESS_GATE=FAIL\n"
                + "\n".join(result["blockers"]) + "\n")

    # Each persistence attempt is bounded by its own exception boundary. A
    # failed writer never prevents the other report or the final privacy scan.
    for name, write in (("terminal_evidence", lambda: write_json(directory / "terminal_evidence.json", evidence)),
                        ("final_report", lambda: write_text(directory / "FINAL_REPORT.md", report_text()))):
        try:
            write()
        except BaseException as exc:
            persistence_failed(name, exc)
    try:
        if scan_artifacts(directory)["passed"] is not True:
            raise RuntimeError("Final artifact sensitive-token scan failed")
    except BaseException as exc:
        persistence_failed("final_artifact_scan", exc)
    if not result["passed"]:
        # Replace any previously written success after a late failure. If the
        # disk is unavailable, the nonzero supervisor result remains mandatory.
        for write in (lambda: write_json(directory / "terminal_evidence.json", evidence),
                      lambda: write_text(directory / "FINAL_REPORT.md", report_text())):
            try:
                write()
            except BaseException:
                pass
    return result


def complete_after_process_exit(directory, process, no_runtime_remains, final_audit):
    """Supervisor boundary: never claim exit from inside the observed process.

    Final inventory and READ_ONLY reconciliation are independent best-effort
    callbacks. A failed identity, exit, inventory or audit never suppresses the
    remaining callbacks, nor can their success erase another terminal failure.
    """
    import json
    directory = Path(directory)
    errors = []
    try:
        evidence = json.loads((directory / "shutdown_evidence.json").read_text(encoding="utf-8"))
        if not isinstance(evidence, dict):
            raise ValueError("Child evidence is not an object")
        if not isinstance(evidence.get("events"), list) or not all(isinstance(row, dict) for row in evidence["events"]):
            raise ValueError("Child events are invalid")
        if not isinstance(evidence.get("hooks"), list) or not all(isinstance(row, dict) for row in evidence["hooks"]):
            raise ValueError("Child hooks are invalid")
    except (OSError, ValueError) as exc:
        evidence = {"events": [], "hooks": [], "mutation_attempts": None}
        errors.append("child_evidence: " + type(exc).__name__)
    events = evidence["events"]

    def record(name, completed):
        events.append({"event": name, "sequence": len(events), "monotonic_ns": time.monotonic_ns(), "completed": completed})

    if getattr(process, "supervisor_error", None):
        errors.append(sanitize(process.supervisor_error))
    try:
        exit_code = process.poll()
    except BaseException as exc:
        exit_code = None
        errors.append("exit: " + type(exc).__name__)
    identity = getattr(process, "runtime_identity", None)
    identity_verified = getattr(process, "identity_verified", False) is True
    matched = (identity_verified and isinstance(identity, dict)
               and evidence.get("process_identity") == identity
               and identity.get("pid") == process.pid == evidence.get("pid")
               and bool(identity.get("creation_token")))
    exited = exit_code is not None and process.pid != os.getpid() and matched
    evidence["launcher_identity"] = sanitize(getattr(process, "launcher_identity", None))
    evidence["runtime_identity"] = sanitize(identity)
    evidence["runtime_identity_verified"] = bool(matched)
    evidence["launcher_pid"] = getattr(process, "launcher_identity", {}).get("pid") if getattr(process, "launcher_identity", None) else None
    evidence["runtime_pid"] = identity.get("pid") if isinstance(identity, dict) else None
    evidence["launcher_exit_code"] = getattr(process, "launcher_exit_code", None)
    evidence["process_lineage"] = sanitize(getattr(process, "lineage", []))
    evidence["identity_error"] = sanitize(getattr(process, "identity_error", None))
    record("RUNTIME_PROCESS_EXITED", exited)
    evidence["runtime_exit_code"] = exit_code
    callbacks = evidence["final_callbacks"] = {}
    quiet = _attempt_final_callback(callbacks, "process_inventory", no_runtime_remains)
    record("NO_ROSS_RUNTIME", quiet is True)
    audit = _attempt_final_callback(callbacks, "broker_audit", final_audit,
        lambda value: isinstance(value, dict) and value.get("query_completed") is True and value.get("disconnected") is True)
    if not isinstance(audit, dict):
        audit = {}
    record("FINAL_BROKER_QUERY", audit.get("query_completed") is True)
    record("FINAL_AUDIT_DISCONNECTED", audit.get("disconnected") is True)
    evidence["final_broker_audit"] = sanitize(audit)
    if errors:
        evidence["supervisor_error"] = sanitize("; ".join(errors))
    record("FINAL_EVIDENCE_FLUSHED", False)
    return finalize_report(directory, evidence)
