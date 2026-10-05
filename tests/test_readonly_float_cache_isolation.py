"""Real cache configuration/persistence with only discovery network calls stubbed."""
import json
import os
import sqlite3
from pathlib import Path

import pytest

from src.config.config_resolver import set_config_overrides
from src.market_data import float_discovery_worker as workers
from src.market_data.float_provider import FloatProvider
from src.scanner import scanner_runner as scanner


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(workers, "_WORKERS", {})
    monkeypatch.setattr(scanner, "_FLOAT_CACHE_STATE", {"mtime_ns": None, "data": {}})
    monkeypatch.setattr(workers.FloatDiscoveryWorker, "ensure_started", lambda self: None)
    monkeypatch.setattr(FloatProvider, "provider_yahoo", lambda self, symbol: (123456, "OK"))
    monkeypatch.setattr(FloatProvider, "provider_finviz", lambda self, symbol: pytest.fail("unexpected fallback"))
    sentinel = Path("data/reference/float_cache.json")
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text('{"OPERATIONAL":{"float":999,"source":"SENTINEL","timestamp":"2099-01-01T00:00:00Z"}}')
    db = Path("data/ibkr_system.db")
    with sqlite3.connect(db) as conn:
        conn.execute("create table sentinel(value text)")
        conn.execute("insert into sentinel values ('unchanged')")
    before = {p: p.read_bytes() for p in [sentinel, db]}
    yield tmp_path
    set_config_overrides(None)
    for p, value in before.items():
        assert p.read_bytes() == value


def configure(cache, db):
    set_config_overrides({"RUN_MODE": "READ_ONLY", "SCANNER_FLOAT_CACHE_FILE": str(cache),
                          "PERSISTENCE_SQLITE_PATH": str(db)})


def test_real_resolver_bootstrap_and_same_cycle_keep_both_stores_isolated(isolated):
    cache, db = isolated / "capture/float.json", isolated / "capture/fund.db"
    configure(cache, db)
    assert scanner._resolve_float_cache_path() == cache
    rows = scanner._bootstrap_float_cache(["BOOT"], provider=None)
    worker = workers.get_float_discovery_worker(scanner._resolve_float_cache_path())
    assert worker._queue.get_nowait() == "BOOT"
    worker._discover_and_cache("BOOT")
    scanner._refresh_float_cache_from_disk_if_changed(float_cache=rows, cache_path=cache)
    assert rows["BOOT"]["float_value"] == 123456
    context = {"symbol": "SAME", "last_price": 7, "bid": 6.99, "ask": 7.01,
               "close": 5, "volume": 1000000}
    proof = scanner._empty_float_discovery_proof()
    scanner._attempt_same_cycle_float_discovery(context, float_cache=rows,
                                               cache_path=scanner._resolve_float_cache_path(), proof=proof)
    assert context["float_shares"] == 123456
    assert set(json.loads(cache.read_text())) == {"BOOT", "SAME"}
    with sqlite3.connect(db) as conn:
        assert conn.execute("select symbol from symbol_fundamentals order by symbol").fetchall() == [("BOOT",), ("SAME",)]


def test_switch_json_paths_equal_mtime_and_missing_path_do_not_reuse_rows(isolated):
    paths = [isolated / "one.json", isolated / "two.json", isolated / "missing.json"]
    for p, symbol in zip(paths, ["ONE", "TWO"]):
        p.write_text(json.dumps({symbol: {"float": 123456, "source": "FIXTURE", "timestamp": "2099-01-01T00:00:00Z"}}))
        os.utime(p, ns=(1000000000, 1000000000))
    for p, expected in zip(paths, [{"ONE"}, {"TWO"}, set()]):
        configure(p, isolated / (p.stem + ".db"))
        assert set(scanner._bootstrap_float_cache([], provider=None)) == expected


def test_worker_identity_includes_sqlite_path(isolated):
    cache = isolated / "same.json"
    configure(cache, isolated / "first.db")
    first = workers.get_float_discovery_worker(cache)
    first.discover_now("FIRST")
    configure(cache, isolated / "second.db")
    second = workers.get_float_discovery_worker(cache)
    assert second is not first
    second.discover_now("SECOND")
    with sqlite3.connect(isolated / "first.db") as conn:
        assert conn.execute("select symbol from symbol_fundamentals").fetchall() == [("FIRST",)]
    with sqlite3.connect(isolated / "second.db") as conn:
        assert conn.execute("select symbol from symbol_fundamentals").fetchall() == [("SECOND",)]


def test_default_cache_path_is_preserved(monkeypatch):
    monkeypatch.delenv("SCANNER_FLOAT_CACHE_FILE", raising=False)
    set_config_overrides({"RUN_MODE": "READ_ONLY"})
    try:
        assert scanner._resolve_float_cache_path() == Path("data/reference/float_cache.json")
    finally:
        set_config_overrides(None)


def test_refresh_switches_path_even_when_mtime_matches(isolated):
    first, second = isolated / "a.json", isolated / "b.json"
    for path, symbol in [(first, "A"), (second, "B")]:
        path.write_text(json.dumps({symbol: {"float": 123, "source": "FIXTURE"}}))
        os.utime(path, ns=(1000000000, 1000000000))
    configure(first, isolated / "isolated.db")
    rows = scanner._bootstrap_float_cache([], provider=None)
    configure(second, isolated / "isolated.db")
    assert scanner._refresh_float_cache_from_disk_if_changed(
        float_cache=rows, cache_path=scanner._resolve_float_cache_path())
    assert set(rows) == {"B"}


def test_ibkr_float_fallback_honors_configured_json_and_sqlite(isolated, monkeypatch):
    from src.scanner.providers.ibkr_provider import IbkrScannerProvider
    cache, db = isolated / "provider/float.json", isolated / "provider/fund.db"
    configure(cache, db)
    provider = IbkrScannerProvider.__new__(IbkrScannerProvider)
    provider.market_data_client = None
    provider.last_scan_details = {}
    monkeypatch.setattr(provider, "_fetch_yahoo_float_detailed", lambda symbol: (234567, "OK"))
    monkeypatch.setattr(provider, "_fetch_finviz_float_detailed", lambda symbol: (None, "NOT_NEEDED"))
    monkeypatch.setattr(provider, "_fetch_ibkr_float_detailed", lambda symbol: (None, "NOT_NEEDED"))
    assert provider.get_float("DIRECT") == 234567
    assert json.loads(cache.read_text())["DIRECT"]["float"] == 234567
    with sqlite3.connect(db) as conn:
        assert conn.execute("select float from symbol_fundamentals where symbol='DIRECT'").fetchone() == (234567,)
