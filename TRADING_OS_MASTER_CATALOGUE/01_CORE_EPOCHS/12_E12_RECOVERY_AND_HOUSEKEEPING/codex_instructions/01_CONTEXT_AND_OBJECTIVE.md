## Context

The system produces logs, traces, reports, watchlists, caches, and a growing SQLite DB.
We have observed DB bloat during scanner troubleshooting (~70MB+), requiring admin tools.

## Objective

Certify and complete a governed housekeeping capability so an operator can:
- Backup / restore / reset the DB
- Delete event logs and generated artefacts
- Clean caches
- Identify and remove legacy artefacts under documentation

Safety:
- No destructive action during active LIVE execution
- LIVE must transition to READ_ONLY or STOPPED first
- All destructive actions must be traceable