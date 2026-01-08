from __future__ import annotations

from typing import Any, Dict, Iterable, List

from scanner.core.canonical_fields import CANONICAL_FIELDS


def print_master(entries: Iterable[Dict[str, Any]]) -> None:
    for entry in entries:
        fire = entry.get("momentum_fire_indicator", "")
        symbol = entry.get("symbol")
        pct = entry.get("current_percentage_change_from_prior_close")
        gap = entry.get("overnight_gap_percentage")
        px = entry.get("last_trade_price")
        flt = entry.get("float_shares_formatted")
        rvol = entry.get("relative_volume")
        news_total = entry.get("news_total_headlines")
        header = (
            f"{fire} {symbol} | %Chg:{pct} | Gap:{gap} | Px:{px} | "
            f"Float:{flt} | RVOL:{rvol} | News:{news_total}"
        )
        print(header)

        for key in CANONICAL_FIELDS:
            value = entry.get(key)
            if key == "news_top_headlines_list":
                print(f"{key}:")
                _print_headlines(value)
            else:
                print(f"{key}: {value}")
        print("-")


def print_watchlist(entries: List[Dict[str, Any]]) -> None:
    print("ROSS WATCHLIST (PHASE 24)")
    sorted_entries = sorted(
        entries,
        key=lambda item: item.get("current_percentage_change_from_prior_close") or 0,
        reverse=True,
    )
    for entry in sorted_entries:
        symbol = entry.get("symbol")
        pct = entry.get("current_percentage_change_from_prior_close")
        price = entry.get("last_trade_price")
        flt = entry.get("float_shares_formatted")
        rvol = entry.get("relative_volume")
        news_total = entry.get("news_total_headlines")
        vel10 = entry.get("news_velocity_10m")
        regions = entry.get("news_regions_list")
        headlines = entry.get("news_top_headlines_list") or []
        url = headlines[0].get("url") if headlines else None
        line = (
            f"{symbol} | %Chg:{pct} | Px:{price} | Float:{flt} | "
            f"RVOL:{rvol} | News:{news_total} | Vel10:{vel10} | Regions:{regions} | {url}"
        )
        print(line)


def _print_headlines(headlines: Any) -> None:
    if not headlines:
        print("  (none)")
        return
    for item in headlines:
        title = item.get("title")
        url = item.get("url")
        source = item.get("source")
        age = item.get("age_minutes")
        region = item.get("region")
        print(f"  - {title} ({source}, {age}m, {region})")
        if url:
            print(f"    {url}")
