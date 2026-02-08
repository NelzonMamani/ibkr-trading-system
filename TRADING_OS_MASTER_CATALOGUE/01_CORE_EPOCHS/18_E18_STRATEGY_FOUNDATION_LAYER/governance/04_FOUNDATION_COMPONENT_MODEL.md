# E18 — FOUNDATION COMPONENT MODEL (SEMANTIC CONTRACTS)

E18 primitives must be defined as semantic contracts, not just code modules.

Each foundation component MUST declare:
- semantic_name (stable identifier)
- component_type (setup_family | execution_trigger | condition | confirmation | candle_pattern | level_zone | structure_state)
- inputs (typed; timeframe requirements; session sensitivity)
- outputs (typed; deterministic)
- assumptions (explicit)
- failure modes (what causes “unknown” or “invalid”)
- explainability hooks (optional details; never required for correctness)
- version tag (foundation version compatibility)

BINDING RULE:
Strategies bind to semantic_name contracts, not to file paths / implementations.

CUSTOM / STRATEGY-LOCAL EXTENSION:
Strategies may implement custom primitives ONLY if they:
- declare custom semantic_name namespace
- provide the same contract metadata
- appear in the translation report and coverage checklist

END
