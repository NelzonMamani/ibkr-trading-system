import os
from typing import Any, Dict


REQUIRE_NEWS = os.environ.get("ROSS_REQUIRE_NEWS", "false").lower() == "true"


def passes_ross_5_pillars(entry: Dict[str, Any]) -> bool:
    pct_change = entry.get("current_percentage_change_from_prior_close")
    price = entry.get("last_trade_price")
    float_shares = entry.get("float_shares_raw")
    rvol = entry.get("relative_volume")
    volume = entry.get("current_intraday_volume")
    news_total = entry.get("news_total_headlines", 0)

    if pct_change is None or pct_change < 10:
        return False
    if price is None or price < 1 or price > 20:
        return False
    if float_shares is None or float_shares > 20_000_000:
        return False
    if rvol is None or rvol < 5:
        return False
    if volume is None or volume < 1_000_000:
        return False
    if REQUIRE_NEWS and news_total <= 0:
        return False
    return True


def passes_catalyst_eligibility(entry: Dict[str, Any]) -> bool:
    total = entry.get("news_total_headlines", 0)
    vel10 = entry.get("news_velocity_10m", 0)
    vel60 = entry.get("news_velocity_60m", 0)
    freshest = entry.get("news_freshest_age_minutes")
    spike = entry.get("news_spike_indicator", False)
    region_count = entry.get("news_region_count", 0)

    if total <= 0:
        return False
    if vel10 < 1:
        return False
    if freshest is None or freshest > 60:
        return False
    if not (spike or vel10 >= 3 or (vel10 >= 1 and vel60 >= 3)):
        return False
    if region_count < 1:
        return False
    return True
