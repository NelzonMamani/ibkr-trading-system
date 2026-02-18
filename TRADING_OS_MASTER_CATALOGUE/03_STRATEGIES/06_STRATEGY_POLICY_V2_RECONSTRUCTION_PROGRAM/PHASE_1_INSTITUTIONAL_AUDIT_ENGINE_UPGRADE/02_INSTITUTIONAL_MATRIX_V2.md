# Institutional Strategy Governance Standard — Audit Matrix V2 (ISGS-V2)

## Intent
The matrix defines **what must be present** in a StrategyPolicyV2 to claim institutional-grade governance readiness.

The matrix is:
- deterministic (no subjective scoring)
- machine-verifiable
- extensible (new controls can be added without breaking semantics)
- non-invasive (spec-only upgrades; no runtime wiring)

## Domains
Domains are audited independently and aggregated into a strategy verdict.

**D0 — Identity & Scope**
- StrategyIdentityV2 present with stable name/id
- Strategy scope notes present (purpose, market, horizon)
- Mode semantics present (SIM/PAPER/READ_ONLY/LIVE)
- Session semantics present (PRE/RTH/AH/OVN/CLOSED)

**D1 — Stock Selection & Universe Governance**
- selection_plan present
- stock_selection_law present (even if trivial, must be explicit)
- liquidity sanity model present
- ranking model present (or explicit “NOT_APPLICABLE” with rationale)
- data requirements for selection present

**D2 — Setup Taxonomy Governance**
- setup_families present with >=1 family OR explicit NOT_APPLICABLE
- pattern_catalog present with >=1 pattern OR explicit NOT_APPLICABLE
- structure_model present (levels/zones list)

**D3 — Trigger Governance**
- trigger_model present
- entry triggers list size >=1 OR explicit NOT_APPLICABLE
- triggers must have stable IDs and categories

**D4 — Confirmation & Condition Governance**
- confirmations list size >=1 OR explicit NOT_APPLICABLE
- conditions are declared either:
  - directly (if StrategyPolicyV2 exposes them), OR
  - indirectly via “Required Confirmations/Conditions” section in notes (until schema supports first-class conditions)
- minimum confirmations cover: data quality, liquidity/spread, level behavior, volume/rvol (when applicable)

**D5 — Execution & Intrabar Authority**
- execution_model present
- intrabar_execution present and declared APPLICABLE/NOT_APPLICABLE
- if intrabar applicable: phase specs + timeframe map + cadence rules + safety throttles
- if intrabar not applicable: explicit declaration + rationale

**D6 — Risk Governance**
- risk_model present
- safety_model present with >=1 rule OR explicit NOT_APPLICABLE
- session reference law present where pct-change/gap semantics matter

**D7 — Position Management Governance**
- position_management present (scale/add/partials/avg-down doctrine)
- trailing_model present with >=1 rule OR explicit NOT_APPLICABLE
- exit_model present with >=1 rule OR explicit NOT_APPLICABLE

**D8 — Data Governance**
- data_requirements present with non-empty required_fields
- required_fields must include at minimum: symbol, last_price, and at least one of (pct_change, volume) depending on style
- notes must define pause/reject behavior on missing required fields

**D9 — Failure Modes & Safety Escalation**
- policy must contain explicit failure-mode handling either via:
  - safety_model rules, and/or
  - intrabar safety throttles, and/or
  - policy notes describing escalation decisions
- “default-only” policies fail here

## Verdict Model
Per domain: PASS / FAIL / NOT_APPLICABLE (only allowed if explicitly declared and justified).

Overall strategy verdict:
- CERTIFIED: all required domains PASS; no CRITICAL control failures
- CONDITIONALLY_CERTIFIED: only MINOR controls missing; none are CRITICAL
- FAIL: any CRITICAL control missing; or “default-only” detected

## Extensibility Rules
- New controls must be added with:
  - stable control ID
  - severity (CRITICAL/MAJOR/MINOR)
  - deterministic evaluation method
- Existing control IDs may never be repurposed.
