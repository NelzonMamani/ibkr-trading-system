# SYSTEM_STATE — Authoritative Project Status

Last updated: 2026-01-15

## Purpose of this File
`SYSTEM_STATE.md` is the single source of truth for:
- where the project is right now
- what is *frozen* vs *plastic*
- what the next execution objectives are
- what must not be changed without explicit intent

This file is expected to evolve. The README is the public charter; this is the operational truth.

---

## Current Epoch Status
### Epoch 4 — COMPLETE (Closed)
Epoch 4 is closed and must not be reopened except for genuine defects that violate the frozen contract.

**Frozen scanner contract:**
Top N gainers → hard gates → Watchlist K → Focus M  
- Watchlist K default 15 (configurable up to 30)  
- Focus M default 3–5 (configurable up to 10)  
- Empty watchlist is valid output (must include clear drop reasons)

### Epoch 5 — COMPLETE (Closed)
Epoch 5 is complete and frozen. It was delivered as a gated, Codex-safe “one-go” PR approach:
- Part A: Stabilisation & Contracts
- Part B: End-to-End Trading OS Completion
- Part C: Hardening, UX, Tests, Cleanup

**Epoch 5 scope is intraday momentum only.** No Buffett/long-horizon strategy work belongs here.

### Epoch 6 — FUTURE (Isolated)
Epoch 6 implements Long-Horizon / Buffett-Style strategy class.
It is isolated by design (different cadence and data), but shares the same OS governance.

---

## What Is Frozen (Non-Negotiable)
### Module Boundary Rules
- Scanner selects and explains candidates; it does not trade.
- Patterns/Strategy produce TradeIntents; they do not place orders.
- Risk is the final gate; it may block anything and must explain why.
- Execution sends broker orders; it does not invent signals.
- Storage is mandatory; every attempt is persisted (including blocked/failed).

### Operational Truths
- The system must run **standalone** (module-by-module) and **integrated** (under orchestrator).
- Determinism and explainability are first-class: logs + stored rationale are required.
- Safety first: live testing is bounded (1-share mode) and circuit breakers can safe-stop.

---

## Epoch 5 Roadmap Summary (Implementation Order)
### Part A — Stabilisation & Contracts (3 phases)
**A1** Governance anchor updates  
- Update `README.md`, `SYSTEM_STATE.md`, and create/confirm `RUNBOOK.md`

**A2** Packaging/import stability  
- Single canonical “run from repo root” method (`python -m ...`)
- Eliminate import ambiguity (`ModuleNotFoundError` class)
- Minimal, necessary package init files

**A3** Run modes + Doctor bootstrap  
- Explicit banners for SIM / READONLY / LIVE_1SHARE
- A “doctor” entrypoint to validate imports/config and run a scanner smoke cycle

### Part B — End-to-End Trading OS Completion (6 phases)
**B1** Orchestrator deterministic cycle (no overlaps)  
**B2** Scanner maturity: TopN→Gates→K→M, drop reasons, state across cycles  
**B3** Patterns engine: Ross core Phase-1 set with standardized PatternResult  
**B4** Strategy policy: Ross confirmation “gold standard” outputs TradeIntent only  
**B5** Risk engine: ALLOW/BLOCK/ALLOW_WITH_CONSTRAINTS with rationale + sizing + circuit breakers  
**B6** Execution + Storage: mode-respecting broker actions + full-context persistence

### Part C — Hardening + UX + Tests + Cleanup (5 phases)
**C1** Health states & data quality flags, safe-stop on CRITICAL  
**C2** Scanner NEW/CONTINUING/DROPPED tracking + drop reason histogram  
**C3** Console UX standard: clear Watchlist K and Focus M lists each cycle  
**C4** Smoke + contract tests (imports, scanner contract, orchestrator readonly cycle)  
**C5** Freeze Epoch 5 completion state and update RUNBOOK/SYSTEM_STATE

---

## Console Output Expectations (Operator Clarity)
At minimum, each orchestrator cycle must print:
- Mode (SIM/READONLY/LIVE_1SHARE) and Session (PRE/REG/AFTER)
- Scanner summary:
  - TopN count
  - Survivors after gates (count + drop reason summary)
  - Watchlist K symbols (explicit list)
  - Focus M symbols (explicit list; default 3–5)
  - If empty: `EMPTY WATCHLIST (valid)` + summarized reasons
- Patterns summary for Focus symbols (best setup + confidence + rationale summary)
- Risk decisions per TradeIntent (ALLOW/BLOCK/constraints + rationale)
- Execution summary (READONLY logs “would place”; LIVE_1SHARE logs submitted/fill statuses)
- Storage confirmation
- Health status line (OK/DEGRADED/CRITICAL) and any trigger reasons

---

## “Codex-Safe” Delivery Rules (Learned From Prior Failures)
These are frozen for Epoch 5 implementation execution:
1. One PR for Epoch 5, but internally gated by Part A → Part B → Part C.
2. Each part has an explicit allowed-file scope; if scope is exceeded, stop and justify.
3. After each part, run the specified commands and paste outputs.
4. If acceptance fails, fix before proceeding; do not “push through” to later parts.
5. Avoid broad refactors; implement the minimum change that satisfies acceptance.
6. Prefer deterministic entrypoints (`python -m ...`) and stable package roots.
7. Add smoke/contract tests so regressions are caught immediately.

---

## Post-Epoch 5 Freeze
- Scanner contract, patterns, strategy intents, risk gating, execution mode law, and storage persistence are frozen.
- Orchestrator and console UX outputs are frozen to the current operator-grade format.
- Any future changes require explicit governance updates and tests.

## Next Action (Operational)
1. Maintain Epoch 5 freeze; only defect fixes allowed with explicit governance justification.
2. Begin planning for Epoch 6 (isolated long-horizon strategy work) without touching intraday momentum paths.
