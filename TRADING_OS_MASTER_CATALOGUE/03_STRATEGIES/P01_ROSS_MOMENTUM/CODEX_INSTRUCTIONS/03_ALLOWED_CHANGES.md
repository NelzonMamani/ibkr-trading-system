# FILE: 03_ALLOWED_CHANGES.md
# TITLE: Allowed Changes for Ross Momentum Implementation
Date: 2026-02-08

## Allowed (additive or safe refactor)
- Add missing dataclasses/spec sections to `strategy_policy.py` (e.g., FlagSpec, FlatTopSpec, ORBSpec, CandlestickGuardSpec).
- Add explicit SF/XL/C/K/SCP/MCP mappings and classification lists.
- Add policy parameters for any hard-coded values found in helpers/runner.
- Add or adjust StrategyContext fields in `strategy_context_schema.py` ONLY if required by policy (additive).
- Add strategy-local tests under `src/strategies/ross_momentum/tests`.

## Not allowed
- Removing existing policy fields without deprecation plan.
- Moving stock selection logic back into scanner.
- Re-introducing SignalEvent-driven strategy selection as the primary mechanism.
- Changing run modes semantics (SIM/PAPER/READ_ONLY/LIVE are locked).
- Breaking end-to-end flow.

END
