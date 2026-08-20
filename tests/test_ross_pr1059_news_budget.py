from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode
from src.news import news_fetcher
from src.scanner import scanner_runner


_ROOT = Path(__file__).resolve().parents[1]
_PR1040_PATH = _ROOT / "scripts" / "certification" / "pr1040_real_readonly_runtime_observation_adapter.py"


def _load_pr1040_module():
    spec = importlib.util.spec_from_file_location("pr1040_adapter_pr1059_test", _PR1040_PATH)
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
    set_config_overrides({"NEWS_MAX_ENTRIES_PER_SYMBOL": 5, "NEWS_TOTAL_BUDGET_S": 5.0, "NEWS_CACHE_FILE": str(tmp_path / "news_cache.json")})
    yield
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._NEWS_CACHE = {}
    set_config_overrides({})


def _entry(title: str, *, summary: str = "", age_seconds: int = 300):
    return SimpleNamespace(
        title=title,
        summary=summary,
        link=f"https://news.example/{title.lower().replace(' ', '-')}",
        published_parsed=time.gmtime(time.time() - age_seconds),
    )


def _feed(*entries):
    return SimpleNamespace(feed={"title": "PR1059_FEED"}, entries=list(entries))


def _headline(title: str, *, age_seconds: int = 300, source_tier: str = "fast") -> scanner_runner.Headline:
    return scanner_runner.Headline(
        title=title,
        source="PR1059_NEWS",
        published_ts=time.time() - age_seconds,
        url="https://news.example/pr1059",
        source_tier=source_tier,
    )


def _summary(
    *,
    total: int = 2,
    failures: int = 0,
    reason: str | None = None,
    tier: str = "fast",
    matches: int = 0,
    ticker_matches: int = 0,
    company_matches: int = 0,
    summary_matches: int = 0,
    budget: float = 5.0,
    elapsed: float = 0.0,
    exhausted: bool = False,
    attempted: int | None = None,
    skipped: int = 0,
) -> scanner_runner.RssFailureSummary:
    attempted_count = total if attempted is None else attempted
    return scanner_runner.RssFailureSummary(
        total_sources=total,
        failure_count=failures,
        failures_by_domain={"news.example": {"TIMEOUT": failures}} if failures else {},
        reason=reason,
        tier_source_counts={tier: total} if total else {},
        tier_match_counts={tier: matches} if matches else {},
        ticker_token_match_count=ticker_matches,
        company_name_match_count=company_matches,
        description_summary_match_count=summary_matches,
        max_entries_per_symbol=5,
        total_news_budget_seconds=budget,
        news_elapsed_seconds=elapsed,
        news_budget_exhausted=exhausted,
        sources_attempted_count=attempted_count,
        sources_skipped_due_to_budget_count=skipped,
        tier_sources_attempted_counts={tier: attempted_count} if total else {},
    )


def test_pr1059_fetcher_clamps_timeout_and_skips_sources_after_budget(monkeypatch: pytest.MonkeyPatch) -> None:
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
        ["PR59A"],
        ["budget://one", "budget://two", "budget://three"],
        request_timeout_s=5.0,
        source_tier="extended",
        total_news_budget_seconds=1.5,
        stage_started_at_s=clock.monotonic(),
        stage_deadline_s=clock.monotonic() + 1.5,
    )

    assert headlines == {"PR59A": []}
    assert calls == [("budget://one", pytest.approx(1.5))]
    assert summary.total_news_budget_seconds == pytest.approx(1.5)
    assert summary.news_elapsed_seconds == pytest.approx(1.5)
    assert summary.news_elapsed_seconds <= summary.total_news_budget_seconds
    assert summary.news_budget_exhausted is True
    assert summary.sources_attempted_count == 1
    assert summary.tier_sources_attempted_counts == {"extended": 1}
    assert summary.sources_skipped_due_to_budget_count == 2


def test_pr1059_fast_first_and_extended_only_unresolved_when_budget_remains(monkeypatch: pytest.MonkeyPatch) -> None:
    call_order: list[tuple[str, list[str], float]] = []

    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        call_order.append(("fast", list(symbols), kwargs["total_news_budget_seconds"]))
        return {
            "FAST": [_headline("FAST reports earnings beat and raises guidance")],
            "SLOW": [],
        }, _summary(total=len(sources), tier="fast", matches=1, ticker_matches=1, attempted=len(sources), elapsed=0.5)

    def fake_extended(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        call_order.append(("extended", list(symbols), kwargs["total_news_budget_seconds"]))
        return {
            "SLOW": [_headline("SLOW announces new AI contract", source_tier="extended")],
        }, _summary(total=len(sources), tier="extended", matches=1, ticker_matches=1, attempted=len(sources), elapsed=1.0)

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fake_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["FAST", "SLOW"], "IBKR")

    assert call_order == [("fast", ["FAST", "SLOW"], 5.0), ("extended", ["SLOW"], 5.0)]
    assert news_by_symbol["FAST"]["ross_catalyst_valid"] is True
    assert news_by_symbol["SLOW"]["ross_catalyst_valid"] is True
    assert diagnostics.fast_sources_attempted_count == len(scanner_runner.RSS_FAST_TRADING)
    assert diagnostics.extended_sources_attempted_count == len(scanner_runner.RSS_PREP_EXTENDED)
    assert diagnostics.news_budget_exhausted is False


def test_pr1059_budget_exhaustion_skips_extended_and_stays_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    set_config_overrides({"NEWS_MAX_ENTRIES_PER_SYMBOL": 5, "NEWS_TOTAL_BUDGET_S": 0.5, "NEWS_CACHE_FILE": str(tmp_path / "news_cache.json")})

    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [] for symbol in symbols}, _summary(
            total=len(sources),
            tier="fast",
            budget=kwargs["total_news_budget_seconds"],
            elapsed=0.5,
            exhausted=True,
            attempted=1,
            skipped=len(sources) - 1,
        )

    def fail_extended(*args, **kwargs):
        raise AssertionError("extended fallback must not start after news budget exhaustion")

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fail_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR59A"], "IBKR")

    assert diagnostics.news_budget_exhausted is True
    assert diagnostics.fast_sources_attempted_count == 1
    assert diagnostics.extended_sources_attempted_count == 0
    assert diagnostics.sources_skipped_due_to_budget_count == (len(scanner_runner.RSS_FAST_TRADING) - 1 + len(scanner_runner.RSS_PREP_EXTENDED))
    assert diagnostics.symbols_unresolved_at_budget_exhaustion == ["PR59A"]
    assert diagnostics.result_status_counts == {"budget_exhausted": 1}
    assert news_by_symbol["PR59A"]["news_diagnostic_status"] == "budget_exhausted"
    assert news_by_symbol["PR59A"]["ross_catalyst_valid"] is False
    assert news_by_symbol["PR59A"]["news_available"] is False


def test_pr1059_confirmed_catalyst_before_budget_exhaustion_confirms_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [_headline(f"{symbol} reports earnings beat and raises guidance")] for symbol in symbols}, _summary(
            total=len(sources), tier="fast", matches=1, ticker_matches=1, attempted=1, elapsed=0.2
        )

    def fail_extended(*args, **kwargs):
        raise AssertionError("extended fallback should not run after confirmed fast catalyst")

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fail_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR59A"], "IBKR")

    assert news_by_symbol["PR59A"]["news_diagnostic_status"] == "catalyst_confirmed"
    assert news_by_symbol["PR59A"]["ross_catalyst_valid"] is True
    assert diagnostics.news_budget_exhausted is False
    assert diagnostics.result_status_counts == {"catalyst_confirmed": 1}


def test_pr1059_generic_news_remains_non_confirming_when_budget_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [_headline(f"{symbol} mentioned in market wrap")] for symbol in symbols}, _summary(
            total=len(sources), tier="fast", matches=1, ticker_matches=1, attempted=len(sources), elapsed=0.5
        )

    def fake_extended(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [] for symbol in symbols}, _summary(total=len(sources), tier="extended", attempted=len(sources), elapsed=1.0)

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fake_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR59A"], "IBKR")

    assert news_by_symbol["PR59A"]["news_diagnostic_status"] == "news_present_non_qualifying"
    assert news_by_symbol["PR59A"]["ross_catalyst_valid"] is False
    assert diagnostics.news_budget_exhausted is False
    assert diagnostics.result_status_counts == {"news_present_non_qualifying": 1}


def test_pr1059_provider_failure_remains_fail_closed_and_skips_extended(monkeypatch: pytest.MonkeyPatch) -> None:
    extended_called = False

    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [] for symbol in symbols}, _summary(
            total=len(sources), failures=len(sources), reason=None, tier="fast", attempted=len(sources), elapsed=0.5
        )

    def fake_extended(*args, **kwargs):
        nonlocal extended_called
        extended_called = True
        return {}, _summary(tier="extended")

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fake_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR59A"], "IBKR")

    assert extended_called is False
    assert diagnostics.provider_status == "provider_request_failure"
    assert diagnostics.result_status_counts == {"provider_request_failure": 1}
    assert news_by_symbol["PR59A"]["ross_catalyst_valid"] is False
    assert news_by_symbol["PR59A"]["news_available"] is False


def test_pr1059_pr1057_company_name_summary_matching_remains_intact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(news_fetcher, "feedparser", object())
    monkeypatch.setattr(
        news_fetcher,
        "_fetch_feed",
        lambda url, timeout_s: _feed(_entry("FDA approval granted for lead therapy", summary="Avidity Biosciences announced the update.")),
    )

    headlines, summary = news_fetcher.fetch_fast_headlines_for_symbols(
        ["RNAZ"],
        ["fast://feed"],
        symbol_metadata={"RNAZ": {"issuer_name": "Avidity Biosciences Inc."}},
    )

    assert [item.title for item in headlines["RNAZ"]] == ["FDA approval granted for lead therapy"]
    assert headlines["RNAZ"][0].match_type == "company_name"
    assert headlines["RNAZ"][0].matched_field == "summary"
    assert summary.description_summary_match_count == 1


def test_pr1059_budget_diagnostics_propagate_to_pr1040_artifact() -> None:
    payload = {
        "diagnostics": {
            "news": {
                "provider_status": "available",
                "result_status_counts": {"budget_exhausted": 1},
                "symbols_by_status": {"budget_exhausted": ["PR59A"]},
                "rss_failures": 0,
                "rss_failure_summary": {},
                "total_news_budget_seconds": 0.5,
                "news_elapsed_seconds": 0.5,
                "news_budget_exhausted": True,
                "fast_sources_attempted_count": 1,
                "extended_sources_attempted_count": 0,
                "sources_skipped_due_to_budget_count": 14,
                "symbols_unresolved_at_budget_exhaustion": ["PR59A"],
            }
        },
        "watchlist_k": [
            {
                "symbol": "PR59A",
                "catalyst_present": False,
                "news_diagnostic_status": "budget_exhausted",
                "news_source_mode": "rss_batch",
                "fresh_news_count": 0,
            }
        ],
    }

    artifact = pr1040._catalyst_news_artifact(payload, ["PR59A"], news_asof="2026-08-20T00:00:00+00:00")

    assert artifact["news_budget_exhausted"] is True
    assert artifact["fast_sources_attempted_count"] == 1
    assert artifact["extended_sources_attempted_count"] == 0
    assert artifact["sources_skipped_due_to_budget_count"] == 14
    assert artifact["symbols_unresolved_at_budget_exhaustion"] == ["PR59A"]
    assert artifact["catalyst_diagnostic_status_by_symbol"] == {"PR59A": "budget_exhausted"}
    assert artifact["catalyst_status_by_symbol"] == {"PR59A": "DATA_UNAVAILABLE"}


def test_pr1059_paper_live_news_behavior_and_broker_mutation_remain_disabled() -> None:
    for run_mode, expected in (
        (RunMode.PAPER, "provider_disabled_for_paper"),
        (RunMode.LIVE, "provider_disabled_for_live"),
    ):
        diagnostics = scanner_runner._disabled_news_diagnostics(
            news_enabled=True,
            run_mode=run_mode,
            explicit_mock=False,
            symbols=["PR59A"],
        )
        assert diagnostics.provider_status == expected
        assert diagnostics.result_status_counts == {expected: 1}

    env = pr1040.build_safe_readonly_env({})
    assert env["RUN_MODE"] == "READ_ONLY"
    assert env["EXECUTION_ENABLED"] == "false"
    assert env["IBKR_API_WRITE_ALLOWED"] == "false"
    assert env["IBKR_ORDER_SUBMISSION_ENABLED"] == "false"