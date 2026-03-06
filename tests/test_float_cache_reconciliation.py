from pathlib import Path

from src.scanner import scanner_runner


class _Provider:
    source_name = "TEST"

    def __init__(self, values: dict[str, int | None]) -> None:
        self.values = values
        self.last_float_source = "YAHOO_FINANCE"

    def get_float(self, symbol: str):
        value = self.values.get(symbol)
        if value is None:
            self.last_float_source = None
        return value


def test_float_cache_hit_and_provider_fetch(monkeypatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text('{"AAPL": {"float_value": 1000000, "float_source": "FINVIZ", "float_asof": "2025-01-01T00:00:00+00:00"}}', encoding="utf-8")

    monkeypatch.setattr(scanner_runner, "get_config", lambda key: str(cache_file) if key == "SCANNER_FLOAT_CACHE_FILE" else {})
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}
    scanner_runner._FLOAT_CACHE_REQUESTED.clear()

    out = scanner_runner._bootstrap_float_cache(["AAPL", "MSFT"], _Provider({"MSFT": 2_000_000}))

    assert out["AAPL"]["float_value"] == 1_000_000
    assert out["MSFT"]["float_value"] == 2_000_000
    assert out["MSFT"]["float_source"] == "YAHOO_FINANCE"


def test_float_cache_missing_explicit(monkeypatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(scanner_runner, "get_config", lambda key: str(cache_file) if key == "SCANNER_FLOAT_CACHE_FILE" else {})
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}
    scanner_runner._FLOAT_CACHE_REQUESTED.clear()

    out = scanner_runner._bootstrap_float_cache(["ZZZZ"], _Provider({"ZZZZ": None}))
    assert "ZZZZ" not in out or out["ZZZZ"].get("float_value") is None
    assert scanner_runner._FLOAT_SOURCE_BY_SYMBOL["ZZZZ"] == "missing"
