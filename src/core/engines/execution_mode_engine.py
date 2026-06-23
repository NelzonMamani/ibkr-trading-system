from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionModeConfig:
    execution_mode: str
    primary_timeframe: str
    refinement_timeframe: str


EXECUTION_MODES: dict[str, dict[str, str]] = {
    "PRE": {"primary": "1m", "refinement": "10s", "mode": "CONDITIONAL"},
    "RTH_OPEN": {"primary": "1m", "refinement": "10s", "mode": "AGGRESSIVE"},
    "RTH_MID": {"primary": "1m", "refinement": "10s", "mode": "NORMAL"},
    "RTH_LATE": {"primary": "5m", "refinement": "1m", "mode": "STRUCTURAL"},
    "AH": {"primary": "5m", "refinement": "1m", "mode": "LOW_LIQUIDITY"},
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

    def _is_ross_strategy(self, intent: Any, context: Any) -> bool:
        strategy_name = str(
            getattr(intent, "strategy_name", None)
            or getattr(intent, "strategy_id", None)
            or getattr(context, "strategy_name", None)
            or getattr(context, "strategy_id", None)
            or ""
        ).upper()
        return "ROSS" in strategy_name

    def _apply_fast_micro_pullback_rules(self, intent: Any, session: str, rvol: float, spread: float, is_ross: bool) -> Any:
        refinement_mode = str(getattr(intent, "execution_refinement_mode", "") or "").upper()
        if refinement_mode != "FAST_MICRO_PULLBACK":
            return intent

        if session == "RTH_LATE":
            intent.execution_refinement_mode = "NONE"
            intent.execution_block_reason = "FAST_MICRO_PULLBACK_BLOCKED_RTH_LATE"
            print("[EXECUTION_BLOCKED] FAST_MICRO_PULLBACK blocked in RTH_LATE")
            return intent

        if session == "AH" and is_ross:
            intent.execution_refinement_mode = "NONE"
            intent.execution_block_reason = "FAST_MICRO_PULLBACK_BLOCKED_AH_ROSS"
            print("[EXECUTION_BLOCKED] FAST_MICRO_PULLBACK blocked in AH for Ross")
            return intent

        if session == "PRE" and (rvol < 2.0 or spread > 0.12):
            intent.execution_refinement_mode = "NONE"
            intent.execution_block_reason = "FAST_MICRO_PULLBACK_BLOCKED_PRE_LIQUIDITY"
            print("[EXECUTION_BLOCKED] FAST_MICRO_PULLBACK blocked in PRE due to liquidity")
            return intent

        if session == "RTH_MID" and (rvol < 1.5 or spread > 0.15):
            intent.execution_refinement_mode = "MICRO_PULLBACK"
            intent.execution_block_reason = "FAST_MICRO_PULLBACK_DOWNGRADED_RTH_MID"
            print("[EXECUTION_DOWNGRADE] FAST_MICRO_PULLBACK -> MICRO_PULLBACK in RTH_MID")
            return intent

        return intent

    def apply(self, intent: Any, context: Any) -> Any:
        session_label = getattr(context, "session", None) or getattr(context, "session_context", None)
        session = self.normalize_session(session_label)
        config = EXECUTION_MODES[session]

        # 🔥 NEW: context fallback
        if self._is_context_incomplete(context):
            print("[EXECUTION_FALLBACK] incomplete_context -> bypass_strict_checks")
            intent.execution_mode = "FALLBACK"
            intent.execution_primary_timeframe = config["primary"]
            intent.execution_refinement_timeframe = config["refinement"]
            print(f"[EXECUTION_MODE] {intent.execution_mode}")
            print(f"[EXECUTION_REFINEMENT] {intent.execution_refinement_timeframe}")
            return intent

        rvol = self._as_float(getattr(context, "rvol", None)) or 0.0
        spread = self._as_float(getattr(context, "spread", None)) or 0.0

        intent.execution_mode = config["mode"]
        intent.execution_primary_timeframe = config["primary"]
        intent.execution_refinement_timeframe = config["refinement"]
        print(f"[EXECUTION_MODE] session={session} mode={intent.execution_mode}")
        print(f"[EXECUTION_REFINEMENT] primary={intent.execution_primary_timeframe} refinement={intent.execution_refinement_timeframe}")

        is_ross = self._is_ross_strategy(intent, context)
        if is_ross and session == "AH":
            intent.execution_mode = "REJECTED"
            intent.execution_block_reason = "ROSS_AH_BLOCKED"
            print("[EXECUTION_BLOCKED] Ross execution blocked in AH")
            return intent

        intent = self._apply_fast_micro_pullback_rules(intent, session, rvol, spread, is_ross)

        return intent
