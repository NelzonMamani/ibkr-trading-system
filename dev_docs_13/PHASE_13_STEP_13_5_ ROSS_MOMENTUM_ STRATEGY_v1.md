PHASE_13_STEP_13_5_ ROSS_MOMENTUM_ STRATEGY_v1.md
PHASE 13 · STEP 13.5 — ROSS MOMENTUM STRATEGY v1 (REAL SIGNALS → TEACHING TRADE INTENTS)

FILES (EXACT)
- CREATE: src/strategies/ross_momentum_strategy_v1.py
- MODIFY: src/strategies/__init__.py
- MODIFY: src/orchestrator/core_orchestrator.py   (strategy registration)
- MODIFY (ONLY IF NEEDED): src/strategies/strategy_runner.py

GOAL
Introduce a RossMomentumStrategyV1 that consumes PatternResult(s) AND/OR SignalEvent(s) (depending on your existing StrategyRunner signature) and produces TradeIntent(s) using Ross-style, teaching-first rules.

This is the “first real” Ross strategy module:
- Deterministic
- Replay-safe
- SIM-first
- Produces intents only (risk/execution decide what happens)

SCOPE
- Add strategy class with clear rules and rationale strings.
- Register it like existing strategies.
- Wire it into StrategyRunner in the cleanest way that does not break existing strategies.

NON-NEGOTIABLES
- No broker calls here.
- No randomness.
- No external APIs.
- No time-based branching.
- Must not break GapAndGoStrategy or MomentumContinuationStrategy.

STEP A — DEFINE THE STRATEGY MODULE (CREATE FILE)
Create `src/strategies/ross_momentum_strategy_v1.py` with:

1) `RossMomentumStrategyConfig` dataclass (defaults are teaching-safe):
   - enabled: bool = True
   - min_confidence: float = 0.55
   - allow_short: bool = False   (default false; shorts later)
   - max_intents_per_cycle: int = 3
   - require_signal_confirmation: bool = False  (default false; can be toggled later)

2) `RossMomentumStrategyV1` implementing your existing strategy interface/base class:
   - name property or attribute: "RossMomentumStrategyV1"
   - `evaluate(...) -> list[TradeIntent]`
   - If you have an `evaluate_exit_signals(...)`, keep it no-op for now.

INPUTS (SUPPORT BOTH IF AVAILABLE)
- Primary input: pattern_results: list[PatternResult]
- Optional input: signals: list[SignalEvent] (if StrategyRunner can pass them)
If signals are not available in StrategyRunner yet, implement strategy using pattern_results only.
If signals are available, use them to boost confidence and/or filter.

STEP B — TEACHING RULESET (ROSS-STYLE, DETERMINISTIC)
Interpret Ross momentum as:
- We want gappers with high RVOL and small float.
- We want a “setup classification” that resembles:
  - Gap & Go / HOD Break / ORB Break / First Pullback / VWAP Reclaim

You must implement these deterministic rules (no candles required yet):

Rule 1: Candidate qualification (from PatternResult rationale/payload if present)
For each PatternResult:
- Extract symbol
- Determine a base score using available attributes:
  - If PatternResult has confidence, start there; else start at 0.55
  - If PatternResult pattern_name contains "Gap" → +0.05
  - If PatternResult pattern_name contains "Momentum" → +0.03
Clamp confidence to [0.30, 0.90]

Rule 2: Optional signal confirmation (if signals provided)
If signals available:
- Build a lookup: signals_by_symbol = {symbol: [SignalEvent,...]}
- If any bullish signal types exist for symbol:
  - "MOMO_BREAKOUT", "HOD_BREAK", "ORB_BREAK", "VWAP_RECLAIM", "FIRST_PULLBACK_LONG"
  → +0.07 confidence boost (once)
- If require_signal_confirmation=True and there are no bullish signals → skip the candidate entirely.

Rule 3: Intent generation
Create a TradeIntent if confidence >= min_confidence.
- direction: "LONG"
- strategy_name: "RossMomentumStrategyV1"
- trader_type:
  - If signal indicates FIRST_PULLBACK_LONG → "SCALPER"
  - Else → "MOMENTUM"
  - If no signals available → default "MOMENTUM"
- stop_loss_price / take_profit_price: None (teaching-first)
- rationale MUST include:
  - "RossMomentumStrategyV1"
  - pattern_name
  - whether signal confirmation was present (yes/no)
  - final confidence numeric value

Rule 4: Limit intents per cycle
- Sort candidates by confidence desc, tie-break by symbol asc
- Return up to max_intents_per_cycle

Rule 5: Shorts are disabled by default
- If allow_short=False: never emit SHORT intents, even if bearish signals exist.
(We will add short module later.)

STEP C — EXPORT STRATEGY (MODIFY __init__)
Modify `src/strategies/__init__.py` to export:
- RossMomentumStrategyV1
- RossMomentumStrategyConfig

STEP D — ORCHESTRATOR REGISTRATION (MODIFY CORE ORCHESTRATOR)
In `src/orchestrator/core_orchestrator.py`:
- Instantiate RossMomentumStrategyV1 using config (enable by default only if you want it active).
- Register it with StrategyRunner in the same way as other strategies.
- Ensure logs show it enabled/registered.

STEP E — STRATEGY RUNNER PLUMBING (ONLY IF NEEDED)
If your StrategyRunner currently calls:
- strategy.evaluate(pattern_results)
and you want to pass signals too:
- Update StrategyRunner to call:
  strategy.evaluate(pattern_results, signals=signals)
But ONLY do this if:
- Your existing strategies can accept extra kwargs, OR
- You implement backward-compatible dispatch:
   - Try calling with signals, catch TypeError, call without.

Preferred approach (backward compatible):
- In StrategyRunner:
  - for strategy in strategies:
      try:
          intents = strategy.evaluate(pattern_results, signals=signals)
      except TypeError:
          intents = strategy.evaluate(pattern_results)

Do not break existing strategies.

STEP F — ACCEPTANCE CHECKLIST
Run main.py and confirm:
- Boot logs show RossMomentumStrategyV1 registered.
- StrategyRunner dispatch includes RossMomentumStrategyV1.
- It produces 0..N TradeIntents deterministically.
- Merged intents flow to RiskEngine and ExecutionEngine without crash.
- Replay still works; no new schema errors beyond existing ones.

OUT OF SCOPE
- Candle building, 1-min/5-min pattern detection
- True HOD/LOD calculations
- VWAP computation
- Real-time Level 2 / tape
- Position management beyond existing teaching exit engine

DELIVERABLES
- src/strategies/ross_momentum_strategy_v1.py
- src/strategies/__init__.py updated
- src/orchestrator/core_orchestrator.py updated (registration)
- src/strategies/strategy_runner.py updated ONLY if required for signals arg support

END