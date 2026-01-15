# PHASE 37 — PERFORMANCE REPORTS FROM STORAGE (AUTHORITATIVE)

## Intent
Shift reporting to “stored truth” so that performance analytics are reproducible.
PerformanceRegistry must be able to:
- emit snapshots during runtime (already present)
- persist snapshots
- reconstruct daily/weekly/cumulative summaries from stored snapshots and outcomes

## Scope
- `src/core/performance_registry.py`
- `src/performance/*`
- `src/storage/*` (performance_snapshots table)
- reporting output under `output/reports/` (new folder)

## Canonical Report Types
1. Daily report (UTC day boundary)
2. Weekly report (ISO week)
3. Cumulative report (all-time for db)

Reports must include:
- trades opened/closed
- win/loss/flat counts
- win rate
- gross and net PnL
- commissions, slippage totals
- by_strategy breakdown
- by_trader_type breakdown
- exit_category distribution (EXIT_STOP_LOSS, EXIT_TARGET, EXIT_RISK, EXIT_BREAKER, ...)
- rule adherence metrics persisted

## No-Recompute Rule
Reports must not re-evaluate price feeds or market conditions.
They may only aggregate:
- stored trade_outcomes
- stored execution_results
- stored performance snapshots emitted by runtime

## Output Contract
- Save deterministic JSON and a human-readable TXT summary.
- Filenames include UTC date/time and run_id.
Example:
- `output/reports/daily_2026-01-15_run_<run_id>.json`
- `output/reports/daily_2026-01-15_run_<run_id>.txt`

## Definition of Done
- performance_snapshots persisted per cycle or per run end.
- CLI/report function can generate daily/weekly/cumulative reports from db alone.
- New test `tests/test_performance_reports_epoch4.py` validates aggregations are stable and deterministic.
