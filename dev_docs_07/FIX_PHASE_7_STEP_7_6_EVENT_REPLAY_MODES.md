# PHASE 7 — EVENT SYSTEM HARDENING
## FIX STEP 7.6 — EVENT REPLAY MODES (CYCLE / ALL / OFF)

You are Codex operating on the IBKR Trading System repository.

Your task is to introduce **explicit, configuration-driven event replay modes**
so that replay behavior is **intentional, deterministic, and safe**, especially
as the system progresses toward live capability.

This step finalizes the event system by preventing accidental or misleading replays.

---

## OBJECTIVE

You will:

- Introduce a configurable EVENT_REPLAY_MODE
- Support three explicit replay modes:
  - OFF   → no replay
  - CYCLE → replay most recent cycle only
  - ALL   → replay all recorded events
- Enforce safe defaults for SIM vs LIVE
- Ensure replay behavior is clear, logged, and deterministic
- Avoid any broker logic or side effects

---

## FILES TO MODIFY (ONLY THESE)

- `src/config/trading_config.py`
- `src/core/event_collector.py`
- `src/core/orchestrator.py`

Do NOT modify any other files.

---

## STEP 1 — ADD REPLAY MODE CONFIGURATION

Modify:

📄 `src/config/trading_config.py`

Add the following configuration:

```python
# Event replay behavior
# OFF   → no replay
# CYCLE → replay most recent cycle events
# ALL   → replay all recorded events (teaching/debug only)

EVENT_REPLAY_MODE = "CYCLE"
