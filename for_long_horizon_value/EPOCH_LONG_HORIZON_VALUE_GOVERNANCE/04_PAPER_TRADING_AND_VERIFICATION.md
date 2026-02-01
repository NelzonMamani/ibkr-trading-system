# 04_PAPER_TRADING_AND_VERIFICATION.md — PAPER IS MANDATORY (LOCKED)

This strategy MUST prove end-to-end behavior in PAPER before any LIVE automation is enabled.

Minimum paper verification scenarios:
1) MARKET_DISCOVERY run with empty/no-capital simulation → creates WATCHLIST/FOCUS but no executions
2) MANUAL_SYMBOL_LIST run (e.g., TSLA, NVDA) → produces full checklist reports
3) Capital constrained scenario → Focus entries become BUY_READY only when capital rules allow
4) Determinism scenario → repeated run yields identical decisions given same inputs

No execution leakage:
- In PAPER, any execution must be explicit, controlled, and test-verified.
- In LIVE_READ_ONLY / LIVE_MICRO safety modes, strategy must never place orders.

END
