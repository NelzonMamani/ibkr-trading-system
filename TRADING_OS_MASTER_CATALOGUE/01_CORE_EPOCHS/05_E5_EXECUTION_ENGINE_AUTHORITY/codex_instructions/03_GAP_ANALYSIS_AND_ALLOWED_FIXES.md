# Gap Analysis & Allowed Fixes — E5

## Allowed fixes
- Add guards preventing direct broker adapter usage outside E5
- Add or harden execution engine entry points
- Add missing rejection paths for READ_ONLY
- Normalize PAPER/LIVE provider selection
- Add trace events or reason codes
- Add tests to prove authority and mode semantics

## Forbidden actions
- Refactor strategies or scanner logic
- Change risk math or capital allocation
- Rename modules or epochs
- Introduce new run modes
- Relax safety constraints

If a gap cannot be fixed without violating rules, STOP and report.
