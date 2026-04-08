# E27 State Machine and Recovery

## 1. Canonical lifecycle states

```text
INTENT_CREATED
→ PLAN_BUILT
→ ENTRY_SUBMITTING
→ ENTRY_WORKING
→ ENTRY_PARTIALLY_FILLED
→ ENTRY_FILLED
→ POSITION_OPEN
→ POSITION_MANAGED
→ EXIT_SUBMITTING
→ EXIT_WORKING
→ EXIT_FILLED
→ POSITION_CLOSED
→ RECONCILED
```

## 2. Symbol management overlays

```text
ACTIVE
→ WARNING
→ PAUSED
→ RE_ARMED
```

These overlays coexist with broker/order lifecycle states.

## 3. Recovery goals

On restart / reconnect, E27 must:
1. fetch open orders
2. fetch positions
3. fetch executions where possible
4. rebuild lifecycle records
5. detect orphan conditions
6. repair or escalate

## 4. Orphan classes

### 4.1 Orphan position
Position exists but no local lifecycle record.

### 4.2 Orphan protective order
Stop/target exists but parent no longer active or known.

### 4.3 Naked position
Position exists without valid protection plan.

### 4.4 Duplicate working order
New intent attempts submission while broker already shows active working order for the same exposure.

## 5. Recovery decision table

| Condition | Verdict | Action |
|---|---|---|
| open position + valid protection | healthy | rebuild and continue |
| open position + no protection | critical | attach protection / escalate |
| active entry order + no local state | orphan order | rebuild local state |
| duplicate working order detected | safe block | suppress resubmission |
| filled parent + children missing | incomplete protection | repair immediately |

## 6. Broker truth rules

Authoritative sources:
- openOrder
- orderStatus
- execDetails
- position / positionEnd
- openOrders snapshots
- executions snapshots

Local DB may guide recovery, but broker data wins.

## 7. Required persistent fields

Each lifecycle record should store at least:
- symbol
- strategy_name
- setup_family
- parent_order_id
- stop_order_id
- target_order_id
- OCA/group id
- intent id
- execution plan id
- filled_qty
- avg_fill_price
- realized PnL
- trail anchor
- current state
- pause state
- broker status
- timestamps

## 8. Restart invariant

Restarting the system must never:
- create duplicate exposure
- lose knowledge of open risk
- forget pending protection
- assume fills without broker confirmation
