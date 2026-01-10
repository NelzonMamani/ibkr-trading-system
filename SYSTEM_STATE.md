# SYSTEM STATE
## Current Authoritative Runtime State

CURRENT_PHASE: 24
SYSTEM_MODE: LIVE_READ_ONLY (IBKR primary, MOCK fallback)
EXECUTION_STATUS: HARD DISABLED
BROKER_WRITE_ACCESS: DISABLED

### Scanner Status
- Canonical output contract: 54 fields (ScannerRow54).
- Symbol discovery priority:
  1) IBKR-assisted symbols (free endpoints only)
  2) Configured defaults (teaching)
  3) MOCK fallback
- Watchlist output is always written, even if empty, with header counts and exclusion reasons.
- Symbol limits are printed each run with source and resolved caps.

### News Status
- News is advisory, not a hard gate.
- RSS failures are expected; they are summarized (domains + codes).
- If all feeds fail, news gates are bypassed automatically.
- News degradation reason is reported in scanner output.

### Known Degradations
- RSS sources may rate-limit or reject requests; summary logging is required.
- MOCK news fallback permitted when IBKR or RSS data is unavailable.
- IBKR snapshot fields may be intermittently unavailable (per-symbol degradation expected).
- Feedparser or requests libraries may be missing, triggering news gate bypass.

### Acceptance Criteria for Phase 24
- Scanner runs standalone as module and script without ImportError.
- Scanner produces 54-field output with missing-data flags.
- Symbol limits are printed with sources and resolved caps.
- RSS failures are summarized (not spammed), with degradation reasons.
- IBKR failures degrade gracefully per symbol; total failure falls back to MOCK.
- Watchlist file is always written with header counts and empty-watchlist reasons.
- Field audit and mechanical checklist artifacts exist in docs/.

This file must be updated as phases advance.
