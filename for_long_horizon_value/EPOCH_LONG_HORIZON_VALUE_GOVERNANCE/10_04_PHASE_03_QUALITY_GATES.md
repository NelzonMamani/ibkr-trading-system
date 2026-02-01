# 10_04_PHASE_03_QUALITY_GATES.md — PHASE 03: QUALITY & MOAT GATES

Goal:
- Apply Buffett-style quality gates producing PASS/FAIL with explicit reasons and a numeric quality score.

Codex tasks:
1) Implement quality gates as a pure function/engine inside strategy module (e.g., `quality_engine.py` or similar) OR within runner if your strategy folder stays minimal.
2) Gates must map to Strategy Constitution:
   - Understandability (documented boolean / flag for now)
   - Moat signals (proxy metrics are acceptable, but must be explicit)
   - Financial strength proxies (interest coverage, leverage)
   - Earnings stability proxies
3) Output:
   - For each symbol, produce:
     - pass/fail
     - reasons list
     - quality_score (0-100 or 0-1 scaled; choose one and freeze)
4) Recordkeeping:
   - Persist gate decisions as storage artifacts for audit.

Do NOT:
- Change `strategy_policy.py` thresholds.
- Use intraday scanner code.

Tests:
- Deterministic quality scoring for stable synthetic fixtures.
- “Hard veto” tests: banned symbol list forces NEVER.

END
