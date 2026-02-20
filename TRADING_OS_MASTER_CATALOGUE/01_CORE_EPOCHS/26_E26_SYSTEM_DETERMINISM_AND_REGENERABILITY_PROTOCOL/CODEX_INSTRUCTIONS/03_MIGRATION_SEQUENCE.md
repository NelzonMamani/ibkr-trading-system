# 03 — Migration Sequence (Safe Order)

1. Implement `src/runtime/paths.py` and wire into existing path consumers (DB/log/output).
2. Implement `bootstrap.py` and call from:
   - orchestrator main entry
   - scanner entry
   - CLI tools that produce runtime artefacts
3. Implement `artifact_registry.py` based on actual observed artefacts.
4. Implement `regen` CLI with purge/backup/restore using registry and safety guards.
5. Add tests using `tmp_path` + env overrides.
6. Add `verification_scripts/phase6_regenerability_cleanroom.py`.
7. Add evidence artifacts and update catalogue certification state.

Rollback safety:
- If any step introduces instability, revert only that step; keep others intact.
- Avoid moving folders; prefer shims and wrappers.
