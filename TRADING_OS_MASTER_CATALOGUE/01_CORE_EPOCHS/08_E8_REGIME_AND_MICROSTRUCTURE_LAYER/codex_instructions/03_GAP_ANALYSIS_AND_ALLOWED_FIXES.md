# Gap Analysis & Allowed Fixes — E8

## Allowed fixes
- Wire existing regime layer into context passed to strategies
- Add missing observers or adapters (observational only)
- Add determinism guards
- Add trace events for regime outputs
- Add tests proving non-interference

## Forbidden actions
- Add trade intent generation
- Add execution or risk gating
- Add learning or auto-mutation
- Refactor strategies
- Change scanner responsibilities

Stop and report if forbidden changes are required.
