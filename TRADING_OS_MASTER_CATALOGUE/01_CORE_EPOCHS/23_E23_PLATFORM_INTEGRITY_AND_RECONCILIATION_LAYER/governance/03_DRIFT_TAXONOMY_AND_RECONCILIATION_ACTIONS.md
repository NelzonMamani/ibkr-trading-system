# 03_DRIFT_TAXONOMY_AND_RECONCILIATION_ACTIONS.md
# E23 — Drift Taxonomy & Reconciliation Actions
Last updated: 2026-02-13

## Drift Taxonomy (E23 must detect)
Drift is any contradiction or fragmentation that harms strategy readiness, safety, or coherence.

### D1 — Contract Authority Drift
Example: selection gates enforced in scanner AND in strategy policy.
Risk: inconsistent results and hard-to-debug behavior.
Fix class: consolidate authority to the policy owner; leave compat shims; emit deprecation decisions.

### D2 — Mode Semantics Drift
Example: LIVE_READ_ONLY appears as a canonical mode; inconsistent enforcement across modes.
Fix class: normalize modes, update docs, add a hard gate check that fails if non-canonical modes appear as canonical.

### D3 — Risk Permission Drift
Example: strategy attempts execution when risk permission disallows; or risk caps differ across layers.
Fix class: ensure Risk Engine is the ultimate gate; unify risk config resolution; produce audit events.

### D4 — Evidence / Certification Drift
Example: epochs implemented, but global state doc shows NOT_STARTED; or evidence missing.
Fix class: E23 evidence crawler + runner regenerates global truth from evidence.

### D5 — Interface / Contract Registry Drift
Example: Strategy interface differs from registry; missing required hooks.
Fix class: reconcile interface registry and adapters; add compatibility adapters; update contract registry.

### D6 — Performance / Robustness Drift
Example: slow path in LIVE due to heavy enrichment; unbounded DB growth.
Fix class: re-assert fast-path constraints; move heavy enrichment to offline prep; enforce data lifecycle constraints.

## Reconciliation Action Classes (E23 permitted actions)
E23 may automatically apply:
- Doc regeneration (SYSTEM_STATE, crosswalks)
- Compatibility shims (aliases, adapters) that preserve behavior but simplify canonical truth
- Authority consolidation (only when governance already prescribes the direction)
- Deprecation tagging + ledger updates
- Test/verification improvements to detect drift early
- Housekeeping recommendations (deletions must be executed under E12 if needed)

E23 must NOT:
- Remove behavior without deprecation + change control trail
- Break core invariants of system law
- Introduce new strategy logic

END
