# EPOCH_03_RISK_AND_EXECUTION_GOVERNANCE.md
# EPOCH 03 — RISK & EXECUTION — GOVERNANCE (AUTHORITATIVE)

## 0. Scope statement
Epoch 3 authorizes the transition from **Decision Intelligence (Epoch 2)** to **Risk & Execution**, under strict safety constraints.

Epoch 3 delivers:
- Canonical **risk gating** for Strategy → Risk payloads
- Canonical **execution routing** (IBKR) that remains safe-by-default
- Canonical **stop-loss / exit enforcement**
- A staged rollout path: **Paper → SIM → LIVE_MICRO (1-share) → LIVE**

Epoch 3 does **not** authorize:
- Unbounded live trading
- Any bypass of risk gates
- Any “strategy places orders” behavior
- Any modification of immutable governance files

## 1. Authority and hierarchy
This file is authoritative for Epoch 3.

Governing hierarchy (highest wins):
1. SYSTEM_CONSTITUTION.md
2. SYSTEM_ROADMAP_EPOCH_02_TO_COMPLETION.md (frozen)
3. SYSTEM_STATE.md (current truth)
4. This file (Epoch 3 governance)
5. Phase documents for Epoch 3 (PHASE_31–PHASE_34)
6. Code/tests

If any conflict exists, the higher-order document overrides the lower-order document.

## 2. Epoch 3 boundary conditions (hard rules)
### 2.1 Execution remains off by default
- Execution MUST remain **HARD DISABLED** unless explicitly enabled by configuration in an allowed run mode.
- Default behavior after implementing Epoch 3 is still safe: **no live orders unless explicitly opted in**.

### 2.2 No broker routing in LIVE_READ_ONLY
- LIVE_READ_ONLY may fetch market data, but MUST block order routing at multiple layers.
- Any attempt to route orders while in LIVE_READ_ONLY must be treated as a defect.

### 2.3 Defense in depth is mandatory
Execution authorization MUST require all of:
- Allowed run mode (SIM / LIVE_MICRO / LIVE)
- Explicit EXECUTION_ENABLED flag
- Broker submission guard passes (read-only guard off, write allowed, etc.)
- RiskEngine approves the StrategyRiskPayload
- Circuit breakers are not tripped

### 2.4 Risk must be authoritative
- Strategy outputs are **suggestions**; RiskEngine is **authoritative**.
- RiskEngine must be able to veto, downgrade, or block intents deterministically.

### 2.5 Determinism and explainability
All risk/execution decisions must be:
- Deterministic for the same inputs
- Logged with explicit reasons
- Persistable in the event stream and storage

## 3. Deliverables (phases)
Epoch 3 is complete when the following phases are complete, tested, and documented:

- **PHASE 31 — Risk Engine Live Gate**
  - Canonical risk evaluation for StrategyRiskPayloads
  - Per-intent approval/veto with explicit reasons
  - Deterministic sizing policy scaffolding (can start as “1 share” for LIVE_MICRO)
  - Unit tests covering allow/deny reasons

- **PHASE 32 — Execution Engine (IBKR)**
  - Canonical order translation (intent → internal order → broker order)
  - Broker submission pipeline with retries and idempotency safeguards
  - Simulation adapter for SIM (no broker submission)
  - Integration tests verifying routing is blocked in LIVE_READ_ONLY

- **PHASE 33 — Stop & Exit Enforcement**
  - Stop-loss placement model and enforcement rules
  - Exit signal precedence rules (stop > risk kill-switch > strategy exit)
  - TradeExitEngine must close open trades deterministically in SIM and in LIVE_MICRO/LIVE when enabled
  - Tests ensuring stops are always honored

- **PHASE 34 — Live-Test Mode & Circuit Breakers**
  - Formal staged rollout modes and gates
  - Micro-live constraints (1-share, limited symbols, daily loss cap)
  - Circuit breakers that disable execution on threshold breaches
  - Operational runbook notes embedded in the phase doc

## 4. Prohibitions (explicit)
You MUST NOT:
- Implement new epochs, phases, or governance docs beyond Epoch 3
- Modify SYSTEM_CONSTITUTION.md or the frozen roadmap
- Add “secret” environment variables without documenting them in configuration references
- Add any execution path that can run without RiskEngine approval
- Assume market state; always treat “unknown” as “unsafe”

## 5. Definition of Done (Epoch 3)
Epoch 3 is Done when:
1. In SIM: the system can take StrategyRiskPayloads → RiskDecision → ExecutionResult without broker routing.
2. In LIVE_READ_ONLY: **no orders** can be routed; attempts are blocked and logged.
3. In LIVE_MICRO: orders can be routed **only** when all gates pass; orders constrained to micro limits.
4. Stop-loss and trade exits are enforced deterministically.
5. Circuit breakers can halt execution and remain latched until reset per rules.
6. Tests validate the above invariants.

---
End of EPOCH_03_RISK_AND_EXECUTION_GOVERNANCE.md
