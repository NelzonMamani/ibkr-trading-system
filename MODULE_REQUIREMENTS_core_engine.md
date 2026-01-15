# MODULE_REQUIREMENTS_core_engine
Last updated: 2026-01-15

## 1. Purpose
Defines requirements for the Core Engine: orchestrator, scheduling, mode handling, and health management.

## 2. Deterministic Orchestrator Cycle (Mandatory)
Order:
Scanner → Data → Patterns → Strategy → Risk → Execution → Storage → Health

Rules:
- cycles do not overlap
- all stages must produce an artifact or an explicit error record
- stage failures must degrade safely

## 3. Session Awareness
Engine must classify current session state:
- PRE (premarket)
- REG (regular session)
- AFTER (after-hours)

Session must be:
- printed each cycle
- included in artifacts
- used in strategy gating (e.g., early-session bias)

## 4. Health State Machine
Health states:
- OK: all critical dependencies healthy
- DEGRADED: non-fatal impairment (e.g., enrichment missing, delayed data)
- CRITICAL: unsafe to trade; blocks execution actions

CRITICAL triggers (examples):
- broker disconnected in LIVE mode
- scanner fails repeatedly
- data feed missing for required fields
- storage unavailable in LIVE mode
- risk circuit breaker tripped

## 5. Configuration Requirements
Must support:
- mode selection
- cycle interval
- WatchlistK size and FocusM size
- scanner thresholds (price, %change, rvol, spread)
- risk limits (daily loss, max trades)
- logging verbosity

## 6. Console Output Requirements (Mandatory)
Each cycle prints:
- mode, session, cycle id
- scanner K/M lists
- stage timings (optional but useful)
- risk decision summary
- execution summary (mode-law compliant)
- health summary line

## 7. Tests
- “doctor” command to validate imports, config, and run a single scanner cycle
- orchestrator READONLY single-cycle smoke test
- health CRITICAL blocks execution

END.
