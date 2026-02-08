# range_bound_fade — Strategy Algorithm (DRAFT)

This document defines the FULL end-to-end algorithm.

This is NOT code.
This is the authoritative human-readable trading logic.

----------------------------------------------------------------------
1. EDGE DEFINITION
----------------------------------------------------------------------
What inefficiency does this strategy exploit?

----------------------------------------------------------------------
2. UNIVERSE & ELIGIBILITY
----------------------------------------------------------------------
- Symbol source
- Liquidity requirements
- Price range
- Exclusions

----------------------------------------------------------------------
3. DATA REQUIREMENTS
----------------------------------------------------------------------
- Timeframes
- Indicators
- Levels / zones
- Market context

----------------------------------------------------------------------
4. SETUP DETECTION (E18)
----------------------------------------------------------------------
Which setup families are allowed and why.

----------------------------------------------------------------------
5. ENTRY LOGIC
----------------------------------------------------------------------
Conditions → Trigger → Confirmations → Trade Intent

----------------------------------------------------------------------
6. POSITION MANAGEMENT
----------------------------------------------------------------------
- Adds
- Partial exits
- Trailing logic
- Time stops

----------------------------------------------------------------------
7. EXIT & INVALIDATION
----------------------------------------------------------------------
- Profit targets
- Structural invalidation
- Hard stops
- Emergency exits

----------------------------------------------------------------------
8. RISK CONTROLS
----------------------------------------------------------------------
- Per-trade risk
- Per-day limits
- Kill-switch conditions

----------------------------------------------------------------------
9. RECOVERY & RESILIENCE
----------------------------------------------------------------------
- Network disconnect
- Order reconciliation
- State rebuild

----------------------------------------------------------------------
10. MODE SEMANTICS
----------------------------------------------------------------------
SIM | PAPER | READ_ONLY | LIVE

Status: DRAFT — to be completed during strategy planning
