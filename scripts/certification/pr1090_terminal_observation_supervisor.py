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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ibkr.evidence_safety import SafeTextStream, capture_console, install_console_protection, write_text
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



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args(argv)
    if args.seconds <= 0:
        parser.error("seconds must be positive")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if head != args.expected_commit:
        parser.error("Worktree does not match expected commit")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    install_console_protection()
    from scripts.certification.pr1040_real_readonly_runtime_observation_adapter import build_safe_readonly_env
    env = build_safe_readonly_env()
    env["PR1090_EVIDENCE_DIR"] = str(output)
    env["PR1090_STOP_FILE"] = str(output / "STOP_REQUESTED")
    process = subprocess.Popen([sys.executable, "-u", "-m", "src.main"], cwd=ROOT, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    capture_errors = []
    readers = [threading.Thread(target=_capture, args=(pipe, output / name, capture_errors))
               for pipe, name in ((process.stdout, "stdout.log"), (process.stderr, "stderr.log"))]
    try:
        for reader in readers:
            reader.start()
        process.wait(timeout=args.seconds)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        pass
    finally:
        write_text(output / "STOP_REQUESTED", "GRACEFUL_STOP_REQUESTED\n")
        try:
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=15)
        for reader in readers:
            if reader.ident is not None:
                reader.join(timeout=15)
    def quiet():
        return not capture_errors and not any(reader.is_alive() for reader in readers) and no_ross_runtime_remains()
    # Set only the audit process environment after the observed child has exited.
    os.environ.update(env)
    def audit():
        with capture_console(output / "audit"):
            return final_broker_audit()
    result = complete_after_process_exit(output, process, quiet, audit)
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
