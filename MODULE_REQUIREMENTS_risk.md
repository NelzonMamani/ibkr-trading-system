# MODULE_REQUIREMENTS_risk
Last updated: 2026-01-15

## 1. Purpose
Risk is the **final authority**. It can veto any TradeIntent and must explain decisions.

## 2. Inputs
- TradeIntent(s) from strategy
- account state / limits
- market quality (spread, liquidity, halts)
- system health (OK/DEGRADED/CRITICAL)
- mode (SIM/READONLY/LIVE_1SHARE)

## 3. Output Contract: RiskDecision (Mandatory)
For each intent:
- symbol
- decision: ALLOW / BLOCK / ALLOW_WITH_CONSTRAINTS
- max_position_size_allowed (shares)
- constraints: list[str] (e.g., LIMIT_ONLY, MAX_SLIPPAGE, NO_ADDING)
- triggered_rules: list[str]
- rationale_text: short, operator-friendly
- risk_flags: list[str]
- timestamp, cycle_id

## 4. Mandatory Rule Set (Epoch 5 Minimum)
### 4.1 Mode Gating
- SIM: BLOCK all execution actions; allow “paper intents” for logging
- READONLY: BLOCK all execution actions; allow “would place” logs
- LIVE_1SHARE: allow only risk-approved execution with 1-share default sizing (unless stricter)

### 4.2 Health Gating
- If health is CRITICAL: BLOCK all intents
- If health is DEGRADED: may ALLOW_WITH_CONSTRAINTS or BLOCK depending on rules

### 4.3 Daily Loss Circuit Breaker
- Maintain realized + unrealized loss budget (config)
- If breached: set system to CRITICAL and BLOCK new entries

### 4.4 Max Trades Per Day
- Hard cap count of entries (config)
- If reached: BLOCK new entries

### 4.5 Spread / Liquidity Quality
- If spread too wide or liquidity low: BLOCK or ALLOW_WITH_CONSTRAINTS (limit-only)
- Spread limits should support absolute and percent thresholds

### 4.6 Data Quality Gating
- If required fields missing (no snapshot, stale bars, missing VWAP for VWAP-dependent setup): BLOCK
- Always explain which fields were missing

### 4.7 Setup Risk Flags
- OVEREXTENDED: reduce size or block depending on config
- FAILED_BREAKOUT: block entries; allow exit-only intents if implemented
- HALT_RISK: default block

## 5. Sizing Rules (Epoch 5)
Default for LIVE_1SHARE:
- max_position_size_allowed = 1 share for entries
- allow partial exits and stop orders as required

Risk may constrain further (e.g., “no new entries” after loss).

## 6. Logging Requirements
Every risk decision must print:
- rule name
- threshold
- observation
- decision result
- short why
This must be machine-structured and human-readable.

## 7. Tests
- Unit tests for mode law
- Unit tests for CRITICAL blocks
- Unit tests for spread/data quality blocks
- Regression tests for max trades / daily loss breaker

END.
