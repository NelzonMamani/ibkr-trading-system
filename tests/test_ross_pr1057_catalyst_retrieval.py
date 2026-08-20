from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.news import news_fetcher
from src.scanner import scanner_runner
from src.config.config_resolver import set_config_overrides
from src.config.runtime_config import RunMode


_ROOT = Path(__file__).resolve().parents[1]
_PR1040_PATH = _ROOT / "scripts" / "certification" / "pr1040_real_readonly_runtime_observation_adapter.py"


def _load_pr1040_module():
    spec = importlib.util.spec_from_file_location("pr1040_adapter_pr1057_test", _PR1040_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pr1040 = _load_pr1040_module()


@pytest.fixture(autouse=True)
def _reset_runtime_state(tmp_path: Path):
    scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True)
    scanner_runner._NEWS_CACHE = {}
    set_config_overrides({"NEWS_MAX_ENTRIES_PER_SYMBOL": 5, "NEWS_CACHE_FILE": str(tmp_path / "news_cache.json")})
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
    return SimpleNamespace(feed={"title": "PR1057_FEED"}, entries=list(entries))


def _patch_feeds(monkeypatch: pytest.MonkeyPatch, feeds_by_url: dict[str, Any]) -> None:
    monkeypatch.setattr(news_fetcher, "feedparser", object())

    def fake_fetch_feed(url: str, timeout_s: float):
        return feeds_by_url[url]

    monkeypatch.setattr(news_fetcher, "_fetch_feed", fake_fetch_feed)


def _headline(title: str, *, age_seconds: int = 300, source_tier: str = "fast") -> scanner_runner.Headline:
    return scanner_runner.Headline(
        title=title,
        source="PR1057_NEWS",
        published_ts=time.time() - age_seconds,
        url="https://news.example/pr1057",
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
) -> scanner_runner.RssFailureSummary:
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
    )


def test_pr1057_exact_ticker_title_and_cash_paren_ticker_matches_still_work(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_feeds(
        monkeypatch,
        {
            "fast://feed": _feed(
                _entry("PR57A reports earnings beat"),
                _entry("$PR57A signs new contract"),
                _entry("(PR57A) announces FDA approval"),
            )
        },
    )

    headlines, summary = news_fetcher.fetch_fast_headlines_for_symbols(
        ["PR57A"],
        ["fast://feed"],
        max_entries_per_symbol=5,
    )

    assert [item.title for item in headlines["PR57A"]] == [
        "PR57A reports earnings beat",
        "$PR57A signs new contract",
        "(PR57A) announces FDA approval",
    ]
    assert {item.match_type for item in headlines["PR57A"]} == {"ticker_token"}
    assert summary.ticker_token_match_count == 3


def test_pr1057_trusted_company_name_title_maps_to_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_feeds(monkeypatch, {"fast://feed": _feed(_entry("Avidity Biosciences wins FDA approval"))})

    headlines, summary = news_fetcher.fetch_fast_headlines_for_symbols(
        ["RNAZ"],
        ["fast://feed"],
        symbol_metadata={"RNAZ": {"company_name": "Avidity Biosciences Inc."}},
    )

    assert [item.title for item in headlines["RNAZ"]] == ["Avidity Biosciences wins FDA approval"]
    assert headlines["RNAZ"][0].match_type == "company_name"
    assert headlines["RNAZ"][0].matched_field == "title"
    assert summary.company_name_match_count == 1


def test_pr1057_company_name_in_summary_maps_when_title_omits_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_feeds(
        monkeypatch,
        {"fast://feed": _feed(_entry("FDA approval granted for lead therapy", summary="Avidity Biosciences announced the update."))},
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


def test_pr1057_unrelated_company_names_do_not_cross_match(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_feeds(monkeypatch, {"fast://feed": _feed(_entry("Beta Robotics signs defense contract"))})

    headlines, summary = news_fetcher.fetch_fast_headlines_for_symbols(
        ["ACME", "RBTX"],
        ["fast://feed"],
        symbol_metadata={
            "ACME": {"company_name": "Acme Therapeutics Inc."},
            "RBTX": {"company_name": "Beta Robotics Corp."},
        },
    )

    assert headlines["ACME"] == []
    assert [item.title for item in headlines["RBTX"]] == ["Beta Robotics signs defense contract"]
    assert summary.company_name_match_count == 1


def test_pr1057_fetcher_keeps_later_qualifying_headline_after_earlier_generic_match(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_feeds(
        monkeypatch,
        {
            "fast://feed": _feed(
                _entry("PR57A mentioned in morning market wrap"),
                _entry("PR57A reports earnings beat and raises guidance"),
            )
        },
    )

    headlines, _summary_obj = news_fetcher.fetch_fast_headlines_for_symbols(
        ["PR57A"],
        ["fast://feed"],
        max_entries_per_symbol=5,
    )

    assert [item.title for item in headlines["PR57A"]] == [
        "PR57A mentioned in morning market wrap",
        "PR57A reports earnings beat and raises guidance",
    ]


def test_pr1057_generic_matching_news_remains_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [_headline(f"{symbol} mentioned in market wrap")] for symbol in symbols}, _summary(matches=1, ticker_matches=1)

    def fake_extended(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [] for symbol in symbols}, _summary(total=len(sources), tier="extended")

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fake_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR57A"], "IBKR")

    assert news_by_symbol["PR57A"]["news_diagnostic_status"] == "news_present_non_qualifying"
    assert news_by_symbol["PR57A"]["ross_catalyst_valid"] is False
    assert diagnostics.result_status_counts == {"news_present_non_qualifying": 1}
    assert diagnostics.non_qualifying_headline_count == 1


def test_pr1057_later_qualifying_headline_confirms_after_earlier_generic_match(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {
            symbol: [
                _headline(f"{symbol} mentioned in market wrap"),
                _headline(f"{symbol} reports earnings beat and raises guidance"),
            ]
            for symbol in symbols
        }, _summary(matches=2, ticker_matches=2)

    def fail_extended(*args, **kwargs):
        raise AssertionError("extended fallback should not run after confirmed fast catalyst")

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fail_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR57A"], "IBKR")

    assert news_by_symbol["PR57A"]["news_diagnostic_status"] == "catalyst_confirmed"
    assert news_by_symbol["PR57A"]["ross_catalyst_valid"] is True
    assert diagnostics.result_status_counts == {"catalyst_confirmed": 1}
    assert diagnostics.qualifying_headline_count == 1


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        (_summary(total=2, failures=2, reason="feedparser_missing"), "provider_unavailable"),
        (_summary(total=2, failures=2, reason=None), "provider_request_failure"),
    ],
)
def test_pr1057_provider_failure_remains_data_unavailable_and_skips_extended(monkeypatch: pytest.MonkeyPatch, summary, expected: str) -> None:
    extended_called = False

    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [] for symbol in symbols}, summary

    def fake_extended(*args, **kwargs):
        nonlocal extended_called
        extended_called = True
        return {}, _summary(tier="extended")

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fake_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR57A"], "IBKR")

    assert extended_called is False
    assert diagnostics.provider_status == expected
    assert diagnostics.result_status_counts == {expected: 1}
    assert news_by_symbol["PR57A"]["news_available"] is False
    assert news_by_symbol["PR57A"]["ross_catalyst_valid"] is False


def test_pr1057_no_matching_news_remains_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [] for symbol in symbols}, _summary()

    def fake_extended(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {symbol: [] for symbol in symbols}, _summary(total=len(sources), tier="extended")

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fake_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR57A"], "IBKR")

    assert diagnostics.provider_status == "available"
    assert diagnostics.result_status_counts == {"no_recent_news": 1}
    assert news_by_symbol["PR57A"]["news_available"] is True
    assert news_by_symbol["PR57A"]["ross_catalyst_valid"] is False


def test_pr1057_extended_fallback_is_bounded_and_only_for_unresolved_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    extended_symbols: list[str] = []

    def fake_fast(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        return {
            "FAST": [_headline("FAST reports earnings beat and raises guidance")],
            "SLOW": [],
        }, _summary(matches=1, ticker_matches=1)

    def fake_extended(symbols, sources, lookback_hours=24.0, request_timeout_s=5.0, **kwargs):
        extended_symbols.extend(symbols)
        return {
            "SLOW": [_headline("SLOW announces new AI contract", source_tier="extended")],
        }, _summary(total=len(sources), tier="extended", matches=1, ticker_matches=1)

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fake_extended)

    news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["FAST", "SLOW"], "IBKR")

    assert extended_symbols == ["SLOW"]
    assert news_by_symbol["FAST"]["ross_catalyst_valid"] is True
    assert news_by_symbol["SLOW"]["ross_catalyst_valid"] is True
    assert news_by_symbol["SLOW"]["news_source_mode"] == "rss_batch_extended"
    assert diagnostics.extended_fallback_requested is True
    assert diagnostics.extended_fallback_symbol_count == 1
    assert diagnostics.tier_source_counts["extended"] == len(scanner_runner.RSS_PREP_EXTENDED)
    assert diagnostics.tier_match_counts["extended"] == 1


def test_pr1057_paper_and_live_news_behavior_remains_disabled() -> None:
    for run_mode, expected in (
        (RunMode.PAPER, "provider_disabled_for_paper"),
        (RunMode.LIVE, "provider_disabled_for_live"),
    ):
        diagnostics = scanner_runner._disabled_news_diagnostics(
            news_enabled=True,
            run_mode=run_mode,
            explicit_mock=False,
            symbols=["PR57A"],
        )
        assert diagnostics.provider_status == expected
        assert diagnostics.result_status_counts == {expected: 1}


def test_pr1057_readonly_broker_mutation_remains_disabled() -> None:
    env = pr1040.build_safe_readonly_env({})

    assert env["RUN_MODE"] == "READ_ONLY"
    assert env["EXECUTION_ENABLED"] == "false"
    assert env["IBKR_API_WRITE_ALLOWED"] == "false"
    assert env["IBKR_ORDER_SUBMISSION_ENABLED"] == "false"


def test_pr1057_pr1056_artifact_propagation_keeps_retrieval_diagnostics() -> None:
    payload = {
        "diagnostics": {
            "news": {
                "provider_status": "available",
                "result_status_counts": {"catalyst_confirmed": 1},
                "symbols_by_status": {"catalyst_confirmed": ["PR57A"]},
                "rss_failures": 0,
                "rss_failure_summary": {},
                "no_recent_news_count": 0,
                "news_present_non_qualifying_count": 0,
                "confirmed_catalyst_count": 1,
                "queried_source_tiers": {"fast": 7, "extended": 13},
                "queried_source_count": 20,
                "fast_tier_match_count": 1,
                "extended_tier_match_count": 1,
                "extended_fallback_requested": True,
                "extended_fallback_symbol_count": 1,
                "ticker_token_match_count": 1,
                "company_name_match_count": 1,
                "description_summary_match_count": 1,
                "qualifying_headline_count": 1,
                "non_qualifying_headline_count": 1,
                "max_entries_per_symbol": 5,
            }
        },
        "watchlist_k": [
            {
                "symbol": "PR57A",
                "catalyst_present": True,
                "news_diagnostic_status": "catalyst_confirmed",
                "news_source_mode": "rss_batch_extended",
                "fresh_news_count": 1,
            }
        ],
    }

    artifact = pr1040._catalyst_news_artifact(payload, ["PR57A"], news_asof="2026-08-20T00:00:00+00:00")

    assert artifact["provider_status"] == "available"
    assert artifact["queried_source_tiers"] == {"fast": 7, "extended": 13}
    assert artifact["extended_fallback_requested"] is True
    assert artifact["company_name_match_count"] == 1
    assert artifact["description_summary_match_count"] == 1
    assert artifact["catalyst_status_by_symbol"] == {"PR57A": "CONFIRMED"}