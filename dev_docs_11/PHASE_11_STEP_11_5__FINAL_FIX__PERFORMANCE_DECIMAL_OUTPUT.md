# PHASE_11_STEP_11_5__FINAL_FIX__PERFORMANCE_DECIMAL_OUTPUT.md
# SINGLE BLOCK — APPLY COMPLETELY

You are Codex in the ibkr-trading-system repository.

GOAL:
Finish Phase 11 · Step 11.5 by fixing PerformanceRegistry so that
ALL monetary fields in PERF_SNAPSHOT are derived from Decimal math
and emitted as float or string — never as raw int.

ONLY MODIFY:
- src/performance/performance_registry.py

============================================================
A) INTERNAL TOTALS MUST BE DECIMAL
============================================================
1) Ensure these imports exist:
from decimal import Decimal
from src.utils.price_math import to_decimal, q_money

2) Ensure internal accumulators are Decimal:
gross_pnl = Decimal("0.00")
total_commissions = Decimal("0.00")

============================================================
B) ACCUMULATE USING DECIMAL (NOT INT)
============================================================
3) When iterating trade outcomes or execution results:
- Wrap all numeric inputs with to_decimal(...)
- Never rely on implicit int addition

Example:
gross_pnl += to_decimal(getattr(outcome, "gross_realised_pnl", 0) or 0)
total_commissions += to_decimal(getattr(result, "commission", 0) or 0)

============================================================
C) QUANTIZE + EMIT CORRECT TYPES
============================================================
4) Before building PERF_SNAPSHOT payload:
gross_q = q_money(gross_pnl)
comm_q  = q_money(total_commissions)
net_q   = q_money(gross_q - comm_q)

avg_q = (
    q_money(gross_q / Decimal(str(total_trades)))
    if total_trades > 0 else Decimal("0.00")
)

5) Emit values as float OR string — choose ONE and be consistent.
Recommended (minimal disruption):

'gross_pnl': float(gross_q)
'total_commissions': float(comm_q)
'net_pnl': float(net_q)
'avg_pnl_per_trade': float(avg_q)

DO NOT emit raw Decimal objects.
DO NOT emit ints.

============================================================
D) VERIFICATION
============================================================
Run:
python src/main.py

Confirm logs show:
PERF_SNAPSHOT payload with:
- gross_pnl: 0.0
- total_commissions: 0.0
- net_pnl: 0.0
(not integer 0)

END PATCH