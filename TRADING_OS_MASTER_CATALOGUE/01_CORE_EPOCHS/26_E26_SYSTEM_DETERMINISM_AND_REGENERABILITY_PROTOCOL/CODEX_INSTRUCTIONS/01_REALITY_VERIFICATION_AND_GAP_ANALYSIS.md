# 01 — Reality Verification and Gap Analysis

## Objective
Prove (with code + evidence) that runtime artefacts can be safely deleted and recreated.

## Reality checks (perform first)
1. Identify current runtime roots (existing code):
   - DB path resolution (`data/ibkr_system.db` or similar)
   - logs root
   - output root
2. Identify existing reset/backup tooling:
   - `src/storage/db_admin.py` commands (backup/reset)
   - any trace/log writers
3. Identify where directories are assumed to exist (potential gaps).
4. Identify any tests that rely on persistent runtime artefacts.

## Expected gaps
- No single canonical “artefact registry” in code.
- No unified purge tool across logs/output/db/caches.
- Paths may be hard-coded and not overrideable for CI/tmp.
- No “clean clone rebuild” verification script/test producing E26 evidence.

## Output of this step
Create `AUDIT_EVIDENCE/E26_gap_analysis.json` containing:
- detected runtime roots
- missing capabilities
- list of files/dirs produced by a typical run
- proposed minimal patch list
