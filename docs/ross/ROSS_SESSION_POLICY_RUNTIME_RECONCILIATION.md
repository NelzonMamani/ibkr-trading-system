# Ross Session / Policy / Runtime Reconciliation

## Canonical policy and runtime sources
- Canonical Ross policy model: `src/strategies/ross_momentum/strategy_policy.py`.
- Scanner runtime enforcement: `src/scanner/scanner_runner.py`.
- Session and pct/gap/RVOL reference logic: `src/scanner/session_pct_change.py`.
- Reference context and execution-readiness flags: `src/scanner/reference_resolver.py`.
- Orchestrator gating and pipeline progression: `src/core/orchestrator.py`.

## Session mapping contract
Canonical session phases are:
- `PRE`
- `RTH_OPEN`
- `RTH_MID`
- `RTH_LATE`
- `AH`
- `CLOSED`

Compatibility aliases remain supported (`REG`, `RTH`, `AFTER`, `WEEKEND`, `OVN`) and map to canonical values in session diagnostics.

## Runtime evidence fields now expected
Scanner runtime logs now emit:
- `[SESSION][MODE]`: UTC, NY time, resolved session, canonical session, forced override, reference trading date, previous valid market date.
- `[SESSION][RVOL_POLICY]`: selected watchlist/focus RVOL threshold family and source.
- `[SESSION][PCT_REFERENCE]`: pct-change and gap reference policy path.
- `[SESSION][EXECUTION_WINDOW]`: execution permission by session and prep/closed activation.

## Policy reconciliation highlights
`StockSelectionSpec` now explicitly exposes:
- `session_watchlist_rvol_min`
- `session_focus_rvol_min`
- `execution_permitted_sessions`

These fields make session-adaptive RVOL and session execution policy explicit and traceable.

## Pipeline traceability chain
`policy -> scanner -> watchlist -> focus -> patterns -> strategy -> risk -> execution`

Primary trace points:
- Scanner selection and gate checks in `scanner_runner.py`
- Strategy/risk/execution events in orchestrator event stream (`CoreOrchestrator.event_collector`)

