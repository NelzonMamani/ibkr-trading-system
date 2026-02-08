# E18 — CANDLESTICK CONTEXTUAL STATES (CANDLE ↔ CONTEXT INTERACTIONS)

Contextual states connect candles to context primitives WITHOUT embedding policy.
These states are used by strategies as inputs.

CHECKLIST:
[ ] Candle vs VWAP: above | below | reclaim | reject | hold | fail
[ ] Candle vs EMA (9/20/…): above | below | reclaim | reject | hold | fail
[ ] Candle vs Key Level: break | hold | reject | reclaim | fail
[ ] Candle vs HOD/LOD: acceptance | failure | reclaim
[ ] Candle vs Opening Range: break | retest | failure | reclaim
[ ] Candle vs Prior Day Close (PDC): reclaim | reject | hold | fail
[ ] Candle vs Prior High/Low: break | hold | reject | reclaim | fail

INVARIANT:
These states are observational. Strategies decide how to trade them.

END
