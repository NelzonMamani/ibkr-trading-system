# 10_05_PHASE_04_ECONOMICS_OWNERS_EARNINGS.md — PHASE 04: ECONOMICS & OWNER EARNINGS

Goal:
- Compute owner’s earnings and economics profiles needed for valuation.

Codex tasks:
1) Implement owner’s earnings calculation:
   - Start from operating cash flow
   - Subtract maintenance capex proxy (conservative)
   - Adjust for working capital volatility (conservative)
2) Compute stability metrics:
   - multi-year volatility of earnings and cash flows
   - drawdown years count
3) Output EconomicsProfile per symbol, including:
   - owner_earnings series
   - reinvestment_rate proxy
   - stability_score

Recordkeeping:
- Persist economics profiles and assumptions used.

Tests:
- Owner earnings negative years → triggers failure reason in later phases.
- Stability_score deterministic for a known fixture series.

END
