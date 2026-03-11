from pathlib import Path

from src.scanner import scanner_runner


class _FloatProviderStub:
    def __init__(self, values: dict[str, tuple[int | None, str]]) -> None:
        self.values = values
        self.calls = 0
        self.last_float_failures = []

    def get_float(self, symbol: str):
        self.calls += 1
        value, source = self.values.get(symbol, (None, "UNKNOWN"))
        if value is None:
            self.last_float_failures = [("YAHOO", "FIELD_NOT_FOUND"), ("FINVIZ", "FIELD_NOT_FOUND")]
        else:
            self.last_float_failures = []
        return value, source


def test_float_cache_hit_and_provider_fetch(monkeypatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text('{"AAPL": {"float_value": 1000000, "float_source": "FINVIZ", "float_asof": "2025-01-01T00:00:00+00:00"}}', encoding="utf-8")

    monkeypatch.setattr(scanner_runner, "get_config", lambda key: str(cache_file) if key == "SCANNER_FLOAT_CACHE_FILE" else {})
    stub = _FloatProviderStub({"MSFT": (2_000_000, "YAHOO")})
    monkeypatch.setattr(scanner_runner, "FloatProvider", lambda cache_path=None: stub)
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}
    scanner_runner._FLOAT_CACHE_REQUESTED.clear()

    out = scanner_runner._bootstrap_float_cache(["AAPL", "MSFT"], provider=None)

    assert out["AAPL"]["float_value"] == 1_000_000
    assert out["MSFT"]["float_value"] == 2_000_000
    assert out["MSFT"]["float_source"] == "YAHOO"


def test_float_cache_missing_explicit(monkeypatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(scanner_runner, "get_config", lambda key: str(cache_file) if key == "SCANNER_FLOAT_CACHE_FILE" else {})
    stub = _FloatProviderStub({"ZZZZ": (None, "UNKNOWN")})
    monkeypatch.setattr(scanner_runner, "FloatProvider", lambda cache_path=None: stub)
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}
    scanner_runner._FLOAT_CACHE_REQUESTED.clear()

    out = scanner_runner._bootstrap_float_cache(["ZZZZ"], provider=None)
    assert "ZZZZ" not in out or out["ZZZZ"].get("float_value") is None
    assert scanner_runner._FLOAT_SOURCE_BY_SYMBOL["ZZZZ"] == "missing"


def test_float_cache_second_pass_uses_cache_without_refetch(monkeypatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(scanner_runner, "get_config", lambda key: str(cache_file) if key == "SCANNER_FLOAT_CACHE_FILE" else {})
    stub = _FloatProviderStub({"MSFT": (3_000_000, "YAHOO")})
    monkeypatch.setattr(scanner_runner, "FloatProvider", lambda cache_path=None: stub)
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}
    scanner_runner._FLOAT_CACHE_REQUESTED.clear()

    out1 = scanner_runner._bootstrap_float_cache(["MSFT"], provider=None)
    assert out1["MSFT"]["float_value"] == 3_000_000
    assert stub.calls == 1

    scanner_runner._FLOAT_CACHE_REQUESTED.clear()
    out2 = scanner_runner._bootstrap_float_cache(["MSFT"], provider=None)
    assert out2["MSFT"]["float_value"] == 3_000_000
    assert stub.calls == 1
    assert "MSFT" in scanner_runner._FLOAT_CACHE_HIT_SYMBOLS


def test_float_cache_missing_logs_provider_reasons(monkeypatch, tmp_path: Path, capsys) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(scanner_runner, "get_config", lambda key: str(cache_file) if key == "SCANNER_FLOAT_CACHE_FILE" else {})
    stub = _FloatProviderStub({"PRSO": (None, "UNKNOWN")})
    monkeypatch.setattr(scanner_runner, "FloatProvider", lambda cache_path=None: stub)
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}
    scanner_runner._FLOAT_CACHE_REQUESTED.clear()

    scanner_runner._bootstrap_float_cache(["PRSO"], provider=None)
    out = capsys.readouterr().out
    assert "[FLOAT][FETCH_FAIL] symbol=PRSO provider=YAHOO reason=FIELD_NOT_FOUND" in out
    assert "[FLOAT][FETCH_FAIL] symbol=PRSO provider=FINVIZ reason=FIELD_NOT_FOUND" in out


def test_float_cache_retry_after_cooldown(monkeypatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(scanner_runner, "get_config", lambda key: str(cache_file) if key == "SCANNER_FLOAT_CACHE_FILE" else (1 if key == "SCANNER_FLOAT_RETRY_COOLDOWN_SECONDS" else {}))

    class _RetryStub:
        def __init__(self):
            self.calls = 0
            self.last_float_failures = []

        def get_float(self, symbol: str):
            self.calls += 1
            if self.calls == 1:
                self.last_float_failures = [("YAHOO", "TEMP_HTTP_503")]
                return None, "UNKNOWN"
            self.last_float_failures = []
            return 4_000_000, "YAHOO"

    stub = _RetryStub()
    monkeypatch.setattr(scanner_runner, "FloatProvider", lambda cache_path=None: stub)
    scanner_runner._FLOAT_CACHE_STATE = {"as_of": None, "data": {}}
    scanner_runner._FLOAT_CACHE_REQUESTED.clear()
    scanner_runner._FLOAT_FETCH_STATE.clear()

    out1 = scanner_runner._bootstrap_float_cache(["CYN"], provider=None)
    assert "CYN" not in out1 or out1["CYN"].get("float_value") is None

    out2 = scanner_runner._bootstrap_float_cache(["CYN"], provider=None)
    assert "CYN" not in out2 or out2["CYN"].get("float_value") is None

    state = scanner_runner._FLOAT_FETCH_STATE["CYN"]
    state["retry_after"] = state["last_attempt_at"]

    out3 = scanner_runner._bootstrap_float_cache(["CYN"], provider=None)
    assert out3["CYN"]["float_value"] == 4_000_000
    assert scanner_runner._FLOAT_FETCH_STATE["CYN"]["fetch_state"] == "SUCCESS"
