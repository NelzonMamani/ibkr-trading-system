from src.market_data.float_provider import FloatProvider


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


def test_get_float_uses_last_known_good_when_stale_and_live_fetch_fails(monkeypatch, tmp_path) -> None:
    cache_file = tmp_path / "float_cache.json"
    cache_file.write_text(
        '{"PRSO": {"float": 14500000, "source": "FINVIZ", "timestamp": "2020-01-01T00:00:00+00:00"}}',
        encoding="utf-8",
    )
    provider = FloatProvider(cache_path=cache_file, sqlite_path=str(tmp_path / "fund.db"), ttl_days=7)
    monkeypatch.setattr(provider, "provider_yahoo", lambda symbol: (None, "REQUEST_ERROR"))
    monkeypatch.setattr(provider, "provider_finviz", lambda symbol: (None, "REQUEST_ERROR"))

    value, source = provider.get_float("PRSO")
    assert value == 14_500_000
    assert source == "FINVIZ"


def test_independent_providers_merge_discoveries_in_shared_cache(tmp_path):
    import json
    cache, db = tmp_path / "float.json", str(tmp_path / "float.db")
    first = FloatProvider(cache_path=cache, sqlite_path=db)
    second = FloatProvider(cache_path=cache, sqlite_path=db)
    first.record_discovery("FIRST", 111, "FIXTURE")
    original = json.loads(cache.read_text())["FIRST"]
    second.record_discovery("SECOND", 222, "FIXTURE")
    saved = json.loads(cache.read_text())
    assert saved["FIRST"] == original
    assert saved["SECOND"]["float"] == 222


def test_concurrent_provider_writes_preserve_all_discoveries(tmp_path):
    import json
    from concurrent.futures import ThreadPoolExecutor
    cache, db = tmp_path / "float.json", str(tmp_path / "float.db")
    providers = [FloatProvider(cache_path=cache, sqlite_path=db) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(provider.record_discovery, f"SYM{i}", i + 1, "FIXTURE")
                   for i, provider in enumerate(providers)]
        for future in futures:
            future.result()
    saved = json.loads(cache.read_text())
    assert {symbol: row["float"] for symbol, row in saved.items()} == {f"SYM{i}": i + 1 for i in range(8)}
