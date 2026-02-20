# 01 — Intent and Scope

## Intent
Establish a canonical, testable protocol that guarantees the platform can be:
1. **Purged** of runtime artefacts (weight shedding)
2. **Rebuilt** deterministically from a clean state (regenerability)
3. **Restored** from optional backups (operator-controlled continuity)
4. **Verified** via repeatable commands producing evidence artifacts

This epoch makes “delete `data/`, `logs/`, `output/` and still run” a **certified invariant**.

## In scope
- Define a **Runtime Artefact Registry** (classification + locations).
- Define a **Rebuild From Zero Protocol** (bootstrap sequence).
- Define **Purge/Reset** semantics for runtime artefacts:
  - DB (SQLite), WAL/SHM, backups
  - logs (jsonl), traces
  - outputs (watchlists, trade_store, reports)
  - caches (float/news caches if present)
- Define **Backup/Restore** semantics (explicit operator action).
- Add deterministic verification (tests + scripts) demonstrating:
  - clean-room rebuild
  - safe purge
  - optional restore
- Evidence files + certification updates.

## Explicitly not in scope
- Large-scale codebase refactors (that is E25).
- Strategy logic changes.
- Dependency upgrades / deprecation cleanup (separate technical debt epoch).
- Live broker behavioural changes (no risk regression).

## Definitions
- **Canonical Source**: git-tracked architecture + catalogue + code.
- **Runtime Artefact**: generated during execution; deletable and regenerable.
- **Determinism**: same inputs/config → same artifacts/decisions within defined tolerances.
- **Regenerability**: the system can recreate required runtime state from canonical source + config.
