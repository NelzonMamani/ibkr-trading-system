from src.data.fundamentals.float_provider import FloatProvider


def test_parse_shares_value_suffixes() -> None:
    assert FloatProvider._parse_shares_value("1.2B") == 1_200_000_000
    assert FloatProvider._parse_shares_value("12.5M") == 12_500_000
    assert FloatProvider._parse_shares_value("300K") == 300_000


def test_get_float_uses_cache(monkeypatch, tmp_path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text('{"PRSO": {"float": 14500000, "source": "FINVIZ", "timestamp": "2099-01-01T00:00:00+00:00"}}', encoding="utf-8")

    provider = FloatProvider(cache_path=cache_file, sqlite_path=str(tmp_path / "fund.db"))
    monkeypatch.setattr(provider, "provider_yahoo", lambda symbol: (None, "REQUEST_ERROR"))
    monkeypatch.setattr(provider, "provider_finviz", lambda symbol: (None, "REQUEST_ERROR"))

    value, source = provider.get_float("PRSO")
    assert value == 14_500_000
    assert source == "FINVIZ"
