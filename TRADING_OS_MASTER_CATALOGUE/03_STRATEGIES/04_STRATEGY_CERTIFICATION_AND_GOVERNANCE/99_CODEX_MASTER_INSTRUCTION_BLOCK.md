# 99_CODEX_MASTER_INSTRUCTION_BLOCK

Objective:
Implement StrategyPolicyV2 Certification Authority.

Codex must:
1. Discover all strategy_policy_v2.py files.
2. Validate required sections per checklist JSON.
3. Enforce no duplicate IDs.
4. Emit certification report (JSON + MD).
5. Integrate with M5 + E23 reconciliation.
6. Add per-strategy unit tests.

Verification commands:
- python -m compileall src
- pytest -q

END
