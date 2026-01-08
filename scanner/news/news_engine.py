from __future__ import annotations

import logging
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from scanner.core.paths import get_verified_rss_path
from scanner.news.credibility import credibility_score
from scanner.news.relevance import normalize_title, symbol_match

logger = logging.getLogger(__name__)

try:
    import feedparser  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    feedparser = None

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    requests = None

NEWS_REFRESH_SECONDS = int(os.environ.get("NEWS_REFRESH_SECONDS", "60"))
NEWS_MAX_ITEMS_PER_FEED = int(os.environ.get("NEWS_MAX_ITEMS_PER_FEED", "50"))
NEWS_MAX_TOP_HEADLINES = int(os.environ.get("NEWS_MAX_TOP_HEADLINES", "5"))

_NEWS_CACHE: Dict[str, Any] = {
    "loaded_at": 0.0,
    "items": [],
}


@dataclass
class NewsItem:
    title: str
    url: str
    published_ts: Optional[float]
    age_minutes: Optional[float]
    domain: str
    region: str
    source_name: str
    summary: Optional[str]


class NewsEngine:
    def __init__(self, refresh_seconds: int = NEWS_REFRESH_SECONDS) -> None:
        self.refresh_seconds = refresh_seconds

    def _load_feeds(self) -> List[str]:
        path = get_verified_rss_path()
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Unable to read verified RSS list at %s: %s", path, exc)
            return []
        feeds = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            feeds.append(line)
        return feeds

    def _fetch_feed(self, url: str) -> Optional[bytes]:
        if requests is None:
            return None
        try:
            response = requests.get(url, timeout=8)
            if response.status_code >= 400:
                return None
            return response.content
        except Exception:
            return None

    def _parse_items(self, feed_data: bytes) -> Sequence[NewsItem]:
        if feedparser is None:
            return []
        parsed = feedparser.parse(feed_data)
        items: List[NewsItem] = []
        feed_title = parsed.feed.get("title") if getattr(parsed, "feed", None) else None
        for entry in parsed.entries[:NEWS_MAX_ITEMS_PER_FEED]:
            title = entry.get("title", "").strip()
            url = entry.get("link", "").strip()
            if not title or not url:
                continue
            published_ts = None
            if entry.get("published_parsed"):
                published_ts = time.mktime(entry.published_parsed)
            elif entry.get("updated_parsed"):
                published_ts = time.mktime(entry.updated_parsed)

            age_minutes = None
            if published_ts:
                age_minutes = round((time.time() - published_ts) / 60.0, 2)

            domain = urlparse(url).netloc.lower()
            region = infer_region(domain)
            source_name = feed_title or domain
            summary = entry.get("summary")
            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    published_ts=published_ts,
                    age_minutes=age_minutes,
                    domain=domain,
                    region=region,
                    source_name=source_name,
                    summary=summary,
                )
            )
        return items

    def _refresh_cache(self) -> None:
        now = time.time()
        if now - _NEWS_CACHE.get("loaded_at", 0.0) < self.refresh_seconds:
            return
        feeds = self._load_feeds()
        all_items: List[NewsItem] = []
        for feed_url in feeds:
            feed_data = self._fetch_feed(feed_url)
            if not feed_data:
                continue
            items = self._parse_items(feed_data)
            all_items.extend(items)
        _NEWS_CACHE["loaded_at"] = now
        _NEWS_CACHE["items"] = all_items

    def get_news(self, symbol: str) -> Dict[str, Any]:
        self._refresh_cache()
        items: List[NewsItem] = list(_NEWS_CACHE.get("items", []))
        matches: List[NewsItem] = []
        for item in items:
            if symbol_match(item.title, symbol) or symbol_match(item.summary, symbol):
                matches.append(item)

        total = len(matches)
        normalized_map: Dict[str, NewsItem] = {}
        for item in matches:
            key = normalize_title(item.title)
            if key and key not in normalized_map:
                normalized_map[key] = item

        unique_items = list(normalized_map.values())
        unique_count = len(unique_items)
        replicated = max(total - unique_count, 0)

        vel10 = sum(1 for item in unique_items if item.age_minutes is not None and item.age_minutes <= 10)
        vel60 = sum(1 for item in unique_items if item.age_minutes is not None and item.age_minutes <= 60)
        freshest = None
        ages = [item.age_minutes for item in unique_items if item.age_minutes is not None]
        if ages:
            freshest = round(min(ages), 2)

        regions = sorted({item.region for item in unique_items if item.region})
        region_count = len(regions)

        sources = [item.source_name for item in unique_items if item.source_name]
        top_sources = [name for name, _count in Counter(sources).most_common(5)]

        if unique_items:
            scores = [credibility_score(item.domain) for item in unique_items]
            credibility = round(sum(scores) / len(scores), 3)
        else:
            credibility = 0.0

        sorted_items = sorted(
            unique_items,
            key=lambda item: item.published_ts if item.published_ts is not None else 0.0,
            reverse=True,
        )
        top_headlines = []
        for item in sorted_items[:NEWS_MAX_TOP_HEADLINES]:
            top_headlines.append(
                {
                    "title": item.title,
                    "url": item.url,
                    "age_minutes": item.age_minutes,
                    "source": item.source_name,
                    "region": item.region,
                }
            )

        spike_indicator = vel10 >= 3 or (vel10 >= 1 and vel60 >= 3)

        return {
            "news_total_headlines": total,
            "news_unique_headlines": unique_count,
            "news_replicated_headlines": replicated,
            "news_velocity_10m": vel10,
            "news_velocity_60m": vel60,
            "news_spike_indicator": spike_indicator,
            "news_freshest_age_minutes": freshest,
            "news_regions_list": regions,
            "news_region_count": region_count,
            "news_top_sources_list": top_sources,
            "news_top_source_credibility_score": credibility,
            "news_top_headlines_list": top_headlines,
        }


def infer_region(domain: str) -> str:
    if not domain:
        return "US/Global"
    tld = domain.split(".")[-1].lower()
    if tld in {"uk", "co", "co.uk"}:
        return "UK"
    if tld == "ca":
        return "CA"
    if tld == "au":
        return "AU"
    if tld == "de":
        return "DE"
    if tld == "fr":
        return "FR"
    if tld == "es":
        return "ES"
    if tld == "it":
        return "IT"
    if tld == "nl":
        return "NL"
    if tld == "jp":
        return "JP"
    if tld == "cn":
        return "CN"
    if tld == "in":
        return "IN"
    if tld == "br":
        return "BR"
    return "US/Global"
