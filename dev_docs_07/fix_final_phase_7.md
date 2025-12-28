You are working on repo: https://github.com/NelzonMamani/ibkr-trading-system

Goal: Fix Phase 7 config authority + structural inconsistencies so the system boots reliably in SIM/PAPER/LIVE, and does NOT break Phase 7. Then ensure Phase 8 readiness (no import errors; deterministic boot).

Constraints:
- Keep Phase 7 behaviour and teaching-first approach intact.
- Do NOT introduce trading logic. Only config + orchestration wiring fixes.
- Make configuration authority unambiguous and eliminate fragmentation.
- Ensure LIVE mode forbids event replay (forces OFF) without runtime crashes.

Tasks:

1) Inspect src/config:
   - runtime_config.py
   - system_config.py
   - trading_config.py
   - any other config modules
   Identify duplicated or conflicting config values (RUN_MODE, EVENT_REPLAY_MODE / REPLAY_MODE, defaults).
   Create a single authoritative entry for each:
   - runtime mode authority belongs in runtime_config.py
   - replay mode authority belongs in system_config.py (but must accept run_mode and apply safety rules)

2) Implement/verify these public functions exist and are imported correctly:
   - config.runtime_config.get_run_mode() -> RunMode
   - config.system_config.get_event_replay_mode(run_mode: RunMode) -> EventReplayMode
   If any code imports missing names, fix imports and/or add compatibility wrapper functions.

3) Standardise naming:
   - Use EVENT_REPLAY_MODE everywhere (not REPLAY_MODE).
   - Use EventReplayMode Enum with OFF/CYCLE/RUN.
   - If there is legacy usage, add a small backward-compatible alias but prefer EVENT_REPLAY_MODE going forward.

4) Fix the boot flow so logs show the true authoritative configuration:
   - In main.py, print both:
       - baseline teaching config (e.g., from trading_config or system_config defaults) clearly labelled as "baseline"
       - authoritative resolved config (run mode + event replay mode) clearly labelled as "resolved"
   Ensure there is no confusing situation where baseline says LIVE but resolved says SIM unless explicitly explained.

5) Fix orchestrator replay resolution:
   - Orchestrator must call get_run_mode() first, then pass run_mode into get_event_replay_mode(run_mode).
   - If run_mode == LIVE and replay requested, force OFF and log a safety message (do not crash).
   - Only crash if there is a truly invalid configuration that cannot be made safe (but prefer safe fallback).

6) Ensure Phase 7 safety invariant:
   - LIVE must never allow replay.
   - SIM/PAPER can use replay (default CYCLE).
   - Execution engine must still not hit real broker calls unless explicitly implemented and gated (keep existing safety).

7) Add a tiny internal “config sanity check” unit or smoke check:
   - e.g. a function or minimal test file (or just a __main__ check) that imports:
       main.py, runtime_config, system_config, orchestrator
     and confirms no ImportError and that LIVE->replay resolves to OFF.

8) Run through codebase and fix any broken imports caused by previous merges:
   - Search for get_event_replay_mode imports, REPLAY_MODE usage, EVENT_REPLAY_MODE env var reads.
   - Ensure consistent across all files.

Deliverables:
- Commit with message: "Phase 7: config authority cleanup (run mode + replay mode)"
- Provide a short summary of what changed and which files were touched.
- Confirm boot output in SIM and LIVE does not crash.

Start by listing every place in codebase where RUN_MODE and replay mode are referenced, then implement the authority cleanup and update imports accordingly.
