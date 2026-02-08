# E18 — IMPLEMENTATION PLAN: CONFIRMATIONS (K_*)

Source of truth list: governance/08_CANONICAL_LIST_CONFIRMATIONS.md

Task:
1) Implement/confirm existence of all K_* confirmations.
2) Confirmations confirm/invalidate; they never initiate trades.
3) Confirmations must work across strategies (policy-neutral) and be testable.

Minimum deliverables per K_*:
- semantic_name: "K_<NAME>"
- component_type: confirmation
- evaluate(context) -> ConfirmationResult
- ConfirmationResult:
  - confirmed (bool)
  - severity (soft/hard) if relevant
  - explanation (optional)

END
