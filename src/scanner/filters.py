"""Filtering rules for scanner watchlists."""
from __future__ import annotations

from typing import Any, Optional

from src.config.config_resolver import get_config


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


def _ross_5_pillars() -> dict:
    return {
        "min_pct_change": float(get_config("ROSS_MIN_PCT_CHANGE")),
        "min_price": float(get_config("ROSS_MIN_PRICE")),
        "max_price": float(get_config("ROSS_MAX_PRICE")),
        "max_float": int(get_config("ROSS_MAX_FLOAT")),
        "min_rvol": float(get_config("ROSS_MIN_RVOL")),
        "min_volume": int(get_config("ROSS_MIN_VOLUME")),
        "min_premarket_volume": int(get_config("ROSS_MIN_PREMARKET_VOLUME")),
        "require_news": bool(get_config("ROSS_REQUIRE_NEWS")),
    }


def _news_gates() -> dict:
    return {
        "max_age_seconds": int(get_config("NEWS_MAX_AGE_SECONDS")),
        "min_velocity_10m": int(get_config("NEWS_MIN_VELOCITY_10M")),
        "min_regions": int(get_config("NEWS_MIN_REGIONS")),
    }


def passes_ross_5_pillars(entry: Any) -> bool:
    pillars = _ross_5_pillars()
    pct = _safe_float(_get_value(entry, "current_percentage_change_from_prior_close"), None)
    px = _safe_float(_get_value(entry, "last_trade_price"), None)
    flt = _get_value(entry, "float_shares_raw")
    rvol = _safe_float(_get_value(entry, "relative_volume"), None)
    vol = _safe_float(_get_value(entry, "current_intraday_volume"), None)
    news_total = _safe_float(_get_value(entry, "news_total_headlines"), 0.0) or 0.0
    session_label = (_get_value(entry, "market_session_label") or "").upper()

    if pct is None or px is None or rvol is None or vol is None:
        return False
    if pct < pillars["min_pct_change"]:
        return False
    if not (pillars["min_price"] <= px <= pillars["max_price"]):
        return False
    if flt is None or flt <= 0 or flt > pillars["max_float"]:
        return False
    if rvol < pillars["min_rvol"]:
        return False
    if session_label in {"PRE", "OVN"}:
        if vol < pillars["min_premarket_volume"]:
            return False
    elif vol < pillars["min_volume"]:
        return False
    if pillars["require_news"] and news_total <= 0:
        return False
    return True


def passes_catalyst_eligibility(entry: Any) -> bool:
    gates = _news_gates()
    total = _safe_float(_get_value(entry, "news_total_headlines"), 0.0) or 0.0
    vel10 = _safe_float(_get_value(entry, "news_velocity_10m"), 0.0) or 0.0
    freshest = _safe_float(_get_value(entry, "news_freshest_age_minutes"), None)
    spike = _get_value(entry, "news_spike_indicator") is True
    region_count = _safe_float(_get_value(entry, "news_region_count"), 0.0) or 0.0

    if total <= 0:
        return False
    if vel10 < gates["min_velocity_10m"]:
        return False
    if freshest is None or freshest * 60 > gates["max_age_seconds"]:
        return False
    if not (spike or vel10 >= 2):
        return False
    if region_count < gates["min_regions"]:
        return False
    return True
