# Step 3 — Codex Master Instruction Block (Copy/Paste)
Date: 2026-01-22

You are implementing **Step 3: Rewire Ross via an Adapter Only**.

## Read First
- `03_00_REWIRE_ROSS_ADAPTER_ONLY.md` (authoritative)

## Absolute Constraints
- No Ross logic changes (thresholds/rules/behaviour).
- Prefer zero-touch in `src/strategies/ross_momentum/**` (adapter should live in `src/strategy_portfolio/adapters/`).
- No scanner, execution, or risk engine changes.
- Orchestrator edits allowed only for minimal routing and must preserve behaviour.

## Required Work (Execute in Order)
1. Recon: identify current Ross decision output and wiring path.
2. Implement additive adapter in `src/strategy_portfolio/adapters/ross_momentum_adapter.py`.
3. Add unit tests for adapter and fail-safe defaults.
4. Minimal rewire: route Ross outputs through adapter without changing behaviour.
5. Create/update BOTH verification reports:
   - `PR_VERIFICATION_REPORT.md`
   - `docs/PR_VERIFICATION_REPORT.md`
6. Run and capture outputs for Mandatory Verification Commands (ALL must pass):
   1) `python -m compileall -q src`
   2) `pytest -q`
   3) `python -m src.main --mode SIM --cycles 1`
   4) `python -m src.main --mode READONLY --cycles 1`
   5) `python -m src.main --mode PAPER --cycles 1`
   6) `python -m src.main --mode LIVE_MICRO --cycles 1`
   7) LIVE_MICRO with explicit ACK env vars for 1 share (cycles 2–3)

## Final Output Required
- List of files added/changed (paths only)
- The captured outputs for each command (or stored logs + excerpt references)
- Confirmation Ross remains live-ready and behaviour unchanged
