# PHASE 4 — CHANGE CONTROL POLICY

## Purpose
Prevent uncontrolled modifications to institutionalized strategy policies.

## Change Categories

1. MINOR_CHANGE
   - Documentation clarification
   - Comment improvements
   - Non-functional refactoring

2. MATERIAL_CHANGE
   - Setup logic changes
   - Trigger modifications
   - Risk parameter adjustments
   - Execution model alteration
   - Intrabar doctrine updates

## Control Rules

MINOR_CHANGE → Requires documentation update + passing tests.
MATERIAL_CHANGE → Requires:
- Updated audit matrix
- Re-certification audit
- Updated SYSTEM_STATE_CERTIFIED
- Explicit PR governance summary

No direct structural edits allowed outside controlled PR process.
