from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from src.config.config_resolver import set_config_overrides
from src.news import batch_rss_adapter, news_fetcher
from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
from src.news.evidence_store import CanonicalNewsEvidenceStore
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService


@pytest.fixture(autouse=True)
def _news_defaults(tmp_path: Path):
    set_config_overrides(
        {
            "NEWS_MAX_ENTRIES_PER_SYMBOL": 5,
            "NEWS_LOOKBACK_HOURS": 24.0,
            "NEWS_REQUEST_TIMEOUT_S": 5,
            "NEWS_TOTAL_BUDGET_S": 8.0,
            "NEWS_EXTENDED_TIER_RESERVE_FRACTION": 0.35,
            "NEWS_CACHE_FILE": str(tmp_path / "news_cache.json"),
        }
    )
    yield
    set_config_overrides({})


def _entry(title: str, *, summary: str = "", age_seconds: int = 120) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        summary=summary,
        link=f"https://news.example/{title.lower().replace(' ', '-')}",
        published_parsed=time.gmtime(time.time() - age_seconds),
    )


def _feed(title: str, *entries: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(feed={"title": title}, entries=list(entries))


def _request() -> NewsRequest:
    return NewsRequest(
        strategy_id="ross_momentum",
        freshness_seconds=60 * 60,
        max_evidence_per_symbol=5,
        need_heat=True,
        need_velocity=True,
        need_reliability=True,
    )


def test_pr1072_multi_symbol_batch_fetches_each_source_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    calls: list[tuple[str, float]] = []

    def fake_fetch_feed(url: str, timeout_s: float):
        calls.append((url, timeout_s))
        return _feed(
            "PR1072_FAST",
            _entry("PR72A reports earnings beat"),
            _entry("PR72B signs new contract"),
        )

    monkeypatch.setattr(news_fetcher, "_fetch_feed", fake_fetch_feed)

    headlines, summary = news_fetcher.fetch_fast_headlines_for_symbols(
        ["PR72A", "PR72B"],
        ["fast://shared-one", "fast://shared-two"],
        max_entries_per_symbol=5,
    )

    assert [url for url, _timeout in calls] == ["fast://shared-one", "fast://shared-two"]
    assert len(calls) == 2
    assert headlines["PR72A"]
    assert headlines["PR72B"]
    assert summary.sources_attempted_count == 2
    assert summary.unique_source_urls_scheduled_count == 2
    assert summary.duplicate_source_fetches_avoided_count == 0
    assert len(summary.source_diagnostics) == 2


def test_pr1072_cross_tier_duplicate_url_is_not_fetched_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    calls: list[str] = []

    def fake_source_urls(group_id: str):
        if group_id == "FAST_TRADING":
            return ("rss://shared", "rss://fast-only")
        if group_id == "PREP_EXTENDED":
            return ("rss://shared", "rss://extended-only")
        return ()

    def fake_fetch_feed(url: str, timeout_s: float):
        calls.append(url)
        return _feed("PR1072_EMPTY")

    monkeypatch.setattr(batch_rss_adapter, "get_source_group_urls", fake_source_urls)
    monkeypatch.setattr(news_fetcher, "_fetch_feed", fake_fetch_feed)

    result = BatchRssNewsIntelligenceProvider().get_news(
        [NewsCandidate("PR72X")],
        _request(),
        RetrievalPolicy(metadata={"unresolved_symbols": ("PR72X",)}),
    )

    assert calls.count("rss://shared") == 1
    assert "rss://extended-only" in calls
    diagnostics = result.diagnostics.diagnostics
    assert diagnostics["duplicate_source_fetches_avoided_count"] == 1
    assert diagnostics["cross_tier_duplicate_source_urls_avoided"] == ("rss://shared",)
    assert diagnostics["diagnostics_mapping_gaps"] == ()
    assert diagnostics["diagnostics_authority_notes"] == (
        "event_and_catalyst_classification_remain_strategy_adapter_authority",
    )
    assert len({row["source_id"] for row in diagnostics["source_diagnostics"]}) == len(diagnostics["source_diagnostics"])
    assert all(row["timeout_seconds"] is not None for row in diagnostics["source_diagnostics"] if row["attempted"])


def test_pr1072_source_timeouts_are_fairly_clamped_to_remaining_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    calls: list[tuple[str, float]] = []

    def fake_fetch_feed(url: str, timeout_s: float):
        calls.append((url, timeout_s))
        return _feed("PR1072_EMPTY")

    monkeypatch.setattr(news_fetcher, "_fetch_feed", fake_fetch_feed)

    _headlines, summary = news_fetcher.fetch_headlines_for_symbols(
        ["PR72B"],
        [f"budget://{idx}" for idx in range(5)],
        request_timeout_s=5.0,
        source_tier="extended",
        total_news_budget_seconds=0.4,
        tier_budget_seconds=0.4,
    )

    assert summary.total_news_budget_seconds == pytest.approx(0.4)
    assert summary.sources_attempted_count == 5
    assert sum(1 for _url, timeout in calls if timeout <= 0.25) >= 4
    assert max(timeout for _url, timeout in calls) <= 0.45
    assert summary.news_elapsed_seconds <= 0.6
    assert summary.source_diagnostics
    attempted_timeouts = [row["timeout_seconds"] for row in summary.source_diagnostics if row["attempted"]]
    assert sum(1 for timeout in attempted_timeouts if timeout <= 0.25) >= 4


def test_pr1072_slow_source_does_not_block_independent_fast_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    calls: list[str] = []

    def fake_fetch_feed(url: str, timeout_s: float):
        calls.append(url)
        if url == "slow://feed":
            time.sleep(0.25)
            return _feed("SLOW_EMPTY")
        return _feed("FAST_HIT", _entry("FASTY receives FDA approval"))

    monkeypatch.setattr(news_fetcher, "_fetch_feed", fake_fetch_feed)
    started = time.monotonic()
    headlines, summary = news_fetcher.fetch_fast_headlines_for_symbols(
        ["FASTY"],
        ["slow://feed", "fast://feed"],
        max_entries_per_symbol=1,
        total_news_budget_seconds=1.0,
        tier_budget_seconds=1.0,
    )
    elapsed = time.monotonic() - started

    assert headlines["FASTY"][0].title == "FASTY receives FDA approval"
    assert "fast://feed" in calls
    assert elapsed < 0.2
    assert summary.sources_attempted_count == 2
    assert any(row["source_id"] == "fast://feed" and row["matched_count"] == 1 for row in summary.source_diagnostics)


def test_pr1072_no_recent_news_and_budget_exhausted_remain_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(news_fetcher, "_fetch_feed", lambda url, timeout_s: _feed("EMPTY"))

    no_news = BatchRssNewsIntelligenceProvider().get_news(
        [NewsCandidate("NONE")],
        _request(),
        RetrievalPolicy(source_groups=("FAST_TRADING",), total_budget_seconds=1.0),
    )

    assert no_news.diagnostics.diagnostics["result_status_counts"] == {"no_recent_news": 1}
    assert no_news.summary_for_symbol("NONE").retrieval_status == "available"  # type: ignore[union-attr]

    def slow_fetch_feed(url: str, timeout_s: float):
        time.sleep(timeout_s + 0.02)
        return _feed("SLOW_EMPTY")

    monkeypatch.setattr(news_fetcher, "_fetch_feed", slow_fetch_feed)
    exhausted = BatchRssNewsIntelligenceProvider().get_news(
        [NewsCandidate("BUDG")],
        _request(),
        RetrievalPolicy(source_groups=("FAST_TRADING",), total_budget_seconds=0.08),
    )

    assert exhausted.diagnostics.diagnostics["result_status_counts"] == {"budget_exhausted": 1}
    assert exhausted.summary_for_symbol("BUDG").retrieval_status == "budget_exhausted"  # type: ignore[union-attr]
    assert exhausted.summary_for_symbol("BUDG").retrieval_unavailable is True  # type: ignore[union-attr]


def test_pr1072_extended_deadline_skip_populates_source_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_source_urls(group_id: str):
        if group_id == "FAST_TRADING":
            return ("rss://fast-only",)
        if group_id == "PREP_EXTENDED":
            return ("rss://extended-only",)
        return ()

    def fast_fetcher(symbols, sources, **kwargs):
        source = sources[0]
        return {symbol: [] for symbol in symbols}, news_fetcher.RssFailureSummary(
            total_sources=len(sources),
            failure_count=0,
            failures_by_domain={},
            reason=None,
            tier_source_counts={"fast": len(sources)},
            max_entries_per_symbol=5,
            sources_attempted_count=len(sources),
            tier_sources_attempted_counts={"fast": len(sources)},
            source_diagnostics=(
                {
                    "source_id": source,
                    "source_url": source,
                    "provider": "rss_batch",
                    "source_group": "FAST_TRADING",
                    "source_tier": "fast",
                    "retrieval_status": "budget_exhausted",
                    "attempted": True,
                    "matched_count": 0,
                    "failure_reason": "deadline_exhausted",
                    "elapsed_seconds": 0.02,
                    "timeout_seconds": 0.01,
                    "budget_exhausted": True,
                },
            ),
            unique_source_urls_scheduled_count=len(sources),
            unique_source_urls_attempted_count=len(sources),
            total_news_budget_seconds=0.01,
            news_elapsed_seconds=0.02,
            news_budget_exhausted=True,
            tier_budget_seconds=0.01,
            tier_elapsed_seconds=0.02,
            tier_budget_exhausted=True,
            tier_budget_seconds_by_tier={"fast": 0.01},
            tier_elapsed_seconds_by_tier={"fast": 0.02},
            tier_budget_exhausted_by_tier={"fast": True},
        )

    def extended_fetcher(*args, **kwargs):  # pragma: no cover - should not run after deadline exhaustion
        raise AssertionError("extended fetch should be skipped when the news deadline is exhausted")

    monkeypatch.setattr(batch_rss_adapter, "get_source_group_urls", fake_source_urls)

    result = BatchRssNewsIntelligenceProvider(
        fast_fetcher=fast_fetcher,
        extended_fetcher=extended_fetcher,
    ).get_news(
        [NewsCandidate("LATE")],
        _request(),
        RetrievalPolicy(total_budget_seconds=0.01, metadata={"unresolved_symbols": ("LATE",)}),
    )

    diagnostics = result.diagnostics.diagnostics
    assert diagnostics["result_status_counts"] == {"budget_exhausted": 1}
    assert diagnostics["symbols_unresolved_at_budget_exhaustion"] == ["LATE"]
    assert diagnostics["sources_skipped_due_to_budget_count"] == 1
    assert diagnostics["unique_source_urls_scheduled_count"] == 2
    assert diagnostics["tier_source_counts"]["extended"] == 1
    skipped = [row for row in diagnostics["source_diagnostics"] if row["source_id"] == "rss://extended-only"]
    assert skipped == [
        {
            "source_id": "rss://extended-only",
            "provider": "rss_batch",
            "source_group": "PREP_EXTENDED",
            "source_tier": "extended",
            "retrieval_status": "budget_exhausted",
            "attempted": False,
            "matched_count": 0,
            "failure_reason": "deadline_exhausted_before_attempt",
            "elapsed_seconds": 0.0,
            "timeout_seconds": 0.0,
            "timed_out": False,
            "budget_exhausted": True,
        }
    ]

def test_pr1072_cache_and_prep_reuse_avoid_network_refresh(tmp_path: Path) -> None:
    prep_payload = {
        "symbols": [
            {
                "symbol": "PREP72",
                "company_name": "Prep Seventy Two",
                "news_asof": datetime.now(timezone.utc).isoformat(),
                "news_context": [
                    {
                        "title": "PREP72 announces new supply contract",
                        "published_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
                        "url": "https://news.example/prep72",
                        "source": "PrepWire",
                        "catalyst_tag": "contract_order",
                    }
                ],
            }
        ]
    }
    store = CanonicalNewsEvidenceStore(tmp_path / "news_cache.json", prep_artifact_loader=lambda: prep_payload)

    class FailingProvider:
        def get_news(self, candidates, request, retrieval_policy):  # pragma: no cover - should not be called
            raise AssertionError("network refresh should not be called when prep evidence is fresh")

    service = CanonicalNewsIntelligenceService(evidence_store=store, retrieval_provider=FailingProvider())

    result = service.get_news(
        [NewsCandidate("PREP72", company_name="Prep Seventy Two")],
        _request(),
        RetrievalPolicy(refresh_mode="bounded_refresh", network_allowed=True),
    )

    assert result.diagnostics.diagnostics["prep_reuse_symbols"] == ["PREP72"]
    assert result.diagnostics.diagnostics["refresh_requested_count"] == 0
    assert result.evidence_for_symbol("PREP72")[0].provider == "prep_cache"
