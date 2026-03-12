# Repair Notes

## Files changed
- `src/config/config_resolver.py`
- `src/runtime/bootstrap.py`
- `src/execution/execution_engine.py`
- `src/risk/risk_engine.py`
- `src/scanner/scanner_runner.py`
- `src/brokers/ibkr_broker.py`

## Repair summary
- Implemented explicit override-first precedence in resolver and documented authority law.
- Added `clear_config_overrides()` canonical reset helper.
- Added resolver env fingerprint invalidation to prevent stale config cache from leaking prior env state.
- Reset shared IBKR connection manager on override mutation to reduce singleton contamination across tests.
- Ensured runtime bootstrap sqlite path resolves from authoritative config (not direct env bypass).
- Restored execution preflight priority before session gate so READ_ONLY and hard mode blocks report correctly.
- Preserved PAPER default provider behavior and made PAPER bypass session gate in execution path for deterministic testing flow.
- Relaxed risk session gating to apply to LIVE only (not PAPER).
- Added backward-compatible optional `session_label` in scanner runtime threshold resolver.
- Adjusted float cache loader to tolerate stale-but-valid entries (logs provenance) instead of dropping hits.
- Restored IBKR readonly broker compatibility with injected client constructor while preserving manager-backed default path.

## Invariants now enforced
- Test overrides dominate env.
- Env changes are observed between tests due to resolver cache invalidation.
- READ_ONLY remains explicitly non-executable.
- LIVE never leaks into tests unless explicitly configured.
