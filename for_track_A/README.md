# Track A — Ross Momentum Live Implementation (Codex Phase Bundle)

This bundle contains the **implementation phases** Codex must execute to take the repo from "strategy specifications exist"
to **Ross Momentum trading live** under strict governance.

Key definitions:
- **Strategy Constitution**: human-readable "what Ross does" (immutable reference)
- **Strategy Policy**: machine-readable rules & thresholds used by code
- **Strategy Context**: live facts snapshot assembled by Orchestrator for the policy/runner

Repository assumption:
- Authoritative strategy lives under `src/strategies/ross_momentum/`.
- Orchestrator and execution pipeline already exist (risk/execution/storage tests passing).

Operator constraint:
- User is in the UK, but trades US markets. All market sessions must be computed in **America/New_York** with DST,
  then displayed in UK local time for operator clarity.
