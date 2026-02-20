# E25 — Architecture Realignment (Read First)

**Epoch ID:** E25_ARCHITECTURE_REALIGNMENT  
**Date:** 2026-02-20  
**Purpose:** Establish an institutional-grade repository architecture with explicit boundaries, import rules, and regenerability assumptions.

This epoch is **structural** (architecture), not strategic (alpha) and not operational (deployment).  
Primary success condition: **the system remains green** (compile + tests) while code boundaries become unambiguous.

## Non-negotiables

- Keep the **domain and business logic** in `src/` (clean core).
- Enforce **adapter boundaries** (IBKR, files, DB, CLI, GUI) so they cannot leak into core modules.
- Ensure **generated artifacts** (DB, watchlists, logs, evidence) are not required to import core code.
- Provide a **migration map** and compatibility shims if required.
- Preserve current system behavior and test suite pass.

## Deliverables

- Target architecture model (tree + boundary rules)
- Dependency rules and forbidden couplings
- Migration and acceptance criteria
- Evidence updates (indices + status)

Proceed to `01_TARGET_ARCHITECTURE_MODEL.md`.
