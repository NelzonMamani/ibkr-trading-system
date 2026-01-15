# PHASE_31_RISK_ENGINE_LIVE_GATE.md
# PHASE 31 — RISK ENGINE LIVE GATE (AUTHORITATIVE)

## 0. Purpose
Implement the canonical **RiskEngine** behavior that gates StrategyRiskPayloads before any execution step.

RiskEngine must:
- Be deterministic and explainable
- Provide per-intent approve/deny decisions with explicit reasons
- Produce a canonical RiskDecision object suitable for storage and execution
- Support SIM and LIVE modes with progressively stricter constraints

## 1. Inputs and outputs
### 1.1 Input (required)
- `StrategyRiskPayload` (Epoch 2 contract)
  - strategy_id, symbol, intents, decision_type, confidence, rationale_text, risk_flags

### 1.2 Output (required)
- `RiskDecision` (existing `src/models/risk_decision.py` or new canonical model if needed)
  - overall_action: ALLOW / BLOCK / DOWNGRADE / REQUIRE_CONFIRMATION (if applicable)
  - per_intent: list of intent decisions (ALLOW/BLOCK with reasons)
  - sizing: position size model output (can start simple)
  - risk_reasons: machine-readable tags + human-readable rationale
  - circuit_breaker_tripped: bool (integration with Phase 34)

## 2. Canonical risk gates (minimum set)
Risk gates are evaluated in a fixed, deterministic order. If a gate fails, it must emit a reason tag.

### Gate A — Execution safety context
- If run mode is LIVE_READ_ONLY → RiskDecision MUST be BLOCK for any execution request.
- If EXECUTION_ENABLED is false → BLOCK.
- If broker submission guard fails → BLOCK.

### Gate B — Data quality and veto flags
- If payload.risk_flags contains severe flags (e.g., `data_quality`, `wide_spread`) → BLOCK or DOWNGRADE depending on policy.
- Default policy in LIVE_MICRO/LIVE: BLOCK on `data_quality`.

### Gate C — Intent sanity
- No intents → NO_ACTION (not a block; just nothing to do).
- Duplicate intent IDs in same cycle → deduplicate and record reason tags.
- Unknown symbols or missing required fields → BLOCK those intents.

### Gate D — Microstructure constraints (minimum viable)
- Spread too wide (config threshold) → BLOCK.
- Price out of allowed range (config) → BLOCK.
- Volume / RVOL below minimum (if provided) → DOWNGRADE or BLOCK (policy-driven).

### Gate E — Exposure and loss limits (scaffolding)
Epoch 3 introduces the canonical placeholders and enforcement hooks:
- max_daily_loss_limit (latched circuit breaker)
- max_open_positions
- max_notional_per_symbol (even if sized to 1 share initially)
- per-strategy caps

In Phase 31 you must implement the data structures and the enforcement checks, even if initial values are conservative defaults.

## 3. Sizing policy (Epoch 3 minimum)
Sizing must exist, but can be conservative:
- SIM: allow configurable sizing model (default small)
- LIVE_MICRO: fixed size = 1 share (or minimal units) unless explicitly overridden by governance config
- LIVE: allow normal sizing only if all circuit breakers and caps are enabled

Sizing output must be explicit and logged.

## 4. Required code touchpoints (expected)
- `src/risk/risk_engine.py` (canonical implementation)
- `src/models/risk_decision.py` (ensure fields cover per-intent reasons)
- `src/core/orchestrator.py` (ensure RiskEngine is called before ExecutionEngine)
- `tests/` add unit tests for allow/deny logic

## 5. Required tests (minimum)
Add/extend tests to validate:
1. LIVE_READ_ONLY always blocks execution requests
2. EXECUTION_ENABLED false blocks
3. spread threshold blocks
4. data_quality flag blocks in LIVE_MICRO/LIVE
5. sizing returns 1 share in LIVE_MICRO

Tests should be deterministic and not require IBKR connectivity.

## 6. Acceptance criteria
Phase 31 is complete when:
- Risk decisions are produced deterministically and logged
- Per-intent decisions include explicit reason tags
- RiskDecision can be persisted in storage as part of TradeRecord
- Tests cover the critical gates above

---
End of PHASE_31_RISK_ENGINE_LIVE_GATE.md
