# SIGNAL INTEGRATION AND QUALITY BRIDGE (M10 ⇄ M9)

M10 feeds M9 signal-quality metadata without imposing policy.

## Bridge rules
- For any signal emitted (M9), the system must be able to attach:
  - data freshness class
  - confidence level
  - limitation summary
  - input provenance event_ids

## Zone and timeframe consistency
When zones or multi-timeframe signals are computed, M10 must record:
- which timeframes were used (1D vs 5M vs 1M etc.)
- which timeframe provided the zone definition
- which timeframe confirmed price interaction

## Post-trade truth
For every executed trade decision (E14 decision artifact), store:
- the minimum provenance chain that explains the decision:
  inputs → derived metrics → signals → decision → execution

END
