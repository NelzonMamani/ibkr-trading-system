# PHASE 5 — Evidence Requirements

All evidence must be committed and reproducible.

## Required files (minimum)

Under `AUDIT_EVIDENCE/phase_5/`:

1. `compileall.log`
2. `pytest.log`
3. `policy_audit_counts.json`
4. `runtime_alignment_report.json`
5. `stress_runs.json`
6. `fault_injection_log.md`
7. `mode_boot_logs/`
   - `SIM.log`
   - `PAPER.log`
   - `READ_ONLY.log`
   - `LIVE.log`

## Report schema (runtime_alignment_report.json)

Suggested structure:

```json
{
  "generated_at_utc": "...",
  "git_commit": "...",
  "policy_audit": {
    "CERTIFIED": 20,
    "FAIL": 0,
    "INVALIDATED_PENDING_REVIEW": 0
  },
  "modes": {
    "SIM": {"boot_ok": true, "cycle_ok": true, "notes": []},
    "PAPER": {"boot_ok": true, "cycle_ok": true, "notes": []},
    "READ_ONLY": {"boot_ok": true, "cycle_ok": true, "notes": []},
    "LIVE": {"boot_ok": true, "cycle_ok": true, "execution_enabled": false, "notes": []}
  },
  "stress": {"iterations": 50, "failures": 0},
  "fault_injection": {"scenarios": 5, "failures": 0}
}
```

## Evidence quality rules

- Logs must be from fresh runs (not stale).
- If a run fails, capture stack trace and fix; do not delete evidence—append to the log and re-run.
- Keep runtime evidence **mode-separated**.
