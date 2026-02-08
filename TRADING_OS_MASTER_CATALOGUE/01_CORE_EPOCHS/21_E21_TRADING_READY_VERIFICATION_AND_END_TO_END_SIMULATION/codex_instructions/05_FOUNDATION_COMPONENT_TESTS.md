# 05_FOUNDATION_COMPONENT_TESTS

Codex must create exhaustive tests for:

A. Setup Families
- Each SF_* must detect valid geometry
- Must reject invalid lookalikes

B. Candlesticks
- Single-candle SCP_* attribute validation
- Multi-candle MCP_* sequence validation

C. Execution Triggers
- XL_* fire only when conditions + confirmations satisfied
- Must never fire standalone

D. Conditions & Confirmations
- Deterministic boolean behavior
- Composable behavior

E. Levels / Zones / Invalidations
- VWAP, EMA, levels computed correctly
- Invalidation rules enforced

All components must be testable in isolation AND in pipeline.
