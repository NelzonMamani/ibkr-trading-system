# 10_11_PHASE_10_DIVIDENDS_COMPOUND.md — PHASE 10: DIVIDENDS & COMPOUNDING

Goal:
- Track dividends and optionally propose reinvestment via the same intent pipeline.

Codex tasks:
1) Ingest dividends history and upcoming events (provider already used in fundamentals phase).
2) Record dividend receipts in storage (or derive from broker statements if available in system).
3) If DIVIDEND_REINVESTMENT_ENABLED:
   - propose reinvestment intents into highest-priority Focus/Owned names (policy-driven)
   - obey the same capital and risk rules

Tests:
- Dividend reinvestment never exceeds MAX_NEW_ALLOCATION_PCT.
- If reinvestment disabled, phase emits report only.

END
