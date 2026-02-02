# Integration Points

## Orchestrator
- Calls strategy per cycle
- Supplies facts and regime
- Handles scheduling

## Scanner
- Supplies facts only
- No decisions

## Risk Engine
- Validates TradeIntent
- Applies sizing rules

## Execution Engine
- Translates intent to orders
- Mode-aware behavior

All integrations must preserve strategy boundaries.
