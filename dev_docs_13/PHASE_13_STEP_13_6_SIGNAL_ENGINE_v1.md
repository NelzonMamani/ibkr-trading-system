PHASE_13_STEP_13_6_SIGNAL_ENGINE_v1.md
PHASE 13 · STEP 13.6 — SIGNAL ENGINE v1 (DETERMINISTIC “ROSS-LIKE” SIGNALS FROM TEACHING DATA)

FILES (EXACT)
- CREATE: src/signals/signal_types.py
- CREATE: src/signals/signal_event.py
- CREATE: src/signals/signal_engine_v1.py
- CREATE: src/signals/__init__.py
- MODIFY: src/orchestrator/core_orchestrator.py
- MODIFY (ONLY IF NEEDED): src/strategies/strategy_runner.py
- MODIFY (OPTIONAL): src/events/event_types.py  (only if you keep a strict enum of event_type strings)

GOAL
Introduce a SignalEngineV1 that generates Ross-style “signal events” (e.g., MOMO_BREAKOUT, HOD_BREAK, ORB_BREAK) deterministically using the EXISTING teaching pipeline outputs (ScannerCandidate + PatternResult + tick + deterministic price feed if already available).

This is NOT candle-based, not IBKR-based, and not predictive.
It is a teaching-friendly signal layer so strategies can consume “signals” explicitly rather than overloading PatternResult.

SCOPE
- Define SignalType enum (string names).
- Define SignalEvent dataclass.
- Implement SignalEngineV1 that:
  - takes scanner candidates + pattern results + tick context
  - emits 0..N signals with rationale
  - is deterministic and replay-safe
- Wire orchestrator to run SignalEngine between PatternEngine and StrategyRunner.
- Pass signals into StrategyRunner (backward compatible) so RossMomentumStrategyV1 can use them.

NON-NEGOTIABLES
- No external calls.
- No randomness.
- No broker calls.
- Signals must be deterministic from inputs.
- Must not break current run loop, event replay, or existing strategies.

STEP A — DEFINE SIGNAL TYPES (CREATE)
Create `src/signals/signal_types.py`:

- Enum `SignalType(str, Enum)` with at least:
  - MOMO_BREAKOUT
  - HOD_BREAK
  - ORB_BREAK
  - VWAP_RECLAIM
  - FIRST_PULLBACK_LONG
  - WEAKNESS (reserved; not used yet)
Keep them as string values matching their names.

STEP B — DEFINE SIGNAL EVENT (CREATE)
Create `src/signals/signal_event.py` with dataclass:

SignalEvent:
- symbol: str
- signal_type: SignalType
- strength: float               # 0.0–1.0 deterministic
- tick: int
- source: str = "SignalEngineV1"
- rationale: str = ""

Include helper:
- `as_dict()` returning JSON-safe primitive dict (signal_type -> str)

STEP C — IMPLEMENT SIGNAL ENGINE (CREATE)
Create `src/signals/signal_engine_v1.py` containing:

- dataclass `SignalEngineConfig`:
  - enabled: bool = True
  - min_strength: float = 0.55
  - max_signals_per_symbol: int = 2
  - max_signals_per_cycle: int = 8

- class `SignalEngineV1`:
  - name: "SignalEngineV1"
  - method:
    `generate(scanner_output: list[ScannerCandidate], pattern_output: list[PatternResult], tick: int) -> list[SignalEvent]`

Deterministic rules (must implement exactly; do not invent market data):
1) Build lookups:
   - candidates_by_symbol from scanner_output
   - patterns_by_symbol from pattern_output

2) For each symbol in candidates_by_symbol:
   - Pull candidate fields if available: gap_percent, rvol, float_millions
   - Compute base_strength:
       base = 0.50
       if gap_percent >= 8.0: base += 0.10
       elif gap_percent >= 4.0: base += 0.06
       if rvol >= 3.0: base += 0.10
       elif rvol >= 2.0: base += 0.06
       if float_millions <= 50.0: base += 0.08
       elif float_millions <= 100.0: base += 0.04
     Clamp to [0.30, 0.90]

3) Derive “signal candidates” (no candles, teaching heuristics):
   - If gap_percent >= 8.0 AND float_millions <= 50.0 AND rvol >= 2.0:
       propose SignalType.HOD_BREAK with strength = min(base + 0.05, 0.90)
   - If gap_percent between 4.0 and 8.0 AND rvol >= 2.0:
       propose SignalType.MOMO_BREAKOUT with strength = base
   - If rvol >= 3.5 AND gap_percent >= 6.0:
       propose SignalType.ORB_BREAK with strength = min(base + 0.03, 0.90)
   - If a PatternResult exists and its pattern_name contains "Gap and Go":
       propose SignalType.FIRST_PULLBACK_LONG with strength = min(base + 0.02, 0.90)
   - If a PatternResult exists and its pattern_name contains "Momentum":
       propose SignalType.VWAP_RECLAIM with strength = min(base + 0.01, 0.90)

4) Filter + limits:
   - Only emit signals where strength >= min_strength
   - Per symbol: sort signals by strength desc, then signal_type name asc; keep max_signals_per_symbol
   - Cycle limit: after collecting all, sort by strength desc, then symbol asc; keep max_signals_per_cycle

5) Rationale (must include):
   - symbol, tick
   - gap%, rvol, float
   - the rule that triggered it (short phrase)
   - final strength numeric value

STEP D — EXPORT PACKAGE (CREATE)
Create `src/signals/__init__.py` exporting:
- SignalType
- SignalEvent
- SignalEngineV1
- SignalEngineConfig

STEP E — ORCHESTRATOR WIRING (MODIFY)
Modify `src/orchestrator/core_orchestrator.py`:

1) Instantiate SignalEngineV1 at boot (log it like other modules).
2) In `run_once()` pipeline order MUST be:
   Scanner → PatternEngine → SignalEngine → StrategyRunner → Risk → Execution → Exits → Storage
3) Capture signals list and print teaching log lines:
   - number of signals
   - list a short one-liner per signal (symbol, type, strength)
4) Emit a SystemEvent for signals:
   - event_type: "SIGNALS_GENERATED" (string)
   - source: "SignalEngineV1"
   - payload: {"signals": <count>}
If you have strict event type schema, register this event (optional file noted above).

STEP F — STRATEGY RUNNER PASS-THROUGH (MODIFY ONLY IF NEEDED)
If your StrategyRunner currently only accepts pattern_output:
- Add optional `signals: list[SignalEvent] | None = None` to the runner method signature used by orchestrator.
- Dispatch to strategies in backward-compatible way:
   try: intents = strategy.evaluate(pattern_output, signals=signals)
   except TypeError: intents = strategy.evaluate(pattern_output)

Do not modify existing strategy implementations unless required.

STEP G — ACCEPTANCE CHECKLIST
Run `src/main.py` and confirm:
- Boot logs show SignalEngineV1 instantiated.
- Each cycle shows signals generated deterministically (given static scanner candidates).
- RossMomentumStrategyV1 can now see “signals present: yes/no” in its rationale (if you already wired that).
- Replay includes the new SIGNALS_GENERATED event without breaking invariants.

OUT OF SCOPE
- Real candles (1m/5m), VWAP math, true HOD/ORB based on OHLC
- IBKR market data subscriptions
- L2 / tape analytics

DELIVERABLES
- src/signals/signal_types.py
- src/signals/signal_event.py
- src/signals/signal_engine_v1.py
- src/signals/__init__.py
- core orchestrator updated to run SignalEngine and emit SIGNALS_GENERATED
- StrategyRunner updated only if required for signals pass-through

END