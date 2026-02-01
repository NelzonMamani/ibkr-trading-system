# 10_10_PHASE_09_MONITOR_REUNDERWRITE.md — PHASE 09: MONITORING & RE-UNDERWRITE

Goal:
- Periodically re-evaluate owned and focus/watchlist names.
- Demote only via explicit reasons and recorded checklist deltas.

Codex tasks:
1) Implement re-underwrite cadence (monthly/quarterly) using `cadence.py` constants.
2) Evaluate thesis validity signals:
   - deterioration in economics/quality gates
   - major leverage changes
   - large valuation drift
3) Produce MonitoringReport:
   - action: HOLD/ADD/REDUCE/EXIT
   - reasons list
4) Demotion:
   - Focus → Watchlist when MoS deteriorates or quality degrades
   - Owned → Review when gates fail

Tests:
- Demotion requires explicit reasons list non-empty.
- Monitoring outputs deterministic for fixed inputs.

END
