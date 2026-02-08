# E18 — CONTEXT AND OBJECTIVE

Objective:
Implement the shared Strategy Foundation Layer so ALL strategies can reuse canonical primitives
(setups, triggers, conditions, confirmations, candlesticks, levels/zones, structure states, invalidations),
while preserving strategy policy primacy and enabling fast symbol context hydration.

E18 is foundational infrastructure. It must be:
- Policy-neutral
- Deterministic and testable
- Versioned and backward-compatible
- Resettable/regenerable for derived data
- Auditable via translation/coverage/drift reports

Required references:
- You MUST read the E18 governance bundle in TRADING_OS_MASTER_CATALOGUE/01_CORE_EPOCHS/18_E18_STRATEGY_FOUNDATION_LAYER/governance/
- You MUST treat all checklists in governance as BINARY pass/fail requirements.

END
