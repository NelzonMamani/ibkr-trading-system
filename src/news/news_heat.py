from __future__ import annotations

import os
from typing import Any, Dict, Optional


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def compute_news_heat_score(news_context: Dict[str, Any]) -> float:
    total = _safe_float(news_context.get("news_total_headlines"), 0.0) or 0.0
    if total <= 0:
        return 0.0
    unique = _safe_float(news_context.get("news_unique_headlines"), 0.0) or 0.0
    vel10 = _safe_float(news_context.get("news_velocity_10m"), 0.0) or 0.0
    vel60 = _safe_float(news_context.get("news_velocity_60m"), 0.0) or 0.0
    freshness = _safe_float(news_context.get("news_freshest_age_minutes"), None)
    regions = _safe_float(news_context.get("news_region_count"), 0.0) or 0.0
    credibility = _safe_float(news_context.get("news_top_source_credibility_score"), 0.0) or 0.0
    sentiment = _safe_float(news_context.get("news_average_sentiment"), 0.0) or 0.0
    spike = 1.0 if news_context.get("news_spike_indicator") is True else 0.0

    total_n = min(total / 50.0, 1.0)
    unique_n = min(unique / 10.0, 1.0)
    vel10_n = min(vel10 / 10.0, 1.0)
    vel60_n = min(vel60 / 20.0, 1.0)
    regions_n = min(regions / 6.0, 1.0)
    cred_n = min(max(credibility, 0.0), 1.0)
    sentiment_n = min(max((sentiment + 1.0) / 2.0, 0.0), 1.0)
    freshness_n = 1.0
    if freshness is not None:
        freshness_n = max(0.0, 1.0 - min(freshness / 120.0, 1.0))

    heat = (
        0.20 * total_n
        + 0.15 * unique_n
        + 0.20 * vel10_n
        + 0.10 * vel60_n
        + 0.10 * regions_n
        + 0.10 * cred_n
        + 0.05 * sentiment_n
        + 0.10 * freshness_n
        + 0.05 * spike
    )
    return round(heat * 100.0, 2)


def compute_fire_indicator(news_context: Dict[str, Any]) -> bool:
    total = _safe_float(news_context.get("news_total_headlines"), 0.0) or 0.0
    vel10 = _safe_float(news_context.get("news_velocity_10m"), 0.0) or 0.0
    freshness = _safe_float(news_context.get("news_freshest_age_minutes"), None)
    spike = news_context.get("news_spike_indicator") is True
    regions = _safe_float(news_context.get("news_region_count"), 0.0) or 0.0

    max_age = int(os.environ.get("NEWS_MAX_AGE_SECONDS", "3600"))
    min_vel = int(os.environ.get("NEWS_MIN_VELOCITY_10M", "1"))
    min_regions = int(os.environ.get("NEWS_MIN_REGIONS", "1"))

    if total <= 0:
        return False
    if vel10 < min_vel:
        return False
    if freshness is None or freshness * 60 > max_age:
        return False
    if regions < min_regions:
        return False
    return spike or vel10 >= 2
