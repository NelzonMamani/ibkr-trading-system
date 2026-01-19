# Phase 3 — Statistical Baselines (Rolling / EWMA)
Last updated: 2026-01-19

## Objective
Maintain rolling baselines for key continuous features to support relative regime detection.

## Deliverables
1) src/regime/baselines.py
Implement BaselineStore with:
- rolling window (size ADAPTIVE_REGIME_BASELINE_WINDOW)
- EWMA (alpha ADAPTIVE_REGIME_EWMA_ALPHA)
- deterministic quantiles via sorting window

Store per-feature:
- rolling_mean, rolling_std (population std)
- ewma_mean
- q25, q50, q75

2) Persistence strategy (safe + deterministic)
- Persist baselines in SQLite via existing StorageEngine if feasible, otherwise a small versioned JSON under data/.

3) Update cadence
- Update baselines once per cycle after feature extraction.
- Default: do update even when market is CLOSED, but record session label in snapshot.

4) Tests
Add tests/test_regime_baselines.py:
- Deterministic baseline updates given fixed feature sequence.
- Quantile correctness for known data.
- EWMA update correctness.

## Acceptance criteria
- Baselines update deterministically across multiple SIM cycles.
