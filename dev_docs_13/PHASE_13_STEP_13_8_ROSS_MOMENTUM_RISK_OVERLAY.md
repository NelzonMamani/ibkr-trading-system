PHASE_13_STEP_13_8_ROSS_MOMENTUM_RISK_OVERLAY.md

OBJECTIVE
Introduce a Ross Momentum–specific risk overlay that enforces discretionary-style
discipline rules ABOVE the generic RiskEngine, without modifying or weakening
global risk logic.

This overlay must be:
- Strategy-scoped (Ross Momentum only)
- Deterministic
- Explainable
- Non-invasive to other strategies
- Enforced BEFORE execution routing

SCOPE
This step applies ONLY to:
- MomentumContinuationStrategy
- RossMomentumStrategy (if split later)

GapAndGo and other strategies MUST remain unaffected.

FILES TO CREATE
1) src/strategies/ross_momentum/ross_momentum_risk_overlay.py
2) src/strategies/ross_momentum/__init__.py (if missing)

FILES TO MODIFY
1) src/strategies/momentum_continuation_strategy.py
2) src/risk/risk_engine.py (integration hook ONLY, no logic duplication)
3) src/models/risk_decision.py (if reason codes missing)
4) src/events/event_types.py (if new block reasons added)

----------------------------------------
ROSS MOMENTUM RISK OVERLAY RULES (HARD)
----------------------------------------

RULE 1 — LONG ONLY
- If TradeIntent.direction != "LONG" → BLOCK
- Reason code: ROSS_BLOCK_SHORT

RULE 2 — GAP WINDOW
- gap_percent MUST be between:
  MIN_GAP = 4.0
  MAX_GAP = 20.0
- Outside range → BLOCK
- Reason code: ROSS_BLOCK_GAP_OUT_OF_RANGE

RULE 3 — FLOAT CEILING
- float_millions MUST be <= 100.0
- Above → BLOCK
- Reason code: ROSS_BLOCK_FLOAT_TOO_HIGH

RULE 4 — RELATIVE VOLUME FLOOR
- rvol MUST be >= 2.0
- Below → BLOCK
- Reason code: ROSS_BLOCK_LOW_RVOL

RULE 5 — SIGNAL CONFIDENCE FLOOR
- confidence MUST be >= 0.60
- Below → BLOCK
- Reason code: ROSS_BLOCK_LOW_CONFIDENCE

RULE 6 — PER-SYMBOL COOLDOWN
- Same symbol cannot be re-entered within:
  COOLDOWN_TICKS = 5
- Track via execution registry or overlay-local cache
- Reason code: ROSS_BLOCK_COOLDOWN_ACTIVE

RULE 7 — MAX ATTEMPTS PER SYMBOL (SESSION)
- Max attempts per symbol per session = 2
- Includes rejected and unfilled attempts
- Reason code: ROSS_BLOCK_MAX_ATTEMPTS

----------------------------------------
IMPLEMENTATION DETAILS
----------------------------------------

1) Create class RossMomentumRiskOverlay

   class RossMomentumRiskOverlay:
       def evaluate(
           self,
           trade_intent: TradeIntent,
           context: RiskContext
       ) -> Optional[RiskDecision]

   - Return None if trade passes overlay
   - Return RiskDecision(allowed=False, ...) if blocked

2) Overlay MUST NOT:
   - Modify TradeIntent
   - Modify global RiskEngine rules
   - Perform sizing logic

3) Overlay MUST:
   - Attach clear rationale text
   - Emit TRADE_BLOCKED event with Ross-specific reason
   - Preserve determinism (no randomness, no time-based logic)

----------------------------------------
INTEGRATION POINT
----------------------------------------

Modify RiskEngine flow:

Existing:
  RiskEngine.evaluate_intent()

New order:
  1) If strategy is Ross Momentum:
        → apply RossMomentumRiskOverlay FIRST
        → if blocked, short-circuit and return RiskDecision
  2) If allowed:
        → proceed with existing RiskEngine logic unchanged

DO NOT duplicate generic limits (max trades, sizing, etc.).

----------------------------------------
EVENT & OBSERVABILITY REQUIREMENTS
----------------------------------------

- All blocks MUST emit:
  event_type = TRADE_BLOCKED
  source = RossMomentumRiskOverlay
  payload includes:
    - symbol
    - strategy_name
    - reason_code
    - human_readable_rationale

- Blocks MUST appear in:
  - event replay
  - cycle summaries
  - invariant checks

----------------------------------------
INVARIANTS
----------------------------------------

- Non-Ross strategies behave IDENTICALLY as before
- Ross Momentum signals can be valid yet blocked
- Replay must reconstruct identical block decisions
- No silent failures
- No live execution impact (SIM/PAPER/LIVE safe)

----------------------------------------
DEFINITION OF DONE
----------------------------------------

PHASE 13 · STEP 13.8 is complete when:

- Ross Momentum trades are blocked deterministically by overlay rules
- Block reasons are visible in logs, events, and replay
- Other strategies are unaffected
- No existing tests or invariants break
- System runs full cycles without error

END