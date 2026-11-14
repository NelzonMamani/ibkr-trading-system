# Development and READ_ONLY runbook

**PAPER_READY=NO; PAPER_READINESS_GATE=FAIL.** Development authorization does not
authorize operational enrollment, orders, broker-state changes or recovery clearing.

## Offline verification

Use the project interpreter with its installed dependencies, from the repository
root. Select focused affected tests before required final-head CI. The offline
transport guard must be present for regression checks:

```bash
PYTHONPATH=tests/offline:src:. python -m pytest -q tests/test_mode_drift_guard.py tests/test_read_only_guard.py tests/test_execution_authority_epoch5.py
```

On PowerShell, set `$env:PYTHONPATH = 'tests/offline;src;.'` for the test child
process and restore its previous value afterwards. Do not use that environment
for natural observation. Tests provide synthetic/offline evidence only.

## Runtime and observation authority

The active entry point is `src.main` / `src.core.orchestrator.CoreOrchestrator`.
CLI mode choices are SIM, READ_ONLY, PAPER and LIVE (`src/main.py`); unsupported
LIVE_MICRO, LIVE_READ_ONLY and LIVE_1SHARE spellings are not executable recipes.
The config-only READONLY compatibility alias is not a CLI choice. SIM is bounded
by `RUN_SIMULATION.ps1`; it is not a natural or broker certification command.
PAPER and LIVE can be writable and require separate operational authorization.
Do not translate an obsolete live spelling into LIVE.

Natural READ_ONLY observation uses the maintained guarded operator/harness,
not a bare main/scanner command or old core_engine orchestrator. The frozen
next-week distribution is commit `3f48bf3fb769cbffc6ddfdc515d965968e71c31a`, with
accepted source `c65bc001fc3428c8eef0315fd1e1b8a903b7c53c` and the unchanged reviewed
finite calendar. Preparation and observation require the existing contemporaneous
PAPER/read-only, disabled submission, exact client71/session ownership,
fresh-root and bounded owned-cleanup checks. This runbook does not launch it or
replace its immutable caller. Unrelated merges do not repin that distribution.

## Failure handling

An empty Focus/watchlist is a valid gated outcome. Inspect original evidence,
source coverage and rejection reasons; do not relax catalyst/freshness gates to
produce a trade. READ_ONLY can connect to external services and is not an offline
mode. Do not reset databases, clear quarantine, assume cancellation succeeded,
terminate another client, or use writable smoke scripts as diagnostics.

Current scope and limitations: [SYSTEM_STATE.md](SYSTEM_STATE.md),
[checkpoint](docs/ross/NATURAL_READONLY_CHECKPOINT.md),
[handoff](docs/architecture/ROSS_SETUP_TRIGGER_HANDOFF.md),
[governance](TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/P01_ROSS_MOMENTUM/GOVERNANCE/STRATEGY_GOVERNANCE.md).
Historical epoch/certification commands remain evidence of their original runs,
not current launch authority.
