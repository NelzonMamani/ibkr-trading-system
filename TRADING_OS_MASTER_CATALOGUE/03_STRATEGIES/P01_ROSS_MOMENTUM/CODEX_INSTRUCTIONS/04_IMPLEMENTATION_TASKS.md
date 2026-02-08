# FILE: 04_IMPLEMENTATION_TASKS.md
# TITLE: Implementation Tasks for Ross Certification
Date: 2026-02-08

## Task 1 — Policy completeness
- Update `strategies/ross_momentum/strategy_policy.py`:
  - Add explicit ALLOWED/DENIED SF lists.
  - Add XL mapping and classification.
  - Add REQUIRED_C and REQUIRED_K mappings.
  - Add candlestick pattern usage lists and guard specs.
  - Ensure ALL numeric thresholds are policy parameters.

## Task 2 — Context completeness
- Verify `strategy_context_schema.py` includes:
  - mode/session_phase
  - required candle streams per timeframe plan
  - required levels/zones
  - indicators: VWAP, EMAs (and optional MACD if required)
  - pattern primitives outputs (SCP/MCP attributes)

Add fields additively if missing.

## Task 3 — Runner enforcement
- Ensure runner evaluates:
  1) REQUIRED_C hard gates
  2) REQUIRED_K confirmations
  3) XL triggers
  4) Emits TradeIntent with SF/XL and trace payload

## Task 4 — Tests
Add unit tests (strategy-local) to prove:
- SF/XL mappings exist and are complete (no partial)
- key guard behaviours (topping pause/halt, micro pullback trigger mapping)
- policy parameters are used (no hidden constants)

## Task 5 — Verification and report
Run mandatory commands (see 05_MANDATORY_VERIFICATION.md) and create/append `PR_VERIFICATION_REPORT.md` describing outcomes.

END
