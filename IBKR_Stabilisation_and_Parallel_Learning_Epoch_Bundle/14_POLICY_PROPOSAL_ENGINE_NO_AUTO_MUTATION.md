# 14 — POLICY PROPOSAL ENGINE (NO AUTO MUTATION)

## Objective
After sufficient sample size (e.g., 30 or 100 trades), generate **alternative policy values** for a strategy.

## Rules (hard)
- Proposals only: never applied automatically.
- No structural changes: policy schema must match baseline exactly.
- Only adjust fields explicitly flagged as “tunable”.
- Keep changes conservative: bounded deltas and sanity constraints.

## Inputs
- Baseline policy (e.g., ROSS_MOMENTUM v1)
- LearningDataset filtered to:
  - strategy_name
  - time window
  - minimum trade count threshold

## Tunable fields (example for Ross Momentum)
- price_min, price_max
- gap_min_pct
- rvol_min
- float_max_millions
- min_volume, min_premarket_volume
- spread_max_pct (if used)
- liquidity_min_dollar_volume (if used)
- require_catalyst (careful; likely stays True)

Non-tunable:
- structural flags that define behaviour invariants
- safety circuit breakers (global)

## Method (simple, defensible; start here)
- For each tunable numeric field:
  - compute distribution of “winning trades” vs “losing trades”
  - propose threshold adjustments that improve separation:
    - e.g., set rvol_min to the 25th percentile of winning trades’ RVOL (bounded)
- Use cross-validation where feasible (train/test split by time).

## Output artifacts
- `proposal_json`: full policy object (same schema)
- `diff_json`: list of changes (field, old, new)
- `rationale_json`: per-field explanation with stats

Persist to `policy_proposals` with status DRAFT.

## Acceptance criteria
- Running:
  - `python -m src.learning.cli propose-policy --strategy ROSS_MOMENTUM --min-trades 30`
creates a proposal when threshold met, otherwise prints “insufficient trades”.

END
