
from datetime import datetime

CANONICAL_FIELDS = [
    "momentum_fire_indicator","symbol","market_session_label","sort_rank_by_gap_desc",
    "previous_close_price","session_open_price","overnight_gap_percentage",
    "last_trade_price","current_percentage_change_from_prior_close",
    "bid_price","ask_price","bid_ask_spread","mid_price","vwap_price",
    "day_high_price","day_low_price","intraday_range_percentage",
    "price_data_type_label","price_truth_source_label","daily_bars_count",
    "float_shares_raw","float_shares_formatted","float_category",
    "float_shares_source","float_cache_hit",
    "current_intraday_volume","current_volume_source_label",
    "average_daily_volume_20d","average_daily_volume_window_days",
    "relative_volume","relative_volume_category",
    "volume_velocity_5m","volume_velocity_15m","volume_data_quality_flag",
    "news_total_headlines","news_unique_headlines","news_replicated_headlines",
    "news_velocity_10m","news_velocity_60m","news_spike_indicator",
    "news_freshest_age_minutes","news_regions_list","news_region_count",
    "news_top_sources_list","news_top_source_credibility_score",
    "news_average_sentiment","news_keyword_relevance_score",
    "news_primary_catalyst_keywords","news_top_headlines_list",
    "composite_momentum_score","score_components_breakdown",
    "attention_tier","trade_suggestion_label","trade_suggestion_rationale"
]

def print_symbol(symbol, rank):
    print("="*90)
    print(f"MASTER SCANNER — {datetime.utcnow().isoformat()}Z")
    print("="*90)
    entry = {k: None for k in CANONICAL_FIELDS}
    entry["symbol"] = symbol
    entry["sort_rank_by_gap_desc"] = rank
    for k in CANONICAL_FIELDS:
        print(f"  - {k}: {entry[k]}")

def main():
    for i, sym in enumerate(["TEST1","TEST2","TEST3"], start=1):
        print_symbol(sym, i)

if __name__ == "__main__":
    main()
