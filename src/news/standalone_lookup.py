"""Standalone research views over the canonical news service (no trading policy)."""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Sequence

from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
from src.news.source_groups import get_source_group_urls

RESEARCH_PROFILE = "standalone_research_v1"
SUPPORTED_SOURCE_GROUPS = ("FAST_TRADING", "PREP_EXTENDED")
MASSIVE_SOURCE_GROUP = "MASSIVE_TICKER_NEWS"
MASSIVE_PROVIDER_ID = "massive_ticker_news"
DEFAULT_CACHE_FILE = Path(__file__).resolve().parents[2] / "output" / "news_lookup" / "news_cache.json"


@dataclass(frozen=True)
class LookupSettings:
    lookback_hours: float = 24.0
    budget_seconds: float = 30.0
    request_timeout_seconds: float = 5.0
    cleanup_seconds: float = 10.0
    refresh_interval_seconds: float = 300.0
    max_items: int = 20
    source_groups: tuple[str, ...] = SUPPORTED_SOURCE_GROUPS
    cache_mode: str = "use"
    cache_file: Path = DEFAULT_CACHE_FILE
    prep_file: Path | None = None
    provider: str = "rss"
    published_after: datetime | str | None = None
    published_before: datetime | str | None = None
    massive_page_size: int = 100
    massive_max_pages_per_symbol: int = 2
    massive_max_requests: int = 5

    def validated(self) -> LookupSettings:
        for name, upper, allow_zero in (
            ("lookback_hours", 720.0, False), ("budget_seconds", 120.0, False),
            ("request_timeout_seconds", 15.0, False), ("cleanup_seconds", 30.0, True),
            ("refresh_interval_seconds", 86400.0, True),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0 or (not allow_zero and float(value) == 0) or float(value) > upper:
                raise ValueError(f"{name} must be {'between 0 and' if allow_zero else 'greater than 0 and at most'} {upper}")
        if isinstance(self.max_items, bool) or not isinstance(self.max_items, int) or not 1 <= self.max_items <= 100:
            raise ValueError("max_items must be an integer between 1 and 100")
        if self.cache_mode not in {"use", "refresh", "only", "off"}:
            raise ValueError("cache_mode must be use, refresh, only or off")
        provider = str(self.provider).strip().lower()
        if provider not in {"rss", "massive"}:
            raise ValueError("provider must be rss or massive")
        for name, upper in (("massive_page_size", 1000), ("massive_max_pages_per_symbol", 10), ("massive_max_requests", 50)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
                raise ValueError(f"{name} must be an integer between 1 and {upper}")
        start = _publication_boundary(self.published_after, "published_after")
        end = _publication_boundary(self.published_before, "published_before")
        if (start is None) != (end is None):
            raise ValueError("--published-after and --published-before must be supplied together")
        if start is not None:
            if provider != "massive":
                raise ValueError("Explicit publication windows require --provider massive")
            if start >= end:
                raise ValueError("--published-after must be earlier than --published-before")
            if end > datetime.now(timezone.utc):
                raise ValueError("--published-before must not be in the future")
            if (end - start).total_seconds() > 720 * 3600:
                raise ValueError("An explicit publication window may span at most 720 hours")
        requested = tuple(dict.fromkeys(str(group).strip().upper() for group in self.source_groups))
        if provider == "massive":
            if requested not in {SUPPORTED_SOURCE_GROUPS, (MASSIVE_SOURCE_GROUP,)}:
                raise ValueError("Massive selection uses only MASSIVE_TICKER_NEWS")
            ordered = (MASSIVE_SOURCE_GROUP,)
        else:
            if not requested or any(group not in SUPPORTED_SOURCE_GROUPS for group in requested):
                raise ValueError("source_groups must select FAST_TRADING and/or PREP_EXTENDED")
            # The existing adapter owns FAST-before-EXTENDED order.
            ordered = tuple(group for group in SUPPORTED_SOURCE_GROUPS if group in requested)
        return replace(self, provider=provider, published_after=start, published_before=end,
                       source_groups=ordered, cache_file=Path(self.cache_file),
                       prep_file=Path(self.prep_file) if self.prep_file is not None else None)


def _publication_boundary(value, name):
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO 8601 timestamp with timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return str(value)


def normalize_candidates(values: Sequence[str | NewsCandidate]) -> tuple[NewsCandidate, ...]:
    ordered: dict[str, NewsCandidate] = {}
    for value in values:
        candidate = value if isinstance(value, NewsCandidate) else NewsCandidate(str(value or ""))
        symbol = candidate.normalized_symbol
        if not symbol:
            continue
        if len(symbol) > 30 or any(character.isspace() for character in symbol):
            raise ValueError(f"Invalid ticker: {symbol!r}")
        candidate = replace(candidate, symbol=symbol)
        if symbol not in ordered:
            ordered[symbol] = candidate
            continue
        previous = ordered[symbol]
        additions = {field.name: getattr(candidate, field.name) for field in fields(candidate)
                     if field.name not in {"symbol", "aliases", "metadata"} and getattr(previous, field.name) is None}
        ordered[symbol] = replace(previous, **additions,
                                  aliases=tuple(dict.fromkeys((*previous.aliases, *candidate.aliases))),
                                  metadata={**dict(candidate.metadata), **dict(previous.metadata)})
    if not ordered:
        raise ValueError("Supply at least one ticker or candidate identity")
    if len(ordered) > 50:
        raise ValueError("Standalone lookup accepts at most 50 symbols per batch")
    return tuple(ordered.values())


def research_contracts(settings: LookupSettings) -> tuple[NewsRequest, RetrievalPolicy]:
    settings = settings.validated()
    window_seconds = float(settings.lookback_hours) * 3600.0
    metadata = {"require_compatible_acquisition": True, "research_profile": RESEARCH_PROFILE}
    if settings.provider == "massive":
        metadata.update(massive_page_size=settings.massive_page_size,
                        massive_max_pages_per_symbol=settings.massive_max_pages_per_symbol,
                        massive_max_requests=settings.massive_max_requests, massive_requests_per_minute=5)
    return (
        NewsRequest(strategy_id=RESEARCH_PROFILE, lookback_seconds=window_seconds,
                    freshness_seconds=window_seconds, include_generic_news=True,
                    max_evidence_per_symbol=settings.max_items, audit_reason="standalone_news_research",
                    metadata={"research_only": True}, query_start_utc=settings.published_after,
                    query_end_utc=settings.published_before),
        RetrievalPolicy(source_groups=settings.source_groups,
                        provider_groups=(MASSIVE_PROVIDER_ID,) if settings.provider == "massive" else ("rss_batch",),
                        allow_cache_read=settings.cache_mode != "off",
                        allow_cache_write=settings.cache_mode not in {"only", "off"},
                        network_allowed=settings.cache_mode != "only",
                        refresh_mode={"use": "incremental", "refresh": "force_refresh",
                                      "only": "cache_only", "off": "force_refresh"}[settings.cache_mode],
                        total_budget_seconds=float(settings.budget_seconds),
                        request_timeout_seconds=float(settings.request_timeout_seconds),
                        timeout_policy="clamp_to_remaining_budget", extended_reserve_fraction=0.35,
                        fallback_mode="unresolved_only" if "PREP_EXTENDED" in settings.source_groups else "none",
                        refresh_interval_seconds=float(settings.refresh_interval_seconds),
                        metadata=metadata),
    )


def _prep_loader(path: Path | None) -> Callable[[], Mapping[str, Any]]:
    if path is None:
        return lambda: {}
    from src.prep.premarket_prep_artifact import load_canonical_premarket_prep_artifact
    return lambda: load_canonical_premarket_prep_artifact(path)


def _selected_sources(settings: LookupSettings) -> list[dict[str, Any]]:
    if settings.provider == "massive":
        return [{"source_id": MASSIVE_PROVIDER_ID, "source_group": MASSIVE_SOURCE_GROUP,
                 "source_url": "https://api.massive.com/v2/reference/news"}]
    seen: set[str] = set()
    rows = []
    for group in settings.source_groups:
        for url in get_source_group_urls(group):
            if url in seen:
                continue
            seen.add(url)
            rows.append({"source_id": url, "source_group": group})
    return rows


def _coverage_rows(selected, raw_rows, *, origin, details=None):
    by_id = {str(row.get("source_id") or row.get("source_url")): dict(row) for row in raw_rows}
    rows = []
    for chosen in selected:
        row = by_id.get(chosen["source_id"])
        if row is None:
            row = {**chosen, "retrieval_status": "not_requested", "attempted": False,
                   "failure_reason": "not_observed_in_acquisition", "elapsed_seconds": None,
                   "request_elapsed_seconds": None, "parse_elapsed_seconds": None,
                   "http_status": None, "timed_out": False, "budget_exhausted": False}
            if details and details.get("provider_status") == "provider_request_failure":
                row["failure_reason"] = "fallback_not_attempted_after_provider_failure"
        row["origin"] = origin
        rows.append(row)
    return rows


def _article(item, *, now: datetime, lookback_seconds: float, query_start_utc=None, query_end_utc=None):
    published = item.published_at
    if published is None or published.tzinfo is None:
        return None, "missing_or_naive_publication_time"
    age = (now - published.astimezone(timezone.utc)).total_seconds()
    if age < 0:
        return None, "future_publication_time"
    if query_start_utc is not None:
        if not query_start_utc <= published.astimezone(timezone.utc) <= query_end_utc:
            return None, "outside_requested_publication_window"
    elif age > lookback_seconds:
        return None, "outside_requested_lookback"
    row = jsonable(item)
    row.update(publisher=item.original_source or item.observed_source,
               age_seconds=age, match_basis={"type": item.match_type, "field": item.matched_field,
                                            "company_name": item.company_name, "aliases": list(item.aliases)})
    return row, None


def lookup_news(
    candidates: Sequence[str | NewsCandidate], settings: LookupSettings, *, service=None, lifecycle=None,
    on_retrieval: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Make one canonical batch call and report research evidence and cleanup truth."""
    started = time.monotonic()
    settings = settings.validated()
    candidates = normalize_candidates(candidates)
    request, policy = research_contracts(settings)
    if service is None:
        from src.news import news_fetcher
        if settings.provider == "rss" and policy.network_allowed and (news_fetcher.requests is None or news_fetcher.feedparser is None):
            raise RuntimeError("Standalone network lookup requires requests and feedparser for bounded HTTP")
        from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
        from src.news.evidence_store import CanonicalNewsEvidenceStore
        from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
        from src.news.rss_lifecycle import RssFetchLifecycle
        lifecycle = lifecycle if lifecycle is not None else RssFetchLifecycle()
        if settings.provider == "massive":
            from src.news.massive_news_adapter import MassiveNewsIntelligenceProvider
            provider = MassiveNewsIntelligenceProvider(lifecycle=lifecycle)
        else:
            provider = BatchRssNewsIntelligenceProvider(lifecycle=lifecycle)
        service = CanonicalNewsIntelligenceService(
            evidence_store=CanonicalNewsEvidenceStore(settings.cache_file, prep_artifact_loader=_prep_loader(settings.prep_file)),
            retrieval_provider=provider,
        )
    service_started = time.monotonic()
    result = service.get_news(candidates, request, policy)
    service_elapsed = time.monotonic() - service_started
    now = datetime.now(timezone.utc)
    diag = jsonable(result.diagnostics)
    details = diag.get("diagnostics", {})
    selected = _selected_sources(settings)
    acquisition_by_symbol = details.get("last_retrieval_by_symbol", {})
    coverage_unknown = set(details.get("acquisition_coverage_unknown_symbols", ()))
    refreshed = set(details.get("refresh_symbols", ())) if details.get("refresh_allowed") else set()
    output = {}
    for candidate in candidates:
        symbol = candidate.normalized_symbol
        summary = result.summary_for_symbol(symbol)
        summary_data = jsonable(summary) if summary else {}
        acquisition = (summary_data.get("diagnostics", {}).get("last_retrieval")
                       or acquisition_by_symbol.get(symbol) or {})
        coverage = acquisition.get("coverage", {})
        live = symbol in refreshed
        rows = diag.get("source_diagnostics", ()) if live else coverage.get("source_diagnostics", ())
        origin = "current_retrieval" if live else "cached_acquisition"
        provider_details = summary_data.get("diagnostics", {}).get("provider_details") or acquisition.get("provider_details") or {}
        if settings.provider == "massive":
            rows = provider_details.get("source_diagnostics") or [
                row for row in rows if str(row.get("source_id", "")).startswith(f"massive:{symbol}:")
            ]
            selected_pages = [{"source_id": row.get("source_id"), "source_group": MASSIVE_SOURCE_GROUP} for row in rows]
            if not selected_pages:
                selected_pages = [{"source_id": f"massive:{symbol}:page:1", "source_group": MASSIVE_SOURCE_GROUP}]
            source_rows = _coverage_rows(selected_pages, rows, origin=origin, details=coverage or diag)
        else:
            source_rows = _coverage_rows(selected, rows, origin=origin, details=coverage or diag)
        current_ids = set(details.get("retrieved_evidence_ids_by_symbol", {}).get(symbol, ()))
        articles = []
        rejected: dict[str, int] = {}
        for item in result.evidence_for_symbol(symbol):
            article, reason = _article(item, now=now, lookback_seconds=request.lookback_seconds,
                                       query_start_utc=request.query_start_utc, query_end_utc=request.query_end_utc)
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
            else:
                article["acquisition_origin"] = (
                    "current_retrieval" if item.evidence_id and item.evidence_id in current_ids
                    else "cache_or_prep" if not live or item.cache_state in {"hit", "stale"}
                    else "unknown"
                )
                articles.append(article)
        status = summary_data.get("retrieval_status", "unknown")
        if symbol in coverage_unknown or (not live and not acquisition.get("acquisition_profile")):
            coverage_status = "unknown"
        elif summary_data.get("provider_available") is False or status in {"unavailable", "provider_error", "timeout"}:
            coverage_status = "unavailable"
        elif status in {"partial", "budget_exhausted", "unknown", "not_requested"} or any(
            row.get("retrieval_status") not in {"available", "cache_hit"} for row in source_rows
        ):
            coverage_status = "partial"
        else:
            coverage_status = "complete"
        outcome = ("matched" if articles else "completed_no_match" if coverage_status == "complete"
                   else "coverage_unknown" if coverage_status == "unknown" else "retrieval_" + coverage_status)
        output[symbol] = {
            "articles": articles, "outcome": outcome, "coverage_status": coverage_status,
            "retrieval_status": status, "provider_status": summary_data.get("provider_status"),
            "provider_available": summary_data.get("provider_available"),
            "budget_exhausted": bool(summary_data.get("budget_exhausted", False)),
            "cache_state": summary_data.get("cache_state", result.cache_state),
            "provenance": "provider_refresh" if live else origin if acquisition else "cache_or_prep_evidence_only",
            "current_retrieval_article_count": sum(item["acquisition_origin"] == "current_retrieval" for item in articles),
            "reused_article_count": sum(item["acquisition_origin"] == "cache_or_prep" for item in articles),
            "acquisition_completed_at": acquisition.get("completed_at"),
            "acquisition_profile": acquisition.get("acquisition_profile"),
            "cache_profile_compatible": details.get("acquisition_profile_compatible_by_symbol", {}).get(symbol),
            "sources": source_rows, "excluded_evidence": rejected,
            "research_only": True,
            **({"provider_details": provider_details} if settings.provider == "massive" else {}),
        }
    payload = {
        "schema_version": "news.standalone_lookup.v1", "ok": True,
        "profile": RESEARCH_PROFILE, "provider": settings.provider,
        "candidates": jsonable(candidates), "settings": jsonable(settings),
        "request": jsonable(request), "retrieval_policy": jsonable(policy),
        "started_at": result.started_at.isoformat() if result.started_at else None,
        "completed_at": now.isoformat(), "symbols": output, "selected_sources": selected,
        "selected_source_groups": list(settings.source_groups),
        "queried_source_groups": list(result.diagnostics.source_groups_queried),
        "diagnostics": diag,
        "timing": {"service_elapsed_seconds": service_elapsed, "retrieval_elapsed_seconds": time.monotonic() - started},
        "cleanup": lifecycle.snapshot() if lifecycle is not None else {"cleanup_complete": None, "reason": "injected_service_without_lifecycle"},
        "research_results_are_trading_catalysts": False,
    }
    if on_retrieval is not None:
        on_retrieval(payload)
    if lifecycle is not None:
        payload["cleanup"] = lifecycle.wait_for_cleanup(float(settings.cleanup_seconds))
    payload["timing"]["total_elapsed_seconds"] = time.monotonic() - started
    return payload


def human_report(result: Mapping[str, Any]) -> str:
    if not result.get("ok"):
        return "News lookup failed: " + str(result.get("error", "unknown error"))
    settings = result["settings"]
    lines = [f"Standalone news research | provider={settings.get('provider', 'rss')} | lookback={settings['lookback_hours']:g}h | groups={','.join(result['selected_source_groups'])}",
             f"Cache={settings['cache_mode']} | budget={settings['budget_seconds']:g}s | request timeout={settings['request_timeout_seconds']:g}s"]
    if settings.get("published_after") is not None:
        lines.append(f"Publication window (inclusive UTC): {settings['published_after']} to {settings['published_before']}")
    for symbol, item in result["symbols"].items():
        lines.append(f"{symbol}: {item['outcome']} | coverage={item['coverage_status']} | {item['provenance']} | {len(item['articles'])} article(s)")
        if item.get("provider_details"):
            facts = item["provider_details"]
            lines.append("  Provider details: " + json.dumps(jsonable({key: value for key, value in facts.items()
                         if key != "source_diagnostics"}), sort_keys=True))
        for article in item["articles"]:
            lines.extend([f"  {article['headline']}", f"  {article['publisher']} | {article['published_at']} | age={article['age_seconds']/3600:.2f}h | match={article['match_type']}/{article['matched_field']} | origin={article['acquisition_origin']}", f"  {article['url']}"])
    lines.append("Source outcomes (current retrieval; cached details are retained per symbol):")
    for source in result["diagnostics"].get("source_diagnostics", []):
        lines.append(f"  {source['source_id']}: {source['retrieval_status']} | request={source.get('request_elapsed_seconds')}s parse={source.get('parse_elapsed_seconds')}s | timeout={source.get('timed_out')} budget={source.get('budget_exhausted')}")
    lines.append(f"Elapsed={result['timing'].get('total_elapsed_seconds', 0):.3f}s | cleanup_complete={result['cleanup'].get('cleanup_complete')}")
    lines.append("Research evidence only; strategy freshness and catalyst qualification remain separate.")
    return "\n".join(lines)
