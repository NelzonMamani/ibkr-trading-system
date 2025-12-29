# PHASE_11_STEP_11_5__FINAL_DECIMAL_AUTHORITY_FIX.md
# SINGLE BLOCK — APPLY COMPLETELY — NO PARTIALS

You are Codex working in ibkr-trading-system.

GOAL:
Eliminate ALL integer monetary values from PerformanceRegistry.
Every monetary value MUST originate from Decimal math and be
emitted as float (or string) — NEVER int.

============================================================
A) FILE TO MODIFY (ONLY THIS FILE)
============================================================
src/performance/performance_registry.py

DO NOT modify any other file.

============================================================
B) FORCE DECIMAL AUTHORITY AT THE SOURCE
============================================================

1) Imports (ensure these exist at top):
from decimal import Decimal
from src.utils.price_math import to_decimal, q_money

============================================================
C) REMOVE ALL INT DEFAULTS (CRITICAL)
============================================================

2) Replace ANY of the following patterns:
- gross_pnl = 0
- total_commissions = 0
- net_pnl = 0
- avg_pnl = 0

WITH:
gross_pnl = Decimal("0.00")
total_commissions = Decimal("0.00")

============================================================
D) ACCUMULATE USING DECIMAL ONLY
============================================================

3) When looping over outcomes or execution results:

DO NOT use:
gross_pnl += outcome.gross_realised_pnl
gross_pnl += 0

INSTEAD ALWAYS:
gross_pnl += to_decimal(getattr(outcome, "gross_realised_pnl", 0) or 0)
total_commissions += to_decimal(getattr(result, "commission", 0) or 0)

============================================================
E) COMPUTE NET + AVERAGES SAFELY
============================================================

4) After accumulation:
gross_q = q_money(gross_pnl)
comm_q  = q_money(total_commissions)
net_q   = q_money(gross_q - comm_q)

avg_q = (
    q_money(net_q / Decimal(str(total_trades)))
    if total_trades > 0 else Decimal("0.00")
)

============================================================
F) EMIT NON-INTEGER TYPES (MANDATORY)
============================================================

5) PERF_SNAPSHOT payload MUST use float():

'gross_pnl': float(gross_q)
'total_commissions': float(comm_q)
'net_pnl': float(net_q)
'avg_pnl_per_trade': float(avg_q)

DO NOT emit Decimal.
DO NOT emit int.
DO NOT emit uncast numeric literals.

============================================================
G) VERIFICATION (REQUIRED)
============================================================

Run:
python src/main.py

CONFIRM in logs and replay:
'gross_pnl': 0.0
'total_commissions': 0.0
'net_pnl': 0.0

If any value is still `0` (int), the patch is NOT complete.

END OF PATCH