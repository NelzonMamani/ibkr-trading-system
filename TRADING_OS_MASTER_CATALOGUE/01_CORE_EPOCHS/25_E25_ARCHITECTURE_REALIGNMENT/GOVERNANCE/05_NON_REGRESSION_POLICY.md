# Non-Regression Policy

## Principle

Architecture realignment must not reduce safety guarantees or certification traceability.

## Non-regression checks

- Existing evidence index files remain consistent and are updated only if required by file moves.
- Strategy policy / governance artefacts remain authoritative (no content changes without explicit reason).
- Runtime behavior (READ_ONLY vs LIVE execution gating) must remain unchanged.

## Rollback

If a migration step causes broad failures:
- revert the step
- add a compatibility shim (re-export module, maintain import paths)
- proceed with a smaller safe step
