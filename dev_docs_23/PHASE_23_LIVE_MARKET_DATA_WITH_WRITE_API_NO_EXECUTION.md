PHASE_23_LIVE_MARKET_DATA_WITH_WRITE_API_NO_EXECUTION.md
# PHASE 23 — Live Market Data with IBKR Write API (Execution Still Disabled)

## Objective
Enable IBKR API write access strictly for market data and metadata requests
while preserving a hard internal ban on all order execution.

This phase MUST NOT allow trades.

## Required Changes

### 1. Execution Lock Must Be Absolute
Even if IBKR write API is enabled:
- ExecutionEngine MUST refuse all order submissions
- Broker adapters MUST NOT be instantiated
- Any attempt to place an order MUST raise immediately

Execution must remain disabled unless RUN_MODE == LIVE_MICRO.

### 2. Separate IBKR Permissions from Execution
IBKR_READONLY_ENABLED must no longer be used to infer execution safety.

Introduce or enforce:
- IBKR_API_WRITE_ALLOWED = True
- EXECUTION_ENABLED = False

Execution safety must be enforced internally, not delegated to IBKR UI.

### 3. Market Data Requests Allowed
Allow:
- reqMktData
- reqScannerSubscription
- reqContractDetails
- reqHistoricalData
- reqOpenOrders (read-only inspection)
- reqCompletedOrders (read-only inspection)

These must NOT trigger kill-switch shutdown.

### 4. Kill-Switch Refinement
Kill-switch MUST trigger only on:
- placeOrder
- cancelOrder
- modifyOrder
- bracket / OCA submission

It MUST NOT trigger on:
- open orders query
- completed orders query
- account summary reads

### 5. Validation Logging (Mandatory)
Startup logs MUST clearly show:
- IBKR API WRITE: ENABLED
- EXECUTION: HARD DISABLED
- ORDER ROUTING: BLOCKED
- MARKET DATA: LIVE IBKR

### 6. Safety Guarantee
Add an invariant check:
If any order object is constructed while EXECUTION_ENABLED=False → raise and shutdown.

## Acceptance Criteria
- IBKR no longer disconnects
- Live scanner runs
- Real tickers appear
- No orders sent
- No IBKR warnings about write access

END