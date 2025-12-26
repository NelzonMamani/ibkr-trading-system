28_PHASE_5_STEP_5_3_CODEX_INSTRUCTIONS_MOMENTUM_CONTINUATION_STRATEGY.md
Title: STEP 5.3 — Codex Instructions: Implement MomentumContinuationStrategy (Teaching-First)

================================================================================
OBJECTIVE
================================================================================
Add a second, independent trading strategy plugin to validate
multi-strategy architecture.

This step proves:
- StrategyRunner can dispatch multiple strategies
- Strategies can coexist without interfering
- Different trader styles (SCALPER vs MOMENTUM) flow together safely

================================================================================
GUARDRAILS (NON-NEGOTIABLE)
================================================================================
1. NO broker calls
2. NO randomness
3. SIM mode only
4. Stateless strategies
5. Strategy returns List[TradeIntent]
6. Teaching logs explaining WHY
7. GapAndGoStrategy must remain unchanged

================================================================================
FILES TO CREATE / MODIFY
================================================================================

CREATE:
1. src/strategy/momentum_continuation_strategy.py

MODIFY:
2. src/strategy/strategy_runner.py (register new strategy ONLY)

DO NOT modify:
- Orchestrator
- RiskEngine
- ExecutionEngine
- StorageEngine

================================================================================
STEP 1 — CREATE MOMENTUM CONTINUATION STRATEGY
================================================================================
File: src/strategy/momentum_continuation_strategy.py

Class:
- MomentumContinuationStrategy(BaseStrategy)

Behavior:
- Input: List[PatternResult]
- Filter patterns where pattern_name contains "Momentum Continuation"
- For each match, create TradeIntent:
  - symbol = pattern.symbol
  - direction = "LONG"
  - strategy_name = "MomentumContinuationStrategy"
  - confidence = pattern.confidence
  - trader_type = "MOMENTUM"
  - rationale = pattern.rationale + teaching note

Rules:
- NO thresholds
- NO sizing
- NO risk logic
- Pure translation: Pattern → TradeIntent

Required logs (prefix with [STRATEGY:Momentum]):
- Start evaluation (pattern count)
- Match vs skip per symbol
- TradeIntent creation
- Summary count

================================================================================
STEP 2 — REGISTER STRATEGY IN STRATEGY RUNNER
================================================================================
File: src/strategy/strategy_runner.py

In __init__:
- Register BOTH strategies:
  - GapAndGoStrategy
  - MomentumContinuationStrategy

Expected boot log:
[BOOT] StrategyRunner instantiated with strategies:
       - GapAndGoStrategy
       - MomentumContinuationStrategy

No other logic changes allowed.

================================================================================
EXPECTED RUNTIME BEHAVIOR
================================================================================
When running main.py:

- GapAndGoStrategy produces SCALPER intents
- MomentumContinuationStrategy produces MOMENTUM intents
- Both flow through:
  Risk → Execution → Storage
- Execution routes by trader_type
- Summary shows mixed strategies

Example:
[SUMMARY] scanner=4 | patterns=3 | trade_intents=3 | risk_decisions=3 | execution_results=3

================================================================================
DEFINITION OF DONE
================================================================================
- Both strategies fire independently
- No duplicated logic
- No crashes
- Logs clearly show which strategy created which TradeIntent
- System remains deterministic and SIM-safe

================================================================================
GIT / CODEX
================================================================================
Commit message:
"Phase 5.3: add MomentumContinuationStrategy and multi-strategy dispatch"

Open PR when complete.
