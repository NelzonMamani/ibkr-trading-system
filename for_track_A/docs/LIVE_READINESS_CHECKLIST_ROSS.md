# LIVE READINESS CHECKLIST — Ross Momentum (UK Operator)

**Session authority:** `America/New_York` (DST-aware).  
**Operator display:** `Europe/London` and `UTC`.

## Preflight (must all be green)
- IBKR TWS/Gateway running and logged in
- Correct port for mode:
  - PAPER: 7497
  - LIVE: 7496
- US market data permissions active
- `RUN_MODE` correct (SIM / PAPER / LIVE)
- `order_submission_enabled` only true when you intend to submit
- `paper_only_enforced` true for PAPER; false for LIVE
- Kill-switch OFF
- LIVE_ARM set only for LIVE
- Risk limits configured (daily max loss, notional caps, max trades)
- Time authority sanity:
  - System prints NY time and UK time
  - Session phase matches real US session
  - UK and US DST change on different dates — do not infer session from UK clock.

## If anything fails
Do not trade. Fix, rerun preflight, then proceed.
