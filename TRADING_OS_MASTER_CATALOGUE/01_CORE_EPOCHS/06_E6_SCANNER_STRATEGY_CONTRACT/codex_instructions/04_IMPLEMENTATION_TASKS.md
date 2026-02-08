# Implementation Tasks — E6

Perform ONLY if gaps are found:

1. Mechanical purity enforcement
   - Ensure scanner emits facts only
   - Remove ranking/decision branches

2. Session semantics
   - Explicit PRE/RTH/AH/CLOSED handling
   - Declare reference prices per session

3. Data quality surfacing
   - Add freshness timestamps
   - Add quality flags (OK / PARTIAL / STALE / INVALID)

4. Artifact guarantees
   - Allow empty watchlists
   - Timestamp and session-tag artifacts

5. Strategy integration
   - Ensure strategies fully own filtering and ranking
   - No scanner changes required for strategy evolution

6. Tests
   - Add tests proving scanner purity and empty-output validity
