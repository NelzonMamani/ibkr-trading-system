# PHASE 5 — Stress & Fault Injection Matrix

Goal: prove safe failure and traceability under load and partial failure.

## Stress dimensions

1. **Cycle count**
   - Run 25–100 orchestrator cycles (fast mode).
   - Expect no memory leak symptoms, no DB runaway, no orphaned tasks.

2. **Empty inputs**
   - Scanner returns empty.
   - Watchlist K = 0 accepted.
   - Focus M = 0 accepted.
   - Expect clean “no-trade” outcomes with explicit reasons.

3. **Broker unavailable**
   - In SIM/PAPER/READ_ONLY: broker may be stubbed or absent.
   - In LIVE: broker connectivity may fail; system must HALT safely with traceable reason.
   - Expect: no crashes; clear error in evidence logs.

4. **Market data gaps**
   - Missing snapshot for a symbol.
   - Missing historical bars.
   - Expect: strategy gating triggers no-trade; logs show data quality gate.

5. **Policy drift attempt**
   - Modify one policy file temporarily (local only) to confirm the audit invalidation works.
   - Revert the file afterwards.
   - Expected: verdict becomes INVALIDATED_PENDING_REVIEW for that strategy while drift exists.

## Output artifacts

- `stress_runs.json` with counts, iterations, and any failures.
- `fault_injection_log.md` summarising scenarios and results.
