# Runtime Mode Authority Repair — Diagnosis Summary

## Root causes
1. **Broken precedence in config resolver**: environment variables were resolved before in-process overrides, so tests using `set_config_overrides(...)` were ignored when shell/env had conflicting values.
2. **Config cache leaked env state across tests**: resolver cache had no environment fingerprint invalidation; monkeypatched env values were not always reflected in later tests.
3. **Execution ordering regression**: session gate ran before mode preflight, causing READ_ONLY decisions to report session rationale instead of authoritative READ_ONLY block.
4. **Scanner API compatibility drift**: `_resolve_runtime_thresholds()` required `session_label` while tests and previous call sites used single-argument form.
5. **Float cache load regression**: stale cache records were dropped too aggressively, causing expected cache-hit paths to miss.
6. **IBKR broker constructor compatibility drift**: readonly broker no longer accepted injected client path expected by tests.
7. **Risk session gating overreach**: PAPER mode was gated by active sessions in risk path, breaking deterministic paper pipeline expectations.

## Evidence of leakage/failures (pre-fix)
- `test_execution_authority_epoch5` showed READ_ONLY execution rationale incorrectly blocked by session gate.
- `test_float_cache_reconciliation` showed cache entries dropped as stale and discovery queued despite existing cache.
- `test_ross_end_to_end_pipeline` showed PAPER risk decision unexpectedly blocked by session gating.

## Scope repaired
- Config authority + cache invalidation
- Mode resolution / execution preflight ordering
- Risk and replay non-regression semantics
- Scanner threshold resolver backward compatibility
- Float cache bootstrap semantics
- IBKR readonly broker constructor backward compatibility
