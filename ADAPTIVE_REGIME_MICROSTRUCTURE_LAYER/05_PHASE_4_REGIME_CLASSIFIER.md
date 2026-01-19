# Phase 4 — Regime Classifier (Rules + Probabilistic Scoring)
Last updated: 2026-01-19

## Objective
Convert features + baselines into a RegimeSnapshot with explainable evidence.

## Deliverables
1) src/regime/classifier.py
Implement RegimeClassifier that returns:
- RegimeSnapshot(label, confidence, evidence, flags)

2) Classification approach (deterministic, explainable)
Two-stage approach:

Stage A — hard gates (data quality)
- If liquidity_thin_flag is true in AFTER session: label AFTER_HOURS_THIN, confidence 0.9
- If pct_missing_prices > 0.5: label UNKNOWN, confidence 0.4, include evidence
- If spreads are extreme (median_spread_bps > threshold): label HIGH_VOL_RISK_OFF

Stage B — scored candidates (soft)
Compute a score per label using z-scores relative to baselines:
- opening_momentum_score uses session==REGULAR + median_gap_pct + median_rvol + range_expansion_proxy
- chop_low_vol_score uses low volatility proxy + low spreads + low rvol
- trending_score uses momentum proxy + directionality if available
- news_driven_score uses news_density_proxy relative to baseline

Convert max score to confidence using a stable mapping (fixed parameters; deterministic).

3) Evidence
Return top 5 evidence items:
- feature value
- baseline reference
- contribution sign/magnitude
- short note

4) Tests
Add tests/test_regime_classifier.py:
- Fixed features produce expected label and confidence ordering.
- Edge cases: missing data yields UNKNOWN deterministically.

## Acceptance criteria
- RegimeClassifier produces the same snapshot given same inputs across runs.
