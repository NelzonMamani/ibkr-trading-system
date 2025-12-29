# PHASE_11_STEP_11_1_MARKET_SLIPPAGE_MODEL.md

## PHASE 11 — MARKET REALISM LAYER
### STEP 11.1 — Introduce Deterministic Slippage Model

## OBJECTIVE
Introduce a deterministic, replay-safe slippage model that adjusts execution prices to simulate realistic market friction, without breaking:
- Event determinism
- Replay correctness
- Existing trade lifecycle logic
- Registry invariants
- Phase 10 behaviour

Slippage must be:
- Deterministic (no randomness)
- Purely functional
- Based only on known inputs (direction, trader_type, quantity)
- Applied ONLY at execution time (entry and exit)
- Fully event-recorded

---

## DESIGN RULES (MANDATORY)

1. **NO randomness**
2. **NO time-based values**
3. **NO external data**
4. **NO modification of strategy logic**
5. **NO modification of risk logic**
6. **NO modification of orchestrator control flow**
7. **Replay must reconstruct identical prices**
8. **Slippage must be visible in events and PnL**

---

## SLIPPAGE MODEL (DETERMINISTIC)

Implement a fixed slippage-per-share model:

| Trader Type | Direction | Slippage (per share) |
|------------|-----------|----------------------|
| SCALPER    | LONG      | +0.01                |
| SCALPER    | SHORT     | -0.01                |
| MOMENTUM  | LONG      | +0.02                |
| MOMENTUM  | SHORT     | -0.02                |

Rules:
- Entry price = price_feed_price + slippage
- Exit price = price_feed_price - slippage (for LONG)
- Exit price = price_feed_price + slippage (for SHORT)

Slippage is symmetric and deterministic.

---

## IMPLEMENTATION TASKS

### 1. CREATE NEW MODULE
Create file:

src/execution/slippage_model.py

Contents:
- SlippageModel class
- Static method:
  apply_slippage(
      price: float,
      direction: str,
      trader_type: str,
      quantity: int
  ) -> float

This function returns the adjusted execution price.

---

### 2. UPDATE EXECUTION ENGINE

File:
src/execution/execution_engine.py

Modify:
- Trade entry execution
- Trade exit execution

Steps:
1. Fetch raw price from price feed
2. Apply slippage via SlippageModel
3. Use adjusted price as:
   - entry_price
   - exit_price
4. Ensure both prices are stored in:
   - ExecutionResult
   - TRADE_OPENED event
   - TRADE_CLOSED event

DO NOT remove the raw price feed logging.

---

### 3. UPDATE EVENT PAYLOADS

Ensure the following fields are present in events:

TRADE_OPENED:
- raw_price
- slippage_applied
- execution_price

TRADE_CLOSED:
- raw_price
- slippage_applied
- execution_price
- realised_pnl (already exists, must now reflect slippage)

Replay must use execution_price, not raw_price.

---

### 4. UPDATE EXECUTION RESULT SCHEMA

File:
src/execution/execution_result.py (or equivalent)

Add fields:
- raw_price: Optional[float]
- slippage_applied: float

Ensure backward compatibility:
- Default slippage_applied = 0.0 if missing

---

### 5. UPDATE REPLAY ENGINE (IF REQUIRED)

If replay reconstructs prices:
- Use execution_price from events
- DO NOT recompute slippage during replay
- Slippage must be event-driven, not recomputed

---

## VALIDATION REQUIREMENTS

After implementation, the following must be true:

1. Trades still open and close exactly as in Phase 10
2. Hold durations unchanged
3. Risk caps unchanged
4. Replay produces identical PnL values
5. Logs clearly show:
   - Raw price
   - Slippage applied
   - Final execution price
6. Invariants pass
7. No schema warnings
8. No randomness introduced

---

## FORBIDDEN ACTIONS

- Do NOT change orchestrator
- Do NOT change strategy interfaces
- Do NOT add randomness
- Do NOT modify event ordering
- Do NOT break replay determinism

---

## COMPLETION CRITERIA

Phase 11 · Step 11.1 is COMPLETE when:
- Slippage is applied deterministically
- PnL reflects slippage
- Replay reproduces identical results
- Phase 10 behaviour remains intact

END OF INSTRUCTIONS
When Codex finishes this step, paste the runtime output exactly like before and I’ll verify:

Slippage correctness

Event integrity

Replay determinism

PnL math

Then we’ll move cleanly to Phase 11 · Step 11.2 — Fees & Commissions 🚀





