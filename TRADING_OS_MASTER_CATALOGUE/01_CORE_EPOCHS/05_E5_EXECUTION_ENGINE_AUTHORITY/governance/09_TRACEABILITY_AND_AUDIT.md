# E5 — Traceability & Audit

E5 must emit structured events sufficient for:
- forensic replay (what happened and why)
- compliance review (even for personal trading: reproducibility)
- debugging and regression detection

## Minimum required fields per execution attempt
- timestamp_utc
- run_mode
- strategy_id
- symbol
- intent_id
- execution_attempt_id
- risk_decision_id (or hash)
- provider_name
- order_id (internal)
- broker_order_id (if any)
- outcome_state (FILLED / PARTIAL / REJECTED / CANCELLED / ERROR)
- reason_codes (list)
- latency_ms (if measurable)

## Storage integration
Events must be compatible with existing trace bus/event collector conventions.
