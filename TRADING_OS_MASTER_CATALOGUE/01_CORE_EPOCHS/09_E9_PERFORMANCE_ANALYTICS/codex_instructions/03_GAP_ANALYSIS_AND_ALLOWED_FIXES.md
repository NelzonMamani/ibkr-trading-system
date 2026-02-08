# Gap Analysis & Allowed Fixes — E9

## Allowed fixes
- Add missing analytics modules or adapters
- Add deterministic recomputation paths
- Add attribution joins (strategy, regime, execution)
- Add metric definitions and versioning
- Add tests for known outcomes

## Forbidden actions
- Introduce live feedback loops
- Block or gate execution based on analytics
- Modify strategy or risk logic
- Infer missing data silently
- Change historical records

Stop and report if a forbidden change is required.
