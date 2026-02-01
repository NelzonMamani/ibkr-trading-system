# 10_03_PHASE_02_FUNDAMENTALS_ASSEMBLY.md — PHASE 02: FUNDAMENTALS ASSEMBLY

Goal:
- For a set of SymbolRef from Phase 01, assemble normalized fundamentals inputs sufficient for quality/economics/valuation.

Key requirement:
- Data quality must be explicit. If data missing/unreliable, decision must become NO (cannot evaluate) with reasons.

Codex tasks:
1) Create/extend contracts under `src/strategies/long_horizon_value/contracts/`:
   - `fundamentals.py` (bundle + quality flags) if missing.
2) Implement a fundamentals assembly pipeline that:
   - Fetches multi-year financial statements (income/balance/cashflow) + share count + dividends.
   - Normalizes currency where needed using FX rates.
   - Produces a FundamentalsDataset with per-symbol `data_quality_flags`.
3) Data sources:
   - Prefer existing repo providers/utilities; do not add heavy third-party dependencies.
   - If IBKR fundamentals are insufficient, use an existing approved fallback provider if already in repo.
4) Caching:
   - Since this strategy runs off-hours and is heavy, implement caching under `data/cache/long_horizon_value/` (aligned with repo cache conventions).
   - Cache keys must include date + symbol + statement type.

Output artifacts:
- Store fundamentals dataset metadata and quality flags.
- Emit report: coverage %, missing fields, symbols dropped due to missing minimum history years.

Tests:
- Unit test: missing critical statement fields produces data_quality_flags and demotes to NO in later phases.
- Cache test: repeated run reads cache and produces identical dataset ids.

END
