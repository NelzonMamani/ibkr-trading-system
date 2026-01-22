# Step 3 — Rewire Ross via Interface Adapter (Adapter Only, No Behaviour Change)
Date: 2026-01-22

## Objective (Authoritative)
Implement a **pure mapping layer** that translates the existing Ross Momentum policy/outputs into the
Epoch 9 Strategy Portfolio Interface types **without changing Ross logic or trading behaviour**.

This step must leave Ross live-ready exactly as before.

## Hard Constraints (Non‑Negotiable)
1. **No Ross logic changes**
   - Do not change thresholds, rules, or decision logic.
   - Treat Ross policy and Ross runner outputs as the source of truth.
2. **Adapter only**
   - The adapter performs *translation/normalisation* only.
   - No additional gating, filtering, or “improvements” are allowed in the adapter.
3. **Prefer zero-touch to Ross module**
   - Do not edit files under `src/strategies/ross_momentum/**` unless absolutely required.
   - Implement the adapter in `src/strategy_portfolio/adapters/` (new) whenever possible.
4. **No scanner changes**
5. **No execution changes**
6. **No risk engine changes**
7. Any change to orchestrator/runner is permitted **only** to route Ross through the adapter,
   and must be behaviour-preserving with evidence.

## Mandatory Verification Commands (Must Run & Pass; Capture Output)
You must run and capture outputs for all:
1) `python -m compileall -q src`
2) `pytest -q`
3) `python -m src.main --mode SIM --cycles 1`
4) `python -m src.main --mode READONLY --cycles 1`
5) `python -m src.main --mode PAPER --cycles 1`
6) `python -m src.main --mode LIVE_MICRO --cycles 1`
7) `LIVE_MICRO` with explicit **ack env vars** for **1 share**, cycles 2–3

If any command fails or behaviour differs from pre-change Ross:
- fix it immediately
- re-run the full verification set until all pass

## Documentation Outputs (Mandatory)
Update/create BOTH:
- `PR_VERIFICATION_REPORT.md`
- `docs/PR_VERIFICATION_REPORT.md`

Each report must include:
- Summary of what changed (file paths)
- Why it is safe (behaviour-preserving argument)
- The full command list and captured outputs (or key excerpts + references to log files)
- Any environment variables required (ACK vars, IBKR port/clientId, etc.)

---

# Phase Plan (Execute in Order)

## Phase 3.1 — Repository Recon & Baseline Capture
### Goal
Identify where Ross policy is currently consumed and where trade intents/actions are produced today.

### Required Actions
1. Locate the Ross policy file (do not edit):
   - `src/strategies/ross_momentum/strategy_policy.py`
2. Locate Ross strategy runner / evaluator (likely under `src/strategies/ross_momentum/` or strategy runner layer).
3. Locate orchestrator entrypoint used by `python -m src.main` and how it selects strategies/policies.
4. Identify the **existing Ross decision output type**:
   - Is it an internal “intent” object?
   - Is it a list of orders?
   - Is it a set of actions (enter/exit/size)?
5. Capture a **baseline** (before any code changes):
   - Run (3) and (4) at minimum to confirm the system runs.
   - Note key log lines indicating the strategy used and any decisions made.

### Deliverable
- A short baseline note in `PR_VERIFICATION_REPORT.md` under “Pre-change baseline”.

---

## Phase 3.2 — Define the Adapter Contract (Mapping Specification)
### Goal
Define precisely how Ross maps into the Epoch 9 interface types, without adding behaviour.

### Required Mapping (Minimum)
Map to Epoch 9 contract types (expected under `src/strategy_portfolio/`):
- `StrategyIdentity`:
  - `strategy_id` = `"ROSS_MOMENTUM"` (or existing canonical id)
  - `strategy_version` = Ross policy version (e.g., `"v1"`)
- `AllowState`:
  - Derived from existing Ross activation / session mode gating **as already implemented**
- `SignalIntent`:
  - Map Ross existing outputs:
    - Enter Long → `ENTER_LONG`
    - Exit → `EXIT_ONLY` or `EXIT`
    - No trade → `NO_TRADE`
  - If the Epoch 9 enum differs, use the closest canonical value.
- Reasons:
  - Use Epoch 9 reason codes; **do not invent new logic**.
  - Reasons should explain translation defaults or existing Ross decision justifications.

### Fail-Safe Rule
If the adapter cannot interpret an output, it must default to:
- `DISALLOW` + `NO_TRADE`
…and include reason code `MAPPING_UNSUPPORTED_OUTPUT` (add this reason code if not present).

---

## Phase 3.3 — Implement Adapter Module (Additive)
### Goal
Add a new adapter module under `src/strategy_portfolio/adapters/`.

### Files to Create (Preferred)
- `src/strategy_portfolio/adapters/__init__.py`
- `src/strategy_portfolio/adapters/ross_momentum_adapter.py`

### Implementation Requirements
1. The adapter must **import**:
   - Epoch 9 contract types (`contracts.py`, `reason_codes.py`)
   - Ross policy (read-only import) if needed for identity/version/timeframes
2. The adapter must not import broker/execution modules.
3. Provide functions (names may vary, but keep them explicit):
   - `ross_identity(policy) -> StrategyIdentity`
   - `ross_policy_to_interface(policy) -> dict | dataclass` (policy mapping)
   - `ross_output_to_decision_intent(ross_output, context) -> DecisionIntent`
4. Keep translation logic strictly mechanical:
   - map fields, map enums, pass through existing values
   - do not change thresholds or behaviour

### Unit Tests (Mandatory)
Create `tests/strategy_portfolio/test_ross_adapter.py` with:
- Import test (adapter imports without side effects)
- Identity mapping test
- Output mapping test (use small mocked Ross output objects)
- Fail-safe test (unknown output → DISALLOW/NO_TRADE + reason)

---

## Phase 3.4 — Minimal Rewire (Routing Ross Through Adapter)
### Goal
Route the existing Ross strategy decision outputs through the adapter so the orchestrator now consumes
canonical interface intents (or a canonical decision object), while preserving behaviour.

### Requirements
1. Make the smallest possible change in the wiring code path.
2. Do not change scanner, risk engine, execution logic.
3. Ensure “strategy selection” remains Ross by default (if that is current behaviour).
4. Ensure logs still identify Ross and produce the same actions.

### Recommended Approach (Behaviour-Preserving)
- Keep Ross runner logic intact.
- After Ross runner computes decisions, call the adapter to translate those decisions into interface intents.
- Feed the translated intent into the same downstream actions that were already taken (or store it for future use).
  - If downstream expects the old decision type, keep old type as well and add the interface intent alongside it.
  - Do not break existing downstream functions.

### Acceptance Check
- Re-run SIM and READONLY cycles and confirm no behaviour changes in log lines and decisions.

---

## Phase 3.5 — Update Strategy Registry (If Present)
If Epoch 9 registry exists and is used at runtime:
- Register Ross strategy identity and mark it enabled (if that was default behaviour).
If registry is not yet wired at runtime, do not force it. Keep this step additive.

---

## Phase 3.6 — Documentation: PR_VERIFICATION_REPORT
Update/create:
- `PR_VERIFICATION_REPORT.md`
- `docs/PR_VERIFICATION_REPORT.md`

Include:
- Summary: adapter added, wiring minimal
- Files changed (paths)
- Why safe: adapter is pure mapping + fail-safe defaults
- Baseline vs post-change confirmation notes
- Mandatory Verification commands with captured outputs

---

## Phase 3.7 — Mandatory Verification Commands (Run All, Capture Output)
Run and capture outputs for:

1) `python -m compileall -q src`
2) `pytest -q`
3) `python -m src.main --mode SIM --cycles 1`
4) `python -m src.main --mode READONLY --cycles 1`
5) `python -m src.main --mode PAPER --cycles 1`
6) `python -m src.main --mode LIVE_MICRO --cycles 1`

### LIVE_MICRO with Explicit ACK Env Vars (1 share), cycles 2–3
You must locate the exact ACK env var names used by this repo.
Do NOT guess. Search the code for `ACK`, `LIVE_MICRO`, `ONE_SHARE`, `CONFIRM`, and `DANGER`.

Then run something like (example — replace with real var names):
- Bash:
  - `ACK_LIVE_MICRO=1 ACK_1_SHARE=1 python -m src.main --mode LIVE_MICRO --cycles 3`
- PowerShell:
  - `$env:ACK_LIVE_MICRO="1"; $env:ACK_1_SHARE="1"; python -m src.main --mode LIVE_MICRO --cycles 3`

Document the exact env vars and values used in the verification report.

---

# Completion Criteria (Step 3)
Step 3 is complete only if:
- Ross behaviour is unchanged and still live-ready
- Adapter exists and is used for Ross → interface translation
- All Mandatory Verification Commands pass
- Both verification reports are updated with outputs and rationale
