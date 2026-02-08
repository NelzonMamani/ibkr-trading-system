# Reality Audit Checklist — E6

Inspect the repository and answer YES/NO with evidence:

1. Does the scanner emit facts only (no ranking or setup logic)?
2. Are scanner outputs mode-agnostic?
3. Are PRE/RTH/AH/CLOSED sessions explicitly labeled?
4. Are % change reference prices session-aware?
5. Are data quality flags surfaced per symbol?
6. Are empty watchlists treated as valid artifacts?
7. Does strategy policy consume scanner output without modifying scanner?
8. Is scanner logic independent of specific strategies?
9. Are fallback data sources explicitly flagged?

Produce a short audit summary.
