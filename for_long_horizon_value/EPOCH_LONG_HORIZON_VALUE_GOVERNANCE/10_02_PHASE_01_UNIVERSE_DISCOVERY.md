# 10_02_PHASE_01_UNIVERSE_DISCOVERY.md — PHASE 01: UNIVERSE DISCOVERY

Goal:
- Implement universe discovery for two input modes:
  A) MARKET_DISCOVERY (market-by-market, global priority order)
  B) MANUAL_SYMBOL_LIST (evaluate exactly provided symbols)

Constraints:
- Global-first: no market excluded due to ignorance.
- This phase is discovery + normalization only. No business decisions yet.

Codex tasks:
1) Create `contracts/universe.py` ONLY if your repo’s strategy module currently lacks it.
   - If long_horizon_value module is minimal, add the contract file under
     `src/strategies/long_horizon_value/contracts/universe.py`.
2) Implement `UniverseProvider` abstraction inside strategy module (not global scanner):
   - For MARKET_DISCOVERY:
     - Iterate markets in `config.MARKET_PRIORITY_ORDER`
     - Produce SymbolRef records with exchange/currency/country populated as best available.
   - For MANUAL_SYMBOL_LIST:
     - Convert symbols into SymbolRef with best-effort defaults; record flags if incomplete.
3) IBKR integration:
   - Use existing IBKR client/hub patterns from repo (do not invent new IBKR client).
   - If global “universe provider” exists elsewhere in system, call it; otherwise implement minimal IBKR query.
4) Output artifacts:
   - Persist a UniverseSnapshot record to existing storage system (db/json) using established storage engine patterns.
   - Emit a human-readable report summarizing counts by market.

Do NOT:
- Apply quality/valuation filters.
- Use intraday scanner code.

Tests:
- Contract smoke test: UniverseSnapshot serializes and includes counts_by_market.
- Determinism: for MANUAL_SYMBOL_LIST, ordering stable and deterministic.

END
