# 02 — Determinism Model

## Determinism tiers
E26 defines three tiers. Each tier has explicit guarantees.

### Tier 0 — Import determinism (baseline)
- Importing any `src.*` module must not require runtime artefacts.
- CLI `--help` paths must be import-safe (no broker network calls; no DB required).

### Tier 1 — Boot determinism (rebuild-from-zero)
From a clean clone with no runtime artefacts:
- A deterministic bootstrap creates required directories and DB schema.
- Orchestrator runs in SIM/READ_ONLY/PAPER without manual artifact creation.
- If IBKR gateway is unavailable, system degrades safely (no crash; no trades).

### Tier 2 — Runtime determinism (repeatable runs)
Within a given mode + seeded inputs:
- Outputs are reproducible (within defined non-determinism boundaries).
- Evidence logs are produced (trace map, run summary).
- Decisions are explainable via stored decision artifacts.

## Allowed sources of non-determinism
Non-deterministic inputs must be treated as *external dependencies*:
- Live market data, live news feeds, time-of-day/session, broker connectivity.
When non-determinism exists, the system must:
- Record the input snapshot or the reason it was unavailable.
- Degrade to deterministic defaults for tests (mock providers, fixtures).

## Determinism enforcement mechanisms
- A single **Paths & Artefact Registry** defines what is runtime state.
- A single **Runtime Bootstrap** creates directories/schema on demand.
- A single **Purge/Reset tool** removes runtime artefacts safely.
- A single **Verification script** executes clean-room rebuild and records evidence.

## Operator guarantees
- Operator can run: `purge → bootstrap → run` without repo surgery.
- Operator can choose: `backup → purge → restore` (optional continuity).
- Operator never has to commit runtime artefacts.
