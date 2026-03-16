# Live Readiness Hardening Evidence (2026-03-16)

## Root causes found
- Scanner diagnostics CLI used non-canonical broker/provider assumptions and could fail when wrapper capabilities diverged from low-level IB calls.
- Session attribution used `FORCED_OVERRIDE` generically, even when no explicit override source was attached.
- Scanner `raw zero` outcomes lacked explicit broker-vs-local-gating attribution fields.
- Pipeline diagnostics lacked explicit partial hydration semantics and safe execution gating language.

## Fixes made
- Reworked scanner diagnostics to use canonical `run_scanner_cycle` path.
- Added source-specific session override attribution in session diagnostics and scanner logs.
- Added explicit `[SCANNER][RAW_ZERO]` attribution block with broker/local gating and counts.
- Hardened trade pipeline diagnostics output and execution safety flags.
- Added a unified read-only `live_readiness_check` CLI.
- Added focused tests for diagnostics CLIs, session attribution, and raw-zero logging.

## Remaining external dependency
- Real IBKR premarket scanner can legitimately return zero candidates under market conditions.
- This is now explicitly attributable via `[SCANNER][RAW_ZERO]` diagnostics instead of ambiguous behavior.
