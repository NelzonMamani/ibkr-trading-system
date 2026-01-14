# PHASE_28_ENTRY_EXIT_INTENT_MODEL

## Objective
Define and implement the **TradeIntent modelling layer**:
- convert pattern outcomes into actionable-but-non-executable intent
- standardise entry zone / trigger phrasing
- standardise stop suggestions (structure-based)
- standardise target suggestions (optional)

## Scope
### In-Scope
- `TradeIntent` datamodel (already introduced in Phase 25; now expanded)
- Intent generation policies for Ross (reference strategy)
- Intent invalidations and expiry (session-aware; no scheduling engine required)

### Out-of-Scope
- Position sizing / risk budget decisions
- Order types, routing, IBKR behaviour

## Files to Create/Modify (Repo)
- Modify: `src/strategies/strategy_contracts.py` (finalise TradeIntent fields)
- Create: `src/strategies/ross_momentum/decision_policy.py` (intent generation only)

## Definition of Done
- For a detected Ross core pattern, the system emits a deterministic `TradeIntent` including:
  - direction
  - entry model (zone or trigger text)
  - stop model (price suggestion + reason)
  - invalidations
  - rationale text
