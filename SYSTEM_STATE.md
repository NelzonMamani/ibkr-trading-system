# SYSTEM STATE
## Current Authoritative Runtime State

CURRENT_PHASE: 24
SYSTEM_MODE: LIVE_READ_ONLY (IBKR primary, MOCK fallback)
EXECUTION_STATUS: HARD DISABLED
BROKER_WRITE_ACCESS: DISABLED

### Scanner Status
- Canonical output contract: 54 fields
- Unfiltered universe: TOP 50 US gainers
- Watchlist output: TOP 15 after Ross-aligned filters
- Scanner must always emit:
  - Raw candidate count
  - Filtered watchlist (even if empty, with explanation)

### News Status
- News is a Ross pillar but NOT a hard gate.
- News failures are expected and tolerated.
- Momentum fire indicator is derived ONLY from news analytics.

### Known Degradations
- RSS sources may rate-limit or reject requests.
- MOCK news fallback permitted.
- Some IBKR snapshot fields may be intermittently unavailable.

### Acceptance Criteria for Phase 24
- Scanner runs standalone without import errors.
- Scanner prints 54-field canonical output.
- Watchlist generation is observable in console.
- MOCK fallback operates transparently.

This file must be updated as phases advance.
