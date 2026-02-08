# 04_CERTIFICATION_MODEL_PASS_FAIL

## Certification levels
E21 introduces two certification scopes:

### A) Foundation Trading-Ready Certification (E21)
Proves the Trading OS pipeline is correct and safe end-to-end with at least one reference strategy.

### B) Strategy Tradability Certification (Strategy epochs)
Each strategy must pass E21 harness tests before being marked tradable.

E21 must define the methodology for both, but only grants (A).

## PASS criteria (E21)
PASS requires all of the following:
- All mandatory verification suites executed (SIM + PAPER minimum)
- Mode parity evidence recorded
- Failure drills executed and passed
- Non-interference verified
- Artifacts produced and archived
- Known gaps documented (allowed only if they do not violate safety/authority invariants)

## FAIL criteria (E21)
Immediate FAIL if any of these occur:
- Any critical-path placeholder/stub exists
- Any suite is skipped
- Any order is emitted in READ_ONLY
- Unbounded risk exposure occurs
- Orchestrator/strategy violates policy primacy
- Event spine is non-deterministic in SIM for the same scenario seed
- Recovery leaves system in unknown state
