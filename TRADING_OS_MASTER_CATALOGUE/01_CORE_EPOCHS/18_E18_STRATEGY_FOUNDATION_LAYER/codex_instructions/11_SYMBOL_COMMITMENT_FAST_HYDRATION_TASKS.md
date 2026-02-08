# E18 — SYMBOL COMMITMENT & FAST CONTEXT HYDRATION TASKS (EDGE)

Source of truth: governance/17_SYMBOL_COMMITMENT_AND_FAST_HYDRATION.md

Goal:
When a strategy (or user) commits to a symbol (e.g., TSLA), the system hydrates all relevant data ASAP.

Task:
1) Define a “SymbolCommitment” event/command contract:
   - symbol
   - requested_timeframes (daily/hourly/intraday)
   - requested_context (levels/zones/candles/indicators/news availability)
   - strategy_id (optional)
2) Implement a “Context Hydrator” service that:
   - fetches bars immediately (daily/hourly/1m minimum)
   - computes derived series as DATA (VWAP/EMA/MACD optional)
   - computes candlestick outputs immediately
   - computes levels (PDC/PDH/PDL/HOD/LOD/whole/half; VWAP/EMA contexts as available)
   - queries news engine for HAS_NEWS boolean (minimum)

3) Add completeness flags:
   - data_complete bool
   - missing_components list

4) Integrate hydration with existing Watchlist/Focus pipeline where applicable:
   - On Focus list entry => commit event triggers hydration
   - Must not slow scanner path; only hydrate committed symbols.

Failure handling:
- If hydration fails or data incomplete, degrade safely (no-trade) and audit.

Deliverables:
- Deterministic tests via mocked data providers (no live IBKR dependency in unit tests)
- Clear logs / audit events

END
