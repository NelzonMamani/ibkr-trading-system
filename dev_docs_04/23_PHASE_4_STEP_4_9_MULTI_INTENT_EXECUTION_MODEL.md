Title: STEP 4.9 — Multi-Intent, Multi-Trader Execution Model (Teaching-First, Scalable)

Content:

Why this step exists (context)

You have now successfully fixed the orchestrator loop and verified that:

the system runs continuously

multiple scanner candidates flow through

multiple patterns → strategies → risk decisions are produced

nothing breaks under repetition

the architecture is observable and safe

At this point, the system is already multi-trade capable in data, but not yet explicit in intent ownership or execution routing.

This step clarifies and formalises something you asked explicitly:

“multi trade? scalper, algo, quant trader? per ticker? per thread?”

This step answers that architecturally, without adding dangerous complexity yet.

Core clarification (very important)

There are THREE different ‘multi’ concepts, and we must separate them cleanly.

1️⃣ Multi-symbol (already achieved ✅)

Scanner returns many symbols

System processes them in a single cycle

This is batch multi-symbol, not concurrency

✅ You already have this.

2️⃣ Multi-intent (this step introduces it explicitly)

One symbol can produce:

multiple TradeIntents

from different strategies

at the same time

Example:

ABC:

Gap-and-Go (scalp)

Opening Range Breakout (momentum)

VWAP reclaim (mean reversion)

These are parallel ideas, not mutually exclusive.

This step makes that explicit in the data model and execution flow.

3️⃣ Multi-trader (future, NOT threads yet)

This does NOT mean threads yet.

It means:

each TradeIntent declares who owns it

execution engine can later route:

scalper

intraday algo

swing algo

quant/stat model

Think logical traders, not Python threads.

Threads/processes come MUCH later.

What STEP 4.9 actually does

We do not add concurrency yet.

We do this instead:

A) TradeIntent gains trader_type

Example values:

"SCALPER"

"MOMENTUM"

"MEAN_REVERSION"

"QUANT"

"MANUAL"

This answers:

“who is responsible for this idea?”

B) Orchestrator treats TradeIntents as FIRST-CLASS

Instead of:

“one risk decision”

“one execution”

We now formalise:

List[TradeIntent]

List[RiskDecision]

List[ExecutionResult]

You are already almost there — this step just locks the rule.

C) Execution engine becomes a router (still teaching-only)

Execution engine does NOT execute yet.

It prints:

which trader would handle it

which symbol

which direction

why

Example log:

[EXECUTION] Routing intent: ABC LONG trader=SCALPER
[EXECUTION] Routing intent: ABC LONG trader=MOMENTUM
[EXECUTION] Routing intent: LMN LONG trader=SCALPER


This prepares:

per-strategy execution logic later

per-broker later

per-risk profile later

What this step does NOT do (important)

❌ No threading
❌ No async
❌ No multiprocessing
❌ No live orders
❌ No IBKR calls

Those come after Phase 5.

Files involved (expected)

src/models/data_models.py

src/strategy/strategy_runner.py

src/core/orchestrator.py

src/execution/execution_engine.py

(No new files yet.)

Teaching outcome (why this matters)

After this step, you will be able to say:

✔ “The system can reason about multiple trade ideas per symbol”
✔ “Each idea knows which trader it belongs to”
✔ “Execution is cleanly separated from strategy logic”
✔ “Scaling later will not break architecture”

This directly satisfies your requirement:

“the structure allocates flexibility and still works robustly”

What comes immediately AFTER this (preview)

STEP 4.10 — Execution Safety Gate

execution engine refuses trades if:

trader type is disabled

risk decision says allowed=False

RUN_MODE != LIVE

this is your last safety wall

What you should do now

Say one of the following:

“Proceed — create STEP 4.9 Codex instructions”

or “Explain STEP 4.9 with a diagram before coding”

We are exactly on track.
This is textbook-clean system engineering.