PHASE_12_STEP_12_4_IBKR_ORDER_SUBMISSION.md 
PHASE 12 · STEP 12.4 — IBKR ORDER SUBMISSION (SIM-ONLY, SINGLE ORDER, KILL-SWITCH) — CODEX INSTRUCTIONS (SINGLE BLOCK)

OBJECTIVE
Enable a tightly controlled “submit exactly ONE order” pathway to IBKR in SIM mode, with:
- Hard kill-switch
- Explicit single-order limit
- Explicit paper-trading only (NO live routing)
- Full audit logs and event emission
- Deterministic idempotency guard (prevent accidental duplicates)

THIS IS THE FIRST STEP WHERE placeOrder IS ALLOWED — BUT ONLY UNDER STRICT GATES.

ABSOLUTE SAFETY RULES (NON-NEGOTIABLE)
1) RUN_MODE MUST be SIM for any order submission attempt.
   - If RUN_MODE != SIM → hard fail (raise RuntimeError).
2) IBKR_ORDER_SUBMISSION_ENABLED MUST be true.
   - If false → hard fail.
3) IBKR_KILL_SWITCH MUST be false.
   - If true → hard fail (do not submit).
4) PAPER TRADING ONLY:
   - Must connect using the paper endpoint / paper port (or explicitly configured “paper” mode).
   - If configuration suggests live trading connection → hard fail.
5) SINGLE ORDER PER RUN:
   - The system may submit at most 1 order in the entire process lifetime.
   - Enforce with a SubmissionGuard that persists in-memory and optionally to disk.
6) NO RETRIES.
7) NO BRACKET ORDERS.
8) NO SHORTING (optional but recommended for Step 12.4):
   - If direction == SHORT → hard fail (unless you already explicitly permit it).
9) DO NOT integrate into the continuous orchestrator loop.
   - This step is a dedicated “submit-once then exit” command path.

SCOPE (WHAT THIS STEP DOES)
✔ Connect to IBKR paper gateway
✔ Translate internal order → IBKR (use Step 12.3 translator)
✔ Submit ONE market order (or allow limit if you prefer, but keep it minimal)
✔ Wait for acknowledgement (order status callback or a short polling window)
✔ Emit events: ORDER_SUBMISSION_ATTEMPTED, ORDER_SUBMITTED_ACK, ORDER_SUBMISSION_FAILED
✔ Exit cleanly

OUT OF SCOPE (FORBIDDEN)
✘ Multiple orders
✘ Auto-retries
✘ Smart order management
✘ Execution simulation
✘ Position tracking
✘ Live trading
✘ Wiring into StrategyRunner / ExecutionEngine main path

CONFIG CHANGES (src/config/runtime_config.py)
Add the following settings (defaults MUST be safe):
- IBKR_ORDER_SUBMISSION_ENABLED: bool = False
- IBKR_KILL_SWITCH: bool = True
- IBKR_MAX_ORDERS_PER_RUN: int = 1
- IBKR_SUBMIT_ONLY_SYMBOL: str | None = None   # if set, only allow that symbol
- IBKR_PAPER_ONLY_ENFORCED: bool = True
- IBKR_PAPER_HOST: str = "127.0.0.1"
- IBKR_PAPER_PORT: int = 7497 (or your paper port)
- IBKR_LIVE_PORT: int = 7496 (kept for detection; do not use)
- IBKR_ACK_TIMEOUT_SECONDS: int = 10
- IBKR_CLIENT_ID_ORDER_SUBMIT: int = 9012      # distinct client id for this mode

IMPORTANT:
- If IBKR_PAPER_ONLY_ENFORCED is true and port == IBKR_LIVE_PORT → hard fail.

NEW MODULES / FILES

1) src/adapters/brokers/ibkr/ibkr_order_submitter.py
Implement:
- class IbkrOrderSubmitter:
    - __init__(ibkr_client, translator, event_bus, config, guard, logger)
    - submit_once(internal_order) -> SubmissionResult

Where:
- translator is IbkrOrderTranslator from Step 12.3
- ibkr_client is your existing Step 12.2 client wrapper (ib_insync-based)
- guard enforces single-order-per-run
- event_bus emits SystemEvents

SubmissionResult must include:
- client_order_id: str
- ibkr_order_id: int | None
- status: str  ("ACKED" | "FAILED" | "TIMED_OUT" | "BLOCKED")
- error: str | None
- submitted_at: datetime
- acked_at: datetime | None

2) src/adapters/brokers/ibkr/submission_guard.py
Implement:
- class SubmissionGuard:
    - can_submit() -> bool
    - mark_submitted(client_order_id: str)
    - submitted_count() -> int
    - already_submitted(client_order_id: str) -> bool

Rules:
- total submissions per run <= IBKR_MAX_ORDERS_PER_RUN
- idempotency: if same client_order_id is attempted twice → BLOCKED

Optional (recommended):
- persist a tiny JSON file in /data or /runtime to guard across accidental restarts:
  - config: IBKR_GUARD_PERSIST_PATH: str = "runtime/submission_guard.json"
  - If exists and indicates already submitted → block
(If you do persist, it must still default safe and never block unit tests unintentionally.)

3) src/events/event_types.py (or wherever)
Register schemas for:
- ORDER_SUBMISSION_ATTEMPTED
- ORDER_SUBMITTED_ACK
- ORDER_SUBMISSION_FAILED
- ORDER_SUBMISSION_BLOCKED
Include schema fields:
- client_order_id, symbol, direction, quantity, order_type
- ibkr_order_id (if known)
- reason/error
- timestamp

4) src/cli/submit_one_order.py (or similar)
Create a dedicated entry point (recommended) OR a “--submit-one-order” mode in main.py.

This command MUST:
- Load config
- Enforce safety gates
- Build a single InternalOrder (from args or from a fixed test order in config)
- Call IbkrOrderSubmitter.submit_once()
- Print a clear final summary
- Exit

ORDER FLOW (MUST FOLLOW THIS EXACT SEQUENCE)

A) Pre-flight gating (fail fast)
1. If RUN_MODE != SIM → raise RuntimeError("IBKR submission forbidden unless RUN_MODE=SIM")
2. If IBKR_ORDER_SUBMISSION_ENABLED is false → raise RuntimeError("IBKR submission disabled by config")
3. If IBKR_KILL_SWITCH is true → raise RuntimeError("Kill-switch enabled; submission blocked")
4. If IBKR_PAPER_ONLY_ENFORCED is true AND port == IBKR_LIVE_PORT → raise RuntimeError("Live port detected; paper-only enforced")
5. If IBKR_SUBMIT_ONLY_SYMBOL is set AND internal_order.symbol != that symbol → raise RuntimeError("Symbol not allowed")
6. Guard checks:
   - if not guard.can_submit() → emit ORDER_SUBMISSION_BLOCKED and return status=BLOCKED
   - if guard.already_submitted(client_order_id) → emit ORDER_SUBMISSION_BLOCKED and return status=BLOCKED

B) Translate
- (contract, order) = translator.translate(internal_order)

C) Connect (paper)
- Use the Step 12.2 IBKR client wrapper to connect to host/port with IBKR_CLIENT_ID_ORDER_SUBMIT
- If connection fails → emit ORDER_SUBMISSION_FAILED and return FAILED

D) Submit (the ONLY allowed placeOrder)
- Emit ORDER_SUBMISSION_ATTEMPTED
- Call placeOrder(contract, order)
- Immediately mark guard.mark_submitted(client_order_id) AFTER successful placeOrder call returns without exception
  (If placeOrder raises → do NOT mark submitted)

E) Await acknowledgement
- Wait up to IBKR_ACK_TIMEOUT_SECONDS for:
  - an OrderStatus / trade update indicating the order exists (Submitted/PreSubmitted/ApiPending/etc.)
  - OR a known orderId assigned
Implementation options:
- If using ib_insync: trade = ib.placeOrder(contract, order)
  - trade.orderStatus updates asynchronously
  - poll trade.orderStatus.status until non-empty or timeout
- On timeout: emit ORDER_SUBMISSION_FAILED with TIMED_OUT but keep guard marked submitted ONLY IF placeOrder succeeded.

F) Emit final event
- If acked: emit ORDER_SUBMITTED_ACK with ibkr_order_id and status
- If failed: emit ORDER_SUBMISSION_FAILED with error

G) Disconnect and exit
- Clean disconnect from IBKR
- Print: "SIM SUBMISSION COMPLETE — NO LIVE TRADING" plus final status

ORDER TYPE POLICY (KEEP MINIMAL)
For Step 12.4:
- Allow ONLY MKT orders by default.
- Optionally allow LMT if you already validated it in Step 12.3.
If you restrict to MKT:
- If internal_order.order_type != "MKT" → raise RuntimeError("Only MKT allowed in Step 12.4")

UNIT TESTS (NO LIVE IBKR REQUIRED)
You MUST add tests with a FakeIbkrClient stub:
- test_submission_blocked_when_kill_switch_true
- test_submission_blocked_when_run_mode_not_sim
- test_submission_blocked_when_disabled
- test_submission_blocks_second_order_same_run
- test_idempotency_blocks_same_client_order_id_twice
- test_success_path_marks_submitted_and_emits_events
- test_placeOrder_exception_does_not_mark_submitted

FakeIbkrClient should simulate:
- connect/disconnect
- placeOrder returning a fake “trade” object with orderStatus

LOGGING REQUIREMENTS
Every run must log:
- RUN_MODE, enabled flags, kill switch state
- Connection target host/port and confirmation it is PAPER
- Full internal order summary
- Translation summary (contract + order fields)
- Submission attempt + result
- Clear banner:
  "IBKR SUBMISSION MODE — SIM ONLY — SINGLE ORDER — KILL SWITCH AVAILABLE"

ACCEPTANCE CHECKLIST
- With defaults, submission is impossible (disabled + kill-switch on).
- Setting IBKR_ORDER_SUBMISSION_ENABLED=true but leaving kill-switch=true still blocks.
- Setting kill-switch=false + enabled=true + RUN_MODE=SIM allows exactly one submission.
- A second submission attempt in same process is blocked.
- No continuous orchestrator loop triggers submission.
- All relevant events are emitted and visible in logs/replay.

END