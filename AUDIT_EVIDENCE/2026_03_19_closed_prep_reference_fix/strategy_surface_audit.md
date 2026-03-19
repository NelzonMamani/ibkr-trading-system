# Strategy surface audit

- Canonical registry remains `mean_reversion` + `ross_momentum`.
- Legacy `GapAndGoStrategy` and `MomentumContinuationStrategy` were disabled from default enabled-strategy config to remove unintended live boot participation.
- `RossMomentumStrategyV1` remains as the existing compatibility runner surface and is audited by `verification_scripts/verify_strategy_runtime_surface.py`.
