from __future__ import annotations

import time
from collections import Counter
from typing import Any, Iterable

from src.news.news_fetcher import Headline, RssFailureSummary


def merge_rss_failure_summaries(*summaries: Any) -> RssFailureSummary:
    total_sources = 0
    failure_count = 0
    failures_by_domain: dict[str, dict[str, int]] = {}
    reason: str | None = None
    tier_source_counts: Counter[str] = Counter()
    tier_match_counts: Counter[str] = Counter()
    tier_sources_attempted_counts: Counter[str] = Counter()
    ticker_token_match_count = 0
    company_name_match_count = 0
    description_summary_match_count = 0
    max_entries_per_symbol = 0
    total_news_budget_seconds = 0.0
    news_elapsed_seconds = 0.0
    news_budget_exhausted = False
    sources_attempted_count = 0
    sources_skipped_due_to_budget_count = 0
    tier_budget_seconds = 0.0
    tier_elapsed_seconds = 0.0
    tier_budget_exhausted = False
    tier_budget_seconds_by_tier: dict[str, float] = {}
    tier_elapsed_seconds_by_tier: dict[str, float] = {}
    tier_budget_exhausted_by_tier: dict[str, bool] = {}
    source_diagnostics: list[dict[str, Any]] = []
    unique_source_urls_scheduled_count = 0
    unique_source_urls_attempted_count = 0
    duplicate_source_fetches_avoided_count = 0
    for summary in summaries:
        if summary is None:
            continue
        total_sources += int(getattr(summary, "total_sources", 0) or 0)
        failure_count += int(getattr(summary, "failure_count", 0) or 0)
        if reason is None:
            raw_reason = getattr(summary, "reason", None)
            reason = str(raw_reason) if raw_reason else None
        for domain, codes in dict(getattr(summary, "failures_by_domain", {}) or {}).items():
            bucket = failures_by_domain.setdefault(str(domain), {})
            if isinstance(codes, dict):
                for code, count in codes.items():
                    bucket[str(code)] = bucket.get(str(code), 0) + int(count or 0)
        tier_source_counts.update(dict(getattr(summary, "tier_source_counts", {}) or {}))
        tier_match_counts.update(dict(getattr(summary, "tier_match_counts", {}) or {}))
        tier_sources_attempted_counts.update(dict(getattr(summary, "tier_sources_attempted_counts", {}) or {}))
        ticker_token_match_count += int(getattr(summary, "ticker_token_match_count", 0) or 0)
        company_name_match_count += int(getattr(summary, "company_name_match_count", 0) or 0)
        description_summary_match_count += int(getattr(summary, "description_summary_match_count", 0) or 0)
        max_entries_per_symbol = max(max_entries_per_symbol, int(getattr(summary, "max_entries_per_symbol", 0) or 0))
        total_news_budget_seconds = max(
            total_news_budget_seconds,
            float(getattr(summary, "total_news_budget_seconds", 0.0) or 0.0),
        )
        news_elapsed_seconds = max(news_elapsed_seconds, float(getattr(summary, "news_elapsed_seconds", 0.0) or 0.0))
        news_budget_exhausted = news_budget_exhausted or bool(getattr(summary, "news_budget_exhausted", False))
        sources_attempted_count += int(getattr(summary, "sources_attempted_count", 0) or 0)
        sources_skipped_due_to_budget_count += int(getattr(summary, "sources_skipped_due_to_budget_count", 0) or 0)
        source_diagnostics.extend(dict(item) for item in tuple(getattr(summary, "source_diagnostics", ()) or ()))
        unique_source_urls_scheduled_count += int(getattr(summary, "unique_source_urls_scheduled_count", 0) or 0)
        unique_source_urls_attempted_count += int(getattr(summary, "unique_source_urls_attempted_count", 0) or 0)
        duplicate_source_fetches_avoided_count += int(getattr(summary, "duplicate_source_fetches_avoided_count", 0) or 0)
        tier_budget_seconds = max(tier_budget_seconds, float(getattr(summary, "tier_budget_seconds", 0.0) or 0.0))
        tier_elapsed_seconds = max(tier_elapsed_seconds, float(getattr(summary, "tier_elapsed_seconds", 0.0) or 0.0))
        tier_budget_exhausted = tier_budget_exhausted or bool(getattr(summary, "tier_budget_exhausted", False))
        for tier, value in dict(getattr(summary, "tier_budget_seconds_by_tier", {}) or {}).items():
            key = str(tier)
            tier_budget_seconds_by_tier[key] = max(tier_budget_seconds_by_tier.get(key, 0.0), float(value or 0.0))
        for tier, value in dict(getattr(summary, "tier_elapsed_seconds_by_tier", {}) or {}).items():
            key = str(tier)
            tier_elapsed_seconds_by_tier[key] = max(tier_elapsed_seconds_by_tier.get(key, 0.0), float(value or 0.0))
        for tier, value in dict(getattr(summary, "tier_budget_exhausted_by_tier", {}) or {}).items():
            key = str(tier)
            tier_budget_exhausted_by_tier[key] = bool(tier_budget_exhausted_by_tier.get(key, False) or value)
    return RssFailureSummary(
        total_sources=total_sources,
        failure_count=failure_count,
        failures_by_domain=failures_by_domain,
        reason=reason,
        tier_source_counts=dict(tier_source_counts),
        tier_match_counts=dict(tier_match_counts),
        ticker_token_match_count=ticker_token_match_count,
        company_name_match_count=company_name_match_count,
        description_summary_match_count=description_summary_match_count,
        max_entries_per_symbol=max_entries_per_symbol,
        total_news_budget_seconds=total_news_budget_seconds,
        news_elapsed_seconds=news_elapsed_seconds,
        news_budget_exhausted=news_budget_exhausted,
        sources_attempted_count=sources_attempted_count,
        sources_skipped_due_to_budget_count=sources_skipped_due_to_budget_count,
        tier_sources_attempted_counts=dict(tier_sources_attempted_counts),
        tier_budget_seconds=tier_budget_seconds,
        tier_elapsed_seconds=tier_elapsed_seconds,
        tier_budget_exhausted=tier_budget_exhausted,
        tier_budget_seconds_by_tier=tier_budget_seconds_by_tier,
        tier_elapsed_seconds_by_tier=tier_elapsed_seconds_by_tier,
        tier_budget_exhausted_by_tier=tier_budget_exhausted_by_tier,
        source_diagnostics=tuple(source_diagnostics),
        unique_source_urls_scheduled_count=unique_source_urls_scheduled_count,
        unique_source_urls_attempted_count=unique_source_urls_attempted_count,
        duplicate_source_fetches_avoided_count=duplicate_source_fetches_avoided_count,
    )


def news_provider_status(summary: Any) -> str:
    reason = str(getattr(summary, "reason", "") or "")
    total_sources = int(getattr(summary, "total_sources", 0) or 0)
    failure_count = int(getattr(summary, "failure_count", 0) or 0)
    if reason == "no_symbols":
        return "no_symbols"
    if reason in {"no_sources", "feedparser_missing"}:
        return "provider_unavailable"
    if total_sources > 0 and failure_count >= total_sources:
        return "provider_request_failure"
    if failure_count > 0:
        return "partial_request_failure"
    return "available"


def dedupe_bounded_headlines(headlines: Iterable[Headline], max_entries_per_symbol: int) -> list[Headline]:
    max_entries = max(1, int(max_entries_per_symbol or 1))
    result: list[Headline] = []
    seen: set[str] = set()
    for headline in headlines:
        key = f"{headline.title.lower().strip()}|{headline.source.lower().strip()}"
        if key in seen:
            continue
        seen.add(key)
        result.append(headline)
        if len(result) >= max_entries:
            break
    return result


def extended_tier_reserve_fraction(raw_value: Any) -> float:
    try:
        raw = float(raw_value or 0.0)
    except Exception:
        return 0.0
    return min(max(raw, 0.0), 0.9)


def fast_tier_budget_seconds(
    total_budget_seconds: float,
    *,
    extended_sources_available: bool,
    extended_reserve_fraction: float,
) -> float:
    total = max(0.0, float(total_budget_seconds or 0.0))
    if total <= 0.0 or not extended_sources_available:
        return total
    reserve = total * extended_reserve_fraction
    if reserve <= 0.0:
        return total
    return max(0.001, total - reserve)


def stage_remaining_seconds(stage_deadline_s: float) -> float:
    return max(0.0, float(stage_deadline_s) - time.monotonic())


def stage_elapsed_seconds(stage_started_at_s: float) -> float:
    return max(0.0, time.monotonic() - float(stage_started_at_s))


__all__ = [
    "dedupe_bounded_headlines",
    "extended_tier_reserve_fraction",
    "fast_tier_budget_seconds",
    "merge_rss_failure_summaries",
    "news_provider_status",
    "stage_elapsed_seconds",
    "stage_remaining_seconds",
]
