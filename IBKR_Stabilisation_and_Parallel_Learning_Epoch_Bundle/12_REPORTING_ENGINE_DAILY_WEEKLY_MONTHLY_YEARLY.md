# 12 — REPORTING ENGINE: DAILY / WEEKLY / MONTHLY / YEARLY

## Objective
Produce consistent, human-readable and machine-readable reports across strategies.

## Report types
1. DAILY (per NY trading day)
2. WEEKLY (ISO week, NY timezone)
3. MONTHLY
4. YEARLY
5. CUMULATIVE (lifetime) — optional but helpful

## Required report sections (minimum)
### A) Executive summary
- trades: opened/closed
- win/loss/flat, win rate
- gross/net PnL, commissions
- average R, expectancy (if R is available)
- max drawdown for the period (if computable)

### B) Rule adherence and safety
- stop loss violations
- near-violations
- daily max loss near breach / breach
- circuit breaker triggers
- execution blocks encountered

### C) Setup/pattern performance (per strategy)
- by pattern/setup tag: count, win rate, avg pnl, expectancy
- by session phase (PRE/OPEN/MIDDAY/POWER_HOUR/AFTER)
- by volatility regime if you already store it

### D) “Missed trades” / “No trade” reasons
- top reasons we did not trade when candidates existed:
  - no catalyst, float too high, rvol too low, pattern not valid, risk blocked, etc.
This requires reason codes in events.

### E) Watchlist quality
- stability metrics: how often top K changed
- whether focus M produced trades
- whether trades came from focus M vs elsewhere

### F) Action items
- top 3 improvements suggested (non-binding)
- top 3 “keep doing” behaviours

## Output formats
- JSON: full payload
- TXT (or Markdown): summary for humans

Store under:
- `data/reports/<strategy>/<YYYY>/<MM>/<YYYY-MM-DD>_daily.json`
- and a `..._daily.md`

## Triggering
- The learning module should be runnable on demand.
- The main system (ops) may trigger a minimal report at shutdown.
- For full reports:
  - run at end of day if trades exist OR if explicitly requested

## Acceptance criteria
- Running:
  - `python -m src.learning.cli report --date YYYY-MM-DD --strategy ROSS_MOMENTUM`
produces files and prints a summary.
- Running with no trades produces a valid “no trades” report, not an error.

END
