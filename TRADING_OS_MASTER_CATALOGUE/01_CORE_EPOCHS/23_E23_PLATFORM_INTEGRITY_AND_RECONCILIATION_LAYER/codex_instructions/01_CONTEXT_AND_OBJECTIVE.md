# 01_CONTEXT_AND_OBJECTIVE.md
# Context & Objective — E23 Platform Integrity and Reconciliation
Last updated: 2026-02-13

## Context
The IBKR Trading OS has implemented all core epochs (E0..E22) and metadata epochs (M0..M10).
However, the global system truth artifact (e.g., SYSTEM_STATE_CERTIFIED.md) has drifted/staled and does not
reflect the platform reality, and the platform may contain cross-layer drift that harms strategy readiness.

## Objective
Implement E23 as an automated platform self-sanitiser that:
1) Discovers E*/M*/P* inventory from the catalogue and repo reality
2) Runs (or reuses) verification authority to prove what is working
3) Detects cross-layer drift
4) Automatically applies minimal safe fixes to resolve drift (where permitted)
5) Regenerates global truth artifacts from evidence
6) Produces a single machine-readable platform integrity verdict

E23 must be runnable with one command and must be reproducible.
E23 must prefer automation: it should run tests, compileall, boot cycles, etc. as needed.

END
