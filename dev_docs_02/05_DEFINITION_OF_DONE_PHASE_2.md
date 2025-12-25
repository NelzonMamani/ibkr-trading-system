✅ 05_DEFINITION_OF_DONE_PHASE_2.md

Phase 2 — Interface & Contracts Completion Criteria

PURPOSE OF THIS DOCUMENT

This document defines the binary, objective criteria for declaring PHASE 2 — Interface & Contracts complete.

It exists to:

prevent premature skeleton coding

ensure Codex work is safe and constrained

guarantee Phase 3 becomes mechanical

If all items are satisfied, Phase 2 is complete.
If any item is missing, Phase 2 remains active.

WHAT “DONE” MEANS IN PHASE 2

Phase 2 is complete when:

The system has a fully defined shared language (data models) and fully defined module interfaces, including logging and recovery expectations — such that implementation cannot drift without being obvious.

REQUIRED DOCUMENTS (ALL MUST EXIST)

The following files must exist in dev_docs_02/:

01_CORE_DATA_MODELS.md

02_MODULE_INTERFACES.md

03_PRINT_AND_LOGGING_CONTRACTS.md

04_ERROR_AND_RECOVERY_CONTRACTS.md

05_DEFINITION_OF_DONE_PHASE_2.md (this file)

☐ All present
☐ Correctly named
☐ Stored under dev_docs_02/

CONTRACT CONSISTENCY CHECKS (NON-NEGOTIABLE)
1️⃣ Data Model Completeness

☐ The six canonical models exist and are defined:

ScannerResult

PatternResult

TradeIntent

RiskDecision

ExecutionResult

TradeRecord

☐ Each model includes:

purpose

producer module

consumer modules

conceptual field groups

2️⃣ Interface Completeness

☐ Each module interface exists and is defined:

ScannerInterface

PatternEngineInterface

StrategyRunnerInterface

RiskEngineInterface

ExecutionEngineInterface

StorageInterface

BrokerInterface

☐ Each interface includes:

responsibility

public methods

required inputs/outputs

failure modes

print/log requirements

3️⃣ Logging Contract Completeness

☐ Standard log prefixes exist and are authoritative
☐ Each module’s required logs are defined
☐ “No action” decisions must be logged (no silent neutrality)
☐ Error logs must include what/why/next

4️⃣ Recovery Contract Completeness

☐ Error categories are defined and fixed
☐ Recovery modes are defined (NORMAL/DEGRADED/SAFE_STOP/RECOVERY)
☐ Module-specific recovery behaviours are defined
☐ Errors and recovery events must be storable in TradeRecord

PHASE 3 READINESS CHECK (THE REAL TEST)

Phase 2 is only complete if the answer is YES to all:

☐ Could a developer create skeleton files without guessing?
☐ Could Codex generate skeletons safely using only these docs?
☐ Are module boundaries and dependencies still respected?
☐ Would a contract violation be obvious immediately?

If any answer is “no”, Phase 2 is not done.

EXPLICIT NON-REQUIREMENTS (IMPORTANT)

Phase 2 does NOT require:
❌ Python code
❌ Skeleton modules
❌ IBKR connectivity
❌ Strategy logic
❌ Pattern implementations
❌ Database schema implementation

Those begin in Phase 3 and Phase 4.

OFFICIAL TRANSITION RULE

You may enter Phase 3 only when:

All requirements above are satisfied

You explicitly declare:

“PHASE 2 — COMPLETE. ENTER PHASE 3.”

No silent transitions.

STATUS

Phase: PHASE 2 — Interface & Contracts

Completion State: READY FOR REVIEW

WHEN READY

Say exactly:

“PHASE 2 — COMPLETE. ENTER PHASE 3.”

Phase 3 is where Codex becomes a power tool — because the rails are now installed.