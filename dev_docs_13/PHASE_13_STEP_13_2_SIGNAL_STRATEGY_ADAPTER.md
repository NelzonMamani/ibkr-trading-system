PHASE_13_STEP_13_2_SIGNAL_STRATEGY_ADAPTER.md
PHASE 13 · STEP 13.2 — SIGNAL → STRATEGY ADAPTER (TURN SIGNALS INTO TRADEINTENTS, STILL SIM/TEACHING)

OBJECTIVE
Wire the new Signals layer into strategy decision-making in a clean, testable way:
- Signals produce SignalEvent(s)
- A dedicated adapter converts selected SignalEvent(s) into TradeIntent(s)
- StrategyRunner consumes the resulting intents WITHOUT rewriting your orchestrator stages

This is still teaching-first: deterministic, SIM-only defaults, no live market data requirement.

SCOPE (DO THIS NOW)
1) Create an adapter module:
   - src/strategy/signal_adapter.py

2) Define a strict adapter contract:
   - class SignalToIntentAdapter:
       - def __init__(self, logger=None): ...
       - def to_trade_intents(
             self,
             signal_events_by_symbol: dict[str, list[SignalEvent]],
             pattern_results: list[PatternResult],
             scanner_candidates: list[ScannerCandidate],
             tick: int
         ) -> list[TradeIntent]

Rules:
- The adapter is responsible for mapping:
  (SignalEvent + (optional PatternResult) + (optional ScannerCandidate)) -> TradeIntent
- The adapter must be deterministic and must not call IBKR or external services.

3) Implement mapping rules (teaching defaults)
A) Direction (system language):
- All initial Ross triggers are LONG-only for teaching: direction="LONG"
- If SignalEvent.decision != SIGNAL → ignore

B) Choose strategy_name and trader_type
Map SignalType → (strategy_name, trader_type)
- HOD_BREAK, PREMARKET_HIGH_BREAK, ORB_1M → GapAndGoStrategy, trader_type="SCALPER"
- MICRO_PULLBACK, BULL_FLAG → MomentumContinuationStrategy, trader_type="MOMENTUM"

C) Confidence
- Use SignalEvent.confidence (not Pattern confidence). If both exist, take max(signal_conf, pattern_conf) but cap at 0.95.

D) Rationale (must be audit-friendly)
TradeIntent.rationale must concatenate:
- Signal rationale
- Trigger levels (entry/invalidation)
- Optional pattern label if a PatternResult exists for the symbol

Example:
"Signal=HOD_BREAK conf=0.70 entry=12.40 invalid=12.10 | Pattern=Gap and Go (Teaching) conf=0.82 | Teaching: signals→intent adapter."

E) stop_loss_price / take_profit_price
- If SignalEvent.stop_level exists, set TradeIntent.stop_loss_price = stop_level
- take_profit_price remains None in this step

4) De-duplication and priority rules
It is possible to have multiple signals per symbol in the same tick.
Implement:
- For each symbol, select at most ONE TradeIntent per trader_type.
- Priority order (highest first):
  1) HOD_BREAK
  2) PREMARKET_HIGH_BREAK
  3) ORB_1M
  4) MICRO_PULLBACK
  5) BULL_FLAG
- If two signals have equal priority, pick higher confidence.
- Additionally, enforce a global cap (teaching):
  - max_total_intents_per_cycle = 3
  - If more exist, keep highest confidence across all.

5) Orchestrator integration (minimal, no churn)
Locate the existing flow:
Scanner -> PatternEngine -> StrategyRunner -> Risk -> Execution ...
You already inserted Signals between Pattern and Strategy.

Now modify orchestrator.run_once() to:
- Collect:
  - scanner_candidates
  - pattern_results
  - signal_events_by_symbol (from SignalEngine)
- Invoke adapter.to_trade_intents(...)
- Pass the resulting TradeIntents to StrategyRunner in ONE of two ways:

Option 1 (preferred, minimal disruption):
- Add a new StrategyRunner method:
  - run_from_intents(intents: list[TradeIntent]) -> list[TradeIntent]
  - For now this method simply returns the same list, but emits STRATEGY_COMPLETE with count.
- This keeps StrategyRunner as the stage owner and preserves event semantics.

Option 2 (if StrategyRunner is not easy to change):
- Bypass StrategyRunner for now and feed intents directly into RiskEngine,
  BUT still emit a STRATEGY_COMPLETE event from orchestrator with correct payload.
(Prefer Option 1.)

6) Eventing
Emit an event for traceability when adapter generates intents:
- SystemEvent event_type="INTENTS_FROM_SIGNALS"
- source="SignalToIntentAdapter"
- payload includes:
  - tick
  - total_intents
  - by_trader_type counts
  - by_strategy counts

Keep payload small (counts only, no huge dumps).

7) Logging
Add a concise summary line per cycle:
- "[ADAPTER] intents=3 by_type={SCALPER:2,MOMENTUM:1} by_strategy={GapAndGoStrategy:2,MomentumContinuationStrategy:1}"

8) Tests (lightweight, deterministic)
Add a minimal unit test file (if you already have tests folder):
- tests/test_signal_adapter.py
Test cases:
- Multiple signals same symbol → chooses highest priority
- Confidence merge with pattern result works
- Global cap of 3 enforced

If no test harness exists, skip tests but ensure adapter is pure and easy to test later.

OUT OF SCOPE (DO NOT DO NOW)
- Replacing PatternEngine logic with Ross logic
- Real candle or volume rules
- Profit targets, trailing stops, partials
- IBKR order placement changes

ACCEPTANCE CRITERIA
- `python src/main.py` runs cleanly.
- During a cycle, signals produce SignalEvent(s).
- Adapter generates TradeIntent(s) and logs [ADAPTER] summary.
- Downstream RiskEngine sees those intents (3 max) and continues to work.
- STRATEGY_COMPLETE semantics remain consistent (event emitted, count correct).

DELIVERABLES
- src/strategy/signal_adapter.py
- StrategyRunner integration (Option 1 preferred)
- Orchestrator wiring updates
- Minimal tests if feasible

END