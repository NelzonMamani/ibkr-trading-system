PHASE_12_STEP_12_3_IBKR_ORDER_TRANSLATION_DRY-RUN_ONLY).md

PHASE 12 · STEP 12.3 — IBKR ORDER TRANSLATION (DRY-RUN ONLY) — CODEX INSTRUCTIONS (SINGLE BLOCK)

OBJECTIVE
Introduce a STRICT, NON-EXECUTING order translation layer that:
1) Converts internal system orders into IBKR Contract + Order objects
2) Validates correctness (side, quantity, order type, prices, time-in-force)
3) Logs the translated IBKR payload clearly
4) STOPS before submission (no placeOrder calls)

This step exists to:
- Prove structural compatibility with IBKR
- Catch mapping errors early
- Prepare for Phase 13 (controlled live submission)

ABSOLUTE SAFETY RULES
- DO NOT call placeOrder under any condition
- DO NOT simulate execution
- DO NOT connect order translation to ExecutionEngine yet
- Translation must be gated by config: IBKR_ORDER_TRANSLATION_ENABLED=true
- If translation is attempted while disabled → hard fail

SCOPE (WHAT THIS STEP DOES)
✔ Translate internal orders → IBKR Contract + Order objects
✔ Validate mapping rules
✔ Log dry-run output
✔ Raise errors on invalid mappings

OUT OF SCOPE (EXPLICITLY FORBIDDEN)
✘ Order submission
✘ Order retries
✘ Execution reports
✘ Trade lifecycle changes

DELIVERABLES (FILES / MODULES)

1) src/adapters/brokers/ibkr/ibkr_order_translator.py
   - New module
   - Responsible ONLY for translation (no networking)

   Implement:
   - class IbkrOrderTranslator:
       - translate(internal_order) -> (Contract, Order)
       - validate(internal_order)
       - log_translation(contract, order)

2) src/domain/models/internal_order.py (or equivalent)
   - Ensure a canonical internal order model exists with at least:
     fields:
       - client_order_id: str
       - symbol: str
       - direction: str           # "LONG" or "SHORT"
       - quantity: int
       - order_type: str          # "MKT" | "LMT"
       - limit_price: float | None
       - time_in_force: str = "DAY"
       - strategy_name: str
       - trader_type: str

3) src/config/runtime_config.py
   - Add:
     - IBKR_ORDER_TRANSLATION_ENABLED: bool (default False)
     - IBKR_DEFAULT_EXCHANGE: str = "SMART"
     - IBKR_DEFAULT_CURRENCY: str = "USD"

4) src/main.py (or a dedicated dry-run entry)
   - Add a DRY-RUN test path:
     - If IBKR_ORDER_TRANSLATION_ENABLED=true AND a test order is provided:
       - Build an internal order
       - Pass it to IbkrOrderTranslator
       - Log the translated IBKR Contract + Order
       - Exit without connecting to IBKR

MAPPING RULES (MUST BE EXACT)

Direction:
- LONG  → Order.action = "BUY"
- SHORT → Order.action = "SELL"

Quantity:
- Must be int > 0
- Reject zero or negative quantities

Order Type:
- Internal "MKT" → IBKR Order.orderType = "MKT"
- Internal "LMT" → IBKR Order.orderType = "LMT"
  - limit_price MUST be provided

Time in Force:
- Internal "DAY" → Order.tif = "DAY"
- Internal "IOC" → Order.tif = "IOC"
- Reject unsupported values explicitly

Contract Mapping:
- symbol → Contract.symbol
- exchange → config default ("SMART")
- currency → config default ("USD")
- secType = "STK"

VALIDATION RULES (HARD FAILURES)
- Unknown direction → RuntimeError
- Unsupported order type → RuntimeError
- LMT without limit_price → RuntimeError
- Quantity <= 0 → RuntimeError
- Translation attempted while IBKR_ORDER_TRANSLATION_ENABLED=false → RuntimeError

LOGGING REQUIREMENTS
- Log before translation:
  - client_order_id
  - symbol
  - direction
  - quantity
- Log after translation (dry-run):
  - Contract fields (symbol, exchange, currency, secType)
  - Order fields (action, orderType, totalQuantity, tif, lmtPrice if present)
- Explicitly log:
  "IBKR ORDER TRANSLATION DRY-RUN — NO SUBMISSION PERFORMED"

TESTING REQUIREMENTS
- Unit tests must cover:
  - LONG + MKT
  - SHORT + LMT
  - Invalid direction
  - Missing limit_price
  - Translation disabled by config
- No live IBKR connection required for tests

ACCEPTANCE CHECKLIST
- No IBKR network calls occur
- No placeOrder usage exists anywhere in this step
- Translation output matches IBKR API expectations
- Errors are explicit and loud
- System behaviour unchanged unless translation flag is enabled

END