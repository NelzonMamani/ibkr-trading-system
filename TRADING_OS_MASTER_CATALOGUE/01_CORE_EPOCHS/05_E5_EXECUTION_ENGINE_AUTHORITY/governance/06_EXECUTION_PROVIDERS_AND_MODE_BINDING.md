# E5 — Execution Providers & Mode Binding

## Providers
The execution engine selects a provider **solely** based on resolved run mode:
- SIM → SimExecutionProvider
- PAPER → PaperExecutionProvider (broker or simulator with paper semantics)
- LIVE_READ_ONLY → NullExecutionProvider (always rejects submission)
- LIVE → LiveExecutionProvider (IBKR)

## Binding rules
- Provider must be selected once per runtime start and logged.
- Provider switching mid-run is forbidden except via controlled restart.
- Provider must expose a minimal interface:
  - submit(order)
  - cancel(order_id)
  - replace(order_id, new_order)
  - stream_fills(order_id) / poll_fills(order_id)

## Paper and Live equivalence
- Paper and Live must use the same order models and normalization logic.
- Differences are limited to:
  - endpoint host/port/account
  - broker-level behavior differences that must be normalized to the canonical model
