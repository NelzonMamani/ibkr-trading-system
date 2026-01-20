from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.config.config_resolver import get_config
from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec

SCANNER_VERSION = "v2026-01-04-11"
SCANNER_GIT_SHA = str(get_config("SCANNER_GIT_SHA") or "")

CANONICAL_FIELD_ORDER: List[str] = [
    "momentum_fire_indicator",
    "symbol",
    "market_session_label",
    "sort_rank_by_gap_desc",
    "previous_close_price",
    "session_open_price",
    "overnight_gap_percentage",
    "last_trade_price",
    "current_percentage_change_from_prior_close",
    "bid_price",
    "ask_price",
    "bid_ask_spread",
    "mid_price",
    "vwap_price",
    "day_high_price",
    "day_low_price",
    "intraday_range_percentage",
    "price_data_type_label",
    "price_truth_source_label",
    "daily_bars_count",
    "float_shares_raw",
    "float_shares_formatted",
    "float_category",
    "float_shares_source",
    "float_cache_hit",
    "current_intraday_volume",
    "current_volume_source_label",
    "average_daily_volume_20d",
    "average_daily_volume_window_days",
    "relative_volume",
    "relative_volume_category",
    "volume_velocity_5m",
    "volume_velocity_15m",
    "volume_data_quality_flag",
    "news_total_headlines",
    "news_unique_headlines",
    "news_replicated_headlines",
    "news_velocity_10m",
    "news_velocity_60m",
    "news_spike_indicator",
    "news_freshest_age_minutes",
    "news_regions_list",
    "news_region_count",
    "news_top_sources_list",
    "news_top_source_credibility_score",
    "news_average_sentiment",
    "news_keyword_relevance_score",
    "news_primary_catalyst_keywords",
    "news_top_headlines_list",
    "composite_momentum_score",
    "composite_news_score",
    "strategy_trade_bias",
    "scanner_version",
    "debug_notes",
]
CANONICAL_FIELDS = CANONICAL_FIELD_ORDER

ALLOWED_NA: Dict[str, bool] = {
    "momentum_fire_indicator": False,
    "symbol": False,
    "market_session_label": False,
    "sort_rank_by_gap_desc": False,
    "previous_close_price": True,
    "session_open_price": True,
    "overnight_gap_percentage": True,
    "last_trade_price": True,
    "current_percentage_change_from_prior_close": True,
    "bid_price": True,
    "ask_price": True,
    "bid_ask_spread": True,
    "mid_price": True,
    "vwap_price": True,
    "day_high_price": True,
    "day_low_price": True,
    "intraday_range_percentage": True,
    "price_data_type_label": True,
    "price_truth_source_label": True,
    "daily_bars_count": True,
    "float_shares_raw": True,
    "float_shares_formatted": True,
    "float_category": True,
    "float_shares_source": True,
    "float_cache_hit": True,
    "current_intraday_volume": True,
    "current_volume_source_label": True,
    "average_daily_volume_20d": True,
    "average_daily_volume_window_days": True,
    "relative_volume": True,
    "relative_volume_category": True,
    "volume_velocity_5m": True,
    "volume_velocity_15m": True,
    "volume_data_quality_flag": True,
    "news_total_headlines": True,
    "news_unique_headlines": True,
    "news_replicated_headlines": True,
    "news_velocity_10m": True,
    "news_velocity_60m": True,
    "news_spike_indicator": True,
    "news_freshest_age_minutes": True,
    "news_regions_list": True,
    "news_region_count": True,
    "news_top_sources_list": True,
    "news_top_source_credibility_score": True,
    "news_average_sentiment": True,
    "news_keyword_relevance_score": True,
    "news_primary_catalyst_keywords": True,
    "news_top_headlines_list": True,
    "composite_momentum_score": True,
    "composite_news_score": True,
    "strategy_trade_bias": True,
    "scanner_version": False,
    "debug_notes": True,
}


@dataclass
class ScannerRow54:
    momentum_fire_indicator: Optional[str]
    symbol: Optional[str]
    market_session_label: Optional[str]
    sort_rank_by_gap_desc: Optional[int]
    previous_close_price: Optional[float]
    session_open_price: Optional[float]
    overnight_gap_percentage: Optional[float]
    last_trade_price: Optional[float]
    current_percentage_change_from_prior_close: Optional[float]
    bid_price: Optional[float]
    ask_price: Optional[float]
    bid_ask_spread: Optional[float]
    mid_price: Optional[float]
    vwap_price: Optional[float]
    day_high_price: Optional[float]
    day_low_price: Optional[float]
    intraday_range_percentage: Optional[float]
    price_data_type_label: Optional[str]
    price_truth_source_label: Optional[str]
    daily_bars_count: Optional[int]
    float_shares_raw: Optional[int]
    float_shares_formatted: Optional[str]
    float_category: Optional[str]
    float_shares_source: Optional[str]
    float_cache_hit: Optional[bool]
    current_intraday_volume: Optional[int]
    current_volume_source_label: Optional[str]
    average_daily_volume_20d: Optional[int]
    average_daily_volume_window_days: Optional[int]
    relative_volume: Optional[float]
    relative_volume_category: Optional[str]
    volume_velocity_5m: Optional[int]
    volume_velocity_15m: Optional[int]
    volume_data_quality_flag: Optional[str]
    news_total_headlines: Optional[int]
    news_unique_headlines: Optional[int]
    news_replicated_headlines: Optional[int]
    news_velocity_10m: Optional[int]
    news_velocity_60m: Optional[int]
    news_spike_indicator: Optional[bool]
    news_freshest_age_minutes: Optional[int]
    news_regions_list: Optional[List[str]]
    news_region_count: Optional[int]
    news_top_sources_list: Optional[List[str]]
    news_top_source_credibility_score: Optional[float]
    news_average_sentiment: Optional[float]
    news_keyword_relevance_score: Optional[float]
    news_primary_catalyst_keywords: Optional[List[str]]
    news_top_headlines_list: Optional[List[Any]]
    composite_momentum_score: Optional[float]
    composite_news_score: Optional[float]
    strategy_trade_bias: Optional[str]
    scanner_version: Optional[str]
    debug_notes: Optional[str]


StockSelectionPolicy = StockSelectionSpec

STOCK_SELECTION_FIELD_ORDER: List[str] = [
    "policy_name",
    "universe_source",
    "exchange_allowlist",
    "top_gainers_n",
    "watchlist_limit_k",
    "focus_limit_m",
    "price_min",
    "price_max",
    "gap_min_pct",
    "gap_max_pct",
    "rvol_min",
    "float_max_millions",
    "min_volume",
    "min_premarket_volume",
    "liquidity_min_dollar_volume",
    "spread_max_pct",
    "require_catalyst",
    "allow_halts",
    "allow_ssr",
    "data_quality_require_price",
    "data_quality_require_bid_ask",
    "max_symbols_per_cycle",
    "session_allowlist",
    "ranking_intent",
    "soft_preferences",
]


def policy_from_config() -> StockSelectionPolicy:
    base = StockSelectionPolicy()
    return replace(
        base,
        policy_name="CONFIG_DEFAULTS",
        price_min=float(get_config("ROSS_MIN_PRICE")),
        price_max=float(get_config("ROSS_MAX_PRICE")),
        gap_min_pct=float(get_config("ROSS_MIN_PCT_CHANGE")),
        gap_max_pct=None,
        rvol_min=float(get_config("ROSS_MIN_RVOL")),
        float_max_millions=float(get_config("ROSS_MAX_FLOAT")) / 1_000_000.0,
        liquidity_min_dollar_volume=None,
        min_volume=int(get_config("ROSS_MIN_VOLUME")),
        min_premarket_volume=int(get_config("ROSS_MIN_PREMARKET_VOLUME")),
        spread_max_pct=None,
        require_catalyst=bool(get_config("ROSS_REQUIRE_NEWS")),
        allow_halts=False,
        allow_ssr=True,
        data_quality_require_price=True,
        data_quality_require_bid_ask=False,
        watchlist_limit_k=int(get_config("SCANNER_WATCHLIST_LIMIT")),
        focus_limit_m=5,
        top_gainers_n=int(get_config("SCANNER_TOP_GAINERS_COUNT")),
        max_symbols_per_cycle=int(get_config("IBKR_MAX_SYMBOLS_PER_CYCLE")),
        session_allowlist=("PRE", "REG", "AFTER"),
    )


def stock_selection_policy_fields() -> List[str]:
    return [field.name for field in fields(StockSelectionPolicy)]


def validate_row(
    row: ScannerRow54,
) -> Tuple[List[str], List[str], bool, float]:
    missing_data_fields: List[str] = []
    non_allowed_na_fields: List[str] = []
    for field_name in CANONICAL_FIELDS:
        value = getattr(row, field_name, None)
        if value is None:
            missing_data_fields.append(field_name)
            if not ALLOWED_NA.get(field_name, True):
                non_allowed_na_fields.append(field_name)
    completeness_flag = not non_allowed_na_fields
    data_integrity_score = max(
        0.0,
        100.0 - (len(missing_data_fields) * 2.0) - (len(non_allowed_na_fields) * 5.0),
    )
    return missing_data_fields, non_allowed_na_fields, completeness_flag, round(data_integrity_score, 2)
