# E4 CODEX — Implementation Tasks

If gaps are found:
1. Enforce canonical market states (PRE, RTH, AH, CLOSED)
2. Treat weekends and holidays as CLOSED
3. Allow preparation and analysis in CLOSED, but forbid execution
4. Enforce session-aware calculations
5. Enforce data-quality-driven no-trade gates
6. Emit trace events for all state and gate decisions

All fixes must be minimal and additive.
END
