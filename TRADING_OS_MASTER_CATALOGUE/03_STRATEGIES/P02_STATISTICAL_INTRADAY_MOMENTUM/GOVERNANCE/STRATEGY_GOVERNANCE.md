# P02 — Statistical Intraday Momentum — STRATEGY GOVERNANCE
**Catalogue path:** `03_STRATEGIES/P02_STATISTICAL_INTRADAY_MOMENTUM/GOVERNANCE/STRATEGY_GOVERNANCE.md`  
**Timestamp:** 2026-02-08T00:52:50Z

## 1) Strategy boundaries (non-negotiable)
- This strategy is **continuation momentum**, not mean reversion.
- Stock selection is **eligibility + ranking**, not entry/trigger logic.
- Entries are executed only via canonical `XL_*` primitives.
- No strategy code may bypass OS risk engine, execution authority, or no-trade contexts.

## 2) Invariants
- **No partial coverage:** all canonical IDs are classified.
- **Traceability:** every decision produces an auditable artifact (E14/M4).
- **Mode parity:** strategy must behave consistently in SIM/PAPER/READ_ONLY/LIVE (E7).
- **Data provenance:** every feature has provenance (M10).

## 3) No-trade contexts (E16)
Strategy must not emit entry intents when:
- market closed or session phase disallowed
- stale/invalid reference prices
- spread/liquidity outside bounds
- max consecutive losses reached
- risk engine veto
- symbol cooldown active
- regime explicitly disallowed (if enabled)

## 4) Change control (M8)
Any parameter change must:
- occur only in `strategy_policy.py` knobs
- be accompanied by a verification run (E21)
- record a change note (what changed, why, expected impact)

## 5) Safety
- Default direction: LONG-only, unless explicitly certified for shorts.
- Event/halts: denied until specialised handling is certified.

