# P03 — CODEX INSTRUCTIONS — 03_ALLOWED_CHANGES (Additive-only)
Allowed:
- Patch/extend existing P03 strategy policy files and helpers under `src/strategies/mean_reversion/`
- Add/update strategy-local unit tests under that strategy folder
- Add wiring adapters needed for E19 interface compliance

Not allowed:
- Redesigning OS components (scanner/risk/execution/storage)
- Introducing new canonical IDs or renaming canon IDs
- Bypassing E16 no-trade contexts

END
