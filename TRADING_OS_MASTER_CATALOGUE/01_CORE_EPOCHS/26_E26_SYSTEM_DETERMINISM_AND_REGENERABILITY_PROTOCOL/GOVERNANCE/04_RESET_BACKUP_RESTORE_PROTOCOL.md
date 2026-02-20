# 04 — Reset / Backup / Restore Protocol

## Purge levels
E26 defines purge levels as a stable public API.

### PURGE_LEVEL=LIGHT
- Delete `logs/` and `output/` only.
- Do not touch DB.

### PURGE_LEVEL=STANDARD
- Delete `logs/`, `output/`
- Delete transient caches
- Vacuum DB (optional), keep DB schema + content

### PURGE_LEVEL=HARD
- Delete `logs/`, `output/`
- Delete DB files (`*.db`, `*.sqlite`, `*-wal`, `*-shm`)
- Delete caches and generated reports
- Recreate empty DB schema on next bootstrap

## Backup protocol
Backups are operator-controlled and must:
- Create a timestamped archive under `data/backups/`
- Include DB + selected Category 3 JSON artifacts (regime baselines, etc.)
- Record a manifest: file sizes, sha256, timestamp, tool version

## Restore protocol
Restore must:
- Require explicit `--confirm` or `--force` to avoid accidents
- Validate manifest hashes
- Refuse to restore into a non-empty target unless forced
- Be idempotent where possible

## Bootstrap protocol (rebuild-from-zero)
Bootstrap must:
- Create required directories
- Create DB schema if missing
- Create empty output/log directories
- Never touch broker connectivity

## Safety invariants
- Purge tooling must refuse to operate outside repo root unless explicitly allowed.
- Purge must never delete `src/` or `TRADING_OS_MASTER_CATALOGUE/`.
- All destructive operations must be logged with an audit record.
