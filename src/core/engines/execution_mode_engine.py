from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionModeConfig:
    execution_mode: str
    primary_timeframe: str
    refinement_timeframe: str


EXECUTION_MODES: dict[str, dict[str, str]] = {
    "PRE": {
        "execution_mode": "STRICT",
        "primary_timeframe": "1m",
        "refinement_timeframe": "10s",
    },
    "RTH_OPEN": {
        "execution_mode": "STRICT",
        "primary_timeframe": "1m",
        "refinement_timeframe": "10s",
    },
    "RTH_MID": {
        "execution_mode": "NORMAL",
        "primary_timeframe": "3m",
        "refinement_timeframe": "30s",
    },
    "RTH_LATE": {
        "execution_mode": "CONSERVATIVE",
        "primary_timeframe": "5m",
        "refinement_timeframe": "1m",
    },
    "AH": {
        "execution_mode": "BLOCKED",
        "primary_timeframe": "5m",
        "refinement_timeframe": "1m",
    },
}


class ExecutionModeEngine:
    """Assign execution mode/timeframe profile from session + liquidity context."""

    _SESSION_ALIAS: dict[str, str] = {
        "": "PRE",
        "PRE": "PRE",
        "PREMARKET": "PRE",
        "RTH": "RTH_OPEN",
        "REG": "RTH_OPEN",
        "REGULAR": "RTH_OPEN",
        "RTH_OPEN": "RTH_OPEN",
        "RTH_MID": "RTH_MID",
        "RTH_LATE": "RTH_LATE",
        "AH": "AH",
        "AFTER": "AH",
        "AFTER_HOURS": "AH",
    }

    def normalize_session(self, session_label: str | None) -> str:
        normalized = str(session_label or "").strip().upper()
        return self._SESSION_ALIAS.get(normalized, "PRE")

    def _is_context_incomplete(self, context: Any) -> bool:
        rvol = getattr(context, "rvol", None)
        spread = getattr(context, "spread", None)

        return rvol is None or spread is None

    def _as_float(self, value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    def apply(self, intent: Any, context: Any) -> Any:
        session_label = getattr(context, "session", None) or getattr(context, "session_context", None)
        session = self.normalize_session(session_label)
        config = EXECUTION_MODES[session]

        # 🔥 NEW: context fallback
        if self._is_context_incomplete(context):
            print("[EXECUTION_FALLBACK] incomplete_context → bypass_strict_checks")
            intent.execution_mode = "FALLBACK"
            intent.execution_primary_timeframe = config["primary_timeframe"]
            intent.execution_refinement_timeframe = config["refinement_timeframe"]
            return intent

        rvol = self._as_float(getattr(context, "rvol", None)) or 0.0
        spread = self._as_float(getattr(context, "spread", None)) or 0.0

        intent.execution_mode = config["execution_mode"]
        intent.execution_primary_timeframe = config["primary_timeframe"]
        intent.execution_refinement_timeframe = config["refinement_timeframe"]

        # Keep strict live validation semantics.
        if session == "PRE":
            if rvol < 2.0 or spread > 0.12:
                intent.execution_mode = "REJECTED"
                intent.execution_block_reason = "PRE_STRICT_REJECTION"
                return intent

        if session == "AH":
            intent.execution_mode = "REJECTED"
            intent.execution_block_reason = "AH_BLOCKED"
            return intent

        if session == "RTH_LATE":
            intent.execution_mode = "REJECTED"
            intent.execution_block_reason = "RTH_LATE_BLOCKED"
            return intent

        if session == "RTH_MID" and (rvol < 1.5 or spread > 0.15):
            intent.execution_mode = "DOWNGRADED"
            intent.execution_primary_timeframe = "5m"
            intent.execution_refinement_timeframe = "1m"
            intent.execution_block_reason = "RTH_MID_DOWNGRADE"
            return intent

        return intent
