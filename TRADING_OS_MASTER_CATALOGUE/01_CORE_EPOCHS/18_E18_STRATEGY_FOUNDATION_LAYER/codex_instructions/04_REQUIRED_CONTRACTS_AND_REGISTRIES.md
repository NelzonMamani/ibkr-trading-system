# E18 — REQUIRED CONTRACTS AND REGISTRIES (SEMANTIC BINDING)

You must implement a semantic contract model for foundation components.

REQUIRED: Foundation Component Contract
Each component MUST declare:
- semantic_name (stable)
- component_type (setup_family|execution_trigger|condition|confirmation|candle_pattern|candle_behaviour|candle_state|level_zone|structure_state|invalidation)
- inputs (typed; timeframe/session notes)
- outputs (typed)
- assumptions
- failure modes
- optional explainability hooks
- version tag

REQUIRED: Registries (single source of truth)
Create (or extend) registries for:
- SF_* setup families
- XL_* execution triggers
- C_* conditions
- K_* confirmations
- Candlestick primitives (named/functional/contextual)
- Levels & zones primitives
- Market structure states vocabulary
- Invalidation semantics vocabulary

Rules:
- Strategies bind to semantic_name, NOT file paths.
- Strategy-local primitives are allowed ONLY if they expose the same contract and are declared in translation reports.

END
