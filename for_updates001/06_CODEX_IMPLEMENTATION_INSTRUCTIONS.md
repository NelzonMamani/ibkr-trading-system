# Codex – Final Implementation Instructions

## Phase 1 – Scanner Fixes
- Enforce STK.US.MAJOR
- Emit all scanner events
- Print raw universe and drops

## Phase 2 – Event Infrastructure
- Define event schemas
- Wire scanner → event bus
- Orchestrator consumes events only

## Phase 3 – Pre-Market Prep Engine
- Background task
- Extended universe (150 symbols)
- Cache float, news, levels

## Phase 4 – Strategy Integration
- Strategy consumes WATCHLIST_K
- Momentum spike may promote symbols

## Mandatory Verification
- Run LIVE_READ_ONLY
- Verify:
  - Universe snapshot printed
  - Drops logged
  - WATCHLIST_K printed
  - Prep cache updated

If verification fails, Codex must fix and retry.