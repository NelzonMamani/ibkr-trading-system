# Gap Analysis & Allowed Fixes — E7

## Allowed fixes
- Remove hidden mode-specific branches
- Centralize mode resolution
- Harden execution blocks for LIVE_READ_ONLY
- Align PAPER/LIVE risk enforcement
- Add trace fields for mode
- Add tests proving parity

## Forbidden actions
- Introduce new modes
- Introduce experimental shortcuts
- Relax safety for testing convenience
- Change strategy logic
- Refactor architecture

If a fix violates rules, STOP and report.
