# Bull Flag / Micro Pullback relationship

Project policy approved explicitly on 7 October 2026, for offline implementation and verification. This is not a universal Ross rule and does not establish Paper readiness. Accepted base: `0cde208452702c0408bc0c9d085134494fc1b822` (PR1102).

## Canonical ownership

| Concern | Before | After |
|---|---|---|
| Bull Flag | `setup_engine/setup_families/momentum.py::BullFlagPattern` | `setup_engine/setup_families/bull_flag.py::BullFlagPattern`; momentum module remains a compatibility import |
| Micro Pullback | `momentum.py::MicroPullbackPattern` and common `detect_micro_pullback` | `setup_engine/setup_families/micro_pullback.py::MicroPullbackPattern`; existing confirmed-continuation and armed-readiness behaviors are explicit methods; common function delegates |
| Registration | Shared setup registry and Ross registry | Same registries and IDs; no duplicate registration |
| Parent/child and management state | Separate detectors, no durable relationship | Existing `execution/trade_management_engine.py::TradeManagementEngine`, persisted by existing `StorageEngine` lifecycle store |
| Trigger / intent | Shared trigger registry and Ross strategy | Same route; relationship Bull Flag delegates confirmation to the Micro Pullback trigger on the recorded closed refinement event |
| Risk / submission / protection | RiskEngine / ExecutionEngine / PostFillLifecycleEngine | Same owners; context and approved stop survive the handoffs; no second management engine |

All paths above are relative to `src/`. Standalone behavior and compatibility imports remain. Formation is non-entry context; only a confirmed same-security child can supply relationship entry permission. Positive supplied conId identifies the security, not an issuer. Original aware timestamps and PRESENT timeframe provenance are required; forming or fabricated bars cannot qualify. Existing active session, input, catalyst and risk gates remain. The draft session table is not adopted as new policy.

## Explicit numerical policy

The structural risk-approved stop protects actual filled quantity. Initial order must be terminal and reconciled before freezing E0 (actual weighted-average fill), S0 (original stop), positive R0=E0-S0 and E0+2R0. At that milestone, reduce floor(half of confirmed available quantity); a one-share position exits one. A durable reservation tracks cumulative partial executions and consumes the milestone once. A cancelled partial can resume only its unfilled balance following reconciliation.

Existing structural, trailing and failure exits remain eligible before the milestone. A failure cancels pending exposure/profit orders once and waits for terminal callback facts and reconciliation before sizing its exit. Cancellation submission is not fill truth. There is no automatic 1R partial or second fixed 25% partial. Adds and stop changes never move E0/R0/milestone or clear consumption.

A fresh-child add is floor(current confirmed quantity/4), never rounded up. Existing RiskEngine approval, pending reservations, quantity/capital caps, no averaging down and maximum three logical adds apply. The operational one-share cap is unchanged: its add quantity is zero. Larger quantities in tests are isolated policy fixtures, not operational permission.

## State and recovery

Canonical lifecycle persistence records parents, consumed events, initial fill notional, immutable risk reference, action reservations and executed quantities before dispatch. Cached IBKR order-status facts are consumed on the execution thread without new broker requests. Aggregate protection and the active-trade registry use confirmed cumulative fills, not requested size. No automatic retry can duplicate a relationship action.

Restored state is unreconciled. Recovery binds the retained broker stop-order identity, quantity and original-stop constraint to the existing recovered protection. Missing/ambiguous protection blocks the plan. Fresh canonical broker position/open-order truth must match the security conId, quantities and pending reservations before discretionary exposure/profit actions resume. Missing callback or snapshot evidence remains a reconciliation blocker, never invented success. The existing global recovery, execution and risk gates remain authoritative.

## Offline acceptance

`tests/test_ross_bullflag_micro_boundaries.py` covers owner compatibility, standalone behavior, formation-only evidence, mode exclusions, metadata/structural stop handoff and actual-fill semantics. `tests/test_ross_bullflag_micro_management.py` exercises real registry -> selected setup -> production trigger -> TradeIntent -> real RiskEngine -> in-memory execution -> installed protection, plus cumulative callbacks, parent invalidation, missing/stale inputs, event consumption, add floors/caps, fixed original 2R, partial cancellation, failure preemption, reentry, SQLite restart and recovered stop binding.

Synthetic fixed-clock candles, in-memory execution providers and broker doubles are labelled fixtures. They do not prove natural opportunities, broker acceptance, news coverage or trading readiness. No operational capture, broker connection or provider lookup is part of this verification.

PAPER_READY=NO
PAPER_READINESS_GATE=FAIL
