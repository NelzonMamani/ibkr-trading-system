# 2026-04-06 Runtime Hierarchy Enforcement Fix (Ross Momentum)

## Root cause

The live runtime path in `RossMomentumStrategy.evaluate()` was not using the hierarchy-selected setup at intent creation time.

It used:

- `summary.best_long_setup` first
- then fallback to first detected long setup

This bypassed PR #798 hierarchy behavior whenever a higher-confidence lower-tier setup (e.g. Stair-Step) existed.

Additionally, setup-name canonicalization for hierarchy matching was incomplete:

- `Gap & Go` did not normalize to `GAP_GO`
- `STAIR_STEP` aliases were not reconciled to `TREND_CONTINUATION_STAIR_STEP`

## Exact files where old selection path persisted

- `src/strategies/ross_momentum/strategy.py` (runtime intent creation path selected from `summary.best_long_setup`)
- `src/strategies/ross_momentum/hierarchy_policy.py` (canonicalization gaps and missing alias reconciliation)

## What changed

1. Added canonical setup alias reconciliation in hierarchy policy.
2. Added `setup_identity(...)` as authoritative setup identity resolver.
3. Added `select_dominant_setup_details(...)` to return selected setup + tier metadata.
4. Updated `RossMomentumStrategy.evaluate()` to:
   - log raw+normalized session and tier-map source
   - log hierarchy input detected setups
   - select setup strictly from hierarchy result
   - emit bypass log if legacy best_long differs
   - emit `[ROSS][INTENT_SETUP]` from hierarchy-selected setup used for intent creation
5. Updated `build_trade_intents(...)` with matching runtime evidence logs and bypass diagnostics.

## Before vs after behavior

### Before

PRE session with detected `Gap & Go` + `Stair-Step` could still create final intent using Stair-Step when Stair-Step had higher confidence via `summary.best_long_setup`.

### After

PRE session selection is hierarchy-driven:

- hierarchy input lists detected canonical setups
- hierarchy selected setup is emitted with tier
- intent setup log uses hierarchy-selected setup identity
- if legacy best_long disagrees, explicit bypass diagnostic is emitted

## Proof hierarchy controls live intent creation

Tests added/updated:

- `tests/test_ross_runtime_hierarchy_enforcement.py`
  - PRE with `GAP_GO + TREND_CONTINUATION_STAIR_STEP` confirms final intent setup is `GAP_GO`
  - `RTH_MID` with only `TREND_CONTINUATION_STAIR_STEP` confirms Stair-Step can still be selected
- `tests/test_ross_decision_policy_trigger_to_intent.py`
  - logging assertions aligned to `[ROSS][HIERARCHY][SELECTED]` and canonical setup output

Runtime evidence logs now emitted in strategy and decision policy paths:

- `[ROSS][SESSION] symbol=... raw=... normalized=...`
- `[ROSS][HIERARCHY][INPUT] symbol=... session=... detected=[...]`
- `[ROSS][HIERARCHY][SELECTED] symbol=... session=... setup=... tier=...`
- `[ROSS][HIERARCHY][BYPASS] ...` when legacy path would differ
- `[ROSS][INTENT_SETUP] symbol=... setup_family=... trigger_type=... intent_id=...`
