import importlib
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

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


# Optional-source packages must not become MOCK/SIM startup prerequisites.
def test_sim_mock_cycle_without_optional_float_packages_or_credentials(tmp_path):
    code = r'''
import importlib.abc, importlib.util, os, sys
from pathlib import Path
class Missing(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'requests', 'bs4', 'yfinance'}:
            raise ModuleNotFoundError('optional package blocked', name=fullname.split('.')[0])
assert all(name not in sys.modules for name in ('requests','bs4','yfinance'))
sys.meta_path.insert(0, Missing())
original_find_spec=importlib.util.find_spec
importlib.util.find_spec=lambda name,*a,**kw: (None if name.split('.')[0] in
    {'requests','bs4','yfinance'} else original_find_spec(name,*a,**kw))
for key in ('MASSIVE_API_KEY','POLYGON_API_KEY'):
    os.environ.pop(key, None)
from ibapi.client import EClient
def forbidden(*args, **kwargs):
    raise AssertionError('broker connection/mutation forbidden')
for name in ('connect','placeOrder','cancelOrder','reqGlobalCancel'):
    setattr(EClient, name, forbidden)
from src.config.config_resolver import set_config_overrides
scratch=Path(sys.argv[1])
set_config_overrides({'RUN_MODE':'SIM','SCANNER_DATA_SOURCE':'MOCK',
    'NEWS_ENABLED':False,'HISTORICAL_ENRICH_ENABLED':False,
    'SCANNER_FLOAT_CACHE_FILE':str(scratch/'float.json'),
    'PERSISTENCE_SQLITE_PATH':str(scratch/'state.db')})
from src.scanner import scanner_runner
payload=scanner_runner.run_scanner_cycle(mode='integrated')
assert payload['diagnostics']['provider_source']=='MOCK'
assert all(name not in sys.modules for name in ('requests','bs4','yfinance'))
print('SIM_MOCK_OPTIONAL_PACKAGES_ABSENT_PASS')
'''
    child = subprocess.run([sys.executable, "-c", code, str(tmp_path)],
                           cwd=Path(__file__).resolve().parents[1], capture_output=True,
                           text=True, timeout=15)
    assert child.returncode == 0, child.stderr
    assert "SIM_MOCK_OPTIONAL_PACKAGES_ABSENT_PASS" in child.stdout.splitlines()


@pytest.mark.parametrize("provider,missing,reason", [
    ("provider_yahoo", "yfinance", "YFINANCE_UNAVAILABLE"),
    ("provider_finviz", "requests", "REQUESTS_UNAVAILABLE"),
    ("provider_finviz", "bs4", "BEAUTIFULSOUP_UNAVAILABLE"),
])
def test_selected_missing_source_package_has_explicit_result(monkeypatch, provider, missing, reason):
    from src.market_data import float_provider as owner
    original = importlib.import_module
    calls = []
    def load(name):
        calls.append(name)
        if name == missing:
            raise ModuleNotFoundError("synthetic missing package", name=name)
        return original(name)
    monkeypatch.setattr(owner.importlib, "import_module", load)
    source = FloatProvider.__new__(FloatProvider)
    assert getattr(source, provider)("FIXTURE") == (None, reason)
    assert calls[-1] == missing


@pytest.mark.parametrize("provider,module", [("provider_yahoo", "yfinance"), ("provider_finviz", "requests")])
@pytest.mark.parametrize("error", [ModuleNotFoundError("broken dependency", name="unrelated_dependency"),
                                   ImportError("broken installed package"), RuntimeError("initialization failure")])
def test_unrelated_import_failures_are_not_reported_as_absent(monkeypatch, provider, module, error):
    from src.market_data import float_provider as owner
    def load(name):
        assert name == module
        raise error
    monkeypatch.setattr(owner.importlib, "import_module", load)
    with pytest.raises(type(error)) as raised:
        getattr(FloatProvider.__new__(FloatProvider), provider)("FIXTURE")
    assert raised.value is error


def test_missing_source_packages_preserve_unknown_float_and_failure_details(monkeypatch, tmp_path):
    from src.market_data import float_provider as owner
    provider = FloatProvider(cache_path=tmp_path/'float.json', sqlite_path=str(tmp_path/'state.db'))
    def missing(name):
        raise ModuleNotFoundError("synthetic missing package", name=name)
    monkeypatch.setattr(owner.importlib, "import_module", missing)
    assert provider.get_float("FIXTURE") == (None, "UNKNOWN")
    assert provider.last_float_failures == [("YAHOO", "YFINANCE_UNAVAILABLE"), ("FINVIZ", "REQUESTS_UNAVAILABLE")]
    assert not provider.cache_path.exists()


def test_cached_float_loads_no_optional_source_packages(monkeypatch, tmp_path):
    from src.market_data import float_provider as owner
    provider = FloatProvider(cache_path=tmp_path/'float.json', sqlite_path=str(tmp_path/'state.db'))
    provider.record_discovery("FIXTURE", 12345, "SYNTHETIC")
    def forbidden(name):
        pytest.fail("cache hit must not load a provider")
    monkeypatch.setattr(owner, "_optional_provider_module", forbidden)
    assert provider.get_float("FIXTURE") == (12345, "SYNTHETIC")


def test_installed_yahoo_and_finviz_paths_keep_parsing_and_request_contract(monkeypatch):
    import requests
    import yfinance
    calls = []
    monkeypatch.setattr(yfinance, "Ticker", lambda symbol: SimpleNamespace(info={"floatShares":12345}))
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(content=b'<table class="snapshot-table2"><tr><td>Float</td><td>12.5M</td></tr></table>')
    monkeypatch.setattr(requests, "get", get)
    provider = FloatProvider.__new__(FloatProvider)
    assert provider.provider_yahoo("FIXTURE") == (12345, "OK")
    assert calls == []  # Yahoo success does not select Finviz.
    assert provider.provider_finviz("FIXTURE") == (12500000, "OK")
    assert calls == [("https://finviz.com/quote.ashx?t=FIXTURE", {"headers":{"User-Agent":"Mozilla/5.0"}, "timeout":8})]


@pytest.mark.parametrize("source", ["AUTO", "IBKR"])
def test_real_scanner_selection_preserves_owned_provider_connect(monkeypatch, source):
    from src.scanner.providers import factory, ibkr_provider
    from src.config.runtime_config import RunMode
    calls = []
    class InstalledProvider:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def connect(self):
            calls.append("connect")
    monkeypatch.setattr(factory, "_source_mode", lambda:source)
    monkeypatch.setattr(factory, "get_run_mode", lambda:RunMode.READ_ONLY)
    monkeypatch.setattr(ibkr_provider, "IbkrScannerProvider", InstalledProvider)
    client, connection = object(), object()
    assert isinstance(factory.build_provider(market_data_client=client, connection_manager=connection), InstalledProvider)
    assert calls == [{"connection_manager":connection, "market_data_client":client}, "connect"]
