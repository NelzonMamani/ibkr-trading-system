# LIVE ROLLOUT PLAN — Ross Momentum (Gradual)

## Stage 0 — Shadow Mode (LIVE data, no orders)
- RUN_MODE=LIVE
- order_submission_enabled=false
- Verify watchlist, signals, policy decisions, and risk blocks.

## Stage 1 — Micro size
- LIVE_ARM=true
- Size cap: 1 share
- Max concurrent symbols: 1
- Max trades/day: small (e.g., 10)
- Verify every order in IBKR activity log.

## Stage 2 — Limited expansion
- 1 share
- Max symbols: 3–5
- Maintain strict daily max loss.

## Stage 3 — Controlled scale
- Increase caps gradually
- Only after multiple clean sessions.

## Abort criteria (immediate)
- Unexpected order type/quantity
- Any behaviour contradicting policy logs
- Any risk-engine mismatch vs expected
- IBKR connectivity anomalies
