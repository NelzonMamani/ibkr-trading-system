# E16_NO_TRADE_CONTEXTS — AUTHORITY AND SCOPE

E16 has global authority.

When a no-trade context is active:
- All strategies are gated
- Execution authority is revoked
- Signals may be observed but not acted upon

Scope:
- Scanner
- Orchestrator
- Strategies
- Risk engine
- Execution engine

Invariant:
No strategy may bypass a no-trade context.

END
