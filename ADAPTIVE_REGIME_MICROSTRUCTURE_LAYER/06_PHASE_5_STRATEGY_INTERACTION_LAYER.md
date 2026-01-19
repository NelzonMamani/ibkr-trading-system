# Phase 5 — Strategy Interaction Layer (Policy Application)
Last updated: 2026-01-19

## Objective
Use regime snapshots to influence strategy selection/weighting without mutating rules.

## Deliverables
1) src/regime/policy.py
Implement RegimePolicy which converts snapshot → decision:
- eligible_strategies (optional; ENABLE_DISABLE mode only)
- strategy_weights (dict[strategy_name] -> float)
- risk_multiplier (bounded)
- notes (human readable)
- applied (bool)

2) Allowed actions and strict safety
- If ADAPTIVE_REGIME_POLICY_ENABLED=False, compute snapshot but do not apply any changes.
- Apply only when confidence >= ADAPTIVE_REGIME_MIN_CONFIDENCE_TO_APPLY.
- risk_multiplier clamped within MIN/MAX and must not exceed 1.0 unless explicitly configured.
- WEIGHT mode: weights must sum to 1.0.
- ENABLE_DISABLE mode: only the listed strategies are eligible; others skipped.

3) Integration wiring
- Orchestrator calls RegimeLayer after scanner outputs are ready.
- StrategyRunner receives RegimePolicyDecision and applies weights/eligibility during dispatch and aggregation.
- RiskEngine may consume risk_multiplier to scale sizing, but must still enforce breakers.

4) Event capture
- Emit REGIME_SNAPSHOT once per cycle (when layer enabled)
- Emit REGIME_POLICY_DECISION when policy enabled (applied or not; include applied=False)

5) Tests
Add tests/test_regime_policy_application.py:
- Policy disabled: no change to StrategyRunner behaviour.
- Policy enabled: weights affect aggregated intent selection deterministically using mocked intents.
- Risk multiplier clamp tested.

## Acceptance criteria
- Flags off: behaviour unchanged.
- Layer on + policy off: regime events only.
- Policy on: dispatch behaviour changes predictably and is logged.
