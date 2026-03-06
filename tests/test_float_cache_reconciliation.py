from pathlib import Path

from src.scanner import scanner_runner


class _Provider:
    source_name = "TEST"

    def __init__(self, values: dict[str, int | None]) -> None:
        self.values = values
        self.last_float_source = "YAHOO_FINANCE"
        self.calls = 0

    def get_float(self, symbol: str):
        self.calls += 1
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


def test_float_cache_second_pass_uses_cache_without_refetch(monkeypatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(scanner_runner, "get_config", lambda key: str(cache_file) if key == "SCANNER_FLOAT_CACHE_FILE" else {})
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}
    scanner_runner._FLOAT_CACHE_REQUESTED.clear()

    provider = _Provider({"MSFT": 3_000_000})
    out1 = scanner_runner._bootstrap_float_cache(["MSFT"], provider)
    assert out1["MSFT"]["float_value"] == 3_000_000
    assert provider.calls == 1

    scanner_runner._FLOAT_CACHE_REQUESTED.clear()
    out2 = scanner_runner._bootstrap_float_cache(["MSFT"], provider)
    assert out2["MSFT"]["float_value"] == 3_000_000
    assert provider.calls == 1
    assert "MSFT" in scanner_runner._FLOAT_CACHE_HIT_SYMBOLS


def test_float_cache_missing_logs_provider_reasons(monkeypatch, tmp_path: Path, capsys) -> None:
    class _ReasonProvider(_Provider):
        def __init__(self) -> None:
            super().__init__({"PRSO": None})
            self.last_float_failures = [("FINVIZ", "FIELD_NOT_FOUND"), ("YAHOO_FINANCE", "PARSE_ERROR")]

    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(scanner_runner, "get_config", lambda key: str(cache_file) if key == "SCANNER_FLOAT_CACHE_FILE" else {})
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}
    scanner_runner._FLOAT_CACHE_REQUESTED.clear()

    scanner_runner._bootstrap_float_cache(["PRSO"], _ReasonProvider())
    out = capsys.readouterr().out
    assert "[FLOAT][FETCH_FAIL] symbol=PRSO provider=FINVIZ reason=FIELD_NOT_FOUND" in out
    assert "[FLOAT][FETCH_FAIL] symbol=PRSO provider=YAHOO_FINANCE reason=PARSE_ERROR" in out
