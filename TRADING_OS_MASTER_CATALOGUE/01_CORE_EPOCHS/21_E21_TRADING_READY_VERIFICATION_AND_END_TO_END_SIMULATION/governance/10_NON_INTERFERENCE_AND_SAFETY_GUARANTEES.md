# 10_NON_INTERFERENCE_AND_SAFETY_GUARANTEES

## Non-interference doctrine (mandatory)
The Trading OS must not alter, cancel, or manage human orders except where:
- explicitly permitted by account segregation OR
- explicitly permitted by a dedicated operator policy that is itself audited

Default stance: **observe only** outside system-owned orders/positions.

## System-owned order marking
All system orders must be uniquely identifiable (tagging):
- client order ID prefix
- strategy name
- run id / cycle id
- account (paper/live)

## Hard safety gates (mandatory)
- READ_ONLY: no orders, ever
- LIVE: execution disabled by default unless explicitly enabled
- LIVE: micro-risk caps enforceable (shares, notional, daily loss)
- Kill switch: stops new orders immediately; open positions handled per doctrine
- SSR, halts, untradeable flags respected

## Operator controls (mandatory evidence)
- Clear console/system state printout of mode + execution enabled state at startup
- Explicit warnings when execution is enabled
- One-line “authority summary” for each cycle: mode, session, permissions, caps
