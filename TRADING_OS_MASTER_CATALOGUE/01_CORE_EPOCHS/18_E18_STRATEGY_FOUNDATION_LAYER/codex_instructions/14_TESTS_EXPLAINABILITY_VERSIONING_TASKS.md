# E18 — TESTS, EXPLAINABILITY, VERSIONING TASKS

Source of truth:
- governance/20_TESTABILITY_EXPLAINABILITY_VERSIONING.md
- governance/22_CERTIFICATION_CRITERIA.md

Task A — Unit tests (mandatory)
- Add deterministic unit tests for ALL foundation primitives.
- Tests must not rely on live IBKR connectivity.
- Provide golden OHLCV sequences for candle recognizers and trigger detectors.

Task B — Explainability hooks
- Implement optional fields describing why a primitive passed/failed.
- Must not be required for correctness (safe to omit in performance modes).
- Ensure explainability is stable enough for learning and debugging.

Task C — Versioning and compatibility
- Introduce explicit foundation version (single source of truth).
- Ensure components declare compatibility.
- Implement version-reset cache invalidation keyed on foundation version.
- Ensure semantic_name stability is preserved over refactors.

Deliverables:
- Foundation version module + tests
- Cache invalidation tests
- Compile-time checks for registry completeness

END
