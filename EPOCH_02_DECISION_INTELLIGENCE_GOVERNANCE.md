# EPOCH_02_DECISION_INTELLIGENCE_GOVERNANCE

## Purpose
Epoch 2 builds **Decision Intelligence**: convert Scanner opportunities into **structured trade intent** without sending broker orders.

This epoch exists to answer:
- “Given a watchlist candidate, what setup(s) exist?”
- “If a setup exists, what is the intended entry/stop/target model?”
- “How confident is the setup and what are the risks?”

## Inputs and Dependencies (Read-Only)
Epoch 2 assumes these are already frozen and must not be modified as part of pattern/strategy work:
- Scanner contract (Top N → hard gates → Watchlist K → Focus M; empty outputs are valid).
- Global print contracts and scanner canonical outputs.
- Module boundary rules: Scanner ≠ Strategy ≠ Risk ≠ Execution.

Reference requirements (authoritative planning sources):
- `GLOBAL_FUNCTIONAL_REQUIREMENTS.md`
- `MODULE_REQUIREMENTS_patterns.md`
- `ROSS_MOMENTUM_PATTERN_REFERENCE.md`
- `ROSS_MOMENTUM_PATTERN_DETECTION_BLUEPRINT.md`
- `STRATEGY_SPEC_ROSS_CAMERON_MOMENTUM.md`

## Epoch Scope
### In-Scope
1. **Strategy Engine canonical model** (lifecycle + interfaces)
2. **Pattern detection contracts** (schemas, required inputs, deterministic outputs)
3. **Ross core pattern implementation** (Phase 1 priorities)
4. **Candlestick library** (single + multi candle recognisers) as *supporting evidence*, not standalone triggers
5. **Pattern aggregation + conflict resolution** (ranking, vetoes, confidence logic)
6. **Entry/exit intent modelling** (zones, stop suggestion, target suggestion, rationale)
7. **Strategy registry (plug-in architecture)** (multiple strategies co-existing)
8. **Strategy explainability** (teacher-style logs, structured returns)

### Out-of-Scope (Hard Prohibitions)
1. **No broker orders** (no IBKR calls that place/modify/cancel orders).
2. **No position sizing decisions** (Risk module owns sizing and permission checks).
3. **No portfolio-level constraints** (daily loss, max trades, circuit breakers belong to Risk/Epoch 3).
4. **No autonomous learning or parameter mutation** (learning begins in Epoch 4; until then, all thresholds are config, versioned, and explicit).
5. **No scanner rewrites** (only consume scanner outputs).

## Determinism and Explainability Rules
1. For identical inputs, pattern outputs **must be identical**.
2. Every `PatternResult` MUST contain a human-readable `rationale_text`.
3. Candlestick patterns MUST be tagged as **support signals** and never be the sole reason for an entry.
4. Any missing/stale data must be surfaced via `data_quality_flags` (not silently ignored).

## Deliverables (Files)
Epoch 2 produces the following governance/instruction artifacts:
- `PHASE_25_STRATEGY_ENGINE_CANONICAL_MODEL.md`
- `PHASE_26A_PATTERN_DETECTION_CONTRACTS.md`
- `PHASE_26B_ROSS_CORE_PATTERN_IMPLEMENTATION.md`
- `PHASE_26C_CANDLESTICK_LIBRARY_IMPLEMENTATION.md`
- `PHASE_27_PATTERN_AGGREGATION_AND_CONFLICT_RESOLUTION.md`
- `PHASE_28_ENTRY_EXIT_INTENT_MODEL.md`
- `PHASE_29_STRATEGY_REGISTRY_AND_PLUGIN_ARCHITECTURE.md`
- `PHASE_30_STRATEGY_EXPLAINABILITY_AND_LOGS.md`

## Acceptance Criteria (Epoch 2)
Epoch 2 is acceptable when:
1. A Focus list symbol can be evaluated and returns:
   - one or more `PatternResult`s
   - ranked best-long / best-short
   - conflict flag (if applicable)
   - structured `TradeIntent` (entry zone, stop suggestion, target suggestion)
2. Ross Momentum “core” patterns (ORB / Premarket High break, Micro Pullback, Bull Flag, Consolidation Breakout, Failed Breakout caution) are implemented end-to-end with explainability.
3. Candlestick recognisers exist for a broad set of patterns and can attach evidence tags to pattern results.
4. Strategy registry can run at least:
   - `Retail_Confirmation_Momentum` (Ross reference)
   - `Early_Entry_Momentum_Continuation` (user)
   without cross-contamination.
5. No execution side effects exist anywhere in Epoch 2 outputs.

## Change Control
- Any change to epoch scope requires an explicit “Roadmap Amendment” discussion.
- Any change to contracts requires version bump and migration notes.

## Codex Stability Guard
When Codex is used for Epoch 2 work:
- Treat `SYSTEM_CONSTITUTION.md` as immutable law.
- Treat `README.md` as descriptive.
- Treat `SYSTEM_STATE.md` as the only file that reflects current progress.
