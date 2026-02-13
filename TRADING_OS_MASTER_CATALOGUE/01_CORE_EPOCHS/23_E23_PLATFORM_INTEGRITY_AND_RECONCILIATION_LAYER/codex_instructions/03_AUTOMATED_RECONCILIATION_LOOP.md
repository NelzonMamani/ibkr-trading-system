# 03_AUTOMATED_RECONCILIATION_LOOP.md
# Automated Reconciliation Loop — E23 (Codex Must Automate)
Last updated: 2026-02-13

## Principle
If E23 detects drift that harms strategy readiness, E23 must attempt safe automatic repair,
re-verify, and iterate until either:
- platform is coherent and verification passes, OR
- remaining issues require operator decision (rare; must be explicitly listed)

## Loop Algorithm (must implement)
1) Discover epoch inventory (E0..E22, M0..M10, P01..P04)
2) Load verification registry
3) Run baseline fast checks:
   - python -m compileall src
   - pytest -q
4) Run E23 drift detection suite
5) If HARD drift detected:
   - implement minimal fix (if permitted)
   - re-run baseline checks
   - re-run drift suite
   - repeat (bounded iterations, e.g., max 5 loops)
6) If SOFT drift detected:
   - auto-fix and continue
7) Regenerate global truth artifacts
8) Write audit evidence and final platform_integrity_state.json

## Auto-Fix Policy (must encode)
Allowed auto-fixes:
- regenerate stale docs from evidence
- normalize run mode aliases
- consolidate duplicated authority only if governance already prescribes the direction
- add missing verification registry entries when discoverable
- add hard drift tests to prevent recurrence
Not allowed auto-fixes:
- removing features without deprecation ledger entry
- any LIVE risk increase
- architectural redesign

## Evidence & Explainability
Every auto-fix must be recorded in RECONCILIATION_REPORT.md:
- what changed
- why
- what verification proved correctness

END
