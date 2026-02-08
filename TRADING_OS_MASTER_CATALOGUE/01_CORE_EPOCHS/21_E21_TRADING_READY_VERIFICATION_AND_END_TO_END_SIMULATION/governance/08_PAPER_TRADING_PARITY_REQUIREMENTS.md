# 08_PAPER_TRADING_PARITY_REQUIREMENTS

## Principle
PAPER must be a **true dress rehearsal** for LIVE behavior with the same code paths:
- same orchestrator
- same strategy runner
- same risk engine
- same execution engine interface
- same lifecycle engine
- same storage/audit

Differences must be strictly declared:
- capital caps
- slippage modeling (optional)
- market data subscription limitations

## Mandatory PAPER checks
- IBKR connectivity health and reconnection behavior
- Market data timing: snapshot/wait semantics verified
- Order acknowledgements and error handling
- Position reconciliation against broker state
- No interference doctrine enforced (see next doc)

## “Ready for LIVE” implication
If PAPER cannot execute end-to-end (scan→trade→exit) with verifiable artifacts,
LIVE readiness is impossible.
