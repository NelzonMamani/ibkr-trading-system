# P02 — CODEX INSTRUCTIONS — 03_ALLOWED_CHANGES (Additive-only)
Allowed:
- Add or extend `src/strategies/statistical_intraday_momentum/strategy_policy.py`
- Add helper modules under that strategy folder to implement canonical mapping logic
- Add/update strategy-local tests
- Add wiring adapters if required by the strategy interface contract

Not allowed:
- Modifying core OS epochs, scanner core, execution engine, risk engine, or shared contracts (unless a certification gap is proven and isolated)
- Introducing new run modes
- Replacing canonical IDs with new names

END
