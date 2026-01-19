# Adaptive Regime / Microstructure Layer

## Purpose
The Adaptive Regime / Microstructure Layer is a deterministic, sandboxed module that:
- Observes market regime conditions from existing scanner inputs.
- Produces a structured `RegimeSnapshot` artifact each cycle.
- Optionally applies a *non-mutating* policy (weights/eligibility/risk multipliers).
- Emits explicit regime events for audit and replay.

The layer never places orders, never mutates strategy rules, and never bypasses Risk.

## Pipeline position
```
Scanner → Patterns → Signals → Regime Layer → Strategy → Risk → Execution → Storage
```

## How to enable (SIM and LIVE_READ_ONLY)
### SIM (policy off)
```
python -m src.main --mode SIM --strategy ross_momentum --cycles 1 --regime-layer
```

### SIM (policy on)
```
python -m src.main --mode SIM --strategy ross_momentum --cycles 1 --regime-layer --regime-policy
```

### LIVE_READ_ONLY (policy off)
```
python -m src.main --mode READONLY --strategy ross_momentum --cycles 1 --regime-layer
```

### LIVE_READ_ONLY (policy on)
```
python -m src.main --mode READONLY --strategy ross_momentum --cycles 1 --regime-layer --regime-policy
```

## Events and storage
The layer emits:
- `REGIME_SNAPSHOT` (always when enabled)
- `REGIME_POLICY_DECISION` (only when policy is enabled)

Artifacts are stored on each cycle in `trade_records.regime_snapshot_json` and
`trade_records.regime_policy_decision_json`.

Use the helper to inspect snapshots:
```
python -m src.tools.regime_dump --limit 20
```

## Configuration keys
Tuning and safe defaults are in `src/config/config_registry.py`:
- `ADAPTIVE_REGIME_LAYER_ENABLED`
- `ADAPTIVE_REGIME_POLICY_ENABLED`
- `ADAPTIVE_REGIME_MIN_CONFIDENCE_TO_APPLY`
- `ADAPTIVE_REGIME_STRATEGY_WEIGHTING_MODE` (OFF | WEIGHT | ENABLE_DISABLE)
- `ADAPTIVE_REGIME_MAX_RISK_MULTIPLIER`
- `ADAPTIVE_REGIME_MIN_RISK_MULTIPLIER`
- `ADAPTIVE_REGIME_ALLOWED_RISK_MULTIPLIERS`
- `ADAPTIVE_REGIME_ALLOWED_STRATEGY_WEIGHTS`
- `ADAPTIVE_REGIME_ALLOWED_SESSIONS`
- `ADAPTIVE_REGIME_FEATURE_SET` (BASIC | EXTENDED)
- `ADAPTIVE_REGIME_BASELINE_WINDOW`
- `ADAPTIVE_REGIME_EWMA_ALPHA`
- `ADAPTIVE_REGIME_LOG_LEVEL`

## Determinism notes
- The layer uses only existing artifacts (scanner candidates, session labels).
- Feature aggregation is ordered and stable.
- Baselines update once per cycle in a fixed order.
- No randomness is introduced; identical inputs yield identical outputs.

## Developer tuning
Regime rules live in:
- `src/regime/observers.py` (feature extraction)
- `src/regime/baselines.py` (rolling + EWMA baselines)
- `src/regime/classifier.py` (regime classification + evidence)
- `src/regime/policy.py` (policy decisions + bounds)

Keep all changes deterministic and ensure new fields are logged, emitted as events,
and persisted in TradeRecord.
