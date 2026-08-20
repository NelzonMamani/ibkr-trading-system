from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.news import news_fetcher
from src.scanner import scanner_runner


_ROOT = Path(__file__).resolve().parents[1]
_PR1040_PATH = _ROOT / "scripts" / "certification" / "pr1040_real_readonly_runtime_observation_adapter.py"


def _load_pr1040_module():
    spec = importlib.util.spec_from_file_location("pr1040_adapter_pr1061_test", _PR1040_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pr1040 = _load_pr1040_module()


class _Clock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


@pytest.fixture(autouse=True)
def _reset_runtime_state(tmp_path: Path):
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._NEWS_CACHE = {}
    set_config_overrides({
        "NEWS_MAX_ENTRIES_PER_SYMBOL": 5,
        "NEWS_TOTAL_BUDGET_S": 8.0,
        "NEWS_EXTENDED_TIER_RESERVE_FRACTION": 0.35,
        "NEWS_CACHE_FILE": str(tmp_path / "news_cache.json"),
    })
    yield
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._NEWS_CACHE = {}
    set_config_overrides({})


def _feed(*entries):
    return SimpleNamespace(feed={"title": "PR1061_FEED"}, entries=list(entries))


def _headline(title: str, *, age_seconds: int = 300, source_tier: str = "fast") -> scanner_runner.Headline:
    return scanner_runner.Headline(
        title=title,
        source="PR1061_NEWS",
        published_ts=time.time() - age_seconds,
        url="https://news.example/pr1061",
        source_tier=source_tier,
    )


def _summary(
    *,
    total: int,
    tier: str,
    matches: int = 0,
    ticker_matches: int = 0,
    budget: float = 8.0,
    elapsed: float = 0.0,
    exhausted: bool = False,
    attempted: int = 0,
    skipped: int = 0,
    tier_budget: float = 0.0,
    tier_elapsed: float = 0.0,
    tier_exhausted: bool = False,
) -> scanner_runner.RssFailureSummary:
    return scanner_runner.RssFailureSummary(
        total_sources=total,
        failure_count=0,
        failures_by_domain={},
        reason=None,
        tier_source_counts={tier: total} if total else {},
        tier_match_counts={tier: matches} if matches else {},
        ticker_token_match_count=ticker_matches,
        max_entries_per_symbol=5,
        total_news_budget_seconds=budget,
        news_elapsed_seconds=elapsed,
        news_budget_exhausted=exhausted,
        sources_attempted_count=attempted,
        sources_skipped_due_to_budget_count=skipped,
        tier_sources_attempted_counts={tier: attempted} if total else {},
        tier_budget_seconds=tier_budget,
        tier_elapsed_seconds=tier_elapsed,
        tier_budget_exhausted=tier_exhausted,
        tier_budget_seconds_by_tier={tier: tier_budget} if total else {},
        tier_elapsed_seconds_by_tier={tier: tier_elapsed} if total else {},
        tier_budget_exhausted_by_tier={tier: tier_exhausted} if total else {},
    )


def test_pr1061_fetcher_clamps_request_timeout_to_tier_budget_without_global_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock(100.0)
    monkeypatch.setattr(news_fetcher.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    calls: list[tuple[str, float]] = []

    def fake_fetch_feed(url: str, timeout_s: float):
        calls.append((url, timeout_s))
        clock.advance(timeout_s)
        return _feed()

    monkeypatch.setattr(news_fetcher, "_fetch_feed", fake_fetch_feed)

    headlines, summary = news_fetcher.fetch_headlines_for_symbols(
        ["PR61A"],
        ["budget://one", "budget://two", "budget://three"],
        request_timeout_s=5.0,
        source_tier="fast",
        total_news_budget_seconds=8.0,
        stage_started_at_s=clock.monotonic(),
        stage_deadline_s=clock.monotonic() + 8.0,
        tier_budget_seconds=2.0,
        tier_started_at_s=clock.monotonic(),
        tier_deadline_s=clock.monotonic() + 2.0,
    )

    assert headlines == {"PR61A": []}
    assert calls == [("budget://one", pytest.approx(2.0))]
    assert summary.news_budget_exhausted is False
    assert summary.tier_budget_exhausted is True
    assert summary.tier_budget_exhausted_by_tier == {"fast": True}
    assert summary.sources_attempted_count == 1
    assert summary.sources_skipped_due_to_budget_count == 2


def test_pr1061_fast_tier_exhaustion_still_allows_extended_fallback_for_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock(100.0)
    monkeypatch.setattr(scanner_runner.time, "monotonic", clock.monotonic)
    calls: list[tuple[str, list[str], float]] = []

    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        calls.append(("fast", list(symbols), kwargs["tier_budget_seconds"]))
        assert kwargs["total_news_budget_seconds"] == pytest.approx(8.0)
        assert kwargs["tier_budget_seconds"] == pytest.approx(5.2)
        clock.advance(kwargs["tier_budget_seconds"])
        return {symbol: [] for symbol in symbols}, _summary(
            total=len(sources),
            tier="fast",
            budget=8.0,
            elapsed=kwargs["tier_budget_seconds"],
            exhausted=False,
            attempted=1,
            skipped=len(sources) - 1,
            tier_budget=kwargs["tier_budget_seconds"],
            tier_elapsed=kwargs["tier_budget_seconds"],
            tier_exhausted=True,
        )

    def fake_extended(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        calls.append(("extended", list(symbols), kwargs["tier_budget_seconds"]))
        assert list(symbols) == ["PR61A"]
        assert kwargs["tier_budget_seconds"] == pytest.approx(2.8)
        return {"PR61A": [_headline("PR61A reports earnings beat and raises guidance", source_tier="extended")]}, _summary(
            total=len(sources),
            tier="extended",
            matches=1,
            ticker_matches=1,
            budget=8.0,
            elapsed=8.0,
            exhausted=False,
            attempted=1,
            tier_budget=kwargs["tier_budget_seconds"],
            tier_elapsed=0.1,
            tier_exhausted=False,
        )

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fake_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR61A"], "IBKR")

    assert calls == [("fast", ["PR61A"], pytest.approx(5.2)), ("extended", ["PR61A"], pytest.approx(2.8))]
    assert diagnostics.fast_budget_seconds == pytest.approx(5.2)
    assert diagnostics.extended_budget_reserved_seconds == pytest.approx(2.8)
    assert diagnostics.extended_budget_seconds == pytest.approx(2.8)
    assert diagnostics.fast_budget_exhausted is True
    assert diagnostics.extended_budget_exhausted is False
    assert diagnostics.news_budget_exhausted is False
    assert diagnostics.extended_fallback_requested is True
    assert diagnostics.result_status_counts == {"catalyst_confirmed": 1}
    assert news_by_symbol["PR61A"]["ross_catalyst_valid"] is True
    assert news_by_symbol["PR61A"]["news_source_mode"] == "rss_batch_extended"


def test_pr1061_global_budget_exhaustion_remains_unavailable_and_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    set_config_overrides({
        "NEWS_MAX_ENTRIES_PER_SYMBOL": 5,
        "NEWS_TOTAL_BUDGET_S": 0.5,
        "NEWS_EXTENDED_TIER_RESERVE_FRACTION": 0.35,
        "NEWS_CACHE_FILE": str(tmp_path / "news_cache.json"),
    })

    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [] for symbol in symbols}, _summary(
            total=len(sources),
            tier="fast",
            budget=kwargs["total_news_budget_seconds"],
            elapsed=0.5,
            exhausted=True,
            attempted=1,
            skipped=len(sources) - 1,
            tier_budget=kwargs["tier_budget_seconds"],
            tier_elapsed=kwargs["tier_budget_seconds"],
            tier_exhausted=True,
        )

    def fail_extended(*args, **kwargs):
        raise AssertionError("extended fallback must not start after global budget exhaustion")

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fail_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR61A"], "IBKR")

    assert diagnostics.news_budget_exhausted is True
    assert diagnostics.fast_budget_exhausted is True
    assert diagnostics.extended_budget_exhausted is True
    assert diagnostics.symbols_unresolved_at_budget_exhaustion == ["PR61A"]
    assert diagnostics.result_status_counts == {"budget_exhausted": 1}
    assert news_by_symbol["PR61A"]["news_diagnostic_status"] == "budget_exhausted"
    assert news_by_symbol["PR61A"]["news_available"] is False
    assert news_by_symbol["PR61A"]["ross_catalyst_valid"] is False


def test_pr1061_tier_budget_diagnostics_propagate_to_pr1040_artifact() -> None:
    payload = {
        "diagnostics": {
            "news": {
                "provider_status": "available",
                "result_status_counts": {"budget_exhausted": 1},
                "symbols_by_status": {"budget_exhausted": ["PR61A"]},
                "rss_failures": 0,
                "rss_failure_summary": {},
                "total_news_budget_seconds": 8.0,
                "news_elapsed_seconds": 8.0,
                "news_budget_exhausted": True,
                "fast_budget_seconds": 5.2,
                "extended_budget_seconds": 2.8,
                "extended_budget_reserved_seconds": 2.8,
                "fast_budget_exhausted": True,
                "extended_budget_exhausted": True,
                "fast_sources_attempted_count": 1,
                "extended_sources_attempted_count": 1,
                "sources_skipped_due_to_budget_count": 18,
                "symbols_unresolved_at_budget_exhaustion": ["PR61A"],
            }
        },
        "watchlist_k": [
            {
                "symbol": "PR61A",
                "catalyst_present": False,
                "news_diagnostic_status": "budget_exhausted",
                "news_source_mode": "rss_batch_extended",
                "fresh_news_count": 0,
            }
        ],
    }

    artifact = pr1040._catalyst_news_artifact(payload, ["PR61A"], news_asof="2026-08-20T00:00:00+00:00")

    assert artifact["fast_budget_seconds"] == pytest.approx(5.2)
    assert artifact["extended_budget_seconds"] == pytest.approx(2.8)
    assert artifact["extended_budget_reserved_seconds"] == pytest.approx(2.8)
    assert artifact["fast_budget_exhausted"] is True
    assert artifact["extended_budget_exhausted"] is True
    assert artifact["catalyst_status_by_symbol"] == {"PR61A": "DATA_UNAVAILABLE"}


def test_pr1061_pr1040_cleanup_resets_scanner_persistent_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[bool, bool]] = []

    def fake_reset(
        *,
        clear_persistent_provider: bool = True,
        suppress_disconnect_errors: bool = True,
    ) -> None:
        calls.append((clear_persistent_provider, suppress_disconnect_errors))

    monkeypatch.setattr(scanner_runner, "reset_scanner_runtime_state", fake_reset)

    pr1040._cleanup_scanner_runtime_after_observation()

    assert calls == [(True, False)]
