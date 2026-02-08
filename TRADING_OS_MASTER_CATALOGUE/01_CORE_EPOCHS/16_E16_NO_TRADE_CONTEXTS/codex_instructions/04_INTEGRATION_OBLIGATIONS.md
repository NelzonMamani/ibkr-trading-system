# E16_NO_TRADE_CONTEXTS — INTEGRATION OBLIGATIONS

Scanner:
- Must surface context-relevant signals
- Must not suppress symbols silently

Strategies:
- Must check global no-trade state
- Must not attempt execution when gated

Risk Engine:
- May trigger contexts
- May not override active contexts

Execution Engine:
- Must hard-block order submission when gated

END
