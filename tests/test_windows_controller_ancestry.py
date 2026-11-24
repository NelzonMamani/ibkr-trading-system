"""Native parent links preserve controller deadlines without a CIM subprocess."""
import ctypes
import os
from types import SimpleNamespace

import pytest

from src.runtime import process_identity as identity


@pytest.mark.parametrize("case", ["valid", "query_denied", "wrong_size", "wrong_pid", "missing_parent", "self_parent", "exited"])
def test_native_parent_query_uses_retained_object_and_refuses_unverified_metadata(monkeypatch, case):
    handle = object.__new__(identity.WindowsProcessHandle)
    handle.pid, handle.handle = 55, 123
    polls = iter((None, 1 if case == "exited" else None))
    handle.poll = lambda: next(polls)
    calls = []

    def query(process, information_class, data, size, returned):
        calls.append(process)
        assert process == 123 and information_class == 0
        assert size == ctypes.sizeof(identity._WindowsBasicInformation)
        data._obj.UniqueProcessId = 56 if case == "wrong_pid" else 55
        data._obj.InheritedFromUniqueProcessId = 0 if case == "missing_parent" else 55 if case == "self_parent" else 12
        returned._obj.value = size - 1 if case == "wrong_size" else size
        return -1073741790 if case == "query_denied" else 0

    monkeypatch.setattr(identity, "_ntdll", lambda: SimpleNamespace(NtQueryInformationProcess=query))
    monkeypatch.setattr(identity.subprocess, "run", lambda *args, **kwargs: pytest.fail("Parent-only lookup must not start PowerShell/CIM"))
    if case == "valid":
        assert handle.parent_pid() == 12
    else:
        with pytest.raises(RuntimeError):
            handle.parent_pid()
    assert calls == [123]


@pytest.mark.parametrize("case", ["direct", "redirector", "four_intermediates", "too_deep", "reused", "controller_reused", "controller_newer", "exited", "cycle", "late", "query_failure"])
def test_controller_ancestry_retains_handles_bounds_and_creation_order(monkeypatch, case):
    # Current child10 -> redirectors11..14 -> retained controller20.
    links = {10: 20} if case == "direct" else {10: 11, 11: 20}
    if case in ("four_intermediates", "too_deep"):
        links = {10: 11, 11: 12, 12: 13, 13: 14, 14: 20}
        if case == "too_deep":
            links.update({14: 15, 15: 20})
    if case == "cycle":
        links[11] = 10
    times = {10: 100, 11: 90, 12: 80, 13: 70, 14: 60, 15: 50, 20: 10}
    if case == "reused":
        times[11] = 101
    if case == "controller_newer":
        times[20] = 101
    opened, closed, clock = [], [], [0.0]

    class Handle:
        def __init__(self, pid, expected_creation=None, *, query_parent=False):
            self.pid = pid
            assert query_parent == (pid != 20)
            self.creation_token = "windows-filetime:" + str(times[pid])
            if expected_creation is not None and (case == "controller_reused" or self.creation_token != expected_creation):
                raise RuntimeError("creation token changed")
            opened.append(pid)
        def parent_pid(self):
            if case == "query_failure":
                raise RuntimeError("query unavailable")
            if case == "late":
                clock[0] = 3.01
            return links[self.pid]
        def poll(self):
            return 1 if case == "exited" and self.pid == 20 else None
        def close(self):
            closed.append(self.pid)

    monkeypatch.setattr(identity, "WindowsProcessHandle", Handle)
    monkeypatch.setattr(identity, "os", SimpleNamespace(name="nt", getpid=lambda: 10))
    monkeypatch.setattr(identity.time, "monotonic", lambda: clock[0])
    if case in ("direct", "redirector", "four_intermediates"):
        identity.require_live_windows_ancestor(20, "windows-filetime:10")
    else:
        with pytest.raises(RuntimeError):
            identity.require_live_windows_ancestor(20, "windows-filetime:10")
    assert closed == list(reversed(opened))
    if case == "too_deep":
        assert 15 not in opened


def test_native_parent_query_refuses_exited_or_missing_api_before_admission(monkeypatch):
    handle = object.__new__(identity.WindowsProcessHandle)
    handle.pid, handle.handle, handle.poll = 55, 123, lambda: 1
    monkeypatch.setattr(identity, "_ntdll", lambda: pytest.fail("Exited process must not be queried"))
    with pytest.raises(RuntimeError, match="exited before"):
        handle.parent_pid()
    handle.poll = lambda: None
    def unavailable():
        raise AttributeError("unsupported API")
    monkeypatch.setattr(identity, "_ntdll", unavailable)
    with pytest.raises(RuntimeError, match="query unavailable"):
        handle.parent_pid()


@pytest.mark.parametrize("query_parent", [False, True])
def test_parent_query_rights_are_opt_in_without_vm_or_termination(monkeypatch, query_parent):
    calls = []
    api = SimpleNamespace(OpenProcess=lambda access, inherit, pid: calls.append((access, inherit, pid)) or 123,
                          CloseHandle=lambda handle: calls.append(("close", handle)))
    monkeypatch.setattr(identity, "_kernel32", lambda: api)
    monkeypatch.setattr(identity, "_creation_token", lambda api, handle: "windows-filetime:100")
    handle = identity.WindowsProcessHandle(55, query_parent=query_parent)
    handle.close()
    assert calls == [(0x101000 | (0x0400 if query_parent else 0), False, 55), ("close", 123)]


@pytest.mark.skipif(os.name != "nt", reason="actual Windows native parent query")
def test_actual_windows_parent_query_uses_kernel_metadata():
    handle = identity.WindowsProcessHandle(os.getpid(), query_parent=True)
    try:
        assert handle.parent_pid() == os.getppid()
        assert handle.poll() is None
        assert ctypes.sizeof(identity._WindowsBasicInformation) == (48 if ctypes.sizeof(ctypes.c_void_p) == 8 else 24)
    finally:
        handle.close()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True, None, "3"])
def test_invalid_ancestry_budget_starts_no_inspection(monkeypatch, timeout):
    monkeypatch.setattr(identity, "os", SimpleNamespace(name="nt", getpid=lambda: 10))
    monkeypatch.setattr(identity, "WindowsProcessHandle", lambda *args, **kwargs: pytest.fail("Invalid budget cannot inspect processes"))
    with pytest.raises(RuntimeError, match="Unsupported controller ancestry"):
        identity.require_live_windows_ancestor(20, "windows-filetime:10", timeout=timeout)
