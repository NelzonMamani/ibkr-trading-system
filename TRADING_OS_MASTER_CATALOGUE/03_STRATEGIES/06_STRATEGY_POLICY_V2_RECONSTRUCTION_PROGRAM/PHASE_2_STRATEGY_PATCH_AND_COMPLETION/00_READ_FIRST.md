# PHASE 2 — Strategy Patch & Completion (Matrix V2 Reconstruction)

Generated (UTC): 2026-02-18T21:00:41Z

## Purpose
Phase 1 activated the Institutional Audit Engine (Matrix V2) and correctly set:

- `STRATEGY_CERTIFICATION_PHASE: RECONSTRUCTION_REQUIRED`
- `STRATEGY_CERTIFICATION_LEVEL: INSTITUTIONAL_MATRIX_V2_ACTIVE`

Phase 2 is the **reconstruction programme** that upgrades strategies **P02–P20** from *default-only* placeholders to **institutionally valid StrategyPolicyV2 artifacts**, meeting Matrix V2 minima and enabling the platform to progress.

## Your declared mode (B)
You selected **B) Fully institutionalise each strategy until CERTIFIED**.

That means:
- Target verdict per strategy: **CERTIFIED** (not merely CONDITIONALLY_CERTIFIED)
- Any *NOT_APPLICABLE* declarations must be explicit, justified, and stable
- Every domain D0–D14 must be addressed (PASS or legitimate NOT_APPLICABLE)

## Primary Outputs of Phase 2
1. For each strategy `src/strategies/<slug>/strategy_policy_v2.py`, implement a **complete** `POLICY_V2`.
2. Ensure `pytest -q` passes (institutional tests).
3. Generate updated audit artifacts:
   - `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/04_STRATEGY_CERTIFICATION_AND_GOVERNANCE/STRATEGY_AUDIT_MATRIX_V2.md`
   - `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/STRATEGY_CERTIFICATION_REPORT.md`

## Read Order
1) `01_PHASE_INTENT_AND_SCOPE.md`  
2) `02_RECONSTRUCTION_WORKFLOW.md`  
3) `03_POLICY_COMPLETION_TEMPLATE.md`  
4) `04_DOMAIN_BY_DOMAIN_PATCH_GUIDE.md`  
5) `05_ACCEPTANCE_CRITERIA.md`  
6) `06_VERIFICATION_AND_EVIDENCE_REQUIREMENTS.md`  
7) `99_CODEX_MASTER_INSTRUCTION_BLOCK.md`  
