## Scanner Responsibilities

The scanner MUST:
- Produce a candidate universe (e.g., Top N movers)
- Attach factual fields only (price, %change, volume, float, liquidity, spreads, halts)
- Be session-aware and explicit about reference prices
- Surface data quality flags (missing, stale, partial)
- Emit artifacts deterministically

The scanner MUST NOT:
- Rank by strategy preference
- Filter by setup logic
- Decide tradability
- Suppress empty outputs
