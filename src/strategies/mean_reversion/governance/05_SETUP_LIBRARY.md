# Setup Library (Current Strategy Surface)

This strategy supports a small set of **auditable** mean reversion setups.
Setups are **labels** for logging/tuning; they do not bypass the contract.

## VWAP_EXTENSION_SNAPBACK
- Mean = VWAP
- Abnormal extension from VWAP
- Evidence of reversal / exhaustion

## EMA_STRETCH_REVERSION
- Mean = EMA20 or EMA9
- Used when VWAP unavailable or secondary mean allowed

## FAILED_BREAKOUT_REVERSION
- Aligned failed breakout marker
- Trap unwind conditions

## EXHAUSTION_SPIKE_TIME_REVERSION
- Volume deceleration flagged
- Rejection wick aligned with reversal

## Governance note
New setups may be added only if:
- they still satisfy ALL 8 clauses
- they are documented here with explicit conditions
