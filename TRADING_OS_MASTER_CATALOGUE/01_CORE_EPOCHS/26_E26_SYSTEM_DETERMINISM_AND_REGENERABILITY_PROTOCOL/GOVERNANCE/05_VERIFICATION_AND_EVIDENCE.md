# 05 — Verification and Evidence

## Verification commands (minimum)
E26 certification requires these to pass:

1. `python -m compileall src`
2. `pytest -q`
3. Clean-room rebuild test:
   - delete runtime artefacts
   - run bootstrap
   - run orchestrator (SIM or READ_ONLY, 1 cycle)
4. Purge protocol tests:
   - LIGHT purge leaves DB intact
   - HARD purge removes DB and system recreates it
5. Evidence generation:
   - `AUDIT_EVIDENCE/E26_regenerability_report.json`
   - `AUDIT_EVIDENCE/E26_artifact_registry_snapshot.json`

## Certification updates
- Update `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md` with `E26: CERTIFIED`.
- If applicable, update integrity reconciliation evidence indexes.
