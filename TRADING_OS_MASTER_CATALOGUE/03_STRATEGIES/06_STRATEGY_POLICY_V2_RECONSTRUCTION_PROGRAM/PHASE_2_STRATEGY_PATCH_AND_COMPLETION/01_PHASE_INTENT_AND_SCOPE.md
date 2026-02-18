# 01 — Phase Intent & Scope

## Intent
Reconstruct all strategies P02–P20 so each strategy’s `StrategyPolicyV2` is:
- **Non-default-only**
- **Institutionally auditable** across Matrix V2 domains D0–D14
- **Operationally coherent** (even if implementation is staged later)

This phase is *policy reconstruction*, not full execution-engine implementation.

## In Scope
- Editing `src/strategies/*/strategy_policy_v2.py` for P02–P20
- Adding any strategy-local supporting constants or helpers that are purely policy composition
- Updating catalogue governance artifacts that reflect the institutional state (matrix/report)
- Adding/adjusting tests **only if** necessary to align with Matrix V2 intent (avoid loosening)

## Out of Scope
- Refactoring runtime/orchestrator/broker layers
- Changing the Matrix V2 enforcement logic to “pass” incomplete strategies
- Large architecture redesign of StrategyPolicyV2 schema

## Guardrails (Non-Negotiable)
- P01 remains CERTIFIED (non-regression)
- Phase 2 must not weaken or bypass institutional controls
- If a domain is truly inapplicable, it must be declared with explicit “NOT_APPLICABLE” markers and rationale
- Maintain consistent semantics across strategies for:
  - run modes (SIM/PAPER/READ_ONLY/LIVE)
  - session semantics (PRE/RTH/AH/CLOSED)
  - data-quality rejection/pause behaviour
  - safety escalation path
