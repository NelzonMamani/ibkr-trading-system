#!/usr/bin/env python
"""Explicit-entrypoint supervisor for a future READ_ONLY observation.

Importing this module never starts a runtime or connects to a broker. The child
must exit before a fresh audit is allowed. This is terminal safety evidence,
not a replacement for full-session RTH strategy certification.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ibkr.evidence_safety import SafeTextStream, capture_console, install_console_protection, scrub_text, write_json, write_text
from src.ibkr.shutdown_evidence import complete_after_process_exit


def no_ross_runtime_remains():
    """Return no command lines or account data; inspection failure fails closed."""
    if os.name == "nt":
        command = "@(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { $_.Name -match '^python' -and $_.CommandLine -match '(src[.]main|pr1040_real_readonly_runtime_observation_adapter)' }).Count"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True, timeout=15, check=True)
        return result.stdout.strip() == "0"
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    for path in proc.glob("[0-9]*/cmdline"):
        try:
            args = path.read_bytes().split(b"\0")
        except FileNotFoundError:
            continue
        if b"src.main" in args or any(b"pr1040_real_readonly_runtime_observation_adapter" in arg for arg in args):
            return False
    return True


def final_broker_audit():
    """Fresh end-marker-confirmed query on a separate READ_ONLY audit client."""
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    from src.config.runtime_config import resolve_ibkr_connection
    from src.ibkr.mutation_audit import snapshot
    host, port, client_id, mode = resolve_ibkr_connection()
    if mode != "READ_ONLY":
        raise RuntimeError("Final audit requires READ_ONLY")
    client = IbkrClient(host=host, port=port, client_id=client_id,
                        market_data_type="DELAYED", snapshot_timeout_seconds=10, readonly_enabled=True)
    client.readonly_enabled = True
    result = {"query_completed": False, "disconnected": False}
    try:
        client.connect()
        client._open_orders_event.clear()
        client._open_orders_snapshot = {}
        client.reqAllOpenOrders()
        if not client._open_orders_event.wait(timeout=10):
            raise RuntimeError("Final audit openOrderEnd missing")
        result["query_completed"] = True
        result["open_orders_count"] = len(client._open_orders_snapshot)
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        try:
            client.disconnect()
            thread = getattr(client, "_thread", None)
            result["disconnected"] = not client.is_connected() and not (thread and thread.is_alive())
        except BaseException as exc:
            result["disconnect_error"] = type(exc).__name__ + ": " + str(exc)
        result["mutation_attempts"] = snapshot()
    return result


def _capture_inner(pipe, path):
    with path.open("w", encoding="utf-8") as file:
        stream = SafeTextStream(file)
        try:
            for line in iter(pipe.readline, ""):
                stream.write(line)
        finally:
            stream.finish()
            os.fsync(file.fileno())
            pipe.close()


def _capture(pipe, path, errors):
    try:
        _capture_inner(pipe, path)
    except BaseException as exc:
        errors.append(type(exc).__name__)



def require_clean_certification_worktree(expected_commit):
    """Fail closed on every porcelain entry without modifying the worktree."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
        if head != expected_commit:
            raise RuntimeError("Worktree does not match expected commit")
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none"],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        raise RuntimeError("Unable to verify certification worktree") from None
    if status:
        entries = []
        records = iter(status.split("\0"))
        for record in records:
            if not record:
                continue
            category = record[:2]
            entries.append({"status": category, "path": scrub_text(record[3:])})
            if "R" in category or "C" in category:
                entries.append({"status": "rename_source", "path": scrub_text(next(records, ""))})
        raise RuntimeError("Certification requires a clean dedicated worktree: " + json.dumps(entries, ensure_ascii=True))
    return head


def stop_and_finalize(process, readers, capture_errors, output, *, graceful_timeout=60,
                      terminate_timeout=15, kill_timeout=15, reader_timeout=15):
    """Bound every escalation and cleanup wait, including after a failed kill."""
    state = {"pid": process.pid, "forced": False, "steps": [], "errors": [],
             "reader_failures": [], "runtime_process_exited": False}

    def error(stage, exc):
        # Exception text/commands can contain account identifiers; retain type only.
        state["errors"].append({"stage": stage, "type": type(exc).__name__})

    def wait_for(stage, timeout):
        try:
            process.wait(timeout=timeout)
            done = process.poll() is not None
            state["steps"].append({"stage": stage, "completed": done})
            return done
        except subprocess.TimeoutExpired:
            state["steps"].append({"stage": stage, "timeout": True, "completed": False})
        except BaseException as exc:
            error(stage, exc)
        return False

    try:
        write_text(output / "STOP_REQUESTED", "GRACEFUL_STOP_REQUESTED\n")
    except BaseException as exc:
        error("request_graceful_stop", exc)
    if not wait_for("graceful_wait", graceful_timeout):
        state["forced"] = True
        try:
            process.terminate()
            state["steps"].append({"stage": "terminate", "called": True})
        except BaseException as exc:
            error("terminate", exc)
        if not wait_for("terminate_wait", terminate_timeout):
            try:
                process.kill()
                state["steps"].append({"stage": "kill", "called": True})
            except BaseException as exc:
                error("kill", exc)
            wait_for("kill_wait", kill_timeout)

    for index, reader in enumerate(readers):
        try:
            if reader.ident is not None:
                reader.join(timeout=reader_timeout)
            if reader.ident is None or reader.is_alive():
                state["reader_failures"].append({"reader": index, "type": "ReaderIncomplete"})
        except BaseException as exc:
            state["reader_failures"].append({"reader": index, "type": type(exc).__name__})

    # Closing a pipe whose reader is blocked can itself block on the stream lock.
    # Attempt close in daemon workers and bound those joins as well.
    for name in ("stdout", "stderr"):
        pipe = getattr(process, name, None)
        if pipe is None:
            continue
        def close_pipe(stream=pipe, label=name):
            try:
                stream.close()
            except BaseException as exc:
                capture_errors.append(label + ":" + type(exc).__name__)
        try:
            closer = threading.Thread(target=close_pipe, daemon=True)
            closer.start()
            closer.join(timeout=reader_timeout)
            if closer.is_alive():
                state["reader_failures"].append({"stream": name, "type": "PipeCloseIncomplete"})
        except BaseException as exc:
            error("close_" + name, exc)
    state["capture_errors"] = [scrub_text(str(item)) for item in capture_errors]
    try:
        exit_code = process.poll()
    except BaseException as exc:
        error("final_poll", exc)
        exit_code = None
    state["runtime_process_exited"] = exit_code is not None
    state["exit_code"] = exit_code
    if exit_code is None:
        state["surviving_pid"] = process.pid
    healthy = not state["forced"] and not state["errors"] and not state["reader_failures"] and not state["capture_errors"]
    try:
        write_json(output / "supervisor_shutdown.json", state)
    except BaseException as exc:
        error("write_supervisor_evidence", exc)
        healthy = False

    def quiet():
        return not state["reader_failures"] and not state["capture_errors"] and no_ross_runtime_remains()

    def audit():
        # Forced/incomplete termination cannot obtain a passing graceful report,
        # even if the OS exit code happens to be zero and child proof exists.
        if not healthy:
            return {"query_completed": False, "disconnected": False,
                    "skipped_reason": "FORCED_OR_INCOMPLETE_SUPERVISOR_SHUTDOWN"}
        with capture_console(output / "audit"):
            return final_broker_audit()

    observed_process = SimpleNamespace(pid=process.pid, poll=lambda: exit_code)
    try:
        result = complete_after_process_exit(output, observed_process, quiet, audit)
    except BaseException as exc:
        error("terminal_finalization", exc)
        result = {"passed": False}
        # Best effort failure artifacts; write errors never turn into success.
        try:
            write_json(output / "supervisor_shutdown.json", state)
            write_text(output / "FINAL_REPORT.md", "PR1090 terminal certification: FAIL\nTerminal finalization failed\nPAPER_READY=NO\nPAPER_READINESS_GATE=FAIL\n")
        except BaseException:
            pass
    return 0 if healthy and result["passed"] else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args(argv)
    if args.seconds <= 0:
        parser.error("seconds must be positive")
    try:
        require_clean_certification_worktree(args.expected_commit)
    except RuntimeError as exc:
        parser.error(str(exc))
    output = args.output.resolve()
    install_console_protection()
    from scripts.certification.pr1040_real_readonly_runtime_observation_adapter import build_safe_readonly_env
    env = build_safe_readonly_env()
    env["PR1090_EVIDENCE_DIR"] = str(output)
    env["PR1090_STOP_FILE"] = str(output / "STOP_REQUESTED")
    # Recheck after preparation, before creating artifacts or starting the child.
    try:
        require_clean_certification_worktree(args.expected_commit)
    except RuntimeError as exc:
        parser.error(str(exc))
    output.mkdir(parents=True, exist_ok=False)
    process = subprocess.Popen([sys.executable, "-u", "-m", "src.main"], cwd=ROOT, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    capture_errors = []
    readers = [threading.Thread(target=_capture, args=(pipe, output / name, capture_errors), daemon=True)
               for pipe, name in ((process.stdout, "stdout.log"), (process.stderr, "stderr.log"))]
    try:
        for reader in readers:
            reader.start()
        process.wait(timeout=args.seconds)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        pass
    except BaseException as exc:
        capture_errors.append(type(exc).__name__)
    # Configure only the supervisor audit environment; the child received env.
    os.environ.update(env)
    return stop_and_finalize(process, readers, capture_errors, output)


if __name__ == "__main__":
    raise SystemExit(main())
