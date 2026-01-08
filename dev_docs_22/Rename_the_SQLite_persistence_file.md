Rename_the_SQLite_persistence_file.md
TASK
Rename the SQLite persistence file from ibkr_system.sqlite to ibkr_system.db.

SCOPE
- Update the configured storage path everywhere.
- Do NOT change schemas, logic, or persistence behavior.
- Ensure existing data remains readable.

EXPECTED RESULT
- Database file name is ibkr_system.db
- Storage logs show the new path
- No behavior changes