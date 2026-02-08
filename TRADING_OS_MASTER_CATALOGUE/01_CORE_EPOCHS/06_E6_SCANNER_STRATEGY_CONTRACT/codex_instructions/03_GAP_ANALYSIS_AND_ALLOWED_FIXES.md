# Gap Analysis & Allowed Fixes — E6

## Allowed fixes
- Remove strategy logic from scanner
- Move ranking/gating into strategy policies
- Add missing session labels or reference price declarations
- Add explicit data quality flags
- Harden scanner contracts and schemas
- Add tests proving mechanical purity

## Forbidden actions
- Add strategy intelligence to scanner
- Add trade intent generation to scanner
- Change execution or risk logic
- Introduce new run modes
- Break backward compatibility of scanner facts

If a fix violates rules, STOP and report.
