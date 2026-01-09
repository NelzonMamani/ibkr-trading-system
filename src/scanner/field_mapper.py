from __future__ import annotations

from typing import Any, Dict, Optional

from news.news_heat import compute_fire_indicator, compute_news_heat_score

from .contracts import ScannerRow54

FIELD_SOURCES: Dict[str, str] = {
    "momentum_fire_indicator": "news.news_heat.compute_fire_indicator",
    "symbol": "scanner_runner (IBKR contract)",
    "market_session_label": "scanner_master_v2026_01_06_07.market_session_label_utc",
    "sort_rank_by_gap_desc": "scanner_runner sort",
    "previous_close_price": "scanner_master_v2026_01_06_07.get_price_truth",
    "session_open_price": "scanner_master_v2026_01_06_07.get_price_truth",
    "overnight_gap_percentage": "scanner_master_v2026_01_06_07.get_price_truth",
    "last_trade_price": "scanner_master_v2026_01_06_07.get_price_truth",
    "current_percentage_change_from_prior_close": "scanner_master_v2026_01_06_07.get_price_truth",
    "bid_price": "scanner_master_v2026_01_06_07.get_price_truth",
    "ask_price": "scanner_master_v2026_01_06_07.get_price_truth",
    "bid_ask_spread": "scanner_master_v2026_01_06_07.get_price_truth",
    "mid_price": "scanner_master_v2026_01_06_07.get_price_truth",
    "vwap_price": "scanner_master_v2026_01_06_07.get_price_truth",
    "day_high_price": "scanner_master_v2026_01_06_07.get_price_truth",
    "day_low_price": "scanner_master_v2026_01_06_07.get_price_truth",
    "intraday_range_percentage": "scanner_master_v2026_01_06_07.get_price_truth",
    "price_data_type_label": "scanner_master_v2026_01_06_07.get_price_truth",
    "price_truth_source_label": "scanner_master_v2026_01_06_07.get_price_truth",
    "daily_bars_count": "scanner_master_v2026_01_06_07.get_price_truth",
    "float_shares_raw": "scanner_master_v2026_01_06_07.get_float_shares",
    "float_shares_formatted": "scanner_master_v2026_01_06_07.fmt_float_human",
    "float_category": "scanner_master_v2026_01_06_07.categorize_float",
    "float_shares_source": "scanner_master_v2026_01_06_07.get_float_shares",
    "float_cache_hit": "scanner_master_v2026_01_06_07.get_float_shares",
    "current_intraday_volume": "scanner_master_v2026_01_06_07.get_volume_truth",
    "current_volume_source_label": "scanner_master_v2026_01_06_07.get_volume_truth",
    "average_daily_volume_20d": "scanner_master_v2026_01_06_07.get_volume_truth",
    "average_daily_volume_window_days": "scanner_master_v2026_01_06_07.get_volume_truth",
    "relative_volume": "scanner_master_v2026_01_06_07.get_volume_truth",
    "relative_volume_category": "scanner_master_v2026_01_06_07.get_volume_truth",
    "volume_velocity_5m": "scanner_master_v2026_01_06_07.get_volume_truth",
    "volume_velocity_15m": "scanner_master_v2026_01_06_07.get_volume_truth",
    "volume_data_quality_flag": "scanner_master_v2026_01_06_07.get_volume_truth",
    "news_total_headlines": "scanner.news_engine.get_news_truth",
    "news_unique_headlines": "scanner.news_engine.get_news_truth",
    "news_replicated_headlines": "scanner.news_engine.get_news_truth",
    "news_velocity_10m": "scanner.news_engine.get_news_truth",
    "news_velocity_60m": "scanner.news_engine.get_news_truth",
    "news_spike_indicator": "scanner.news_engine.get_news_truth",
    "news_freshest_age_minutes": "scanner.news_engine.get_news_truth",
    "news_regions_list": "scanner.news_engine.get_news_truth",
    "news_region_count": "scanner.news_engine.get_news_truth",
    "news_top_sources_list": "scanner.news_engine.get_news_truth",
    "news_top_source_credibility_score": "scanner.news_engine.get_news_truth",
    "news_average_sentiment": "scanner.news_engine.get_news_truth",
    "news_keyword_relevance_score": "scanner.news_engine.get_news_truth",
    "news_primary_catalyst_keywords": "scanner.news_engine.get_news_truth",
    "news_top_headlines_list": "scanner.news_engine.get_news_truth",
    "composite_momentum_score": "scanner.field_mapper._compute_scores",
    "score_components_breakdown": "scanner.field_mapper._compute_scores",
    "attention_tier": "scanner.field_mapper._compute_scores",
    "trade_suggestion_label": "scanner.field_mapper._compute_scores",
    "trade_suggestion_rationale": "scanner.field_mapper._compute_scores",
}


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _compute_scores(symbol_context: Dict[str, Any], news_context: Dict[str, Any]) -> Dict[str, Any]:
    pct = _safe_float(symbol_context.get("current_percentage_change_from_prior_close"), None)
    gap = _safe_float(symbol_context.get("overnight_gap_percentage"), None)
    rvol = _safe_float(symbol_context.get("relative_volume"), None)
    volume = _safe_float(symbol_context.get("current_intraday_volume"), None)
    news_heat = compute_news_heat_score(news_context)

    if pct is None or rvol is None:
        return {
            "composite_momentum_score": None,
            "score_components_breakdown": None,
            "attention_tier": None,
            "trade_suggestion_label": None,
            "trade_suggestion_rationale": None,
        }

    pct_n = min(max((pct + 5.0) / 50.0, 0.0), 2.0)
    gap_n = 0.0 if gap is None else min(max((gap + 5.0) / 50.0, 0.0), 2.0)
    rvol_n = min(max(rvol / 10.0, 0.0), 2.0)
    vol_n = 0.0 if volume is None else min(max(volume / 5_000_000.0, 0.0), 2.0)
    news_n = min(news_heat / 100.0, 1.0)

    score = (
        0.30 * pct_n
        + 0.20 * gap_n
        + 0.25 * rvol_n
        + 0.15 * vol_n
        + 0.10 * news_n
    )
    score_0_100 = round(min(score, 1.0) * 100.0, 2)

    if score_0_100 >= 70:
        tier = "A"
        label = "HOT"
        rationale = "High momentum with supportive volume and news context."
    elif score_0_100 >= 50:
        tier = "B"
        label = "WATCH"
        rationale = "Moderate momentum; monitor for continuation."
    else:
        tier = "C"
        label = "PASS"
        rationale = "Below threshold momentum or volume conditions."

    breakdown = {
        "pct_change_norm": round(min(pct_n, 1.0), 3),
        "gap_norm": round(min(gap_n, 1.0), 3),
        "rvol_norm": round(min(rvol_n, 1.0), 3),
        "volume_norm": round(min(vol_n, 1.0), 3),
        "news_heat_score": news_heat,
    }
    return {
        "composite_momentum_score": score_0_100,
        "score_components_breakdown": breakdown,
        "attention_tier": tier,
        "trade_suggestion_label": label,
        "trade_suggestion_rationale": rationale,
    }


def build_scanner_row54(
    symbol_context: Dict[str, Any],
    news_context: Dict[str, Any],
    meta_context: Dict[str, Any],
    diagnostics: Dict[str, Any],
) -> ScannerRow54:
    fire_on = compute_fire_indicator(news_context)
    scores = _compute_scores(symbol_context, news_context)
    fire_indicator = "🔥" if fire_on else ""

    return ScannerRow54(
        momentum_fire_indicator=fire_indicator,
        symbol=symbol_context.get("symbol"),
        market_session_label=symbol_context.get("market_session_label"),
        sort_rank_by_gap_desc=symbol_context.get("sort_rank_by_gap_desc"),
        previous_close_price=symbol_context.get("previous_close_price"),
        session_open_price=symbol_context.get("session_open_price"),
        overnight_gap_percentage=symbol_context.get("overnight_gap_percentage"),
        last_trade_price=symbol_context.get("last_trade_price"),
        current_percentage_change_from_prior_close=symbol_context.get(
            "current_percentage_change_from_prior_close"
        ),
        bid_price=symbol_context.get("bid_price"),
        ask_price=symbol_context.get("ask_price"),
        bid_ask_spread=symbol_context.get("bid_ask_spread"),
        mid_price=symbol_context.get("mid_price"),
        vwap_price=symbol_context.get("vwap_price"),
        day_high_price=symbol_context.get("day_high_price"),
        day_low_price=symbol_context.get("day_low_price"),
        intraday_range_percentage=symbol_context.get("intraday_range_percentage"),
        price_data_type_label=symbol_context.get("price_data_type_label"),
        price_truth_source_label=symbol_context.get("price_truth_source_label"),
        daily_bars_count=symbol_context.get("daily_bars_count"),
        float_shares_raw=symbol_context.get("float_shares_raw"),
        float_shares_formatted=symbol_context.get("float_shares_formatted"),
        float_category=symbol_context.get("float_category"),
        float_shares_source=symbol_context.get("float_shares_source"),
        float_cache_hit=symbol_context.get("float_cache_hit"),
        current_intraday_volume=symbol_context.get("current_intraday_volume"),
        current_volume_source_label=symbol_context.get("current_volume_source_label"),
        average_daily_volume_20d=symbol_context.get("average_daily_volume_20d"),
        average_daily_volume_window_days=symbol_context.get("average_daily_volume_window_days"),
        relative_volume=symbol_context.get("relative_volume"),
        relative_volume_category=symbol_context.get("relative_volume_category"),
        volume_velocity_5m=symbol_context.get("volume_velocity_5m"),
        volume_velocity_15m=symbol_context.get("volume_velocity_15m"),
        volume_data_quality_flag=symbol_context.get("volume_data_quality_flag"),
        news_total_headlines=news_context.get("news_total_headlines"),
        news_unique_headlines=news_context.get("news_unique_headlines"),
        news_replicated_headlines=news_context.get("news_replicated_headlines"),
        news_velocity_10m=news_context.get("news_velocity_10m"),
        news_velocity_60m=news_context.get("news_velocity_60m"),
        news_spike_indicator=news_context.get("news_spike_indicator"),
        news_freshest_age_minutes=news_context.get("news_freshest_age_minutes"),
        news_regions_list=news_context.get("news_regions_list"),
        news_region_count=news_context.get("news_region_count"),
        news_top_sources_list=news_context.get("news_top_sources_list"),
        news_top_source_credibility_score=news_context.get("news_top_source_credibility_score"),
        news_average_sentiment=news_context.get("news_average_sentiment"),
        news_keyword_relevance_score=news_context.get("news_keyword_relevance_score"),
        news_primary_catalyst_keywords=news_context.get("news_primary_catalyst_keywords"),
        news_top_headlines_list=news_context.get("news_top_headlines_list"),
        composite_momentum_score=scores.get("composite_momentum_score"),
        score_components_breakdown=scores.get("score_components_breakdown"),
        attention_tier=scores.get("attention_tier"),
        trade_suggestion_label=scores.get("trade_suggestion_label"),
        trade_suggestion_rationale=scores.get("trade_suggestion_rationale"),
    )

