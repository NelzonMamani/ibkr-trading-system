"""Subprocess checks exercise the real startup audit hook, including Windows."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def child(code):
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT / 'tests' / 'offline'), str(ROOT)])
    result = subprocess.run([sys.executable, '-c', code], env=env, cwd=ROOT,
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_default_asyncio_policy_and_main_import_collect_on_guarded_child():
    child('''
import asyncio, sys
policy = asyncio.get_event_loop_policy()
loop = asyncio.new_event_loop()
try:
    assert loop.run_until_complete(asyncio.sleep(0, result=42)) == 42
    if sys.platform == 'win32':
        assert isinstance(loop, asyncio.ProactorEventLoop)
finally:
    loop.close()
from src import main
assert asyncio.get_event_loop_policy() is policy
main.loop.close()
''')


def test_stdlib_tcp_socketpair_and_fallback_asyncio_work_without_loopback_bypass():
    child('''
import asyncio, socket
# Exercise the Windows TCP fallback on Linux too, rather than native AF_UNIX.
a, b = socket._fallback_socketpair()
try:
    a.sendall(b'ok')
    assert b.recv(2) == b'ok'
    target = a.getsockname()
    with socket.socket() as unrelated:
        try:
            unrelated.connect(target)
        except OSError as error:
            assert str(error) == 'OFFLINE_CI: network acquisition disabled'
        else:
            raise AssertionError('ordinary loopback connection escaped')
finally:
    a.close()
    b.close()
# Exercise asyncio through that same fallback, preserving the default policy.
socket.socketpair = socket._fallback_socketpair
loop = asyncio.new_event_loop()
try:
    assert loop.run_until_complete(asyncio.sleep(0, result=42)) == 42
finally:
    loop.close()
''')


@pytest.mark.parametrize('method', ['connect', 'connect_ex'])
@pytest.mark.parametrize('target', [('203.0.113.1', 443), ('127.0.0.1', 4001),
    ('127.0.0.1', 4002), ('127.0.0.1', 7496), ('127.0.0.1', 7497), ('localhost', 7497),
    ('::1', 4001), ('::1', 4002), ('::1', 7496), ('::1', 7497)])
def test_external_and_ibkr_connections_remain_blocked(method, target):
    child(f'''
import socket
with socket.socket(socket.AF_INET6 if {target[0]!r} == '::1' else socket.AF_INET) as connection:
    try:
        connection.{method}({target!r})
    except OSError as error:
        assert str(error) == 'OFFLINE_CI: network acquisition disabled'
    else:
        raise AssertionError('network connection escaped')
''')


def test_dns_datagram_and_grandchild_guard():
    child('''
import socket, subprocess, sys
for operation in [lambda: socket.getaddrinfo('example.invalid', 443),
                  lambda: socket.socket(type=socket.SOCK_DGRAM).sendto(b'x', ('127.0.0.1', 7497))]:
    try:
        operation()
    except OSError as error:
        assert str(error) == 'OFFLINE_CI: network acquisition disabled'
    else:
        raise AssertionError('acquisition escaped')
code = """
import asyncio, socket
loop = asyncio.new_event_loop()
loop.close()
with socket.socket() as connection:
    try:
        connection.connect(('127.0.0.1', 7497))
    except OSError as error:
        assert str(error) == 'OFFLINE_CI: network acquisition disabled'
    else:
        raise AssertionError('child lost offline guard')
"""
result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=15)
assert result.returncode == 0, result.stdout + result.stderr
''')
