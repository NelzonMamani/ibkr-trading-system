# System State Integration (M5 + E23)

## Canonical Files
- `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md`
- repo-root `SYSTEM_STATE_CERTIFIED.md`

## Required Fields
Strategy certification phase state must be represented as:
- STRATEGY_CERTIFICATION_PHASE: ACTIVE | COMPLETE
- CERTIFIED_STRATEGIES: count
- FAILED_STRATEGIES: count

## Relationship to Platform State
Platform state remains:
- TRADING_READY_PAPER (until explicitly elevated)

Strategy certification is an overlay:
- Platform can be TRADING_READY_PAPER while strategies are FAIL
- CERTIFIED strategy set is enumerated explicitly

## E23 Reconciliation Linkage
The E23 reconciliation report should be able to consume:
- strategy matrix v2
- strategy certification report

If E23 expects a specific artifact path, Codex must preserve compatibility or extend E23 in an additive way only.
