
# 99_CODEX_MASTER_INSTRUCTION_BLOCK — E22 (COPY/PASTE)

File: `99_CODEX_MASTER_INSTRUCTION_BLOCK.md`
Title: E22 Codex Master Instruction Block
END marker: present at bottom

--- BEGIN INSTRUCTION BLOCK (COPY/PASTE TO CODEX) ---

You are implementing epoch: E22_STRATEGY_SCALABILITY_AND_ARBITRATION_LAYER.

CONSTRAINTS (LAW):
1) Additive changes only. Do not redesign core architecture. Wire E22 at the single canonical intent aggregation point.
2) Preserve authoritative run modes: SIM, PAPER, READ_ONLY, LIVE. Do not create new run modes.
3) Determinism is mandatory: stable arbitration outputs given same inputs (excluding timestamps/UUIDs).
4) Audit evidence is mandatory: write the E22 evidence directory with index + verdict.
5) No new runtime warnings (esp. un-awaited coroutine warnings).

STEP 0 — READ GOVERNANCE
- Read the operator-provided governance bundle for E22.
- Extract required contracts: scheduling, shared data coordination (minimal), intent arbitration, evidence.

STEP 1 — REALITY MAP
- Produce REALITY_MAP_E22.md: locate where strategy intents are created/aggregated and passed to risk/execution.

STEP 2 — GAP ANALYSIS
- Write GAP_ANALYSIS_E22.md: list missing pieces; choose minimal additive implementation.

STEP 3 — IMPLEMENTATION
Implement:
A) StrategyScheduler (priority + budgets)
B) IntentArbitrator (deterministic sorting + conflict rules + reason codes)
C) ArbitrationDecisionArtifact writer (json + md)
D) verification_scripts/verify_e22_strategy_scalability_and_arbitration.py (evidence writer)
E) Wire E22 into runtime at canonical point (intents -> E22 -> risk/execution)

STEP 4 — TESTS
Add unit/integration tests to validate:
- deterministic ordering
- conflict suppression reason codes
- budget breach behaviour

STEP 5 — MANDATORY VERIFICATION
Run:
1) python -m compileall -q src tests verification_scripts
2) python -m pytest -q
3) python verification_scripts/verify_e22_strategy_scalability_and_arbitration.py --allow-overwrite
4) python verification_scripts/system_integrity_and_capability_report.py --allow-overwrite

Record outputs under the E22 evidence directory.

STEP 6 — PR
Open a single PR with:
- code changes
- tests
- E22 evidence artifacts
- brief PR_VERIFICATION_REPORT.md summarizing command results and key outputs.

--- END INSTRUCTION BLOCK ---
END
