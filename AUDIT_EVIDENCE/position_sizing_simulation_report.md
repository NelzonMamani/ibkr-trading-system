# Position Sizing Simulation Report

Generated at: `2026-03-04T11:37:20.517477+00:00`

Formula: `target_qty = floor((portfolio_equity * target_weight)/price)` then adjusted for existing quantity and position cap.

| Case | Output qty |
|---|---:|
| baseline | 100 |
| qty<1 | 0 |
| position cap exceeded | 120 |
| existing position present | 40 |

Expected baseline check: portfolio_equity=100000, price=50, target_weight=0.05 => qty=100 ✅
