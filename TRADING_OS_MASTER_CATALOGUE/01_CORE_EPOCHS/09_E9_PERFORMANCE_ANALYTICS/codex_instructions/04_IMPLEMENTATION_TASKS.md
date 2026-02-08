# Implementation Tasks — E9

Perform ONLY if gaps are found:

1. Data ingestion
   - Consume trade ledger, fills, positions, execution traces

2. Metric computation
   - Implement core metrics (P&L, expectancy, drawdown, slippage)
   - Ensure deterministic ordering and rounding

3. Attribution
   - Join metrics by strategy, symbol, session, regime

4. Versioning
   - Centralize metric definitions
   - Version outputs when definitions change

5. Isolation
   - Ensure analytics runs offline / post-trade only

6. Tests
   - Add tests for known trade scenarios
