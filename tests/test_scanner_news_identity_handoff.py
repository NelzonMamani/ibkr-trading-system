"""Real scanner identity handoff and volume diagnostics; no provider requests."""
from dataclasses import replace
from datetime import datetime, timezone
import json
import pytest
from src.config.config_resolver import set_config_overrides
from src.scanner import scanner_runner as scanner
from src.news.batch_rss_adapter import _metadata_by_symbol
from src.news.news_fetcher import company_aliases_for_symbol
from src.news.news_intelligence_contract import NewsBatchResult, NewsRequest, RetrievalPolicy, RetrievalDiagnostics
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.retrieval_diagnostics import emit_retrieval_diagnostics
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy
from test_scanner_pct_change_fallback import _BaseProvider


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    set_config_overrides({"RUN_MODE": "READ_ONLY", "SCANNER_FLOAT_CACHE_FILE": str(tmp_path / "float.json"),
                          "PERSISTENCE_SQLITE_PATH": str(tmp_path / "runtime.sqlite3"), "NEWS_CACHE_FILE": str(tmp_path / "news.json")})
    yield
    set_config_overrides(None)


def candidates(contexts):
    return scanner._news_candidates_for_symbols([row["symbol"] for row in contexts], scanner._news_symbol_metadata_for_contexts(contexts))


def test_real_provider_context_to_news_preserves_supplied_identity():
    provider = _BaseProvider(close=100)
    provider.last_scan_details = {"symbol_details": {
        "ONE": {"conId": 123, "exchange": "SMART", "primaryExchange": "NASDAQ", "longName": "One Industrial Inc", "aliases": ["One Research"], "cik": "0000123"},
        "TWO": {"conId": 456, "exchange": "NYSE", "longName": "Two Medical Ltd", "issuer_aliases": ["Two Therapeutics"]}}}
    contexts = [scanner._build_symbol_context(provider, symbol, "RTH_MID", float_cache={}) for symbol in ("ONE", "TWO")]
    one, two = candidates(contexts)
    assert one.company_name == "One Industrial Inc" and two.company_name == "Two Medical Ltd"
    assert one.aliases == ("One Research",) and two.aliases == ("Two Therapeutics",)
    assert one.exchange == "SMART" and two.exchange == "NYSE"
    assert one.metadata["con_id"] == 123 and two.metadata["con_id"] == 456
    assert isinstance(one.metadata["con_id"], int)
    assert one.metadata["cik"] == "0000123"
    effective = _metadata_by_symbol((one, two))
    assert company_aliases_for_symbol("ONE", effective["ONE"]) == ("ONE INDUSTRIAL", "ONE RESEARCH")
    assert "TWO MEDICAL" not in company_aliases_for_symbol("ONE", effective["ONE"])


def test_missing_names_stay_missing_and_security_ids_are_not_issuer_names(capsys):
    (candidate,) = candidates([{"symbol": "NONE", "con_id": 123, "exchange": "SMART", "aliases": []}])
    assert candidate.company_name is None and candidate.aliases == ()
    emit_retrieval_diagnostics(NewsBatchResult(candidates=(candidate,)), provider_invoked=False)
    line = [x for x in capsys.readouterr().out.splitlines() if x.startswith("[NEWS][RETRIEVAL_DIAGNOSTICS]")][-1]
    identity = json.loads(line.split(" ", 1)[1])["candidate_identities"][0]
    assert identity["issuer_identifiers"] == {}
    assert identity["security_identifiers"]["con_id"] == 123
    assert identity["effective_rss_matching_identity"]["company_aliases"] == []


@pytest.mark.parametrize("value,expected", [("123", 123), (True, None), (1.5, None), ("bad", None)])
def test_security_identifier_type_is_preserved_or_rejected(value, expected):
    (candidate,) = candidates([{"symbol": "ONE", "con_id": value}])
    assert candidate.metadata.get("con_id") == expected


@pytest.mark.parametrize("symbol,volume", [("MOBX", 627661), ("OLOX", 874640)])
def test_saved_midday_volume_flag_uses_authoritative_session_floor(symbol, volume):
    policy = RossMomentumPolicy().stock_selection
    thresholds = scanner._gate_thresholds(policy, scanner._resolve_runtime_thresholds(policy, "RTH_MID"))
    threshold, source = scanner._focus_volume_threshold_for_session("RTH_MID", thresholds)
    assert threshold == 300000 and source == "policy.session_focus_volume_min[RTH_MID]"
    for catalyst in (False, True):
        context = {"symbol": symbol, "session": "RTH_MID", "volume": volume, "catalyst_present": catalyst}
        assert scanner._focus_gate_checks(context, thresholds)["volume_ok"] is True
    assert scanner._focus_gate_checks({"session": "RTH_MID", "volume": 299999}, thresholds)["volume_ok"] is False


def test_handoff_identity_change_invalidates_compatible_acquisition_only(tmp_path):
    class Provider:
        calls = 0
        def get_news(self, supplied, request, policy):
            self.calls += 1
            now = datetime.now(timezone.utc)
            return NewsBatchResult(candidates=tuple(supplied), evidence_by_symbol={x.symbol: () for x in supplied},
                diagnostics=RetrievalDiagnostics(retrieval_status="available", provider_available=True, provider_status="ok"),
                started_at=now, completed_at=now)
    provider = Provider()
    service = CanonicalNewsIntelligenceService(evidence_store=CanonicalNewsEvidenceStore(tmp_path / "cache.json", prep_artifact_loader=lambda: {}), retrieval_provider=provider)
    policy = RetrievalPolicy(source_groups=("FAST_TRADING",), refresh_interval_seconds=1800, metadata={"require_compatible_acquisition": True})
    old = candidates([{"symbol": "ONE", "company_name": "One Industrial"}])
    new = candidates([{"symbol": "ONE", "company_name": "One Industrial", "aliases": ["One Research"], "exchange": "NASDAQ", "con_id": 123}])
    assert scanner._evidence_signature((), None, candidate=old[0]) != scanner._evidence_signature((), None, candidate=new[0])
    service.get_news(old, NewsRequest(), policy)
    only = service.get_news(new, NewsRequest(), replace(policy, refresh_mode="cache_only", network_allowed=False))
    assert provider.calls == 1
    assert only.diagnostics.diagnostics["acquisition_profile_mismatch_symbols"] == ["ONE"]
    service.get_news(new, NewsRequest(), policy)
    service.get_news(new, NewsRequest(), policy)
    assert provider.calls == 2


def test_generated_scanner_id_is_not_news_identity(monkeypatch):
    provider = _BaseProvider(close=100)
    rows = []
    for surrogate in (111, 999):
        monkeypatch.setattr(scanner, "hash", lambda symbol, value=surrogate: value, raising=False)
        rows.append(scanner._build_symbol_context(provider, "MOCKX", "RTH_MID", float_cache={}))
    assert rows[0]["con_id"] != rows[1]["con_id"]
    first, second = candidates([rows[0]])[0], candidates([rows[1]])[0]
    assert "con_id" not in first.metadata and "conId" not in first.metadata
    assert first == second
    assert scanner._evidence_signature((), None, candidate=first) == scanner._evidence_signature((), None, candidate=second)


def test_set_aliases_survive_handoff_and_direct_candidate_calls():
    context = {"symbol": "ONE", "aliases": {"One Research", "One Industrial", 123}}
    for candidate in (candidates([context])[0], scanner._news_candidates_for_symbols(["ONE"], {"ONE": {"aliases": context["aliases"]}})[0]):
        assert candidate.aliases == ("One Industrial", "One Research")
        assert candidate.metadata["aliases"] == candidate.aliases
        effective = _metadata_by_symbol((candidate,))
        assert company_aliases_for_symbol("ONE", effective["ONE"]) == ("ONE INDUSTRIAL", "ONE RESEARCH")
