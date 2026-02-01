# 05_ROSS_SETUPS_IMPLEMENTATION.md
TITLE: Complete Ross Momentum — Implement All Setup Families and Micro Execution Patterns
DATE: 2026-01-31

## 1. Goal
Ross Momentum must be **complete and trade-ready**, implementing all setup families and micro execution patterns listed in the user’s catalogue.

This is not a partial PR. This is completion.

## 2. Non-negotiables
- Strategy policy decides; scanner provides facts.
- Each setup family must have:
  - explicit conditions
  - explicit invalidation/exit logic
  - explicit “do not add / pause entries” states
- No TODOs for missing setups. If a setup cannot be implemented due to missing data, Codex must add the required data to the facts contract (scanner) or implement a conservative fallback.

## 3. Source of truth catalogue
Use `SETUP_FAMILIES_AND_PATTERNS.md` (user-provided) as the authoritative list.
At minimum implement:
Macro families:
1. Gap & Go (Opening Drive)
2. ORB
3. First Pullback / First Flag
4. Micro Pullback (10s/15s)
5. Bull Flag / High-Tight Flag
6. Break of Key Level (PMH, whole/half dollar, prior day high, multi-day high)
7. ABCD continuation / extension
8. Cup & Handle (intraday)
9. Momentum Reclaim (VWAP / key EMA reclaim)
10. Red-to-Green / Green-to-Red (contextual confirm/warn)
11. Half-Dollar / Whole-Dollar Break
12. Pre-market High Break (overlaps #1 but must be explicit)
13. Halt Resume Continuation
14. Parabolic Exhaustion (avoid/exit family)

Micro patterns:
A. Micro pullback re-entry trigger (first green candle that reclaims pullback; conservative and aggressive triggers)
B. First pullback continuation trigger (reclaim pullback high / break prior candle high)
C. Breakout trigger (break defined resistance with volume/momentum)
D. Failure triggers (loss of VWAP/EMA, macro rejection, topping tail)

## 4. Architecture placement
All setup logic must live in:
- `src/strategies/ross_momentum/strategy_policy.py` (or the strategy’s designated decision module)
Pattern detection helpers may live under:
- `src/strategies/ross_momentum/patterns/…` (if present in repo)

## 5. Session-aware behavior
Setups must behave appropriately by session:
- PRE: allow watchlist + early signals only if data quality flags allow; avoid trades unless policy explicitly allows premarket trading.
- RTH: full trading.
- AH: generally no new trades; manage exits only unless explicitly allowed.
- CLOSED: prep only.

## 6. Risk profile integration
MICRO must behave identically to NORMAL except position sizing and constraints.
Do not alter setup logic for MICRO; enforce at intent boundary.

## 7. Acceptance criteria
- A unit/integration test exists for each setup family: it can recognize the structure and produce a consistent intent in PAPER harness.
- The strategy logs/trace can attribute each intent to:
  - setup family name
  - trigger pattern name
  - key levels used (PMH/ORH/flag high/etc.)
- “Parabolic exhaustion” and “big red volume bigger than green” conditions must veto new entries (pause state).

END
