
# E22 Invariants and Failure Modes

## Invariants (must always hold)
1) **Mode safety**: RUN_MODE gating remains authoritative. E22 cannot enable trading in READ_ONLY or SIM.
2) **Risk authority**: E22 can suppress intents early, but can never bypass risk engine denies.
3) **Deterministic arbitration**: given identical inputs, arbitration outputs (allowed/suppressed sets and ordering) are stable excluding timestamps.
4) **Bounded resource use**: per-cycle global budgets are enforced (snapshots/scans/bars).
5) **Explainability**: every suppressed intent has a reason code + minimal context payload.
6) **Non-regression**: single-strategy behaviour remains unchanged unless E22 explicitly gates for budget/risk reasons.

## Fail-closed policy
On internal errors in E22 components:
- default action is to suppress new intents and emit `E22_INTERNAL_ERROR`
- do not “best-effort” trade when arbitration is inconsistent

## Failure modes catalog (E22-specific)
- FM-E22-1: Budget accounting bug -> runaway calls
- FM-E22-2: Non-deterministic tie-breaker -> flaky tests and audit drift
- FM-E22-3: Strategy bypasses coordinator and pulls data directly -> inconsistent view
- FM-E22-4: Arbitration merges intents incorrectly -> double position or wrong side
- FM-E22-5: Evidence writer fails -> missing certification artifacts

## Required mitigations
- unit tests for tie-breaker determinism
- integration tests that run 3 cycles and compare stable payloads
- explicit “escape hatch” config to disable E22 for emergency (READ_ONLY only), but never in LIVE without evidence
