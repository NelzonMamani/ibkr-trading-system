# ENFORCED INVARIANTS

Cross-mode invariants are mandatory across SIM, PAPER, READ_ONLY, and LIVE.

- Canonical modes are immutable once certified.
- Execution permissions must match the declared mode boundaries.
- No implicit fallback between modes is allowed.
- Strategy logic, scanner logic, and risk logic must not mutate based on
  undeclared mode-specific behavior (mode may only gate execution and data
  sources).
- Observability, traceability, and audit artifacts must be emitted consistently
  across modes.
- Any violation or ambiguity forces certification failure.

END
