# STRATEGY_CERTIFICATION_REPORT

Generated (UTC): 2026-02-18T20:31:50Z

## Summary
- Strategies audited: 20
- CERTIFIED: 1
- CONDITIONALLY_CERTIFIED: 0
- FAIL: 19

## Per Strategy Results

| Strategy | Verdict | Default-Only | Missing Controls |
|---|---|---|---|
| P01_ross_momentum | CERTIFIED | False | None |
| P02_statistical_intraday_momentum | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P03_mean_reversion | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P04_long_horizon_value | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P05_opening_drive | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P06_vwap_reclaim | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P07_power_hour | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P08_volatility_expansion | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P09_range_bound_fade | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P10_support_resistance_channel | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P11_event_earnings_reaction | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P12_event_news_shock_continuation | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P13_volatility_contraction_breakout | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P14_volatility_carry_risk_premium | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P15_pairs_divergence_reversion | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P16_cross_sectional_relative_strength_rotation | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P17_time_based_seasonality | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P18_trend_following_classic | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P19_long_horizon_quality_compounder | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |
| P20_regime_adaptive_meta_allocator | FAIL | True | D1.C03: liquidity_sanity_model missing halt policy<br>D1.C04: ranking model missing rationale<br>D10.C01: required_fields must be non-empty<br>D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol<br>D10.C03: data requirements notes must define pause/reject behavior<br>D11.C01: explicit safety escalation path required<br>D11.C02: default-only policy detected<br>D13.C02: cadence authority should be explicit<br>D14.C01: scaling doctrine notes missing<br>D2.C01: setup_families requires >=1<br>D2.C02: pattern_catalog requires >=1<br>D2.C03: structure_model levels should be non-empty<br>D3.C01: conditions/confirmations require >=1<br>D3.C02: data-quality condition missing<br>D3.C03: level behavior condition not declared<br>D4.C01: confirmations require >=1<br>D4.C02: liquidity/spread confirmation missing<br>D4.C03: volume/rvol confirmation missing<br>D5.C02: trigger entries require >=1<br>D6.C02: intrabar applicability not declared<br>D6.C03: intrabar phase_specs/timeframe_map required when applicable<br>D7.C02: safety_model requires >=1 rule<br>D7.C03: session reference law is empty<br>D8.C01: exit rules require >=1<br>D8.C02: trailing rules should be declared<br>D8.C03: failure-fast bailout behavior not declared<br>D9.C01: position management doctrine note required |

## P01_ross_momentum

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | PASS |
| D2 Setup Taxonomy | PASS |
| D3 Conditions | PASS |
| D4 Confirmations | PASS |
| D5 Trigger Model | PASS |
| D6 Intrabar Execution Doctrine | PASS |
| D7 Risk Governance | PASS |
| D8 Exit Governance | PASS |
| D9 Position Management | PASS |
| D10 Data Requirements | PASS |
| D11 Safety & Failure Modes | PASS |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | PASS |

Missing controls:
- None

## P02_statistical_intraday_momentum

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P03_mean_reversion

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P04_long_horizon_value

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P05_opening_drive

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P06_vwap_reclaim

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P07_power_hour

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P08_volatility_expansion

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P09_range_bound_fade

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P10_support_resistance_channel

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P11_event_earnings_reaction

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P12_event_news_shock_continuation

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P13_volatility_contraction_breakout

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P14_volatility_carry_risk_premium

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P15_pairs_divergence_reversion

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P16_cross_sectional_relative_strength_rotation

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P17_time_based_seasonality

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P18_trend_following_classic

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P19_long_horizon_quality_compounder

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required

## P20_regime_adaptive_meta_allocator

| Domain | Verdict |
|---|---|
| D0 Strategy Identity | PASS |
| D1 Stock Selection / Universe Definition | FAIL |
| D2 Setup Taxonomy | FAIL |
| D3 Conditions | FAIL |
| D4 Confirmations | FAIL |
| D5 Trigger Model | FAIL |
| D6 Intrabar Execution Doctrine | FAIL |
| D7 Risk Governance | FAIL |
| D8 Exit Governance | FAIL |
| D9 Position Management | FAIL |
| D10 Data Requirements | FAIL |
| D11 Safety & Failure Modes | FAIL |
| D12 Execution Constraints | PASS |
| D13 Timeframe Authority | PASS |
| D14 Scaling Doctrine | FAIL |

Missing controls:
- D1.C03: liquidity_sanity_model missing halt policy
- D1.C04: ranking model missing rationale
- D10.C01: required_fields must be non-empty
- D10.C02: required fields must include symbol,last_price and pct_change|volume|rvol
- D10.C03: data requirements notes must define pause/reject behavior
- D11.C01: explicit safety escalation path required
- D11.C02: default-only policy detected
- D13.C02: cadence authority should be explicit
- D14.C01: scaling doctrine notes missing
- D2.C01: setup_families requires >=1
- D2.C02: pattern_catalog requires >=1
- D2.C03: structure_model levels should be non-empty
- D3.C01: conditions/confirmations require >=1
- D3.C02: data-quality condition missing
- D3.C03: level behavior condition not declared
- D4.C01: confirmations require >=1
- D4.C02: liquidity/spread confirmation missing
- D4.C03: volume/rvol confirmation missing
- D5.C02: trigger entries require >=1
- D6.C02: intrabar applicability not declared
- D6.C03: intrabar phase_specs/timeframe_map required when applicable
- D7.C02: safety_model requires >=1 rule
- D7.C03: session reference law is empty
- D8.C01: exit rules require >=1
- D8.C02: trailing rules should be declared
- D8.C03: failure-fast bailout behavior not declared
- D9.C01: position management doctrine note required
