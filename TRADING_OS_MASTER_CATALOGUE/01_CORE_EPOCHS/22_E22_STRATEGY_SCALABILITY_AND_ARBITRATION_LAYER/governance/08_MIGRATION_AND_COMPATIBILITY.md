
# E22 Migration and Compatibility

## Compatibility requirements
- Existing strategies must continue to run under current orchestrator wiring.
- E22 is introduced behind a feature flag (config), default OFF in LIVE until certified.
- In SIM/PAPER, E22 may default ON for validation.

## Minimal wiring principle
- Add a single call-site in the orchestration path where intents are aggregated.
- Do not require each strategy to implement new interfaces immediately.
- Provide adapters:
  - `StrategyIntentEmitterAdapter`
  - `LegacyStrategyRunnerAdapter` (if needed)

## Backwards compatibility rules
- If a strategy does not provide priority/budget metadata, it receives conservative defaults.
- All defaults must be explicit (no hidden magic).
