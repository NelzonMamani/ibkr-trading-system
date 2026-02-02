# Detailed Tasks by Phase

## Phase 1 — Type Alignment
- Map ScannerFacts fields to scanner output
- Ensure ATR, VWAP, EMA, exhaustion flags exist
- Reject missing ATR early

## Phase 2 — Strategy Registration
- Add mean_reversion to strategy registry
- Ensure unique strategy identifier
- No conditional registration

## Phase 3 — Data Provisioning
- Scanner emits facts only
- No setup labels added to scanner
- MarketRegimeFacts available once per cycle

## Phase 4 — Policy Invocation
- For each symbol:
  - call evaluate_symbol()
  - capture allowed/denied decisions
  - never short-circuit internal gates

## Phase 5 — Risk Integration
- Risk engine may veto intent
- Risk engine may size position
- Risk engine may NOT remove stop/target

## Phase 6 — Execution Mapping
- SIM/PAPER: simulated fills
- LIVE_READ_ONLY: no orders, log only
- LIVE_MICRO: 1-share max
- LIVE: full size per risk engine

## Phase 7 — State & Telemetry
- Persist:
  - no-trade reasons
  - approvals
  - intent parameters
- Timestamp all actions

## Phase 8 — Mode Validation
- Each mode must run without code changes
- No silent downgrades

## Phase 9 — Hardening
- Deterministic outputs
- Explicit error messages
- No swallowed exceptions
