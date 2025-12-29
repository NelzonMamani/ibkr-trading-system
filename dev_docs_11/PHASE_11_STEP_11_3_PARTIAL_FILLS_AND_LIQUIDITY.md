# PHASE_11_STEP_11_3_PARTIAL_FILLS_AND_LIQUIDITY.md

## PHASE 11 — MARKET REALISM LAYER
### STEP 11.3 — Partial Fills & Liquidity Constraints (Deterministic)

## OBJECTIVE
Add a deterministic “liquidity constraint” layer that can cause:
- FULL fills
- PARTIAL fills
- ZERO fills (no fill)

This must:
- Preserve determinism & replay safety
- Avoid randomness and external data
- Not change strategy/risk intent generation
- Only affect execution outcomes (fills) and resulting trade lifecycle
- Be explainable via events and logs

This is a teaching-first simulation of market microstructure constraints.

---

## DESIGN RULES (MANDATORY)

1. NO randomness (no random.choice, random.uniform, etc.)
2. NO time-based nondeterminism
3. NO external data feeds / broker calls
4. NO changes to strategy logic
5. NO changes to risk decision rules (allowed vs blocked)
6. Partial fills happen ONLY in ExecutionEngine
7. Replay must reconstruct identical fills from emitted events
8. Liquidity results must be computed deterministically from:
   - tick
   - symbol
   - trader_type
   - requested quantity
   - run_mode (SIM/LIVE but in LIVE it may be bypassed later)

---

## DEFINITIONS

### Requested Quantity
The quantity the execution layer is asked to fill (from RiskDecision).

### Filled Quantity
The quantity actually filled this cycle.

### Remaining Quantity
requested_quantity - filled_quantity

---

## LIQUIDITY MODEL (DETERMINISTIC)

Create deterministic “available liquidity per tick” for each symbol.

Rule: available_liquidity is derived from (symbol, tick) using a stable hash.
NO Python built-in hash() (it is process-randomized).
Use a stable hash like hashlib.sha256.

Example algorithm (must match exactly):
1) key = f"{symbol}|{tick}"
2) digest = sha256(key.encode("utf-8")).hexdigest()
3) take first 8 hex chars -> int
4) map into range [0..MAX_LIQUIDITY_PER_TICK]

MAX_LIQUIDITY_PER_TICK values:
- SCALPER: 1
- MOMENTUM: 2

Interpretation:
- SCALPER can fill at most 1 share per tick
- MOMENTUM can fill at most 2 shares per tick
(Teaching constraints, not realistic broker specs.)

Additionally, introduce a “no fill” possibility deterministically:
- If (mapped_value == 0) => 0 liquidity => no fill this tick.

Thus:
filled_quantity = min(requested_quantity, available_liquidity)

---

## IMPLEMENTATION TASKS

### 1) CREATE NEW MODULE: LIQUIDITY MODEL

Create:
src/execution/liquidity_model.py

Implement:
- class LiquidityModel
- function:

  available_liquidity(
      symbol: str,
      tick: int,
      trader_type: str
  ) -> int

Use deterministic stable hashing (sha256) and the trader_type max table.

Also add helper:
- max_liquidity_per_tick(trader_type: str) -> int

---

### 2) UPDATE EXECUTION RESULT MODEL

File:
src/execution/execution_result.py (or equivalent)

Add fields (default-safe):
- requested_quantity: int
- filled_quantity: int
- remaining_quantity: int
- fill_status: str  # "FULL" | "PARTIAL" | "NONE"
- average_fill_price: float | None  # for partials (can equal entry_price in this phase)
- note: str | None  # teaching explanation

Rules:
- FULL: filled_quantity == requested_quantity && requested_quantity > 0
- PARTIAL: 0 < filled_quantity < requested_quantity
- NONE: filled_quantity == 0

Maintain backward compatibility:
- If old fields exist, do not break imports; provide defaults.

---

### 3) UPDATE EXECUTION ENGINE TO APPLY LIQUIDITY

File:
src/execution/execution_engine.py (or equivalent)

When processing an ALLOWED RiskDecision:
1) Determine requested_quantity (normally max_position_size)
2) Compute available = LiquidityModel.available_liquidity(symbol, tick, trader_type)
3) filled_quantity = min(requested_quantity, available)
4) remaining_quantity = requested_quantity - filled_quantity

If filled_quantity == 0:
- Do NOT register a trade in registry
- Emit an event TRADE_NOT_FILLED (or ORDER_NOT_FILLED) with reason and liquidity info
- Return ExecutionResult with fill_status="NONE"

If filled_quantity > 0:
- Register trade with filled_quantity (NOT requested_quantity)
- Emit TRADE_OPENED event including requested/fill/remaining

If PARTIAL:
- Include clear teaching logs:
  “Partial fill due to deterministic liquidity cap.”

IMPORTANT:
- This phase does NOT require multi-tick completion of remaining quantity.
Remaining quantity is simply reported and then dropped (teaching simplicity).
We will handle “order persistence” in a later phase.

---

### 4) UPDATE REGISTRY SCHEMA (IF NEEDED)

If trade registry stores quantity, ensure it stores actual filled quantity.

Ensure unregister/close uses the stored quantity.

---

### 5) UPDATE EVENTS (SCHEMA + EMISSION)

Add new event type:
- TRADE_NOT_FILLED (or ORDER_NOT_FILLED)

Payload must include:
- symbol
- trader_type
- tick
- requested_quantity
- available_liquidity
- filled_quantity=0
- reason: "LIQUIDITY_ZERO" or "LIQUIDITY_CAP"

Update TRADE_OPENED payload to include:
- requested_quantity
- filled_quantity
- remaining_quantity
- fill_status ("FULL" or "PARTIAL")

---

### 6) UPDATE REPLAY LOGIC (IF REQUIRED)

Replay must:
- Read these events and reproduce the same registry state changes
- Not recompute liquidity during replay
- Use the event payload as the source of truth

---

### 7) UPDATE INVARIANTS / VALIDATION

Add/extend invariants:
- No trade can be registered with quantity <= 0
- TRADE_OPENED must have filled_quantity > 0
- TRADE_NOT_FILLED must have filled_quantity == 0
- remaining_quantity == requested_quantity - filled_quantity

---

## TEST / DEMO REQUIREMENTS

Add/extend tests (or deterministic demo assertions) so that:

1) At least one symbol produces:
   - FULL fill
   - PARTIAL fill
   - NONE fill
Across a small tick range (e.g., ticks 1..10)

2) Performance + PnL remain valid:
- If no fill, there must be no trade outcome
- If partial fill, realised pnl reflects partial quantity

3) Replay produces identical fills and outcomes.

---

## LOGGING REQUIREMENTS (TEACHING-FIRST)

When partial or none occurs:
- Print a clear, single-line explanation:
  [LIQUIDITY] symbol=XYZ tick=5 trader_type=MOMENTUM requested=2 available=1 filled=1 remaining=1 status=PARTIAL

When none occurs:
  [LIQUIDITY] symbol=ABC tick=3 trader_type=SCALPER requested=1 available=0 filled=0 remaining=1 status=NONE (no trade opened)

---

## FORBIDDEN ACTIONS

- Do NOT implement “order carryover” yet (no pending orders store)
- Do NOT modify strategies or risk rules
- Do NOT add randomness
- Do NOT use Python hash()

---

## COMPLETION CRITERIA

Phase 11 · Step 11.3 is COMPLETE when:
- Execution deterministically produces FULL/PARTIAL/NONE fills
- Trades are only registered for filled_quantity > 0
- Events include all fill metadata
- Replay reconstructs identical behaviour
- Invariants pass
- Logs clearly explain liquidity outcomes

END OF INSTRUCTIONS