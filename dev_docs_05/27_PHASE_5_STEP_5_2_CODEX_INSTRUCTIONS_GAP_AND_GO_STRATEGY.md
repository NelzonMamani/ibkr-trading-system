27_PHASE_5_STEP_5_2_CODEX_INSTRUCTIONS_GAP_AND_GO_STRATEGY.md
Title: STEP 5.2 — Codex Instructions: Implement GapAndGoStrategy (Teaching-First, Deterministic)

Content:

Objective (What Codex must build)

Implement a real Strategy module as a first-class component:

Create GapAndGoStrategy as its own file/class

Refactor StrategyRunner to dispatch strategies (not own logic)

Keep system deterministic, safe, and SIM-only

Preserve / improve teaching logs

Ensure python src/main.py still runs cleanly with multi-symbol flow

This is Phase 5 behavior: Strategy as a plugin.

Guardrails (Non-Negotiable)

No broker calls (no IBKR, no ib_insync, no network).

No randomness (no random module, no time-based “choices”).

Must run in RUN_MODE=SIM unchanged.

Keep logging teacher-first: explain decisions, thresholds, why included/excluded.

Strategies must be stateless per cycle (no persistence, no caching).

Strategy must return List[TradeIntent].

Files to Create / Modify
✅ Create

src/strategy/base_strategy.py

src/strategy/gap_and_go_strategy.py

✅ Modify

src/strategy/strategy_runner.py

src/models/data_models.py (only if needed for new fields / types; keep backwards-safe)

No other files unless absolutely necessary.

Step-by-Step Instructions for Codex
1) Create BaseStrategy contract

File: src/strategy/base_strategy.py

Implement a minimal interface:

class BaseStrategy(Protocol) or simple ABC-style base class

Required attributes / methods:

name: str

evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]

Teaching comment: explain why we keep strategies isolated and stateless.

2) Implement GapAndGoStrategy

File: src/strategy/gap_and_go_strategy.py

This strategy should:

Take PatternResult list as input

Filter only items where pattern_name contains "Gap and Go" (case sensitive match ok)

For each matching PatternResult:

Create a TradeIntent with:

symbol = pattern.symbol

direction = "LONG" (teaching-only assumption)

strategy_name = "GapAndGoStrategy"

confidence = pattern.confidence (pass-through)

rationale includes:

original pattern rationale

a teaching note about gap-and-go

trader_type = "SCALPER" (teaching routing: gap-and-go → scalper execution path)

Teaching Logs required:

When evaluation starts: how many patterns received

For each pattern:

“matched gap-and-go” or “skipped”

state why (pattern_name)

When an intent is created:

show symbol, direction, trader_type, confidence

Summary line: count of intents created

No other logic (no thresholds here yet). Pure “pattern → intent” mapping.

3) Refactor StrategyRunner into a dispatcher

File: src/strategy/strategy_runner.py

Current StrategyRunner likely translates pattern results directly.

Refactor to:

Instantiate registered strategies inside StrategyRunner.__init__

For now register:

GapAndGoStrategy()

(Optionally keep Momentum as placeholder later, but do NOT implement unless already exists cleanly)

Provide a single method used by Orchestrator:

generate_trade_intents(self, pattern_results: List[PatternResult]) -> List[TradeIntent]

note plural naming: intents

It loops strategies and aggregates results

Required Logs:

list registered strategies by name at boot

for each strategy:

announce evaluation start

number of intents returned

final summary count

Compatibility note:
If Orchestrator currently calls generate_trade_intent(...) singular, either:

Keep the old method as a wrapper calling the new one, OR

Update orchestrator call site (prefer minimal change)

Do not break main execution.

4) Data model checks

File: src/models/data_models.py

Ensure the following exist and are used consistently:

PatternResult(symbol, pattern_name, confidence, rationale)

TradeIntent(symbol, direction, strategy_name, confidence, rationale, trader_type)

If trader_type doesn’t exist, add it with a default like "UNKNOWN" to avoid breaking existing code.

Make sure dataclass defaults don’t cause mutable-default issues (use field(default_factory=list) where needed).

Expected Runtime Behavior (What I should see in console)

Running python src/main.py should show:

Pattern engine generates PatternResults (already done)

StrategyRunner prints:

registered strategies: GapAndGoStrategy

calls GapAndGoStrategy

GapAndGoStrategy prints:

matched symbols (ABC, LMN) for Gap and Go

creates TradeIntents for those

Risk engine then evaluates those intents (already implemented)

Execution engine routes based on trader_type (already implemented)

Storage prints TradeRecord summary

Net result:

Instead of StrategyRunner building intents directly, it delegates to GapAndGoStrategy.

Output Quality Bar

Clear, consistent log prefixes:

[BOOT], [STRATEGY], [STRATEGY:GapAndGo], [TEACH]

Teaching notes are short, not essays.

No diff headers, no plus signs in files (must be clean Python).

Git Workflow (Codex)

Make changes on a branch

Commit with message similar to:

Phase 5.2: add GapAndGoStrategy and refactor StrategyRunner dispatcher

Open PR

After PR Merge — My Local Check

I will:

Pull in PyCharm

Run: python src/main.py

Confirm:

No exceptions

StrategyRunner delegates

GapAndGoStrategy creates intents only for “Gap and Go”

Everything still SIM / teaching-only

Done When

Code compiles

Main runs

GapAndGoStrategy exists + used

StrategyRunner is dispatcher

Logs show the new structure clearly



27_PHASE_5_STEP_5_2_CODEX_INSTRUCTIONS_GAP_AND_GO_STRATEGY.md
Title: STEP 5.2 — Codex Instructions: Implement GapAndGoStrategy (Teaching-First, Deterministic)

================================================================================
OBJECTIVE
================================================================================
Implement the first real, pluggable trading strategy as part of Phase 5.

This step transitions the system from:
- Strategy logic embedded inside StrategyRunner
to:
- StrategyRunner acting as a dispatcher of independent strategy modules.

We will implement:
- A BaseStrategy contract
- A GapAndGoStrategy plugin
- A refactored StrategyRunner that dispatches strategies
- Fully deterministic, SIM-only behavior with teaching-first logs

================================================================================
GUARDRAILS (NON-NEGOTIABLE)
================================================================================
1. NO broker calls (no IBKR, no ib_insync, no networking).
2. NO randomness (no random, no time-based logic).
3. RUN_MODE must remain SIM-safe.
4. Strategy logic must be stateless per cycle.
5. Strategy returns List[TradeIntent], never a single object.
6. Extensive teaching logs explaining WHY decisions occur.
7. Orchestrator and main.py must continue running unchanged.

================================================================================
FILES TO CREATE / MODIFY
================================================================================

CREATE:
1. src/strategy/base_strategy.py
2. src/strategy/gap_and_go_strategy.py

MODIFY:
3. src/strategy/strategy_runner.py
4. src/models/data_models.py (ONLY if required; backward-safe changes only)

DO NOT modify any other modules.

================================================================================
STEP 1 — CREATE BASE STRATEGY CONTRACT
================================================================================
File: src/strategy/base_strategy.py

Purpose:
- Define a minimal shared interface for all strategies.
- Keep StrategyRunner generic and extensible.

Requirements:
- Class BaseStrategy (ABC or simple base class)
- Attribute:
  - name: str
- Method:
  - evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]

Teaching notes to include:
- Why strategies are isolated modules
- Why they are stateless
- Why they consume PatternResults instead of raw scanner data

================================================================================
STEP 2 — IMPLEMENT GAP AND GO STRATEGY
================================================================================
File: src/strategy/gap_and_go_strategy.py

Responsibilities:
- Receive List[PatternResult]
- Filter patterns where pattern_name contains "Gap and Go"
- For each matching pattern, create a TradeIntent with:
  - symbol = pattern.symbol
  - direction = "LONG"
  - strategy_name = "GapAndGoStrategy"
  - confidence = pattern.confidence
  - trader_type = "SCALPER"
  - rationale = pattern.rationale + short teaching note

Rules:
- NO thresholds here
- NO sizing logic
- NO broker logic
- Pure translation: Pattern → TradeIntent

Required Teaching Logs (prefix all with [STRATEGY:GapAndGo]):
- When evaluation starts (number of patterns received)
- For each pattern:
  - Matched → creating TradeIntent
  - Skipped → not a Gap and Go pattern
- Final summary of TradeIntents created

================================================================================
STEP 3 — REFACTOR STRATEGY RUNNER INTO DISPATCHER
================================================================================
File: src/strategy/strategy_runner.py

Old behavior:
- StrategyRunner directly created TradeIntents

New behavior:
- StrategyRunner owns and dispatches strategy modules

Implementation requirements:
- __init__:
  - Instantiate and register strategies in a list
    - GapAndGoStrategy()
- Method:
  - generate_trade_intents(self, pattern_results: List[PatternResult]) -> List[TradeIntent]

Execution flow:
1. Log registered strategies at startup
2. For each strategy:
   - Call strategy.evaluate(pattern_results)
   - Collect returned TradeIntents
3. Return a flat list of all TradeIntents

Backward compatibility:
- If orchestrator calls generate_trade_intent (singular),
  keep a wrapper method that forwards to generate_trade_intents.

Required logs:
- Registered strategy names
- When each strategy evaluation begins
- How many TradeIntents each strategy returns
- Final total TradeIntent count

================================================================================
STEP 4 — DATA MODEL CHECK (MINIMAL)
================================================================================
File: src/models/data_models.py

Ensure existence of:
- PatternResult
- TradeIntent with fields:
  - symbol
  - direction
  - strategy_name
  - confidence
  - rationale
  - trader_type (default to "UNKNOWN" if missing)

Rules:
- Do NOT remove existing fields
- Add defaults only
- Backward compatible only

================================================================================
EXPECTED RUNTIME BEHAVIOR
================================================================================
Running:
python src/main.py

Expected:
- PatternEngine produces PatternResults
- StrategyRunner logs registered strategies
- GapAndGoStrategy creates TradeIntents only for Gap and Go patterns
- RiskEngine evaluates multiple TradeIntents
- ExecutionEngine routes by trader_type
- Storage receives a TradeRecord with all stages populated
- No crashes
- No broker calls
- Deterministic output

================================================================================
GIT / CODEX WORKFLOW
================================================================================
Codex must:
1. Create a new branch
2. Implement all steps above
3. Commit with message:
   "Phase 5.2: add GapAndGoStrategy and refactor StrategyRunner to dispatcher"
4. Open a Pull Request

================================================================================
DEFINITION OF DONE
================================================================================
- Code compiles cleanly
- Main runs end-to-end
- StrategyRunner no longer owns strategy logic
- GapAndGoStrategy is standalone and pluggable
- Multiple TradeIntents flow correctly through risk and execution
- Logs clearly teach WHY decisions occur
