# E26 — SYSTEM DETERMINISM AND REGENERABILITY PROTOCOL (GOVERNANCE)

## Read order
1. 01_INTENT_AND_SCOPE.md
2. 02_DETERMINISM_MODEL.md
3. 03_RUNTIME_ARTIFACT_CLASSIFICATION.md
4. 04_RESET_BACKUP_RESTORE_PROTOCOL.md
5. 05_VERIFICATION_AND_EVIDENCE.md
6. 06_ACCEPTANCE_CRITERIA.md

## Purpose
E26 institutionalises **rebuild-from-zero determinism** and **weight shedding** for the Trading OS:
- Any runtime artefact (DB/logs/output/watchlists/caches) can be deleted safely.
- The system can be reconstituted deterministically from a clean clone.
- Runtime state is treated as **disposable**; backups are optional and explicit.
