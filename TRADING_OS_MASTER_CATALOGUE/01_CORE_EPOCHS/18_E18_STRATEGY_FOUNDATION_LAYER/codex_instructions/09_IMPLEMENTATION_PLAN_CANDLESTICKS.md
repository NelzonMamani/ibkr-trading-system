# E18 — IMPLEMENTATION PLAN: CANDLESTICKS (3-LAYER MODEL)

Source of truth:
- governance/09_CANDLESTICK_FOUNDATION_MODEL.md
- governance/10_SINGLE_CANDLE checklist
- governance/11_MULTI_CANDLE checklist
- governance/12_FUNCTIONAL_BEHAVIOURS checklist
- governance/13_CONTEXTUAL_STATES checklist

Task:
Implement candlesticks as THREE layers of primitives:

Layer 1 — Named patterns
- Implement all single- and multi-candle named patterns as deterministic recognizers.
- Parameterize thresholds; do not hardcode strategy-specific values.

Layer 2 — Functional behaviours
- Implement all required behaviours as parameterized measurement functions + detectors.
- Must return detected + measurements used.

Layer 3 — Contextual candle states
- Implement candle ↔ context interaction states (VWAP/EMA/key levels/HOD/LOD/opening range/PDC/PDH/PDL).
- These are observational states, not decisions.

Deliverables:
- Registry entries for all candle primitives
- Unit tests with fixed OHLCV sequences for each recognizer/behaviour/state
- Optional explainability fields

END
