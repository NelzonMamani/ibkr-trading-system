"""Managed qualification response reuse; all broker callbacks are synthetic."""
from types import SimpleNamespace
import pytest
from ibapi.contract import Contract, ContractDetails
from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.ibkr.market_data_client import MarketDataClient
from src.scanner.providers.ibkr_provider import IbkrScannerProvider
from src.config.config_resolver import set_config_overrides
from src.scanner import scanner_runner as scanner
from src.news.batch_rss_adapter import _metadata_by_symbol
from src.news.news_fetcher import company_aliases_for_symbol
from test_ibkr_provider_contract_pipeline import DummyMarketDataClient
from test_scanner_pct_change_fallback import _BaseProvider


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    set_config_overrides({"RUN_MODE": "READ_ONLY", "SCANNER_FLOAT_CACHE_FILE": str(tmp_path / "float.json"),
        "NEWS_CACHE_FILE": str(tmp_path / "news.json"), "PERSISTENCE_SQLITE_PATH": str(tmp_path / "runtime.sqlite3")})
    yield
    set_config_overrides(None)


def contract(symbol="ONE", con_id=123):
    c = Contract()
    c.symbol, c.conId, c.secType, c.currency = symbol, con_id, "STK", "USD"
    c.exchange, c.primaryExchange, c.localSymbol, c.tradingClass = "SMART", "NASDAQ", symbol, "SCM"
    return c


def setup_client(monkeypatch, mode="ok"):
    client = IbkrClient("127.0.0.1", 7497, 999, 0.001 if mode == "timeout" else 5, "LIVE", True)
    monkeypatch.setattr(client, "is_connected", lambda: True)
    monkeypatch.setattr(client, "isConnected", lambda: True)
    calls = []
    def request(req_id, requested):
        calls.append((req_id, requested))
        if mode == "timeout":
            return
        detail = ContractDetails()
        detail.contract = contract(requested.symbol, 123 if requested.symbol == "ONE" else 456)
        detail.longName = "One Industrial Inc" if requested.symbol == "ONE" else "Two Medical Ltd"
        if mode == "missing": detail.longName = ""
        if mode == "mismatch": detail.contract.conId = 999
        if mode == "currency": detail.contract.currency = "CAD"
        client.contractDetails(req_id, detail)
        if mode == "ambiguous": client.contractDetails(req_id, detail)
        if mode == "error":
            client.error(req_id, 200, "synthetic failure")
        else:
            client.contractDetailsEnd(req_id)
    monkeypatch.setattr(client, "reqContractDetails", request)
    return client, calls


def test_real_managed_provider_to_rss_reuses_qualification(monkeypatch):
    client, calls = setup_client(monkeypatch)
    md = MarketDataClient(connection_manager=SimpleNamespace(get_client=lambda: client), allow_direct_connection=False)
    dummy = DummyMarketDataClient()
    monkeypatch.setattr(md, "snapshot_stock", dummy.snapshot_stock)
    monkeypatch.setattr(md, "daily_bars_from_history", lambda *args, **kwargs: [])
    provider = IbkrScannerProvider(market_data_client=md)
    provider.last_scan_details = {"symbol_details": {s: {"conId": i, "exchange": "SMART", "primaryExchange": "NASDAQ", "currency": "USD"} for s, i in (("ONE",123),("TWO",456))}}
    monkeypatch.setattr(provider, "get_previous_rth_close", lambda identity: 10.0)
    monkeypatch.setattr(provider, "get_average_daily_volume", lambda identity, window: (100000, 20))
    base = _BaseProvider(close=10)
    for name in ("get_intraday_stats", "get_float", "get_daily_bars", "get_prev_close"):
        monkeypatch.setattr(provider, name, getattr(base, name))
    rows = [scanner._build_symbol_context(provider, s, "RTH_MID", float_cache={}) for s in ("ONE", "TWO")]
    candidates = scanner._news_candidates_for_symbols(["ONE", "TWO"], scanner._news_symbol_metadata_for_contexts(rows))
    assert [c.company_name for c in candidates] == ["One Industrial Inc", "Two Medical Ltd"]
    effective = _metadata_by_symbol(candidates)
    assert company_aliases_for_symbol("ONE", effective["ONE"]) == ("ONE INDUSTRIAL",)
    assert company_aliases_for_symbol("TWO", effective["TWO"]) == ("TWO MEDICAL",)
    assert all(c.aliases == () for c in candidates)
    request_count = len(calls)
    for _ in range(2):
        assert md.get_contract_reference_metadata(contract())["longName"] == "One Industrial Inc"
    assert len(calls) == request_count
    from src.news.news_intelligence_contract import NewsBatchResult
    for candidate in candidates:
        context = scanner._ross_news_context_from_evidence(candidate.symbol, (), None, NewsBatchResult(candidates=(candidate,)))
        assert context["ross_catalyst_valid"] is False


@pytest.mark.parametrize("mode", ["missing", "mismatch", "currency", "ambiguous", "error", "timeout"])
def test_unavailable_names_are_not_promoted(monkeypatch, mode):
    client, calls = setup_client(monkeypatch, mode)
    client.qualifyContracts(contract())
    assert client.get_contract_reference_metadata(contract()) == {}
    assert len(calls) == 1


def test_late_completion_and_disconnect_cannot_supply_name(monkeypatch):
    client, calls = setup_client(monkeypatch, "timeout")
    client.qualifyContracts(contract())
    req_id = calls[0][0]
    detail = ContractDetails()
    detail.contract, detail.longName = contract(), "Too Late Inc"
    client.contractDetails(req_id, detail)
    client.contractDetailsEnd(req_id)
    assert client.get_contract_reference_metadata(contract()) == {}
    client.disconnect()
    assert client.get_contract_reference_metadata(contract()) == {}


def test_metadata_read_does_not_connect(monkeypatch):
    def forbidden(): raise AssertionError("metadata read connected")
    md = MarketDataClient(connection_manager=SimpleNamespace(get_client=forbidden), allow_direct_connection=False)
    assert md.get_contract_reference_metadata(contract()) == {}


def test_existing_name_is_preserved_and_no_lookup_is_added(monkeypatch):
    dummy = DummyMarketDataClient()
    def forbidden(*args): raise AssertionError("unnecessary name lookup")
    dummy.get_contract_reference_metadata = forbidden
    provider = IbkrScannerProvider(market_data_client=dummy)
    provider.last_scan_details = {"symbol_details": {"ONE": {"conId": 123, "longName": "Already Supplied Inc"}}}
    provider.get_quote("ONE")
    assert provider.last_scan_details["symbol_details"]["ONE"]["longName"] == "Already Supplied Inc"


@pytest.mark.parametrize("mode", ["missing", "mismatch", "ambiguous", "error", "timeout"])
def test_provider_missing_name_stays_missing(monkeypatch, mode):
    client, calls = setup_client(monkeypatch, mode)
    md = MarketDataClient(connection_manager=SimpleNamespace(get_client=lambda: client), allow_direct_connection=False)
    monkeypatch.setattr(md, "snapshot_stock", DummyMarketDataClient().snapshot_stock)
    provider = IbkrScannerProvider(market_data_client=md)
    provider.last_scan_details = {"symbol_details": {"ONE": {"conId": 123, "currency": "USD"}}}
    provider.get_quote("ONE")
    assert "longName" not in provider.last_scan_details["symbol_details"]["ONE"]
    assert len(calls) == 1


def test_completion_boundary_is_frozen_and_new_failure_supersedes_success(monkeypatch):
    client, calls = setup_client(monkeypatch)
    client.qualifyContracts(contract())
    req_id = calls[0][0]
    assert client.get_contract_reference_metadata(contract())["longName"] == "One Industrial Inc"
    late = ContractDetails()
    late.contract, late.longName = contract("TWO", 456), "Wrong Late Name"
    client.contractDetails(req_id, late)
    client.contractDetailsEnd(req_id)
    assert client.get_contract_reference_metadata(contract())["longName"] == "One Industrial Inc"
    client.snapshot_timeout_seconds = 0.001
    monkeypatch.setattr(client, "reqContractDetails", lambda *args: None)
    client.qualifyContracts(contract())
    assert client.get_contract_reference_metadata(contract()) == {}


def test_disconnect_invalidates_completed_name(monkeypatch):
    client, calls = setup_client(monkeypatch)
    client.qualifyContracts(contract())
    assert client.get_contract_reference_metadata(contract())
    client.disconnect()
    # Even a reconnect cannot resurrect the previous connection's response.
    assert client.get_contract_reference_metadata(contract()) == {}


def test_one_quote_qualification_is_the_only_name_request(monkeypatch):
    client, calls = setup_client(monkeypatch)
    md = MarketDataClient(connection_manager=SimpleNamespace(get_client=lambda: client), allow_direct_connection=False)
    monkeypatch.setattr(md, "snapshot_stock", DummyMarketDataClient().snapshot_stock)
    provider = IbkrScannerProvider(market_data_client=md)
    provider.last_scan_details = {"symbol_details": {"ONE": {"conId": 123, "currency": "USD"}}}
    provider.get_quote("ONE")
    assert provider.last_scan_details["symbol_details"]["ONE"]["longName"] == "One Industrial Inc"
    assert len(calls) == 1


def test_late_end_is_unavailable_even_if_waiter_awakes(monkeypatch):
    client, calls = setup_client(monkeypatch)
    client.qualifyContracts(contract())
    state = client._request_context_by_req_id[calls[0][0]]
    state["reference_deadline"] = state["reference_response"][0] - 0.001
    assert client.get_contract_reference_metadata(contract()) == {}


def test_old_and_post_completion_order_errors_do_not_poison_name(monkeypatch):
    client, calls = setup_client(monkeypatch)
    client.error(1, 2109, "earlier unrelated order warning")
    client.qualifyContracts(contract())
    assert calls[0][0] == 1
    assert client.get_contract_reference_metadata(contract())["longName"] == "One Industrial Inc"
    client.error(1, 201, "later unrelated order error")
    assert client.get_contract_reference_metadata(contract())["longName"] == "One Industrial Inc"


def test_active_contract_error_stays_ineligible_even_with_end_callback(monkeypatch):
    client, calls = setup_client(monkeypatch, "error")
    client.qualifyContracts(contract())
    client.contractDetailsEnd(calls[0][0])
    assert client.get_contract_reference_metadata(contract()) == {}
