# Live readiness hardening evidence (2026-03-16)

## Root causes found
- Scanner diagnostics previously relied on non-canonical lower-level invocation patterns; this drift could fail when wrapper internals differ from production scanner path.
- Session attribution could be misleading when forced-session wiring was passed through unconditionally from deterministic orchestrator path.

## Fixes applied
- Scanner diagnostics now runs through canonical `run_scanner_cycle(...)` and reports broker/scanner summary in dry-run and runtime-safe modes.
- Session diagnostics now emits source-specific reasons (`MARKET_CLOCK`, `ENV_OVERRIDE`, `CONFIG_OVERRIDE`, `TEST_OVERRIDE`, `PARAMETER_OVERRIDE`) with explicit `override_source`.
- Core engine scanner invocation no longer forces session unless a real forced session was supplied.
- Existing scanner raw-zero attribution block retained with explicit broker-vs-local gating fields and counts.

## Remaining external dependency
- Real IBKR premarket conditions can still legitimately return zero scanner candidates even with correct request and architecture. The system now provides explicit attribution fields so operators can distinguish broker-empty responses from local gating elimination.
