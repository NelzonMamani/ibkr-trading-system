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
        return {"schema": "PR1090.shutdown.v1", "pid": os.getpid(), "events": self.events, "hooks": self.hooks, "mutation_attempts": snapshot()}

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
    try:
        require_zero_attempts(evidence.get("mutation_attempts"))
    except RuntimeError as exc:
        blockers.append(str(exc))
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


def finalize_report(directory, evidence):
    """Write and sync terminal evidence before any verdict or final report."""
    directory = Path(directory)
    write_json(directory / "terminal_evidence.json", evidence)
    result = validate_terminal(evidence)
    scan = scan_artifacts(directory)
    if not scan["passed"]:
        result["passed"] = False
        result["blockers"].append("Sensitive-token scan failed")
    write_json(directory / "sensitive_token_scan.json", scan)
    write_text(directory / "FINAL_REPORT.md", "PR1090 terminal certification: " + ("PASS" if result["passed"] else "FAIL") + "\nPAPER_READY=NO\nPAPER_READINESS_GATE=FAIL\n" + "\n".join(result["blockers"]) + "\n")
    final_scan = scan_artifacts(directory)
    if not final_scan["passed"]:
        result["passed"] = False
        result["blockers"].append("Final report sensitive-token scan failed")
    return result


def complete_after_process_exit(directory, process, no_runtime_remains, final_audit):
    """Supervisor boundary: never claim exit from inside the observed process.

    final_audit returns a fresh broker query and disconnect proof; both callbacks
    must report explicit booleans. Missing evidence is retained as a failed report.
    """
    import json
    directory = Path(directory)
    try:
        evidence = json.loads((directory / "shutdown_evidence.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        evidence = {"events": [], "hooks": [], "mutation_attempts": None}
    events = evidence.setdefault("events", [])

    def record(name, completed):
        events.append({"event": name, "sequence": len(events), "monotonic_ns": time.monotonic_ns(), "completed": completed})

    exit_code = process.poll()
    exited = exit_code is not None and process.pid != os.getpid() and evidence.get("pid") == process.pid
    record("RUNTIME_PROCESS_EXITED", exited)
    evidence["runtime_exit_code"] = exit_code
    quiet = False
    audit = {}
    try:
        if exited:
            quiet = no_runtime_remains() is True
        record("NO_ROSS_RUNTIME", quiet)
        if exited and quiet:
            audit = final_audit()
    except BaseException as exc:
        evidence["supervisor_error"] = sanitize(type(exc).__name__ + ": " + str(exc))
    finally:
        record("FINAL_BROKER_QUERY", audit.get("query_completed") is True)
        record("FINAL_AUDIT_DISCONNECTED", audit.get("disconnected") is True)
        evidence["final_broker_audit"] = sanitize(audit)
        evidence["audit_mutation_attempts"] = snapshot()
        try:
            require_zero_attempts(evidence["audit_mutation_attempts"])
        except RuntimeError:
            record("AUDIT_MUTATION_ATTEMPTED", False)
        write_json(directory / "terminal_evidence.json", evidence)
        record("FINAL_EVIDENCE_FLUSHED", True)
    return finalize_report(directory, evidence)
