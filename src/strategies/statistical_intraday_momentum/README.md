# Statistical Intraday Momentum (Interface-Native)

This strategy is an **additive** module that produces interface-native intents and
policy outputs without wiring into the orchestrator. It is designed to evaluate
short-horizon continuation signals only when volatility and liquidity regimes
are stable and explicitly defined by configuration. The initial implementation
is **long-only by default** and avoids microstructure assumptions.

## Scope
- Intraday continuation signals with time-of-day conditioning.
- Volatility and liquidity regime gating to avoid unstable periods.
- Deterministic scoring with conservative defaults.

## Non-Goals
- No HFT or queue-position dependencies.
- No mean-reversion logic.
- No ML dependencies or external data sources.
