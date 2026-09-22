#!/usr/bin/env python
"""Explicit-entrypoint supervisor for a future READ_ONLY observation.

Importing this module never starts a runtime or connects to a broker. The child
is bound to a verified runtime identity before observation begins. This is terminal safety evidence,
not a replacement for full-session RTH strategy certification.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import math
import posixpath
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
from src.runtime.process_identity import (HANDSHAKE_ACK, HANDSHAKE_NONCE, HANDSHAKE_PATH,
                                          SupervisedProcess, split_windows_command_line)



def is_ross_runtime(args):
    """Match the Python entrypoint, never later arguments or arbitrary text."""
    if not args:
        return False
    executable = args[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not re.fullmatch(r"python(?:w)?(?:\d+(?:\.\d+)*)?(?:\.exe)?", executable):
        return False
    modules = {"src.main", "scripts.certification.pr1040_real_readonly_runtime_observation_adapter"}
    index = 1
    while index < len(args):
        arg = args[index]
        if arg == "--":
            index += 1
            break
        if arg == "-m":
            return index + 1 < len(args) and args[index + 1] in modules
        if arg.startswith("-m"):
            return arg[2:] in modules
        if arg == "-" or arg.startswith("-c") or arg in {"--help", "--version", "-h", "-V"}:
            return False
        if arg in {"-W", "-X", "--check-hash-based-pycs"}:
            index += 2
            continue
        if arg.startswith(("-W", "-X", "--check-hash-based-pycs=")):
            index += 1
            continue
        if re.fullmatch(r"-[bBdEiIOPqRsSuvx]+m", arg):
            return index + 1 < len(args) and args[index + 1] in modules
        if re.fullmatch(r"-[bBdEiIOPqRsSuvx]+c", arg):
            return False
        if arg.startswith("-"):
            # Python short flags can be grouped, e.g. -Iu. Unknown options
            # invalidate the inventory rather than hiding an ambiguous launch.
            if not re.fullmatch(r"-[bBdEiIOPqRsSuvx]+", arg):
                raise ValueError("Unrecognized Python interpreter option")
            index += 1
            continue
        break
    if index >= len(args):
        return False
    script = posixpath.normpath(args[index].replace("\\", "/"))
    if executable.endswith(".exe"):
        script = script.lower()
    parts = [part for part in script.split("/") if part not in {"", "."}]
    return (len(parts) >= 2 and parts[-2:] == ["src", "main.py"]) or (
        parts and parts[-1] == "pr1040_real_readonly_runtime_observation_adapter.py")


def runtime_inventory(*, platform=None, proc_root=None):
    """Preserve matching PID/argv evidence; any incomplete enumeration fails closed."""
    platform = os.name if platform is None else platform
    evidence = {"completed": False, "runtimes": []}
    try:
        if platform == "nt":
            command = (
                "$ErrorActionPreference='Stop'; "
                "@(Get-CimInstance Win32_Process -ErrorAction Stop | "
                "Where-Object { $_.Name -match '^python' } | "
                "Select-Object ProcessId,CommandLine) | ConvertTo-Json -Compress"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=15, check=True)
            rows = json.loads(result.stdout)
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list) or not rows:
                raise ValueError("Python process inventory is incomplete")
            processes = []
            for row in rows:
                if not isinstance(row.get("CommandLine"), str) or not row["CommandLine"]:
                    raise ValueError("Python command line unavailable")
                processes.append((int(row["ProcessId"]), split_windows_command_line(row["CommandLine"])))
        else:
            proc = Path("/proc") if proc_root is None else Path(proc_root)
            # iterdir raises on unavailable enumeration; glob could look empty.
            entries = [entry for entry in proc.iterdir() if entry.name.isdigit()]
            if not entries:
                raise ValueError("Process inventory is empty")
            processes = []
            for entry in entries:
                try:
                    raw = (entry / "cmdline").read_bytes()
                except FileNotFoundError:
                    # A reaped process is harmless; a live unreadable entry is not.
                    if entry.exists():
                        raise
                    continue
                args = [os.fsdecode(arg) for arg in raw.rstrip(b"\0").split(b"\0")] if raw else []
                processes.append((int(entry.name), args))
        # A successful inventory must include this Python supervisor.
        if os.getpid() not in {pid for pid, _ in processes}:
            raise ValueError("Supervisor missing from process inventory")
        for pid, args in processes:
            if is_ross_runtime(args):
                evidence["runtimes"].append({"pid": pid, "argv": [scrub_text(arg) for arg in args]})
        evidence["completed"] = True
    except Exception as exc:
        evidence["error_type"] = type(exc).__name__
    return evidence


def no_ross_runtime_remains(evidence_path=None):
    evidence = runtime_inventory()
    if evidence_path is not None:
        write_json(evidence_path, evidence)
    return evidence["completed"] and not evidence["runtimes"]


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
        # Cleanup continues, but no partial query success survives any abort.
        result["query_completed"] = False
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
    state = {"pid": process.pid, "launcher_pid": getattr(getattr(process, "launcher", process), "pid", None),
             "runtime_pid": getattr(process, "runtime_identity", {}).get("pid") if getattr(process, "runtime_identity", None) else None,
             "launcher_identity": getattr(process, "launcher_identity", None),
             "runtime_identity": getattr(process, "runtime_identity", None),
             "runtime_identity_verified": getattr(process, "identity_verified", False) is True,
             "identity_error": getattr(process, "identity_error", None),
             "lineage": getattr(process, "lineage", []),
             "forced": False, "steps": [], "errors": [],
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
    state["runtime_process_exited"] = exit_code is not None and state["runtime_identity_verified"]
    state["runtime_exit_code"] = exit_code
    state["exit_code"] = exit_code  # Compatibility: this field now always belongs to the runtime.
    launcher = getattr(process, "launcher", process)
    try:
        if launcher is not process and launcher is not getattr(process, "runtime_handle", None):
            launcher.wait(timeout=terminate_timeout)
        state["launcher_exit_code"] = launcher.poll()
        if state["launcher_exit_code"] != 0:
            state["errors"].append({"stage": "launcher_exit", "type": "UnsuccessfulLauncherExit"})
    except BaseException as exc:
        state["launcher_exit_code"] = None
        error("launcher_exit", exc)
    if exit_code is None:
        state["surviving_pid"] = process.pid
    healthy = (state["runtime_identity_verified"] and exit_code == 0 and not state["identity_error"]
               and not state["forced"] and not state["errors"] and not state["reader_failures"] and not state["capture_errors"])
    try:
        write_json(output / "supervisor_shutdown.json", state)
    except BaseException as exc:
        error("write_supervisor_evidence", exc)
        healthy = False

    def quiet():
        return no_ross_runtime_remains(output / "runtime_inventory.json")

    def audit():
        with capture_console(output / "audit"):
            return final_broker_audit()

    observed_process = SimpleNamespace(
        pid=process.pid, poll=lambda: exit_code,
        launcher_identity=state["launcher_identity"], runtime_identity=state["runtime_identity"],
        identity_verified=state["runtime_identity_verified"], identity_error=state["identity_error"],
        launcher_exit_code=state["launcher_exit_code"], lineage=state["lineage"],
        supervisor_error=None if healthy else "FORCED_OR_INCOMPLETE_SUPERVISOR_SHUTDOWN")
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
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("seconds must be finite and positive")
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
    nonce = secrets.token_hex(32)
    handshake = output / ("runtime_identity_" + nonce + ".json")
    acknowledgement = output / ("runtime_identity_" + nonce + ".accepted.json")
    env[HANDSHAKE_NONCE] = nonce
    env[HANDSHAKE_PATH] = str(handshake)
    env[HANDSHAKE_ACK] = str(acknowledgement)
    # Recheck after preparation, before creating artifacts or starting the child.
    try:
        require_clean_certification_worktree(args.expected_commit)
    except RuntimeError as exc:
        parser.error(str(exc))
    output.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-u", "-m", "src.main"]
    launcher = subprocess.Popen(command, cwd=ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    process = SupervisedProcess(launcher, command, nonce, handshake, acknowledgement_path=acknowledgement)
    capture_errors = []
    readers = [threading.Thread(target=_capture, args=(pipe, output / name, capture_errors), daemon=True)
               for pipe, name in ((process.stdout, "stdout.log"), (process.stderr, "stderr.log"))]
    try:
        for reader in readers:
            reader.start()
        process.bind()
        write_json(output / "process_binding.json", {
            "launcher_identity": process.launcher_identity, "runtime_identity": process.runtime_identity,
            "lineage": process.lineage, "identity_verified": process.identity_verified})
        process.wait(timeout=args.seconds)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        pass
    except BaseException as exc:
        capture_errors.append(type(exc).__name__)
    # Configure only the supervisor audit environment; the child received env.
    # Handshake variables belong exclusively to the child, not the audit.
    os.environ.update({key: value for key, value in env.items()
                       if key not in {HANDSHAKE_PATH, HANDSHAKE_NONCE, HANDSHAKE_ACK}})
    try:
        return stop_and_finalize(process, readers, capture_errors, output)
    finally:
        process.close()


if __name__ == "__main__":
    raise SystemExit(main())
