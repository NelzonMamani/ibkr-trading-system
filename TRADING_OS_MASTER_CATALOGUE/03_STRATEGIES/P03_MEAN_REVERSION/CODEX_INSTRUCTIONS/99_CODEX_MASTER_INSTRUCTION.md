# P03 — CODEX MASTER INSTRUCTION (Single Block)
You are operating inside repository `ibkr-trading-system`.

Task:
Certify and patch `03_STRATEGIES/P03_MEAN_REVERSION` using governance docs as the source of truth.

Rules:
- Core E0–E21 and Metadata M0–M10 are authoritative.
- NO PARTIALS: full canon registry mapping required.
- All tunables in strategy policy.
- Additive-only fixes; preserve tradeability and safety.

Steps:
1) Read P03 governance docs in `03_STRATEGIES/P03_MEAN_REVERSION/GOVERNANCE/`
2) Locate existing implementation under `src/strategies/mean_reversion/`
3) Patch/extend policy and helpers to match the canon mapping and algorithm
4) Add strategy-local tests per process
5) Wire to existing runner/orchestrator via E19 interface
6) Run mandatory verification and capture results

Deliverable:
A PR that satisfies P03 certification checklist and passes all verification.

END
