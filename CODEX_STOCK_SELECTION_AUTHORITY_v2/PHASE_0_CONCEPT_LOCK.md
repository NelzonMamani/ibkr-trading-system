PHASE 0 — CONCEPT LOCK (NO CODE)

Objective:
- Confirm architectural truth before touching code.

Non‑Negotiable Rules:
1. Orchestrator may NOT invent strategy logic.
2. StrategyPolicy (ross_momentum/strategy_policy.py) is authoritative.
3. Scanner executes StockSelectionPolicy mechanically.
4. Empty results are VALID.
5. No heuristic padding. No invented defaults.

Canonical Flow:
50 TOP_GAINERS
→ mechanical gates → ~15
→ catalyst/news diagnostics → 3–5
→ allow empty
→ log drop reasons
