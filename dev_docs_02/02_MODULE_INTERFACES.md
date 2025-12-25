🔌 02_MODULE_INTERFACES.md

Phase 2 — Canonical Module Interfaces (Contracts Only)

PURPOSE OF THIS DOCUMENT

This document defines the interfaces between modules.

It answers:

What functions exist?

What inputs they accept

What outputs they return

What they must print/log

What failures look like

This document defines contracts only.
No implementation, no logic, no broker calls.

If a future implementation violates these interfaces, the implementation is wrong.

GLOBAL INTERFACE RULES (NON-NEGOTIABLE)

Every interface:

has a clear responsibility

accepts explicit inputs

returns explicit outputs

No hidden globals

No side effects beyond declared outputs

Every call:

prints meaningful logs

returns structured data

Errors are returned or raised explicitly — never silent

INTERFACE OVERVIEW

The system exposes the following module interfaces:

ScannerInterface
PatternEngineInterface
StrategyRunnerInterface
RiskEngineInterface
ExecutionEngineInterface
StorageInterface
BrokerInterface


Each interface is defined below.

1️⃣ ScannerInterface
Responsibility

Observe the market and produce ranked, explainable candidates.

Called by

Core Orchestrator

Public Methods
run_scan_cycle() -> list[ScannerResult]

Inputs

None (scanner manages its own data sources internally)

Outputs

List of ScannerResult

Print / Log Contract

One summary header per cycle

One explainable line per symbol

Data quality warnings if applicable

Failure Modes

Data unavailable → return empty list + warning log

Partial data → return results with data_quality_flags

2️⃣ PatternEngineInterface
Responsibility

Evaluate scanner candidates for known patterns.

Called by

Core Orchestrator

Public Methods
evaluate_patterns(scanner_results: list[ScannerResult]) -> list[PatternResult]

Inputs

List of ScannerResult

Outputs

List of PatternResult

Print / Log Contract

Pattern detected logs

Pattern rejected logs with reason

Summary of best candidates

Failure Modes

Missing indicators → flagged in PatternResult

Evaluation failure → detected=False with rationale

3️⃣ StrategyRunnerInterface
Responsibility

Convert pattern evaluations into trade intent or neutrality.

Called by

Core Orchestrator

Public Methods
generate_trade_intent(pattern_results: list[PatternResult]) -> list[TradeIntent]

Inputs

List of PatternResult

Outputs

List of TradeIntent (may be empty)

Print / Log Contract

Strategy decision explanation

Neutral decisions must be logged explicitly

Failure Modes

Conflicting patterns → neutral intent with rationale

Insufficient confidence → no intent produced

4️⃣ RiskEngineInterface
Responsibility

Protect capital and approve or block trade intent.

Called by

Core Orchestrator

Public Methods
evaluate_trade_intent(trade_intent: TradeIntent) -> RiskDecision

Inputs

Single TradeIntent

Outputs

RiskDecision

Print / Log Contract

Risk decision explanation

Explicit log for blocked trades

Failure Modes

Account data missing → BLOCK with rationale

Circuit breaker triggered → BLOCK with flag

5️⃣ ExecutionEngineInterface
Responsibility

Execute risk-approved trades at the broker.

Called by

Core Orchestrator

Public Methods
execute_trade(risk_decision: RiskDecision) -> ExecutionResult | None

Inputs

RiskDecision

Outputs

ExecutionResult if trade attempted

None if trade blocked

Print / Log Contract

Order submission logs

Fill / rejection logs

Broker error explanations

Failure Modes

Broker unavailable → ExecutionResult with error codes

Order rejected → ExecutionResult with rationale

6️⃣ StorageInterface
Responsibility

Persist all system activity for learning and recovery.

Called by

Core Orchestrator

Public Methods
store_trade_record(trade_record: TradeRecord) -> bool

Inputs

TradeRecord

Outputs

Boolean success flag

Print / Log Contract

Confirmation on success

Error logs on failure

Failure Modes

Storage unavailable → error log + False return

Partial write → error flag stored

7️⃣ BrokerInterface (Abstract)
Responsibility

Abstract broker-specific behaviour (IBKR, paper, sim).

Called by

Execution Engine

Public Methods
connect() -> bool
disconnect() -> None
submit_order(order_params) -> broker_order_id
get_order_status(broker_order_id) -> status_info

Inputs

Broker-specific order parameters (wrapped by Execution Engine)

Outputs

Broker identifiers and status info

Print / Log Contract

Connection status

Order acknowledgements

Broker error codes

Failure Modes

Connection failure → explicit error

Order rejection → explicit status

INTERFACE BOUNDARY RULE (CRITICAL)

Interfaces do not import implementations

Implementations must not change interfaces

All modules communicate only via these contracts

STANDALONE REQUIREMENT

Each interface must be implementable in a module that:

can be run standalone

prints meaningful output

demonstrates its contract without other modules

STATUS

Phase: PHASE 2 — Interface & Contracts

Step: 2.2 — Module Interfaces

State: COMPLETE (Initial Canonical Definition)

Next Step: Define print & logging contracts

NEXT ACTION

When ready, say:

“Proceed to STEP 2.3 — Define print & logging contracts”

After Step 2.3 and 2.4, we will be ready to use Codex confidently.