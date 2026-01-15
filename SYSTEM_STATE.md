# SYSTEM_STATE.md
# SYSTEM STATE (SINGLE SOURCE OF TRUTH)

## Current status (authoritative)
- Repository: `ibkr-trading-system`
- Governance: `SYSTEM_CONSTITUTION.md` is frozen and authoritative.
- Roadmap: `SYSTEM_ROADMAP_EPOCH_02_TO_COMPLETION.md` is frozen.

## Epoch progress
- Epoch 1 — Market Perception: COMPLETE
- Epoch 2 — Decision Intelligence: COMPLETE (Phases 25–30 implemented)
- Epoch 3 — Risk & Execution: COMPLETE (Phases 31–34 implemented)

## What is enabled right now
- Market data: allowed in LIVE_READ_ONLY when configured
- Execution: HARD DISABLED by default; order routing must remain blocked until Epoch 3 governance explicitly permits it
- Replay: locked down in LIVE/LIVE_READ_ONLY/LIVE_MICRO by safety policy

## Immediate next actions (authoritative)
1) Prepare Epoch 4 governance and phase definitions
2) Validate storage and replay readiness for Trade Storage Canonical Schema
3) Maintain safety self-tests as Epoch 4 work begins

## Notes
- Any discrepancy between code and this file must be resolved in favour of this file.
- `README.md` may be updated for clarity but cannot override governance.

Last updated: 2026-01-15 (America/New_York reference date)
