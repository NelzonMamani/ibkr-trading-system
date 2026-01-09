# PHASE 24 Scanner Mechanical Checklist

Scanner version: `v2026-01-04-11`
Scanner git SHA: ``
Sample size: `50`

| # | Field | Status | Source | Notes |
| --- | --- | --- | --- | --- |
| 1 | `momentum_fire_indicator` | PRESENT | src.news.news_heat.compute_fire_indicator | Observed non-empty values in sample. |
| 2 | `symbol` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 3 | `market_session_label` | PRESENT | scanner_runner session label | Observed non-empty values in sample. |
| 4 | `sort_rank_by_gap_desc` | PRESENT | scanner_runner sort | Observed non-empty values in sample. |
| 5 | `previous_close_price` | PRESENT | scanner_runner provider quote | Observed non-empty values in sample. |
| 6 | `session_open_price` | PRESENT | scanner_runner provider quote | Observed non-empty values in sample. |
| 7 | `overnight_gap_percentage` | PRESENT | scanner_runner derived gap | Observed non-empty values in sample. |
| 8 | `last_trade_price` | PRESENT | scanner_runner provider quote | Observed non-empty values in sample. |
| 9 | `current_percentage_change_from_prior_close` | PRESENT | scanner_runner derived pct | Observed non-empty values in sample. |
| 10 | `bid_price` | PRESENT | scanner_runner provider quote | Observed non-empty values in sample. |
| 11 | `ask_price` | PRESENT | scanner_runner provider quote | Observed non-empty values in sample. |
| 12 | `bid_ask_spread` | PRESENT | scanner_runner derived spread | Observed non-empty values in sample. |
| 13 | `mid_price` | PRESENT | scanner_runner derived mid | Observed non-empty values in sample. |
| 14 | `vwap_price` | PRESENT | scanner_runner provider quote | Observed non-empty values in sample. |
| 15 | `day_high_price` | PRESENT | scanner_runner provider quote | Observed non-empty values in sample. |
| 16 | `day_low_price` | PRESENT | scanner_runner provider quote | Observed non-empty values in sample. |
| 17 | `intraday_range_percentage` | PRESENT | scanner_runner derived range | Observed non-empty values in sample. |
| 18 | `price_data_type_label` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 19 | `price_truth_source_label` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 20 | `daily_bars_count` | MISSING | scanner_runner | No non-empty values observed in sample. |
| 21 | `float_shares_raw` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 22 | `float_shares_formatted` | PRESENT | scanner_runner derived | Observed non-empty values in sample. |
| 23 | `float_category` | PRESENT | scanner_runner derived | Observed non-empty values in sample. |
| 24 | `float_shares_source` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 25 | `float_cache_hit` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 26 | `current_intraday_volume` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 27 | `current_volume_source_label` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 28 | `average_daily_volume_20d` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 29 | `average_daily_volume_window_days` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 30 | `relative_volume` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 31 | `relative_volume_category` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 32 | `volume_velocity_5m` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 33 | `volume_velocity_15m` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 34 | `volume_data_quality_flag` | PRESENT | scanner_runner provider | Observed non-empty values in sample. |
| 35 | `news_total_headlines` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 36 | `news_unique_headlines` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 37 | `news_replicated_headlines` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 38 | `news_velocity_10m` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 39 | `news_velocity_60m` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 40 | `news_spike_indicator` | PRESENT | scanner_runner spike heuristic | Observed non-empty values in sample. |
| 41 | `news_freshest_age_minutes` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 42 | `news_regions_list` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 43 | `news_region_count` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 44 | `news_top_sources_list` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 45 | `news_top_source_credibility_score` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 46 | `news_average_sentiment` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 47 | `news_keyword_relevance_score` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 48 | `news_primary_catalyst_keywords` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 49 | `news_top_headlines_list` | PRESENT | src.news.news_normalizer.normalize_headlines | Observed non-empty values in sample. |
| 50 | `composite_momentum_score` | PRESENT | scanner.field_mapper._compute_scores | Observed non-empty values in sample. |
| 51 | `composite_news_score` | PRESENT | scanner.field_mapper._compute_scores | Observed non-empty values in sample. |
| 52 | `strategy_trade_bias` | PRESENT | scanner.field_mapper._compute_scores | Observed non-empty values in sample. |
| 53 | `scanner_version` | PRESENT | scanner.contracts.SCANNER_VERSION | Observed non-empty values in sample. |
| 54 | `debug_notes` | MISSING | scanner.field_mapper._compute_scores | No non-empty values observed in sample. |
