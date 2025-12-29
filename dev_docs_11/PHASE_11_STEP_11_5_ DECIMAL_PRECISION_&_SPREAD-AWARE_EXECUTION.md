PHASE_11_STEP_11_5_ DECIMAL_PRECISION_&_SPREAD-AWARE_EXECUTION

# PHASE 11 — MARKET REALISM & EXECUTION FIDELITY
## STEP 11.5 — DECIMAL PRECISION & SPREAD-AWARE EXECUTION (PHASE CLOSURE)

You are Codex operating on the IBKR Trading System repository.

This step FINALIZES Phase 11 by enforcing:
- Monetary correctness via Decimal arithmetic
- Spread-aware execution pricing
- Deterministic, replay-safe behaviour

This step is REQUIRED to close Phase 11.

---

## OBJECTIVES

You must:

1. Replace all float-based monetary values with Decimal
2. Introduce deterministic bid/ask spread handling
3. Preserve replay determinism
4. Ensure gross PnL, commissions, and net PnL remain mathematically correct
5. Avoid changing strategy logic or external APIs

---

## FILES TO MODIFY (ONLY THESE)

- `src/execution/execution_engine.py`
- `src/execution/liquidity_engine.py`
- `src/performance/performance_registry.py`
- `src/models/execution_result.py`
- `src/utils/price_math.py` (NEW FILE)

Do NOT modify any other files.

---

## STEP 1 — CREATE CENTRAL DECIMAL PRICE UTILITIES

Create a new file:

📄 `src/utils/price_math.py`

Add the following:

```python
from decimal import Decimal, getcontext, ROUND_HALF_UP

# Global precision for money
getcontext().prec = 12

MONEY_QUANT = Decimal("0.01")


def D(value) -> Decimal:
    """Convert value safely to Decimal."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

# PHASE 11 — MARKET REALISM & EXECUTION FIDELITY
## STEP 11.2 (FIXED + COMPLETE, SINGLE-BLOCK) — FEES & COMMISSIONS + PRICING PRECISION FOUNDATION
## PLUS STEP 11.4/11.5 SUPPORT — SPREAD-AWARE PRICING + DECIMAL CORRECTNESS

You are Codex operating on the IBKR Trading System repository.
The user confirms: Step 1 (price_math.py) was created by Codex already, but Step 2 (spread model + integration) was NOT implemented due to fragmented instructions.
Your job now is to (1) verify Step 1 exists and is correct, (2) implement Step 2 fully, and (3) ensure the phase is correct and deterministic, then re-run and confirm.

### CRITICAL RULES
- Output must be deterministic between runs (given same tick/symbol/trader_type).
- Use Decimal for ALL money math: prices, slippage, commission, PnL.
- Slippage is applied AFTER spread-adjustment.
- DO NOT change files outside the allowed list.

### Allowed files to change (ONLY)
- `src/utils/price_math.py` (verify; minimal edits if necessary)
- `src/execution/execution_engine.py`
- `src/execution/liquidity_engine.py` (only if needed for Decimal compatibility)
- `src/performance/performance_registry.py`
- `src/models/execution_result.py`

---

# A) VERIFY STEP 1 WAS DONE (DO NOT SKIP)
1. Confirm file exists:
   - `src/utils/price_math.py`

2. Open and verify it provides at minimum:
   - `to_decimal(x) -> Decimal`
   - `q_money(d, places="0.01") -> Decimal` (quantize to cents by default)
   - `q_price(d, places="0.01") -> Decimal` (same, but semantically price)
   - `q_qty(d, places="1") -> Decimal` or integer qty support (we still trade whole shares; qty can remain int, but keep helper)
   - `safe_div(a,b,default=Decimal("0"))`
   - constant context/rounding rule (HALF_UP recommended)

If anything is missing, FIX it minimally (do not refactor unrelated logic).
If Step 1 is already correct, do not modify it.

---

# B) IMPLEMENT STEP 2 — DETERMINISTIC SPREAD MODEL (THIS IS WHAT WAS MISSED)
## B1) Add deterministic spread helper in `src/utils/price_math.py`
Add functions (or equivalent) WITHOUT breaking existing exports:

### `deterministic_spread(symbol: str, tick: int, trader_type: str) -> Decimal`
- Returns a spread value in dollars (e.g. 0.01, 0.02, 0.05), deterministic.
- Use a stable hash-free mapping (no Python hash()).
- Recommended: use sum of `ord()` values and modular arithmetic.

Example deterministic algorithm (Codex may implement equivalent):
- key = f"{symbol}|{tick}|{trader_type}|SPREAD"
- r = sum(ord(c) for c in key) % 10
- Map r to spreads:
  - r in [0,1,2] => 0.01
  - r in [3,4,5] => 0.02
  - r in [6,7]   => 0.03
  - r in [8]     => 0.05
  - r in [9]     => 0.08
Return Decimal with 2dp quantization.

### `apply_spread_mid_to_quote(mid: Decimal, spread: Decimal) -> tuple[Decimal, Decimal]`
- bid = mid - spread/2
- ask = mid + spread/2
- Quantize to cents.
- Ensure bid < ask always (if mid is tiny, clamp spread or clamp bid >= 0.01).

### `choose_execution_reference_price(direction: str, bid: Decimal, ask: Decimal) -> Decimal`
- If direction == "LONG" => reference = ask
- If direction == "SHORT" => reference = bid
- Else raise / default safely.

### `apply_slippage(reference_price: Decimal, slippage: Decimal, direction: str) -> tuple[Decimal, Decimal]`
- For LONG: execution = reference + slippage
- For SHORT: execution = reference - slippage
- Return (execution_price, slippage_applied) both quantized.

NOTE: slippage must remain deterministic too. If you already have deterministic slippage, keep it but convert to Decimal and apply after spread.

---

# C) EXECUTION ENGINE INTEGRATION (SPREAD-AWARE + DECIMAL CORRECTNESS)
Edit `src/execution/execution_engine.py`.

## C1) Convert all price + pnl math to Decimal
- Any `float` price math must become Decimal via `to_decimal`.
- Store raw feed price as Decimal (`raw_price`).
- Determine spread via `deterministic_spread`.
- Compute bid/ask via `apply_spread_mid_to_quote`.
- Select reference price based on direction (LONG uses ask).
- Apply slippage AFTER spread via `apply_slippage`.

## C2) Extend execution events payload (no schema system changes required)
Your logs show schema warnings like:
- Unknown event_type=ORDER_SUBMITTED / ORDER_GATEWAY_DECISION
- event=TRADE_OPENED has extra keys: attempt_number, client_order_id, gateway_decision

Do NOT build a schema registry in this step.
Just ensure we populate ExecutionResult consistently; schema warnings are acceptable for now.

## C3) Update how fills register entry_price
When a fill happens:
- Use `execution_price` (after spread + slippage) for entry_price/avg fill price.
- Ensure registry uses Decimal-safe storage OR convert to float ONLY at the last moment if registry is strict.
  - Prefer keeping Decimal everywhere.

## C4) Partial fills (compatibility)
Your current output supports:
- requested_quantity
- filled_quantity
- remaining_quantity
- fill_status (NONE/FULL)

Keep that behavior.
If liquidity engine later supports partial fills, execution_price logic MUST still apply to the filled portion.
No PnL should be realized on OPEN.

---

# D) FEES & COMMISSIONS (STEP 11.2 PROPER)
Edit `src/execution/execution_engine.py` and `src/models/execution_result.py` to support fees now, but keep fee charged only on fills.

## D1) Commission model (deterministic, simple, pluggable)
Implement a `commission_for_fill(symbol, trader_type, filled_qty, execution_price) -> Decimal` in execution_engine OR a local helper.

Rules (teaching but correct):
- Minimum commission per order: $0.35
- Per-share commission: $0.0035 * filled_qty
- Cap: 1% of notional (execution_price * filled_qty) (rare here, but correct)
- Commission = min(max(per_share, min_commission), cap)
- Quantize to cents using Decimal.

Apply commission ONLY when `filled_qty > 0`.
If no fill => commission 0.

## D2) Store commission + net fields in ExecutionResult
ExecutionResult already has:
- commission
- gross_realised_pnl
- net_realised_pnl

Populate:
- gross_realised_pnl = 0 on OPEN (no realized PnL yet)
- net_realised_pnl = gross_realised_pnl - commission (so negative on entry if you want accounting realism)
  - If you prefer to defer commission to close, still store it here and keep net=0. Either is acceptable BUT must be consistent.
Recommended (more correct): on OPEN, realized pnl=0, commission recorded but net realized remains 0; total commissions tracked separately.
Implement as:
- `commission` populated
- `gross_realised_pnl = 0`
- `net_realised_pnl = 0`
Then performance_registry will account for commission when trades close.
This avoids “realised pnl negative on entry”.

---

# E) DECIMAL PNL + PERFORMANCE REGISTRY FIX (STEP 11.5)
Your log shows:
- `[SCHEMA] event=PERF_SNAPSHOT has extra keys: net_pnl, total_commissions`
So perf_registry is already emitting those keys, but ensure correctness with Decimal.

Edit `src/performance/performance_registry.py`.

## E1) Use Decimal internally
- Track:
  - `gross_pnl: Decimal`
  - `total_commissions: Decimal`
  - `net_pnl: Decimal = gross_pnl - total_commissions`
- Quantize to cents.
- When producing payload or printing, convert to float ONLY if your current serialization expects numeric float.
  - Prefer string formatting with 2 decimals OR float conversion at output boundary.

## E2) Commission accounting on CLOSE
When a trade is closed (TradeOutcome produced):
- gross_realised_pnl should be computed from (exit_price - entry_price) * qty (LONG) or reversed for SHORT.
- total_commissions should include:
  - entry commission + exit commission (if you model both)
For now we can model a single commission charge:
- If you charged commission at OPEN only: add that commission once per trade.
- If you plan to charge again at close later: add both.

Given current system closes in TradeExitEngine, but you’re not allowed to edit it now.
So do this:
- If TradeOutcome currently has realised_pnl already: treat that as gross pnl and keep commissions tracked from ExecutionResult events.
- If not available: compute from entry/exit in outcome.

Because you can’t reliably reach entry commission at performance_registry unless it already stores it:
- Update `ExecutionResult` to carry commission and ensure when a trade closes, the close result includes commission too (if your system emits close results as ExecutionResult).
- If close results don’t exist yet, then:
  - Store commissions in PerformanceRegistry during TRADE_OPENED events (if it sees them) OR
  - Accept “commission tracked on execution results only” and keep total_commissions = sum(result.commission for results in cycle)
Given your output includes ExecutionResult list each cycle, easiest is:
- In performance snapshot, compute:
  - `total_commissions = sum(result.commission for result in cycle_execution_results if result.commission)`
- Keep gross/net for realized trades only.

Implement the simplest correct approach consistent with your current data flow:
- total_commissions sums ALL commissions recorded on fills (opened or closed) from execution results that cycle.
- gross pnl sums realized pnl from TradeOutcome list (if present), else 0.
- net = gross - total_commissions.

---

# F) UPDATE EXECUTION RESULT MODEL (DECIMAL-SAFE)
Edit `src/models/execution_result.py`.

## F1) Ensure monetary fields can be Decimal
Fields that should be Decimal (or Optional[Decimal]):
- raw_price
- entry_price
- exit_price
- slippage_applied
- gross_realised_pnl
- commission
- net_realised_pnl
- average_fill_price

Add NEW optional fields to support spread-aware pricing (if not already present):
- bid_price: Optional[Decimal]
- ask_price: Optional[Decimal]
- spread: Optional[Decimal]
- reference_price: Optional[Decimal]  (pre-slippage; after spread selection)
- execution_price: Optional[Decimal]  (post-slippage; used as entry/exit fill)

If you want to avoid breaking dataclass construction, provide defaults of None for new fields.

## F2) Keep printing readable
If the code prints dataclass directly, Decimal will show as `Decimal('47.83')`. That’s acceptable.
If you prefer clean output, implement `__repr__` or a helper formatter, but DO NOT add new files.

---

# G) REQUIRED SMOKE TESTS (MUST RUN AND REPORT RESULTS)
After implementing, run:

1) `python -m compileall src`
2) `python src/main.py` (let it run 2 cycles; then Ctrl+C)

Then confirm in the output:
- Each attempted order shows bid/ask or at least spread-derived execution price fields in ExecutionResult.
- LONG orders execute at ask + slippage (when filled).
- NOT_FILLED orders still show raw_price and (bid/ask/spread/reference) but no entry_price.
- Commission is non-zero when filled (LMN/XYZ in your example should show commission >= 0.35).
- PERF snapshot shows `gross_pnl`, `total_commissions`, `net_pnl` consistent and quantized.

---

# H) ACCEPTANCE CRITERIA (PHASE 11 CAN ADVANCE ONLY IF ALL TRUE)
- Determinism: same run with same ticks produces same spreads, same bid/ask, same execution prices.
- Spread-aware pricing: LONG uses ask reference; SHORT uses bid reference.
- Slippage applied AFTER spread.
- Commission model applied on fills deterministically.
- Performance snapshot includes net_pnl computed from Decimal math.
- No crashes; compileall passes.

---

# I) CODEx DOUBLE-CHECK (MANDATORY)
Before finalizing, Codex must do these confirmations:
- Confirm `src/utils/price_math.py` existed before and Step 1 wasn’t duplicated.
- Confirm Step 2 (deterministic_spread + apply_spread_mid_to_quote) is now present and USED by execution_engine.
- Confirm execution_engine uses Decimal conversions consistently.
- Confirm performance_registry totals align with commissions.

If any check fails, fix and re-run tests again.

END.