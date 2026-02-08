# E16_NO_TRADE_CONTEXTS — OBLIGATIONS

Strategies:
- Must check global no-trade state
- Must not attempt execution when gated
- May continue diagnostics only

Orchestrator:
- Sole authority to activate/deactivate contexts
- Must enforce gates before execution path

Risk Engine:
- May trigger no-trade contexts
- Cannot override them

END
