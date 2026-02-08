# VERIFICATION COMMANDS

The following verifications are mandatory for certification:

1. Ledger completeness
- For a sample run across modes, assert:
  - every emitted M9 signal links to >=1 provenance event_id
  - every E14 decision links to a provenance chain

2. Premarket prep coverage
- In PRE session, assert presence of provenance events for:
  - prior close reference
  - gap computation inputs
  - at least one zone/level artifact (if strategy requires zones)
  - news presence boolean or explicit UNKNOWN

3. Hydration audit
- For a committed symbol, verify:
  - DATA_HYDRATION_REQUESTED exists
  - READY or PARTIAL exists before first decision
  - limitations recorded when PARTIAL/DEGRADED

4. Mode truth sanity
- Verify MODE_TRUTH_MATRIX exists and matches configured modes:
  SIM, PAPER, READ_ONLY, LIVE

END
