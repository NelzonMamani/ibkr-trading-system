from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from src.config.config_resolver import get_config
from src.news.news_fetcher import Headline
from src.news.news_heat import compute_news_heat_score
from src.news.news_intelligence_contract import (
    CacheState,
    NewsCandidate,
    NewsEvidence,
    NewsEvidenceSummary,
    NewsRequest,
    RetrievalStatus,
)
from src.news.news_normalizer import normalize_headlines
from src.prep.premarket_prep_artifact import load_canonical_premarket_prep_artifact


NEWS_INTELLIGENCE_CACHE_NAMESPACE = "news_intelligence"
NEWS_INTELLIGENCE_SCHEMA_VERSION = "PR1069.news_intelligence_evidence_store.v1"
DATETIME_FIELDS = {"published_at", "fetched_at", "first_seen_at"}
TUPLE_FIELDS = {"aliases", "failures"}
MAPPING_FIELDS = {"raw", "audit"}


@dataclass(frozen=True)
class EvidenceStoreReadResult:
    evidence_by_symbol: dict[str, tuple[NewsEvidence, ...]]
    summaries_by_symbol: dict[str, NewsEvidenceSummary]
    diagnostics: dict[str, Any]


def normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def evidence_freshness_seconds(request: NewsRequest | None = None) -> float:
    if request is not None and request.freshness_seconds is not None:
        try:
            return max(0.0, float(request.freshness_seconds))
        except Exception:
            return 0.0
    try:
        return max(0.0, float(get_config("NEWS_MAX_AGE_HOURS") or 6.0) * 3600.0)
    except Exception:
        return 6.0 * 3600.0


def evidence_max_entries(request: NewsRequest | None = None) -> int:
    if request is not None and request.max_evidence_per_symbol is not None:
        try:
            return max(1, int(request.max_evidence_per_symbol))
        except Exception:
            return 5
    try:
        return max(1, int(get_config("NEWS_MAX_ENTRIES_PER_SYMBOL") or 5))
    except Exception:
        return 5


def evidence_cache_path() -> Path:
    return Path(str(get_config("NEWS_CACHE_FILE")))


class CanonicalNewsEvidenceStore:
    """Canonical objective evidence view over existing prep/news cache files."""

    def __init__(
        self,
        cache_path: Path | None = None,
        *,
        prep_artifact_loader=load_canonical_premarket_prep_artifact,
    ) -> None:
        self.cache_path = cache_path or evidence_cache_path()
        self._prep_artifact_loader = prep_artifact_loader

    def read(
        self,
        candidates: Sequence[NewsCandidate],
        request: NewsRequest | None = None,
        *,
        include_prep: bool = True,
    ) -> EvidenceStoreReadResult:
        symbols = _candidate_symbols(candidates)
        now = datetime.now(timezone.utc)
        evidence_by_symbol = {symbol: tuple() for symbol in symbols}
        diagnostics: dict[str, Any] = {
            "schema_version": NEWS_INTELLIGENCE_SCHEMA_VERSION,
            "cache_namespace": NEWS_INTELLIGENCE_CACHE_NAMESPACE,
            "cache_file": str(self.cache_path),
            "cache_read_failed": False,
            "cache_read_error": None,
            "cache_hits_by_symbol": {},
            "cache_hit_symbols": [],
            "cache_miss_symbols": [],
            "stale_cache_miss_symbols": [],
            "prep_reuse_symbols": [],
            "prep_stale_symbols": [],
            "legacy_news_cache_symbols": [],
            "fresh_evidence_reused_symbols": [],
        }

        payload = self._load_cache_payload(diagnostics)
        cache_rows = _canonical_cache_rows(payload)
        legacy_rows = _legacy_news_cache_rows(payload)
        prep_rows = self._load_prep_rows(diagnostics) if include_prep else {}

        for candidate in candidates:
            symbol = candidate.normalized_symbol
            if not symbol:
                continue
            evidence: list[NewsEvidence] = []
            for row in list(cache_rows.get(symbol, ())) + list(legacy_rows.get(symbol, ())):
                parsed = evidence_from_mapping(row, request=request, now=now)
                if parsed is not None:
                    evidence.append(parsed)
            if symbol in legacy_rows:
                diagnostics["legacy_news_cache_symbols"].append(symbol)
            if symbol in prep_rows:
                prep_evidence = evidence_from_prep_entry(
                    prep_rows[symbol],
                    candidate=candidate,
                    request=request,
                    now=now,
                )
                evidence.extend(prep_evidence)
                if prep_evidence:
                    diagnostics["prep_reuse_symbols"].append(symbol)

            deduped = dedupe_evidence(evidence, max_items=evidence_max_entries(request))
            evidence_by_symbol[symbol] = tuple(deduped)
            fresh_count = sum(1 for item in deduped if item.stale is False)
            stale_count = sum(1 for item in deduped if item.stale is True)
            if fresh_count:
                diagnostics["cache_hits_by_symbol"][symbol] = fresh_count
                diagnostics["cache_hit_symbols"].append(symbol)
                diagnostics["fresh_evidence_reused_symbols"].append(symbol)
            elif stale_count:
                diagnostics["stale_cache_miss_symbols"].append(symbol)
                if symbol in prep_rows:
                    diagnostics["prep_stale_symbols"].append(symbol)
            else:
                diagnostics["cache_miss_symbols"].append(symbol)

        for key in (
            "cache_hit_symbols",
            "cache_miss_symbols",
            "stale_cache_miss_symbols",
            "prep_reuse_symbols",
            "prep_stale_symbols",
            "legacy_news_cache_symbols",
            "fresh_evidence_reused_symbols",
        ):
            diagnostics[key] = sorted(set(diagnostics[key]))

        summaries = {
            symbol: summarize_news_evidence(
                symbol,
                evidence,
                request=request,
                retrieval_status=("cache_hit" if any(item.stale is False for item in evidence) else "not_requested"),
                provider_status="cache",
                provider_available=True,
                cache_state=_cache_state_for_evidence(evidence),
                diagnostics={"cache_read": dict(diagnostics)},
            )
            for symbol, evidence in evidence_by_symbol.items()
        }
        return EvidenceStoreReadResult(evidence_by_symbol=evidence_by_symbol, summaries_by_symbol=summaries, diagnostics=diagnostics)

    def write(
        self,
        evidence_by_symbol: Mapping[str, Sequence[NewsEvidence]],
        request: NewsRequest | None = None,
    ) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {
            "schema_version": NEWS_INTELLIGENCE_SCHEMA_VERSION,
            "cache_namespace": NEWS_INTELLIGENCE_CACHE_NAMESPACE,
            "cache_file": str(self.cache_path),
            "cache_write_failed": False,
            "cache_write_error": None,
            "cache_write_symbols": [],
            "cache_write_evidence_count": 0,
        }
        payload = self._load_cache_payload(diagnostics)
        namespace = payload.setdefault(NEWS_INTELLIGENCE_CACHE_NAMESPACE, {})
        if not isinstance(namespace, dict):
            namespace = {}
            payload[NEWS_INTELLIGENCE_CACHE_NAMESPACE] = namespace
        namespace["schema_version"] = NEWS_INTELLIGENCE_SCHEMA_VERSION
        namespace["updated_at"] = datetime.now(timezone.utc).isoformat()
        symbols_payload = namespace.setdefault("symbols", {})
        if not isinstance(symbols_payload, dict):
            symbols_payload = {}
            namespace["symbols"] = symbols_payload

        now = datetime.now(timezone.utc)
        max_items = evidence_max_entries(request)
        for raw_symbol, evidence in evidence_by_symbol.items():
            symbol = normalize_symbol(raw_symbol)
            if not symbol:
                continue
            existing_rows = list((symbols_payload.get(symbol) or {}).get("evidence") or [])
            existing = [
                item
                for row in existing_rows
                if (item := evidence_from_mapping(row, request=request, now=now)) is not None
            ]
            incoming = [
                replace(item, cache_state="hit" if item.cache_state == "not_checked" else item.cache_state)
                for item in evidence
                if isinstance(item, NewsEvidence)
            ]
            merged = dedupe_evidence(existing + incoming, max_items=max_items)
            symbols_payload[symbol] = {
                "updated_at": now.isoformat(),
                "evidence": [serialize_evidence(item) for item in merged],
            }
            diagnostics["cache_write_symbols"].append(symbol)
            diagnostics["cache_write_evidence_count"] += len(incoming)

        diagnostics["cache_write_symbols"] = sorted(set(diagnostics["cache_write_symbols"]))
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:
            diagnostics["cache_write_failed"] = True
            diagnostics["cache_write_error"] = type(exc).__name__
        return diagnostics

    def _load_cache_payload(self, diagnostics: dict[str, Any]) -> dict[str, Any]:
        if not self.cache_path.exists():
            return {"symbols": {}, NEWS_INTELLIGENCE_CACHE_NAMESPACE: {"schema_version": NEWS_INTELLIGENCE_SCHEMA_VERSION, "symbols": {}}}
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception as exc:
            diagnostics_key = "cache_read_failed" if "cache_read_failed" in diagnostics else "cache_write_failed"
            error_key = "cache_read_error" if "cache_read_error" in diagnostics else "cache_write_error"
            diagnostics[diagnostics_key] = True
            diagnostics[error_key] = type(exc).__name__
            return {"symbols": {}, NEWS_INTELLIGENCE_CACHE_NAMESPACE: {"schema_version": NEWS_INTELLIGENCE_SCHEMA_VERSION, "symbols": {}}}
        return payload if isinstance(payload, dict) else {}

    def _load_prep_rows(self, diagnostics: dict[str, Any]) -> dict[str, dict[str, Any]]:
        try:
            payload = self._prep_artifact_loader() or {}
        except Exception as exc:
            diagnostics["prep_read_failed"] = True
            diagnostics["prep_read_error"] = type(exc).__name__
            return {}
        symbols = payload.get("symbols") if isinstance(payload, dict) else []
        rows: dict[str, dict[str, Any]] = {}
        for entry in symbols or []:
            if not isinstance(entry, dict):
                continue
            symbol = normalize_symbol(entry.get("symbol"))
            if symbol:
                rows[symbol] = entry
        return rows


def summarize_news_evidence(
    symbol: str,
    evidence: Sequence[NewsEvidence],
    *,
    request: NewsRequest | None = None,
    retrieval_status: RetrievalStatus = "unknown",
    provider_status: str | None = None,
    provider_available: bool | None = None,
    cache_state: CacheState = "not_checked",
    budget_exhausted: bool = False,
    diagnostics: Mapping[str, Any] | None = None,
) -> NewsEvidenceSummary:
    normalized = normalize_symbol(symbol)
    items = list(dedupe_evidence(evidence, max_items=evidence_max_entries(request)))
    fresh_items = [item for item in items if item.stale is False]
    generic_count = sum(1 for item in items if item.is_generic is True)
    qualifying_count = sum(1 for item in items if item.is_qualifying_event_class is True)
    freshest_age = min((float(item.age_seconds) for item in items if item.age_seconds is not None), default=None)
    reliability_values = [
        float(value)
        for item in items
        for value in (item.source_reliability_score, item.source_credibility_score)
        if value is not None
    ]
    source_count = len({item.observed_source or item.original_source or item.source_domain for item in items if item.observed_source or item.original_source or item.source_domain})
    event_counts: dict[str, int] = {}
    for item in items:
        event = str(item.event_class or item.catalyst_classification or "").strip()
        if event:
            event_counts[event] = event_counts.get(event, 0) + 1
    return NewsEvidenceSummary(
        symbol=normalized,
        evidence_count=len(items),
        fresh_evidence_count=len(fresh_items),
        qualifying_event_class_count=qualifying_count,
        generic_evidence_count=generic_count,
        freshest_evidence_age_seconds=freshest_age,
        highest_reliability_score=max(reliability_values) if reliability_values else None,
        average_reliability_score=(sum(reliability_values) / len(reliability_values)) if reliability_values else None,
        heat_score=max((item.heat_score for item in items if item.heat_score is not None), default=None),
        velocity_5m=max((item.velocity_5m for item in items if item.velocity_5m is not None), default=None),
        velocity_10m=max((item.velocity_10m for item in items if item.velocity_10m is not None), default=None),
        velocity_30m=max((item.velocity_30m for item in items if item.velocity_30m is not None), default=None),
        velocity_60m=max((item.velocity_60m for item in items if item.velocity_60m is not None), default=None),
        independent_source_count=source_count,
        event_class_counts=event_counts,
        retrieval_status=retrieval_status,
        provider_status=provider_status,
        provider_available=provider_available,
        cache_state=cache_state,
        budget_exhausted=budget_exhausted,
        evidence_ids=tuple(item.evidence_id for item in items if item.evidence_id),
        diagnostics=dict(diagnostics or {}),
    )


def serialize_evidence(evidence: NewsEvidence) -> dict[str, Any]:
    payload = asdict(evidence)
    for field_name in DATETIME_FIELDS:
        value = payload.get(field_name)
        if isinstance(value, datetime):
            payload[field_name] = value.astimezone(timezone.utc).isoformat()
    return payload


def evidence_from_mapping(
    row: Mapping[str, Any],
    *,
    request: NewsRequest | None = None,
    now: datetime | None = None,
) -> NewsEvidence | None:
    if not isinstance(row, Mapping):
        return None
    now = now or datetime.now(timezone.utc)
    allowed = {field.name for field in fields(NewsEvidence)}
    payload: dict[str, Any] = {key: row.get(key) for key in allowed if key in row}
    symbol = normalize_symbol(payload.get("symbol"))
    if not symbol:
        return None
    payload["symbol"] = symbol
    for field_name in DATETIME_FIELDS:
        payload[field_name] = _parse_datetime(payload.get(field_name))
    for field_name in TUPLE_FIELDS:
        value = payload.get(field_name)
        if value is None:
            payload[field_name] = ()
        elif isinstance(value, tuple):
            payload[field_name] = value
        elif isinstance(value, (list, set)):
            payload[field_name] = tuple(value)
        else:
            payload[field_name] = (str(value),)
    for field_name in MAPPING_FIELDS:
        value = payload.get(field_name)
        payload[field_name] = dict(value) if isinstance(value, Mapping) else {}
    evidence = NewsEvidence(**payload)
    return refresh_evidence_age(evidence, request=request, now=now, cache_state=evidence.cache_state)


def evidence_from_prep_entry(
    entry: Mapping[str, Any],
    *,
    candidate: NewsCandidate,
    request: NewsRequest | None,
    now: datetime | None = None,
) -> tuple[NewsEvidence, ...]:
    now = now or datetime.now(timezone.utc)
    news_items = [item for item in list(entry.get("news_context") or []) if isinstance(item, Mapping)]
    news_asof = _parse_datetime(entry.get("news_asof"))
    evidence: list[NewsEvidence] = []
    for index, item in enumerate(news_items):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        published = _parse_datetime(item.get("published_at"))
        age_hours = _safe_float(item.get("age_hours"), None)
        if published is None and age_hours is not None:
            published = datetime.fromtimestamp(now.timestamp() - max(0.0, age_hours) * 3600.0, tz=timezone.utc)
        published = published or news_asof or now
        tag = str(item.get("catalyst_tag") or "").strip().lower()
        event_class = None if not tag else tag
        is_generic = tag in {"", "generic", "none"}
        source = str(item.get("source") or "prep_cache")
        url = str(item.get("url") or "")
        evidence_id = _stable_evidence_id("prep", candidate.normalized_symbol, title, source, url, str(index))
        raw = {
            "prep_news_asof": entry.get("news_asof"),
            "prep_context_status": entry.get("context_status"),
            "catalyst_tag": item.get("catalyst_tag"),
            "source_mode": "prep_cache",
        }
        evidence.append(
            refresh_evidence_age(
                NewsEvidence(
                    symbol=candidate.normalized_symbol,
                    evidence_id=evidence_id,
                    company_name=candidate.company_name or entry.get("company_name"),
                    aliases=tuple(candidate.aliases or ()),
                    match_type=str(item.get("match_type") or "prep_context"),
                    matched_field=str(item.get("matched_field") or "news_context"),
                    headline=title,
                    summary=str(item.get("summary") or ""),
                    url=url,
                    reference_id=url or evidence_id,
                    event_class=event_class,
                    is_generic=is_generic,
                    is_qualifying_event_class=False,
                    dilution_or_offering=tag == "offering",
                    published_at=published,
                    fetched_at=news_asof or now,
                    first_seen_at=published,
                    original_source=source,
                    observed_source=source,
                    source_domain=_domain(url),
                    provider="prep_cache",
                    source_group="PREP_EXTENDED",
                    source_tier="prep_cache",
                    verified_source=True,
                    cache_state="hit",
                    retrieval_status="cache_hit",
                    raw=raw,
                    audit={"evidence_origin": "canonical_premarket_prep_artifact"},
                ),
                request=request,
                now=now,
                cache_state="hit",
            )
        )
    enriched = enrich_evidence_metrics(evidence, now_ts=now.timestamp()) if evidence else ()
    return tuple(dedupe_evidence(enriched, max_items=evidence_max_entries(request)))


def refresh_evidence_age(
    evidence: NewsEvidence,
    *,
    request: NewsRequest | None = None,
    now: datetime | None = None,
    cache_state: CacheState | None = None,
) -> NewsEvidence:
    now = now or datetime.now(timezone.utc)
    basis = evidence.published_at or evidence.fetched_at or evidence.first_seen_at
    age_seconds = evidence.age_seconds
    if basis is not None:
        age_seconds = max(0.0, (now - basis.astimezone(timezone.utc)).total_seconds())
    freshness_seconds = evidence_freshness_seconds(request)
    stale = None
    if age_seconds is not None:
        stale = age_seconds > freshness_seconds
    return replace(
        evidence,
        age_seconds=age_seconds,
        stale=stale,
        freshness_bucket=_freshness_bucket(age_seconds),
        cache_state=cache_state or evidence.cache_state,
    )


def enrich_evidence_metrics(
    evidence: Sequence[NewsEvidence],
    *,
    now_ts: float,
) -> tuple[NewsEvidence, ...]:
    headlines = [
        Headline(
            title=str(item.headline or ""),
            source=str(item.observed_source or item.original_source or item.source_domain or ""),
            published_ts=(item.published_at.timestamp() if item.published_at is not None else now_ts),
            url=str(item.url or ""),
            summary=str(item.summary or ""),
            source_tier=str(item.source_tier or ""),
            match_type=str(item.match_type or ""),
            matched_field=str(item.matched_field or ""),
        )
        for item in evidence
        if item.headline
    ]
    metrics = normalize_headlines(headlines, now_ts=now_ts)
    heat_score = compute_news_heat_score(metrics)
    velocity_5m = _safe_int(metrics.get("news_velocity_5m"), None)
    velocity_10m = _safe_int(metrics.get("news_velocity_10m"), None)
    velocity_60m = _safe_int(metrics.get("news_velocity_60m"), None)
    velocity_30m = _velocity(headlines, 30, now_ts)
    credibility = _safe_float(metrics.get("news_top_source_credibility_score"), None)
    source_count = _safe_int(metrics.get("news_sources_count"), None)
    return tuple(
        replace(
            item,
            velocity_5m=item.velocity_5m if item.velocity_5m is not None else velocity_5m,
            velocity_10m=item.velocity_10m if item.velocity_10m is not None else velocity_10m,
            velocity_30m=item.velocity_30m if item.velocity_30m is not None else velocity_30m,
            velocity_60m=item.velocity_60m if item.velocity_60m is not None else velocity_60m,
            heat_score=item.heat_score if item.heat_score is not None else heat_score,
            hotness_score=item.hotness_score if item.hotness_score is not None else heat_score,
            source_credibility_score=item.source_credibility_score if item.source_credibility_score is not None else credibility,
            source_reliability_score=item.source_reliability_score if item.source_reliability_score is not None else credibility,
            independent_source_count=item.independent_source_count if item.independent_source_count is not None else source_count,
            publication_count=item.publication_count if item.publication_count is not None else len(evidence),
        )
        for item in evidence
    )


def dedupe_evidence(evidence: Sequence[NewsEvidence], *, max_items: int) -> list[NewsEvidence]:
    seen: set[str] = set()
    ordered = sorted(
        evidence,
        key=lambda item: (
            item.stale is True,
            -(item.published_at.timestamp() if item.published_at else 0.0),
            str(item.evidence_id or ""),
        ),
    )
    result: list[NewsEvidence] = []
    for item in ordered:
        key = item.evidence_id or _stable_evidence_id(
            "evidence",
            item.normalized_symbol,
            item.headline or "",
            item.observed_source or item.original_source or "",
            item.url or "",
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= max(1, int(max_items or 1)):
            break
    return result


def _canonical_cache_rows(payload: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    namespace = payload.get(NEWS_INTELLIGENCE_CACHE_NAMESPACE) if isinstance(payload, Mapping) else None
    symbols = namespace.get("symbols") if isinstance(namespace, Mapping) else {}
    rows: dict[str, list[Mapping[str, Any]]] = {}
    if not isinstance(symbols, Mapping):
        return rows
    for raw_symbol, bucket in symbols.items():
        symbol = normalize_symbol(raw_symbol)
        if not symbol or not isinstance(bucket, Mapping):
            continue
        rows[symbol] = [row for row in list(bucket.get("evidence") or []) if isinstance(row, Mapping)]
    return rows


def _legacy_news_cache_rows(payload: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    symbols = payload.get("symbols") if isinstance(payload, Mapping) else {}
    rows: dict[str, list[Mapping[str, Any]]] = {}
    if not isinstance(symbols, Mapping):
        return rows
    now = datetime.now(timezone.utc)
    for raw_symbol, result in symbols.items():
        symbol = normalize_symbol(raw_symbol)
        if not symbol or not isinstance(result, Mapping):
            continue
        items = []
        fetched_at = result.get("fetched_at")
        for index, item in enumerate(list(result.get("news_context") or [])):
            if not isinstance(item, Mapping):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            published = _parse_datetime(item.get("published_at"))
            if published is None:
                age_hours = _safe_float(item.get("age_hours"), None)
                if age_hours is not None:
                    published = datetime.fromtimestamp(now.timestamp() - max(0.0, age_hours) * 3600.0, tz=timezone.utc)
            tag = str(item.get("catalyst_tag") or "").strip().lower()
            url = str(item.get("url") or "")
            source = str(item.get("source") or result.get("source_mode") or "legacy_news_cache")
            items.append(
                {
                    "symbol": symbol,
                    "evidence_id": _stable_evidence_id("legacy-news-cache", symbol, title, source, url, str(index)),
                    "headline": title,
                    "summary": str(item.get("summary") or ""),
                    "url": url,
                    "event_class": tag or None,
                    "is_generic": tag in {"", "generic", "none"},
                    "is_qualifying_event_class": False,
                    "dilution_or_offering": tag == "offering",
                    "published_at": (published or now).isoformat(),
                    "fetched_at": fetched_at,
                    "first_seen_at": (published or now).isoformat(),
                    "original_source": source,
                    "observed_source": source,
                    "source_domain": _domain(url),
                    "provider": "legacy_news_provider_cache",
                    "source_group": "FAST_TRADING",
                    "source_tier": "legacy_cache",
                    "verified_source": True,
                    "cache_state": "hit",
                    "retrieval_status": "cache_hit",
                    "raw": {"source_mode": result.get("source_mode"), "catalyst_tag": item.get("catalyst_tag")},
                    "audit": {"evidence_origin": "NEWS_CACHE_FILE.symbols"},
                }
            )
        if items:
            rows[symbol] = items
    return rows


def _candidate_symbols(candidates: Sequence[NewsCandidate]) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        symbol = candidate.normalized_symbol
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def _cache_state_for_evidence(evidence: Sequence[NewsEvidence]) -> CacheState:
    if not evidence:
        return "miss"
    if any(item.stale is False for item in evidence):
        return "hit"
    if any(item.stale is True for item in evidence):
        return "stale"
    return "hit"


def _stable_evidence_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha1(
        "|".join(str(part or "").strip().lower() for part in parts).encode("utf-8")
    ).hexdigest()[:16]
    symbol = normalize_symbol(parts[0] if parts else "")
    return f"{prefix}:{symbol}:{digest}" if symbol else f"{prefix}:{digest}"


def _parse_datetime(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _domain(url: str) -> str | None:
    try:
        parsed = urlparse(str(url or ""))
    except Exception:
        return None
    return parsed.netloc or None


def _freshness_bucket(age_seconds: float | None) -> str | None:
    if age_seconds is None:
        return None
    if age_seconds <= 5 * 60:
        return "0_5m"
    if age_seconds <= 30 * 60:
        return "5_30m"
    if age_seconds <= 6 * 60 * 60:
        return "30m_6h"
    return "older_than_6h"


def _velocity(headlines: Sequence[Headline], window_minutes: int, now_ts: float) -> int:
    threshold = now_ts - window_minutes * 60.0
    return sum(1 for headline in headlines if headline.published_ts >= threshold)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


__all__ = [
    "CanonicalNewsEvidenceStore",
    "EvidenceStoreReadResult",
    "NEWS_INTELLIGENCE_CACHE_NAMESPACE",
    "NEWS_INTELLIGENCE_SCHEMA_VERSION",
    "dedupe_evidence",
    "enrich_evidence_metrics",
    "evidence_cache_path",
    "evidence_freshness_seconds",
    "evidence_from_mapping",
    "evidence_from_prep_entry",
    "evidence_max_entries",
    "normalize_symbol",
    "refresh_evidence_age",
    "serialize_evidence",
    "summarize_news_evidence",
]
