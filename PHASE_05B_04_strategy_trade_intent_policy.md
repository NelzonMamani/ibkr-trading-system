# PHASE_05B_04_strategy_trade_intent_policy

Date: 2026-01-15

## Objective
Implement the Ross confirmation “gold standard” strategy policy that converts PatternResults into TradeIntents.
Strategy produces intent only; it never places orders.

## Inputs (Must Read)
- STRATEGY_SPEC_ROSS_CAMERON_MOMENTUM.md
- MODULE_REQUIREMENTS_patterns.md
- MODULE_REQUIREMENTS_risk.md
- EPOCH_05_GOVERNANCE.md (authority boundaries)

## Allowed Files (Strict)
- src/strategies/ross_momentum/ross_playbook.py
- src/strategies/ross_momentum/decision_policy.py
- src/strategies/ross_momentum/setup_rules.py
- src/strategies/strategy_registry.py
- src/utils/time_utils.py
- src/utils/logging.py

## Tasks
1. Define TradeIntent contract:
   - symbol, side, setup_id, intended entry logic, stop plan, target plan
   - time validity and session context
   - rationale_text and tags
2. Implement session-aware policy:
   - premarket planning vs open execution vs midday filtering
3. Convert PatternResults → TradeIntents using confirmation rules:
   - intent must cite the setup and key confirmations (VWAP/EMA/volume etc. as available)
4. Ensure no broker calls exist in strategy code.

## Commands (Mandatory)
From repo root:
1. `python -m src.strategies.ross_momentum.decision_policy --mode SIM --cycles 1`
(Or equivalent standalone strategy harness. Must be runnable.)

## Required Console Output
- list of generated intents (or “0 intents”)
- each intent prints: symbol, setup_id, side, stop plan summary, rationale

## Acceptance Checklist
- Strategy runs standalone.
- Generates 0..N intents deterministically.
- No orders are placed; no IBKR calls from strategy.

## Rollback Rule
Avoid adding “adaptive” logic in this phase; keep the policy explicit and explainable.

END.
