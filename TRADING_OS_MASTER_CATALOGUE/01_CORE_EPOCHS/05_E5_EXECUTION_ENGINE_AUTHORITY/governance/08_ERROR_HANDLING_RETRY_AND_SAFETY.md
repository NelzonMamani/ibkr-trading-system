# E5 — Error Handling, Retry, and Safety

## Error classes
1. Guard violation (mode/read-only/risk/data gate) → immediate reject; no retry.
2. Permanent broker reject (insufficient permissions, invalid contract) → reject; no retry.
3. Transient transport faults (disconnect, timeout) → bounded retry if safe.
4. Ambiguous outcome (unknown submission state) → enter SAFE-HOLD, require reconciliation poll; no duplicate orders.

## Retry rules
- Retries are capped (e.g., max_attempts).
- Retries are never allowed to increase risk exposure beyond approved intent.
- For replace/cancel, retry is allowed only if idempotency is preserved.

## Safety escalation
- If repeated failures indicate broker instability, E5 may raise a STOP signal via StopController.
- E5 must emit a high-severity fault event when halting.
