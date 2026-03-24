# P01 Trigger Activation — Before vs After

## Before (no trigger)
- Case: `price=10.19`, `HOD=10.30`, `PREMARKET_HIGH=10.25`, `rvol=1.6`, `pct_change=4.0`.
- Observed outcome: fast-path emits `[ROSS][TRIGGER_SKIP]` and no fast trigger is attached.

## After (trigger + override)
- Case: `price=10.34`, `HOD=10.30`, `PREMARKET_HIGH=10.25`, `rvol=2.6`, `pct_change=11.2`.
- Observed outcome: fast-path emits:
  - `[ROSS][TRIGGER_OVERRIDE] reason=HIGH_MOMENTUM_BREAK`
  - `[ROSS][TRIGGER] trigger_type=HOD_BREAK_FAST ...`
- The strategy then emits an intent (`DecisionType.EMIT_INTENT`) through normal decision policy.

## Evidence
- Raw log capture: `sample_trigger_logs.txt`.
