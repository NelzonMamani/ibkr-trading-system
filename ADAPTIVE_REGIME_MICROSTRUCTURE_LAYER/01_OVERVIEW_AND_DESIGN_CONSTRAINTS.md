# ADAPTIVE_REGIME_MICROSTRUCTURE_LAYER — Overview & Design Constraints
Last updated: 2026-01-19

## Position in the Trading OS
This layer is not a strategy. It is a governed, sandboxed module that sits between:
- Scanner/Pattern/Signal generation (market perception + decision intelligence), and
- StrategyRunner/Risk/Execution (decision dispatch + capital control)

It observes the market regime and provides a non-mutating policy that can:
- Adjust strategy weights / enablement
- Adjust risk parameters (within allowed limits)
- Gate low-quality conditions (halts, spreads, liquidity degradation)
- Annotate intents with regime metadata for audit and learning

It must never:
- Place orders
- Invent intents
- Mutate strategy rules without explicit configuration
- Introduce non-determinism

## High-level architecture
A) RegimeObservers (pure measurement)
- Deterministic feature extraction from available inputs:
  - Prices/returns (bars), spreads, volume, volatility proxies
  - Session context (PRE/REGULAR/AFTER) and time-of-day windows
  - Scanner artifacts (gap%, rvol, float bands, liquidity flags)
- Observers must be side-effect free.

B) BaselineStore (cache + rolling stats)
- Holds rolling baselines (EWMA, rolling mean/std, quantiles)
- Stores only what is needed for regime detection; no heavy ML dependencies
- Deterministic update order

C) RegimeClassifier (rules + probabilistic scoring)
- Produces: RegimeLabel, regime_confidence (0..1), evidence (top contributing features)
- Must support fallbacks when some inputs are missing (especially in LIVE_READ_ONLY).

D) RegimePolicy (non-mutating)
- Converts RegimeSnapshot into RegimePolicyDecision
- Can recommend strategy weights, bounded risk multipliers, or skip-trading hints
- Must be explainable and persisted as events.

E) Integration points
- Orchestrator produces RegimeSnapshot early in the cycle
- StrategyRunner consumes PolicyDecision (weights + eligibility hints)
- RiskEngine may consume bounded risk adjustments (multipliers, but never bypass gates)
- Storage persists regime artifacts in TradeRecord

## Determinism contract
Given identical inputs (scanner candidates, market data snapshots, bars, and config), the layer must produce:
- identical features
- identical regime label + confidence
- identical policy decisions

Where data is missing, behaviour must degrade deterministically (explicit flags), not randomly.

## Configuration contract
All behaviour is behind flags:
- ADAPTIVE_REGIME_LAYER_ENABLED (default False)
- ADAPTIVE_REGIME_POLICY_ENABLED (default False; allows policy application)
- ADAPTIVE_REGIME_LOG_LEVEL (INFO)
- ADAPTIVE_REGIME_ALLOWED_RISK_MULTIPLIERS (bounded list)
- ADAPTIVE_REGIME_ALLOWED_STRATEGY_WEIGHTS (bounded list)

## Scope constraints
- No external ML services.
- No network calls.
- No new heavy dependencies (stdlib + existing deps only).
