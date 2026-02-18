# PHASE 1 — Institutional Audit Engine Upgrade (ISGS-V2)

Generated (UTC): 2026-02-18T19:25:56Z

## Purpose
Upgrade the StrategyPolicyV2 certification system from a **structural presence check** to an **institutional-grade governance audit**.

This phase delivers:
- A **control framework** (domains, controls, severities)
- An **Institutional Audit Matrix V2** (what is evaluated and how)
- **Deterministic PASS/FAIL criteria**
- **Minimum section requirements** (avoid “default-only” policies)
- **Audit enforcement logic** requirements for implementation
- **Test enforcement requirements** (pytest-based gates)
- **System-state integration** rules (M5 + E23 alignment)
- A single Codex instruction block to implement the upgrade safely

## In Scope
- StrategyPolicyV2 objects defined in: `src/strategies/*/strategy_policy_v2.py`
- StrategyPolicyV2 schema types in: `src/strategy_policy_v2/policy_v2.py`
- Metadata tests in: `tests/metadata/*`
- Catalogue governance artifacts in:
  - `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/04_STRATEGY_CERTIFICATION_AND_GOVERNANCE/*`
  - `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/06_STRATEGY_POLICY_V2_RECONSTRUCTION_PROGRAM/*`

## Out of Scope (Phase 1)
- Implementing missing strategy logic in P02–P20 (Phase 2)
- Runtime wiring (execution, broker, live routing)
- Performance optimization, parameter calibration, ML/regime inference

## Success Criteria
A strategy policy audit must be able to:
1. **Detect completeness** across institutional domains (selection→setup→trigger→confirm→execute→risk→exit→data→failure modes).
2. Produce a **stable, deterministic report** with:
   - domain verdicts
   - missing controls
   - minimum-section breaches
   - severity classification
3. Block certification when:
   - critical controls missing
   - a policy is “default-only”
   - required governance sections are absent
4. Integrate into `SYSTEM_STATE_CERTIFIED.md` and E23 reconciliation without breaking existing certified epochs.

## Deliverables
The implementation outcome of this phase (Codex output) must produce:
- Updated audit matrix: `.../STRATEGY_AUDIT_MATRIX_V2.md`
- Updated report: `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/STRATEGY_CERTIFICATION_REPORT.md`
- Updated system state files:
  - `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md`
  - repo-root `SYSTEM_STATE_CERTIFIED.md`
- Updated/added tests in `tests/metadata/` that enforce institutional requirements

## Non-Regression Requirements
- P01 must remain CERTIFIED.
- Existing compileall + pytest must pass.
- No changes to run-modes, broker wiring, or strategy runtime behavior.
