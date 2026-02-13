# 06_CHANGE_CONTROL_AND_SAFETY_RULES.md
# E23 — Change Control & Safety Rules
Last updated: 2026-02-13

E23 is empowered to improve coherence, but must preserve safety and change control.

## Safety Rules
- No behavioural change that increases LIVE risk without an explicit risk-permission gate and evidence.
- In LIVE, execution must remain gated by Risk Engine authority.
- Any automatic fix must keep the platform trade-safe.

## Change Control Rules (M8)
- Every automatic fix must:
  - be traceable (why, where, what)
  - be reversible (small, bounded changes)
  - be backed by verification evidence (post-fix)

- Deletions/removals are not performed by E23 automatically unless explicitly permitted under housekeeping epoch E12.
  E23 may:
  - mark for deletion in RECONCILIATION_REPORT
  - open a housekeeping TODO entry

## Default Strategy Readiness Bias
- Prefer changes that improve determinism, traceability, and fast-path performance.
- Prefer compatibility shims over removals.
- Prefer tightening invariants and tests over redesign.

END
