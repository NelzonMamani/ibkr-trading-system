# E3_RISK_ENGINE_COMPLETENESS — Gap Analysis

## Summary of Gaps
- Risk decisions did not previously include required decision metadata (decision codes, evaluated limits, run mode, timestamp).
- Session/time gating and portfolio-level caps (max open positions, max total exposure) were missing from the risk engine.
- Risk-profile caps for per-trade notional and risk-per-trade were not enforced when entry/stop prices are available.
- Risk decision outputs were not emitted as explicit `RISK_DECISION` events for audit/replay.

## Remediation
- Added decision metadata fields to `RiskDecision` and populated them in all risk paths.
- Implemented session gating with `ACTIVE_SESSIONS` enforcement and new portfolio-level limits.
- Added risk-profile enforcement for position value and risk per trade when price data is provided.
- Emitted `RISK_DECISION` events for each decision to support audit and replay.
- Added test coverage for max-open-positions gating.
