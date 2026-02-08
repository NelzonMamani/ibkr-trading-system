# FILE: 00_READ_FIRST.md
# TITLE: P01_ROSS_MOMENTUM — CODEX READ ORDER (Authoritative)
Date: 2026-02-08

## Read order (must follow)
1) ../GOVERNANCE/ALGORITHM.md
2) ../GOVERNANCE/STRATEGY_CAPABILITY_MAP.md
3) ../GOVERNANCE/STRATEGY_GOVERNANCE.md
4) ../GOVERNANCE/CERTIFICATION_CHECKLIST.md
5) Repository-wide canon registries (already certified): SF_*, XL_*, C_*, K_*, SCP_*, MCP_*, levels/zones/INV
6) Current implementation candidate: `strategies/ross_momentum/strategy_policy.py` and `strategy_context_schema.py`

## Non-negotiable rules
- Do NOT replace `strategy_policy.py`. Patch additively and safely.
- No behavioural constants outside policy.
- No partial coverage: every canonical item must be classified as ALLOWED/OPTIONAL/DENIED.

END
