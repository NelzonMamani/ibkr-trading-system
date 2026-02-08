# 01_EPOCH_OVERVIEW — E21 Trading Ready Verification & End-to-End Simulation

## Mission
E21 is the **single authoritative gate** that answers one binary question:

> **Is the Trading OS safe and correct to run in LIVE mode with execution enabled under a controlled risk configuration?**

E21 exists because "we wrote the code" is not evidence. The only acceptable evidence is **repeatable, end-to-end verification** across run modes and failure conditions.

## What E21 produces
- A **repeatable verification harness** that exercises the full lifecycle:
  **Discovery → Qualification → Watchlist → Focus → Intent → Order → Fill → Position lifecycle → Exit → Audit**
- A **mode parity matrix** proving SIM/PAPER/READ_ONLY/LIVE semantics are coherent.
- A **scenario library** (synthetic + recorded) that deterministically reproduces edge cases.
- A **certification report** with PASS/FAIL plus a signed evidence set.

## What E21 does NOT do
- It does not tune strategy edge parameters.
- It does not invent strategy logic.
- It does not bypass strategy policy primacy.
- It does not loosen safety gates.

## Relationship to strategies
- E21 certifies the **Trading OS foundation** and the **strategy execution pathway**.
- A strategy becomes “tradable” only after it passes **strategy-level certification** using the E21 harness (performed in the strategy epoch).
- E21 must provide the harness and contracts so each strategy can be validated end-to-end without bespoke ad-hoc scripts.

## Completion gate
E21 is complete only when:
1) the harness runs successfully in CI/local, and
2) a PASS report exists for foundation + at least one reference strategy in SIM and PAPER, and
3) the system can be put into LIVE safely with execution enabled (micro-cap configuration), with proof of non-interference and kill-switch behavior.
