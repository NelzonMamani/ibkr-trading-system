# Implementation Tasks — E7

Perform ONLY if gaps are found:

1. Mode resolution
   - Resolve mode once at startup
   - Log resolved mode

2. Parity enforcement
   - Eliminate divergent logic paths
   - Centralize provider selection

3. Safety hardening
   - Ensure LIVE_READ_ONLY is non-executing
   - Ensure SIM cannot mutate live state

4. Traceability
   - Stamp all events with run_mode

5. Tests
   - Add tests proving parity and safety
