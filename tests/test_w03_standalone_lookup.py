"""Offline acceptance of the supported standalone research interface.

The IRON article is the original W02 capture, replayed at a controlled +18h
instant. This verifies the requested research window, not new live discovery.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.news import batch_rss_adapter, evidence_store, news_fetcher, news_intelligence_service, standalone_lookup
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.news_intelligence_contract import NewsCandidate
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
from src.news.standalone_lookup import LookupSettings, human_report, lookup_news


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = json.loads((Path(__file__).parent / "fixtures/w02_captured_issuer_news.json").read_text(encoding="utf-8"))
PUBLICATION = datetime.fromisoformat(CAPTURE["published_at"])
FAST_URLS = (CAPTURE["source_url"], "https://example.test/second-feed")
EXTENDED_URLS = ("https://example.test/extended-feed",)


@pytest.fixture(autouse=True)
def research_clock(monkeypatch, tmp_path):
    class Clock(datetime):
        current = PUBLICATION + timedelta(hours=18)

        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(cls.current.timestamp(), tz=tz)

    for module in (batch_rss_adapter, evidence_store, news_intelligence_service, standalone_lookup):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(time, "time", lambda: Clock.current.timestamp())
    set_config_overrides({"NEWS_ENABLED": True, "NEWS_LOOKBACK_HOURS": 6.0,
                          "NEWS_MAX_AGE_HOURS": 6.0, "NEWS_MAX_ENTRIES_PER_SYMBOL": 5,
                          "NEWS_TOTAL_BUDGET_S": 8.0, "NEWS_REQUEST_TIMEOUT_S": 5,
                          "NEWS_EXTENDED_TIER_RESERVE_FRACTION": 0.35,
                          "NEWS_CACHE_FILE": str(tmp_path / "operational-must-not-be-used.json")})
    yield Clock
    set_config_overrides({})


class CountingService(CanonicalNewsIntelligenceService):
    def __init__(self, path):
        super().__init__(evidence_store=CanonicalNewsEvidenceStore(path, prep_artifact_loader=lambda: {}))
        self.calls = []

    def get_news(self, candidates, request, policy):
        self.calls.append((tuple(candidates), request, policy))
        return super().get_news(candidates, request, policy)


def _source_groups(monkeypatch):
    def urls(group):
        return FAST_URLS if group == "FAST_TRADING" else EXTENDED_URLS if group == "PREP_EXTENDED" else ()
    for module in (batch_rss_adapter, news_intelligence_service, standalone_lookup):
        monkeypatch.setattr(module, "get_source_group_urls", urls)


def _feeds(monkeypatch, *, failing=False, empty=False):
    _source_groups(monkeypatch)
    calls = []
    issuer = SimpleNamespace(title=CAPTURE["headline"], summary=CAPTURE["summary_excerpt"],
                             link=CAPTURE["url"], published_parsed=time.gmtime(PUBLICATION.timestamp()))
    unrelated = SimpleNamespace(title="Malaysia launches research programme", summary="Visitors enjoy egg tarts.",
                                link="https://example.test/egg", published_parsed=time.gmtime(PUBLICATION.timestamp()))
    old = SimpleNamespace(title="Disc Medicine (NASDAQ: IRON) older company update", summary="Disc Medicine, Inc.",
                          link="https://example.test/older-iron", published_parsed=time.gmtime((PUBLICATION - timedelta(hours=7)).timestamp()))

    def fetch(url, timeout):
        calls.append((url, timeout))
        if failing and (failing == "all" or url == FAST_URLS[1]):
            raise news_fetcher.requests.exceptions.ReadTimeout("controlled offline timeout")
        return SimpleNamespace(feed={"title": "GlobeNewswire Finance"}, entries=[] if empty or url != FAST_URLS[0] else [issuer, unrelated, old])

    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(news_fetcher, "_fetch_feed", fetch)
    return calls


def _settings(tmp_path, **changes):
    return replace(LookupSettings(cache_file=tmp_path / "research.json", source_groups=("FAST_TRADING",)), **changes)


@pytest.mark.parametrize("extra_symbols", [[], [" egg ", "EGG"]], ids=["single", "batch"])
def test_single_and_batch_share_one_canonical_call_and_each_feed_once(monkeypatch, tmp_path, extra_symbols):
    feeds = _feeds(monkeypatch)
    service = CountingService(tmp_path / "research.json")
    identity = NewsCandidate("iron", company_name=CAPTURE["company_name"], aliases=("Disc Medicine",),
                             exchange="NASDAQ", region="US", priority_rank=2, price=42.0,
                             metadata={"issuer_id": "offline-identity", "conId": 12345})
    result = lookup_news([" IRON ", identity, *extra_symbols], _settings(tmp_path), service=service)
    assert len(service.calls) == 1
    candidates, request, policy = service.calls[0]
    assert len(candidates) == (2 if extra_symbols else 1)
    assert candidates[0] == replace(identity, symbol="IRON")
    assert request.lookback_seconds == request.freshness_seconds == 86400
    assert request.strategy_id == "standalone_research_v1"
    assert policy.total_budget_seconds == 30.0
    assert sorted(url for url, _ in feeds) == sorted(FAST_URLS)
    assert result["selected_source_groups"] == ["FAST_TRADING"]
    assert result["queried_source_groups"] == ["FAST_TRADING"]
    assert result["candidates"][0]["metadata"] == dict(identity.metadata)
    assert result["research_results_are_trading_catalysts"] is False
    assert result["cleanup"]["cleanup_complete"] is None
    article, = result["symbols"]["IRON"]["articles"]
    assert article["headline"] == CAPTURE["headline"]
    assert article["url"] == CAPTURE["url"]
    assert article["published_at"] == CAPTURE["published_at"]
    assert article["age_seconds"] == 18 * 3600
    assert article["publisher"] == "GlobeNewswire Finance"
    assert article["match_basis"]["type"] == "ticker_token"
    assert article["evidence_id"]
    assert article["acquisition_origin"] == "current_retrieval"
    assert result["symbols"]["IRON"]["current_retrieval_article_count"] == 1
    assert result["symbols"]["IRON"]["outcome"] == "matched"
    assert result["symbols"]["IRON"]["coverage_status"] == "complete"
    if extra_symbols:
        assert result["symbols"]["EGG"]["articles"] == []
        assert result["symbols"]["EGG"]["outcome"] == "completed_no_match"
    # The public result is machine-readable without a custom JSON encoder.
    assert json.loads(json.dumps(result))["symbols"]["IRON"]["articles"][0]["published_at"] == CAPTURE["published_at"]
    assert "18.00h" in human_report(result)
    assert not (tmp_path / "operational-must-not-be-used.json").exists()


def test_requested_window_applies_to_cold_and_cached_articles(monkeypatch, tmp_path, research_clock):
    feeds = _feeds(monkeypatch)
    settings = _settings(tmp_path)
    service = CountingService(settings.cache_file)
    candidate = NewsCandidate("IRON", company_name=CAPTURE["company_name"])
    cold = lookup_news([candidate], settings, service=service)
    first = cold["symbols"]["IRON"]["articles"][0]
    research_clock.current += timedelta(seconds=60)
    warm = lookup_news([candidate], settings, service=CountingService(settings.cache_file))
    cached = warm["symbols"]["IRON"]["articles"][0]
    assert cached["evidence_id"] == first["evidence_id"]
    assert cached["published_at"] == first["published_at"]
    assert cached["age_seconds"] == first["age_seconds"] + 60
    assert warm["symbols"]["IRON"]["provenance"] == "cached_acquisition"
    assert cached["acquisition_origin"] == "cache_or_prep"
    assert warm["symbols"]["IRON"]["current_retrieval_article_count"] == 0
    assert warm["symbols"]["IRON"]["coverage_status"] == "complete"
    assert len(feeds) == len(FAST_URLS)
    cached_short = lookup_news([candidate], replace(settings, lookback_hours=6, cache_mode="only"), service=service)
    assert cached_short["symbols"]["IRON"]["articles"] == []
    assert cached_short["symbols"]["IRON"]["excluded_evidence"] == {"outside_requested_lookback": 1}
    assert cached_short["symbols"]["IRON"]["coverage_status"] == "unknown"
    assert len(feeds) == len(FAST_URLS)
    cold_short = lookup_news([candidate], replace(settings, lookback_hours=6, cache_mode="off"), service=service)
    assert cold_short["symbols"]["IRON"]["articles"] == []
    assert cold_short["symbols"]["IRON"]["outcome"] == "completed_no_match"
    assert len(feeds) == 2 * len(FAST_URLS)


@pytest.mark.parametrize("groups", [("PREP_EXTENDED",), ("PREP_EXTENDED", "FAST_TRADING")])
def test_selected_extended_sources_are_requested_and_reported(monkeypatch, tmp_path, groups):
    feeds = _feeds(monkeypatch, empty=True)
    service = CountingService(tmp_path / "research.json")
    result = lookup_news(["EGG"], _settings(tmp_path, source_groups=groups), service=service)
    expected = list(FAST_URLS) + list(EXTENDED_URLS) if "FAST_TRADING" in groups else list(EXTENDED_URLS)
    assert sorted(url for url, _ in feeds) == sorted(expected)
    assert [row["source_id"] for row in result["selected_sources"]] == expected
    assert [row["source_id"] for row in result["symbols"]["EGG"]["sources"]] == expected
    assert result["symbols"]["EGG"]["outcome"] == "completed_no_match"
    assert service.calls[0][2].fallback_mode == "unresolved_only"


@pytest.mark.parametrize("empty", [False, True], ids=["matched", "empty"])
def test_partial_source_failure_never_becomes_completed_no_match(monkeypatch, tmp_path, empty):
    _feeds(monkeypatch, failing=True, empty=empty)
    result = lookup_news(["IRON"], _settings(tmp_path), service=CountingService(tmp_path / "research.json"))
    symbol = result["symbols"]["IRON"]
    assert symbol["coverage_status"] == "partial"
    assert symbol["outcome"] == ("retrieval_partial" if empty else "matched")
    source = next(row for row in symbol["sources"] if row["source_id"] == FAST_URLS[1])
    assert source["timed_out"] is True
    assert source["budget_exhausted"] is False
    assert source.get("request_elapsed_seconds") is None
    assert source.get("parse_elapsed_seconds") is None
    assert result["timing"]["total_elapsed_seconds"] >= result["timing"]["service_elapsed_seconds"] >= 0


@pytest.mark.parametrize("changes", [
    {"lookback_hours": 0}, {"lookback_hours": float("nan")}, {"budget_seconds": float("inf")},
    {"budget_seconds": 121}, {"request_timeout_seconds": -1}, {"max_items": True},
    {"source_groups": ("MACRO_LONG_HORIZON",)}, {"cache_mode": "unknown"},
])
def test_invalid_research_settings_fail_before_service_or_network(tmp_path, changes):
    service = CountingService(tmp_path / "research.json")
    with pytest.raises(ValueError):
        lookup_news(["IRON"], _settings(tmp_path, **changes), service=service)
    assert service.calls == []
    assert not (tmp_path / "research.json").exists()


def test_cli_supervised_cache_only_json_exits_cleanly_with_unknown_coverage(tmp_path):
    output_file = tmp_path / "result.json"
    cache_file = tmp_path / "diagnostic-cache.json"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_news_discovery.py"), "IRON,EGG",
         "--cache-mode", "only", "--cache-file", str(cache_file),
         "--source-groups", "FAST_TRADING", "--format", "json", "--json-output", str(output_file),
         "--budget-seconds", "0.5", "--cleanup-seconds", "0.5"],
        cwd=ROOT, text=True, encoding="utf-8", capture_output=True, timeout=25,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == json.loads(output_file.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert list(result["symbols"]) == ["IRON", "EGG"]
    assert result["process"]["exit_code"] == 0
    assert result["process"]["exit_confirmed"] is True
    assert result["process"]["terminated_at_wall_limit"] is False
    assert result["cleanup"]["cleanup_complete"] is True
    assert result["diagnostics"]["sources_attempted_count"] == 0
    assert result["retrieval_policy"]["network_allowed"] is False
    assert result["runtime"]["source_hashes_unchanged"] is True
    assert "src/news/standalone_lookup.py" in result["runtime"]["source_hashes"]
    for symbol in result["symbols"].values():
        assert symbol["articles"] == []
        assert symbol["coverage_status"] == "unknown"
        assert symbol["outcome"] == "coverage_unknown"
    assert not cache_file.exists()


@pytest.mark.parametrize("arguments", [
    [], ["IRON", "EGG", "--company-name", "Disc Medicine"],
    ["IRON", "EGG", "--alias", "Disc Medicine"], ["IRON", "--lookback-hours", "nan"],
    ["IRON", "--source-groups", "MACRO_LONG_HORIZON"],
])
def test_cli_rejects_invalid_or_ambiguous_input_before_starting_worker(monkeypatch, arguments, capsys):
    from scripts import verify_news_discovery as command

    def no_worker(*args, **kwargs):
        pytest.fail("Invalid CLI input must not start a worker")

    monkeypatch.setattr(command, "run_supervised", no_worker)
    with pytest.raises(SystemExit) as raised:
        command.main(arguments)
    assert raised.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_cli_candidate_file_retains_identity_and_normalizes_source_selection(monkeypatch, tmp_path, capsys):
    from scripts import verify_news_discovery as command
    candidate_file = tmp_path / "candidates.json"
    identity = {"symbol": "iron", "company_name": CAPTURE["company_name"], "aliases": ["Disc Medicine"],
                "exchange": "NASDAQ", "market": "US", "region": "North America", "priority_rank": 2,
                "price": 42.0, "metadata": {"issuer_id": "fixture", "nested": {"source": "preparation"}}}
    candidate_file.write_text(json.dumps({"candidates": [identity, {"symbol": "egg"}]}), encoding="utf-8")
    captured = []

    def supervised(candidates, settings):
        captured.append((candidates, settings))
        return {"ok": True, "candidates": standalone_lookup.jsonable(candidates)}, 0

    monkeypatch.setattr(command, "run_supervised", supervised)
    assert command.main(["--candidates-file", str(candidate_file), "--source-groups", "PREP_EXTENDED,FAST_TRADING",
                         "--format", "json", "--cache-file", str(tmp_path / "research.json")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["candidates"][0] == {**standalone_lookup.jsonable(NewsCandidate(**{**identity, "aliases": tuple(identity["aliases"])})), "symbol": "IRON"}
    candidates, settings = captured[0]
    assert candidates[0].metadata == identity["metadata"]
    assert candidates[1].symbol == "EGG"
    assert settings.source_groups == ("FAST_TRADING", "PREP_EXTENDED")



def test_all_failed_sources_are_unavailable_not_an_empty_completed_query(monkeypatch, tmp_path):
    _feeds(monkeypatch, failing="all")
    result = lookup_news(["IRON"], _settings(tmp_path), service=CountingService(tmp_path / "research.json"))
    symbol = result["symbols"]["IRON"]
    assert symbol["articles"] == []
    assert symbol["coverage_status"] == "unavailable"
    assert symbol["outcome"] == "retrieval_unavailable"
    assert all(source["timed_out"] for source in symbol["sources"])


def test_lookup_cleanup_does_not_promote_late_article_into_retrieval(monkeypatch, tmp_path):
    import threading
    _source_groups(monkeypatch)
    slow_started = threading.Event()
    release_slow = threading.Event()
    partials = []
    fast_article = SimpleNamespace(title=CAPTURE["headline"], summary=CAPTURE["summary_excerpt"],
                                   link=CAPTURE["url"], published_parsed=time.gmtime(PUBLICATION.timestamp()))
    late_article = SimpleNamespace(title="Disc Medicine (NASDAQ: IRON) late company update", summary="Disc Medicine, Inc.",
                                   link="https://example.test/late", published_parsed=time.gmtime(PUBLICATION.timestamp()))

    def fetch(url, timeout):
        if url == FAST_URLS[1]:
            slow_started.set()
            assert release_slow.wait(3), "test must release its owned worker"
            return SimpleNamespace(feed={"title": "Late publisher"}, entries=[late_article])
        assert slow_started.wait(1), "concurrent sources must be submitted together"
        return SimpleNamespace(feed={"title": "GlobeNewswire Finance"}, entries=[fast_article])

    def after_retrieval(payload):
        partials.append(json.loads(json.dumps(payload)))
        release_slow.set()

    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(news_fetcher, "_fetch_feed", fetch)
    try:
        result = lookup_news([NewsCandidate("IRON", company_name=CAPTURE["company_name"])],
                             _settings(tmp_path, budget_seconds=0.3, cleanup_seconds=2), on_retrieval=after_retrieval)
    finally:
        release_slow.set()
    assert len(partials) == 1
    assert partials[0]["cleanup"]["unfinished_count"] == 1
    assert partials[0]["cleanup"]["cleanup_complete"] is False
    assert result["cleanup"]["cleanup_complete"] is True
    assert result["cleanup"]["unfinished_count"] == result["cleanup"]["alive_worker_count"] == 0
    assert result["symbols"]["IRON"]["coverage_status"] == "partial"
    assert [article["url"] for article in result["symbols"]["IRON"]["articles"]] == [CAPTURE["url"]]
    late_source = next(row for row in result["symbols"]["IRON"]["sources"] if row["source_id"] == FAST_URLS[1])
    assert late_source["budget_exhausted"] is True
    assert late_source["timed_out"] is False
    completed_source = next(row for row in result["cleanup"]["sources"] if row["source_id"] == FAST_URLS[1])
    assert completed_source["state"] == "completed"
    assert completed_source["cancellation_succeeded"] is False


@pytest.mark.parametrize("requires_kill", [False, True], ids=["terminate", "kill-after-terminate-timeout"])
def test_cli_supervisor_reaps_its_worker_and_preserves_partial_result_on_wall_deadline(monkeypatch, tmp_path, requires_kill):
    from scripts import verify_news_discovery as command
    children = []

    class Worker:
        def __init__(self, argv, **kwargs):
            self.argv = argv
            self.returncode = None
            self.calls = []
            config = json.loads(Path(argv[-1]).read_text(encoding="utf-8"))
            self.temporary_root = Path(argv[-1]).parent
            Path(config["result_file"]).write_text(json.dumps({
                "ok": True, "worker_stage": "retrieval_complete_cleanup_pending",
                "cleanup": {"cleanup_complete": False, "unfinished_count": 1},
                "symbols": {"IRON": {"articles": [{"url": CAPTURE["url"]}]}},
            }), encoding="utf-8")
            children.append(self)

        def communicate(self, timeout):
            self.calls.append(("communicate", timeout))
            if self.returncode is None:
                raise subprocess.TimeoutExpired(self.argv, timeout)
            return "late worker log is not article evidence\n", ""

        def terminate(self):
            self.calls.append(("terminate",))
            if not requires_kill:
                self.returncode = -15

        def kill(self):
            self.calls.append(("kill",))
            self.returncode = -9

        def poll(self):
            return self.returncode

    monkeypatch.setattr(command.subprocess, "Popen", Worker)
    settings = _settings(tmp_path, budget_seconds=0.5, cleanup_seconds=0.5)
    result, exit_code = command.run_supervised((NewsCandidate("IRON"),), settings)
    worker, = children
    assert exit_code == 1
    assert result["ok"] is False
    assert "wall limit" in result["error"].lower()
    assert result["process"]["terminated_at_wall_limit"] is True
    assert result["process"]["exit_confirmed"] is True
    assert result["process"]["exit_code"] == (-9 if requires_kill else -15)
    assert result["cleanup"]["cleanup_complete"] is False
    assert result["cleanup"]["terminated_process"] is True
    assert result["symbols"]["IRON"]["articles"] == [{"url": CAPTURE["url"]}]
    assert ("terminate",) in worker.calls
    assert (("kill",) in worker.calls) is requires_kill
    assert worker.calls[0] == ("communicate", command.STARTUP_ALLOWANCE_SECONDS + 1.0)
    assert not worker.temporary_root.exists()


@pytest.mark.parametrize("protected_input", ["cache", "prep", "candidates"])
def test_cli_rejects_json_output_overwriting_an_input(monkeypatch, tmp_path, protected_input, capsys):
    from scripts import verify_news_discovery as command
    target = tmp_path / (protected_input + ".json")
    target.write_text(json.dumps([{"symbol": "IRON"}]) if protected_input == "candidates" else "{}", encoding="utf-8")
    original = target.read_bytes()
    arguments = ["IRON", "--json-output", str(target)]
    arguments += ["--" + ("candidates-file" if protected_input == "candidates" else protected_input + "-file"), str(target)]
    monkeypatch.setattr(command, "run_supervised", lambda *args: pytest.fail("A path collision must not start a worker"))
    with pytest.raises(SystemExit) as raised:
        command.main(arguments)
    assert raised.value.code == 2
    assert "different from cache, prep and candidate input files" in capsys.readouterr().err
    assert target.read_bytes() == original



@pytest.mark.parametrize("failed_refresh", [False, True], ids=["completed-empty-refresh", "unavailable-refresh"])
def test_cached_article_is_not_claimed_as_current_discovery_after_explicit_refresh(monkeypatch, tmp_path, failed_refresh):
    _feeds(monkeypatch)
    settings = _settings(tmp_path)
    candidate = NewsCandidate("IRON", company_name=CAPTURE["company_name"])
    cold = lookup_news([candidate], settings, service=CountingService(settings.cache_file))
    original = cold["symbols"]["IRON"]["articles"][0]
    _feeds(monkeypatch, empty=True, failing="all" if failed_refresh else False)
    refreshed = lookup_news([candidate], replace(settings, cache_mode="refresh"), service=CountingService(settings.cache_file))
    symbol = refreshed["symbols"]["IRON"]
    retained, = symbol["articles"]
    assert retained["evidence_id"] == original["evidence_id"]
    assert retained["url"] == original["url"]
    assert retained["published_at"] == original["published_at"]
    assert retained["acquisition_origin"] == "cache_or_prep"
    assert symbol["current_retrieval_article_count"] == 0
    assert symbol["provenance"] == "provider_refresh"
    assert symbol["coverage_status"] == ("unavailable" if failed_refresh else "complete")
