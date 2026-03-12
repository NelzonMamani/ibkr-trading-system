# LIVE Ross Momentum Execution Path Audit Note

## Reconciliation Summary

- Duplicate IBKR connection ownership existed across `IbkrLiveBroker.ensure_connection`, `IbkrOrderSubmitter.submit_once`, and ad-hoc capital resolution in `core_engine/orchestrator.py`.
- Duplicate capital path existed where LIVE capital fell back to config default capital via `resolve_available_capital` and `RISK_ACCOUNT_EQUITY` fallback.
- Quantity loss/reset issue existed in the Epoch-5 order router path that hardcoded `submitted 1-share order` regardless of risk-approved size.

## Canonical Path Enforced

- Canonical broker owner is `IbkrLiveBroker`; submitter no longer performs connection lifecycle ownership.
- Canonical LIVE capital source is `IBKR_CANONICAL`; LIVE with unavailable canonical capital now blocks.
- Canonical quantity is the risk-approved quantity (`approved_quantity` / `max_position_size`) propagated to submission detail, with mismatch blocking.

## Deprecated/Bypassed Shadow Behaviours

- Submitter-level ad-hoc connect/disconnect ownership has been bypassed in favor of broker-owned session lifecycle.
- LIVE capital fallback behavior in strict mode is forbidden (`allow_fallback=False` raises `CANONICAL_CAPITAL_UNAVAILABLE`).
- The shadow “submitted 1-share order” reporting path is removed and replaced with explicit quantity reporting.

## Enforced Invariants

- LIVE capital law: `mode == LIVE => capital_source == IBKR_CANONICAL` else `BLOCK`.
- Quantity propagation law: `risk approved qty == submitted qty`, else `BLOCK` with `EXECUTION_QUANTITY_MISMATCH`.
- Invalid retry configuration (`host`/`port`) blocks connect path with explicit error.

## Evidence Tests

- `tests/test_live_execution_integrity.py` covers LIVE capital block, fallback prohibition, quantity propagation, mismatch block, and deterministic focus split sizing.
