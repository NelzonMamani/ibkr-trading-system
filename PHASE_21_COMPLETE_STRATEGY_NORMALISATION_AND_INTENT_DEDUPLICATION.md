TITLE:
PHASE 21 — Strategy Normalisation and Intent De-Duplication

OBJECTIVE:
Normalise strategy outputs and ensure that, per symbol and cycle, the system produces
a single, coherent trading intent per trader type, without conflicting or duplicated
strategy signals.

SCOPE:
This phase operates strictly between StrategyRunner and RiskEngine.

IMPLEMENTATION REQUIREMENTS:

1. STRATEGY INTENT NORMALISATION
   - Introduce a normalisation layer after StrategyRunner aggregation.
   - Group TradeIntents by:
     - symbol
     - trader_type (e.g. MOMENTUM, SCALPER)
     - direction
   - For each group, retain only ONE final TradeIntent.

2. DEDUPLICATION RULES
   - Prefer higher confidence intents.
   - If confidence ties:
     - Prefer pattern priority (HOD > ORB > GAP_AND_GO > FIRST_PULLBACK > VWAP).
   - Log discarded intents with rationale.

3. TRACEABILITY
   - Emit a new event type:
     - INTENT_NORMALISED
   - Payload must include:
     - kept_intent
     - discarded_intents (ids + reasons)

4. SAFETY GUARANTEES
   - Do NOT change strategy logic.
   - Do NOT change RiskEngine rules.
   - Do NOT change ExecutionEngine behaviour.
   - Do NOT change persistence schema (reuse existing events table).

5. TEACHING MODE COMPATIBILITY
   - Behaviour must be deterministic in SIM mode.
   - Output logs must clearly explain why intents were dropped.

EXPECTED OUTCOME:
- Per cycle, at most ONE TradeIntent per (symbol, trader_type).
- RiskEngine receives a clean, non-duplicated intent list.
- Replay remains deterministic and invariant-safe.

DEFINITION OF DONE:
- No duplicate TradeIntents reach RiskEngine.
- INTENT_NORMALISED events visible in SQLite DB.
- Replay passes invariants with normalised intent set.

END
