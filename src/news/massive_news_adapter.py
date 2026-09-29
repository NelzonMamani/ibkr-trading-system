"""Optional bounded Massive ticker-news acquisition for standalone research.

Bearer credentials never enter query URLs, diagnostics or acquisition profiles.
The shared local ledger accounts for this application's processes and keys, not
unrelated applications or machines using the account. No automatic retries.
"""
from __future__ import annotations

from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import math
import os
import re
import threading
import time
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, urlsplit

from src.news.evidence_store import dedupe_evidence, evidence_max_entries, summarize_news_evidence
from src.news.massive_rate_limit import MassiveRateLimiter
from src.news.news_fetcher import requests, symbol_relevance_match
from src.news.news_intelligence_contract import (
    NewsBatchResult, NewsCandidate, NewsEvidence, NewsRequest, RetrievalDiagnostics,
    RetrievalPolicy, SourceDiagnostic,
)
from src.news.rss_lifecycle import RssFetchLifecycle


ENDPOINT = "https://api.massive.com/v2/reference/news"
PROVIDER_ID = "massive_ticker_news"
SOURCE_GROUP = "MASSIVE_TICKER_NEWS"
_AUTH_PARAMETERS = {"apikey", "key", "token", "accesstoken", "authorization", "password", "secret", "bearer"}


def _has_auth_query(query: str) -> bool:
    return any(re.sub(r"[^a-z]", "", name.lower()) in _AUTH_PARAMETERS for name, _ in parse_qsl(query))


def trusted_page_url(value: Any) -> bool:
    if not isinstance(value, str) or not value or any(ord(char) <= 32 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and parsed.hostname == "api.massive.com"
                and parsed.port in (None, 443) and not parsed.username and not parsed.password
                and parsed.path == "/v2/reference/news" and not parsed.fragment
                and len(parse_qsl(parsed.query, keep_blank_values=True)) == 1
                and parse_qsl(parsed.query, keep_blank_values=True)[0][0] == "cursor"
                and bool(parse_qsl(parsed.query, keep_blank_values=True)[0][1]))
    except ValueError:
        return False


def _number(value, default, *, maximum):
    number = default if value is None else float(value)
    if not math.isfinite(number) or number <= 0 or number > maximum:
        raise ValueError("Massive request limits must be finite positive values within bounds")
    return number


def _integer(value, default, maximum):
    number = _number(value, default, maximum=maximum)
    if int(number) != number or isinstance(value, bool):
        raise ValueError("Massive page and request limits must be integers")
    return int(number)


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


class _PreserveBearerAuth:
    """An explicit auth hook prevents Requests from substituting .netrc auth."""
    def __call__(self, request):
        return request


class MassiveNewsIntelligenceProvider:
    provider_id = PROVIDER_ID

    def __init__(self, *, lifecycle=None, transport=None, limiter=None):
        self._credential = (os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY") or "").strip()
        self.lifecycle = lifecycle if lifecycle is not None else RssFetchLifecycle()
        self._transport = transport
        self._limiter = limiter

    def _safe(self, value: Any) -> str:
        text = value if isinstance(value, str) else ""
        if self._credential:
            text = text.replace(self._credential, "[REDACTED]")
        text = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", text)
        text = re.sub(r"(?i)([?&](?:api_?key|access_?token|authorization|token|password|secret)=)[^&#\s]*",
                      r"\1[REDACTED]", text)
        return text

    def _article(self, row, candidate, request, start, end, acquired):
        if not isinstance(row, Mapping):
            return None, "invalid_article"
        published = _timestamp(row.get("published_utc"))
        if published is None:
            return None, "invalid_publication_time"
        if published > acquired:
            return None, "future_publication_time"
        if not start <= published <= end:
            return None, "outside_query_window"
        title = self._safe(row.get("title"))
        summary = self._safe(row.get("description"))
        identity = dict(candidate.metadata)
        if candidate.company_name:
            identity.setdefault("company_name", candidate.company_name)
        if candidate.aliases:
            identity["aliases"] = (identity.get("aliases", ()), *candidate.aliases)
        match = symbol_relevance_match(candidate.normalized_symbol, title=title, summary=summary, metadata=identity)
        if not match:
            return None, "issuer_relevance_rejected"
        article_id = self._safe(row.get("id"))
        url = row.get("article_url")
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
            safe_url = (parsed is not None and parsed.scheme in {"http", "https"} and parsed.hostname
                        and not parsed.username and not parsed.password and not _has_auth_query(parsed.query)
                        and not any(ord(char) <= 32 for char in url)
                        and (not self._credential or self._credential not in url))
        except ValueError:
            safe_url = False
        if not article_id or not safe_url:
            return None, "invalid_article_identity_or_url"
        publisher = row.get("publisher")
        name = self._safe(publisher.get("name")) if isinstance(publisher, Mapping) else ""
        tags = row.get("tickers")
        tags = tuple(self._safe(value) for value in tags if isinstance(value, str)) if isinstance(tags, list) else ()
        age = (acquired - published).total_seconds()
        freshness = request.freshness_seconds
        return NewsEvidence(
            symbol=candidate.normalized_symbol, evidence_id=f"massive:{candidate.normalized_symbol}:{article_id}",
            company_name=candidate.company_name, aliases=candidate.aliases, match_type=match[0], matched_field=match[1],
            match_confidence=1.0, headline=title, summary=summary or None, url=url, reference_id=article_id,
            published_at=published, fetched_at=acquired, first_seen_at=acquired, age_seconds=age,
            stale=age > float(freshness) if freshness is not None else None,
            original_source=name or None, observed_source=name or None, source_domain=parsed.hostname,
            provider=PROVIDER_ID, source_group=SOURCE_GROUP, source_tier="historical", verified_source=None,
            is_qualifying_event_class=False, retrieval_status="available",
            raw={"provider_article_id": article_id, "provider_tickers": tags,
                 "provider_published_utc": self._safe(row.get("published_utc"))},
            audit={"classification_authority": "strategy_adapter_not_common_provider",
                   "provider_ticker_association_is_relevance_proof": False},
        ), None

    def _normalize_page(self, payload, candidate, request, start, end, acquired, prior_items, page_size, deadline):
        if (not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list)
                or payload.get("status", "OK") != "OK"
                or ("count" in payload and (not isinstance(payload["count"], int)
                    or isinstance(payload["count"], bool) or payload["count"] != len(payload["results"])))):
            return None, "invalid_response"
        entries = payload["results"]
        accepted, rejected = [], Counter()
        for row in entries[:page_size]:
            if time.monotonic() >= deadline:
                return None, "deadline_exhausted"
            evidence, reason = self._article(row, candidate, request, start, end, acquired)
            if reason:
                rejected[reason] += 1
            else:
                accepted.append(evidence)
        items = [*prior_items, *accepted]
        unique = dedupe_evidence(items, max_items=max(1, len(items)))
        if time.monotonic() >= deadline:
            return None, "deadline_exhausted"
        return {"returned": len(entries), "accepted": len(accepted), "rejected": dict(rejected),
                "duplicates": len(items)-len(unique), "unique": unique,
                "overflow": len(entries) > page_size, "next_url": payload.get("next_url")}, None

    def _fetch_page(self, url, params, timeout, deadline, index, callback_ready, observation,
                    candidate, request, start, end, prior_items, page_size):
        response = None
        payload = None
        normalized = None
        failure = None
        timed_out = False
        request_elapsed = parse_elapsed = status = None
        attempted = False
        try:
            failure = self._limiter.acquire(deadline)
            if failure is None and time.monotonic() >= deadline:
                failure = "deadline_exhausted_before_attempt"
            if failure is None:
                attempted = True
                observation["attempted"] = True
                self.lifecycle.source_started(index, time.monotonic())
                request_started = time.monotonic()
                try:
                    transport = self._transport or requests.get
                    response = transport(url, params=params, headers={"Authorization": "Bearer " + self._credential},
                                         timeout=min(timeout, max(0.001, deadline - time.monotonic())), allow_redirects=False,
                                         auth=_PreserveBearerAuth())
                finally:
                    request_elapsed = max(0.0, time.monotonic() - request_started)
                status = int(response.status_code)
                if status == 429:
                    retry = 60.001
                    header = response.headers.get("Retry-After", "")
                    try:
                        retry = max(retry, float(header))
                    except (ValueError, TypeError):
                        try:
                            parsed = parsedate_to_datetime(header)
                            retry = max(retry, (parsed - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError, OverflowError):
                            pass
                    observation["cooldown_persisted"] = self._limiter.cooldown(retry)
                    failure = "HTTP_429"
                elif 300 <= status < 400:
                    failure = "redirect_refused"
                elif status < 200 or status >= 300:
                    failure = f"HTTP_{status}"
                else:
                    parse_started = time.monotonic()
                    try:
                        payload = response.json()
                    except Exception:
                        failure = "invalid_json"
                    finally:
                        parse_elapsed = max(0.0, time.monotonic() - parse_started)
        except Exception as exc:
            # Never serialize exception text, request objects, headers or body.
            timed_out = requests is not None and isinstance(exc, requests.exceptions.Timeout)
            failure = "request_timeout" if timed_out else "request_error"
        acquired = datetime.now(timezone.utc)
        if failure is None:
            try:
                normalized, failure = self._normalize_page(payload, candidate, request, start, end, acquired,
                                                            prior_items, page_size, deadline)
            except Exception:
                failure = "invalid_response"
        completed = time.monotonic()
        result = {"normalized": normalized, "failure_reason": failure, "timed_out": timed_out,
                  "attempted": attempted, "http_status": status, "request_elapsed_seconds": request_elapsed,
                  "parse_elapsed_seconds": parse_elapsed, "completed_at_s": completed,
                  "elapsed_seconds": max(0.0, completed - observation["submitted_at_s"]),
                  "response_closed": None, "_response": response,
                  "fetched_at": acquired, "cooldown_persisted": observation.get("cooldown_persisted")}
        public = {key: value for key, value in result.items() if key not in {"normalized", "_response", "fetched_at"}}
        self.lifecycle.source_completed(index, public)
        callback_ready.wait()
        return result

    def _close_page(self, future, index):
        if future.cancelled():
            return
        result = future.result()
        response = result.pop("_response", None)
        updates = {}
        if response is not None:
            try:
                response.close()
                updates["response_closed"] = True
            except Exception:
                updates.update(response_closed=False, cleanup_error="response_close_error")
        result.update(updates)
        self.lifecycle.source_cleanup_completed(index, updates)

    def get_news(self, candidates: Sequence[NewsCandidate], request: NewsRequest, retrieval_policy: RetrievalPolicy) -> NewsBatchResult:
        started_s = time.monotonic()
        started_at = datetime.now(timezone.utc)
        first_candidates = {}
        for candidate in candidates:
            if candidate.normalized_symbol:
                first_candidates.setdefault(candidate.normalized_symbol, candidate)
        ordered = tuple(first_candidates.values())
        metadata = retrieval_policy.metadata
        page_size = _integer(metadata.get("massive_page_size"), 100, 1000)
        max_pages = _integer(metadata.get("massive_max_pages_per_symbol"), 2, 100)
        max_requests = _integer(metadata.get("massive_max_requests"), 5, 100)
        if metadata.get("massive_requests_per_minute", 5) != 5:
            raise ValueError("Massive entitlement is unverified; the limit remains five requests per minute")
        budget = _number(retrieval_policy.total_budget_seconds, 30, maximum=600)
        timeout = _number(retrieval_policy.request_timeout_seconds, 5, maximum=60)
        deadline = started_s + budget
        start, end = getattr(request, "query_start_utc", None), getattr(request, "query_end_utc", None)
        if start is None and end is None:
            end = started_at
            start = end - timedelta(seconds=_number(request.lookback_seconds, 86400, maximum=3660*86400))
        elif (start is None or end is None or start.tzinfo is None or end.tzinfo is None or start >= end):
            raise ValueError("Massive query requires an ordered timezone-aware UTC window pair")
        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        if end > started_at:
            raise ValueError("Massive query end must not be in the future")
        states = {candidate.normalized_symbol: {"candidate": candidate, "items": [], "rows": [], "pages": 0,
            "returned": 0, "accepted": 0, "duplicates": 0, "rejected": Counter(), "reason": None,
            "complete": False, "budget": False, "cooldown_persisted": None, "urls": set(), "next": ENDPOINT} for candidate in ordered}
        pending = deque(states)
        attempted_count = submitted_count = 0
        stop_reason = None
        if not retrieval_policy.network_allowed or retrieval_policy.refresh_mode in {"cache_only", "disabled"}:
            stop_reason = "network_disabled"
        elif not self._credential:
            stop_reason = "missing_credential"
        elif requests is None and self._transport is None:
            stop_reason = "requests_unavailable"
        if self._limiter is None and stop_reason is None:
            self._limiter = MassiveRateLimiter()
        executor = None
        try:
            while pending and stop_reason is None:
                if time.monotonic() >= deadline:
                    stop_reason = "deadline_exhausted_before_attempt"
                    break
                if submitted_count >= max_requests:
                    stop_reason = "request_limit_reached"
                    break
                symbol = pending.popleft()
                state = states[symbol]
                page = state["pages"] + 1
                source_id = f"massive:{symbol}:page:{page}"
                url = state["next"]
                params = ({"ticker": symbol, "published_utc.gte": start.isoformat(), "published_utc.lte": end.isoformat(),
                           "sort": "published_utc", "order": "asc", "limit": page_size} if page == 1 else None)
                submitted = time.monotonic()
                index = self.lifecycle.source_submitted(source_id, "historical", submitted)
                observation = {"attempted": False, "submitted_at_s": submitted}
                callback_ready = threading.Event()
                if executor is None:
                    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="news-massive")
                    self.lifecycle.register_executor(executor)
                future = executor.submit(self._fetch_page, url, params, timeout, deadline, index, callback_ready, observation,
                                         state["candidate"], request, start, end, tuple(state["items"]), page_size)
                submitted_count += 1
                try:
                    self.lifecycle.register_future(index, future)
                    future.add_done_callback(lambda done, i=index: self._close_page(done, i))
                finally:
                    callback_ready.set()
                wait([future], timeout=max(0.0, deadline - time.monotonic()))
                if future.done():
                    page_result = future.result()
                    attempted = page_result["attempted"]
                    late = page_result["completed_at_s"] >= deadline
                    failure = page_result["failure_reason"]
                    state["cooldown_persisted"] = page_result["cooldown_persisted"]
                    stage_budget = late or failure in {"rate_limit_deadline", "deadline_exhausted_before_attempt", "deadline_exhausted"}
                    state["budget"] = stage_budget
                    failure = failure or ("deadline_exhausted" if late else None)
                    row = SourceDiagnostic(source_id, provider=PROVIDER_ID, source_group=SOURCE_GROUP,
                        source_tier="historical", retrieval_status="budget_exhausted" if stage_budget else "provider_error" if failure else "available",
                        attempted=attempted, failure_reason=failure, elapsed_seconds=page_result["elapsed_seconds"],
                        timeout_seconds=timeout, timed_out=page_result["timed_out"], budget_exhausted=stage_budget,
                        request_elapsed_seconds=page_result["request_elapsed_seconds"], parse_elapsed_seconds=page_result["parse_elapsed_seconds"],
                        http_status=page_result["http_status"], response_closed=page_result["response_closed"],
                        elapsed_kind="worker_fetch_parse", worker_completed=True)
                else:
                    cancelled = future.cancel()
                    self.lifecycle.cancellation_requested(index, cancelled)
                    attempted = bool(observation["attempted"])
                    state["budget"] = True
                    failure = "deadline_exhausted"
                    row = SourceDiagnostic(source_id, provider=PROVIDER_ID, source_group=SOURCE_GROUP, source_tier="historical",
                        retrieval_status="budget_exhausted", attempted=attempted, failure_reason=failure,
                        elapsed_seconds=max(0.0, time.monotonic()-submitted), timeout_seconds=timeout,
                        budget_exhausted=True, elapsed_kind="since_submission", worker_completed=False)
                state["rows"].append(row)
                attempted_count += int(attempted)
                if attempted:
                    state["pages"] += 1
                if failure:
                    state["reason"] = failure
                    if state["budget"] or failure in {"HTTP_401", "HTTP_403", "HTTP_429", "rate_limiter_unavailable"}:
                        stop_reason = failure
                    continue
                normalized = page_result["normalized"]
                state["returned"] += normalized["returned"]
                state["accepted"] += normalized["accepted"]
                state["rejected"].update(normalized["rejected"])
                state["duplicates"] += normalized["duplicates"]
                state["rows"][-1] = replace(row, feed_item_count=normalized["returned"], matched_count=normalized["accepted"])
                unique = normalized["unique"]
                cap = evidence_max_entries(request)
                state["items"] = unique[:cap]
                next_url = normalized["next_url"]
                response_overflow = normalized["overflow"]
                if response_overflow:
                    state["reason"] = "response_limit_reached"
                elif len(unique) > cap or (len(unique) >= cap and next_url):
                    state["reason"] = "result_limit_reached"
                elif next_url:
                    if not trusted_page_url(next_url) or (self._credential and self._credential in next_url):
                        state["reason"] = "untrusted_pagination_url"
                    elif next_url in state["urls"]:
                        state["reason"] = "pagination_cycle"
                    elif state["pages"] >= max_pages:
                        state["reason"] = "page_limit_reached"
                    else:
                        state["urls"].add(next_url)
                        state["next"] = next_url
                        pending.append(symbol)
                else:
                    state["complete"] = True
        finally:
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
        for symbol in pending:
            state = states[symbol]
            state["reason"] = stop_reason
            state["budget"] = time.monotonic() >= deadline or stop_reason in {"deadline_exhausted", "deadline_exhausted_before_attempt", "rate_limit_deadline"}
            state["rows"].append(SourceDiagnostic(f"massive:{symbol}:page:{state['pages']+1}", provider=PROVIDER_ID,
                source_group=SOURCE_GROUP, source_tier="historical", retrieval_status="not_requested",
                attempted=False, failure_reason=stop_reason, budget_exhausted=state["budget"]))
        summaries, evidence, rows = {}, {}, []
        for symbol, state in states.items():
            status = ("available" if state["complete"] else "budget_exhausted" if state["budget"]
                      else "partial" if state["pages"] and (state["items"] or state["reason"] in {
                          "request_limit_reached", "page_limit_reached", "result_limit_reached", "response_limit_reached", "pagination_cycle", "untrusted_pagination_url"})
                      else "unavailable")
            available = any(row.http_status is not None and 200 <= row.http_status < 300 for row in state["rows"])
            evidence[symbol] = tuple(state["items"])
            details = {"source_diagnostics": [asdict(row) for row in state["rows"]],
                "query_start_utc": start.isoformat(), "query_end_utc": end.isoformat(),
                "pages_attempted": state["pages"], "returned_article_count": state["returned"],
                "accepted_article_count": state["accepted"], "duplicate_article_count": state["duplicates"],
                "retained_article_count": len(state["items"]), "accepted_before_cap_count": state["accepted"] - state["duplicates"],
                "result_truncated": state["reason"] in {"result_limit_reached", "response_limit_reached"}, "rejected_article_counts": dict(state["rejected"]),
                "complete": state["complete"], "failure_reason": state["reason"],
                "cooldown_persisted": state["cooldown_persisted"],
                "objective_news_status": "news_present_unclassified" if state["items"] else "no_recent_news" if state["complete"] else state["reason"],
                "classification_authority": "strategy_adapter_not_common_provider"}
            summaries[symbol] = summarize_news_evidence(symbol, state["items"], request=request,
                retrieval_status=status, provider_status="available" if state["complete"] else state["reason"],
                provider_available=available, budget_exhausted=state["budget"], diagnostics=details)
            rows.extend(state["rows"])
        incomplete = tuple(symbol for symbol, state in states.items() if not state["complete"])
        any_available = any(summary.provider_available for summary in summaries.values())
        exhausted = any(summary.budget_exhausted for summary in summaries.values())
        diagnostics = RetrievalDiagnostics(
            retrieval_status="available" if not incomplete else "budget_exhausted" if exhausted else "partial" if any_available else "unavailable",
            provider_status="available" if not incomplete else "partial_request_failure" if any_available else stop_reason or "provider_request_failure",
            provider_available=any_available, source_groups_queried=(SOURCE_GROUP,) if attempted_count else (),
            provider_groups_queried=(PROVIDER_ID,) if attempted_count else (),
            sources_queried=tuple(row.source_id for row in rows if row.attempted), source_diagnostics=tuple(rows),
            source_failures={row.source_id: row.failure_reason for row in rows if row.failure_reason},
            sources_attempted_count=attempted_count, sources_skipped_due_to_budget_count=sum(not row.attempted and row.budget_exhausted for row in rows),
            timeout_count=sum(row.timed_out for row in rows), elapsed_seconds=max(0.0,time.monotonic()-started_s),
            total_budget_seconds=budget, budget_exhausted=exhausted, unresolved_symbols=incomplete,
            diagnostics={"provider_id": PROVIDER_ID, "endpoint": ENDPOINT, "query_start_utc": start.isoformat(),
                "query_end_utc": end.isoformat(), "requests_attempted": attempted_count, "max_requests": max_requests,
                "max_pages_per_symbol": max_pages, "page_size": page_size, "requests_per_minute": 5,
                "automatic_retries": 0, "rate_scope": "shared_local_user_all_massive_keys",
                "external_account_usage_observable": False, "provider_updates": "hourly",
                "provider_details_by_symbol": {symbol: dict(summary.diagnostics) for symbol,summary in summaries.items()}},
        )
        return NewsBatchResult(candidates=ordered, evidence_by_symbol=evidence, summaries_by_symbol=summaries,
            diagnostics=diagnostics, request=request, retrieval_policy=retrieval_policy, started_at=started_at,
            completed_at=datetime.now(timezone.utc))
