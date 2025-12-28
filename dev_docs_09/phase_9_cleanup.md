phase_9_cleanup.md

GOAL
-----
Permanently close all remaining A / B / C (teaching-choice) branches and
converge the system onto a single authoritative execution model.

This is NOT a functional expansion.
This is a structural cleanup and authority finalisation step.

CONTEXT
-------
The system has successfully completed Phase 9:
- Runtime safety gates are enforced
- Event replay rules are enforced
- Invariants pass
- Trade lifecycle is coherent in SIM
- No unresolved ambiguity remains

A / B / C paths were teaching scaffolding only and must now be removed.

SCOPE
-----
This change MUST NOT:
- Alter runtime behaviour
- Alter event order
- Alter safety checks
- Alter public interfaces
- Break Phase 9 invariants

This change MUST:
- Remove all "Option A / Option B / Option C" comments
- Remove conditional teaching forks that no longer apply
- Leave exactly ONE valid execution path

TASKS
-----

1) CONFIG AUTHORITY CLEANUP
---------------------------
- Ensure runtime_config.py is the single authority for:
  - RUN_MODE
  - EVENT_REPLAY_MODE

- system_config.py and trading_config.py may define defaults
  but MUST NOT override runtime_config.

- Remove any remaining comments or logic suggesting multiple
  valid runtime authorities.

2) EXECUTION / EXIT AUTHORITY FINALISATION
------------------------------------------
- Confirm:
  - ExecutionEngine ONLY opens trades
  - TradeExitEngine is the ONLY component allowed to close trades

- If ExecutionEngine still contains any conditional logic like:
  - "Option A: close immediately"
  - "Option B: defer close"
  - "Option C: teaching shortcut"

  → REMOVE IT.

There must be ONE rule:
- Execution opens
- Exit engine closes

3) EVENT FLOW CONSOLIDATION
---------------------------
- Ensure there is exactly ONE event flow:
  CYCLE_START
  SCAN_COMPLETE
  STRATEGY_COMPLETE
  TRADE_OPENED
  TRADE_CLOSED
  EXECUTION_COMPLETE
  TRADE_EXIT_COMPLETE
  PERF_SNAPSHOT
  STRATEGY_PERF_SNAPSHOT

- Remove any conditional emission paths tied to teaching modes.

4) COMMENT & DOCUMENTATION CLEANUP
----------------------------------
- Delete comments referring to:
  - "Option A / B / C"
  - "Teaching choice"
  - "Alternate teaching paths"

- Replace with declarative statements:
  - "Authoritative behaviour"
  - "Single execution path"
  - "Runtime invariant"

5) INVARIANT VERIFICATION
-------------------------
- Run the system in SIM mode
- Confirm:
  - No runtime warnings
  - No missing imports
  - No unreachable branches
  - Event replay passes
  - Registry invariants pass

OUTPUT REQUIREMENTS
-------------------
- The system must run exactly as before
- Logs may be cleaner but behaviour identical
- No new features added
- No TODOs left behind

FINAL STATE
-----------
After this step:
- There are NO A / B / C decisions left in the codebase
- The system has ONE authoritative execution model
- Phase 10 can begin cleanly

DO NOT PROCEED TO PHASE 10 IN THIS CHANGE.
THIS STEP IS PURELY A CLOSURE AND CLEANUP STEP.