# POLICY_DIFF_MATRIX

| Strategy | selection_plan | stock_selection_law | ranking_model | risk_model | execution_model | trailing_model | exit_model |
|---|---|---|---|---|---|---|---|
| P01:ross_momentum | 77a5133d190693a4 | 39b33f61bb6d07bd | 97526f973eb47a43 | 30f263979bfe1058 | abfb5ec4d246322e | 38126e874b348133 | b654b8b55fad5a38 |
| P02:statistical_intraday_momentum | cb11688e6dd3269c | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P03:mean_reversion | 99b0aea939415b53 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P04:long_horizon_value | 44cdfbe017c954d5 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P05:opening_drive | 93b3bc1f531e01ab | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P06:vwap_reclaim | e8f8f2a4a2fbd255 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P07:power_hour | 3e3825738a2ac0de | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P08:volatility_expansion | afac3f23c874a72e | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P09:range_bound_fade | 136b317bf5c06cbd | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P10:support_resistance_channel | e0c467d04d8ed671 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P11:event_earnings_reaction | a678698b77148fd2 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P12:event_news_shock_continuation | a678698b77148fd2 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P13:volatility_contraction_breakout | d013a6e0ff1eff67 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P14:volatility_carry_risk_premium | 44cdfbe017c954d5 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P15:pairs_divergence_reversion | 44cdfbe017c954d5 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P16:cross_sectional_relative_strength_rotation | 44cdfbe017c954d5 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P17:time_based_seasonality | a678698b77148fd2 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P18:trend_following_classic | 44cdfbe017c954d5 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P19:long_horizon_quality_compounder | 44cdfbe017c954d5 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |
| P20:regime_adaptive_meta_allocator | 44cdfbe017c954d5 | 39624ad9ce90ca2e | 6e42f4b9f52f8ba1 | ed32e0caf7e946b8 | c774302cfc5ac841 | fa73a620ff4c07ec | 80d7c6788787512d |

## Collision list (identical canonical JSON hash by surface)

### selection_plan
- P04:long_horizon_value, P14:volatility_carry_risk_premium, P15:pairs_divergence_reversion, P16:cross_sectional_relative_strength_rotation, P18:trend_following_classic, P19:long_horizon_quality_compounder, P20:regime_adaptive_meta_allocator
- P11:event_earnings_reaction, P12:event_news_shock_continuation, P17:time_based_seasonality

### stock_selection_law
- P02:statistical_intraday_momentum, P03:mean_reversion, P04:long_horizon_value, P05:opening_drive, P06:vwap_reclaim, P07:power_hour, P08:volatility_expansion, P09:range_bound_fade, P10:support_resistance_channel, P11:event_earnings_reaction, P12:event_news_shock_continuation, P13:volatility_contraction_breakout, P14:volatility_carry_risk_premium, P15:pairs_divergence_reversion, P16:cross_sectional_relative_strength_rotation, P17:time_based_seasonality, P18:trend_following_classic, P19:long_horizon_quality_compounder, P20:regime_adaptive_meta_allocator

### ranking_model
- P02:statistical_intraday_momentum, P03:mean_reversion, P04:long_horizon_value, P05:opening_drive, P06:vwap_reclaim, P07:power_hour, P08:volatility_expansion, P09:range_bound_fade, P10:support_resistance_channel, P11:event_earnings_reaction, P12:event_news_shock_continuation, P13:volatility_contraction_breakout, P14:volatility_carry_risk_premium, P15:pairs_divergence_reversion, P16:cross_sectional_relative_strength_rotation, P17:time_based_seasonality, P18:trend_following_classic, P19:long_horizon_quality_compounder, P20:regime_adaptive_meta_allocator

### risk_model
- P02:statistical_intraday_momentum, P03:mean_reversion, P04:long_horizon_value, P05:opening_drive, P06:vwap_reclaim, P07:power_hour, P08:volatility_expansion, P09:range_bound_fade, P10:support_resistance_channel, P11:event_earnings_reaction, P12:event_news_shock_continuation, P13:volatility_contraction_breakout, P14:volatility_carry_risk_premium, P15:pairs_divergence_reversion, P16:cross_sectional_relative_strength_rotation, P17:time_based_seasonality, P18:trend_following_classic, P19:long_horizon_quality_compounder, P20:regime_adaptive_meta_allocator

### execution_model
- P02:statistical_intraday_momentum, P03:mean_reversion, P04:long_horizon_value, P05:opening_drive, P06:vwap_reclaim, P07:power_hour, P08:volatility_expansion, P09:range_bound_fade, P10:support_resistance_channel, P11:event_earnings_reaction, P12:event_news_shock_continuation, P13:volatility_contraction_breakout, P14:volatility_carry_risk_premium, P15:pairs_divergence_reversion, P16:cross_sectional_relative_strength_rotation, P17:time_based_seasonality, P18:trend_following_classic, P19:long_horizon_quality_compounder, P20:regime_adaptive_meta_allocator

### trailing_model
- P02:statistical_intraday_momentum, P03:mean_reversion, P04:long_horizon_value, P05:opening_drive, P06:vwap_reclaim, P07:power_hour, P08:volatility_expansion, P09:range_bound_fade, P10:support_resistance_channel, P11:event_earnings_reaction, P12:event_news_shock_continuation, P13:volatility_contraction_breakout, P14:volatility_carry_risk_premium, P15:pairs_divergence_reversion, P16:cross_sectional_relative_strength_rotation, P17:time_based_seasonality, P18:trend_following_classic, P19:long_horizon_quality_compounder, P20:regime_adaptive_meta_allocator

### exit_model
- P02:statistical_intraday_momentum, P03:mean_reversion, P04:long_horizon_value, P05:opening_drive, P06:vwap_reclaim, P07:power_hour, P08:volatility_expansion, P09:range_bound_fade, P10:support_resistance_channel, P11:event_earnings_reaction, P12:event_news_shock_continuation, P13:volatility_contraction_breakout, P14:volatility_carry_risk_premium, P15:pairs_divergence_reversion, P16:cross_sectional_relative_strength_rotation, P17:time_based_seasonality, P18:trend_following_classic, P19:long_horizon_quality_compounder, P20:regime_adaptive_meta_allocator
