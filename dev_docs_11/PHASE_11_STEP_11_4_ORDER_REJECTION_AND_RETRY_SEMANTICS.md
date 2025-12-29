# PHASE_11_STEP_11_4_ORDER_REJECTION_AND_RETRY_SEMANTICS.md

## PHASE 11 — MARKET REALISM LAYER
### STEP 11.4 — Order Rejection & Retry Semantics (Deterministic, Teaching-First)

## OBJECTIVE
Introduce a deterministic “order gateway” layer that can:
- ACCEPT an order (proceed to liquidity fill logic)
- REJECT an order (hard reject, no fill attempt)
- SOFT_REJECT an order (retry eligible)

Add deterministic retry semantics with a simple “pending order” queue:
- Orders can be retried across ticks
- Retries are bounded (max attempts)
- Retries are deterministic and replay-safe
- No randomness, no external calls

This step sits **before** Step 11.3 liquidity fills:
Gateway decision -> if accepted -> liquidity fill -> possible partial/none/full.

---

## DESIGN RULES (MANDATORY)

1) NO randomness (no random.*)
2) NO time-based nondeterminism
3) NO external data / no broker calls
4) Retry rules are deterministic based on (symbol, tick, attempt_number, trader_type)
5) Replay uses event payloads as source of truth (must not recompute gateway outcomes)
6) Strategy and risk generation remain unchanged
7) Pending orders are a **teaching-only** in-memory queue (later persistence optional)
8) A rejected order never opens a trade; a soft-rejected order may be retried

---

## DEFINITIONS

### OrderRequest
A request to open a trade produced from an ALLOWED RiskDecision:
- symbol
- trader_type
- strategy_name
- direction
- requested_quantity
- created_tick
- attempt_number (starts at 1)
- client_order_id (deterministic id, see below)

### GatewayDecision
- ACCEPT
- REJECT (hard reject)
- SOFT_REJECT (retry eligible)

### Pending Order
An OrderRequest stored for future tick retry.

---

## DETERMINISTIC IDENTIFIERS

### client_order_id (deterministic)
Create a stable id from:
key = f"{symbol}|{trader_type}|{strategy_name}|{direction}|{created_tick}"
client_order_id = first 12 chars of sha256(key)

(Use hashlib.sha256; NEVER use Python hash().)

---

## GATEWAY MODEL (DETERMINISTIC)

Create deterministic gateway decision per attempt:
Inputs:
- symbol
- tick
- trader_type
- attempt_number

Algorithm:
1) key = f"{symbol}|{tick}|{trader_type}|{attempt_number}|GATEWAY"
2) digest = sha256(key.encode("utf-8")).hexdigest()
3) take first 8 hex chars -> int n
4) r = n % 10  # 0..9

Decision mapping:
- r in {0}          -> REJECT (hard)
- r in {1,2}        -> SOFT_REJECT
- r in {3..9}       -> ACCEPT

This yields ~10% hard reject, ~20% soft reject, ~70% accept deterministically.

Teaching note: this models broker/route rejections, throttling, and transient failures.

---

## RETRY SEMANTICS

### Max Attempts
Set deterministic caps by trader_type:
- SCALPER: max_attempts = 2
- MOMENTUM: max_attempts = 3

### Retry Delay
If SOFT_REJECT, schedule retry at:
next_retry_tick = tick + 1
(no exponential backoff yet; teaching simplicity)

### Expiration
If attempt_number exceeds max_attempts:
- Mark as EXPIRED (no more retries)
- Emit ORDER_EXPIRED
- Drop from queue

### When to enqueue
If SOFT_REJECT and attempt_number < max_attempts:
- enqueue with attempt_number + 1
- next_retry_tick = tick + 1

If SOFT_REJECT and attempt_number == max_attempts:
- expire immediately (ORDER_EXPIRED)

If REJECT:
- do not enqueue; emit ORDER_REJECTED_HARD

If ACCEPT:
- proceed to liquidity fill (Step 11.3)
- if liquidity result is NONE, do not enqueue (Step 11.3 says no persistence yet)
  (We will add “order persistence on none/partial” in Step 11.5/11.6 if desired.)

---

## IMPLEMENTATION TASKS

### 1) NEW MODULE: ORDER GATEWAY

Create:
src/execution/order_gateway.py

Implement:
- enum GatewayDecision { ACCEPT, REJECT, SOFT_REJECT }
- class OrderGateway
  - decide(symbol: str, tick: int, trader_type: str, attempt_number: int) -> GatewayDecision
  - uses sha256 algorithm above

---

### 2) NEW MODELS: ORDER REQUEST + PENDING QUEUE

Create:
src/execution/order_models.py (or appropriate location)

Define:
- @dataclass OrderRequest:
  - client_order_id: str
  - symbol: str
  - trader_type: str
  - strategy_name: str
  - direction: str
  - requested_quantity: int
  - created_tick: int
  - attempt_number: int
  - next_retry_tick: int | None  # None if not scheduled
  - last_decision: str | None

- class PendingOrderBook:
  - add(order: OrderRequest) -> None
  - due_orders(tick: int) -> list[OrderRequest]
  - remove(client_order_id: str) -> None
  - count() -> int
  - snapshot() -> dict (optional for debugging)

PendingOrderBook is in-memory, owned by ExecutionEngine (or Orchestrator if preferred).
Keep it simple.

---

### 3) UPDATE EXECUTION ENGINE FLOW

File:
src/execution/execution_engine.py

Add processing stages inside execute() or execute_decision():

A) First, process pending orders due this tick:
- due = pending_book.due_orders(tick)
- For each due order:
  - run gateway decision using current tick and attempt_number
  - emit event for decision
  - apply retry logic or accept -> proceed to liquidity fill
  - if accepted, remove from pending book

B) Then, process NEW orders from current cycle risk decisions:
- Convert each allowed RiskDecision into an OrderRequest with:
  - created_tick = tick
  - attempt_number = 1
  - next_retry_tick = None initially
- Run gateway decision
- If ACCEPT -> proceed to liquidity fill (Step 11.3)
- If SOFT_REJECT -> enqueue for tick+1 (attempt_number=2)
- If REJECT -> drop

IMPORTANT:
- Gateway decision happens BEFORE liquidity.
- If gateway REJECT/SOFT_REJECT, do not call liquidity model.
- Ensure the final ExecutionResult reflects gateway status if not accepted.

---

### 4) UPDATE EXECUTION RESULT MODEL

Extend ExecutionResult fields to capture gateway state:
- gateway_decision: str  # "ACCEPT" | "REJECT" | "SOFT_REJECT"
- attempt_number: int
- client_order_id: str
- retry_scheduled: bool
- next_retry_tick: int | None
- rejection_reason: str | None  # "GATEWAY_HARD_REJECT" | "GATEWAY_SOFT_REJECT" | "EXPIRED"

For accepted orders, gateway_decision="ACCEPT" and fill fields are populated via Step 11.3.

For rejected/soft-rejected, fill fields should indicate:
- filled_quantity = 0
- fill_status = "NONE"
- attempted = False (or keep attempted=True but ensure consistent semantics)
Pick a consistent rule and update invariants accordingly.

---

### 5) EVENTS (SCHEMA + EMISSION)

Add new event types:

1) ORDER_SUBMITTED
Payload:
- client_order_id, symbol, trader_type, strategy_name, direction
- requested_quantity, created_tick, attempt_number

2) ORDER_GATEWAY_DECISION
Payload:
- client_order_id, symbol, trader_type, tick, attempt_number
- decision: ACCEPT/REJECT/SOFT_REJECT
- deterministic_key (optional but nice for teaching)
- mapping_r (optional)

3) ORDER_REJECTED_HARD
Payload:
- client_order_id, symbol, trader_type, tick, attempt_number
- reason="GATEWAY_HARD_REJECT"

4) ORDER_RETRY_SCHEDULED
Payload:
- client_order_id, symbol, trader_type
- from_tick, next_retry_tick
- next_attempt_number

5) ORDER_EXPIRED
Payload:
- client_order_id, symbol, trader_type, tick, attempt_number
- reason="MAX_ATTEMPTS_REACHED"

Update existing Step 11.3 events:
- TRADE_NOT_FILLED should only occur after ACCEPT + liquidity NONE
- TRADE_OPENED includes client_order_id and attempt_number

---

### 6) REPLAY SAFETY

Replay must:
- Use emitted events to reconstruct:
  - pending order additions/removals
  - gateway decisions
  - retries and expirations
- Must NOT recompute gateway decisions during replay
- Ensure deterministic equivalence even if code changes later:
  events are the truth.

If current replay engine only prints events, that’s fine, but invariant checks must rely on events.

---

### 7) INVARIANTS / VALIDATION

Add/extend invariants:

- Every ORDER_RETRY_SCHEDULED must reference a prior ORDER_GATEWAY_DECISION with decision=SOFT_REJECT.
- No retry scheduled if attempt_number >= max_attempts.
- ORDER_EXPIRED only when attempt_number == max_attempts and decision=SOFT_REJECT OR explicitly forced by rule.
- A trade can open ONLY if:
  - gateway_decision == ACCEPT
  - filled_quantity > 0
- No liquidity event (TRADE_OPENED / TRADE_NOT_FILLED) should occur without a prior ACCEPT decision.

---

## LOGGING REQUIREMENTS (TEACHING-FIRST)

On each submission:
- [ORDER] submit id=... symbol=... qty=... trader_type=... attempt=1

On gateway decision:
- [GATEWAY] id=... tick=... attempt=... decision=...

On retry:
- [RETRY] id=... scheduled next_tick=... next_attempt=...

On expiry:
- [EXPIRE] id=... attempts=... max=... dropped

---

## TEST / DEMO REQUIREMENTS

Create a deterministic test scenario across ticks (e.g. ticks 1..20) that demonstrates:
- At least one HARD REJECT
- At least one SOFT REJECT that later ACCEPTS on retry
- At least one SOFT REJECT that EXPIRES (max attempts reached)
- At least one ACCEPT that proceeds to liquidity and opens a trade

Replay must reproduce the same event sequence and outcomes.

---

## FORBIDDEN ACTIONS

- No randomness
- No external broker calls
- No exponential backoff
- Do not persist pending orders to disk in this step
- Do not modify strategies/risk rules

---

## COMPLETION CRITERIA

Step 11.4 is COMPLETE when:
- Deterministic gateway decisions exist and are evented
- Soft rejects are retried deterministically with bounded attempts
- Hard rejects are final
- Expiration is handled and evented
- Accepted orders proceed to Step 11.3 liquidity fill logic
- Replay reproduces identical order lifecycle
- Invariants pass

END OF INSTRUCTIONS