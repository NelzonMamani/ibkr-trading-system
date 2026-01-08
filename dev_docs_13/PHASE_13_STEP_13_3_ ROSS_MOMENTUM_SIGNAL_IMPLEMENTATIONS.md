PHASE_13_STEP_13_3_ ROSS_MOMENTUM_SIGNAL_IMPLEMENTATIONS.md
PHASE 13 · STEP 13.3 — ROSS MOMENTUM SIGNAL IMPLEMENTATIONS (CORE TRIGGERS, TEACHING-FIRST)

OBJECTIVE
Implement the first concrete, Ross-style momentum signals inside the SignalEngine
using deterministic, teaching-first logic. These signals must:
- Be auditable and explainable
- Operate on existing ScannerCandidate + PatternResult inputs
- Produce SignalEvent(s) only (NO TradeIntent creation here)
- Remain SIM-safe and replay-safe

This step turns the SignalEngine from a placeholder into a real Ross-style trigger layer.

SCOPE (DO THIS NOW)

1) Files to modify / create
- MODIFY: src/signals/signal_engine.py
- MODIFY (if needed): src/signals/signal_models.py
- NO orchestrator changes in this step

2) Signal types to implement (INITIAL SET)
Implement the following Ross-style signals:

A) PREMARKET_HIGH_BREAK
B) HOD_BREAK
C) ORB_1M (Opening Range Break – teaching approximation)
D) MICRO_PULLBACK (simplified)
E) BULL_FLAG (simplified)

You already have SignalType enum — extend it if required.

3) Input contract (STRICT)
SignalEngine.evaluate(...) must ONLY use:
- scanner_candidates: list[ScannerCandidate]
- pattern_results: list[PatternResult]
- tick: int
- deterministic price feed helper (already in execution layer; mirror logic)

NO live data, NO IBKR calls, NO randomness beyond deterministic mapping.

4) Deterministic price reference (TEACHING RULE)
For each symbol at a given tick:
- base_price = scanner_candidate.price
- simulated_last_price = base_price + (tick * 0.01)
This keeps signals reproducible across replay.

5) Signal definitions (TEACHING LOGIC)

A) PREMARKET_HIGH_BREAK
Trigger when:
- scanner_candidate.gap_percent >= 4.0
- simulated_last_price > scanner_candidate.price * 1.01
Emit SignalEvent:
- type=PREMARKET_HIGH_BREAK
- confidence=0.65
- entry_level = simulated_last_price
- stop_level = simulated_last_price * 0.985
- rationale must mention gap + premarket break

B) HOD_BREAK
Trigger when:
- simulated_last_price > scanner_candidate.price * 1.02
Emit SignalEvent:
- type=HOD_BREAK
- confidence=0.70
- entry_level = simulated_last_price
- stop_level = simulated_last_price * 0.99
- rationale must mention HOD-style momentum

C) ORB_1M (Teaching Approximation)
Trigger when:
- tick == 1
- simulated_last_price > scanner_candidate.price * 1.005
Emit SignalEvent:
- type=ORB_1M
- confidence=0.60
- entry_level = simulated_last_price
- stop_level = scanner_candidate.price
- rationale must mention opening range concept (teaching)

D) MICRO_PULLBACK (Simplified)
Trigger when:
- tick >= 2
- simulated_last_price > scanner_candidate.price * 1.015
Emit SignalEvent:
- type=MICRO_PULLBACK
- confidence=0.55
- entry_level = simulated_last_price
- stop_level = simulated_last_price * 0.99
- rationale must mention pullback continuation

E) BULL_FLAG (Simplified)
Trigger when:
- pattern_result.pattern_name contains "Gap"
- simulated_last_price > scanner_candidate.price * 1.018
Emit SignalEvent:
- type=BULL_FLAG
- confidence=0.60
- entry_level = simulated_last_price
- stop_level = simulated_last_price * 0.985
- rationale must mention bull flag structure (teaching)

6) Pattern association
If a PatternResult exists for the symbol:
- Attach pattern_name into SignalEvent.metadata["pattern"]
- Do NOT boost confidence here (adapter handles merging)

7) Emission rules
- Multiple signals per symbol per tick ARE allowed
- Each emitted SignalEvent must include:
  - symbol
  - signal_type
  - confidence
  - entry_level
  - stop_level
  - tick
  - rationale
  - metadata (dict)

8) Eventing
For every emitted signal:
Emit SystemEvent:
- event_type="SIGNAL_DETECTED"
- source="SignalEngine"
- payload:
  - symbol
  - signal_type
  - confidence
  - tick

Additionally emit a summary event per cycle:
- event_type="SIGNAL_SUMMARY"
- payload includes:
  - tick
  - total_signals
  - by_type counts

9) Logging
Add concise logs:
- Per signal:
  "[SIGNAL] {symbol} {signal_type} conf={confidence} entry={entry_level} stop={stop_level}"
- Per cycle:
  "[SIGNAL] total={n} by_type={...}"

10) Safety constraints
- Never emit signals if RUN_MODE == LIVE (still teaching)
- If RUN_MODE == LIVE, log:
  "[SIGNAL] LIVE mode — signal generation disabled"

11) Acceptance criteria
- python src/main.py runs cleanly
- Signals appear in logs before adapter stage
- Replay reproduces identical signals
- Multiple signals per symbol are visible
- No TradeIntent creation occurs in SignalEngine

OUT OF SCOPE
- Real OHLCV logic
- VWAP, EMA, volume surges
- Halts, SSR, LULD
- Short signals

DELIVERABLES
- Updated SignalEngine with Ross-style triggers
- Extended SignalType enum if required
- Deterministic, replay-safe signal output

END