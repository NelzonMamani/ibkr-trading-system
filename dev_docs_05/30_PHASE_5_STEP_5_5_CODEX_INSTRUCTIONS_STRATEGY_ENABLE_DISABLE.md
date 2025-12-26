# PHASE 5 — STRATEGY GOVERNANCE
## STEP 5.5 — STRATEGY ENABLE / DISABLE VIA CONFIGURATION

You are Codex operating on the IBKR Trading System repository.

Your task is to implement **configuration-based strategy enable/disable controls** so that strategies can be turned ON or OFF **without modifying strategy code**.

This step introduces **institutional-grade strategy governance** and is REQUIRED before any capital allocation, lifecycle tracking, or portfolio governance.

You must assume:
- Previous steps MAY be partially implemented or missing
- Your instructions must be safe to apply idempotently
- Configuration must be the single source of truth

---

## GLOBAL OBJECTIVE

Enable or disable trading strategies at runtime via configuration, while ensuring:

- Deterministic behaviour
- Teaching-first clarity
- No strategy class logic is modified
- The system continues running safely if strategies are disabled
- Logging clearly reflects governance decisions

---

## LOCAL OBJECTIVES

You will:

1. Define a configuration switch for each strategy
2. Ensure disabled strategies are fully skipped
3. Ensure missing strategies default to DISABLED
4. Prevent disabled strategies from producing TradeIntents
5. Preserve existing orchestration flow

---

## FILES YOU ARE ALLOWED TO MODIFY

Modify **only** the following files:

- `src/config/trading_config.py`
- `src/strategy/strategy_runner.py`

❌ Do NOT modify:
- Individual strategy classes
- Orchestrator
- Risk engine
- Execution engine

---

## STEP 1 — ADD STRATEGY ENABLE / DISABLE CONFIGURATION

Open the file:

`src/config/trading_config.py`

If the file already exists, extend it safely.
If the configuration already exists, ensure it matches EXACTLY.

Add (or ensure the presence of) the following block:

```python
# ==========================================================
# Strategy enable / disable governance
# True  = strategy allowed to run
# False = strategy skipped entirely
# ==========================================================

ENABLED_STRATEGIES = {
    "GapAndGoStrategy": True,
    "MomentumContinuationStrategy": True,
}
