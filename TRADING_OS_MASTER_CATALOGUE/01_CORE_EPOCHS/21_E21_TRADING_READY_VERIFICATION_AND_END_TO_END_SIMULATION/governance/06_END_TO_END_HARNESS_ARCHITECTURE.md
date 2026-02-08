# 06_END_TO_END_HARNESS_ARCHITECTURE

## The Harness is a Product, not a Script
E21 requires a first-class harness that is:
- runnable from CLI
- repeatable
- self-reporting
- produces artifacts in a stable location
- can run on CI (SIM suite) and locally (SIM+PAPER)

## Harness components (conceptual)
1. Scenario loader
   - Synthetic generator OR recorded inputs
2. Market data provider adapter
   - Mock provider for synthetic bars/ticks
   - Replay provider for recorded data
   - Real provider for PAPER/LIVE
3. Scanner runner
   - Contract: Top N → gates → Watchlist K → Focus M
4. Strategy interface translator
   - Draft policy → certified policy (E19)
5. Strategy runner
   - Setup family composition
   - Conditions + confirmations + triggers
   - Intent production
6. Risk engine
   - permission checks
   - caps & kill state
7. Execution engine provider
   - mock execution (SIM)
   - paper broker (PAPER)
8. Storage & audit writer
   - event spine
   - decision artifacts
   - provenance ledger
9. Report generator
   - PASS/FAIL + evidence links

## Required CLI contract (minimum)
- `python -m src.verify.e2e --mode SIM --scenario <name> --cycles <n>`
- `python -m src.verify.e2e --mode PAPER --scenario smoke --duration <seconds>`
- `python -m src.verify.e2e --mode READ_ONLY --scenario smoke --duration <seconds>`

Exact module names are implementation details for CODEX instructions, but governance requires a stable entrypoint and stable artifacts.
