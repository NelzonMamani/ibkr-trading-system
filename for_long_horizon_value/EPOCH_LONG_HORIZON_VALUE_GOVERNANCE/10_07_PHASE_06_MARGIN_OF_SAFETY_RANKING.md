# 10_07_PHASE_06_MARGIN_OF_SAFETY_RANKING.md — PHASE 06: MARGIN OF SAFETY & RANKING

Goal:
- Combine price + intrinsic value + market-confidence to determine:
  - WATCHLIST vs FOCUS eligibility
  - Priority ranking for Focus List

Codex tasks:
1) Fetch current prices (IBKR via existing market data client).
2) Compute margin-of-safety:
   - MoS = (IntrinsicBase - Price) / IntrinsicBase
   - Use policy-required margin-of-safety adjusted by market confidence:
     `required_margin_of_safety(confidence)` from `strategy_policy.py`
3) State assignment:
   - If quality passed but MoS insufficient → WATCHLIST
   - If quality + MoS sufficient → FOCUS
4) Ranking:
   - Primary: MoS
   - Secondary: quality_score
   - Tertiary: stability_score
   - Produce stable deterministic ordering (tie-breaker by symbol)

Outputs:
- Focus list with priority ranks.
- Watchlist entries with explicit “waiting for price” reason.

Tests:
- MoS threshold boundary test.
- Ranking determinism test.

END
