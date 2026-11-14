# IBKR Trading System

A multi-strategy trading system under active development for Interactive Brokers.
Ross Momentum is the current completion priority. Strategy modules and historical
certification matrices do not establish positive Core integration or operational
readiness for every strategy.

**PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.** Synthetic execution, accounting and
protection proofs are distinct from natural progression and broker validation.
All five ownership vetoes remain active. Operational recovery and trading are
not authorized by development or test results.

Read [SYSTEM_STATE.md](SYSTEM_STATE.md) for current scope and
[RUNBOOK.md](RUNBOOK.md) for offline verification and the maintained READ_ONLY
operator boundary. Existing evidence, limitations and the current work queue are
maintained in the Ross checkpoint, setup handoff and strategy governance records.

The old root/console live and unbounded PAPER launchers are retired. The previous
paper-open smoke command may submit an order; it is not an offline verification
command or evidence of readiness. See [DEPRECATION_LEDGER.md](DEPRECATION_LEDGER.md)
for retired paths and retained compatibility obligations.
