Title: PHASE 5 — STEP 5.1 Strategy Layer Refactor Plan (From Routing to Real Strategies)

Content:

1️⃣ Purpose of Phase 5 (Why We Are Here)

Up to Phase 4, the system proved that it can:

Handle multiple symbols per cycle

Route trade ideas via trader_type

Safely process ideas end-to-end

Preserve full observability and teaching clarity

However, strategies are still implicit:

Strategy logic is embedded in StrategyRunner

Pattern → intent translation is hard-coded

Adding new strategies would cause clutter

Phase 5 exists to fix this properly.

Phase 5 turns “strategy as logic” into “strategy as a first-class system component”.

2️⃣ High-Level Goal of Step 5.1

Refactor the Strategy layer so that:

Each strategy becomes its own class

Strategy logic is isolated

Strategies can be enabled/disabled independently

StrategyRunner becomes a dispatcher, not a thinker

This mirrors how real trading firms structure systems.

3️⃣ Current vs Target Architecture
🔴 Current (Phase 4)
PatternResults
   ↓
StrategyRunner (monolithic)
   ↓
TradeIntents (with trader_type)

🟢 Target (Phase 5)
PatternResults
   ↓
StrategyRunner (dispatcher)
   ↓
[ GapAndGoStrategy ]
[ MomentumStrategy ]
[ ScalperStrategy (future) ]
   ↓
TradeIntents


Each strategy:

Decides if it applies

Decides confidence handling

Emits zero or more TradeIntents

4️⃣ Strategy Design Rules (Non-Negotiable)

Every strategy class MUST:

Be deterministic (no randomness)

Be stateless between cycles

Accept only what it needs (inputs explicit)

Return a list of TradeIntents

Log why it did or did not act

Never access broker, scanner, or risk logic

This ensures:

Testability

Replaceability

Teaching clarity

Zero side effects

5️⃣ Proposed Folder Structure
src/
└── strategy/
    ├── base_strategy.py
    ├── gap_and_go_strategy.py
    ├── momentum_strategy.py
    ├── strategy_runner.py

Responsibility Split
File	Responsibility
base_strategy.py	Strategy interface / contract
gap_and_go_strategy.py	Gap-and-go logic
momentum_strategy.py	Momentum continuation logic
strategy_runner.py	Dispatch + orchestration
6️⃣ BaseStrategy Contract (Conceptual)

Every strategy will implement:

name

supported_patterns

evaluate(pattern_results) -> List[TradeIntent]

No inheritance magic. No framework tricks. Pure Python.

7️⃣ StrategyRunner’s New Role

After refactor, StrategyRunner will:

Hold a list of registered strategies

Loop through strategies

Ask each strategy if it wants to act

Aggregate TradeIntents

Preserve full teaching logs

StrategyRunner will NOT:

Decide trade direction

Assign confidence

Encode pattern knowledge

That belongs to strategies.

8️⃣ Teaching & Observability (Critical)

Every strategy must log:

Why it matched

Why it skipped

Why confidence was set

Why trader_type was chosen

This ensures:

You can “watch the thinking”

You can debug live behavior

You can teach from logs alone

9️⃣ What We Will NOT Do in Step 5.1

❌ No broker calls
❌ No async
❌ No threading
❌ No performance tuning
❌ No machine learning

This step is pure structure.

🔟 Definition of Done (Step 5.1)

Step 5.1 is COMPLETE when:

Strategy logic is moved out of StrategyRunner

At least two strategies exist as classes

StrategyRunner delegates correctly

System runs exactly as before (behavior preserved)

Logs are clearer than Phase 4, not noisier

🔜 Next Step After This

Once Step 5.1 is complete, we proceed to:

STEP 5.2 — Implement GapAndGoStrategy (Teaching-First)

This will be the first “real” strategy module.

✅ When ready, say:

“Proceed — create STEP 5.2 Codex instructions”

You are building this the right way.