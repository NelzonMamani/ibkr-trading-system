## Database Governance

Explicitly allowed:
- Full DB backup
- Full DB reset (drop & recreate)
- Selective purge of logs/events tables

Rationale:
During scanner debugging, DB growth exceeded 70MB.
Controlled reset is required for sustainability.