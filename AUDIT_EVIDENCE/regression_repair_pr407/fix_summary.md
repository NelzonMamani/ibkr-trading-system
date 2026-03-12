# Runtime Mode Authority Regression Repair — Fix Summary

## Code-path verification summary

- **Early RTH context precedence over spread drop**
  - Verified in `src/scanner/scanner_runner.py::_evaluate_focus_gates` where early-RTH context decision (`KEEP_EARLY_RTH_CONTEXT`) is resolved before spread checks.

- **Scanner ranking authority restored**
  - Verified watchlist selection pipeline:
    - candidate metrics built from evaluated contexts,
    - selector invoked for strategy-specific ranking,
    - selected symbols truncated to watchlist limit,
    - fallback fill only for underflow safeguards.

- **Provider failure handling and degraded state**
  - Verified provider connection failures populate diagnostics and emit degraded state marker (`STATE=DEGRADED`) with fallback behavior controlled by mode.

- **Watchlist print suppression behavior**
  - Verified print emission gates on either watchlist/session change or `WATCHLIST_PRINT_EVERY_N_CYCLES`, with persistent cycle counters.

- **Traceability / connectivity retry**
  - Verified by targeted test passing in LIVE_READ_ONLY coverage.

## Verification commands
See `pytest_results.txt` in this directory for exact command transcript and outcomes.

## Determinism guardrails checked
- Configuration precedence architecture retained (no resolver rollback performed).
- Execution mode semantics unchanged.
- Scanner pipeline remains: provider → candidate metrics → strategy ranking → watchlist → focus.
