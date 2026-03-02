# StrategyPolicyV2 Registry

`registry.py` is the strategy-agnostic resolver used by orchestrator runtime wiring.

## Add a strategy
1. Add `<strategy_key>: <import_path>` to `_POLICY_IMPORT_PATHS`.
2. Add a lazy resolver entry to `_RESOLVERS` that imports and returns `POLICY_V2`.
3. Enable it in config (`STRATEGY_POLICY_V2_STRATEGIES`) only when migration evidence is ready.

## Toggles
- Global gate: `STRATEGY_POLICY_V2_ENABLED`
- Per-strategy gate: `STRATEGY_POLICY_V2_STRATEGIES` (`dict[str, bool]`)

Global `false` disables all V2 strategies. Global `true` still requires the strategy key to be explicitly enabled in the per-strategy map.

## Orchestrator interaction
Orchestrator resolves a strategy policy with `resolve_policy_v2(selected_strategy_key)`. If a policy exists and flags permit it, V2 selection/ranking/builders are used; otherwise orchestrator executes the legacy V1 path.
