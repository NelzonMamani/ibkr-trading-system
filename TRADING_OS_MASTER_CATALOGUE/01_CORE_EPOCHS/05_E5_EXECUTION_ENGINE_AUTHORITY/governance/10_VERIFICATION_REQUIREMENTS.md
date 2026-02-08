# E5 — Verification Requirements

Certification must include proof of:
1. **Authority**
   - There is no path to submit orders outside E5 in LIVE/PAPER.
2. **Mode correctness**
   - LIVE_READ_ONLY submission is blocked deterministically.
   - SIM uses sim provider only.
   - PAPER uses paper provider only.
3. **End-to-end execution**
   - A minimal trade intent can flow through: intent → risk approve → order → result.
4. **Reconciliation**
   - Partial fills update state correctly.
5. **Idempotency**
   - Re-running the same event timeline does not create duplicate orders.

## Required verification command classes (repo-specific scripts allowed)
- compileall
- pytest
- at least one smoke run per mode with execution disabled/enabled correctly
