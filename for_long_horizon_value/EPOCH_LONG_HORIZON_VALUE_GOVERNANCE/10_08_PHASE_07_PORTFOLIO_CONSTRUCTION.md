# 10_08_PHASE_07_PORTFOLIO_CONSTRUCTION.md — PHASE 07: PORTFOLIO CONSTRUCTION

Goal:
- Convert Focus List into a percent-based portfolio plan, respecting capital governance.
- Determine BUY_READY subset based on available allocation headroom.

Codex tasks:
1) Read current portfolio / exposures from existing system portfolio state (do not invent).
2) Apply percent-based constraints from `strategy_policy.py`:
   - MAX_SINGLE_POSITION_PCT
   - MAX_NEW_ALLOCATION_PCT
3) For each Focus symbol:
   - propose target_pct (simple default: equal-weight within constraints OR rank-weighted)
   - propose max_price (optional; can be current price or intrinsic-based cap)
4) Determine readiness:
   - If allocation headroom exists AND automation/approval allows → BUY_READY
   - Else remain FOCUS (capital constrained)

Outputs:
- PortfolioPlan record
- Updated Focus entries with “blocked by capital” reasons when applicable

Tests:
- Capital constrained scenario forces BUY_READY empty and leaves FOCUS populated.
- Target_pct never exceeds MAX_SINGLE_POSITION_PCT.

END
