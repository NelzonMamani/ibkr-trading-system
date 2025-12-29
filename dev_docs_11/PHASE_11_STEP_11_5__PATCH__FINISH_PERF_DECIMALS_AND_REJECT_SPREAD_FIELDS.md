# PHASE_11_STEP_11_5__PATCH__FINISH_PERF_DECIMALS_AND_REJECT_SPREAD_FIELDS.md
# SINGLE-BLOCK / APPLY ENTIRELY

You are Codex in the IBKR Trading System repo.
Goal: finish Step 11.5 by (1) making PerformanceRegistry Decimal-correct and (2) ensuring spread/bid/ask/reference are populated on REJECTED/RETRY_SCHEDULED when mid is available.

Only modify:
- src/performance/performance_registry.py
- src/execution/execution_engine.py
- src/utils/price_math.py (ONLY if missing a helper you need)

============================================================
A) PERFORMANCE REGISTRY — DECIMAL TOTALS + QUANTIZED OUTPUT
============================================================
1) Open src/performance/performance_registry.py.

2) Ensure you import Decimal helpers:
- from decimal import Decimal
- from src.utils.price_math import to_decimal, q_money

3) Make sure internal totals are Decimal (even if zero):
- gross_pnl: Decimal = Decimal("0.00")
- total_commissions: Decimal = Decimal("0.00")
- net_pnl: Decimal = Decimal("0.00")

4) When building the snapshot payload:
- Convert any pnl inputs via to_decimal(...)
- Quantize all money fields to cents via q_money(...)
- Compute net as gross - commissions (Decimal)

Example pattern (adapt to your structure):

gross = Decimal("0.00")
comm = Decimal("0.00")

# If you have trade_outcomes:
for o in trade_outcomes:
    gross += to_decimal(getattr(o, "gross_realised_pnl", 0) or 0)

# If you have access to execution results (preferred for commissions):
for r in execution_results:
    comm += to_decimal(getattr(r, "commission", 0) or 0)

gross_q = q_money(gross)
comm_q  = q_money(comm)
net_q   = q_money(gross_q - comm_q)

avg_q = q_money(gross_q / Decimal(str(total_trades))) if total_trades > 0 else Decimal("0.00")

5) Payload emission:
- Keep existing keys, but ensure the values come from Decimal math.
- If you currently output ints, change them to float(gross_q), float(comm_q), float(net_q) and float(avg_q)
  OR output str(...) consistently. Choose one, but be consistent.
Recommended (minimal disruption): output floats derived from quantized Decimal:
- 'gross_pnl': float(gross_q)
- 'total_commissions': float(comm_q)
- 'net_pnl': float(net_q)
- 'avg_pnl_per_trade': float(avg_q)

6) After changes, PERF_SNAPSHOT in logs must show money fields like 0.0 (float) or "0.00" (string),
but NOT bare int 0 originating from int math.

============================================================
B) EXECUTION ENGINE — FILL SPREAD FIELDS ON REJECTED/RETRY WHEN MID EXISTS
============================================================
1) Open src/execution/execution_engine.py.

2) Locate the path that returns an ExecutionResult for:
- status='REJECTED' (gateway hard reject)
- status='RETRY_SCHEDULED' (soft reject)

Right now your log shows spread/bid/ask/reference are None there.

3) Rule:
- If you can compute a mid price deterministically without violating architecture, DO SO.
- Otherwise, if your code already has access to the mid (or can request it) at that stage, compute spread/bid/ask/reference.

Implementation options (pick the one that matches your current design):

OPTION 1 (preferred): If you already have a deterministic price feed method available:
- Call your price feed getter even on reject/soft-reject to obtain mid.
- Then compute:
  spread = deterministic_spread(symbol, tick, trader_type)
  bid, ask = apply_spread_mid_to_quote(mid_q, spread)
  ref = choose_execution_reference_price(direction, bid, ask)
- For REJECTED/RETRY_SCHEDULED:
  - raw_price=mid_q
  - spread/bid/ask/reference populated
  - execution_price=None
  - slippage_applied must remain Decimal('0.00') for these statuses

OPTION 2 (acceptable): If you MUST reject before price fetch:
- Make it explicit and consistent:
  - Always keep these fields None for REJECTED/RETRY_SCHEDULED
  - BUT then do not compute them anywhere else in those paths.
This is weaker than Step 11.5 intent; use only if architecture prevents price access.

Given the user’s requirement (“record when possible”), implement OPTION 1 unless there is a hard constraint.

4) Ensure determinism:
- The mid you fetch/compute must be deterministic for (symbol, tick).
- Convert immediately to Decimal and quantize using q_price.

============================================================
C) VERIFICATION (DO THIS EXACTLY)
============================================================
Run:
1) python -m compileall src
2) python src/main.py  (let it run 2 cycles, Ctrl+C)

Confirm in output:
- PERF_SNAPSHOT payload shows gross_pnl / total_commissions / net_pnl as float-like 0.0 or string "0.00" (derived from Decimal), not ints.
- For a REJECTED or RETRY_SCHEDULED ExecutionResult where mid is available, spread/bid/ask/reference are populated (not None).
- Filled trades still show:
  entry_price == execution_price
  execution_price == reference_price +/- slippage
  LONG uses ASK as reference.

END PATCH
