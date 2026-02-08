# E5 — Fill Handling & Reconciliation

## Fill model requirements
- Each fill has:
  - broker_order_id
  - fill_id or broker exec id (if available)
  - filled_qty, fill_price
  - timestamp (broker or normalized)
  - liquidity flag if available (add/remove)
  - commission estimate if available

## Reconciliation invariants
- Total filled qty must never exceed original order qty.
- Partial fills accumulate; remaining qty is tracked deterministically.
- Position updates occur only from fills (not from assumptions).
- If broker reports a correction, E5 must emit a correction event and reconcile idempotently.

## Persistence expectations (downstream)
E5 must produce artifacts that storage can persist:
- order ledger entries
- fill ledger entries
- execution result records
- linkage to position lifecycle transitions
