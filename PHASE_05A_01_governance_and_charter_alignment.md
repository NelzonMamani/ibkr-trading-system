# PHASE_05A_01_governance_and_charter_alignment

Date: 2026-01-15

## Objective
Update governance-facing documentation to eliminate ambiguity and prevent scope drift during Epoch 5 implementation.

This phase is documentation-only and must not introduce trading logic.

## Inputs (Must Read)
- SYSTEM_CONSTITUTION.md
- README.md
- SYSTEM_STATE.md
- EPOCH_05_GOVERNANCE.md

## Tasks
1. Ensure README.md clearly states:
   - Ross Momentum is first-class (intraday momentum class)
   - Epoch model and boundaries
   - Explicit isolation of Epoch 6 (Buffett; not in Epoch 5)
   - Run modes (SIM / READONLY / LIVE_1SHARE)

2. Ensure SYSTEM_STATE.md clearly states:
   - Epoch 4 closed
   - Epoch 5 active
   - Epoch 6 future and isolated
   - “Frozen vs plastic” and operator console expectations

3. Create or update RUNBOOK.md:
   - exact run commands for scanner standalone and orchestrator (SIM/READONLY/LIVE_1SHARE)
   - troubleshooting for common issues (imports, IBKR connection, missing data)

## Allowed Files (Strict)
- README.md
- SYSTEM_STATE.md
- RUNBOOK.md

## Commands (Optional)
No mandatory commands in this phase.

## Acceptance Checklist
- README.md and SYSTEM_STATE.md contain no contradictions with SYSTEM_CONSTITUTION.md.
- README.md contains clear epoch boundaries and run modes.
- SYSTEM_STATE.md contains operator console expectations for K and M lists.
- RUNBOOK.md contains copy/paste run commands.

## Rollback Rule
If any change introduces ambiguity or contradicts higher governance documents, revert and restate with simpler wording.

END.
