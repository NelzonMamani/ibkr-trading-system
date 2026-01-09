"""Filtering rules for scanner watchlists."""
from __future__ import annotations

import os
from typing import Any, Optional


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _get_value(entry: Any, key: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


ROSS_5_PILLARS = {
    "min_pct_change": float(os.environ.get("ROSS_MIN_PCT_CHANGE", "10")),
    "min_price": float(os.environ.get("ROSS_MIN_PRICE", "1")),
    "max_price": float(os.environ.get("ROSS_MAX_PRICE", "20")),
    "max_float": int(os.environ.get("ROSS_MAX_FLOAT", "20000000")),
    "min_rvol": float(os.environ.get("ROSS_MIN_RVOL", "5")),
    "min_volume": int(os.environ.get("ROSS_MIN_VOLUME", "1000000")),
    "min_premarket_volume": int(os.environ.get("ROSS_MIN_PREMARKET_VOLUME", "100000")),
    "require_news": os.environ.get("ROSS_REQUIRE_NEWS", "1").strip().lower() in {"1", "true", "yes"},
}
NEWS_GATES = {
    "max_age_seconds": int(os.environ.get("NEWS_MAX_AGE_SECONDS", "3600")),
    "min_velocity_10m": int(os.environ.get("NEWS_MIN_VELOCITY_10M", "1")),
    "min_regions": int(os.environ.get("NEWS_MIN_REGIONS", "1")),
}


def passes_ross_5_pillars(entry: Any) -> bool:
    pct = _safe_float(_get_value(entry, "current_percentage_change_from_prior_close"), None)
    px = _safe_float(_get_value(entry, "last_trade_price"), None)
    flt = _get_value(entry, "float_shares_raw")
    rvol = _safe_float(_get_value(entry, "relative_volume"), None)
    vol = _safe_float(_get_value(entry, "current_intraday_volume"), None)
    news_total = _safe_float(_get_value(entry, "news_total_headlines"), 0.0) or 0.0
    session_label = (_get_value(entry, "market_session_label") or "").upper()

    if pct is None or px is None or rvol is None or vol is None:
        return False
    if pct < ROSS_5_PILLARS["min_pct_change"]:
        return False
    if not (ROSS_5_PILLARS["min_price"] <= px <= ROSS_5_PILLARS["max_price"]):
        return False
    if flt is None or flt <= 0 or flt > ROSS_5_PILLARS["max_float"]:
        return False
    if rvol < ROSS_5_PILLARS["min_rvol"]:
        return False
    if session_label in {"PRE", "OVN"}:
        if vol < ROSS_5_PILLARS["min_premarket_volume"]:
            return False
    elif vol < ROSS_5_PILLARS["min_volume"]:
        return False
    if ROSS_5_PILLARS["require_news"] and news_total <= 0:
        return False
    return True


def passes_catalyst_eligibility(entry: Any) -> bool:
    total = _safe_float(_get_value(entry, "news_total_headlines"), 0.0) or 0.0
    vel10 = _safe_float(_get_value(entry, "news_velocity_10m"), 0.0) or 0.0
    freshest = _safe_float(_get_value(entry, "news_freshest_age_minutes"), None)
    spike = _get_value(entry, "news_spike_indicator") is True
    region_count = _safe_float(_get_value(entry, "news_region_count"), 0.0) or 0.0

    if total <= 0:
        return False
    if vel10 < NEWS_GATES["min_velocity_10m"]:
        return False
    if freshest is None or freshest * 60 > NEWS_GATES["max_age_seconds"]:
        return False
    if not (spike or vel10 >= 2):
        return False
    if region_count < NEWS_GATES["min_regions"]:
        return False
    return True
