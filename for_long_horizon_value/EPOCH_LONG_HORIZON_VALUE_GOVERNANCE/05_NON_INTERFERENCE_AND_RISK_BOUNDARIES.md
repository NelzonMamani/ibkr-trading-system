# 05_NON_INTERFERENCE_AND_RISK_BOUNDARIES.md — NON-INTERFERENCE (LOCKED)

Isolation rules:
- No reuse of intraday scanner logic.
- No price-action signals.
- No shared mutable state across strategies.

Risk authority:
- Risk engine may veto any TradeIntent.
- Strategy must not override, retry-spam, or bypass vetoes.

Capital governance:
- Percent-based allocations only.
- No leverage assumptions.
- No averaging down without Phase 09 re-underwrite and explicit reasons.

END
