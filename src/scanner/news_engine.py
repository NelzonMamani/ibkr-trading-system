"""RSS-based news engine for the scanner (stand-alone friendly)."""
from __future__ import annotations

import importlib
import importlib.util
import logging
import re
import time
import urllib.parse
from collections import Counter
from typing import Optional

from .scanner_config import (
    NEWS_ENABLED,
    NEWS_LOOKBACK_HOURS,
    NEWS_MAX_ENTRIES_PER_SYMBOL,
    NEWS_REQUEST_TIMEOUT_S,
    VERIFIED_RSS_PATH,
)

if importlib.util.find_spec("feedparser"):
    feedparser = importlib.import_module("feedparser")  # type: ignore
else:  # pragma: no cover
    feedparser = None

if importlib.util.find_spec("requests"):
    requests = importlib.import_module("requests")  # type: ignore
else:  # pragma: no cover
    requests = None

logging.getLogger("feedparser").setLevel(logging.ERROR)

from src.config.config_resolver import get_config

NEWS_REFRESH_SECONDS = int(get_config("NEWS_REFRESH_SECONDS"))
NEWS_MAX_ITEMS_PER_FEED = int(get_config("NEWS_MAX_ITEMS_PER_FEED"))
NEWS_MAX_TOP_HEADLINES = int(get_config("NEWS_MAX_TOP_HEADLINES"))
NEWS_DEBUG = bool(get_config("NEWS_DEBUG"))

DOMAIN_CREDIBILITY = {
    "reuters.com": 1.00,
    "bloomberg.com": 0.95,
    "wsj.com": 0.95,
    "ft.com": 0.90,
    "apnews.com": 0.90,
    "bbc.co.uk": 0.88,
    "bbc.com": 0.88,
}

_NEWS_CACHE = {
    "loaded_at": 0.0,
    "rss_urls": [],
    "items": [],
}


def _load_verified_rss_urls(path: str) -> list:
    """Load RSS feed URLs from a verified list (one per line)."""
    urls: list = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = (line or "").strip()
                if not s or s.startswith("#"):
                    continue
                urls.append(s)
    except FileNotFoundError:
        logging.warning("verified_rss.txt not found at %s (News will be empty).", path)
        urls = []
    except Exception as exc:
        logging.warning("Failed reading verified_rss.txt at %s: %s", path, exc)
        urls = []

    out = []
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)

    if NEWS_DEBUG:
        logging.info("RSS sources loaded: %d", len(out))

    return out


def _domain_from_url(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        host = host.split("@")[-1]
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _infer_region_from_domain(domain: str) -> str:
    if domain.endswith(".co.uk") or domain.endswith(".uk"):
        return "UK"
    if domain.endswith(".ca"):
        return "CA"
    if domain.endswith(".au"):
        return "AU"
    if domain.endswith(".de"):
        return "DE"
    if domain.endswith(".fr"):
        return "FR"
    if domain.endswith(".es"):
        return "ES"
    if domain.endswith(".it"):
        return "IT"
    if domain.endswith(".nl"):
        return "NL"
    if domain.endswith(".jp"):
        return "JP"
    if domain.endswith(".cn"):
        return "CN"
    if domain.endswith(".in"):
        return "IN"
    if domain.endswith(".br"):
        return "BR"
    return "US/Global"


def _credibility_for_domain(domain: str) -> float:
    if not domain:
        return 0.0
    if domain in DOMAIN_CREDIBILITY:
        return float(DOMAIN_CREDIBILITY[domain])
    for suffix, score in DOMAIN_CREDIBILITY.items():
        if domain.endswith(suffix):
            return float(score)
    return 0.60


def _published_ts_from_entry(entry) -> Optional[float]:
    try:
        if getattr(entry, "published_parsed", None):
            return time.mktime(entry.published_parsed)
        if getattr(entry, "updated_parsed", None):
            return time.mktime(entry.updated_parsed)
    except Exception:
        return None
    return None


def _fetch_feed(url: str):
    if feedparser is None:
        return None
    if requests is None:
        return feedparser.parse(url)
    try:
        response = requests.get(url, timeout=NEWS_REQUEST_TIMEOUT_S)
        response.raise_for_status()
        return feedparser.parse(response.text)
    except Exception as exc:
        logging.debug("[NEWS] RSS fetch failed for %s: %s", url, exc)
        return None


def _refresh_news_cache_if_needed(now_ts: float) -> None:
    if (now_ts - _NEWS_CACHE["loaded_at"]) < NEWS_REFRESH_SECONDS and _NEWS_CACHE["items"]:
        return

    if feedparser is None:
        _NEWS_CACHE["loaded_at"] = now_ts
        _NEWS_CACHE["items"] = []
        return

    rss_urls = _load_verified_rss_urls(str(VERIFIED_RSS_PATH))
    _NEWS_CACHE["rss_urls"] = rss_urls

    if not rss_urls:
        _NEWS_CACHE["loaded_at"] = now_ts
        _NEWS_CACHE["items"] = []
        return

    items = []
    feeds_ok = 0
    feeds_err = 0
    for url in rss_urls:
        feed = _fetch_feed(url)
        if feed is None:
            feeds_err += 1
            continue
        if getattr(feed, "bozo", False):
            feeds_err += 1
            if NEWS_DEBUG:
                logging.info("RSS parse bozo: %s (%s)", url, getattr(feed, "bozo_exception", ""))
        else:
            feeds_ok += 1

        feed_title = ""
        try:
            feed_title = (feed.feed.get("title") or "").strip()
        except Exception:
            feed_title = ""

        for entry in (feed.entries or [])[:NEWS_MAX_ITEMS_PER_FEED]:
            title = (getattr(entry, "title", "") or "").strip()
            link = (getattr(entry, "link", "") or "").strip()
            if not title or not link:
                continue
            ts = _published_ts_from_entry(entry)
            age_min = None
            if ts is not None:
                age_min = max(0.0, (now_ts - ts) / 60.0)
            domain = _domain_from_url(link)
            region = _infer_region_from_domain(domain)

            items.append(
                {
                    "title": title,
                    "url": link,
                    "published_ts": ts,
                    "age_minutes": age_min,
                    "source": feed_title or domain or "Unknown",
                    "domain": domain,
                    "region": region,
                }
            )

    items.sort(key=lambda item: (item["published_ts"] is None, -(item["published_ts"] or 0)))

    _NEWS_CACHE["loaded_at"] = now_ts
    if NEWS_DEBUG:
        logging.info("RSS refresh: feeds_ok=%d feeds_err=%d items=%d", feeds_ok, feeds_err, len(items))
    _NEWS_CACHE["items"] = items


def blank_news_fields() -> dict:
    return {
        "news_total_headlines": 0,
        "news_unique_headlines": 0,
        "news_replicated_headlines": 0,
        "news_velocity_10m": 0,
        "news_velocity_60m": 0,
        "news_spike_indicator": False,
        "news_freshest_age_minutes": None,
        "news_regions_list": [],
        "news_region_count": 0,
        "news_top_sources_list": [],
        "news_top_source_credibility_score": 0.0,
        "news_average_sentiment": 0.0,
        "news_keyword_relevance_score": 0.0,
        "news_primary_catalyst_keywords": [],
        "news_top_headlines_list": [],
    }


def _matches_symbol(text: str, symbol: str) -> bool:
    if not text or not symbol:
        return False
    pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", re.IGNORECASE)
    return pattern.search(text) is not None


def get_news_truth(symbol: str) -> dict:
    if not NEWS_ENABLED or feedparser is None:
        return blank_news_fields()

    now_ts = time.time()
    _refresh_news_cache_if_needed(now_ts)

    items = _NEWS_CACHE.get("items", [])
    if not items:
        return blank_news_fields()

    matched = [it for it in items if _matches_symbol(it.get("title", ""), symbol)]

    lookback_minutes = NEWS_LOOKBACK_HOURS * 60.0
    if lookback_minutes > 0:
        matched = [
            it
            for it in matched
            if it.get("age_minutes") is None or it.get("age_minutes") <= lookback_minutes
        ]

    if not matched:
        return blank_news_fields()

    matched = matched[:NEWS_MAX_ENTRIES_PER_SYMBOL]

    norm_map = {}
    for item in matched:
        norm = re.sub(r"\s+", " ", (item.get("title") or "").strip().lower())
        norm_map.setdefault(norm, []).append(item)

    unique_items = [value[0] for value in norm_map.values()]
    replicated = sum(max(0, len(value) - 1) for value in norm_map.values())

    def within(minutes: float, item: dict) -> bool:
        age = item.get("age_minutes")
        return age is not None and age <= minutes

    vel10 = sum(1 for item in unique_items if within(10, item))
    vel60 = sum(1 for item in unique_items if within(60, item))

    freshest = None
    ages = [item.get("age_minutes") for item in unique_items if item.get("age_minutes") is not None]
    if ages:
        freshest = min(ages)

    regions = sorted({(item.get("region") or "US/Global") for item in unique_items})
    sources = [item.get("source") or "Unknown" for item in unique_items]
    top_sources = [name for name, _ in Counter(sources).most_common(5)]

    credibility = 0.0
    for item in unique_items[:10]:
        credibility = max(credibility, _credibility_for_domain(item.get("domain", "")))

    spike = (vel10 >= 5) or (vel10 >= 3 and vel60 >= 6)

    top_headlines = []
    for item in unique_items[:NEWS_MAX_TOP_HEADLINES]:
        top_headlines.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "age_minutes": item.get("age_minutes"),
                "source": item.get("source", ""),
                "region": item.get("region", ""),
            }
        )

    return {
        "news_total_headlines": len(matched),
        "news_unique_headlines": len(unique_items),
        "news_replicated_headlines": int(replicated),
        "news_velocity_10m": int(vel10),
        "news_velocity_60m": int(vel60),
        "news_spike_indicator": bool(spike),
        "news_freshest_age_minutes": round(float(freshest), 2) if freshest is not None else None,
        "news_regions_list": regions,
        "news_region_count": int(len(regions)),
        "news_top_sources_list": top_sources,
        "news_top_source_credibility_score": round(float(credibility), 2),
        "news_average_sentiment": 0.0,
        "news_keyword_relevance_score": 0.0,
        "news_primary_catalyst_keywords": [],
        "news_top_headlines_list": top_headlines,
    }
