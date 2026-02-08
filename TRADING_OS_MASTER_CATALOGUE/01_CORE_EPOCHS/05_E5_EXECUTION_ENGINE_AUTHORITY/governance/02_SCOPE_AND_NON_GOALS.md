# E5 — Scope and Non-Goals

## In scope
- Execution Engine authority boundaries (who is allowed to submit orders)
- Order construction (internal order model → broker adapter model)
- Order routing (market/limit/stop, tif, routing hints if present)
- Provider selection (SIM vs PAPER vs LIVE providers)
- Order lifecycle tracking (submitted → ack → partials → fills → terminal)
- Fill interpretation and reconciliation (multiple fills, partial fills, corrections)
- Explicit, deterministic error handling (transient vs permanent)
- Execution trace events (intent_id, order_id, broker_order_id, timestamps, reasons)

## Not in scope
- Alpha/signal logic (strategies)
- Risk policy math (E3)
- Session detection rules (E4)
- Scanner selection logic (E6)
- Capital allocation arbitration (E10)
- Any refactor or rename of architecture epochs (certification-only approach)

## Explicit separation of concerns
Execution Engine may enforce safety and correctness, but must NOT:
- reinterpret strategy signals
- invent new intents
- change the risk-approved size beyond allowed rounding rules
