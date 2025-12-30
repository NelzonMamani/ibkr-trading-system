
PHASE_12_STEP_12_5_SINGLE_ORDER_CLI_SUBMISSION.md

# PHASE 12 — BROKER INTEGRATION (SIM-FIRST, GUARDED)
## STEP 12.5 — SINGLE-ORDER CLI SUBMISSION (ISOLATED, KILL-SWITCHED)

You are Codex operating on the `ibkr-trading-system` repository.

This step introduces a **deliberate, isolated, command-line path** for submitting
**exactly one order**, outside the orchestrator loop.

This is REQUIRED to prevent accidental live trading and to separate
continuous strategy execution from intentional broker actions.

---

## CORE PRINCIPLES (NON-NEGOTIABLE)

- The orchestrator loop MUST NOT submit IBKR orders
- This CLI submits **ONE order only**
- System must exit immediately after submission attempt
- Must enforce SIM-only or PAPER-only rules
- Must include a hard kill-switch
- Teaching-first, deterministic, auditable behavior

---

## FILES TO CREATE

Create the following new file ONLY:

📄 `src/cli/submit_one_order.py`

Do NOT modify any existing orchestrator, strategy, or execution files.

---

## CLI BEHAVIOR

This script must:

1. Be executed manually:

python -m cli.submit_one_order 


2. Perform **explicit safety validation**:
- Abort if `RUN_MODE == LIVE`
- Abort if `IBKR_ORDER_TRANSLATION_ENABLED != True`
- Abort if `IBKR_READONLY_ENABLED == True`
- Abort if more than ONE order is attempted

3. Construct exactly ONE order request
4. Route it through the IBKR submission path (SIM or PAPER only)
5. Emit events
6. Print a final result
7. Exit process

---

## ORDER DEFINITION (TEACHING)

Inside the script, define a single hardcoded order:

- symbol: "AAPL"
- direction: "LONG"
- quantity: 1
- order_type: "MKT"
- trader_type: "MANUAL"
- strategy_name: "CLI_TEST"

No dynamic input yet — this is intentional.

---

## IMPLEMENTATION DETAILS

### Step 1 — Imports and Safety Guards

In `submit_one_order.py`, import:

- runtime configuration
- IBKR submission service
- event collector
- sys.exit

Perform checks:

- If `RUN_MODE == LIVE` → raise RuntimeError
- If order translation disabled → raise RuntimeError
- If readonly enabled → raise RuntimeError

Print a clear `[ABORT]` message before exiting.

---

### Step 2 — Create Order Request Object

Create a minimal `OrderRequest` or equivalent structure containing:

- client_order_id (UUID)
- symbol
- direction
- quantity
- order_type
- trader_type
- strategy_name

This object must be immutable after creation.

---

### Step 3 — Submit Order

Call the IBKR submission service in SIM/PAPER mode:

- Submit exactly ONE order
- Capture submission result
- Emit:
- ORDER_SUBMITTED
- ORDER_ACCEPTED / ORDER_REJECTED
- ORDER_FINAL_STATUS

No retries. No loops.

---

### Step 4 — Output and Exit

Print a final summary:

- order id
- symbol
- status
- mode (SIM / PAPER)
- timestamp

Then call:

2. Perform **explicit safety validation**:
- Abort if `RUN_MODE == LIVE`
- Abort if `IBKR_ORDER_TRANSLATION_ENABLED != True`
- Abort if `IBKR_READONLY_ENABLED == True`
- Abort if more than ONE order is attempted

3. Construct exactly ONE order request
4. Route it through the IBKR submission path (SIM or PAPER only)
5. Emit events
6. Print a final result
7. Exit process

---

## ORDER DEFINITION (TEACHING)

Inside the script, define a single hardcoded order:

- symbol: "AAPL"
- direction: "LONG"
- quantity: 1
- order_type: "MKT"
- trader_type: "MANUAL"
- strategy_name: "CLI_TEST"

No dynamic input yet — this is intentional.

---

## IMPLEMENTATION DETAILS

### Step 1 — Imports and Safety Guards

In `submit_one_order.py`, import:

- runtime configuration
- IBKR submission service
- event collector
- sys.exit

Perform checks:

- If `RUN_MODE == LIVE` → raise RuntimeError
- If order translation disabled → raise RuntimeError
- If readonly enabled → raise RuntimeError

Print a clear `[ABORT]` message before exiting.

---

### Step 2 — Create Order Request Object

Create a minimal `OrderRequest` or equivalent structure containing:

- client_order_id (UUID)
- symbol
- direction
- quantity
- order_type
- trader_type
- strategy_name

This object must be immutable after creation.

---

### Step 3 — Submit Order

Call the IBKR submission service in SIM/PAPER mode:

- Submit exactly ONE order
- Capture submission result
- Emit:
- ORDER_SUBMITTED
- ORDER_ACCEPTED / ORDER_REJECTED
- ORDER_FINAL_STATUS

No retries. No loops.

---

### Step 4 — Output and Exit

Print a final summary:

- order id
- symbol
- status
- mode (SIM / PAPER)
- timestamp

Then call:
sys.exit(0)

or `sys.exit(1)` on failure.

---

## VALIDATION REQUIREMENTS

This step is complete when:

- Running the script does NOT start the orchestrator
- Exactly one order is attempted
- System exits immediately after submission
- LIVE mode is impossible
- Output is deterministic and readable
- No other system components are affected

---

## COMPLETION MESSAGE

When finished and verified, respond with:

**"STEP 12.5 complete — single-order CLI submission operational"**

---

END