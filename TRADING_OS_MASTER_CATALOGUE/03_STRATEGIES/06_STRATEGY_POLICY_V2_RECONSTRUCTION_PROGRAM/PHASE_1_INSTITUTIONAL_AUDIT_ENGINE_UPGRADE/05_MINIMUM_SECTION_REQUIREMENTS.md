# Minimum Section Requirements (Institutional Baseline)

This document defines **minimum counts** and **required primitives** that must exist for a policy to be treated as non-placeholder.

## Global Minimums (All Strategies)
- Identity present: yes
- Risk model present: yes
- Execution model present: yes
- Data requirements present with required_fields non-empty: yes

## Intraday Strategies (Default)
### Must have (minimum counts)
- Setup families: >= 1
- Triggers: >= 1
- Confirmations: >= 1
- Exit rules: >= 1
- Safety rules OR safety throttles: >= 1
- Required fields: >= 8 (symbol, price, volume-related, and structure fields)

### Must include (minimum primitives)
- Data quality gate (confirmation or safety rule)
- Spread/liquidity feasibility gate (confirmation or safety rule)
- Failure fast / bailout rule (exit rule or intrabar override doctrine)
- Session semantics and CLOSED behavior documented

## Non-Intraday / Positional Strategies (Allowed)
These strategies may declare:
- INTRABAR: NOT_APPLICABLE
- certain confirmations/triggers NOT_APPLICABLE

But they must still provide:
- setup taxonomy (even if high-level)
- entry trigger concept (even if time-based)
- exit/risk rules (portfolio-level)

## Explicit Threshold Overrides
A strategy may override thresholds only if it explicitly states in notes:
- why the domain is N/A
- what alternative governance mechanism exists

Example:
- “Confirmations: NOT_APPLICABLE — entries are scheduled at close using end-of-day data; validation occurs in data requirements and risk model.”

## Implementation Hook
Codex must implement these minimums in:
- audit engine
- metadata tests (pytest)
