# E15_FAILURE_MODES — IMPLEMENTATION TASKS

Codex must:

1. Locate existing failure-handling logic
2. Map existing behaviour to E15 governance
3. Identify missing detectors or containment paths
4. Implement missing detectors (additive only)
5. Wire detector output to containment state transitions
6. Enforce monotonic escalation per cycle
7. Block execution immediately upon failure in LIVE
8. Surface failure reasons via logs and audit records

No strategy logic may be modified.
No scanner logic may be refactored.
Only authority and containment paths may be added.

END
