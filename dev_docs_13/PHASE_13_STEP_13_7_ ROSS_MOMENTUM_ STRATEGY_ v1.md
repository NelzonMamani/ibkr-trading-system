PHASE_13_STEP_13_7_ ROSS_MOMENTUM_ STRATEGY_ v1.md
PHASE 13 · STEP 13.7 — ROSS MOMENTUM STRATEGY v1 (CONSUME SIGNALS → TRADEINTENT) + OPTIONAL “ONE-SHOT” MODE

FILES (EXACT)
- CREATE: src/strategies/ross_momentum_strategy_v1.py
- MODIFY: src/strategies/__init__.py
- MODIFY: src/orchestrator/core_orchestrator.py
- MODIFY (OPTIONAL): src/config/runtime_config.py
- MODIFY (OPTIONAL): src/main.py

GOAL
Introduce a RossMomentumStrategyV1 that consumes SignalEvent(s) from SignalEngineV1 and converts them into TradeIntent(s) using deterministic, teaching-safe rules (SIM only).
Also add an OPTIONAL “ONE_SHOT” run mode for quick validation (single cycle then exit cleanly).

NON-NEGOTIABLES
- No live trading enablement here.
- Must remain deterministic and replay-safe.
- Must not break existing strategies (GapAndGoStrategy, MomentumContinuationStrategy).
- Strategy must never emit more than:
  - 1 TradeIntent per symbol per cycle
  - 2 total TradeIntents per cycle (from this strategy)

SCOPE
A) Add a new Strategy implementation: RossMomentumStrategyV1
B) Wire it into the StrategyRunner registration (same as other strategies)
C) Orchestrator passes SignalEvents into StrategyRunner (already added in Step 13.6)
D) Optional “ONE_SHOT” mode to stop after a single orchestrator cycle for faster iteration

A — CREATE STRATEGY FILE
Create `src/strategies/ross_momentum_strategy_v1.py`.

Implement:
1) Class `RossMomentumStrategyV1` with:
   - `name = "RossMomentumStrategyV1"`
   - `trader_type = "MOMENTUM"` (match your existing trader_type conventions)
   - `enabled` handled by config the same way other strategies are enabled

2) Method signature MUST accept signals:
   - `evaluate(self, pattern_results: list[PatternResult], signals: list[SignalEvent] | None = None) -> list[TradeIntent]`

3) Deterministic intent rules (implement exactly):
   - If signals is None or empty → return []
   - Build signals_by_symbol.
   - Priority order of signal types for LONG intents:
       1) HOD_BREAK
       2) ORB_BREAK
       3) MOMO_BREAKOUT
       4) VWAP_RECLAIM
       5) FIRST_PULLBACK_LONG
   - For each symbol:
       - Choose the highest-priority signal present; if multiple of same type choose highest strength.
       - Only proceed if signal.strength >= 0.60
       - Determine confidence:
            confidence = clamp(signal.strength, 0.50, 0.90)
       - Create ONE TradeIntent per symbol:
            symbol = signal.symbol
            direction = "LONG"
            strategy_name = "RossMomentumStrategyV1"
            trader_type = "MOMENTUM"
            confidence = confidence
            rationale MUST include:
              - selected signal_type
              - signal strength
              - tick
              - short teaching note: “signal → intent (no prediction)”
       - Do not set stop_loss_price / take_profit_price yet (leave None).

4) Cycle cap:
   - Sort created intents by confidence desc then symbol asc
   - Keep at most 2 intents per cycle.

5) Logging:
   - Print:
     - number of signals received
     - number of intents generated
     - per intent: symbol, signal_type used, confidence

B — EXPORT STRATEGY (MODIFY)
Modify `src/strategies/__init__.py` to export RossMomentumStrategyV1.

C — REGISTER STRATEGY (MODIFY)
In whichever strategy registration mechanism you currently use (likely orchestrator boot where other strategies are enabled):
- Import RossMomentumStrategyV1
- Add config toggle:
   - Key name: ROSS_MOMENTUM_STRATEGY_ENABLED (default False unless you already manage in config)
- When enabled: register it with StrategyRunner alongside existing strategies.
- Boot log must include:
   [BOOT] Strategy 'RossMomentumStrategyV1' ENABLED via config and registered.

D — OPTIONAL: ADD ONE_SHOT MODE (FAST VALIDATION)
If you want faster iterative testing without Ctrl+C:

1) runtime_config (OPTIONAL)
Modify `src/config/runtime_config.py` to add:
- RUN_LOOP_MODE: "CYCLE" | "ONE_SHOT" (default "CYCLE")

2) main.py (OPTIONAL)
Modify main loop so:
- If RUN_LOOP_MODE == "ONE_SHOT":
   - run exactly one orchestrator cycle
   - perform event replay selection once
   - initiate graceful shutdown sequence without KeyboardInterrupt

3) orchestrator/core_orchestrator.py (OPTIONAL)
- Ensure calling run_once() directly works without needing continuous loop state.

This is optional; do it only if it’s easy and does not risk destabilising the loop.

E — ACCEPTANCE CHECKLIST
Run with:
- Signal engine enabled (from Step 13.6)
- RossMomentumStrategyV1 enabled

Expected:
- Signals generated (non-zero) from teaching candidates.
- RossMomentumStrategyV1 receives those signals and emits up to 2 intents.
- RiskEngine sees MOMENTUM trader_type and enforces existing MOMENTUM limits.
- ExecutionEngine runs SIM-only deterministic flow as before.
- No breaking changes to existing strategies.

DO NOT CHANGE
- Existing GapAndGoStrategy / MomentumContinuationStrategy logic
- RiskEngine limits (unless failing tests)

DELIVERABLES
- src/strategies/ross_momentum_strategy_v1.py
- strategies/__init__.py updated
- strategy registration updated (config-gated)
- (optional) ONE_SHOT mode implemented cleanly

END