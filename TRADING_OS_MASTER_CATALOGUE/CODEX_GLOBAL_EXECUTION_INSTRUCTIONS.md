# CODEX_GLOBAL_EXECUTION_INSTRUCTIONS.md
# Global Instructions for Codex — Trading OS Catalogue Certification Pipeline

**Status:** FROZEN (authoritative)
**Last updated:** 2026-02-08
**Scope:** These rules govern how Codex must read TRADING_OS_MASTER_CATALOGUE and perform epoch-by-epoch verification, gap-implementation, optimisation, and certification.

## 0. Absolute Authority & Read Path

- Codex must treat `TRADING_OS_MASTER_CATALOGUE/` as the **only authoritative instruction source**.
- Codex must read, in this order:
  1) `TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST/`
  2) `TRADING_OS_MASTER_CATALOGUE/SYSTEM_CONSTITUTION.md`
  3) `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE.md`
  4) Epoch folders in strict order:
     - `01_CORE_EPOCHS/00_E0_SYSTEM_LAW_AND_PURPOSE` → … → `01_CORE_EPOCHS/21_E21_TRADING_READY_VERIFICATION_AND_END_TO_END_SIMULATION`
     - then `02_METADATA_EPOCHS/`
     - then foundation inventories and strategy folders **only when explicitly allowed**

## 1. File Edit Permissions (Non-Negotiable)

### Codex MUST NEVER modify:
- `SYSTEM_CONSTITUTION.md`
- `SYSTEM_STATE.md`
- Any frozen files under `00_READ_FIRST/`

### Codex MAY create/update:
- `SYSTEM_CONSTITUTION_CERTIFIED.md` (append-only; never edit past entries)
- `SYSTEM_STATE_CERTIFIED.md` (overwrite allowed; must reflect observed reality)
- Epoch-level certification artifacts inside the active epoch folder

## 2. Epoch Processing Contract (Mandatory, One Epoch at a Time)

For each epoch in strict numerical order:

1) **Audit**
- Inspect the current codebase and runtime behavior against epoch guarantees.
- Identify authoritative implementations, duplication, gaps, and risks.

2) **Gap Analysis**
- Produce an epoch-local audit report containing:
  - Intended Capability
  - Observed Implementation
  - Gaps / Risks
  - Duplication Detected

3) **Amend**
- Apply amendments **only if** they improve current live behaviour.
- Eliminate duplication.
- Tighten invariants.
- Preserve or improve tradeability.
- No clean-slate rewrites.

4) **Re-verify**
- Mandatory commands:
  - `python -m compileall src`
  - `pytest`
  - Relevant smoke runs (READ_ONLY / PAPER / SIM as applicable)
- Collect evidence under the epoch folder.

5) **Certify**
- Append certification entry to `SYSTEM_CONSTITUTION_CERTIFIED.md`.
- Update `SYSTEM_STATE_CERTIFIED.md` to reflect certified reality.

An epoch is complete **only** when certification is appended.

## 3. Strategy Implementation Hard Gate (Non-Negotiable)

Codex MUST NOT treat any strategy as complete, executable, or certifiable until:

- **ALL Core Epochs (E0–E21) are CERTIFIED**, and
- **ALL Metadata Epochs (M0–M10) are CERTIFIED**.

Before this condition is met:
- Strategy code may exist only as legacy or design artifacts.
- Strategy behaviour must not be relied upon for trading readiness.
- No strategy may be certified.

Strategy certification is a **post-system activity**.

## 4. Strategy Foundation Layer (E18–E20)

When Strategy Foundation epochs are reached and unlocked:

Codex must build and/or certify:
- Setup Family primitives
- Execution Trigger primitives
- Conditions and Confirmations
- Single- and Multi-candlestick pattern primitives

Rules:
- Pure logic only (no broker, no DB writes)
- Fully unit-tested
- Single authoritative implementation per primitive
- Strategies may only *compose*, never reimplement

## 5. Optimisation Authority

Codex is explicitly authorised to:
- Optimise runtime paths
- Simplify orchestration where safe
- Remove dead or unused code under housekeeping governance
- Fix long-standing issues (e.g. PAPER execution path)
- Improve determinism, traceability, and robustness

Provided:
- No certified capability is removed
- Tradeability is never reduced
- All changes are audited and certified

## 6. Stop Conditions

Codex must stop and request human confirmation if:
- A change would materially alter system architecture
- A deletion affects core runtime paths
- Verification repeatedly fails without a safe resolution

Otherwise, Codex proceeds automatically.

## 7. Completion Criteria

The certification programme is complete only when:
- All Core Epochs (E0–E21) are CERTIFIED
- All Metadata Epochs (M0–M10) are CERTIFIED
- All strategies are fully implemented, tested, verified, and certified
- End-to-end SIM, PAPER, and READ_ONLY runs pass deterministically

END
