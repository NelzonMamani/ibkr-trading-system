# P02 — CODEX MASTER INSTRUCTION (Single Block)
You are operating inside repository `ibkr-trading-system`.

Task:
Implement and certify `03_STRATEGIES/P02_STATISTICAL_INTRADAY_MOMENTUM` using the provided governance docs as the source of truth.

Rules:
- Treat Core E0–E21 and Metadata M0–M10 as implemented and authoritative.
- NO PARTIALS: every canonical registry must be classified and mapped.
- All tunable thresholds live in `strategy_policy.py`.
- Additive changes only; do not redesign OS engines.

Steps:
1) Read `03_STRATEGIES/P02_STATISTICAL_INTRADAY_MOMENTUM/GOVERNANCE/ALGORITHM.md`
2) Read `.../STRATEGY_CAPABILITY_MAP.md`, `.../STRATEGY_GOVERNANCE.md`, `.../CERTIFICATION_CHECKLIST.md`
3) Implement/extend P02 policy + mapping modules under `src/strategies/statistical_intraday_momentum/`
4) Add strategy-local unit tests per locked process
5) Wire to existing orchestrator/runner via the strategy interface contract (E19)
6) Run mandatory verification commands and record results in `PR_VERIFICATION_REPORT.md`

Deliverable:
A PR that passes all mandatory verification and satisfies the certification checklist.

END
