"""Filtering rules for scanner watchlists."""
from __future__ import annotations

import os
from typing import Optional


def _safe_float(value, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


ROSS_5_PILLARS = {
    "min_pct_change": float(os.environ.get("ROSS_MIN_PCT_CHANGE", "10")),
    "min_price": float(os.environ.get("ROSS_MIN_PRICE", "1")),
    "max_price": float(os.environ.get("ROSS_MAX_PRICE", "20")),
    "max_float": int(os.environ.get("ROSS_MAX_FLOAT", "20000000")),
    "min_rvol": float(os.environ.get("ROSS_MIN_RVOL", "5")),
    "min_volume": int(os.environ.get("ROSS_MIN_VOLUME", "1000000")),
    "require_news": os.environ.get("ROSS_REQUIRE_NEWS", "0").strip().lower() in {"1", "true", "yes"},
}


def passes_ross_5_pillars(entry: dict) -> bool:
    pct = _safe_float(entry.get("current_percentage_change_from_prior_close"), None)
    px = _safe_float(entry.get("last_trade_price"), None)
    flt = entry.get("float_shares_raw")
    rvol = _safe_float(entry.get("relative_volume"), None)
    vol = _safe_float(entry.get("current_intraday_volume"), None)
    news_total = _safe_float(entry.get("news_total_headlines"), 0.0) or 0.0

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
    if vol < ROSS_5_PILLARS["min_volume"]:
        return False
    if ROSS_5_PILLARS["require_news"] and news_total <= 0:
        return False
    return True


def passes_catalyst_eligibility(entry: dict) -> bool:
    total = _safe_float(entry.get("news_total_headlines"), 0.0) or 0.0
    vel10 = _safe_float(entry.get("news_velocity_10m"), 0.0) or 0.0
    freshest = _safe_float(entry.get("news_freshest_age_minutes"), None)
    spike = entry.get("news_spike_indicator") is True
    region_count = _safe_float(entry.get("news_region_count"), 0.0) or 0.0

    if total <= 0:
        return False
    if vel10 < 1:
        return False
    if freshest is None or freshest > 60:
        return False
    if not (spike or vel10 >= 2):
        return False
    if region_count < 1:
        return False
    return True
