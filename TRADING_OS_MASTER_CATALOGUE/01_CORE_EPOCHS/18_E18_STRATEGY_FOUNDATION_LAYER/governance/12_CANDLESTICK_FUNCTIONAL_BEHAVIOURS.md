# E18 — CANDLESTICK FUNCTIONAL BEHAVIOURS (PARAMETERISED PRIMITIVES)

These behaviours are REQUIRED building blocks for setups (flags, reclaims, failures).
They are non-named, parameterised, reusable primitives.

CHECKLIST:
[ ] Range Expansion (range > X * avg_range)
[ ] Range Contraction (sequential narrowing)
[ ] Body Dominance (body_pct_of_range)
[ ] Wick Rejection Strength (wick_to_body_ratio)
[ ] Close Location Value (CLV) / close-in-range (near high/low)
[ ] Open Location Value / open-in-range (near high/low)
[ ] Momentum Continuity Bars (higher closes with controlled range)
[ ] Exhaustion Bars (large range + poor follow-through / reversal risk)
[ ] Compression Count (N bars within tight band)
[ ] Breakout Attempt + Immediate Failure (probe-and-fail)
[ ] Reclaim Attempt + Hold Window (reclaim-and-hold mechanics)

OUTPUT REQUIREMENT:
Each behaviour returns:
- detected(bool)
- measurements (numeric values used)
- optional explanation fields

END
