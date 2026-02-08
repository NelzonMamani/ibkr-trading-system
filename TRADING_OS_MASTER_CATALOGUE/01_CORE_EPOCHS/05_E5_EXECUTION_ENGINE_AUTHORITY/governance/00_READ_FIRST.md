# E5 — EXECUTION ENGINE AUTHORITY (GOVERNANCE)

## Why this epoch exists
E5 certifies that the Trading OS has a **single, lawful, auditable** path from an approved `TradeIntent`
to an order submission and fill reconciliation outcome. The Execution Engine is the **only** component
permitted to:
- construct broker-facing orders
- submit / cancel / replace orders
- interpret fills and translate them into lifecycle state updates
- emit execution outcomes for storage, reporting, and review

E5 is **downstream** of:
- **E2 Position Lifecycle Engine** (positions and transitions are real)
- **E3 Risk Engine Completeness** (permission & sizing authority is real)
- **E4 Data Quality & Market State** (market/session trust gates are real)

E5 is **upstream** of:
- storage & accounting (trade store, order ledger, reconciliation reports)
- learning / reporting epochs
- strategy-level post-trade review

## Non-negotiable principle
**No execution bypass** is permitted. If any code path can transmit orders without going through the
Execution Engine, E5 is **not certified**.

## Terminology
- **Intent**: Strategy-produced proposed action (buy/sell/add/exit) with context.
- **RiskDecision**: E3 output that approves/rejects and provides effective sizing/limits.
- **ExecutionAttempt**: E5 tries to perform the approved action (submit/cancel/replace).
- **ExecutionResult**: Normalized result (accepted/rejected/partial/filled/cancelled) + reasons.
