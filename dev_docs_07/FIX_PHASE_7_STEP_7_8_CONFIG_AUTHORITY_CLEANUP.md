FIX_PHASE_7_STEP_7_8_CONFIG_AUTHORITY_CLEANUP

GOAL
Unify configuration authority for runtime safety and replay behaviour.
There must be ONE authoritative source for RUN_MODE and ONE authoritative
resolver for EVENT_REPLAY_MODE. Eliminate contradictory boot banners and
remove duplicated or misleading configuration variables.

AFTER THIS CHANGE:
- RUN_MODE is defined and resolved ONLY by runtime_config.py
- EVENT_REPLAY_MODE is resolved ONLY by system_config.py
- LIVE mode MUST always force EVENT_REPLAY_MODE=OFF
- trading_config.py MUST NOT define or influence runtime mode
- main.py MUST print resolved (actual) values, not baselines
- Orchestrator must never crash due to LIVE + replay mismatch

---

STEP 1 — CLEAN UP trading_config.py
ACTION:
- Remove any RUN_MODE variable or logic from trading_config.py
- trading_config.py may ONLY contain trading logic (strategies, thresholds, risk caps)
- If a teaching comment exists, clarify that runtime mode is owned by runtime_config

ACCEPTANCE:
- Searching trading_config.py for "RUN_MODE" returns nothing

---

STEP 2 — MAKE runtime_config.py THE SINGLE SOURCE OF TRUTH
ACTION:
Replace runtime_config.py with an authoritative resolver.

IMPLEMENT EXACTLY:

"""
Define the runtime safety mode for the trading system.
Single source of truth for SIM / PAPER / LIVE.
"""

from __future__ import annotations
import os
from enum import Enum


class RunMode(str, Enum):
    SIM = "SIM"
    PAPER = "PAPER"
    LIVE = "LIVE"


DEFAULT_RUN_MODE: RunMode = RunMode.SIM


def get_run_mode() -> RunMode:
    """
    Authoritative runtime mode resolver.

    Resolution order:
    1) ENV: RUN_MODE
    2) DEFAULT_RUN_MODE (SIM)
    """
    raw = (os.getenv("RUN_MODE") or "").strip().upper()
    if not raw:
        return DEFAULT_RUN_MODE

    try:
        return RunMode(raw)
    except ValueError:
        print(f"[RUNTIME] Invalid RUN_MODE='{raw}'. Falling back to SAFE default SIM.")
        return RunMode.SIM

ACCEPTANCE:
- RUN_MODE unset → SIM
- RUN_MODE=LIVE → LIVE
- RUN_MODE=banana → SIM with warning

---

STEP 3 — MOVE REPLAY AUTHORITY TO system_config.py
ACTION:
system_config.py controls replay behaviour and must enforce safety.

IMPLEMENT EXACTLY:

"""
System-level configuration (logging, replay, persistence).
"""

from __future__ import annotations
import os
from enum import Enum
from .runtime_config import RunMode


class EventReplayMode(str, Enum):
    OFF = "OFF"
    CYCLE = "CYCLE"
    RUN = "RUN"


DEFAULT_EVENT_REPLAY_MODE: EventReplayMode = EventReplayMode.CYCLE


def get_event_replay_mode(run_mode: RunMode) -> EventReplayMode:
    """
    Resolve replay mode safely.

    RULES:
    - LIVE always forces OFF
    - SIM / PAPER allow ENV override
    """
    if run_mode == RunMode.LIVE:
        return EventReplayMode.OFF

    raw = (os.getenv("EVENT_REPLAY_MODE") or "").strip().upper()
    if not raw:
        return DEFAULT_EVENT_REPLAY_MODE

    try:
        return EventReplayMode(raw)
    except ValueError:
        print(
            f"[SYSTEM] Invalid EVENT_REPLAY_MODE='{raw}'. "
            f"Falling back to default {DEFAULT_EVENT_REPLAY_MODE}."
        )
        return DEFAULT_EVENT_REPLAY_MODE

ACCEPTANCE:
- RUN_MODE=LIVE → replay OFF (always)
- SIM/PAPER → replay defaults to CYCLE unless overridden
- Invalid replay values fall back safely

---

STEP 4 — FIX CoreOrchestrator TO USE RESOLVERS
ACTION:
Update orchestrator initialisation to use authoritative resolvers.

IMPLEMENT LOGIC:
- run_mode = get_run_mode()
- replay_mode = get_event_replay_mode(run_mode)
- Keep RuntimeError guard, but it should never trigger with correct resolution

PSEUDOCODE (must be reflected in implementation):

from config.runtime_config import get_run_mode, RunMode
from config.system_config import get_event_replay_mode, EventReplayMode

self.run_mode = get_run_mode()
self.replay_mode = get_event_replay_mode(self.run_mode)

if self.run_mode == RunMode.LIVE and self.replay_mode != EventReplayMode.OFF:
    raise RuntimeError("Replay must be OFF in LIVE mode")

ACCEPTANCE:
- LIVE starts cleanly with replay OFF
- No crash caused by replay resolution

---

STEP 5 — FIX main.py BOOT BANNER
ACTION:
main.py must print RESOLVED values only.

REPLACE any baseline/bogus printing with:

- RUN_MODE from get_run_mode()
- EVENT_REPLAY_MODE from get_event_replay_mode(run_mode)

TARGET OUTPUT STYLE:

[CONFIG] Resolved runtime configuration:
  - RUN_MODE: LIVE
  - EVENT_REPLAY_MODE: OFF (forced by LIVE)
  - CYCLE_SLEEP_SECONDS: 3
  - ACTIVE_SESSIONS: PRE, REGULAR, AFTER

ACCEPTANCE:
- No contradictory banner lines
- What is printed matches actual runtime behaviour

---

FINAL SAFETY GUARANTEES
- Default is always SIM
- LIVE can never replay events
- One source of truth per responsibility
- Teaching clarity preserved without runtime ambiguity

END FIX_PHASE_7_STEP_7_8_CONFIG_AUTHORITY_CLEANUP
