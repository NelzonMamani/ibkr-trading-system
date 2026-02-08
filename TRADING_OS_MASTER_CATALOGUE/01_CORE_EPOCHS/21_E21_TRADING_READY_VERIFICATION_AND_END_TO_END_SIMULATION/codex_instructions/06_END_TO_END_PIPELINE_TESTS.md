# 06_END_TO_END_PIPELINE_TESTS

Codex must verify the full pipeline:

Market Data → Scanner → Watchlist → Focus → Strategy Runner
→ Intents → Risk Engine → Execution Engine → Position Lifecycle → Exit → Audit

Required:
- Deterministic SIM replay
- Recorded historical replay
- Evidence of correct state transitions

Any divergence without explanation FAILS.
