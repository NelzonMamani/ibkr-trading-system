# PHASE_29_STRATEGY_REGISTRY_AND_PLUGIN_ARCHITECTURE

## Objective
Implement a safe **Strategy Registry** so multiple strategies can coexist without state leakage or contract drift.

## Scope
### In-Scope
- Registry capabilities:
  - register strategies by `strategy_id`
  - enable/disable strategies by config
  - execute one or multiple strategies per cycle (configurable)
- Isolation rules:
  - strategies receive data; they do not fetch broker state directly
  - strategies must not mutate shared globals

### Out-of-Scope
- Learning-based strategy mutation (Epoch 4+)

## Required Built-In Strategies (end of Epoch 2)
- `Retail_Confirmation_Momentum` (Ross reference)
- `Early_Entry_Momentum_Continuation` (user)

## Files to Create/Modify (Repo)
- Modify: `src/strategies/strategy_registry.py`
- Create: `src/strategies/ross_momentum/strategy.py`
- Create: `src/strategies/early_entry_momentum/strategy.py`

## Definition of Done
- Two strategies can be registered and executed in the same run, producing separate deterministic `StrategyDecision` outputs.
- A config flag can select which strategies run.
