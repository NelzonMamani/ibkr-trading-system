# E5 — Canonical Order Lifecycle

## Required order states (normalized)
- CREATED (internal order object exists)
- SUBMITTED (sent to provider)
- ACKNOWLEDGED (provider/broker acknowledged)
- PARTIALLY_FILLED (one or more fills received; remaining qty > 0)
- FILLED (remaining qty == 0)
- CANCEL_REQUESTED
- CANCELLED
- REJECTED (terminal)
- ERROR (terminal when unrecoverable)

### Notes
- Multiple partial fills are permitted.
- Some brokers may not emit explicit ACK; E5 must normalize consistently.
- All transitions must be logged.

## Required linkages
- Every order must reference:
  - intent_id
  - position_id (if applicable)
  - execution_attempt_id
  - strategy_id (or strategy name)
