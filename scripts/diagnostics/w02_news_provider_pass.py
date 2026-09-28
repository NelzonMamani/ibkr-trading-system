"""One bounded provider-only evidence pass; no broker/scanner runtime imports.

Raw responses stay in the explicitly supplied diagnostic directory. The sentinel
prevents accidental repetition. Health-only requests cover never-attempted URLs;
they are not included in production-budget results and never retry a URL.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-once", action="store_true", required=True)
    args = parser.parse_args()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with (out / "pass_started.json").open("x", encoding="utf-8") as f:
        json.dump({"started_at": datetime.now(timezone.utc).isoformat(), "max_seconds": 240}, f)
    def expired():
        (out / "deadline_exit.json").write_text(json.dumps({"exit_code": 124, "at": datetime.now(timezone.utc).isoformat()}))
        os._exit(124)
    watchdog = threading.Timer(240, expired)
    watchdog.daemon = True
    watchdog.start()
    import requests
    from src.config.config_resolver import get_config, get_config_resolution_trace
    from src.news import news_fetcher
    from src.news.batch_rss_adapter import BatchRssNewsIntelligenceProvider
    from src.news.evidence_store import CanonicalNewsEvidenceStore
    from src.news.news_intelligence_contract import NewsCandidate, NewsRequest, RetrievalPolicy
    from src.news.news_intelligence_service import CanonicalNewsIntelligenceService
    from src.news.source_groups import get_source_group_urls

    names = ["NEWS_ENABLED", "NEWS_TOTAL_BUDGET_S", "NEWS_REQUEST_TIMEOUT_S", "NEWS_EXTENDED_TIER_RESERVE_FRACTION",
             "NEWS_MAX_AGE_HOURS", "NEWS_MAX_AGE_SECONDS", "NEWS_LOOKBACK_HOURS", "NEWS_MAX_ENTRIES_PER_SYMBOL",
             "NEWS_REFRESH_SECONDS_PREP", "NEWS_REFRESH_SECONDS_PRE", "NEWS_REFRESH_SECONDS_RTH", "NEWS_CACHE_FILE"]
    config = get_config_resolution_trace(names)
    total = float(get_config("NEWS_TOTAL_BUDGET_S"))
    timeout = float(get_config("NEWS_REQUEST_TIMEOUT_S"))
    reserve = total * float(get_config("NEWS_EXTENDED_TIER_RESERVE_FRACTION"))
    fast_budget = total - reserve
    fast_urls = list(get_source_group_urls("FAST_TRADING"))
    extended_urls = list(get_source_group_urls("PREP_EXTENDED"))
    allowed = set(fast_urls + extended_urls)
    production_cache = Path(str(get_config("NEWS_CACHE_FILE")))
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    cache_before = digest(production_cache)
    baseline = json.loads((ROOT / "artifacts/w01/live_20260928T1730Z/observation.json").read_text(encoding="utf-8"))
    symbols = baseline["scanner_cycle_artifact"]["top_n_symbols"][:2]
    candidates = [NewsCandidate(symbol) for symbol in symbols]
    request = NewsRequest(lookback_seconds=float(get_config("NEWS_LOOKBACK_HOURS"))*3600,
                          freshness_seconds=float(get_config("NEWS_MAX_AGE_HOURS"))*3600,
                          max_evidence_per_symbol=int(get_config("NEWS_MAX_ENTRIES_PER_SYMBOL")),
                          include_generic_news=True, audit_reason="w02_provider_only_saved_candidates")
    lock = threading.Lock()
    local = threading.local()
    rows = []
    raw_bodies = {}
    attempts = set()
    tier_parameters = {}
    native_get = requests.get
    native_fetch = news_fetcher._fetch_feed
    started = time.monotonic()

    def utc(): return datetime.now(timezone.utc).isoformat()
    def safe_url(url):
        p = urlsplit(str(url))
        return urlunsplit((p.scheme, p.netloc, p.path, "", ""))

    def observed_get(url, *pos, **kw):
        if url not in allowed:
            raise RuntimeError("Unconfigured endpoint refused")
        with lock:
            if url in attempts:
                raise RuntimeError("Repeated source request refused")
            attempts.add(url)
        row = local.row
        row["http_started_at"] = utc()
        http_start = time.monotonic()
        try:
            response = native_get(url, *pos, **kw)
            row.update(http_status=response.status_code, content_type=response.headers.get("Content-Type"),
                       response_bytes=len(response.content), final_url=safe_url(response.url),
                       redirects=[{"status": item.status_code, "url": safe_url(item.url)} for item in response.history])
            with lock:
                raw_bodies[url] = response.content
            return response
        except Exception as exc:
            row["http_exception"] = type(exc).__name__
            raise
        finally:
            row["http_elapsed_seconds"] = time.monotonic() - http_start
            row["http_completed_at"] = utc()

    def observed_fetch(url, timeout_s):
        source_start = time.monotonic()
        row = {"source_id": url, "scope": tier_parameters.get(url, {}).get("scope", "health_only"),
               "started_at": utc(), "started_offset_seconds": source_start-started, "timeout_seconds": timeout_s,
               "deadline": tier_parameters.get(url, {}), "http_status": None, "parse_outcome": None}
        local.row = row
        try:
            feed = native_fetch(url, timeout_s)
            parsed_at = time.monotonic()
            row["fetch_parse_elapsed_seconds"] = parsed_at-source_start
            row["non_http_seconds"] = max(0, row["fetch_parse_elapsed_seconds"]-row.get("http_elapsed_seconds", 0))
            entries = list(getattr(feed, "entries", ()) or ()) if feed is not None else []
            version = getattr(feed, "version", None)
            row.update(feed_version=version, bozo=bool(getattr(feed, "bozo", False)),
                       bozo_exception=type(getattr(feed, "bozo_exception", None)).__name__,
                       item_count=len(entries), parse_outcome="recognized_feed" if version else "unrecognized_document")
            counts = {"missing_title": 0, "missing_time": 0, "future": 0, "stale": 0, "fresh": 0}
            matched = {s: 0 for s in symbols}
            unmatched = 0
            now = time.time()
            for entry in entries:
                title = news_fetcher._clean_text(news_fetcher._entry_value(entry, "title"))
                stamp = news_fetcher._entry_timestamp(entry)
                if not title: counts["missing_title"] += 1; continue
                if stamp is None: counts["missing_time"] += 1; continue
                if stamp > now: counts["future"] += 1; continue
                if stamp < now - request.lookback_seconds: counts["stale"] += 1; continue
                counts["fresh"] += 1
                summary = news_fetcher._entry_summary(entry)
                matches = [s for s in symbols if news_fetcher.symbol_relevance_match(s, title=title, summary=summary)]
                for symbol in matches: matched[symbol] += 1
                unmatched += not bool(matches)
            row.update(item_time_counts=counts, fresh_issuer_matches=matched, fresh_unmatched_items=unmatched)
            return feed
        except Exception as exc:
            row["fetch_exception"] = type(exc).__name__
            raise
        finally:
            row["completed_at"] = utc()
            row["total_observed_seconds"] = time.monotonic()-source_start
            with lock: rows.append(row)

    def tier_fetch(native, scope):
        def wrapped(symbols, urls, **kw):
            for url in urls:
                tier_parameters[url] = {"scope": scope, "total_budget_seconds": kw.get("total_news_budget_seconds"),
                    "tier_budget_seconds": kw.get("tier_budget_seconds"),
                    "stage_started_offset": kw.get("stage_started_at_s", started)-started,
                    "stage_deadline_offset": kw.get("stage_deadline_s", started)-started,
                    "tier_deadline_offset": kw.get("tier_deadline_s", started)-started}
            return native(symbols, urls, **kw)
        return wrapped

    requests.get = observed_get
    news_fetcher._fetch_feed = observed_fetch
    provider = BatchRssNewsIntelligenceProvider(
        fast_fetcher=tier_fetch(news_fetcher.fetch_fast_headlines_for_symbols, "production_fast"),
        extended_fetcher=tier_fetch(news_fetcher.fetch_headlines_for_symbols, "production_extended"))
    service = CanonicalNewsIntelligenceService(evidence_store=CanonicalNewsEvidenceStore(
        out / "diagnostic_cache.json", prep_artifact_loader=lambda: {}), retrieval_provider=provider)
    results = {}
    try:
        results["cold_cache"] = service.get_news(candidates, request, RetrievalPolicy(network_allowed=False, refresh_mode="cache_only"))
        results["fast"] = service.get_news(candidates, request, RetrievalPolicy(source_groups=("FAST_TRADING",),
            total_budget_seconds=total, tier_budgets={"fast": fast_budget}, request_timeout_seconds=timeout,
            extended_reserve_fraction=float(get_config("NEWS_EXTENDED_TIER_RESERVE_FRACTION")),
            fallback_mode="none", refresh_mode="bounded_refresh", metadata={"refresh_symbols": symbols}))
        # These W01 symbols are deliberately unresolved by their saved Ross capture.
        # This is a provider-only policy probe; no current Ross qualification is inferred.
        ext_budget = min(reserve, max(0, total - (results["fast"].diagnostics.elapsed_seconds or 0)))
        results["extended"] = service.get_news(candidates, request, RetrievalPolicy(source_groups=("PREP_EXTENDED",),
            total_budget_seconds=ext_budget, tier_budgets={"extended": ext_budget}, request_timeout_seconds=timeout,
            fallback_mode="unresolved_only", refresh_mode="bounded_refresh",
            metadata={"refresh_symbols": symbols, "unresolved_symbols": symbols}))
        production_finished = time.monotonic()
        # A separate one-shot health sample only for sources never attempted in-budget.
        scheduled_attempts = {item.source_id for result in results.values()
                              for item in result.diagnostics.source_diagnostics if item.attempted}
        health_urls = [url for url in fast_urls+extended_urls if url not in scheduled_attempts and url not in attempts]
        def health(url):
            tier_parameters[url] = {"scope": "health_only", "configured_timeout_seconds": timeout}
            try: observed_fetch(url, timeout)
            except Exception: pass
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="w02-health") as pool:
            list(pool.map(health, health_urls))
        # Allow already-started budget-discarded requests to finish; never retry them.
        limit = time.monotonic()+max(10, 2*timeout)
        while len(rows) < len(attempts) and time.monotonic() < limit:
            time.sleep(0.05)
        raw_dir = out / "raw_responses"
        raw_dir.mkdir(exist_ok=True)
        for index, url in enumerate(fast_urls+extended_urls):
            if url in raw_bodies:
                data = raw_bodies[url]
                path = raw_dir / f"{index:02d}.response"
                path.write_bytes(data)
                for row in rows:
                    if row["source_id"] == url:
                        row.update(raw_path=str(path.relative_to(out)), raw_sha256=hashlib.sha256(data).hexdigest())
        payload = {"schema": "w02.provider_only.v1", "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "interpreter": sys.executable, "python": sys.version, "symbols": symbols,
            "identity_limit": "Saved symbols only; original issuer metadata was not retained in W01 artifact.",
            "effective_config": config, "request": asdict(request), "started_at": json.loads((out/"pass_started.json").read_text())["started_at"],
            "completed_at": utc(), "elapsed_seconds": time.monotonic()-started, "production_elapsed_seconds": production_finished-started,
            "results": {key: asdict(value) for key,value in results.items()}, "source_records": rows,
            "configured_sources": {"fast": fast_urls, "extended": extended_urls}, "health_only_urls": health_urls,
            "requests_per_url": {url: 1 for url in attempts}, "operational_cache_before": cache_before,
            "operational_cache_after": digest(production_cache), "no_broker_imports": not any(name.startswith(("ibapi", "ib_insync")) for name in sys.modules),
            "limitations": ["Diagnostic symbol evidence is separate from current strategy qualification.",
                "Health-only and late-completed source data do not count as production-budget evidence."]}
        (out/"provider_pass.json").write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
        print(json.dumps({"result": str(out/"provider_pass.json"), "sources": len(rows), "elapsed": payload["elapsed_seconds"]}))
    finally:
        requests.get = native_get
        news_fetcher._fetch_feed = native_fetch
        if len(rows) >= len(attempts):
            watchdog.cancel()

if __name__ == "__main__": main()
