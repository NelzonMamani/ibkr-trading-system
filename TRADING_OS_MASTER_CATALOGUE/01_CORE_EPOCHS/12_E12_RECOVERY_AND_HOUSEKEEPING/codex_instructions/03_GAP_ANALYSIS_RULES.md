## Gap Analysis Rules

Allowed (additive):
- Add missing housekeeping CLI commands
- Add safe guards (mode gating, confirmation prompts)
- Add log/artefact purge functions
- Add documentation files listing legacy artefacts
- Add tests for safe behavior (no LIVE destructive ops)

Forbidden:
- Silent deletion in runtime
- Auto-cleanup in LIVE cycles
- Removing governance artefacts
- Refactoring unrelated systems

If forbidden change is needed, STOP and report.