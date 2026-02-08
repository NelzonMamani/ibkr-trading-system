# E2 — Allowed Transitions

Valid transitions:
FLAT → OPEN
OPEN → SCALING_IN
OPEN → REDUCING
SCALING_IN → OPEN
REDUCING → OPEN
OPEN → CLOSING
CLOSING → CLOSED

All other transitions are invalid and must be rejected.
