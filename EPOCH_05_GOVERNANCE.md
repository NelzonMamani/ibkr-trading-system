# EPOCH_05_GOVERNANCE — System Completion & Hardening (Intraday Momentum Class Only)

Last updated: 2026-01-15

## 0. Purpose
This document is the **scope and rules** for **Epoch 5**. It binds all Phase 05A/05B/05C execution files.

Epoch 5 delivers a **robust, deterministic, live-testable Trading OS** for the **intraday momentum strategy class** (Ross Momentum first).

**Buffett / long-horizon strategy work is explicitly excluded** and belongs only to **Epoch 6**.

---

## 1. Inputs (Authoritative Governance Stack)
Epoch 5 must remain aligned to the following governing artifacts (do not contradict them):

- SYSTEM_CONSTITUTION.md (law; immutable)
- README.md (public charter; stable)
- SYSTEM_STATE.md (authoritative current status; living)
- SYSTEM_VISION_AND_GLOBAL_OBJECTIVES.md
- GLOBAL_FUNCTIONAL_REQUIREMENTS.md
- SYSTEM_TREE_AND_MODULE_MAP.md
- MODULE_REQUIREMENTS_scanner.md
- MODULE_REQUIREMENTS_patterns.md
- MODULE_REQUIREMENTS_risk.md
- MODULE_REQUIREMENTS_execution.md
- MODULE_REQUIREMENTS_storage.md

If any Phase instruction appears to conflict with these documents, **stop** and resolve the conflict before implementation.

---

## 2. Epoch 5 Scope
### 2.1 Included
1. **Repo stability and determinism**
   - consistent imports and entrypoints
   - explicit run modes (SIM / READONLY / LIVE_1SHARE)
   - minimal “doctor” diagnostics

2. **Scanner contract compliance and operator clarity**
   - Top N gainers → hard gates → Watchlist K → Focus M
   - K default 15 (configurable up to 30)
   - M default 3–5 (configurable up to 10)
   - **Empty watchlists are valid output** and must print clear reasons

3. **End-to-end orchestration**
   - Scanner → Patterns → Strategy → Risk → Execution → Storage
   - deterministic, non-overlapping cycles
   - health reporting and safe-stop

4. **Ross Momentum pattern and intent generation (Phase 1 priorities)**
   - Premarket high break / ORB
   - Micro pullback
   - Bull flag
   - Consolidation breakout
   - Failed breakout (filter/exit warning)
   - VWAP tags (context)

5. **Risk gating and circuit breakers**
   - percent-based sizing
   - 1-share live-test mode
   - daily loss / max trades / data quality / spread thresholds
   - explain every block or constraint

6. **Execution and lifecycle management (IBKR/TWS)**
   - submit orders only in LIVE_1SHARE mode and only if risk-approved
   - track order lifecycle and broker errors
   - never loosen stops autonomously

7. **Storage of all trade attempts**
   - allowed, blocked, failed execution, executed+closed
   - full context persistence for audit and learning

8. **Minimal but real tests**
   - smoke + contract tests to prevent regressions and “Codex drift”

### 2.2 Excluded (Hard Non-Goals)
- Buffett / long-horizon / fundamental strategy logic (Epoch 6 only)
- HFT/ultra-low-latency execution optimization
- options/futures/crypto
- “silent” adaptive logic that mutates rules without explicit versioning and logs

---

## 3. Safety & Authority Rules (Invariant)
1. **Module boundaries are absolute**
   - Scanner does not trade.
   - Patterns/Strategy produce TradeIntents, not orders.
   - Risk is final gate and can block anything; must explain why.
   - Execution submits orders; does not invent signals.
   - Storage persists all attempts; no silent drops.

2. **Mode law (explicit and enforceable)**
   - SIM: no broker orders
   - READONLY: no broker orders; log “would place”
   - LIVE_1SHARE: broker orders allowed only if risk-approved and constrained to 1-share mode by default

3. **Determinism**
   - identical inputs ⇒ identical outputs (as feasible with live feeds)
   - randomness is forbidden in decision logic

4. **Explainability**
   - every decision must print a short rationale and store a structured rationale
   - “blocked” is still a first-class outcome, not an error

---

## 4. Codex Execution Discipline (Learned From Prior Failures)
This epoch must be implemented in a single PR **with internal gates**:
- Part A must pass acceptance before Part B begins
- Part B must pass acceptance before Part C begins
- If a gate fails: fix until it passes; do not “push through”

### 4.1 Allowed-file Scoping
Each phase file defines an **ALLOWED FILES** set. Codex must not modify files outside that scope.
If additional files are required, Codex must:
- stop
- justify the file(s) needed
- update the phase doc (or create a small addendum) before changing them

### 4.2 Console Proof, Not “It Should Work”
For each phase, acceptance depends on:
- running the specified commands
- producing the specified console outputs
- passing the specified tests (when present)

### 4.3 No Broad Refactors
Avoid refactors that are not required for acceptance. Fix the minimum surface area to satisfy contracts and tests.

---

## 5. Epoch 5 Definition of Done (DoD)
Epoch 5 is complete only if all are true:

1. Scanner produces deterministic **Watchlist K** and **Focus M**, or prints valid empty with reasons.
2. Patterns and Strategy generate **TradeIntents** for Focus symbols, with explanations.
3. Risk gates every intent with ALLOW/BLOCK/ALLOW_WITH_CONSTRAINTS and rationale.
4. Execution respects run modes; LIVE_1SHARE can place and track orders; READONLY never places orders.
5. Storage persists every attempt with full context.
6. Orchestrator runs deterministic cycles and never overlaps cycles.
7. Console output is operator-grade (clear K and M lists, clear decisions).
8. Smoke/contract tests pass in one command.
9. SYSTEM_STATE.md is updated to reflect Epoch 5 completion status when finished.

---

## 6. Reference Command Conventions
All run commands should be executed **from repository root** using `python -m ...` entrypoints where possible.

---

END.
