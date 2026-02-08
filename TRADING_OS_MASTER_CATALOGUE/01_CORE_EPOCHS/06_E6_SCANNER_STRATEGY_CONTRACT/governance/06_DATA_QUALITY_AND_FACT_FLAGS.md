## Data Quality & Fact Flags

Each symbol must carry:
- Data source (IBKR / fallback / cached)
- Freshness timestamp
- Quality flags (OK / PARTIAL / STALE / INVALID)
- Reason codes for exclusion if dropped

Strategies decide how to react.
