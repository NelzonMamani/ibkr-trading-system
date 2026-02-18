# PHASE 5 — Runtime Alignment Workplan

This workplan is executed by Codex with mandatory evidence.

## A. Baseline sanity

1. `python -m compileall src`
2. `pytest -q`

## B. Policy audit (governance lock active)

Run audit artifact generation and record counts:

- `python - <<'PY'
from src.metadata.strategy_policy_v2_audit import generate_audit_artifacts
r=generate_audit_artifacts()
print({v:sum(1 for x in r if x.verdict==v) for v in ['CERTIFIED','CONDITIONALLY_CERTIFIED','FAIL','INVALIDATED_PENDING_REVIEW']})
PY`

Expected:
- CERTIFIED == 20
- FAIL == 0
- INVALIDATED_PENDING_REVIEW == 0 (unless you intentionally mutated a policy file)

## C. Runtime alignment verification

### C1. “Policy import & registry” smoke test

Create / update a verification script (prefer `verification_scripts/verify_strategy_policy_v2_runtime_alignment.py`) that:

- Imports all strategies policy modules without side effects.
- Verifies `POLICY_V2` exists and matches required schema shape.
- Optionally serialises each policy to JSON-like dict (or asserts dataclass fields present) to confirm predictable structure.

### C2. Orchestrator boot per mode

For each run mode:
- SIM
- PAPER
- READ_ONLY
- LIVE (execution disabled)

Perform:
- Boot orchestrator / runtime manager.
- Run a minimal cycle (single iteration), allowing empty watchlists.
- Ensure:
  - No unhandled exceptions
  - No broker calls in SIM/READ_ONLY beyond permitted stubs
  - No trade submissions in LIVE unless explicitly enabled (must remain disabled)

Record logs.

### C3. Strategy selection path

If the runtime supports selecting a strategy set (single strategy vs all), run:
- P01
- One intrabar APPLICABLE sample (P02)
- One intrabar NOT_APPLICABLE sample (P04)
- One slow/long-horizon style (P19 or P04)

Ensure runtime can instantiate these without extra missing dependencies.

## D. Fixes (only if required)

If you find misalignment, you may:
- Add missing adapter hooks that read policy constraints.
- Add missing guards that prevent import-time broker calls.
- Add missing tests to enforce these invariants.

You must NOT:
- Change strategy policy content (except under controlled change control policy).
- Disable governance lock checks.

## E. Evidence

Write evidence to:
- `AUDIT_EVIDENCE/phase_5/`

Minimum:
- `compileall.log`
- `pytest.log`
- `policy_audit_counts.json`
- `runtime_alignment_report.json`
- `mode_boot_logs/` (one per mode)
