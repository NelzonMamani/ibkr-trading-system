# E2 — Gap Analysis

Legend: ✔ = complete, ◐ = partial, ❌ = missing

- ❌ Canonical position states (FLAT, OPEN, SCALING_IN, REDUCING, CLOSING, CLOSED) are not implemented; current state machine uses OPENED/PROTECTED/IN_PROFIT/EXIT_PENDING/CLOSED.
- ❌ Allowed transition guards do not match governance model (e.g., no explicit FLAT→OPEN or OPEN→REDUCING lifecycle enforcement).
- ◐ Transition validation exists in `ActiveTrade.transition_state`, but it targets the non-canonical state set.
- ❌ Lifecycle actions for ADD/SCALE_OUT/FULL_EXIT/STOP_EXIT/TIME_EXIT/RISK_EXIT/SYSTEM_EXIT are not modeled as explicit lifecycle events.
- ❌ Mode-aware lifecycle handling is implicit via broker/execution code, not explicit in the lifecycle engine.
- ❌ Position lifecycle persistence is in-memory only; no explicit persistence of lifecycle transitions.

Certification is blocked until canonical lifecycle states and transitions are implemented and verified across all modes.
