# 12_GOVERNANCE_LOCKS_AND_AMENDMENT_POLICY

## Locks
- E21 defines “ready”. No strategy epoch may redefine readiness.
- E21 requires end-to-end proof. No claim of readiness is allowed without E21 artifacts.
- E21 is binary: PASS/FAIL. “Mostly ready” is FAIL.

## Amendment policy
- New scenarios can be added (never removed) unless superseded by explicit deprecation.
- PASS criteria can only be tightened, not weakened, except by explicit constitution amendment.
- Any change to harness entrypoints must be documented and versioned.

## Drift control
If a future change breaks determinism or parity, E21 must fail and block LIVE enablement until repaired.
