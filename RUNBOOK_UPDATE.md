> This flow sketch is architectural context only. Current launch authority and
> offline/READ_ONLY boundaries are in [RUNBOOK.md](RUNBOOK.md). It does not
> authorize orders, recovery clearing or operational enrollment.
> PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.

# RUNBOOK UPDATE — STRATEGY DEPLOYMENT

## Canonical Execution Flow
1. Load Strategy Constitution (human reference)
2. Load Strategy Policy (machine authority)
3. Orchestrator builds StrategyContext
4. StrategyRunner evaluates policy
5. Risk engine gates
6. Execution engine submits orders
7. Storage records outcomes

## Emergency Controls
- StopController overrides all strategies
- Circuit breakers are global and latched

This runbook supersedes prior strategy notes.
