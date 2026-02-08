# CODEX_GLOBAL_EXECUTION_INSTRUCTIONS

## Purpose

This document defines how Codex must execute the Trading OS Certification Programme as a single, continuous, deterministic process.

This is a programme-level instruction. It governs ordering, continuity, and stopping conditions.

## Scope Lock

- Codex must operate ONLY inside `TRADING_OS_MASTER_CATALOGUE`.
- Codex must treat the existing trading system as live-capable reality.
- Codex must not recreate history or regress behaviour.

## Execution Order (Mandatory)

1. Read and internalise all documents in:
   `TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST`

2. Process epochs in strict numerical order:
   - `01_CORE_EPOCHS/00_E0_SYSTEM_LAW_AND_PURPOSE`
   - then `01_E1_...`
   - continuing until `18_E18_STRATEGY_FOUNDATION_LAYER`
   - then metadata epochs in order

3. No epoch may be skipped.
4. No epoch may be processed out of order.

## Per-Epoch Obligations

For each epoch, Codex must:

- Audit the current system implementation
- Identify authoritative components
- Detect gaps, duplication, or ambiguity
- Apply amendments ONLY if they improve current system behaviour
- Re-run verification commands
- Produce an audit report inside the epoch folder
- Append certification entries to:
  - `SYSTEM_CONSTITUTION.md`
  - `SYSTEM_STATE.md`

An epoch is complete ONLY when certified.

## Duplication and Deletion

- Duplication is forbidden.
- When multiple implementations exist:
  - Select the runtime-authoritative one
  - Migrate usage if required
  - Delete unused or legacy files under housekeeping governance
- Deletions must be documented.

## Continuity Rule

This is a single certification programme.

- Codex must preserve context across epochs.
- Later epochs must respect decisions made earlier.
- Improvements must be monotonic.

## Stopping Conditions

Codex must stop and wait for human confirmation when:

- An epoch introduces non-trivial architectural change
- A deletion affects core runtime paths
- A conflict in intent cannot be resolved safely

Otherwise, Codex proceeds to the next epoch.

## Completion Criteria

The programme is complete only when:

- All core epochs are certified
- All metadata epochs are certified
- `SYSTEM_CONSTITUTION.md` and `SYSTEM_STATE.md` fully describe the system

END
