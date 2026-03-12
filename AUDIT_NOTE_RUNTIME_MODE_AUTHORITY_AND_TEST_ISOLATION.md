# AUDIT NOTE — Runtime Mode Authority and Test Isolation

## Final certified precedence invariant
**test/runtime override authority > env > registry > default**

## Root cause statement
Regressions were caused by configuration precedence inversion (env winning over in-process overrides) and resolver cache behavior that did not invalidate on environment mutation. Together, these leaked accidental LIVE-like semantics into tests and produced nondeterministic mode/execution behavior.

## Repairs applied
- Repaired resolver precedence ordering to make in-process overrides authoritative.
- Added explicit override reset API: `clear_config_overrides()`.
- Added env fingerprint cache invalidation to prevent stale env/config leakage.
- Repaired execution ordering to enforce hard mode preflight (READ_ONLY/SIM/LIVE guards) before session gate.
- Preserved/validated PAPER default provider path and READ_ONLY order blocking.
- Repaired scanner threshold resolver compatibility (`session_label` optional).
- Repaired float-cache bootstrap cache-hit behavior.
- Restored `IbkrBroker` injected-client backward compatibility while keeping manager-backed default.

## Governance invariants affirmed
- READ_ONLY cannot submit orders.
- PAPER defaults to paper execution provider when execution is enabled and provider absent.
- SIM/PAPER replay allowed; LIVE/READ_ONLY replay blocked.
- LIVE semantics are explicit only, not inherited accidentally in tests.
