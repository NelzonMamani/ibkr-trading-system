# Strategy Assumptions & Research Anchors

## Research Anchors (Qualitative)
- Intraday momentum effects have been documented in multiple studies, often with
  time-of-day dependencies (open/close vs midday).
- Volatility exhibits intraday periodicity and persistence; regimes matter for
  signal validity.
- Short-horizon continuation is more reliable in stable liquidity conditions.

## Assumptions (Explicit, Conservative)
- **Time-of-day matters**: Signals are only considered within configured windows
  to avoid open/close microstructure noise.
- **Volatility regime gating**: Avoids trading during volatility collapse or
  extreme spikes where continuation breaks down.
- **Long-only by default**: Short selling is disabled unless explicitly enabled
  in policy.
- **Deterministic scoring**: No stochastic model components; deterministic input
  -> deterministic intent.

## Safety Defaults
- Missing inputs yield DISALLOW/NO_TRADE.
- Any gating failure yields DISALLOW/NO_TRADE with explicit reason codes.
