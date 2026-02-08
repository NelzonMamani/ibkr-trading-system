# 09_FAILURE_INJECTION_AND_RECOVERY_DRILLS

## Non-negotiable doctrine
A trading system is only real if it survives failures deliberately induced.

## Mandatory failure drills (minimum)
1. Market data disconnect mid-cycle
2. Broker disconnect with open position
3. Order rejection on submit (bad symbol / permissions)
4. Partial fill + disconnect before full reconciliation
5. Process kill and restart during active position
6. DB write failure simulation (disk full / locked) with safe fallback behavior
7. Clock skew / session misclassification attempt (ensure safe no-trade gating)

## Recovery requirements
After recovery, system must:
- reconcile positions/orders
- restore lifecycle state (or safely stop with clear status)
- emit an audit artifact describing recovery actions taken
- prevent duplicate orders

## Evidence
Each drill produces:
- a trace event series
- a recovery artifact
- a PASS/FAIL verdict for that drill
