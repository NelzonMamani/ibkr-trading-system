# PHASE_25_STRATEGY_ENGINE_CANONICAL_MODEL

## Objective
Define the **canonical Strategy Engine model** for the Trading OS.

This phase establishes:
1) A stable strategy lifecycle (initialise → evaluate → emit intents)
2) Canonical schemas for strategy inputs/outputs
3) Hard boundaries: Strategy produces **intent**, never broker orders

## Scope
### In-Scope
- Base interfaces and datamodels for:
  - `StrategyInput` (what the scanner/patterns provide)
  - `StrategyDecision` (what a strategy returns per symbol)
  - `TradeIntent` (entry/exit intent model; no execution)
- Strategy lifecycle methods (conceptual):
  - `initialise(context)`
  - `evaluate(symbol, inputs)`
  - `summarise_cycle(results)`
- A standard **Strategy → Risk** handoff payload shape (even if Risk is implemented in Epoch 3)
- A stable strategy identifier convention: `strategy_id`, `strategy_name`, `version`

### Out-of-Scope
- Any IBKR execution calls
- Any position sizing, portfolio limits, circuit breakers
- Any learning/parameter mutation

## Canonical Contracts
### Required StrategyInput fields (minimum)
- `symbol`
- `session_context` (PRE/REGULAR/AFTER)
- `scanner_context` (score, rank, drop reasons if applicable)
- `market_context` (price, spread, volume, RVOL, key levels if known)
- `news_context` (optional, structured)
- `data_quality_flags` (list)

### Required StrategyDecision fields (minimum)
- `symbol`
- `strategy_id`
- `decision_type` (NO_ACTION / WATCH / CONSIDER / EMIT_INTENT)
- `confidence` (0.0–1.0)
- `rationale_text`
- `risk_flags` (list)
- `intents` (0..n `TradeIntent`)

### Required TradeIntent fields (minimum)
- `intent_id`
- `symbol`
- `direction` (LONG/SHORT)
- `entry_model` (zone or trigger description)
- `stop_model` (structure-based suggestion)
- `target_model` (optional)
- `time_in_force_policy` (conceptual; used later by execution)
- `invalidations` (conditions that cancel the intent)
- `rationale_text`
- `risk_flags`

## Files to Create/Modify (Repo)
- Create: `src/strategies/strategy_contracts.py` (dataclasses/enums only)
- Create: `src/strategies/strategy_base.py` (abstract base)
- Create: `src/strategies/strategy_registry.py` (stub registry; full plug-in in Phase 29)
- (Optional) Create: `src/strategies/README_strategies.md` (developer notes)

## Definition of Done
- A strategy can be evaluated in isolation with a mocked `StrategyInput` and returns a deterministic `StrategyDecision`.
- Contracts are explicit, validated, and versioned.
- There is a clear payload shape for Strategy → Risk handoff.

## Notes
This phase is intentionally “boring.” If the strategy contracts are unstable, every later strategy becomes expensive to implement and hard to debug.
