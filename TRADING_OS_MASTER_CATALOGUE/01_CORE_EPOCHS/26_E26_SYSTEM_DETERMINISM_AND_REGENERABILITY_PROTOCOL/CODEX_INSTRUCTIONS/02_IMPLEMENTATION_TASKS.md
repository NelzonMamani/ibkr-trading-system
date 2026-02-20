# 02 — Implementation Tasks (Additive + Minimal)

## Task A — Runtime paths authority
Create `src/runtime/paths.py` (or equivalent) providing:
- `get_data_dir()`, `get_logs_dir()`, `get_output_dir()`
- env overrides: `IBKR_OS_DATA_DIR`, `IBKR_OS_LOG_DIR`, `IBKR_OS_OUTPUT_DIR`
- safe defaults: `data`, `logs`, `output`
- helper: `resolve_repo_root()` (avoid deleting outside project)

## Task B — Artefact registry
Create `src/runtime/artifact_registry.py` defining:
- categories (CANONICAL / REGENERABLE / SEMI_PERSISTENT)
- registry entries with:
  - root path
  - glob patterns
  - purge level applicability (LIGHT/STANDARD/HARD)
  - backup scope inclusion
- export function to snapshot registry to JSON.

## Task C — Bootstrap (idempotent)
Create `src/runtime/bootstrap.py`:
- creates dirs (data/logs/output)
- ensures DB schema exists (reuse existing schema creation path; do not fork logic)
- no network/broker calls

Ensure orchestrator and CLI entrypoints call bootstrap early.

## Task D — Purge/reset tool
Create CLI module: `python -m src.runtime.regen --help`
Commands:
- `bootstrap`
- `purge --level {LIGHT,STANDARD,HARD} [--confirm]`
- `backup [--label ...]`
- `restore --archive <path> [--force]`
- `snapshot-registry` (writes audit JSON)

Requirements:
- refuses dangerous paths (must be under repo runtime roots)
- writes audit log entry
- prints concise summary

## Task E — Tests & verification
Add tests:
- `tests/test_e26_cleanroom_rebuild.py`
- `tests/test_e26_purge_levels.py`

Use `tmp_path` and env overrides to avoid touching real user runtime directories.

Add verification script:
- `verification_scripts/phase6_regenerability_cleanroom.py`
that:
- runs purge in tmp dirs
- runs orchestrator 1 cycle in READ_ONLY
- writes `AUDIT_EVIDENCE/E26_regenerability_report.json`

## Task F — Git hygiene
Confirm `.gitignore` covers runtime artifacts:
- output/
- logs/
- data/*.db, *.sqlite, *-wal, *-shm
- data/**/*.jsonl, data/**/*.log

Do not remove existing ignore rules; extend as needed.
