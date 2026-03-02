# StrategyPolicyV2 Consumption Layer

This package implements runtime-safe, strategy-agnostic consumption of `StrategyPolicyV2`.

## Pipeline

1. `SelectionEngineV2`: applies hard gates from `stock_selection_law`, `liquidity_sanity_model`, and `selection_plan.session_allowlist`.
2. `RankingEngineV2`: computes deterministic ranking scores from `ranking_model`.
3. `WatchlistBuilderV2`: deterministic top-K (`watchlist_limit_k`).
4. `FocusBuilderV2`: deterministic top-M (`focus_limit_m`).

## Per-strategy wiring

- Strategy adapters convert scanner-native candidates into the minimal `Candidate` contract.
- P01 Ross migration uses this package through orchestrator integration.
- Future strategies (P02+) only need:
  - `POLICY_V2` surface,
  - an adapter from scanner rows to `Candidate`,
  - opt-in wiring in orchestrator (or central policy resolver).

## Config flag

- `STRATEGY_POLICY_V2_ENABLED` controls whether runtime consumes V2 engines.
- Default is `true` for all run modes; set `false` for emergency fallback to V1.

## Determinism

- No randomness.
- Stable sorting tie-breakers: `score DESC`, `pct_change DESC`, `dollar_volume DESC`, `symbol ASC`.
- Ranking output includes score breakdown for auditability.

## Evidence paths

- Baseline verifier: `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/P01_ROSS_V2_MIGRATION/<timestamp>/`
- Consumption verifier: `TRADING_OS_MASTER_CATALOGUE/AUDIT_EVIDENCE/P01_ROSS_POLICY_V2_CONSUMPTION/<timestamp>/`
