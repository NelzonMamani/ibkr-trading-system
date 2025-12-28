FIX_PHASE_7_STEP_7_5_EVENT_COLLECTOR_SNAPSHOT_POLICY.md

# PHASE 7 — STEP 7.5: EventCollector Snapshot Policy (Cycle vs Global) + Replay Source-of-Truth

## Goal
Make EventCollector behaviour explicit, correct, and testable:

- Maintain TWO distinct stores:
  1) `cycle_events` (cleared at the start of every orchestrator cycle)
  2) `all_events` (append-only, for full-run history across cycles)

- Provide two snapshot APIs:
  - `snapshot_cycle()` → returns `cycle_events`
  - `snapshot_all()` → returns `all_events`

- Ensure replay is deterministic and explicit:
  - `replay_cycle()` replays ONLY the last cycle snapshot (cycle store)
  - `replay_all()` replays the full history (global store)

- Ensure “event counts” printed at end of cycle are NOT misleading:
  - Print both counts (cycle vs all) or clearly label which store is referenced.

- Ensure no accidental duplication:
  - Each cycle should CLEAR `cycle_events` at cycle start.
  - Recording an event should ALWAYS append to `all_events` AND `cycle_events`.

## Implementation Instructions (Codex)

### 1) Update EventCollector class
Locate `src/core/event_collector.py` (or the file where EventCollector currently lives).

Implement the following structure and semantics:

- Add two internal lists:
  - `self._cycle_events: list[SystemEvent]`
  - `self._all_events: list[SystemEvent]`

- On init:
  - initialise both to empty lists

- Replace/standardise the cycle clearing method:
  - method name: `clear_cycle()`
  - behaviour: clears ONLY `_cycle_events`
  - it should print: `[EVENT_COLLECTOR] Clearing cycle-scoped events`
  - it MUST NOT clear `_all_events`

- Recording:
  - method name remains `record(event: SystemEvent) -> None` (or adapt to existing signature)
  - append to BOTH `_cycle_events` and `_all_events`
  - Do NOT print noisy per-event lines (7.4 already removed that); keep it silent or minimal.
  - If you keep a print, it must be behind a config flag like `DEBUG_EVENTS`.

- Snapshot APIs:
  - `snapshot_cycle(self) -> list[SystemEvent]`: return a shallow copy of `_cycle_events`
  - `snapshot_all(self) -> list[SystemEvent]`: return a shallow copy of `_all_events`

- Optional but recommended for safety:
  - return `list(self._cycle_events)` and `list(self._all_events)` to prevent external mutation.

### 2) Update Orchestrator cycle start to clear ONLY cycle events
Locate orchestrator cycle entry (likely `src/core/orchestrator.py` or similar).

At the START of each `run_once()` (or the cycle boundary):
- call `event_collector.clear_cycle()`

Do NOT call `clear_all()` or anything that wipes global history.

### 3) Update end-of-cycle summary to display correct counts
Wherever you currently print:
- `Cycle produced X total events`

Replace that output with explicit, non-confusing labels:

- `cycle_event_count = len(event_collector.snapshot_cycle())`
- `all_event_count = len(event_collector.snapshot_all())`

Print exactly:
- `[EVENT_SUMMARY] Cycle produced {cycle_event_count} event(s) (cycle scope)`
- `[EVENT_SUMMARY] Run has {all_event_count} total event(s) (all cycles)`

This will prevent confusion where multiple cycles show “8 total events” when the number is actually global.

### 4) Update replay to support both cycle and all-history replay
Locate replay logic (likely in Orchestrator or EventCollector).

Implement two functions (names can vary but must exist and be used clearly):

- `replay_cycle_events()`:
  - uses `snapshot_cycle()` only

- `replay_all_events()`:
  - uses `snapshot_all()` only

If you currently have a single replay method, keep it but make it explicit:
- default replay should be cycle-scoped replay (teaching expectation)
- optionally provide a CLI/config switch for full replay.

### 5) Ensure timestamps remain correct and non-duplicated across cycles
In your logs you sometimes see identical timestamps reused for multiple cycles.
This is likely because a static timestamp is being reused across event creation.

Fix requirement:
- Each new SystemEvent created MUST use a fresh `datetime.now()` (or equivalent) at creation time.
- Ensure event timestamp is assigned at event construction, not inherited from a shared object.
- Ensure orchestrator uses a fresh timestamp per cycle start event.

### 6) Add a minimal deterministic test (must pass)
Create a test file:
- `tests/test_event_collector_snapshot_policy.py`

Test cases:

1) `test_cycle_clear_does_not_clear_all()`
- Create collector
- record 2 events
- assert cycle=2, all=2
- call clear_cycle()
- assert cycle=0, all=2

2) `test_record_appends_to_both_stores()`
- Create collector
- record 1 event
- assert cycle=1 and all=1

3) `test_multiple_cycles_accumulate_all_but_not_cycle()`
- Create collector
- Cycle A: clear_cycle(), record 2 events → cycle=2, all=2
- Cycle B: clear_cycle(), record 3 events → cycle=3, all=5

If tests framework isn’t set up yet:
- add a simple runnable script under `src/devtools/verify_event_collector_policy.py`
that prints PASS/FAIL and exits non-zero on failure.

### 7) Acceptance Criteria (must match runtime output)
After implementation, when running `src/main.py` for two cycles:

- Each cycle should print cycle event count as 4 (CYCLE_START, SCAN_COMPLETE, STRATEGY_COMPLETE, EXECUTION_COMPLETE)
- Global all-events should increase:
  - after cycle 1: 4
  - after cycle 2: 8

Replay:
- cycle replay should replay ONLY the 4 events from last cycle
- all replay should replay 8 events across both cycles (if enabled)

## Notes
- This step formalises behaviour rather than “reducing event totals”.
- The system is allowed to keep growing `all_events` across cycles — that is the point.
- Cycle summaries must be cycle-scoped to avoid misleading the operator.

## Deliverable
- Updated EventCollector with cycle/all stores and snapshot APIs
- Updated Orchestrator to clear only cycle events at cycle start
- Updated summary printing to show BOTH counts
- Updated replay to support cycle vs all replays
- Tests or verification script proving the policy
