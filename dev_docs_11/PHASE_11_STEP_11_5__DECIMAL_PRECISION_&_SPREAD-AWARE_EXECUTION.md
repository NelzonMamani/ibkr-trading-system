# PHASE_11_STEP_11_5__DECIMAL_PRECISION_&_SPREAD-AWARE_EXECUTION.md
# (SINGLE-BLOCK, COMPLETE, CANONICAL — DO NOT DOWNGRADE OR PARTIALLY APPLY)
# Objective: FULL Decimal correctness + FULL spread-aware execution + deterministic behaviour.
# If any earlier partial work exists, KEEP it and ONLY fill missing parts.
# Codex must verify what exists, then implement the missing items so Step 11.5 is 100% achieved.

You are Codex working in the IBKR Trading System repo.

============================================================
0) HARD REQUIREMENTS (NON-NEGOTIABLE)
============================================================
R0.1 Deterministic: For same (symbol, tick, trader_type, direction) the spread, bid/ask, reference price, slippage, and final execution_price MUST be identical across runs.
R0.2 Decimal-first: ALL money math uses Decimal end-to-end:
     - raw/mid price, bid, ask, spread, reference_price, execution_price
     - slippage_applied
     - commission
     - PnL (gross + net) and performance totals
R0.3 Spread-aware: execution reference uses:
     - LONG buys at ASK (plus slippage)
     - SHORT sells at BID (minus slippage)
R0.4 Quantization: prices and money quantized to cents (0.01) using ROUND_HALF_UP unless already defined.
R0.5 Minimal blast radius: Only modify the specific files listed in Section 2.
R0.6 Backwards compatibility: do not break existing logs/prints; new fields should default to None.
R0.7 Step must be “complete”: after implementing, run the tests in Section 9 and confirm output evidence.

============================================================
1) CURRENT STATE SIGNALS (FROM USER RUN) — WHAT MUST BE FIXED
============================================================
- You already have some Decimal/slippage fields in ExecutionResult (raw_price, slippage_applied, etc).
- Your output shows schema warnings (fine for now), but the real issue is:
  - Step 11.5 was partially executed earlier, then the instruction set got downgraded and Step 11.5 stopped being fully applied.
- We must ensure Step 11.5 includes:
  (A) Spread-aware pricing integrated in execution
  (B) Decimal correctness end-to-end, including performance totals
  (C) Deterministic spread model and deterministic slippage application order (spread then slippage)
  (D) PnL precision (Decimal) and quantization correctness

============================================================
2) ALLOWED FILES TO CHANGE (ONLY THESE)
============================================================
- src/utils/price_math.py
- src/execution/execution_engine.py
- src/models/execution_result.py
- src/performance/performance_registry.py
OPTIONAL (only if your liquidity code currently forces floats):
- src/execution/liquidity_engine.py

Do NOT touch any other files.

============================================================
3) STEP 11.5 DELIVERABLES (MUST ALL EXIST AFTER THIS)
============================================================
D3.1 src/utils/price_math.py:
     - Decimal helpers (to_decimal, quantize helpers)
     - Deterministic spread model (no Python hash usage)
     - Bid/ask derivation from mid
     - Spread-aware reference price selection
     - Slippage application AFTER spread
D3.2 src/models/execution_result.py:
     - Monetary fields accept Decimal (or Optional[Decimal])
     - NEW fields for spread-aware execution (spread, bid_price, ask_price, reference_price, execution_price)
     - Defaults so older construction still works
D3.3 src/execution/execution_engine.py:
     - Uses Decimal through the entire calculation pipeline
     - Computes mid/raw -> spread -> bid/ask -> reference -> slippage -> execution_price
     - entry_price uses execution_price on fills
     - average_fill_price uses execution_price on fills
     - NOT_FILLED and REJECTED still record spread/bid/ask/reference when possible (if mid exists)
D3.4 src/performance/performance_registry.py:
     - Uses Decimal for gross_pnl, net_pnl, totals
     - Quantizes outputs
     - If it emits extra keys (net_pnl, total_commissions) keep them and ensure correctness

============================================================
4) IMPLEMENTATION — VERIFY/AMEND STEP 1 IF NEEDED
============================================================
4.1 Open src/utils/price_math.py.
IF IT ALREADY EXISTS AND HAS THESE, DO NOT REWRITE THEM; only add missing pieces:
- from decimal import Decimal, getcontext, ROUND_HALF_UP
- getcontext().prec sufficiently high (e.g. 28)
- to_decimal(x) that safely converts:
  - None -> None (or Decimal("0") depending usage; prefer None-safe helper plus explicit defaults)
  - Decimal -> Decimal
  - int/str/float -> Decimal(str(x))  (IMPORTANT: float must be via str(x))
- q_money(d, places="0.01") quantize HALF_UP
- q_price(d, places="0.01") quantize HALF_UP
- safe_div(a,b,default=Decimal("0"))

If any are missing, add them.

============================================================
5) IMPLEMENTATION — DETERMINISTIC SPREAD MODEL (MUST EXIST)
============================================================
5.1 In src/utils/price_math.py, add (or ensure exists) these functions:

5.1.1 deterministic_mod_key(key: str, mod: int) -> int
- return sum(ord(c) for c in key) % mod
- NEVER use Python hash()

5.1.2 deterministic_spread(symbol: str, tick: int, trader_type: str) -> Decimal
Algorithm:
- key = f"{symbol}|{tick}|{trader_type}|SPREAD"
- r = deterministic_mod_key(key, 10)
- map r to spread dollars (Decimal):
  r in [0,1,2] => 0.01
  r in [3,4,5] => 0.02
  r in [6,7]   => 0.03
  r in [8]     => 0.05
  r in [9]     => 0.08
- return q_price(Decimal("..."))

5.1.3 apply_spread_mid_to_quote(mid: Decimal, spread: Decimal) -> tuple[Decimal, Decimal]
- half = spread / Decimal("2")
- bid = mid - half
- ask = mid + half
- clamp:
  - minimum tick price: bid >= Decimal("0.01")
  - ask must be > bid, if ask <= bid then ask = bid + Decimal("0.01")
- return q_price(bid), q_price(ask)

5.1.4 choose_execution_reference_price(direction: str, bid: Decimal, ask: Decimal) -> Decimal
- direction upper
- if LONG: return ask
- if SHORT: return bid
- else: return ask (safe default) but log/raise if your style prefers

5.1.5 apply_slippage(reference_price: Decimal, slippage: Decimal, direction: str) -> tuple[Decimal, Decimal]
- if slippage is None: slippage = Decimal("0")
- LONG: exec = reference_price + slippage
- SHORT: exec = reference_price - slippage
- clamp exec >= 0.01
- return q_price(exec), q_price(slippage)

============================================================
6) IMPLEMENTATION — EXECUTION RESULT MODEL (SPREAD FIELDS + DECIMAL SAFE)
============================================================
6.1 Edit src/models/execution_result.py.
- Ensure existing monetary fields accept Decimal or Optional[Decimal]
- Add NEW optional fields with default None (DO NOT BREAK CONSTRUCTORS):
  - spread: Optional[Decimal] = None
  - bid_price: Optional[Decimal] = None
  - ask_price: Optional[Decimal] = None
  - reference_price: Optional[Decimal] = None
  - execution_price: Optional[Decimal] = None
- Ensure existing fields like raw_price, entry_price, exit_price, slippage_applied are Decimal-safe.
- If the file uses dataclass, just add fields at end to avoid positional issues.

============================================================
7) IMPLEMENTATION — EXECUTION ENGINE (SPREAD-AWARE + DECIMAL END-TO-END)
============================================================
7.1 Edit src/execution/execution_engine.py.

7.2 Import required helpers from price_math:
- to_decimal, q_price, q_money
- deterministic_spread
- apply_spread_mid_to_quote
- choose_execution_reference_price
- apply_slippage

7.3 Convert “mid/raw price” from price feed to Decimal immediately:
- raw_mid = to_decimal(price_feed_value)
- raw_mid_q = q_price(raw_mid)

7.4 Compute spread and bid/ask deterministically per attempted order:
- spread = deterministic_spread(symbol, tick, trader_type)
- bid, ask = apply_spread_mid_to_quote(raw_mid_q, spread)

7.5 Choose reference price based on direction:
- ref = choose_execution_reference_price(direction, bid, ask)

7.6 Slippage application MUST be AFTER spread:
- slippage_dec = to_decimal(existing_slippage_value or 0)
- exec_price, slippage_applied = apply_slippage(ref, slippage_dec, direction)

7.7 Fill pipeline:
- Liquidity decision determines fill_qty and status
- If fill_qty > 0:
  - entry_price = exec_price
  - average_fill_price = exec_price  (until partial fills support VWAP)
  - quantity = fill_qty (int)
- If not filled:
  - entry_price = None
  - average_fill_price = None
  - but still store raw_price (mid), spread, bid_price, ask_price, reference_price, execution_price=None

7.8 Ensure ExecutionResult is populated with these new fields on ALL outcomes where mid is known:
- raw_price = raw_mid_q
- spread = spread
- bid_price = bid
- ask_price = ask
- reference_price = ref
- execution_price = exec_price if filled else None
- slippage_applied = slippage_applied

7.9 Edge cases:
- If gateway hard rejects before price feed is called:
  - raw_price/spread/bid/ask/ref should be None (since no mid)
  - That is acceptable.
- If you already call price feed before gateway, then populate them; keep consistent with current architecture.

7.10 Ensure registry registration uses Decimal entry_price.
If registry currently expects float:
- Prefer updating registry to accept Decimal if it’s in allowed files (it is not listed; do NOT edit registry unless it resides in allowed list).
- If you cannot, convert only at the last boundary:
  - float(entry_price)  BUT ONLY IF REQUIRED.
Prefer to keep Decimal everywhere if possible.

============================================================
8) IMPLEMENTATION — PERFORMANCE REGISTRY (DECIMAL CORRECTNESS)
============================================================
8.1 Edit src/performance/performance_registry.py.

Goal: gross_pnl, total_commissions, net_pnl are Decimal and quantized.

8.2 Internal storage:
- Use Decimal for:
  - gross_pnl
  - total_commissions
  - net_pnl
- Quantize to cents at snapshot time:
  - gross_pnl_q = q_money(gross_pnl)
  - total_commissions_q = q_money(total_commissions)
  - net_pnl_q = q_money(gross_pnl - total_commissions)

8.3 Data sources (given current system constraints):
- If you have TradeOutcome list for realized trades: sum those realized_pnl as gross_pnl (convert to Decimal via to_decimal)
- total_commissions should be sum of commissions in execution results (convert to Decimal).
- If both open and close executions exist, this naturally accumulates.
- If only opens exist, it still tracks cost-of-trading, which is correct.

8.4 Emit payload:
- Keep existing keys plus ensure:
  - 'gross_pnl' is numeric (float) or Decimal; pick what your serialization expects.
Recommended:
  - store Decimal internally
  - output float(gross_pnl_q) etc
- If you already output 'total_commissions' and 'net_pnl', keep them.

8.5 Ensure avg_pnl_per_trade uses Decimal division and quantize:
- avg = gross_pnl / total_trades if total_trades>0 else 0
- q_money(avg)

============================================================
9) REQUIRED VERIFICATION RUN (Codex MUST DO THIS)
============================================================
After changes, run exactly:
1) python -m compileall src
2) python src/main.py
Let it run at least 2 cycles, then Ctrl+C.

Codex must confirm in output / or by inspecting ExecutionResult prints:
- For a filled LONG:
  - entry_price == ask(mid, spread) + slippage (quantized)
  - bid/ask exist and ask > bid
- For NOT_FILLED:
  - raw_price exists
  - spread/bid/ask/reference exist
  - execution_price is None
- For performance snapshot:
  - gross_pnl, total_commissions, net_pnl are present and correctly computed using Decimal (quantized)

============================================================
10) ACCEPTANCE CRITERIA (STEP 11.5 COMPLETE ONLY IF ALL TRUE)
============================================================
A10.1 deterministic_spread exists and is used by execution_engine.
A10.2 bid/ask are computed from mid using Decimal and quantized.
A10.3 LONG uses ask as reference; SHORT uses bid.
A10.4 slippage applied after spread and quantized.
A10.5 ExecutionResult includes spread/bid/ask/reference/execution_price fields without breaking construction.
A10.6 performance_registry totals use Decimal and net_pnl is correct.
A10.7 compileall passes, main runs without exceptions.

============================================================
11) IMPORTANT NOTE ABOUT “FRAGMENTED INSTRUCTIONS”
============================================================
This single block is the full canonical Step 11.5.
Codex must NOT apply only the beginning.
Codex must implement everything missing and then verify via Section 9.

END OF PHASE_11_STEP_11_5__DECIMAL_PRECISION_&_SPREAD-AWARE_EXECUTION.md