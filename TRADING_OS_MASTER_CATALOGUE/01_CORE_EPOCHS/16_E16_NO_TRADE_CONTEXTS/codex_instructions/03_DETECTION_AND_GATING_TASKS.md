# E16_NO_TRADE_CONTEXTS — DETECTION AND GATING TASKS

Codex must:

1. Locate existing gating / pause logic
2. Map existing behaviour to E16 contexts
3. Identify missing detectors
4. Implement deterministic detectors (additive only)
5. Centralise no-trade state in orchestrator
6. Enforce gating before order creation
7. Preserve signal generation for diagnostics

No execution path may bypass gating.

END
