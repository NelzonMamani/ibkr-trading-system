# SYSTEM_CONSTITUTION.md
# IBKR Trading OS — Normative Constitution (Intent / Law)

**Status:** FROZEN (authoritative intent)
**Last updated:** 2026-02-03
**Scope:** Defines what the Trading OS **must** do when fully complete, expressed as Epoch guarantees.
**Non-scope:** This document does **not** describe current implementation reality. That is recorded in SYSTEM_CONSTITUTION_CERTIFIED.md.

## Global Non‑Negotiables (apply to all epochs)

- **Reality over intent:** Nothing is “DONE” unless certified by verification commands and evidence artifacts.
- **Single authority chain:** Strategies emit intents; Risk authorizes; Execution submits; Storage persists; Trace records.
- **Mode safety:** READ_ONLY never submits orders; PAPER never touches broker; LIVE can submit only with explicit enablement + risk approval.
- **No silent decisions:** Every block, skip, degrade, or action emits a reason code and stage.
- **One epoch at a time:** Certification proceeds strictly in ascending epoch order unless explicitly overridden by human instruction.

---

## CORE EPOCHS (E0–E18)

### E0_SYSTEM_LAW_TRUTH
**Purpose:** Establish immutable law, mutable state, and canonical truth sources.
**This epoch guarantees:**
- A single, immutable law document governs system constraints and authority boundaries.
- A mutable state document exists for declared system status and operational parameters.
- A certified state document exists and is the only authoritative statement of reality.
- Any behavior change must be reflected in certification artifacts before being treated as true.

### E1_TRACEABILITY_OBSERVABILITY
**Purpose:** Ensure no silent decisions; everything is traceable.
**This epoch guarantees:**
- Stage taxonomy exists (BOOT → SHUTDOWN) and is consistently applied.
- Every decision includes reason codes and minimal required fields (mode, strategy, cycle_id, symbol when relevant).
- Trace output supports audit, debugging, and downstream learning (E11).

### E2_POSITION_LIFECYCLE_ENGINE
**Purpose:** Unified lifecycle: entry → add → reduce → exit, with persistence.
**This epoch guarantees:**
- Canonical position state machine with deterministic transitions.
- Supported intent types (at minimum): OPEN, ADD, SCALE_OUT, FULL_EXIT, STOP_EXIT, TIME_EXIT, RISK_EXIT, SYSTEM_EXIT.
- Lifecycle actions are mode-aware and produce trace + persistence artifacts.
- PAPER mode supports simulated fills sufficient to exercise lifecycle logic.

### E3_RISK_ENGINE_COMPLETENESS
**Purpose:** Risk is the sole authority that permits execution.
**This epoch guarantees:**
- No strategy can bypass risk gating.
- Deterministic risk verdict schema (ALLOW/BLOCK/DEGRADED) with reason codes.
- Circuit breakers (loss limits, exposure caps, trade limits) and safety rules are enforced centrally.
- Risk integrates data-quality and no-trade contexts (E16).

### E4_DATA_QUALITY_MARKET_STATE
**Purpose:** Session-aware market data truth + integrity gates.
**This epoch guarantees:**
- Canonical session labeling (PRE/RTH/AH/CLOSED) including weekends/holidays.
- Reference-price and percent-change semantics are explicit and consistent with session policy.
- Data quality flags exist (stale, missing subscription, wide spread, halted/SSR where relevant).
- Degraded states cannot silently proceed into execution.

### E5_EXECUTION_ENGINE_AUTHORITY
**Purpose:** Single execution interface; providers differ by mode.
**This epoch guarantees:**
- Execution provider abstraction exists with strict mode semantics.
- READ_ONLY hard-blocks submission; PAPER simulates; LIVE submits via broker adapter.
- Order lifecycle events (submit/ack/fill/reject/cancel) are emitted and persisted.
- Execution cannot run without risk approval (E3).

### E6_SCANNER_STRATEGY_CONTRACT
**Purpose:** Scanner is mechanical; strategy owns selection/ranking logic.
**This epoch guarantees:**
- Strategy supplies StockSelectionSpec (universe constraints and caps).
- Scanner produces TopN snapshot and Watchlist K using mechanical rules and provided spec.
- Empty watchlists are valid and must be traceable with reason codes.
- Scanner does not embed discretionary edge logic (policy lives in strategy/foundation).

### E7_MODE_PARITY_AND_SAFETY
**Purpose:** Guarantee consistent semantics across READ_ONLY/PAPER/LIVE.
**This epoch guarantees:**
- Mode truth table exists and is enforced.
- Only execution behavior differs by mode; scanning/strategy/risk semantics remain consistent.
- Misconfiguration is surfaced loudly (trace + hard blocks where required).

### E8_REGIME_AND_MICROSTRUCTURE_LAYER
**Purpose:** Produce regime snapshots; strategies consume them for gating.
**This epoch guarantees:**
- RegimeSnapshot contract exists and is emitted each cycle.
- Regime is computed centrally (not inside strategies).
- Strategies and risk gates can block or throttle based on regime.

### E9_PERFORMANCE_ANALYTICS
**Purpose:** Measure performance, slippage, attribution, and reporting.
**This epoch guarantees:**
- Canonical trade/performance ledger exists (at least daily summaries).
- Reports can be produced from persisted events/orders/fills/positions.
- Strategy-level attribution exists or is explicitly deferred with a defined interface.

### E10_CAPITAL_ALLOCATION
**Purpose:** Multi-strategy portfolio governance and allocation.
**This epoch guarantees:**
- Capital allocation contract exists (budgets, priority, overlap caps).
- Allocation decisions are traceable and do not bypass risk.

### E11_LEARNING_SYSTEM
**Purpose:** Post-facto learning reports and proposals under strict governance.
**This epoch guarantees:**
- Learning consumes events/decisions/trades and never trades or modifies live behavior.
- Sample gating exists (e.g., evaluate after 30–100 trades per strategy window).
- Outputs are **reports + proposals**, requiring human approval to change policy/params.
- Learning is auditable and deterministic given the same inputs.

### E12_RECOVERY_AND_HOUSEKEEPING
**Purpose:** Operational recovery: backups, resets, retention, safe-to-delete policy.
**This epoch guarantees:**
- DB backup and hard-reset mechanisms exist with documented procedures.
- Retention and safe-to-delete rules are explicit and enforced where possible.
- Operational runbooks exist for recovery scenarios.

### E13_STRATEGY_FACTORY_STANDARD
**Purpose:** Uniform strategy wiring and test rules.
**This epoch guarantees:**
- Standard strategy folder and wiring contract exists.
- Strategy-local unit tests live under src/strategies/<strategy>/tests (locked rule).
- Cross-strategy/system tests live outside strategy folders.

### E14_DECISION_ARTIFACTS
**Purpose:** Structured decision objects for audit and learning.
**This epoch guarantees:**
- Canonical decision schemas exist (Entry/Add/Reduce/Exit/Block).
- Decisions serialize into logs and persistence for replay/analysis.

### E15_FAILURE_MODES
**Purpose:** Explicit failure taxonomy and degraded policies.
**This epoch guarantees:**
- Failure mode registry exists (connectivity, data, broker rejects, mode violations).
- System response is deterministic: degrade/halt/skip with reason codes and evidence.

### E16_NO_TRADE_CONTEXTS
**Purpose:** Explicit contexts that block or throttle trading.
**This epoch guarantees:**
- No-trade contexts are defined (e.g., stale data, wide spreads, halt uncertainty, lunch liquidity vacuum).
- Risk and/or strategy gates enforce these contexts with traceable blocks.

### E17_STRATEGY_INTERACTION_RULES
**Purpose:** Multi-strategy overlap/priority/exposure rules.
**This epoch guarantees:**
- Rules for symbol overlap, cooldown propagation, and priority are defined.
- Portfolio router (or equivalent) applies rules deterministically.

### E18_STRATEGY_FOUNDATION_LAYER
**Purpose:** Shared strategy-agnostic primitives and libraries.
**This epoch guarantees:**
- Foundation inventories exist for: Setup Families, Execution Triggers, Conditions, Confirmations.
- Candlestick pattern primitives exist (single + multi-candle), as reusable detection logic only.
- Strategies compose from foundation primitives; duplication is prohibited by tests/policy.
- Foundation primitives are pure logic (no broker calls, no DB writes), fully unit-tested.

---

## METADATA EPOCHS (M0–M10)

### M0_CANON
- Canon glossary and definitions exist; prevents term drift.

### M1_ARCHITECTURE_MAP
- Module boundaries and ownership map exists and is maintained.

### M2_CONTRACT_REGISTRY
- Versioned registry of system contracts (StrategyInput, StockSelectionSpec, RiskVerdict, ExecutionProvider, RegimeSnapshot, DecisionArtifacts).

### M3_MODE_SEMANTICS_CERT
- Truth table for modes exists and is proven by tests/smoke logs.

### M4_TRACEABILITY_SEMANTICS
- Trace schema, stages, required fields, and examples exist.

### M5_VERIFICATION_AUTHORITY
- Defines mandatory verification commands and evidence artifacts per epoch.

### M6_DATA_LIFECYCLE_GOV
- Retention policy, safe-to-delete list, and data lifecycle rules exist.

### M7_EPOCH_AUDIT_CERTIFICATION
- Standard audit template exists; each epoch produces certification evidence.

### M8_CHANGE_CONTROL
- Formal change control and breaking-change policy exists.

### M9_SIGNAL_SEMANTICS_REGISTRY
- Registry of signal meanings exists; prevents duplicate/ambiguous semantics.

### M10_DATA_PROVENANCE_LEDGER
- Data lineage ledger exists (origin, transformations, timestamps).

