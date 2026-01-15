# MODULE_REQUIREMENTS_execution
Last updated: 2026-01-15

## 1. Purpose
Execution is the only module permitted to interact with broker APIs (IBKR).
Execution must not invent signals, patterns, or intents. It only executes approved intents.

## 2. Mode Law (Hard)
- SIM: never submit/modify/cancel broker orders
- READONLY: never submit/modify/cancel broker orders (log “would place” only)
- LIVE_1SHARE: may submit orders only when risk-approved and within constraints

Any violation is a CRITICAL defect.

## 3. Inputs
- RiskDecision(s) + associated TradeIntent(s)
- broker connectivity state
- session state

## 4. Supported Order Types (Epoch 5 Minimum)
- Market (MKT) or marketable limit (preferred to reduce slippage surprises)
- Limit (LMT)
- Stop (STP) or stop-limit if supported

Brackets and advanced routing may be added later, but are not required for Epoch 5 completion unless Phase docs mandate.

## 5. Lifecycle Tracking (Mandatory)
Track and emit ExecutionEvents:
- submitted (with broker order id)
- acknowledged
- partial fill
- filled
- cancelled
- rejected
- error/warning (store + print)

## 6. Safety Rules
- Never loosen stops autonomously
- Never average down unless explicitly permitted by risk constraints (default NO_ADDING)
- On disconnect: halt submissions and raise DEGRADED/CRITICAL health depending on duration

## 7. Console Output (Mandatory)
For each cycle:
- summary counts: intents received, allowed, submitted (LIVE only)
- in READONLY: explicit “WOULD PLACE” lines; never show “SUBMITTED”
- in LIVE_1SHARE: explicit “SUBMITTED/ACK/FILL” lifecycle lines

## 8. Tests
- Mode law tests: ensure no broker calls in SIM/READONLY
- Lifecycle event mapping tests (mocked broker)

END.
