# PROGRAMME_EXECUTION_PLAN

## Purpose
Define the post-approval execution sequence for the Trading OS catalogue so work proceeds in a controlled, auditable order. This plan is planning-only and does not authorize execution.

## Preconditions (Mandatory)
- All documents in `TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST/` are read and accepted.
- The Reality Map, Capability Crosswalk, Truth Source Registry, Contracts, and Verification Runbook are complete and internally consistent.
- No changes have been made outside the catalogue during this planning stage.

## Global Ordering (Execution Stage)
1. **Catalogue Baseline Lock**
   - Freeze the catalogue documents as the canonical plan-of-record.
   - Confirm Truth Source Registry and Contracts match the codebase reality snapshot.
2. **Core Epoch Foundation (E0–E4)**
   - Establish non-negotiable system law, traceability, lifecycle, risk discipline, and market state quality.
3. **Execution Authority and Gating (E5–E7, E16)**
   - Ensure execution permissions, risk gates, and no-trade contexts are enforceable before strategy work.
4. **Regime, Analytics, Capital, Learning (E8–E12)**
   - Validate supporting subsystems that inform strategy selection and post-trade governance.
5. **Strategy Factory and Interfaces (E13–E20)**
   - Standardize strategy interfaces, certifications, and composition rules before new strategy onboarding.
6. **End-to-End Readiness (E21)**
   - Run full-system verification and simulation readiness checks.
7. **Metadata Epochs (M0–M10)**
   - Execute metadata epochs in parallel where dependencies allow, but never ahead of their linked core epoch dependencies.
8. **Strategy Epochs (P01–P20)**
   - Only once E13–E20 are certified and contracts are stable.

## Dependencies and Stop Rules
- **Dependency enforcement**: Any epoch that depends on a contract or registry must not proceed unless that contract is stable and registered.
- **Stop rule**: If verification fails or contracts diverge from implementation, pause execution, update catalogue, and re-verify.
- **No parallel execution**: Do not overlap epochs that share the same risk or execution surfaces.

## Verification Ladder
1. **Level 0 – Static checks**: compile, lint, and baseline tests.
2. **Level 1 – Component checks**: scanner, strategy, risk, execution, market data.
3. **Level 2 – Integration checks**: scanner → strategy → execution intent → risk gating.
4. **Level 3 – End-to-end checks**: simulation run, read-only live run, and full-mode parity validation.

## Evidence and Audit Expectations
- Every epoch must produce an evidence bundle (logs, commands run, outputs) saved into that epoch’s audit folder.
- Only evidence in the catalogue audit structure can be used for certification.

## Next-Stage Gate
Execution may begin only once this plan and all required catalogue artifacts are signed off by authority defined in the system constitution.

## Planning Stage Summary (Completion Indicator)
- **Complete**: Execution plan, reality map, capability crosswalk, truth source registry, contract set, and verification runbook are all defined and ready for execution stage.
- **Missing in underlying system**: Most capabilities are PARTIAL per the capability crosswalk; contracts exist in code but are not yet formalized against the canonical contract documents.
- **Next when execution begins**: Follow the ordering in this plan, validate contract expectations from `CONTRACTS/`, and run the verification ladder in `VERIFICATION_RUNBOOK.md` to certify each epoch.

[DEFERRED — HIGH PRIORITY]
MarketSessionContext implementation required after trade activation phase.

Trigger phrase:
"Resume Market Context Phase-Aware Refactor"
