# Storage & Data Hygiene

Constraints:
- Database growth must be controlled.
- No unbounded time-series storage.

Rules:
- Float stored once per symbol per week
- News headlines stored ≤ 6 hours
- Prep cache cleared weekly
- Intraday snapshots remain ephemeral

Result:
- Predictable storage size
- Fast reads