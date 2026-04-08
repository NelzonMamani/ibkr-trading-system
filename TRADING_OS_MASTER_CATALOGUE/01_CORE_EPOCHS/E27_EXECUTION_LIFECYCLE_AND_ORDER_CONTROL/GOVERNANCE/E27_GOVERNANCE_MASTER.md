# E27_EXECUTION_LIFECYCLE_AND_ORDER_CONTROL — GOVERNANCE MASTER

## 1. Epoch identity

**Epoch name:** E27_EXECUTION_LIFECYCLE_AND_ORDER_CONTROL

**Epoch mission:**  
Provide the shared execution lifecycle for all strategies that require broker execution, trade protection, active trade management, exit control, restart recovery, and broker-truth reconciliation.

## 2. Scope

E27 governs the path:

`TradeIntent → ExecutionPlan → Broker Orders → Fills → Position → Management → Exit → Recovery`

It covers:
- order construction
- order attachment structure (entry, stop, target, trail, OCA/bracket semantics)
- lifecycle state transitions
- broker-truth callback interpretation
- position management
- partial fill handling
- duplicate prevention
- restart recovery
- reconciliation and orphan repair / escalation

It does **not** cover:
- scanning
- setup detection
- trigger detection
- initial risk approval logic
- strategy alpha generation

## 3. Design principle

### 3.1 Shared engine, strategy-specific policy
E27 must be shared infrastructure.
Strategies must provide policy, not lifecycle plumbing.

### 3.2 No strategy-managed broker state
No strategy may directly:
- submit broker orders
- manage broker order children
- trail broker stops
- reconcile orphan broker orders
- own restart recovery

Strategies may only emit:
- intent
- stop model preference
- target model preference
- trailing model preference
- session constraints
- scale/management preferences

### 3.3 Broker truth wins
Broker callbacks and snapshots are authoritative for:
- acknowledgement
- working-order state
- fills
- positions

### 3.4 No naked entries
No entry is valid without a defined protection and exit plan, even if some protection is attached after fill under a staged protocol.

## 4. Core responsibilities

### 4.1 ExecutionPlanBuilder
Transforms strategy intent plus risk decision into a broker- and policy-aware execution plan.

### 4.2 OrderControlEngine
Builds broker-ready order structures:
- market or marketable entry
- stop order
- take-profit order
- bracket / OCA semantics
- trailing updates
- partial position child resizing

### 4.3 LifecycleCoordinator
Maintains the canonical state machine for each trade lifecycle.

### 4.4 RecoveryEngine
On restart or reconnect:
- queries broker open orders
- queries positions
- queries executions when available
- rebuilds state
- identifies orphans
- repairs or escalates

### 4.5 ReconciliationAuthority
Produces authoritative verdicts on whether local state matches broker truth.

## 5. Canonical contracts

### 5.1 TradeIntent
Produced by strategies. Must contain enough information to build an execution plan.

### 5.2 ExecutionPolicy
Strategy-provided policy adapter consumed by E27.

### 5.3 ExecutionPlan
Concrete plan including:
- entry order specification
- initial stop
- first target
- trailing configuration
- scale rules
- session behavior
- recovery metadata

### 5.4 LifecycleRecord
Persistent canonical record of:
- parent order id
- child order ids
- fill quantities
- average prices
- stop/target state
- trail state
- pause state
- recovery markers

## 6. Mandatory invariants

1. **Trigger-to-intent continuity** must be preserved before E27 starts.
2. **Intent-to-plan continuity** must never fail silently.
3. **No naked entries**: every entry must have an exit plan.
4. **Broker-truth authority**: execDetails/openOrder/orderStatus/positions override local assumptions.
5. **Idempotent recovery**: restart must not duplicate broker exposure.
6. **Duplicate submission blocking** must remain active.
7. **Protection must resize on partial fills**.
8. **Exit signals override trailing looseness** when higher-priority failure conditions appear.

## 7. Priority hierarchy for active trade management

From highest to lowest authority:
1. Hard stop
2. >50% retrace failure
3. red-volume dominance
4. level rejection / failed breakout
5. trailing stop
6. time-based or discretionary cleanup

## 8. Order structure doctrine

E27 must support, at minimum:
- single market/marketable entries
- bracket entry + stop + target
- synthetic attachment fallback when broker-native attachment is not used
- scale-out orders
- single remainder trailing control

## 9. Strategy integration doctrine

All strategies requiring active trade management must consume E27 through an `ExecutionPolicy` profile.

Ross is the first consumer profile but not the only consumer.

## 10. Minimum live-readiness condition for E27

E27 is not live-ready until all are verified:
- entry fill
- stop execution
- target execution
- trailing stop update
- duplicate prevention
- restart recovery
- reconciliation of live working orders
- orphan handling
