# E18 — LEVELS & ZONES FOUNDATION (SUPPORT/RESISTANCE, SUPPLY/DEMAND)

E18 MUST treat levels and zones as first-class neutral primitives.

LEVEL PRIMITIVE (required fields):
- level_id
- level_type (VWAP, EMA, PDC, PDH, PDL, HOD, LOD, WholeDollar, HalfDollar, Custom)
- timeframe (intraday/daily/weekly)
- source (indicator | price_action | session | higher_tf | user_defined)
- price (single value) OR bounds (if band)
- tolerance (ticks/percent)
- strength (optional; non-binding)
- freshness/tested flags (optional)

ZONE PRIMITIVE (required fields):
- zone_id
- zone_type (supply | demand | volatility_band | custom)
- upper, lower bounds
- origin (impulse/base/rejection/volume)
- created_timestamp
- freshness/tested flags
- decay/aging semantics (optional)

INTERACTION STATES (shared vocabulary):
- approach, break, hold, reject, reclaim, fail

INVARIANT:
Levels/zones provide context; strategies decide trade rules.

END
