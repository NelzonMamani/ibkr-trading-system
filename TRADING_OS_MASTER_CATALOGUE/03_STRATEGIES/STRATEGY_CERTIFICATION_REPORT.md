# STRATEGY_CERTIFICATION_REPORT

Generated (UTC): 2026-02-18T17:24:27.512714+00:00

## Scope & Inputs
- Policies audited: `src/strategies/*/strategy_policy_v2.py`
- Template baseline: `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/04_STRATEGY_CERTIFICATION_AND_GOVERNANCE/STRATEGY_CERTIFICATION_TEMPLATE.md`
- Checklist baseline: `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/04_STRATEGY_CERTIFICATION_AND_GOVERNANCE/STRATEGY_CERTIFICATION_CHECKLIST.json`
- Audit matrix updated: `TRADING_OS_MASTER_CATALOGUE/03_STRATEGIES/04_STRATEGY_CERTIFICATION_AND_GOVERNANCE/STRATEGY_AUDIT_MATRIX.md`

## Summary Verdict
- CERTIFIED: 1
- CONDITIONALLY CERTIFIED: 0
- FAIL: 19

| Strategy | ID | Status | Setup Families | Triggers | Confirmations | Exit Rules | Position Mgmt | Safety Rules | Data Requirements | Intrabar Doctrine |
|---|---:|---|---:|---:|---:|---:|---|---:|---:|---:|
| `ross_momentum` | P01 | **CERTIFIED** | 27 | 18 | 20 | 5 | Defined | 1 | 1 | 1 |
| `statistical_intraday_momentum` | P02 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `mean_reversion` | P03 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `long_horizon_value` | P04 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `opening_drive` | P05 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `vwap_reclaim` | P06 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `power_hour` | P07 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `volatility_expansion` | P08 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `range_bound_fade` | P09 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `support_resistance_channel` | P10 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `event_earnings_reaction` | P11 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `event_news_shock_continuation` | P12 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `volatility_contraction_breakout` | P13 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `volatility_carry_risk_premium` | P14 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `pairs_divergence_reversion` | P15 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `cross_sectional_relative_strength_rotation` | P16 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `time_based_seasonality` | P17 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `trend_following_classic` | P18 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `long_horizon_quality_compounder` | P19 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |
| `regime_adaptive_meta_allocator` | P20 | **FAIL** | 0 | 0 | 0 | 0 | Default-only | 0 | 0 | 0 |

## P01 — ross_momentum
1. **Certification Status:** CERTIFIED
2. **Missing Sections:** None detected against checklist minima.
3. **Risk Governance Gaps:** None material.
4. **Execution Governance Gaps:** None material.
5. **Structural Coverage Gaps:** None material.
6. **Recommended SPEC-ONLY Additions:** No additions required.

## P02 — statistical_intraday_momentum
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P03 — mean_reversion
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P04 — long_horizon_value
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P05 — opening_drive
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P06 — vwap_reclaim
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P07 — power_hour
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P08 — volatility_expansion
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P09 — range_bound_fade
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P10 — support_resistance_channel
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P11 — event_earnings_reaction
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P12 — event_news_shock_continuation
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P13 — volatility_contraction_breakout
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P14 — volatility_carry_risk_premium
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P15 — pairs_divergence_reversion
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P16 — cross_sectional_relative_strength_rotation
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P17 — time_based_seasonality
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P18 — trend_following_classic
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P19 — long_horizon_quality_compounder
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.

## P20 — regime_adaptive_meta_allocator
1. **Certification Status:** FAIL
2. **Missing Sections:** Setup Families; Triggers; Confirmations; Exit Model rules; Position Management specifics; Data Requirements; Safety Rules; Intrabar doctrine (where applicable).
3. **Risk Governance Gaps:** No explicit safety-rule set (halt/spread/volatility fail-safe declarations absent). No explicit hard-exit doctrine beyond framework defaults. Position sizing/add/partial policies remain default and uncalibrated.
4. **Execution Governance Gaps:** No executable trigger entry specification. No explicit confirmation layer. No intrabar cadence/timeframe authority declaration.
5. **Structural Coverage Gaps:** Setup taxonomy missing. Data contract is not strategy-specific. Failure-mode termination/exit map not concretely enumerated.
6. **Recommended SPEC-ONLY Additions:** Add named setup families with explicit thesis and timeframe scope. Add trigger + confirmation IDs mapped to setup families. Add explicit exit-rule catalog (hard exits + discretionary governance notes). Add strategy-specific position management doctrine (scale, partials, averaging constraints). Add required/optional data field contracts and quality gates. Add safety-rule matrix (halts, spread blowout, stale feed, liquidity vacuum). Declare intrabar doctrine explicitly as APPLICABLE/NOT_APPLICABLE with rationale.
