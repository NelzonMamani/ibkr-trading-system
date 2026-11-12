from __future__ import annotations

import logging
import re
import time
from collections import Counter
from collections.abc import Mapping
from typing import Dict, Iterable, List
from urllib.parse import urlparse

from .news_fetcher import Headline

REGION_TLDS = {
    "uk": "UK",
    "co.uk": "UK",
    "ca": "CA",
    "au": "AU",
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "it": "IT",
    "nl": "NL",
    "jp": "JP",
    "cn": "CN",
    "in": "IN",
    "br": "BR",
}

HIGH_CREDIBILITY_SOURCES = {
    "reuters",
    "bloomberg",
    "wsj",
    "financial times",
    "associated press",
    "ap news",
    "bbc",
    "cnbc",
}

SENTIMENT_POSITIVE = {"beats", "surge", "soars", "record", "profit", "upgrade", "wins"}
SENTIMENT_NEGATIVE = {"miss", "falls", "drop", "lawsuit", "downgrade", "loss", "halt"}

CATALYST_KEYWORDS = {
    "earnings",
    "guidance",
    "merger",
    "acquisition",
    "fda",
    "approval",
    "contract",
    "partnership",
    "downgrade",
    "upgrade",
}


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def publisher_identity(label: str, provenance=None) -> str:
    """Declared publisher grouping only; never verification/confirmation authority.

    Prefer an explicit HTTP(S) publisher URL, never an article/transport URL.
    Only host case and the conventional www prefix are normalized. Distinct
    subdomains remain distinct; human names have no inferred domain mapping.
    """
    declared = (provenance or {}).get('publisher_url') if isinstance(provenance, Mapping) else None
    if isinstance(declared, str):
        try:
            parsed = urlparse(declared)
            if parsed.scheme.lower() in {'http', 'https'} and parsed.hostname and not parsed.username and not parsed.password:
                host = parsed.hostname.lower().removeprefix('www.')
                return 'host:' + host
        except ValueError:
            pass
    text = str(label or '').strip().casefold()
    if re.fullmatch(r'(?:[a-z0-9-]+\.)+[a-z]{2,63}', text):
        return 'host:' + text.removeprefix('www.')
    return 'label:' + text if text else ''


def _region_from_domain(domain: str) -> str:
    for tld, region in REGION_TLDS.items():
        if domain.endswith(tld):
            return region
    return "US"


def _sentiment_score(text: str) -> float:
    tokens = {token.strip(".,:;!?").lower() for token in text.split()}
    pos_hits = len(tokens & SENTIMENT_POSITIVE)
    neg_hits = len(tokens & SENTIMENT_NEGATIVE)
    if pos_hits == 0 and neg_hits == 0:
        return 0.0
    return (pos_hits - neg_hits) / max(pos_hits + neg_hits, 1)


def _freshness_bucket(age_seconds: float | None) -> str:
    if age_seconds is None:
        return "N/A"
    minutes = age_seconds / 60.0
    if minutes <= 5:
        return "0-5m"
    if minutes <= 15:
        return "5-15m"
    if minutes <= 60:
        return "15-60m"
    return "60m+"


def _velocity(headlines: Iterable[Headline], window_minutes: int, now_ts: float) -> int:
    threshold = now_ts - (window_minutes * 60.0)
    return sum(1 for headline in headlines if headline.published_ts >= threshold)


def normalize_headlines(
    headlines: List[Headline],
    now_ts: float | None = None,
) -> Dict[str, object]:
    now_ts = now_ts or time.time()
    if not headlines:
        return {
            "news_total_headlines": 0,
            "news_unique_headlines": 0,
            "news_replicated_headlines": 0,
            "news_sources_count": 0,
            "news_regions_list": [],
            "news_region_count": 0,
            "international_news_flag": False,
            "news_velocity_5m": 0,
            "news_velocity_10m": 0,
            "news_velocity_60m": 0,
            "seconds_since_latest_news": None,
            "news_freshest_age_minutes": None,
            "freshness_bucket": "N/A",
            "news_average_sentiment": 0.0,
            "news_weighted_sentiment": 0.0,
            "high_credibility_source_count": 0,
            "high_credibility_flag": False,
            "news_top_sources_list": [],
            "news_top_source_credibility_score": 0.0,
            "news_keyword_relevance_score": 0.0,
            "news_primary_catalyst_keywords": [],
            "news_top_headlines_list": [],
        }

    unique_keyed = {}
    for headline in headlines:
        key = (headline.title.lower(), headline.source.lower())
        unique_keyed.setdefault(key, headline)
    unique_headlines = list(unique_keyed.values())
    total = len(headlines)
    unique = len(unique_headlines)
    replicated = total - unique

    source_counts = Counter()
    source_labels = {}
    for headline in headlines:
        identity = publisher_identity(headline.source, headline.source_provenance)
        if identity:
            source_counts[identity] += 1
            source_labels.setdefault(identity, set()).add(headline.source or identity.removeprefix("host:"))
    top_sources = [sorted(source_labels[identity])[0] for identity, _ in source_counts.most_common(5)]

    regions = []
    for headline in headlines:
        domain = _domain_from_url(headline.url)
        regions.append(_region_from_domain(domain))
    region_counts = Counter(regions)
    region_list = list(region_counts.keys())
    international_flag = any(region != "US" for region in region_list)

    vel_5m = _velocity(headlines, 5, now_ts)
    vel_10m = _velocity(headlines, 10, now_ts)
    vel_60m = _velocity(headlines, 60, now_ts)
    latest_ts = max(headline.published_ts for headline in headlines)
    seconds_since_latest = max(now_ts - latest_ts, 0.0)

    sentiments = [(_sentiment_score(headline.title), headline) for headline in headlines]
    avg_sentiment = sum(score for score, _ in sentiments) / max(len(sentiments), 1)

    weighted_scores = []
    for score, headline in sentiments:
        source = headline.source.lower()
        weight = 1.0
        if any(token in source for token in HIGH_CREDIBILITY_SOURCES):
            weight = 1.25
        weighted_scores.append(score * weight)
    weighted_sentiment = (
        sum(weighted_scores) / max(len(weighted_scores), 1) if weighted_scores else 0.0
    )

    credibility_count = sum(
        1 for identity in source_counts if any(token in label.lower() for label in source_labels[identity] for token in HIGH_CREDIBILITY_SOURCES)
    )
    top_source_score = round(min(credibility_count / 3.0, 1.0), 2)

    keyword_hits = []
    for headline in headlines:
        title_lower = headline.title.lower()
        for keyword in CATALYST_KEYWORDS:
            if keyword in title_lower:
                keyword_hits.append(keyword)
    keyword_counts = Counter(keyword_hits)
    top_keywords = [keyword for keyword, _ in keyword_counts.most_common(5)]
    keyword_score = round(min(len(keyword_hits) / 5.0, 1.0), 2)

    top_headlines = [headline.title for headline in unique_headlines[:5]]
    logging.debug("[NEWS] normalized headlines total=%d unique=%d", total, unique)

    return {
        "news_total_headlines": total,
        "news_unique_headlines": unique,
        "news_replicated_headlines": replicated,
        "news_sources_count": len(source_counts),
        "news_regions_list": region_list,
        "news_region_count": len(region_list),
        "international_news_flag": international_flag,
        "news_velocity_5m": vel_5m,
        "news_velocity_10m": vel_10m,
        "news_velocity_60m": vel_60m,
        "seconds_since_latest_news": seconds_since_latest,
        "news_freshest_age_minutes": int(round(seconds_since_latest / 60.0)),
        "freshness_bucket": _freshness_bucket(seconds_since_latest),
        "news_average_sentiment": round(avg_sentiment, 3),
        "news_weighted_sentiment": round(weighted_sentiment, 3),
        "high_credibility_source_count": credibility_count,
        "high_credibility_flag": credibility_count > 0,
        "news_top_sources_list": top_sources,
        "news_top_source_credibility_score": top_source_score,
        "news_keyword_relevance_score": keyword_score,
        "news_primary_catalyst_keywords": top_keywords,
        "news_top_headlines_list": top_headlines,
    }
