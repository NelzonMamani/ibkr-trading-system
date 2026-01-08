PHASE_23_FIX_LIVEREADONLYSCANNER_INTERFACE.md
# PHASE 23 — Fix LiveReadOnlyScanner Interface Completeness

## Problem
Runtime crash occurred in PHASE 23:

'LiveReadOnlyScanner' object has no attribute 'auto_lockdown_enabled'

This indicates that LiveReadOnlyScanner does not fully implement
the Scanner interface expected by CoreOrchestrator.

## Root Cause
Base Scanner defines:
- self.auto_lockdown_enabled (from get_ibkr_auto_lockdown_enabled)

LiveReadOnlyScanner omits this attribute, but CoreOrchestrator
accesses it unconditionally.

## REQUIRED FIX (MANDATORY)

### 1. Interface Parity
LiveReadOnlyScanner MUST define the following attributes
with identical semantics to Scanner:

- auto_lockdown_enabled
- fallback_enabled (if present in base Scanner)
- fallback_source (if present)
- max_symbols_per_cycle (if used)
- snapshot_max_age_seconds (if used)

Values must be sourced from the same config getters
used by the base Scanner.

### 2. Constructor Alignment
LiveReadOnlyScanner.__init__ must:
- Call the same config getters as Scanner
- Store attributes on self
- Not rely on inheritance assumptions

### 3. No Behaviour Change
This is an interface completion only.
- Do NOT alter lockdown logic
- Do NOT add execution paths
- Do NOT modify IBKR calls

### 4. Validation
After fix:
- PHASE 23 must boot
- LiveReadOnlyScanner must scan symbols
- Data quality flags may appear
- No AttributeError must occur
- System must continue cycles or halt gracefully by policy

## Acceptance Criteria
A correct run MUST:
- Stay in RUN_MODE=LIVE_READ_ONLY
- Use LiveReadOnlyScanner
- Produce live market data
- Not crash due to missing attributes

END