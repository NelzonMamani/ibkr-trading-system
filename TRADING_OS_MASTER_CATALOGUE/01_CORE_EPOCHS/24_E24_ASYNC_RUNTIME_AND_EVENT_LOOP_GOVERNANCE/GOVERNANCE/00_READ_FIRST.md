# E24 — Async Runtime & Event Loop Governance (GOVERNANCE)

**Catalogue Path**
`TRADING_OS_MASTER_CATALOGUE/01_CORE_EPOCHS/24_E24_ASYNC_RUNTIME_AND_EVENT_LOOP_GOVERNANCE/`

**Generated:** 2026-02-19T00:35:32Z

## Purpose of this bundle
This GOVERNANCE bundle defines the institutional-grade **async runtime law** for the Trading OS:
- deterministic event-loop lifecycle across **SIM / PAPER / READ_ONLY / LIVE**
- import-time safety (no implicit loop acquisition)
- test-collection safety (pytest must not crash at import time)
- IBKR ecosystem compatibility (ib_insync / eventkit and downstream dependencies)
- auditability and evidence requirements

## Read Order
1. `01_INTENT_AND_SCOPE.md`
2. `02_CANONICAL_RUNTIME_MODEL.md`
3. `03_INVARIANTS_AND_FAILURE_MODES.md`
4. `04_VERIFICATION_AND_EVIDENCE.md`
5. `05_ACCEPTANCE_CRITERIA.md`

## Non-goals
- Redesign of strategies, risk model, scanner policy, or portfolio doctrine.
- Large refactors of file structure or epoch renaming.
- Swapping broker libraries (unless required as a minimal compatibility shim).

