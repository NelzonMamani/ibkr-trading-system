24_PHASE_4_STEP_4_9_CODEX_INSTRUCTIONS_MULTI_INTENT_EXECUTION_MODEL.md
Title: STEP 4.9 Codex Instructions — Multi-Intent + Trader Routing (Teaching-First, No Concurrency)

Content:

0) Objective (read first)

Upgrade Phase 4 teaching system so it can safely handle multiple TradeIntents and route them by trader_type (SCALPER/MOMENTUM/etc.) without adding threads, async, or real broker execution.

This is structure + contracts + prints, not trading logic.

1) Scope (what to change)

Modify only these files:

src/models/data_models.py

src/strategy/strategy_runner.py

src/core/orchestrator.py

src/execution/execution_engine.py

Do not create new modules unless absolutely necessary.

2) Non-negotiable rules

Keep it deterministic (no randomness).

Keep it teaching-first (clear logs).

Keep it safe (no broker calls).
-(relates to earlier “diff header” issue)

Ensure every file remains valid Python (no patch headers, no diff --git, no + lines).

Maintain existing Phase 4 runtime output style.

3) Data model updates (data_models.py)
3.1 Add/extend TradeIntent

Ensure TradeIntent includes:

symbol: str

direction: str # "LONG" | "SHORT" | "NEUTRAL"

strategy_name: str

confidence: float

rationale: str

trader_type: str # NEW: e.g. "SCALPER" | "MOMENTUM" | "QUANT" | "MANUAL"

Add teaching comments explaining:

why trader_type exists

why it’s not threads yet

3.2 Add ExecutionResult dataclass (if missing)

Create a small deterministic structure:

symbol: str

trader_type: str

attempted: bool

status: str # "SKIPPED" | "SIMULATED"

rationale: str

This is only for prints + storing in TradeRecord.

3.3 Update TradeRecord

Ensure TradeRecord can store:

strategy_output: list (already storing intents)

risk_output: list (risk decisions list)

execution_output: list (NOW list of ExecutionResult instead of None/single)

Update __repr__ / dataclass printing behavior if needed so logs remain readable.

4) StrategyRunner updates (strategy_runner.py)
4.1 Output remains List[TradeIntent]

Guarantee generate_trade_intent(pattern_results) -> List[TradeIntent].

4.2 Assign trader_type deterministically

For teaching purposes:

If pattern name contains "Gap and Go" → trader_type="SCALPER"

If pattern name contains "Momentum" → trader_type="MOMENTUM"

Else → trader_type="MANUAL"

Log clearly:

which trader_type was assigned

why that mapping exists (teaching)

No randomness.

5) Orchestrator updates (core/orchestrator.py)
5.1 Risk evaluation must loop over intents

Current bug class we already hit: list vs object.

Implement explicit loop:

trade_intents: List[TradeIntent]

risk_decisions: List[RiskDecision] (skip None)

Only pass single intent to risk_engine.evaluate_trade_intent(intent).

Add teaching log:

“Risk engine will evaluate N trade intents.”

5.2 Execution must loop over risk decisions

execution_results: List[ExecutionResult]

For each RiskDecision:

call execution_engine.execute_trade(risk_decision)

append returned ExecutionResult if not None

Add teaching log:

“Execution engine will process N risk decisions.”

5.3 TradeRecord should store lists

Ensure:

risk_output is a list

execution_output is a list

Log a compact summary at end of cycle:

count of candidates

count of patterns

count of intents

count of allowed risk decisions

count of execution results

6) Execution engine updates (execution_engine.py)
6.1 Change input contract

execute_trade(risk_decision: RiskDecision) -> ExecutionResult

6.2 Route by trader_type

Assume RiskDecision includes symbol (already) and either:

contains trader_type directly, OR

includes a rationale field that references it, OR

we can extend RiskDecision to include trader_type: str (preferred)

Preferred approach: extend RiskDecision dataclass to include trader_type: str so execution can route cleanly.

Execution engine logs:

“Routing intent: SYMBOL DIRECTION trader=TRADER_TYPE”

“SIM mode: no broker call; returning simulated result”

Return ExecutionResult(...status="SIMULATED"...attempted=True...)

7) Acceptance criteria (how we verify)

After merge + pull, running python src/main.py should:

run continuous cycles

show scanner candidates

show pattern results

show trade intents with trader_type in prints

risk evaluates each intent (no list/object crash)

execution logs show routing per trader_type

TradeRecord print includes execution_output list (not None)

No exceptions.

8) GitHub workflow instruction (Codex)

When done:

create a PR named: STEP 4.9 — Multi-intent trader routing

ensure PR touches only the four files above

End.

did you get stuck?      where are the instructions? 

24_PHASE_4_STEP_4_9_CODEX_INSTRUCTIONS_MULTI_INTENT_EXECUTION_MODEL.md
Title: STEP 4.9 Codex Instructions — Multi-Intent + Trader Routing (Teaching-First, No Concurrency)

Content:

Copy/paste the block below directly into Codex:

YOU ARE WORKING IN: PHASE 4 — Minimal Live-Capable System (Teaching-First)

STEP 4.9 OBJECTIVE
Upgrade the Phase 4 teaching system so it can safely handle MULTIPLE TradeIntents and route them by trader_type (SCALPER/MOMENTUM/QUANT/MANUAL) WITHOUT threads/async and WITHOUT real broker execution.
This is structure + contracts + prints, not trading logic.

NON-NEGOTIABLE RULES
- Deterministic: no randomness, no external calls.
- Teaching-first: clear logs for every step.
- Safe: no broker calls, no ib_insync usage, no IBKR connections.
- Valid Python only: NO patch headers, NO 'diff --git', NO leading '+' lines.
- Keep changes minimal and limited to the files listed below.

FILES YOU MAY MODIFY (ONLY THESE 4)
1) src/models/data_models.py
2) src/strategy/strategy_runner.py
3) src/core/orchestrator.py
4) src/execution/execution_engine.py

TASK A — Update data models (src/models/data_models.py)
A1) Ensure TradeIntent includes:
- symbol: str
- direction: str  # LONG/SHORT/NEUTRAL
- strategy_name: str
- confidence: float
- rationale: str
- trader_type: str  # NEW: SCALPER/MOMENTUM/QUANT/MANUAL
Add teaching comments explaining why trader_type exists (routing), and why we are NOT adding concurrency yet.

A2) Create a new dataclass ExecutionResult (if it does not exist) with:
- symbol: str
- trader_type: str
- attempted: bool
- status: str  # SKIPPED or SIMULATED
- rationale: str

A3) Ensure TradeRecord stores LIST outputs:
- scanner_output: list
- pattern_output: list
- strategy_output: list  # list[TradeIntent]
- risk_output: list      # list[RiskDecision]
- execution_output: list # list[ExecutionResult]
Make sure TradeRecord prints nicely in console.

TASK B — Strategy runner emits trader_type (src/strategy/strategy_runner.py)
B1) generate_trade_intent(...) MUST return List[TradeIntent] always.
B2) Assign trader_type deterministically:
- if pattern_name contains "Gap and Go" -> trader_type="SCALPER"
- elif pattern_name contains "Momentum" -> trader_type="MOMENTUM"
- else -> trader_type="MANUAL"
B3) Log clearly for each intent:
- symbol, strategy_name, confidence, trader_type, and the reason for the mapping (teaching).

TASK C — Orchestrator loops properly (src/core/orchestrator.py)
C1) Risk stage MUST evaluate each TradeIntent individually:
- trade_intents: List[TradeIntent]
- risk_decisions: List[RiskDecision]
Loop over trade_intents and call:
  self.risk_engine.evaluate_trade_intent(intent)
Avoid passing a LIST into risk_engine (we previously saw AttributeError: 'list' object has no attribute 'symbol').

C2) Execution stage MUST loop over risk_decisions and call:
  self.execution_engine.execute_trade(risk_decision)
Collect a list of ExecutionResult.

C3) End-of-cycle teaching summary log (single compact block):
- count(scanner candidates)
- count(pattern results)
- count(trade intents)
- count(risk decisions)
- count(execution results)

C4) TradeRecord must store risk_output as LIST and execution_output as LIST.

TASK D — Execution engine routes by trader_type (src/execution/execution_engine.py)
D1) execute_trade(risk_decision) MUST return ExecutionResult.
D2) Route by trader_type:
Preferred: extend RiskDecision to include trader_type: str (ONLY if RiskDecision lives in data_models.py; if RiskDecision is elsewhere, do NOT create new files — instead infer trader_type via getattr with fallback "MANUAL").
D3) In SIM mode: do NOT execute broker orders. Return:
ExecutionResult(symbol=..., trader_type=..., attempted=True, status="SIMULATED", rationale="Teaching-only: routed to trader_type, no broker call in SIM.")

D4) Log:
- routing decision (symbol, trader_type)
- SIM safety message

ACCEPTANCE CRITERIA
After the changes, running:
  python src/main.py
should:
- show scanner -> patterns -> strategy (with trader_type) -> risk (loops over intents) -> execution (loops over risk decisions) -> storage
- have NO exceptions
- show execution_output as a list in TradeRecord print

DELIVERABLE
Create a PR titled:
"STEP 4.9 — Multi-intent trader routing"
Only modify the 4 files listed above.


After Codex finishes:

Click Create PR

Merge it on GitHub (if checks pass / no conflicts)

In PyCharm: Git → Pull

Run src/main.py and paste the console output here if anything breaks.