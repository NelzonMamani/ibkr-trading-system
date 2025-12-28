# FIX_PHASE_7_STEP_7_7_REPLAY_LOCKDOWN_LIVE_MODE.md

## PHASE 7 — EVENT SYSTEM HARDENING
## STEP 7.7 — HARD LOCK EVENT REPLAY IN LIVE MODE

You are **Codex**, operating on the **IBKR Trading System** repository.

Your task is to **strictly forbid event replay when the system is running in LIVE mode**.
This is a non-negotiable institutional safety rule.

Replay is allowed ONLY in SIM or PAPER modes.

---

## GLOBAL OBJECTIVE

Guarantee that:
- Event replay can NEVER occur in LIVE trading
- Misconfiguration is caught immediately at startup
- Safety rules are enforced centrally
- Deterministic behavior is preserved

---

## LOCAL OBJECTIVES

You will:
- Enforce replay lockdown at orchestrator boot time
- Prevent replay execution paths from running in LIVE mode
- Fail fast with a clear error message
- Avoid changing behavior for SIM or PAPER modes
- Modify ONLY the orchestrator

---

## FILES YOU ARE ALLOWED TO MODIFY

Modify **only** the following file:

- `src/core/orchestrator.py`

Do NOT:
- Modify any other file
- Create new files
- Add new configuration values

---

## STEP 1 — IDENTIFY REPLAY MODE RESOLUTION

Open:

`src/core/orchestrator.py`

Locate the section where replay mode is resolved and logged, similar to:

```python
self.replay_mode = resolve_replay_mode(...)
print(f"[BOOT] Event replay mode resolved — mode={self.replay_mode}")
