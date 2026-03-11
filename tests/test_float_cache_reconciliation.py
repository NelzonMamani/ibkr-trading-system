from pathlib import Path

from src.scanner import scanner_runner


class _WorkerStub:
    def __init__(self) -> None:
        self.queued: list[str] = []

    def enqueue(self, symbol: str) -> bool:
        if symbol in self.queued:
            return False
        self.queued.append(symbol)
        return True


def test_float_cache_hit_uses_cache_only(monkeypatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text(
        '{"AAPL": {"float_value": 1000000, "float_source": "FINVIZ", "float_asof": "2025-01-01T00:00:00+00:00"}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(scanner_runner, "_resolve_float_cache_path", lambda: cache_file)
    worker = _WorkerStub()
    monkeypatch.setattr(scanner_runner, "get_float_discovery_worker", lambda path: worker)
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}

    out = scanner_runner._bootstrap_float_cache(["AAPL"], provider=None)

    assert out["AAPL"]["float_value"] == 1_000_000
    assert scanner_runner._FLOAT_SOURCE_BY_SYMBOL["AAPL"] == "FINVIZ"
    assert worker.queued == []


def test_float_cache_missing_marks_unknown_and_queues(monkeypatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(scanner_runner, "_resolve_float_cache_path", lambda: cache_file)
    worker = _WorkerStub()
    monkeypatch.setattr(scanner_runner, "get_float_discovery_worker", lambda path: worker)
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}

    out = scanner_runner._bootstrap_float_cache(["ZZZZ"], provider=None)

    assert "ZZZZ" not in out or out["ZZZZ"].get("float_value") is None
    assert scanner_runner._FLOAT_SOURCE_BY_SYMBOL["ZZZZ"] == "UNKNOWN"
    assert worker.queued == ["ZZZZ"]


def test_float_cache_missing_queue_only_once(monkeypatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(scanner_runner, "_resolve_float_cache_path", lambda: cache_file)
    worker = _WorkerStub()
    monkeypatch.setattr(scanner_runner, "get_float_discovery_worker", lambda path: worker)
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}

    scanner_runner._bootstrap_float_cache(["MSFT"], provider=None)
    scanner_runner._bootstrap_float_cache(["MSFT"], provider=None)

    assert worker.queued == ["MSFT"]
