from __future__ import annotations

import datetime as dt
from typing import Any, Dict

from ib_insync import IB, Stock

from scanner.core.canonical_fields import CANONICAL_FIELDS
from scanner.engines.float_engine import get_float_shares
from scanner.engines.price_engine import get_price_truth
from scanner.engines.volume_engine import get_volume_truth
from scanner.news.news_engine import NewsEngine


def _format_float(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return str(value)


def _float_category(value: int) -> str:
    if value <= 5_000_000:
        return "LOW"
    if value <= 20_000_000:
        return "MID"
    return "HIGH"


def build_entry(
    ib: IB,
    contract: Stock,
    news_engine: NewsEngine,
    float_cache: Dict[str, Any],
) -> Dict[str, Any]:
    symbol = contract.symbol

    price_truth = get_price_truth(ib, contract)
    float_shares, float_source, float_cache_hit = get_float_shares(ib, contract, float_cache)
    volume_truth = get_volume_truth(ib, contract)
    news = news_engine.get_news(symbol)

    bid_ask_spread = price_truth.spread
    mid_price = price_truth.mid

    float_formatted = _format_float(float_shares) if float_shares else None
    float_category = _float_category(float_shares) if float_shares else None

    relative_volume = volume_truth.relative_volume
    relative_volume_category = volume_truth.relative_volume_category

    pct_change = price_truth.pct_change
    rvol = relative_volume
    news_total = news.get("news_total_headlines", 0)
    fire_indicator = "🔥" if pct_change is not None and rvol is not None and pct_change >= 10 and rvol >= 2 and news_total > 0 else ""

    entry: Dict[str, Any] = {key: None for key in CANONICAL_FIELDS}

    entry.update(
        {
            "momentum_fire_indicator": fire_indicator,
            "symbol": symbol,
            "market_session_label": "REGULAR",
            "sort_rank_by_gap_desc": None,
            "previous_close_price": price_truth.prev_close,
            "session_open_price": price_truth.session_open,
            "overnight_gap_percentage": price_truth.gap_pct,
            "last_trade_price": price_truth.last,
            "current_percentage_change_from_prior_close": price_truth.pct_change,
            "bid_price": price_truth.bid,
            "ask_price": price_truth.ask,
            "bid_ask_spread": bid_ask_spread,
            "mid_price": mid_price,
            "vwap_price": price_truth.vwap,
            "day_high_price": price_truth.day_high,
            "day_low_price": price_truth.day_low,
            "intraday_range_percentage": price_truth.intraday_range_pct,
            "price_data_type_label": price_truth.data_type_label,
            "price_truth_source_label": price_truth.truth_source_label,
            "daily_bars_count": price_truth.daily_bars_count,
            "float_shares_raw": float_shares,
            "float_shares_formatted": float_formatted,
            "float_category": float_category,
            "float_shares_source": float_source,
            "float_cache_hit": float_cache_hit,
            "current_intraday_volume": volume_truth.current_intraday_volume,
            "current_volume_source_label": volume_truth.current_volume_source_label,
            "average_daily_volume_20d": volume_truth.average_daily_volume_20d,
            "average_daily_volume_window_days": volume_truth.average_daily_volume_window_days,
            "relative_volume": relative_volume,
            "relative_volume_category": relative_volume_category,
            "volume_velocity_5m": volume_truth.volume_velocity_5m,
            "volume_velocity_15m": volume_truth.volume_velocity_15m,
            "volume_data_quality_flag": volume_truth.volume_data_quality_flag,
            "news_total_headlines": news.get("news_total_headlines"),
            "news_unique_headlines": news.get("news_unique_headlines"),
            "news_replicated_headlines": news.get("news_replicated_headlines"),
            "news_velocity_10m": news.get("news_velocity_10m"),
            "news_velocity_60m": news.get("news_velocity_60m"),
            "news_spike_indicator": news.get("news_spike_indicator"),
            "news_freshest_age_minutes": news.get("news_freshest_age_minutes"),
            "news_regions_list": news.get("news_regions_list"),
            "news_region_count": news.get("news_region_count"),
            "news_top_sources_list": news.get("news_top_sources_list"),
            "news_top_source_credibility_score": news.get("news_top_source_credibility_score"),
            "news_average_sentiment": None,
            "news_keyword_relevance_score": None,
            "news_primary_catalyst_keywords": None,
            "news_top_headlines_list": news.get("news_top_headlines_list"),
            "composite_momentum_score": None,
            "score_components_breakdown": None,
            "attention_tier": None,
            "trade_suggestion_label": None,
            "trade_suggestion_rationale": None,
        }
    )

    entry["market_session_label"] = _session_label()

    return entry


def _session_label() -> str:
    now = dt.datetime.utcnow().time()
    if now < dt.time(13, 30):
        return "PRE"
    if now > dt.time(20, 0):
        return "POST"
    return "REGULAR"
