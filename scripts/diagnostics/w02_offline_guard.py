"""Block external/broker sockets; allow only stdlib socketpair self-pipes."""
import json
from pathlib import Path
import socket
import threading

_originals = {}
_attempts = []
_lock = threading.Lock()
_current_test = None
_socketpair_state = threading.local()
_self_pipe_connections = 0


def pytest_addoption(parser):
    parser.addoption("--w02-network-audit", default=None)


def _deny(*args, **kwargs):
    with _lock:
        _attempts.append({"test": _current_test, "outcome": "blocked_before_connection"})
    raise OSError("W02_OFFLINE_NETWORK_DISABLED")


def _connect(sock, address):
    global _self_pipe_connections
    # Windows implements stdlib socketpair via a private loopback listener.
    # Only that synchronous stdlib call is exempt; ordinary localhost/broker
    # connections still fail closed, including from other threads.
    if getattr(_socketpair_state, "active", False) and isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
        _self_pipe_connections += 1
        return _originals[(socket.socket, "connect")](sock, address)
    return _deny(sock, address)


def _socketpair(*args, **kwargs):
    previous = getattr(_socketpair_state, "active", False)
    _socketpair_state.active = True
    try:
        return _originals[(socket, "socketpair")](*args, **kwargs)
    finally:
        _socketpair_state.active = previous


def pytest_sessionstart(session):
    global _self_pipe_connections
    _attempts.clear()
    _self_pipe_connections = 0
    for owner, name, replacement in ((socket.socket, "connect", _connect), (socket.socket, "connect_ex", _deny), (socket, "create_connection", _deny), (socket, "socketpair", _socketpair)):
        _originals[(owner, name)] = getattr(owner, name)
        setattr(owner, name, replacement)


def pytest_runtest_logstart(nodeid, location):
    global _current_test
    _current_test = nodeid


def pytest_sessionfinish(session, exitstatus):
    path = session.config.getoption("--w02-network-audit")
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"guard": "external/broker sockets blocked; stdlib private socketpair self-pipes allowed", "attempts": _attempts,
                                      "stdlib_socketpair_connections": _self_pipe_connections,
                                      "exit_status": int(exitstatus)}, indent=2), encoding="utf-8")
    for (owner, name), value in _originals.items():
        setattr(owner, name, value)
