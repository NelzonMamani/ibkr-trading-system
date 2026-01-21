# 17 — TESTS, SAFETY BOUNDARIES, AND VERIFICATION (LEARNING EPOCH)

## Objective
Keep learning changes safe, testable, and non-invasive.

## Safety boundaries
- Learning code must never import broker submission pathways.
- Learning code must never call order routing.
- Learning code may only read:
  - storage
  - configuration
  - policy schemas

## Required tests
1. Unit tests:
   - report generation on empty DB
   - report generation with mocked TradeRecords
   - policy proposal eligibility thresholds
   - proposal schema matches baseline schema exactly
2. Integration test:
   - start system in SIM with event generation
   - run learning CLI against produced DB

## Performance constraints
- Reports must complete quickly (seconds to tens of seconds).
- Use incremental computation and caching where needed.

## Mandatory Verification Commands
After implementing the Learning Epoch, run `99_MANDATORY_VERIFICATION_COMMANDS.md`.
Additionally run:
- `python -m src.learning.cli report --date <some date> --strategy ROSS_MOMENTUM`
- `python -m src.learning.cli propose-policy --strategy ROSS_MOMENTUM --min-trades 30`

END
