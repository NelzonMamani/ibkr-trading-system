# 99_CODEX_MASTER_INSTRUCTION_BLOCK.md
# COPY/PASTE MASTER INSTRUCTION BLOCK FOR CODEX — E23
Last updated: 2026-02-13

FILE: 99_CODEX_MASTER_INSTRUCTION_BLOCK.md
TITLE: Implement E23_PLATFORM_INTEGRITY_AND_RECONCILIATION_LAYER (Automated Self-Sanitiser)

You are Codex operating on repo: ibkr-trading-system.

GOAL:
Implement 23_E23_PLATFORM_INTEGRITY_AND_RECONCILIATION_LAYER as an automated platform self-sanitiser.
It must discover, verify, reconcile drift, auto-fix safely, regenerate global truth artifacts, and output a single platform verdict.

IMPORTANT BEHAVIOR:
- Automate aggressively: run compileall, pytest, boot cycles, E23 runner; iterate fixes until coherent.
- Prefer minimal additive fixes; do not redesign.
- Preserve trade safety invariants (READ_ONLY and PAPER must never route unsafe LIVE orders).
- When conflicts exist: follow truth precedence and record deprecation/supersession decisions in DEPRECATION_LEDGER.md.
- Regenerate SYSTEM_STATE_CERTIFIED.md from evidence so it cannot be stale.

REQUIRED OUTPUTS (repo files):
1) src/integrity/e23_platform_integrity_runner.py (or aligned path) with CLI: python -m src.integrity.e23
2) src/integrity/epoch_verification_registry.yaml (E0..E22, M0..M10, P01..P04)
3) Generated/managed docs (location consistent with repo conventions):
   - SYSTEM_STATE_CERTIFIED.md (regenerated)
   - platform_integrity_state.json
   - DEPRECATION_LEDGER.md
   - RECONCILIATION_REPORT.md
4) Audit evidence outputs under an evidence folder (append-only).

IMPLEMENTATION STEPS:
A) Locate existing integrity/certification scripts (system_integrity_and_capability_report, verify_system_reality_v2, etc.).
   Reuse and extend rather than duplicating.
B) Implement E23 runner:
   - discover catalogue inventory
   - load verification registry
   - run baseline checks
   - run drift detectors
   - auto-fix safe drift
   - re-verify (loop max 5)
   - regenerate global truth artifacts
   - write audit evidence + final verdict JSON
C) Add hard drift checks (as code checks executed by E23) for:
   - canonical run modes = SIM/PAPER/READ_ONLY/LIVE
   - no unsafe routing in READ_ONLY/PAPER
   - risk engine remains ultimate permission gate
D) Update docs from evidence; do not leave stale status tables.

MANDATORY VERIFICATION (run and capture evidence):
- python -m compileall src
- pytest -q
- python -m src.integrity.e23
- python -m src.main --mode SIM --cycles 1
- python -m src.main --mode PAPER --cycles 1
- python -m src.main --mode READ_ONLY --cycles 1

SUCCESS CRITERIA:
- platform_integrity_state.json indicates coherent readiness (not DRIFT_DETECTED / INVARIANT_VIOLATION)
- regenerated SYSTEM_STATE_CERTIFIED.md consistent with verdict JSON
- deprecation ledger exists and lists reconciliation decisions (or explicitly empty)

END
