# Ross Symbol Authority + THA Gate Validation Runbook

## Purpose
Validate that Ross cycle symbol authority remains coherent from orchestrator handoff into `RossMomentumStrategyV1`, and that THA blocks entries without silently erasing authoritative symbols.

## Environment prep
1. Ensure Python env + dependencies are active.
2. Use PAPER mode with execution disabled for safe validation.
3. Enable strategy and logs:
   - `RUN_MODE=PAPER`
   - `SELECTED_STRATEGY=ross_momentum`
   - `ROSS_MOMENTUM_STRATEGY_ENABLED=true`

## Command (PAPER mode)
```bash
RUN_MODE=PAPER EXECUTION_ENABLED=false SELECTED_STRATEGY=ross_momentum python -m src.main
```

## Required log expectations
For cycles where upstream scanner/focus yields symbols:
1. Symbol authority chain:
   - `[SYMBOL_AUTHORITY][SOURCE] ... source=strategy_watchlist_pre_tha count=N`
   - `[SYMBOL_AUTHORITY][MERGE] ... source=tha_gate authoritative_count=N blocked_entries=B preserved_authority=True`
   - `[SYMBOL_AUTHORITY][FINAL] ... authoritative_count=N process_count=N`
2. Ross input reconciliation:
   - `[ROSS][INPUT_AUTHORITY] ... authoritative_symbols=N process_symbols=N tha_entry_blocked=B`
   - `[ROSS][PROCESS_START] symbols=N`
3. THA semantics:
   - `[THA][ENTRY_POLICY] ... blocked_entries=B authoritative_symbols=N`
   - `[THA][SYMBOL_EFFECT] ... action=block_entries_only ...` (only when B>0)
   - `[THA][FLAT_POLICY] ...` if force-flat applies to existing positions.

## Success criteria before submission stage
- Upstream symbols appear in authority logs and are passed into Ross process (`process_symbols=N`) unless explicitly dropped with truthful reason logs.
- No contradictory sequence where symbol eval starts for concrete symbols and same cycle later reports empty watchlist without reason.
- If THA blocks entries, entries are dropped post-strategy with explicit drop logs (`[SYMBOL_AUTHORITY][DROP] ... reason=dropped_by_tha_policy`) while symbol authority remains non-empty.

## Diagnose outcomes quickly
### A) True empty watchlist
- `[SYMBOL_AUTHORITY][SOURCE] ... count=0`
- `[ROSS][NO_SYMBOLS_REASON] ... reason=authoritative_watchlist_empty`

### B) THA-blocked entries with preserved authority
- `[SYMBOL_AUTHORITY][SOURCE] ... count>0`
- `[THA][ENTRY_POLICY] ... blocked_entries>0`
- `[ROSS][INPUT_AUTHORITY] ... authoritative_symbols>0 process_symbols>0`
- Optional downstream drop: `[SYMBOL_AUTHORITY][DROP] ... reason=dropped_by_tha_policy`

### C) Broken handoff / state loss regression
- Upstream symbol logs appear, but missing `[SYMBOL_AUTHORITY][FINAL]` / `[ROSS][INPUT_AUTHORITY]` reconciliation.
- `process_symbols=0` while source count > 0 and no truthful drop reason.
- Treat as authority-path defect and halt runtime validation.
