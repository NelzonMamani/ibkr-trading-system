# E16_NO_TRADE_CONTEXTS — REQUIRED CONTEXTS

Codex must ensure detection and gating for the following context classes:

1. Market Structure Contexts
   - Broad market chop (no follow-through)
   - Market-wide breakdowns

2. Session Contexts
   - Market CLOSED
   - Illiquid transition windows
   - Post-halt instability

3. Data Integrity Contexts
   - Missing critical inputs
   - Session reference mismatch
   - Stale reference prices

4. Risk Contexts
   - Daily max loss reached
   - Volatility shock events
   - Correlated drawdown

5. Behavioural Contexts
   - Consecutive losses threshold
   - Rule violations detected

Uncertainty defaults to NO TRADE.

END
