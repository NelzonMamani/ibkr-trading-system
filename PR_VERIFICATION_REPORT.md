# PR Verification Report

## Summary
- Objective: enforce live/paper micro execution guardrails, daily loss limits, and remove teaching fallbacks in production scan paths.
- Status: Run-mode checks executed; LIVE_MICRO halted on safety violation due to deterministic price feed (IBKR unavailable).

## Checks
1. `python -m src.main --mode SIM --cycles 3`
   - Result: PASS
2. `python -m src.main --mode PAPER --cycles 3`
   - Result: PASS (execution disabled by default config)
3. `python -m src.main --mode READONLY --cycles 3`
   - Result: PASS (read-only; IBKR broker unavailable, SIM fallback in market data)
4. `python -m src.main --mode LIVE_MICRO --cycles 3`
   - Result: FAIL (safety halt: deterministic price feed detected in LIVE_MICRO; IBKR broker unavailable)

## Required Confirmations
- LIVE_MICRO executes real trades at 1 share — NOT VERIFIED (execution disabled and IBKR broker unavailable in this environment).
- Daily max loss enforced at −$10 — Implemented via DAILY_LOSS_HARD_LIMIT; not triggered during verification.
- No teaching mode active in production — NOT VERIFIED (scanner fell back to teaching/static paths due to missing IBKR connectivity).

## Notes
- LIVE_MICRO safety check correctly blocks deterministic price feed usage; requires IBKR connectivity and execution-enabled configuration to validate live execution.
- PAPER and LIVE_MICRO runs require `EXECUTION_ENABLED=True`, `IBKR_READONLY_ENABLED=False`, and IBKR order translation/submission enabled to verify real execution.
