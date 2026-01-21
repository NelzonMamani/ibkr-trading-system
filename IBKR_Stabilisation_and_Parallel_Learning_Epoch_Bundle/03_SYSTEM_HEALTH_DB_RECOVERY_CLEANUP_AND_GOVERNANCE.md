# 03 — SYSTEM HEALTH, DB RECOVERY, CLEANUP, AND GOVERNANCE UPDATES

## Objective (priority order)
1. System trades live safely (LIVE_MICRO, 1 share, real data).
2. System recovers from failure (DB deletion, laptop off, crash).
3. System is observable (health checks, prints, minimal reports).
4. System learns in parallel (never mutates live logic).
5. System remains governable (Ross baseline never overwritten).

This phase focuses on **operational robustness**, not new strategy logic.

---

## Part A — Startup health & safety checks (must be printed every run)
Add/confirm a “startup banner” that prints:
- run mode, session allowlist, replay mode
- execution flags:
  - EXECUTION_ENABLED
  - IBKR_READONLY_ENABLED
  - IBKR_ORDER_TRANSLATION_ENABLED
  - IBKR_ORDER_SUBMISSION_ENABLED
- live micro guardrails:
  - required ack
  - 1-share enforcement
  - max positions
  - daily max loss
- broker connectivity config:
  - host/port/clientId
  - market data type
- storage:
  - sqlite path
  - schema version (if applicable)
  - db file exists: Y/N

This is in addition to existing `[CONFIG] Resolved runtime configuration` output.

### Acceptance
- On each run, the banner appears **once** at startup, before the first cycle.

---

## Part B — DB recovery: “delete db and still boot”
### Required behaviour
If the SQLite DB file is missing (or deleted intentionally):
1. The system must re-create the DB file.
2. It must create the full schema required for this version.
3. It must not crash due to missing columns/tables.
4. It must be fast (“ASAP”): do not run expensive backfills at boot.

### Implementation
- Centralise schema creation/migrations in a single module:
  - e.g., `src/storage/schema.py`
- Introduce a schema version table (if not already):
  - `schema_meta(version int, applied_at_utc text)`
- On boot:
  - open DB
  - if schema missing or version behind: apply migrations
  - commit
- If you already have migrations:
  - ensure they run automatically on boot.

### Tests
- Add a test that:
  - deletes/creates a temp db path
  - boots StorageEngine
  - asserts required tables exist

---

## Part C — Minimal daily operational report trigger (non-learning)
This is NOT the full learning epoch; it is the operator’s sanity check.

### Required behaviour
At shutdown (graceful or panic), if there were trades or intents during the day:
- write a compact summary to:
  - console
  - and optionally `data/reports/ops/YYYY-MM-DD_ops_summary.json`

Include:
- counts (scanned symbols, watchlist size, focus size)
- trade counts open/closed
- realised PnL, commissions, max loss status
- circuit breaker triggers
- last watchlist hash

Do not block shutdown if report writing fails.

---

## Part D — Cleanup (tidy repo without breaking workflows)
### Rules
- Do not delete governance files.
- Do not delete scripts referenced in docs/tests.
- Remove only clearly obsolete one-off scanner scripts or duplicates **if**:
  - they are unused
  - and not referenced by tests or documentation

### Required output
- A short “cleanup report” listing:
  - removed files (paths)
  - justification (unused, superseded)
  - grep evidence (no imports/references)

---

## Part E — Governance updates (only AFTER Parts A–D are stable)
Update:
- `SYSTEM_STATE.md`
- `README.md`
- any “Phase/Epoch status” doc that is used as the single source of truth

Must reflect:
- LIVE_MICRO scanner now uses market data safely
- watchlist lifecycle implemented
- DB auto-recovery at boot
- mandatory verification commands are the official gate

---

## Mandatory Verification Commands (must run and report)
After completing this doc, run the commands in `99_MANDATORY_VERIFICATION_COMMANDS.md`.

If any command fails:
- fix the failure
- rerun the full suite
- only then proceed to the Learning Epoch docs (10+)

END
