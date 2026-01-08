PHASE_13_STEP_13_1_ROSS_MOMENTUM_SIGNAL_ARCHITECTURE
PHASE 13 · STEP 13.1 — ROSS MOMENTUM SIGNAL ARCHITECTURE (SKELETON-FIRST, NO REAL DATA YET)

OBJECTIVE
Create a clean “Signals” architecture that can host Ross-style momentum triggers (HOD break, PMH break, micro pullback, bull flag, ORB 1m, etc.) without changing the orchestrator pipeline. This step is ONLY architecture + contracts + deterministic teaching stubs. No IBKR. No live feeds. No randomness.

SCOPE (DO THIS NOW)
1) Add a new module: src/signals/
   - src/signals/__init__.py
   - src/signals/base.py
   - src/signals/types.py
   - src/signals/registry.py
   - src/signals/engine.py
   - src/signals/impl/ (folder)
     - src/signals/impl/__init__.py
     - src/signals/impl/hod_break.py
     - src/signals/impl/premarket_high_break.py
     - src/signals/impl/micro_pullback.py
     - src/signals/impl/bull_flag.py
     - src/signals/impl/orb_1m.py

2) Define signal data contracts in src/signals/types.py
   Requirements:
   - Use dataclasses
   - Keep fields explicit and stable; no Any payloads
   - Include:
     a) SignalType (Enum) for the signal names
     b) SignalDecision (Enum) with values: NO_SIGNAL, SIGNAL, INVALID
     c) SignalContext dataclass with minimally:
        - symbol: str
        - tick: int
        - run_mode: str  (store as string to avoid import cycles; can be “SIM”, “PAPER”, “LIVE”)
        - session: str   (store as string: “PRE”, “REGULAR”, “AFTER”, “CLOSED”)
     d) Level dataclass (optional but recommended):
        - name: str (e.g. “HOD”, “PMH”, “VWAP”)
        - price: Decimal
     e) SignalEvent dataclass:
        - signal_type: SignalType
        - symbol: str
        - tick: int
        - decision: SignalDecision
        - confidence: float (0..1)
        - rationale: str
        - entry_level: Optional[Decimal]
        - stop_level: Optional[Decimal]
        - target_level: Optional[Decimal]
        - invalidation_level: Optional[Decimal]
        - source: str (e.g. class name)
   - Use Decimal for all prices.
   - Provide helper function validate_signal_event(event) that enforces:
     - confidence between 0 and 1
     - if decision != SIGNAL then entry/stop/target may be None
     - if decision == SIGNAL then entry_level and invalidation_level must not be None
   - Keep validation strict but non-crashing: return (ok: bool, reason: str)

3) Define a base interface in src/signals/base.py
   - Abstract class BaseSignal:
     - property signal_type: SignalType
     - method evaluate(context: SignalContext, inputs: dict) -> SignalEvent
   Notes:
   - “inputs” stays as dict for now to avoid forcing candle structures; later phases will replace with typed MarketSnapshot/CandleSeries.
   - In this step, implementations will read only what they need from inputs (e.g. inputs.get("hod"), inputs.get("last_price")).

4) Add registry in src/signals/registry.py
   - SignalRegistry class:
     - register(signal: BaseSignal)
     - list_signals() -> list[BaseSignal]
     - get_by_type(signal_type: SignalType) -> BaseSignal
   - Enforce uniqueness by signal_type.
   - Provide convenience factory function build_default_signal_registry() that registers all implementations from src/signals/impl/*.

5) Add signal engine in src/signals/engine.py
   - SignalEngine class:
     - __init__(registry: SignalRegistry, event_collector: Optional[EventCollector] = None)
     - evaluate_all(context: SignalContext, inputs_by_symbol: dict[str, dict]) -> dict[str, list[SignalEvent]]
       - For each symbol, evaluate each registered signal.
       - Collect SignalEvent objects.
       - Validate each; if invalid, emit INVALID event with rationale that includes validation reason.
       - Return mapping symbol -> list[SignalEvent] (including NO_SIGNAL events is OPTIONAL; prefer returning only SIGNAL or INVALID to keep output concise.)
   - Integrate with existing event system:
     - Emit SystemEvent with event_type="SIGNAL_EMITTED" when a valid SIGNAL occurs
     - Emit SystemEvent with event_type="SIGNAL_INVALID" when validation fails
     - Payload must include: symbol, signal_type, decision, confidence

6) Provide deterministic teaching stub implementations in src/signals/impl/*.py
   - IMPORTANT: These are placeholders; they must be deterministic and simple.
   - Each implementation must:
     - Set its signal_type
     - Read minimal inputs from dict:
       - last_price: Decimal
       - hod: Decimal
       - pmh: Decimal
       - vwap: Decimal
       - orb_high: Decimal
       - pullback_low: Decimal
     - Evaluate with simple rule and produce SignalEvent:
       a) hod_break: SIGNAL if last_price >= hod and hod > 0
       b) premarket_high_break: SIGNAL if last_price >= pmh and pmh > 0
       c) micro_pullback: SIGNAL if last_price >= (pullback_low + (pullback_low * Decimal("0.02"))) (2% reclaim from pullback low) and pullback_low > 0
       d) bull_flag: SIGNAL if last_price >= vwap and vwap > 0 (teaching placeholder)
       e) orb_1m: SIGNAL if last_price >= orb_high and orb_high > 0
     - Set:
       - entry_level = the trigger level (hod/pmh/vwap/orb_high/etc.)
       - invalidation_level = pullback_low if available else (entry_level - small offset)
       - stop_level = invalidation_level
       - target_level optional (can be None in this step)
       - confidence:
         - 0.70 for HOD/PMH/ORB triggers
         - 0.55 for bull_flag and micro_pullback placeholders
     - If required input missing, return NO_SIGNAL with rationale.

7) Integrate Signals into the orchestrator pipeline without changing strategy logic yet
   - Find the orchestrator run_once() pipeline stage order.
   - Insert after Pattern stage and before Strategy stage:
     - Build a SignalContext for each cycle.
     - Create a simple “inputs_by_symbol” for teaching:
       - Use the ScannerCandidate price as last_price
       - Create deterministic fake levels derived from price:
         - hod = price * 1.00 (or price rounded)
         - pmh = price * 0.99
         - vwap = price * 0.995
         - orb_high = price * 1.01
         - pullback_low = price * 0.97
       - Use Decimal with quantize to 0.01 where appropriate.
     - Evaluate signals with SignalEngine
     - Print a concise log line:
       - “[SIGNALS] symbol=XYZ signals=2 (HOD_BREAK, ORB_1M)”
   - Do NOT modify StrategyRunner yet; we are only adding observability and future input.

8) Update README / docs
   - Add a short section: “Phase 13 — Signals Layer”
     - Explain Signals sit between PatternEngine and StrategyRunner
     - Explain later phases will replace dict inputs with CandleSeries + MarketSnapshot
     - Document the new event types: SIGNAL_EMITTED, SIGNAL_INVALID

OUT OF SCOPE (DO NOT DO NOW)
- Real candle building
- Real VWAP computation
- Real Ross pattern math
- Feeding signals into strategies
- Broker integration changes
- New config flags (unless required for wiring)

ACCEPTANCE CRITERIA
- `python src/main.py` runs with no errors.
- Logs show the new stage and at least 1 SIGNAL_EMITTED event during a cycle (teaching data must produce some triggers).
- SignalEngine returns mapping symbol -> list[SignalEvent].
- No circular imports.
- All prices use Decimal.
- Validation never crashes the run; it downgrades to INVALID events.

DELIVERABLES
- New `src/signals/` package with the files listed.
- Orchestrator integration + logs.
- Updated README.

END