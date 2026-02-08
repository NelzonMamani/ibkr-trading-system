## Implementation Tasks (only if gaps exist)

A) DB ADMIN
- Ensure commands exist:
  - status
  - backup (timestamped)
  - hard-reset (drop/recreate)
  - optional: purge-events / purge-traces / purge-reports
- Ensure DB path discovery works from any cwd (verification_scripts included)

B) ARTEFACT PURGE
- Provide operator tools to delete:
  - logs/trace_*.jsonl
  - output/verification/*.log
  - output/watchlists/*.txt
  - data/reports/*
  - data/cache/*
- Ensure purge targets are explicit and documented

C) MODE SAFETY
- Enforce: LIVE must be READ_ONLY or STOPPED for destructive ops
- PAPER allowed but still trace actions

D) LEGACY DOCUMENTATION
- Create a doc listing legacy folders/artifacts and removal status:
  - XXX TRADING_OS_MASTER_CATALOGUE
  - old troubleshooting backups
  - superseded scripts

E) TRACEABILITY
- Every housekeeping action emits a record to:
  - a housekeeping log file
  - and/or DB audit table (if available)