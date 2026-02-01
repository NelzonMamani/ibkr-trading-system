# 01_CONTEXT_AND_GOALS.md
TITLE: Context, Non-Negotiables, and Outcomes
DATE: 2026-01-31

## 0. Operating premise (do not debate)
The user can manually pick IBKR top gainers and filter using Ross’s 5 pillars. The system is currently useless unless it automates that workflow **end-to-end**.

## 1. The three issues to solve (ordered)
1. **Scanner correction**: make scanner outputs session-qualified facts that are trustworthy in CLOSED/PRE/RTH/AH including weekends/holidays; enable Monday-prep.
2. **PAPER trading + verification**: make PAPER a first-class execution path with deterministic verification proving end-to-end lifecycle.
3. **Complete Ross setups**: implement all missing setup families and micro execution patterns so Ross is complete and trade-ready.

## 2. “No-parallelism” rule
Codex must not open parallel refactors/PRs for unrelated items. The system must stabilize in the order above.

## 3. “Contract > behavior” rule
All critical behavior must be enforced via contracts:
- Session labels & reference types must be explicit.
- Scanner emits facts only (no strategy decisions).
- Strategy policy decides trades.
- Risk profiles are config-only and orthogonal to execution mode.

## 4. Required system-level outcomes
After completing this pack:
- The system can run in **CLOSED mode on weekends** and produce a **Monday watchlist** (or empty list if no candidates).
- PAPER runs the full lifecycle (scan → watchlist → focus → intent → execution → DB) deterministically.
- LIVE can be enabled safely only after PAPER and LIVE_READ_ONLY parity checks pass.
- Ross Momentum strategy includes all setup families/patterns listed in `SETUP_FAMILIES_AND_PATTERNS.md` (the catalogue provided by the user).

END
