# PHASE 24 Scanner Mechanical Checklist

Scanner version: `v2026-01-04-11`
Scanner git SHA: ``
Sample size: `1`

| # | Field | Status | Source | Notes |
| --- | --- | --- | --- | --- |
| 1 | `momentum_fire_indicator` | PRESENT | news.news_heat.compute_fire_indicator | Observed non-empty values in sample. |
| 2 | `symbol` | PRESENT | scanner_runner (IBKR contract) | Observed non-empty values in sample. |
| 3 | `market_session_label` | PRESENT | scanner_master_v2026_01_06_07.market_session_label_utc | Observed non-empty values in sample. |
| 4 | `sort_rank_by_gap_desc` | PRESENT | scanner_runner sort | Observed non-empty values in sample. |
| 5 | `previous_close_price` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 6 | `session_open_price` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 7 | `overnight_gap_percentage` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 8 | `last_trade_price` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 9 | `current_percentage_change_from_prior_close` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 10 | `bid_price` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 11 | `ask_price` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 12 | `bid_ask_spread` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 13 | `mid_price` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 14 | `vwap_price` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 15 | `day_high_price` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 16 | `day_low_price` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 17 | `intraday_range_percentage` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 18 | `price_data_type_label` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 19 | `price_truth_source_label` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 20 | `daily_bars_count` | PRESENT | scanner_master_v2026_01_06_07.get_price_truth | Observed non-empty values in sample. |
| 21 | `float_shares_raw` | PRESENT | scanner_master_v2026_01_06_07.get_float_shares | Observed non-empty values in sample. |
| 22 | `float_shares_formatted` | PRESENT | scanner_master_v2026_01_06_07.fmt_float_human | Observed non-empty values in sample. |
| 23 | `float_category` | PRESENT | scanner_master_v2026_01_06_07.categorize_float | Observed non-empty values in sample. |
| 24 | `float_shares_source` | PRESENT | scanner_master_v2026_01_06_07.get_float_shares | Observed non-empty values in sample. |
| 25 | `float_cache_hit` | PRESENT | scanner_master_v2026_01_06_07.get_float_shares | Observed non-empty values in sample. |
| 26 | `current_intraday_volume` | PRESENT | scanner_master_v2026_01_06_07.get_volume_truth | Observed non-empty values in sample. |
| 27 | `current_volume_source_label` | PRESENT | scanner_master_v2026_01_06_07.get_volume_truth | Observed non-empty values in sample. |
| 28 | `average_daily_volume_20d` | PRESENT | scanner_master_v2026_01_06_07.get_volume_truth | Observed non-empty values in sample. |
| 29 | `average_daily_volume_window_days` | PRESENT | scanner_master_v2026_01_06_07.get_volume_truth | Observed non-empty values in sample. |
| 30 | `relative_volume` | PRESENT | scanner_master_v2026_01_06_07.get_volume_truth | Observed non-empty values in sample. |
| 31 | `relative_volume_category` | PRESENT | scanner_master_v2026_01_06_07.get_volume_truth | Observed non-empty values in sample. |
| 32 | `volume_velocity_5m` | PRESENT | scanner_master_v2026_01_06_07.get_volume_truth | Observed non-empty values in sample. |
| 33 | `volume_velocity_15m` | PRESENT | scanner_master_v2026_01_06_07.get_volume_truth | Observed non-empty values in sample. |
| 34 | `volume_data_quality_flag` | PRESENT | scanner_master_v2026_01_06_07.get_volume_truth | Observed non-empty values in sample. |
| 35 | `news_total_headlines` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 36 | `news_unique_headlines` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 37 | `news_replicated_headlines` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 38 | `news_velocity_10m` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 39 | `news_velocity_60m` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 40 | `news_spike_indicator` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 41 | `news_freshest_age_minutes` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 42 | `news_regions_list` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 43 | `news_region_count` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 44 | `news_top_sources_list` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 45 | `news_top_source_credibility_score` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 46 | `news_average_sentiment` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 47 | `news_keyword_relevance_score` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 48 | `news_primary_catalyst_keywords` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 49 | `news_top_headlines_list` | PRESENT | scanner.news_engine.get_news_truth | Observed non-empty values in sample. |
| 50 | `composite_momentum_score` | PRESENT | scanner.field_mapper._compute_scores | Observed non-empty values in sample. |
| 51 | `score_components_breakdown` | PRESENT | scanner.field_mapper._compute_scores | Observed non-empty values in sample. |
| 52 | `attention_tier` | PRESENT | scanner.field_mapper._compute_scores | Observed non-empty values in sample. |
| 53 | `trade_suggestion_label` | PRESENT | scanner.field_mapper._compute_scores | Observed non-empty values in sample. |
| 54 | `trade_suggestion_rationale` | PRESENT | scanner.field_mapper._compute_scores | Observed non-empty values in sample. |
