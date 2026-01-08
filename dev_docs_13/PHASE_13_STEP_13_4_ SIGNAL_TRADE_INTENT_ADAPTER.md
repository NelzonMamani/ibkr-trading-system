PHASE_13_STEP_13_4_  SIGNAL_TRADE_INTENT_ADAPTER.md
PHASE 13 · STEP 13.4 — SIGNAL → TRADE INTENT ADAPTER (ROSS MOMENTUM MAPPING, TEACHING-FIRST)

FILES (EXACT)
- CREATE: src/signals/signal_to_intent_adapter.py
- MODIFY: src/signals/__init__.py
- MODIFY: src/orchestrator/core_orchestrator.py   (or your current orchestrator module that runs the stage pipeline)

GOAL
Add a dedicated adapter that converts SignalEvent(s) into TradeIntent(s) using Ross-style, teaching-friendly heuristics.
Do NOT change SignalEngine logic. Do NOT remove StrategyRunner.
Pipeline becomes:
Scanner → Pattern → Signals → Adapter → StrategyRunner → Merge Intents → Risk → Execution

NON-NEGOTIABLE RULES
- Deterministic: same inputs produce same outputs.
- Replay-safe: no randomness, no time-based branching.
- SIM-only behaviour: adapter generates intents but does NOT place orders (ExecutionEngine already controls broker routing).
- Clear rationale strings: must explain why an intent was created from a signal.
- No breaking changes: all existing phases must still run.

STEP A — IMPLEMENT THE ADAPTER (CREATE FILE)
Create `src/signals/signal_to_intent_adapter.py` with:
1) A small config dataclass for thresholds (with sensible defaults)
2) A `SignalToIntentAdapter` class with:
   - __init__(config, event_collector=None)
   - convert(signals: list[SignalEvent], tick: int | None = None) -> list[TradeIntent]

REQUIRED DEFAULT HEURISTICS (TEACHING-FIRST, ROSS-STYLE)
For each SignalEvent:
- If signal_type indicates a LONG bias:
  - "MOMO_BREAKOUT", "HOD_BREAK", "VWAP_RECLAIM", "ORB_BREAK", "FIRST_PULLBACK_LONG"
  → create TradeIntent(direction="LONG")
- If signal_type indicates a SHORT bias:
  - "FAIL_HOD", "VWAP_REJECT", "ORB_BREAKDOWN", "FIRST_PULLBACK_SHORT"
  → create TradeIntent(direction="SHORT")

Trader type mapping (use your existing enum/strings if present):
- Breakout/HOD/ORB signals → trader_type="MOMENTUM"
- First pullback signals → trader_type="SCALPER"
- VWAP reclaim/reject → trader_type="MOMENTUM"

Confidence mapping (deterministic, no randomness):
- Start with base_confidence = 0.55
- Add +0.10 if payload contains rvol >= 2.0
- Add +0.10 if payload contains gap_percent >= 4.0
- Add +0.05 if payload contains float_millions <= 50
- Clamp to [0.30, 0.90]

Stop/TP:
- Leave stop_loss_price and take_profit_price as None for now (teaching-first).
- (Optional) include a text note in rationale that risk/exit will handle later phases.

Origin tagging:
- Set TradeIntent fields:
  - strategy_name = "SignalAdapter"
  - rationale includes: signal_type + key payload fields used
  - direction, symbol, trader_type, confidence
If your TradeIntent supports extra fields:
- origin="SIGNAL"
- trigger=signal_type

Event emission (if you have EventCollector available):
- Emit SystemEvent event_type="SIGNAL_INTENTS_CREATED"
  payload: {"count": N, "signals_in": len(signals)}
Do NOT introduce schema enforcement failures—keep payload minimal.

STEP B — EXPORT ADAPTER (MODIFY __init__)
Modify `src/signals/__init__.py` to export:
- SignalToIntentAdapter
- SignalToIntentConfig (if you create it)

STEP C — ORCHESTRATOR WIRING (MODIFY CORE ORCHESTRATOR)
In `src/orchestrator/core_orchestrator.py` (or your orchestrator runner file), add:
1) Instantiate adapter during boot:
   - self.signal_intent_adapter = SignalToIntentAdapter(config=..., event_collector=self.event_collector)
2) In run_once() / cycle:
   - signals = self.signal_engine.evaluate(...)   (whatever you named it from Step 13.3)
   - adapter_intents = self.signal_intent_adapter.convert(signals, tick=context.tick)

3) Keep StrategyRunner as-is, but merge:
   - strategy_intents = self.strategy_runner.evaluate(pattern_results, ...) (existing)
   - merged_intents = adapter_intents + strategy_intents
   - Pass merged_intents into RiskEngine

IMPORTANT MERGE RULE
Do not duplicate intents for same symbol/direction/trader_type.
Implement a simple deterministic de-dup step before RiskEngine:
- Key = (symbol, direction, trader_type)
- Keep the higher-confidence intent if duplicates occur
- If confidence ties, keep adapter intent first (origin SIGNAL) for determinism

Logging/Teaching prints (minimal but explicit)
Add prints similar to:
- [SIGNAL_ADAPTER] signals_in=X intents_out=Y
- [INTENTS] merged total=Z (adapter=A strategy=S)

STEP D — ACCEPTANCE CHECKLIST
Run main.py and confirm:
- System still boots and cycles
- Signal stage runs
- Adapter creates intents (even if zero)
- RiskEngine receives merged intents (counts visible in logs)
- No crashes; exit/shutdown still clean

DO NOT DO (OUT OF SCOPE)
- No new IBKR order logic here
- No changes to ExecutionEngine kill-switch logic
- No strategy rewrites
- No persistence changes
- No time-of-day logic changes

DELIVERABLES
- New file: src/signals/signal_to_intent_adapter.py
- Updated: src/signals/__init__.py
- Updated: src/orchestrator/core_orchestrator.py (pipeline updated + merge/de-dup)

END