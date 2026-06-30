# PR1025 Ross Runtime Completion Audit

## Scope

This audit covers the Ross READ_ONLY/PAPER runtime fixes after PR1022 through PR1024 and the remaining PR1025 wrapper-level focus handoff gap closed in this branch.

This is a runtime completion audit only. It does not tune Ross thresholds, weaken selection gates, enable PAPER/LIVE execution, create synthetic trades, or bypass risk/execution controls.

## Runtime Failure Trace

Original runtime evidence showed a READ_ONLY crash after `[ROSS][PATTERN_INPUT]` with:

```text
AttributeError: 'str' object has no attribute 'tzinfo'
```

The crash was in the PR4 pattern input timestamp path. Current `main` already normalizes datetime, ISO strings, IBKR bar date strings, naive datetimes, and timezone-aware datetimes before freshness checks. Unsupported timestamp values are classified through `[ROSS][RUNTIME_FIX][PATTERN_INPUT_UNAVAILABLE]` and converted into stale/missing/unavailable pattern input state instead of crashing.

The second runtime concern was a focus handoff mismatch: scanner focus could be empty while later Ross runtime paths still evaluated broader watchlist rows. Current `main` blocks PAPER/READ_ONLY/LIVE-like executable fallback at the orchestrator handoff when official Ross focus is empty. This PR closes the remaining wrapper-level gap by filtering `RossMomentumRunner` inputs when explicit focus metadata is present.

## Files Audited

- `src/strategies/ross_momentum/patterns/pattern_inputs.py`
- `src/strategies/ross_momentum/patterns/pattern_trace.py`
- `src/strategies/ross_momentum/policy/pattern_input_policy.py`
- `src/core/orchestrator.py`
- `src/strategy/strategy_runner.py`
- `src/strategies/ross_momentum/runner.py`
- `src/strategies/ross_momentum_strategy_v1.py`

## Findings

### Timestamp normalization

Verdict: Complete on current `main`.

Evidence:

- `normalize_timestamp_utc()` accepts datetime objects, ISO strings, IBKR bar-style strings, naive datetimes, timezone-aware datetimes, and date-only strings.
- `_normalize_candle_timestamps()` applies normalization before freshness/provenance checks.
- `_timeframe_provenance()` uses normalized timestamps and classifies stale data through `IndicatorProvenance.STALE`.
- `build_runtime_pattern_inputs()` catches timestamp `ValueError` and logs `[ROSS][RUNTIME_FIX][PATTERN_INPUT_UNAVAILABLE]` instead of raising.

Tests already present:

- `test_ibkr_intraday_timestamp_strings_use_eastern_market_timezone`
- `test_timestamp_strings_preserve_explicit_timezone_and_date_only_is_safe`
- `test_stale_timeframe_is_explicit_in_freshness_provenance`
- `test_runtime_builder_marks_stale_opening_10s_as_block`

### Pattern input unavailable classification

Verdict: Complete on current `main`.

Evidence:

- 10s and 5m fetch `ValueError` is logged and skipped as unavailable.
- Non-primary timeframe exceptions do not crash the runtime path.
- Missing/stale required inputs become setup-scoped BLOCK/DEGRADE/WARN actions through `PatternInputPolicy`.
- PR4/PR6 tests prove stale 10s input blocks the affected setup without creating a trade intent.

### Focus handoff authority

Verdict: Complete with this PR.

Evidence:

- `CoreOrchestrator` keeps Ross watchlist fallback diagnostic-only when official focus is empty in PAPER/READ_ONLY/LIVE-like runtime.
- `[ROSS][FOCUS_AUTHORITY]`, `[ROSS][FOCUS_HANDOFF]`, and `[ROSS][NO_TRADE] reason=NO_FOCUS_CANDIDATES` document the handoff state.
- This PR adds a final wrapper guard in `RossMomentumRunner` so explicit focus metadata (`focus_list`, `focus_symbols`, `focus_m_symbols`) is honored before `RossMomentumStrategyV1.process_watchlist()` can fetch pattern inputs.
- Non-focus rows are logged as `[ROSS][FOCUS][SKIP] ... execution_ineligible=true` and are not sent to the Ross V1 pattern pipeline.

New test in this PR:

- `test_ross_runner_explicit_focus_skips_non_focus_rows`

### Synthetic/fallback trade safety

Verdict: Preserved.

Evidence:

- This PR does not alter `synthetic_intent_allowed()`, validation override policy, risk gates, execution mode gates, or threshold values.
- The runner guard only reduces strategy inputs when explicit focus metadata is present.
- No code path added by this PR creates a `TradeIntent`.

## Verification

Local verification could not be run in this Codex session because the Windows command sandbox fails before command startup with:

```text
windows sandbox failed: helper_unknown_error: apply deny-read ACLs
```

Remote verification on the PR branch:

- GitHub Actions workflow `pytest`, run `28456679039`: success on head `8db037d193838a239fdd96826fdd770bcbde0b97` before this documentation-only audit commit.

Required follow-up after this documentation commit:

- Confirm the next GitHub Actions `pytest` run is green for the updated head.

## Final Verdict

PR1025 runtime completion audit is satisfied by current `main` plus this PR branch:

- Timestamp crash path: closed.
- Pattern input unavailable classification: closed.
- Empty-focus executable fallback: closed.
- Explicit focus wrapper bypass: closed by this PR.
- Synthetic/fallback trade creation: not introduced.

Status: Draft PR remains safe for review. Do not move to PAPER or LIVE as part of this work.
