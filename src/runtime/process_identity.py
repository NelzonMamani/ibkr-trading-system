"""Process identity for supervised evidence collection (no broker dependencies).

A startup handshake is accepted only after an OS observation binds its nonce,
PID, creation token, argv and ancestry to the launched process. Windows retains
an actual runtime process handle; Linux direct children retain their Popen
handle. Neither a launcher exit nor a PID from a shutdown file proves exit.
Unsupported/unreadable process metadata fails closed.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from src.ibkr.evidence_safety import write_json

HANDSHAKE_PATH = "CERTIFICATION_PROCESS_IDENTITY_FILE"
HANDSHAKE_NONCE = "CERTIFICATION_PROCESS_NONCE"
HANDSHAKE_ACK = "CERTIFICATION_PROCESS_ACK_FILE"
_runtime_identity = None


def split_windows_command_line(command):
    """Decode Windows quoting/backslashes into argv without a shell."""
    args, index = [], 0
    while index < len(command):
        while index < len(command) and command[index] in " \t":
            index += 1
        if index == len(command):
            break
        arg, quoted = [], False
        while index < len(command) and (quoted or command[index] not in " \t"):
            slashes = 0
            while index < len(command) and command[index] == "\\":
                slashes += 1
                index += 1
            if index < len(command) and command[index] == '"':
                arg.extend("\\" * (slashes // 2))
                if slashes % 2:
                    arg.append('"')
                elif quoted and index + 1 < len(command) and command[index + 1] == '"':
                    arg.append('"')
                    index += 1
                else:
                    quoted = not quoted
                index += 1
            else:
                arg.extend("\\" * slashes)
                if index < len(command) and (quoted or command[index] not in " \t"):
                    arg.append(command[index])
                    index += 1
        if quoted:
            raise ValueError("Unclosed process command quoting")
        args.append("".join(arg))
    return args


def _kernel32():
    from ctypes import wintypes
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    api.GetProcessTimes.restype = wintypes.BOOL
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.GetExitCodeProcess.restype = wintypes.BOOL
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    api.TerminateProcess.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def _creation_token(api, handle):
    from ctypes import wintypes
    values = [wintypes.FILETIME() for _ in range(4)]
    if not api.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
        raise ctypes.WinError(ctypes.get_last_error())
    return "windows-filetime:" + str((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime)


class WindowsProcessHandle:
    """A retained kernel handle cannot be redirected by PID reuse."""
    def __init__(self, pid, expected_creation=None, *, allow_terminate=False):
        self.pid = pid
        self.api = _kernel32()
        access = 0x1000 | 0x00100000 | (0x0001 if allow_terminate else 0)
        self.handle = self.api.OpenProcess(access, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            self.creation_token = _creation_token(self.api, self.handle)
            if expected_creation is not None and self.creation_token != expected_creation:
                raise RuntimeError("Process creation token changed")
        except BaseException:
            self.close()
            raise

    def poll(self):
        from ctypes import wintypes
        status = self.api.WaitForSingleObject(self.handle, 0)
        if status == 258:  # WAIT_TIMEOUT, including a live process with code 259.
            return None
        if status != 0:
            raise OSError("Unable to observe runtime handle")
        code = wintypes.DWORD()
        if not self.api.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            code = self.poll()
            if code is not None:
                return code
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired("verified runtime", timeout)
            time.sleep(min(0.05, remaining))

    def terminate(self):
        if not self.api.TerminateProcess(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    kill = terminate

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def read_process_identity(pid, *, platform=None, proc_root=None, timeout=15):
    """Read PID/parent/creation/argv from Windows or Linux OS metadata."""
    platform = os.name if platform is None else platform
    if type(pid) is not int or pid <= 0:
        raise ValueError("Invalid process PID")
    if platform == "nt":
        command = (
            "$ErrorActionPreference='Stop'; "
            f"Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' -ErrorAction Stop | "
            "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress"
        )
        # Retain the process object before querying PID-addressed CIM metadata.
        # Both liveness checks must refer to that object, not a reused PID.
        handle = WindowsProcessHandle(pid)
        try:
            if handle.poll() is not None:
                raise RuntimeError("Process exited before identity inspection")
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                                    capture_output=True, text=True, timeout=timeout, check=True)
            row = json.loads(result.stdout)
            if not isinstance(row, dict) or int(row["ProcessId"]) != pid or not row.get("CommandLine"):
                raise RuntimeError("Process metadata unavailable")
            if handle.poll() is not None:
                raise RuntimeError("Process exited during identity inspection")
            return {"pid": pid, "parent_pid": int(row["ParentProcessId"]),
                    "creation_token": handle.creation_token,
                    "argv": split_windows_command_line(row["CommandLine"])}
        finally:
            handle.close()
    if platform != "posix":
        raise RuntimeError("Unsupported process identity platform")
    proc = Path("/proc") if proc_root is None else Path(proc_root)
    entry = proc / str(pid)
    # stat names may contain spaces or ')'; fields after the final ')' start at 3.
    before = (entry / "stat").read_text()
    fields = before[before.rindex(")") + 2:].split()
    argv = [os.fsdecode(part) for part in (entry / "cmdline").read_bytes().rstrip(b"\0").split(b"\0")]
    after = (entry / "stat").read_text()
    if before != after:
        later = after[after.rindex(")") + 2:].split()
        if fields[19] != later[19] or fields[1] != later[1]:
            raise RuntimeError("Process identity changed during inspection")
    if not argv or not argv[0]:
        raise RuntimeError("Process command unavailable")
    boot = (proc / "sys/kernel/random/boot_id").read_text().strip()
    if not boot:
        raise RuntimeError("OS boot identity unavailable")
    return {"pid": pid, "parent_pid": int(fields[1]),
            "creation_token": "linux-start:" + boot + ":" + fields[19], "argv": argv}


def publish_runtime_identity(*, timeout=90):
    """Called before main imports only for an explicitly supervised launch."""
    global _runtime_identity
    path, nonce = os.environ.get(HANDSHAKE_PATH), os.environ.get(HANDSHAKE_NONCE)
    ack = os.environ.get(HANDSHAKE_ACK)
    if not path and not nonce and not ack:
        return
    if not path or not nonce or not ack:
        raise RuntimeError("Incomplete supervised process handshake configuration")
    identity = read_process_identity(os.getpid())
    write_json(path, {"nonce": nonce, "identity": identity})
    _runtime_identity = identity
    # Hold before application imports: startup cannot outrun the OS binding.
    deadline = time.monotonic() + timeout
    while True:
        try:
            accepted = json.loads(Path(ack).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            accepted = None
        if accepted is not None:
            if accepted != {"nonce": nonce, "identity": identity}:
                raise RuntimeError("Invalid supervisor startup acknowledgement")
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("Supervisor startup acknowledgement unavailable")
        time.sleep(0.05)


def runtime_identity_for_evidence():
    return _runtime_identity


def _creation_order(identity):
    token = identity.get("creation_token", "")
    if token.startswith("windows-filetime:"):
        return "windows", int(token.split(":")[1])
    if token.startswith("linux-start:"):
        _, boot, ticks = token.split(":")
        if not boot:
            raise RuntimeError("Missing boot identity")
        return "linux:" + boot, int(ticks)
    raise RuntimeError("Unrecognized process creation authority")


def _validate_identity(identity):
    if not isinstance(identity, dict) or type(identity.get("pid")) is not int or identity["pid"] <= 0:
        raise RuntimeError("Invalid process identity")
    if type(identity.get("parent_pid")) is not int or identity["parent_pid"] < 0:
        raise RuntimeError("Invalid parent process identity")
    if not isinstance(identity.get("argv"), list) or not identity["argv"] or not all(isinstance(arg, str) for arg in identity["argv"]):
        raise RuntimeError("Invalid process command")
    if _creation_order(identity)[1] <= 0:
        raise RuntimeError("Invalid process creation time")


def verify_runtime_handshake(handshake, nonce, launcher, expected_command, *, read_identity=read_process_identity):
    """Bind a live startup handshake to the exact launch; never infer success."""
    if not isinstance(handshake, dict) or handshake.get("nonce") != nonce:
        raise RuntimeError("Runtime handshake nonce mismatch")
    reported = handshake.get("identity")
    _validate_identity(reported)
    _validate_identity(launcher)
    runtime = read_identity(reported["pid"])
    _validate_identity(runtime)
    if runtime != reported:
        raise RuntimeError("Runtime handshake disagrees with OS process identity")
    normalize = lambda path: os.path.normcase(os.path.abspath(path))
    expected_executables = {normalize(expected_command[0]),
                            normalize(getattr(sys, "_base_executable", sys.executable))}
    if normalize(launcher["argv"][0]) != normalize(expected_command[0]) or launcher["argv"][1:] != expected_command[1:]:
        raise RuntimeError("Unexpected launcher command")
    args = runtime["argv"]
    if normalize(args[0]) not in expected_executables or args[1:] != expected_command[1:]:
        raise RuntimeError("Unexpected runtime command")
    lineage, current = [], runtime
    for _ in range(16):
        lineage.append(current)
        if current["pid"] == launcher["pid"]:
            if current != launcher:
                raise RuntimeError("Launcher identity changed (possible PID reuse)")
            return {"runtime": runtime, "launcher": launcher, "lineage": lineage}
        if current["parent_pid"] <= 0 or current["parent_pid"] in {row["pid"] for row in lineage}:
            break
        parent = read_identity(current["parent_pid"])
        _validate_identity(parent)
        child_clock, child_time = _creation_order(current)
        parent_clock, parent_time = _creation_order(parent)
        if child_clock != parent_clock or parent_time > child_time:
            raise RuntimeError("Parent creation time contradicts runtime lineage")
        current = parent
    raise RuntimeError("Runtime is not a descendant of the observed launcher")


class SupervisedProcess:
    """Popen-compatible runtime witness; launcher and runtime are separate.

    Windows indirect children use a retained native handle for exit and signals.
    POSIX direct children use Popen/waitpid; unsupported indirect exit authority
    is rejected rather than deriving an exit status from a launcher or JSON.
    """
    def __init__(self, launcher, command, nonce, handshake_path, *, read_identity=read_process_identity,
                 handle_factory=WindowsProcessHandle, platform=None, acknowledgement_path=None):
        self.launcher = launcher
        self.pid = launcher.pid
        self.stdout, self.stderr = launcher.stdout, launcher.stderr
        self.command, self.nonce, self.handshake_path = command, nonce, Path(handshake_path)
        self.acknowledgement_path = Path(acknowledgement_path) if acknowledgement_path is not None else None
        self.read_identity, self.handle_factory = read_identity, handle_factory
        self.platform = os.name if platform is None else platform
        self.launcher_identity = None
        self.runtime_identity = None
        self.lineage = []
        self.identity_verified = False
        self.identity_error = None
        self.runtime_handle = None
        try:
            if launcher.poll() is not None:
                raise RuntimeError("Launcher exited before identity binding")
            self.launcher_identity = read_identity(launcher.pid)
            if self.platform == "nt":
                # Popen owns this handle from CreateProcess; its creation time
                # prevents a late PID lookup from adopting an unrelated launch.
                owned_creation = _creation_token(_kernel32(), int(launcher._handle))
                if owned_creation != self.launcher_identity["creation_token"]:
                    raise RuntimeError("Launcher creation token changed")
            if launcher.poll() is not None:
                raise RuntimeError("Launcher exited during identity binding")
        except Exception as exc:
            self.launcher_identity = None
            self.identity_error = type(exc).__name__

    def bind(self, timeout=30):
        deadline = time.monotonic() + timeout
        try:
            if self.launcher_identity is None:
                raise RuntimeError("Launcher identity unavailable")
            while True:
                try:
                    handshake = json.loads(self.handshake_path.read_text(encoding="utf-8"))
                    break
                except (FileNotFoundError, json.JSONDecodeError):
                    if time.monotonic() >= deadline or self.launcher.poll() is not None:
                        raise RuntimeError("Runtime handshake unavailable") from None
                    time.sleep(min(0.05, max(0, deadline - time.monotonic())))
            def read_before_deadline(pid):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Runtime identity binding timed out")
                result = self.read_identity(pid, timeout=min(15, deadline - time.monotonic()))
                if time.monotonic() >= deadline:
                    raise RuntimeError("Runtime identity binding timed out")
                return result
            binding = verify_runtime_handshake(handshake, self.nonce, self.launcher_identity,
                                               self.command, read_identity=read_before_deadline)
            runtime = binding["runtime"]
            if self.platform == "nt":
                witness = self.handle_factory(runtime["pid"], runtime["creation_token"], allow_terminate=True)
            elif self.platform == "posix" and runtime["pid"] == self.launcher.pid:
                witness = self.launcher
            else:
                raise RuntimeError("No independent exit witness for indirect POSIX runtime")
            if time.monotonic() >= deadline:
                if witness is not self.launcher:
                    witness.close()
                raise RuntimeError("Runtime identity binding timed out")
            self.runtime_identity, self.lineage, self.runtime_handle = runtime, binding["lineage"], witness
            self.pid, self.identity_verified = runtime["pid"], True
            if self.acknowledgement_path is not None:
                write_json(self.acknowledgement_path, {"nonce": self.nonce, "identity": runtime})
        except Exception as exc:
            self.identity_error = type(exc).__name__ + ": " + str(exc)
            if self.runtime_handle is not None and self.runtime_handle is not self.launcher:
                self.runtime_handle.close()
            self.runtime_handle = None
            self.runtime_identity = None
            self.identity_verified = False
            self.lineage = []
            self.pid = self.launcher.pid
            raise

    def poll(self):
        return self.runtime_handle.poll() if self.identity_verified else None

    def wait(self, timeout):
        if not self.identity_verified:
            # Controlled stop may still let the launcher exit, but proves no runtime exit.
            self.launcher.wait(timeout=timeout)
            return None
        return self.runtime_handle.wait(timeout=timeout)

    def terminate(self):
        if not self.identity_verified:
            raise RuntimeError("Refusing termination without bound runtime identity")
        self.runtime_handle.terminate()

    def kill(self):
        if not self.identity_verified:
            raise RuntimeError("Refusing kill without bound runtime identity")
        self.runtime_handle.kill()

    def close(self):
        if self.runtime_handle is not None and self.runtime_handle is not self.launcher:
            self.runtime_handle.close()
