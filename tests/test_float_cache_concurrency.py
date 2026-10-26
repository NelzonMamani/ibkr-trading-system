"""Offline publication/reader ownership, including a native Windows cause control."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.market_data import float_provider as module

BASELINE = 'a13cb2314f2e1827032d3a47a94e7c8fd7ca3156'


def test_publication_holds_metadata_gate_until_replace_finishes(monkeypatch, tmp_path):
    provider = module.FloatProvider(cache_path=tmp_path/'float.json', sqlite_path=str(tmp_path/'float.db'))
    replace = os.replace
    checks = []
    def publish(*args):
        # A second thread models another provider resolving its lock identity.
        def probe():
            acquired = module._CACHE_LOCKS_GUARD.acquire(blocking=False)
            checks.append(acquired)
            if acquired:
                module._CACHE_LOCKS_GUARD.release()
        thread = threading.Thread(target=probe)
        thread.start(); thread.join(3)
        assert not thread.is_alive()
        return replace(*args)
    monkeypatch.setattr(module.os, 'replace', publish)
    provider.record_discovery('ONE', 1, 'FIXTURE')
    assert checks == [False]


@pytest.mark.parametrize('reader', ['provider', 'constructor', 'scanner', 'mock'])
def test_cache_read_handles_close_before_publication(monkeypatch, tmp_path, reader):
    from src.scanner import scanner_runner
    from src.scanner.providers import mock_provider
    cache, db = tmp_path/'float.json', str(tmp_path/'float.db')
    provider = module.FloatProvider(cache_path=cache, sqlite_path=db)
    provider.record_discovery('OLD', 1, 'FIXTURE')
    opened, release = threading.Event(), threading.Event()
    read_text = Path.read_text
    def held_read(path, *args, **kwargs):
        if path == cache and threading.current_thread().name.startswith('cache-reader'):
            with path.open(encoding='utf-8') as handle:
                opened.set()
                assert release.wait(3), 'reader release missing'
                return handle.read()
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', held_read)
    readers = {
        'provider': provider._load_cache,
        'constructor': lambda: module.FloatProvider(cache_path=cache, sqlite_path=db),
        'scanner': lambda: scanner_runner._load_float_cache(cache),
        'mock': lambda: mock_provider._load_float_cache(cache),
    }
    with ThreadPoolExecutor(1, thread_name_prefix='cache-reader') as pool:
        future = pool.submit(readers[reader])
        try:
            assert opened.wait(3)
            # No metadata resolution or publication may pass an owned read handle.
            acquired = module._CACHE_LOCKS_GUARD.acquire(blocking=False)
            if acquired:
                module._CACHE_LOCKS_GUARD.release()
            assert not acquired
        finally:
            release.set()
        future.result(timeout=3)
    provider.record_discovery('NEW', 2, 'FIXTURE')
    assert set(json.loads(cache.read_text())) == {'OLD', 'NEW'}


def test_aliases_merge_and_permission_failure_remains_fail_closed(monkeypatch, tmp_path):
    cache, db = tmp_path/'float.json', str(tmp_path/'float.db')
    monkeypatch.chdir(tmp_path)
    aliases = [cache, Path('float.json'), tmp_path/'sub'/ '..'/'float.json']
    (tmp_path/'sub').mkdir()
    if os.name == 'nt':
        aliases.append(Path(str(cache).swapcase()))
    providers = [module.FloatProvider(cache_path=p, sqlite_path=db) for p in aliases]
    with ThreadPoolExecutor(4) as pool:
        futures = [pool.submit(p.record_discovery, str(i), i+1, 'FIXTURE') for i,p in enumerate(providers)]
        for future in futures:
            future.result(timeout=3)
    original = cache.read_bytes()
    memory = dict(providers[0]._cache)
    calls = []
    def denied(*args):
        calls.append(args)
        raise PermissionError('external denial fixture')
    monkeypatch.setattr(module.os, 'replace', denied)
    with pytest.raises(PermissionError, match='external denial fixture'):
        providers[0].record_discovery('DENIED', 999, 'FIXTURE')
    assert len(calls) == 1 and cache.read_bytes() == original
    assert providers[0]._cache == memory and not list(tmp_path.glob('*.tmp'))
    assert providers[0]._get_db_float('DENIED') is None
    assert set(json.loads(original)) == {str(i) for i in range(len(aliases))}


@pytest.mark.skipif(os.name != 'nt', reason='native Windows file-sharing semantics')
@pytest.mark.parametrize('legacy', [True, False], ids=['exact-failed-head-control', 'repaired-head'])
def test_windows_resolve_handle_versus_atomic_publication(monkeypatch, tmp_path, legacy):
    """Hold the same share=0 handle as CPython3.13.3 _getfinalpathname.

    Enlarge a known lock-lookup resolution window; do not mock os.replace's
    outcome. This proves a reachable cause, not the uncaptured CI interleaving.
    """
    import ctypes
    from ctypes import wintypes
    selected = module
    if legacy:
        source = subprocess.check_output(['git', 'show', BASELINE+':src/market_data/float_provider.py'])
        file = tmp_path/'legacy_float_provider.py'
        file.write_bytes(source)
        spec = importlib.util.spec_from_file_location('float_cache_failed_head_control', file)
        selected = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, selected)
        spec.loader.exec_module(selected)
    cache, db = tmp_path/'float.json', str(tmp_path/'float.db')
    writer = selected.FloatProvider(cache_path=cache, sqlite_path=db)
    writer.record_discovery('OLD', 1, 'FIXTURE')
    original = cache.read_bytes()
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]; close.restype = wintypes.BOOL
    at_publish, publish, held, close_resolver = (threading.Event() for _ in range(4))
    resolve, replace = Path.resolve, os.replace
    def hold_resolution(path, *args, **kwargs):
        canonical = resolve(path, *args, **kwargs)
        if path == cache and threading.current_thread().name.startswith('cache-resolver'):
            handle = create(str(path), 0, 0, None, 3, 0x02000000, None)
            assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
            try:
                held.set()
                assert close_resolver.wait(5), 'resolver release missing'
            finally:
                assert close(handle)
        return canonical
    def pause_publication(*args):
        at_publish.set()
        assert publish.wait(5), 'publication release missing'
        return replace(*args)
    monkeypatch.setattr(Path, 'resolve', hold_resolution)
    monkeypatch.setattr(os, 'replace', pause_publication)
    def lookup():
        with selected._cache_lock(cache):
            pass
    with ThreadPoolExecutor(1, thread_name_prefix='cache-writer') as writes, \
         ThreadPoolExecutor(1, thread_name_prefix='cache-resolver') as resolvers:
        write = writes.submit(writer.record_discovery, 'NEW', 2, 'FIXTURE')
        try:
            assert at_publish.wait(5)
            lookup_future = resolvers.submit(lookup)
            if legacy:
                assert held.wait(5)
                publish.set()
                with pytest.raises(PermissionError) as error:
                    write.result(timeout=5)
                assert error.value.winerror in (5, 32)
                close_resolver.set()
                lookup_future.result(timeout=5)
                assert cache.read_bytes() == original
                assert writer._get_db_float('NEW') is None
            else:
                acquired = selected._CACHE_LOCKS_GUARD.acquire(blocking=False)
                if acquired:
                    selected._CACHE_LOCKS_GUARD.release()
                assert not acquired
                publish.set()
                write.result(timeout=5)
        finally:
            publish.set(); close_resolver.set()
        lookup_future.result(timeout=5)
    assert not list(tmp_path.glob('*.tmp'))
    if not legacy:
        assert set(json.loads(cache.read_text())) == {'OLD', 'NEW'}
        assert writer._get_db_float('NEW').value == 2
    print(f'NATIVE_WINDOWS_CONTROL legacy={legacy} publication_failed={legacy} handles_closed=True')


def test_scanner_missing_symbol_metadata_stays_inside_publication_gate(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from src.scanner import scanner_runner as scanner
    cache = tmp_path/'float.json'
    cache.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(scanner, '_resolve_float_cache_path', lambda: cache)
    monkeypatch.setattr(scanner, 'get_float_discovery_worker', lambda path: SimpleNamespace(enqueue=lambda symbol: False))
    for name, value in [('_FLOAT_CACHE_STATE', {}), ('_FLOAT_SOURCE_BY_SYMBOL', {}),
                        ('_FLOAT_CACHE_HIT_SYMBOLS', set())]:
        monkeypatch.setattr(scanner, name, value)
    stat = Path.stat
    observations = []
    def checked_stat(path, *args, **kwargs):
        if path == cache:
            def probe():
                acquired = module._CACHE_LOCKS_GUARD.acquire(blocking=False)
                observations.append(acquired)
                if acquired:
                    module._CACHE_LOCKS_GUARD.release()
            thread = threading.Thread(target=probe)
            thread.start(); thread.join(3)
            assert not thread.is_alive()
            assert not observations[-1], 'scanner metadata handle escaped publication gate'
        return stat(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', checked_stat)
    assert scanner._bootstrap_float_cache(['MISSING'], provider=None) == {}
    assert observations and not any(observations)
