# 10_06_PHASE_05_INTRINSIC_VALUE.md — PHASE 05: INTRINSIC VALUE ESTIMATION

Goal:
- Produce a conservative intrinsic value RANGE (low/base/high) per symbol, with assumptions recorded.

Codex tasks:
1) Implement at least two valuation methods (conservative):
   - Earnings power / owner earnings multiple approach
   - Simple DCF using owner earnings growth assumptions bounded tightly
2) Combine into IntrinsicValueRange:
   - low/base/high derived from conservative assumption bands
3) Sensitivity:
   - Record sensitivity table (at least growth and discount) for audit.
4) Output:
   - IntrinsicValueSet with notes and method provenance.

Do NOT:
- Overfit or add fancy models.
- Use intraday signals.

Tests:
- Sanity: intrinsic low ≤ base ≤ high.
- Determinism: same inputs → identical intrinsic outputs.

END
