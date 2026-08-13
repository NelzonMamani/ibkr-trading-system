# PR1050 Float Discovery and Focus M After Market-Data Fix

## Scope

PR1050 repairs the real READ_ONLY Ross observation path after PR1049 confirmed usable IBKR market data. The remaining blocker was mostly `DROP_FLOAT_UNKNOWN`: scanner candidates could resolve/write float during a cycle, but final Ross watchlist/focus gates could still evaluate the same candidate before the newly discovered value was reused.

This change adds bounded same-cycle float discovery and rehydration for READ_ONLY non-mock scanner candidates that already have usable quote fields. It does not alter Ross thresholds, does not relax float/rvol/price/catalyst gates, does not bypass catalyst, does not create manual or synthetic focus symbols, and does not enable trading.

## Executive Verdict

PAPER_READY: NO
PAPER_READINESS_GATE: FAIL
ZERO_BROKER_ORDER_MUTATIONS: YES
READ_ONLY_ONLY_CHANGE: YES
ROSS_THRESHOLDS_CHANGED: NO
ROSS_GATES_WEAKENED: NO
CATALYST_BYPASS_ADDED: NO
MANUAL_FOCUS_PROOF_ALLOWED: NO
SYNTHETIC_FOCUS_ALLOWED: NO
PAPER_LIVE_ENABLED: NO
BROKER_ORDER_MUTATION_ALLOWED: NO

## Implementation

Scanner runtime now performs one bounded foreground float discovery attempt before the final Ross float/watchlist/focus gates when all of these are true:

- runtime mode is `READ_ONLY`
- scanner provider is not `MOCK`
- candidate still lacks `float_shares`
- candidate has usable market data: last price, bid, ask, and volume are present and positive enough for the existing quote checks
- candidate has not hit snapshot timeout or snapshot error evidence
- the cycle has not exceeded `PR1050_FLOAT_DISCOVERY_MAX_PER_CYCLE`

When discovery returns a positive share count, the scanner updates the in-memory float cache for the current cycle, rehydrates the candidate context, removes `FLOAT_UNKNOWN`, and then continues through the existing Ross gates. If discovery fails, returns no value, or the request limit is exhausted, the existing strict `DROP_FLOAT_UNKNOWN` behavior remains in force.

## Proof Fields

Scanner payloads, diagnostics, PR1040 observation input artifacts, and PR1046 market-data diagnostics now propagate:

- `float_discovery_requested_count`
- `float_discovery_success_count`
- `float_discovery_failed_count`
- `float_discovery_cache_hit_count`
- `float_discovery_same_cycle_rehydrated_count`
- `float_discovery_pending_count`
- `float_unknown_after_bounded_discovery_count`
- `symbols_rehydrated_from_same_cycle_float_discovery`
- `symbols_still_dropped_float_unknown`
- `symbols_pending_same_cycle_float_discovery`
- `symbols_failed_same_cycle_float_discovery`
- `max_same_cycle_float_discovery_requests`

The same-cycle request count is bounded and only reflects foreground lookups during the active READ_ONLY cycle. Existing float-cache hits remain tracked separately.

## Focus M Diagnostics

PR1050 adds explicit empty-Focus-M explanations for real usable-market-data cases:

- `FOCUS_M_POPULATED`
- `USABLE_MARKET_DATA_BUT_UNKNOWN_FLOAT`
- `USABLE_MARKET_DATA_BUT_OVER_FLOAT`
- `USABLE_MARKET_DATA_BUT_RVOL_FAILURE`
- `USABLE_MARKET_DATA_BUT_CATALYST_NEWS_FAILURE`
- `USABLE_MARKET_DATA_BUT_NO_ROSS_QUALITY_FOCUS_CANDIDATE`
- `MISSING_MARKET_DATA`

The diagnostics also list symbols in each category and include `focus_drop_reason_counts` for focus-stage rejection visibility.

## Safety Boundaries

PR1050 does not submit, cancel, modify, preview-submit, stage, flatten, reconcile, or clean-start broker orders. It does not modify execution routing. It does not enable PAPER or LIVE. It keeps PR1040 and PR1046 outputs explicit:

```text
PAPER_READY=NO
PAPER_READINESS_GATE=FAIL
ZERO_BROKER_ORDER_MUTATIONS=YES
```

Unknown float remains non-quality evidence in READ_ONLY unless the bounded same-cycle lookup finds a real usable positive float value. Over-float candidates continue to fail `DROP_FLOAT_MAX`. Catalyst-required candidates continue to fail `DROP_NO_CATALYST` when catalyst evidence is unavailable.

## Validation Commands

Run from the repository root using the project test environment:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
.\.venv\Scripts\python.exe -m pytest tests/test_pr1046_ibkr_market_data_diagnostics.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_ross_pr1045_real_bounded_observation_runtime_controls.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_ross_pr1040_real_readonly_runtime_observation_adapter.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_ross_pr1039_readonly_full_strategy_observation_producer.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_ross_pr1038_readonly_full_strategy_observation_collector.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_ross_pr1050_float_discovery_focus_m.py -q
```

Local validation completed from the short-path PR1050 clone using the original checkout virtual environment:

- `compileall -q src tests scripts`: PASS
- `tests/test_pr1046_ibkr_market_data_diagnostics.py -q`: 18 passed
- `tests/test_ross_pr1045_real_bounded_observation_runtime_controls.py -q`: 8 passed
- `tests/test_ross_pr1040_real_readonly_runtime_observation_adapter.py -q`: 22 passed
- `tests/test_ross_pr1039_readonly_full_strategy_observation_producer.py -q`: 29 passed
- `tests/test_ross_pr1038_readonly_full_strategy_observation_collector.py -q`: 16 passed
- `tests/test_ross_pr1050_float_discovery_focus_m.py -q`: 6 passed

PR1050 focused coverage:

- same-cycle discovered float rehydrates before final Ross gates and can reach Focus M only through `LIVE_SCAN`
- failed discovery keeps `DROP_FLOAT_UNKNOWN` and no Focus M quality proof
- over-float discovery keeps `DROP_FLOAT_MAX`
- rvol focus failure remains a focus-stage reject after valid float rehydration
- catalyst-required candidates remain blocked without catalyst evidence
- PR1040/PR1046 artifacts propagate proof fields while keeping PAPER readiness failed and broker order mutation count zero
