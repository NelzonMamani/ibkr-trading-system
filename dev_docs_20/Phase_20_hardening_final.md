Phase_20_hardening_final.md
TASK
Phase 20 hardening (final).

SCOPE
- Reconcile TRADE_CLOSED schema (state_history warning).
- Make SQLite database path explicit and logged.
- Add minimal export capability for persisted runs/events.
- Optionally add schema_version tagging.

STRICT RULES
- Do NOT change strategy, risk, execution, or replay logic.
- Do NOT refactor orchestrator flow.
- Keep changes minimal and explicit.

EXPECTED RESULT
- No schema warnings on shutdown.
- SQLite DB clearly discoverable.
- Runs/events exportable.