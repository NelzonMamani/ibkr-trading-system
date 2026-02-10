# SYSTEM_STATE.md
# IBKR Trading OS — Declared State (Unverified Starting Snapshot)

**Status:** DECLARED (non-authoritative)
**Last updated:** 2026-02-10
**Meaning:** This is a human-declared hypothesis about the current system. Codex must verify and then supersede with SYSTEM_STATE_CERTIFIED.md.

## Declared Run Modes (hypothesis)
- Modes exist: READ_ONLY, PAPER, LIVE
- Known pain point (declared): PAPER execution path has been historically broken or incomplete and requires verification.

## Declared Core Epoch Status (hypothesis)
Legend: NOT_STARTED / PARTIAL / IMPLEMENTED_UNCERTIFIED / CERTIFIED

- E0_SYSTEM_LAW_TRUTH: PARTIAL
- E1_TRACEABILITY_OBSERVABILITY: PARTIAL
- E2_POSITION_LIFECYCLE_ENGINE: PARTIAL
- E3_RISK_ENGINE_COMPLETENESS: PARTIAL
- E4_DATA_QUALITY_MARKET_STATE: PARTIAL
- E5_EXECUTION_ENGINE_AUTHORITY: PARTIAL
- E6_SCANNER_STRATEGY_CONTRACT: IMPLEMENTED_UNCERTIFIED (scanner mechanical; strategy policy ownership intended)
- E7_MODE_PARITY_AND_SAFETY: PARTIAL
- E8_REGIME_AND_MICROSTRUCTURE_LAYER: PARTIAL (regime layer exists as a directory/capability; requires integration verification)
- E9_PERFORMANCE_ANALYTICS: NOT_STARTED
- E10_CAPITAL_ALLOCATION: NOT_STARTED
- E11_LEARNING_SYSTEM: NOT_STARTED (design agreed; implementation pending)
- E12_RECOVERY_AND_HOUSEKEEPING: IMPLEMENTED_UNCERTIFIED (db_admin tooling exists; needs certification)
- E13_STRATEGY_FACTORY_STANDARD: PARTIAL (tests placement rule enforced by policy; needs verification)
- E14_DECISION_ARTIFACTS: PARTIAL
- E15_FAILURE_MODES: PARTIAL
- E16_NO_TRADE_CONTEXTS: PARTIAL
- E17_STRATEGY_INTERACTION_RULES: PARTIAL
- E18_STRATEGY_FOUNDATION_LAYER: NOT_STARTED (locked as next major epoch after certifications)

## Declared Metadata Epoch Status (hypothesis)
- M0_CANON: PARTIAL
- M1_ARCHITECTURE_MAP: CERTIFIED
- M2_CONTRACT_REGISTRY: CERTIFIED
- M3_MODE_SEMANTICS_CERT: CERTIFIED
- M4_TRACEABILITY_SEMANTICS: PARTIAL
- M5_VERIFICATION_AUTHORITY: PARTIAL
- M6_DATA_LIFECYCLE_GOV: PARTIAL
- M7_EPOCH_AUDIT_CERTIFICATION: NOT_STARTED
- M8_CHANGE_CONTROL: PARTIAL
- M9_SIGNAL_SEMANTICS_REGISTRY: NOT_STARTED
- M10_DATA_PROVENANCE_LEDGER: NOT_STARTED

## Declared Strategy Readiness (hypothesis)
- Ross Momentum: PARTIAL (core target; scanner + policy alignment ongoing historically)
- Statistical Intraday Momentum: PARTIAL
- Mean Reversion: PARTIAL (policy work planned; needs full wiring + tests)
- Long Horizon Value: PARTIAL (separate track; governance exists; needs certification)

## Notes / Known Historical Constraints
- Session-aware percent-change semantics (PRE/AH/weekend vs RTH) has been a major source of scanner discrepancies; must be explicitly verified under E4/E6/E7.
- Repo previously faced DB size bloat (~70MB); db_admin utility added; retention policy must be formalized under E12/M6.
