# E5 — Execution Authority & Hierarchy

## Authority hierarchy (strict)
Strategy → TradeIntent → (E4 data trust gate) → (E3 risk decision) → **E5 execution engine** → broker adapter

### Who may submit orders?
- **Only** the Execution Engine.
- Broker adapters are *transport layers* and must not be used directly by strategies or orchestrators.

### Prohibited behaviors
- Strategy calls broker adapter directly
- Orchestrator submits orders directly
- Any CLI utility bypasses E5 in LIVE or PAPER without explicit “unsafe” guardrails
- Any “test helper” path that can execute outside E5 in non-test modes

## Authority proof obligations
To certify E5, the repository must demonstrate:
- a single code path for submission in LIVE/PAPER
- all other paths are blocked or routed into E5
- enforcement via tests + runtime guards
