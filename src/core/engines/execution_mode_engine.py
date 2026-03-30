"""Session-aware execution mode governance for trade intents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EXECUTION_MODES: dict[str, dict[str, Any]] = {
    "PREMARKET": {
        "mode": "CONDITIONAL_FAST",
        "allowed_refinements": ["FAST_MICRO_PULLBACK"],
        "primary_timeframe": "1m",
        "refinement_timeframe": "10s",
        "require_conditions": ["high_rvol", "tight_spread"],
    },
    "RTH_OPEN": {
        "mode": "HIGH_SPEED",
        "allowed_refinements": ["FAST_MICRO_PULLBACK"],
        "primary_timeframe": "1m",
        "refinement_timeframe": "10s",
    },
    "RTH_MID": {
        "mode": "MODERATE",
        "allowed_refinements": ["SLOW_MICRO_PULLBACK"],
        "primary_timeframe": "1m",
        "refinement_timeframe": "1m",
    },
    "RTH_LATE": {
        "mode": "STRUCTURAL",
        "allowed_refinements": [],
        "primary_timeframe": "5m",
        "refinement_timeframe": None,
    },
    "AFTER_HOURS": {
        "mode": "LOW_LIQUIDITY",
        "allowed_refinements": [],
        "primary_timeframe": "1m",
        "refinement_timeframe": None,
    },
}


_SESSION_NORMALIZATION = {
    "PRE": "PREMARKET",
    "PREMARKET": "PREMARKET",
    "RTH_OPEN": "RTH_OPEN",
    "RTH_MID": "RTH_MID",
    "RTH_LATE": "RTH_LATE",
    "AH": "AFTER_HOURS",
    "AFTER_HOURS": "AFTER_HOURS",
}


@dataclass
class ExecutionModeEngine:
    """Applies deterministic execution governance to a TradeIntent."""

    def normalize_session(self, session_label: str | None) -> str:
        normalized = _SESSION_NORMALIZATION.get(str(session_label or "").upper())
        if normalized is None:
            return "AFTER_HOURS"
        return normalized

    def apply(self, intent, context):
        session_label = getattr(context, "session", None) or getattr(context, "session_context", None)
        session = self.normalize_session(session_label)
        config = EXECUTION_MODES[session]

        refinement = str(getattr(intent, "execution_refinement_mode", "NONE") or "NONE").upper()
        refinement = self._validate_refinement(refinement, config=config, context=context, raw_session=session_label)

        if refinement is None:
            print("[EXECUTION_REJECT] reason=invalid_refinement_for_session")
            return None

        intent.execution_refinement_mode = refinement
        intent.execution_primary_timeframe = config["primary_timeframe"]
        intent.execution_refinement_timeframe = config["refinement_timeframe"]
        intent.execution_mode = config["mode"]

        effective_tf = intent.execution_refinement_timeframe or intent.execution_primary_timeframe
        print(
            "[EXECUTION_MODE] "
            f"session={session} mode={intent.execution_mode} tf={effective_tf}"
        )
        print(
            "[EXECUTION_REFINEMENT] "
            f"{intent.execution_refinement_mode} allowed=True"
        )

        return intent

    def _validate_refinement(self, refinement: str, *, config: dict[str, Any], context, raw_session: str | None) -> str | None:
        session = self.normalize_session(raw_session)

        # PREMARKET rules
        if session == "PREMARKET" and refinement == "FAST_MICRO_PULLBACK":
            rvol = getattr(context, "rvol", None)
            spread = getattr(context, "spread", None)
            if rvol is None or float(rvol) < 1.5:
                print("[EXECUTION_REJECT] reason=premarket_low_rvol")
                return None
            if spread is None or float(spread) > 0.02:
                print("[EXECUTION_REJECT] reason=premarket_wide_spread")
                return None

        # AFTER HOURS: block completely
        if session == "AFTER_HOURS":
            print("[EXECUTION_REJECT] reason=invalid_session")
            return None

        # RTH_LATE: no micro execution
        if session == "RTH_LATE":
            print("[EXECUTION_REJECT] reason=late_session_refinement_blocked")
            return None

        # RTH_MID downgrade
        if session == "RTH_MID" and refinement == "FAST_MICRO_PULLBACK":
            print("[EXECUTION_DOWNGRADE] FAST → SLOW")
            return "SLOW_MICRO_PULLBACK"

        if refinement not in config["allowed_refinements"]:
            print("[EXECUTION_REJECT] reason=invalid_session")
            return None

        return refinement
