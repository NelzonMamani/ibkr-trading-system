# Implementation Phases (Mandatory Order)

Codex must implement the strategy in **this exact order**.

PHASE 1 — Type Alignment
- Align ScannerFacts and MarketRegimeFacts to canonical system types
- Ensure no duplication or divergence

PHASE 2 — Strategy Registration
- Register Mean Reversion in strategy registry
- Ensure orchestrator can call it

PHASE 3 — Data Provisioning
- Ensure scanner provides all required facts
- Add missing measurements if absent

PHASE 4 — Policy Invocation
- Call MeanReversionStrategyPolicy per symbol per cycle
- Capture PolicyDecision outputs

PHASE 5 — Risk Integration
- Wire risk engine veto path
- Enforce stop/target immutability

PHASE 6 — Execution Mapping
- Translate TradeIntent into execution orders
- Respect mode-specific behavior

PHASE 7 — State & Telemetry
- Persist decisions, denials, intents
- Ensure full observability

PHASE 8 — Mode Validation
- Verify SIM / PAPER / LIVE_READ_ONLY / LIVE_MICRO / LIVE

PHASE 9 — Hardening
- Edge cases, guards, determinism
