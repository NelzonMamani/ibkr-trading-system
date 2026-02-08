# E18 — REALITY CERTIFICATION STEPS (MANDATORY FIRST)

Codex must certify existing repo reality BEFORE implementing anything.

Step A — Locate current strategy foundation code:
- Search for existing “setup family”, “trigger”, “condition”, “confirmation”, “candlestick” modules.
- Identify existing registries/factories used by strategies (Ross, Statistical, Mean Reversion, Value).

Step B — Map existing reality to E18 governance checklists:
Produce a file at:
TRADING_OS_MASTER_CATALOGUE/01_CORE_EPOCHS/18_E18_STRATEGY_FOUNDATION_LAYER/governance/REALITY_MAP_E18.md

REALITY_MAP_E18.md must include:
- For each checklist item (SF/XL/C/K/candles/levels/zones/structure/invalidations):
  - implemented? (yes/no)
  - location (module path)
  - contract shape (inputs/outputs)
  - test coverage status (yes/no)
- Identify gaps and duplicates.
- Identify any strategy-local re-implementations that should be moved to foundation OR declared as custom.

Step C — Define “minimum additive path”:
- For each missing item, propose the smallest additive implementation that conforms to governance.
- No re-architecting.

No implementation begins until REALITY_MAP_E18.md exists.

END
