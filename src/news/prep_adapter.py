"""Prep-shaped views of canonical news evidence; no retrieval/cache authority."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.config.config_resolver import get_config
from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
from src.news.news_intelligence_service import CanonicalNewsIntelligenceService


@dataclass
class NewsItem:
    title: str
    source: str
    published_at: str | None
    url: str
    age_hours: float | None
    freshness: str
    catalyst_tag: str


@dataclass
class NewsResult:
    symbol: str
    fetched_at: str
    source_mode: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    news_context: list[dict[str, Any]] = field(default_factory=list)


class NewsProvider:
    """Compatibility result shape for preparation and inspection consumers.

    One batch goes through the same service as scanner evidence. Receipt time
    never substitutes for publication time, and this adapter does not classify
    catalysts or retain a second cache. Strategy eligibility remains downstream.
    """

    def __init__(self, *, service=None) -> None:
        self.service = service if service is not None else CanonicalNewsIntelligenceService()

    @property
    def cache_file(self):
        return self.service.evidence_store.cache_path

    def get_news(self, symbol: str) -> NewsResult:
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return NewsResult("", datetime.now(timezone.utc).isoformat(), "invalid")
        return self.get_news_batch([normalized])[normalized]

    def get_news_batch(self, symbols: list[str]) -> dict[str, NewsResult]:
        candidates = tuple(NewsCandidate(symbol=s) for s in dict.fromkeys(
            str(value or "").strip().upper() for value in symbols
        ) if s)
        if not candidates:
            return {}
        enabled = bool(get_config("NEWS_ENABLED"))
        result = self.service.get_news(
            candidates,
            NewsRequest(
                lookback_seconds=float(get_config("NEWS_LOOKBACK_HOURS")) * 3600,
                freshness_seconds=float(get_config("NEWS_MAX_AGE_HOURS")) * 3600,
                max_evidence_per_symbol=int(get_config("NEWS_MAX_ENTRIES_PER_SYMBOL")),
                include_generic_news=True,
                audit_reason="premarket_prep",
            ),
            RetrievalPolicy(
                source_groups=("FAST_TRADING",),
                network_allowed=enabled,
                allow_cache_read=enabled,
                allow_cache_write=enabled,
                refresh_mode="bounded_refresh" if enabled else "disabled",
                total_budget_seconds=float(get_config("NEWS_TOTAL_BUDGET_S")),
                request_timeout_seconds=float(get_config("NEWS_REQUEST_TIMEOUT_S")),
                fallback_mode="none",
                refresh_interval_seconds=float(get_config("NEWS_REFRESH_SECONDS_PREP")),
            ),
        )
        output = {}
        for candidate in candidates:
            symbol = candidate.normalized_symbol
            evidence = result.evidence_by_symbol.get(symbol, ())
            context = []
            for item in evidence:
                row = asdict(NewsItem(
                    title=item.headline or "",
                    source=item.original_source or item.observed_source or "",
                    published_at=item.published_at.isoformat() if item.published_at else None,
                    url=item.url or "",
                    age_hours=item.age_seconds / 3600 if item.age_seconds is not None else None,
                    freshness="fresh" if item.stale is False else "stale" if item.stale is True else "unknown",
                    catalyst_tag=item.event_class or "generic",
                ))
                row.update(evidence_id=item.evidence_id, provider=item.provider,
                           summary=item.summary, company_name=item.company_name,
                           aliases=list(item.aliases), matched_field=item.matched_field,
                           match_type=item.match_type, match_confidence=item.match_confidence,
                           fetched_at=item.fetched_at.isoformat() if item.fetched_at else None,
                           retrieval_status=item.retrieval_status)
                context.append(row)
            summary = result.summary_for_symbol(symbol)
            output[symbol] = NewsResult(
                symbol=symbol,
                fetched_at=(result.completed_at or datetime.now(timezone.utc)).isoformat(),
                source_mode=self.service.provider_id,
                diagnostics={"retrieval": asdict(result.diagnostics),
                             "summary": asdict(summary) if summary else None},
                news_context=context,
            )
        return output
