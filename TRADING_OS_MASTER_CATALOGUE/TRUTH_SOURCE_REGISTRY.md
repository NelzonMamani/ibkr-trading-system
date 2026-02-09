# TRUTH_SOURCE_REGISTRY

## Purpose
Establish single sources of truth for catalogue governance, operational contracts, and verification evidence. Any conflicts must be resolved here before execution.

## Canonical Sources (Authoritative)
| Domain | Source of Truth | Notes |
| --- | --- | --- |
| System law & programme rules | `TRADING_OS_MASTER_CATALOGUE/SYSTEM_CONSTITUTION_CERTIFIED.md` | Certified constitution is the binding authority. |
| System state | `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE_CERTIFIED.md` | Certified system state is authoritative for readiness decisions. |
| Catalogue execution rules | `TRADING_OS_MASTER_CATALOGUE/00_READ_FIRST/` | Read order and enforcement rules are binding. |
| Programme plan | `TRADING_OS_MASTER_CATALOGUE/PROGRAMME_EXECUTION_PLAN.md` | Controls sequencing after approval. |
| Contracts | `TRADING_OS_MASTER_CATALOGUE/CONTRACTS/` | Canonical human-readable contracts. |
| Verification | `TRADING_OS_MASTER_CATALOGUE/VERIFICATION_RUNBOOK.md` | Defines verification intent and commands for execution stage. |
| Reality snapshot | `TRADING_OS_MASTER_CATALOGUE/REALITY_MAP.md` | Baseline reality mapping. |
| Capability mapping | `TRADING_OS_MASTER_CATALOGUE/CAPABILITY_CROSSWALK.md` | Crosswalk for status and evidence. |

## Secondary Sources (Informational)
| Domain | Source | Rationale |
| --- | --- | --- |
| System law drafts | `TRADING_OS_MASTER_CATALOGUE/SYSTEM_CONSTITUTION.md` | Useful for edits; not authoritative once certified. |
| System state drafts | `TRADING_OS_MASTER_CATALOGUE/SYSTEM_STATE.md` | Draft working notes only. |
| Global execution instructions | `TRADING_OS_MASTER_CATALOGUE/CODEX_GLOBAL_EXECUTION_INSTRUCTIONS.md` | Supplemental; must not conflict with certified constitution. |
| Strategy execution protocol | `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/00_STRATEGY_EXECUTION_PROTOCOL.md/00_STRATEGY_EXECUTION_PROTOCOL.md` | Strategy execution context. |

## Duplicate Candidates and Decisions
- **System Constitution vs Certified**: Use `SYSTEM_CONSTITUTION_CERTIFIED.md` as authoritative; treat non-certified as editable draft.
- **System State vs Certified**: Use `SYSTEM_STATE_CERTIFIED.md` as authoritative; treat non-certified as editable draft.
- **Global Execution Instructions**: File exists in both `TRADING_OS_MASTER_CATALOGUE/` and `00_READ_FIRST/`. Canonical source is the `00_READ_FIRST/` copy; root copy is informational.
- **Strategy-specific verification lists**: Treat strategy `CODEX_INSTRUCTIONS` as local supplements; global runbook remains canonical.

## Contract Versioning Policy
- Contracts in `CONTRACTS/` are versioned manually in-place.
- Contract updates require updating the Contract Registry metadata epoch (M2) and the Verification Runbook.

## Change Control Reminder
Any update to canonical sources must be recorded in the audit trail for M8 Change Control during execution stage.
