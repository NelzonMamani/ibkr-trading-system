import inspect

from src.news.news_heat import compute_fire_indicator
from src.scanner.contracts import (
    CANONICAL_FIELDS,
    STOCK_SELECTION_FIELD_ORDER,
    ScannerRow54,
    stock_selection_policy_fields,
    validate_row,
)


def _blank_row() -> ScannerRow54:
    return ScannerRow54(
        momentum_fire_indicator=None,
        symbol=None,
        market_session_label=None,
        sort_rank_by_gap_desc=None,
        previous_close_price=None,
        session_open_price=None,
        overnight_gap_percentage=None,
        last_trade_price=None,
        current_percentage_change_from_prior_close=None,
        bid_price=None,
        ask_price=None,
        bid_ask_spread=None,
        mid_price=None,
        vwap_price=None,
        day_high_price=None,
        day_low_price=None,
        intraday_range_percentage=None,
        price_data_type_label=None,
        price_truth_source_label=None,
        daily_bars_count=None,
        float_shares_raw=None,
        float_shares_formatted=None,
        float_category=None,
        float_shares_source=None,
        float_cache_hit=None,
        current_intraday_volume=None,
        current_volume_source_label=None,
        average_daily_volume_20d=None,
        average_daily_volume_window_days=None,
        relative_volume=None,
        relative_volume_category=None,
        volume_velocity_5m=None,
        volume_velocity_15m=None,
        volume_data_quality_flag=None,
        news_total_headlines=None,
        news_unique_headlines=None,
        news_replicated_headlines=None,
        news_velocity_10m=None,
        news_velocity_60m=None,
        news_spike_indicator=None,
        news_freshest_age_minutes=None,
        news_regions_list=None,
        news_region_count=None,
        news_top_sources_list=None,
        news_top_source_credibility_score=None,
        news_average_sentiment=None,
        news_keyword_relevance_score=None,
        news_primary_catalyst_keywords=None,
        news_top_headlines_list=None,
        composite_momentum_score=None,
        composite_news_score=None,
        strategy_trade_bias=None,
        scanner_version=None,
        debug_notes=None,
    )


def test_canonical_order_has_54_fields():
    assert len(CANONICAL_FIELDS) == 54


def test_validate_row_flags_non_allowed_na_fields():
    row = _blank_row()
    _, non_allowed, complete, _ = validate_row(row)
    assert complete is False
    assert set(non_allowed) == {
        "momentum_fire_indicator",
        "symbol",
        "market_session_label",
        "sort_rank_by_gap_desc",
        "scanner_version",
    }


def test_fire_indicator_signature_only_accepts_news_context():
    signature = inspect.signature(compute_fire_indicator)
    assert len(signature.parameters) == 1


def test_stock_selection_policy_fields_unique_and_ordered():
    fields = stock_selection_policy_fields()
    assert fields == STOCK_SELECTION_FIELD_ORDER
    assert len(fields) == len(set(fields))
