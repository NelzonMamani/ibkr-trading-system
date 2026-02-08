# E15_FAILURE_MODES — FAILURE TAXONOMY

All failures must map to one primary class.

1. Data Failures
   - Missing data
   - Stale or frozen data
   - Session mismatch
   - Corrupted fields

2. Decision Failures
   - Missing required inputs
   - Policy hard-gate violation
   - Ambiguous signal state

3. Execution Failures
   - Order rejection
   - Execution outside LIVE
   - Provider mismatch

4. System Failures
   - Run-mode drift
   - DB failure
   - Resource exhaustion

Invariant:
Ambiguity defaults to NO ACTION.

END
