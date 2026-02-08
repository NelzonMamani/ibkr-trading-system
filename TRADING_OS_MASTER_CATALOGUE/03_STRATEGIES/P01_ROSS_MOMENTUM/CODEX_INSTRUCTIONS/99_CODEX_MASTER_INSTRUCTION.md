# FILE: 99_CODEX_MASTER_INSTRUCTION.md
# TITLE: MASTER INSTRUCTION — P01_ROSS_MOMENTUM Strategy Certification
Date: 2026-02-08

You are Codex working in ibkr-trading-system.

Mission:
Bring Ross Momentum to full certification under E19/E21 using the canon registries and the governance docs in this folder.

Hard rules:
- Do NOT replace `strategy_policy.py`. Patch additively and safely.
- No partial registry coverage: every SF/XL/C/K/SCP/MCP item relevant to Ross must be explicitly mapped and/or denied.
- All behavioural thresholds must live in strategy policy parameters.
- Maintain end-to-end tradeability in SIM and PAPER; preserve LIVE read-only safety.

Execution order:
1) Read 00_READ_FIRST.md and all GOVERNANCE docs.
2) Audit current Ross implementation against GOVERNANCE/ALGORITHM.md.
3) Implement missing policy specs + mappings.
4) Ensure runner/context wiring supports required fields.
5) Add tests.
6) Run mandatory verification commands.
7) Write PR_VERIFICATION_REPORT.md with:
   - what changed
   - commands run and outputs
   - remaining gaps (must be zero for certification)

STOP when:
- Certification checklist is fully satisfied.

END
