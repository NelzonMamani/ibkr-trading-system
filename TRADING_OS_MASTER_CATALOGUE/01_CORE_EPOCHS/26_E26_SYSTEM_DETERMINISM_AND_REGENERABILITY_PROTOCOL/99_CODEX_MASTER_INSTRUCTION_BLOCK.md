# 99 — CODEX MASTER INSTRUCTION BLOCK (E26)

FILE: TRADING_OS_MASTER_CATALOGUE/01_CORE_EPOCHS/26_E26_SYSTEM_DETERMINISM_AND_REGENERABILITY_PROTOCOL/CODEX_INSTRUCTIONS/99_CODEX_MASTER_INSTRUCTION_BLOCK.md
TITLE: Execute E26 — System Determinism and Regenerability Protocol
END MARKER REQUIRED: YES (write END at bottom)

## MISSION
Implement E26 as specified in GOVERNANCE and CODEX_INSTRUCTIONS:
- A canonical runtime artefact registry
- Deterministic bootstrap
- Safe purge/reset (LIGHT/STANDARD/HARD)
- Optional backup/restore
- Clean-room rebuild verification (tests + script)
- Evidence + certification updates

## HARD RULES
- Do NOT move large directories.
- Do NOT change strategy logic.
- Do NOT require IBKR connectivity for tests.
- Do NOT introduce import-time side effects.

## STEPS (execute in order)
1. Reality verification + gap analysis; write `AUDIT_EVIDENCE/E26_gap_analysis.json`.
2. Implement `src/runtime/paths.py` with env overrides and safe repo-root checks.
3. Implement `src/runtime/bootstrap.py` (idempotent directory + DB schema bootstrap).
4. Implement `src/runtime/artifact_registry.py` + JSON snapshot export.
5. Implement `src/runtime/regen.py` CLI (`python -m src.runtime.regen ...`) providing:
   - bootstrap
   - purge (LIGHT/STANDARD/HARD with safety guards + --confirm)
   - backup/restore (manifested archives)
   - snapshot-registry
6. Wire bootstrap into orchestrator/scanner/CLI entrypoints (minimal, compatibility-first).
7. Add tests using `tmp_path` and env overrides:
   - clean-room rebuild
   - purge level semantics
8. Add `verification_scripts/phase6_regenerability_cleanroom.py` to run the protocol and emit E26 evidence.
9. Run mandatory verification commands; capture outputs into `AUDIT_EVIDENCE/E26_regenerability_report.json`.
10. Update `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md` with E26 CERTIFIED.

## MANDATORY OUTPUTS
- Green `pytest -q`
- Evidence JSONs created
- Orchestrator READ_ONLY cycle runs after HARD purge + bootstrap
- `.gitignore` prevents runtime artifacts from being committed

END
