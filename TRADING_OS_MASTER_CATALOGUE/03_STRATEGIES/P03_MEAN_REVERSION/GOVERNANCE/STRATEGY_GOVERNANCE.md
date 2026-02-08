# P03 — Mean Reversion — STRATEGY GOVERNANCE
**Catalogue path:** `03_STRATEGIES/P03_MEAN_REVERSION/GOVERNANCE/STRATEGY_GOVERNANCE.md`  
**Timestamp:** 2026-02-08T01:01:41Z

## 1) Boundary
- P03 is mean reversion. It must not include momentum continuation entries.
- OPENING mode is stricter by default (optionally disabled) due to trend risk.

## 2) Invariants
- NO PARTIALS coverage across canon registries
- Policy is the single tuning surface (all thresholds in policy)
- Traceability + decision artifacts for every cycle
- Mode parity across SIM/PAPER/READ_ONLY/LIVE

## 3) Safety / No-trade contexts (E16)
- Strong-trend regime disallowed unless explicitly permitted
- Data quality failures block all intents
- Spread/liquidity limits enforced
- Loss-streak and cooldown enforced
- Halt handling denied unless certified

## 4) Change control (M8)
All changes must be parameter edits in strategy_policy + verification + certification note.

