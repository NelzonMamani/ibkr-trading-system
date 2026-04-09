# IBKR Inactive Diagnosis Runbook (Single Order)

Use this runbook to collect unambiguous execution evidence for exactly one submitted order.

## 1) Enable single-order validation control

Set:

```bash
export EXECUTION_SINGLE_ORDER_VALIDATION_MODE=1
```

This allows normal candidate generation but suppresses additional submissions after the first real submit attempt.

## 2) Run one normal paper/live cycle

Run your normal cycle command (paper/live) without strategy/risk threshold changes.

## 3) Extract required logs for the one submitted order

Collect these lines for the same `order_id`:

1. `[EXECUTION][ORDER_WIRE_PAYLOAD]`
2. `[IBKR][OPEN_ORDER_DETAIL]`
3. `[EXECUTION][FILLABILITY]`
4. `[IBKR][CALLBACK_RAW] event=orderStatus`
5. `[EXECUTION][INACTIVE_CLASSIFICATION]`
6. `[IBKR][CALLBACK_RAW] event=execDetails` (if any)

## 4) Interpret quickly

- If fillability is marketable and open-order echo matches payload, INACTIVE usually points to session/routing/held semantics.
- If fillability is passive/non-marketable, INACTIVE likely reflects non-marketable limit behavior.
- If quote context is absent, expect `INACTIVE_NO_QUOTE_CONTEXT` unless stronger `whyHeld` evidence exists.
