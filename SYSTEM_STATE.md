# IBKR Trading System — Current development state

Updated 2026-11-14. This current-status record supersedes historical readiness
claims in generated certification snapshots; their original evidence is retained.

**PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.** No natural, broker, restart-resumption
or full multi-strategy readiness upgrade is established by synthetic proofs.

## Active authority and scope

- Runtime/configuration: `src/main.py`, `src/config/runtime_config.py` and
  `src/config/config_resolver.py`. CLI modes are SIM, READ_ONLY, PAPER and LIVE.
  READONLY remains a configuration compatibility alias only.
- Active orchestration: `src/core/orchestrator.py`; strategy policy/runner,
  shared risk, execution, fill, lifecycle and capital owners retain their gates.
  Module presence, imports, NO_TRADE smoke results and old P01–P20 matrix statuses
  do not establish positive integration for every strategy.
- Ross is the completion priority. Existing synthetic family/management proofs,
  natural evidence and unresolved limits are in the SAME3 records linked below.
  Committed-accounting cold restart, non-Ross positive Core integration and
  targeted legacy retirement are the grounded offline queue, not certified
  completed capabilities merely because they were proposed.
- All five ownership vetoes remain. Cold startup quarantine, broker-truth
  quantities, protection, uncertainty/replay latches and risk/capital gates
  remain authoritative; this status record grants no resumption or clearing.
- Corporate/listing-compliance/SEC remains parked; direct GAP_GO and HALT and
  existing confidence vetoes remain unchanged. No additional strategy is enabled
  by this documentation.

## Observation distribution

The corrected next-week caller remains frozen at
`3f48bf3fb769cbffc6ddfdc515d965968e71c31a`, accepted runtime source
`c65bc001fc3428c8eef0315fd1e1b8a903b7c53c` / tree
`6ece4121d7e2350a6fba94cdfe0e687b64b20328`, with its reviewed finite calendar.
Unrelated accepted engineering changes do not automatically repin it. No observer
is launched in this batch. See [RUNBOOK.md](RUNBOOK.md) for the guard boundary.

## Maintained evidence and continuation

- [Natural checkpoint](docs/ross/NATURAL_READONLY_CHECKPOINT.md)
- [Setup/trigger handoff](docs/architecture/ROSS_SETUP_TRIGGER_HANDOFF.md)
- [Ross governance](TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/P01_ROSS_MOMENTUM/GOVERNANCE/STRATEGY_GOVERNANCE.md)
- [Deprecation ledger](DEPRECATION_LEDGER.md)

Historical certification files, receipts, failed runs, databases and accounting/
recovery state are preserved. Operational enrollment, trading, broker/provider
activity and recovery clearing remain outside this offline engineering scope.
