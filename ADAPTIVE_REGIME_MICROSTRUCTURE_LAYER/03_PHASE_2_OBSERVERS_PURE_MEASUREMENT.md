# Phase 2 — Observers: Pure Measurement (Feature Extraction)
Last updated: 2026-01-19

## Objective
Implement deterministic feature extraction with strict data-quality semantics.

## Deliverables
1) src/regime/observers.py
Implement observer classes/functions that accept existing OS artifacts and return FeatureVector + RegimeDataQualityFlag[].

### Inputs available (use what exists; do not invent network calls)
- ScannerCandidate list (price, bid/ask, spread, volume, gap%, rvol, data_quality_flags)
- Market session context (PRE/REGULAR/AFTER/CLOSED)
- Market data snapshots from IBKR READ_ONLY path (where available)
- Pattern results / signals count (optional; do not make required)

### Minimum features (BASIC set)
- session (categorical)
- universe_count (count of candidates in watchlist/focus)
- median_spread_bps (spread/price * 10,000)
- pct_missing_prices
- pct_missing_volume
- median_rvol (if available)
- median_gap_pct (if available)
- top1_momentum_move_pct (if available from candidate fields, else None)
- news_density_proxy (use existing news artifacts if present; else 0.0 with flag)
- liquidity_thin_flag (derived from spread + volume + missingness)

### EXTENDED features (only if ADAPTIVE_REGIME_FEATURE_SET=EXTENDED)
- return_volatility_proxy (use recent bars if already available; else skip)
- range_expansion_proxy
- orderbook_quality_proxy (bid/ask present and spread within threshold)

2) Deterministic computation rules
- Always sort symbols lexicographically before aggregation.
- Missing values: never impute randomly; produce explicit flags and skip via stable rules.

3) Logging
- One compact feature summary line at INFO when enabled
- DEBUG includes full feature vector dump (stable order)

4) Tests
Add tests/test_regime_observers.py:
- Feed a fixed set of synthetic ScannerCandidates and assert exact feature outputs.
- Include missing data cases and assert flags.

## Acceptance criteria
- SIM yields deterministic feature vector for teaching scanner watchlist.
- LIVE_READ_ONLY at closed market yields deterministic flags without crashing.
