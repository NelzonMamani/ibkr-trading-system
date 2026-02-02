# Context & Scope

## What Codex is implementing
Codex is tasked with implementing the **Mean Reversion strategy**
defined by the governance artifacts already present in the repository.

Codex must treat all governance documents as **immutable law**.

## What Codex is NOT allowed to do
- Invent new strategy rules
- Modify the 8-clause contract
- Move decision logic into scanner or execution
- Bypass regime, R:R, or stop constraints
- Implement partial logic and stop early

## Definition of DONE
The strategy must:
- Run end-to-end in all supported modes
- Produce trades only when all 8 clauses pass
- Be verifiable via deterministic commands
