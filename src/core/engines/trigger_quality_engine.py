from __future__ import annotations

from typing import Any


class TriggerQualityEngine:
    """Quality scoring engine for trigger ranking and capital scaling."""

    _HIGH_BASE_FAMILIES = {"PREMARKET_HIGH_BREAK", "FIRST_PULLBACK", "HOD_BREAK"}
    _MEDIUM_BASE_FAMILIES = {"MICRO_PULLBACK", "BULL_FLAG"}

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    def evaluate_trigger_quality(
        self,
        *,
        trigger: dict,
        structure: dict,
        session_context: str | None,
        rvol: float | None,
    ) -> dict[str, Any]:
        setup_family = str(trigger.get("setup_family_id") or "").upper()
        trigger_flags = set(str(flag).upper() for flag in (trigger.get("trigger_quality_flags") or []))
        structure_flags = set(str(flag).upper() for flag in (structure.get("structure_quality_flags") or []))

        if setup_family in self._HIGH_BASE_FAMILIES:
            base_setup_weight = 0.6
        elif setup_family in self._MEDIUM_BASE_FAMILIES:
            base_setup_weight = 0.5
        else:
            base_setup_weight = 0.45

        trend = str(structure.get("dominant_direction") or "UNKNOWN").upper()
        trend_alignment = 0.1 if trend == "UP" else 0.0

        pullback_depth_present = bool(structure.get("pullback_depth"))
        pullback_depth_score = 0.05 if pullback_depth_present else 0.0

        compression_active = bool(structure.get("compression_active") or structure.get("consolidation_active"))
        compression_score = 0.05 if compression_active else 0.0

        session = str(session_context or "UNKNOWN").upper()
        session_context_score = 0.05 if session == "RTH_OPEN" else 0.0

        liquidity_threshold = 1.2 if session == "PRE" else 2.0
        liquidity_score = 0.05 if (self._safe_float(rvol) or 0.0) > liquidity_threshold else 0.0

        low_confidence_penalty = -0.2 if ("LOW_CONFIDENCE" in trigger_flags or "LOW_CONFIDENCE" in structure_flags) else 0.0
        missing_level_penalty = -0.1 if ("MISSING_TRIGGER_REFERENCE" in trigger_flags or "MISSING_INVALIDATION_REFERENCE" in trigger_flags) else 0.0

        score = (
            base_setup_weight
            + trend_alignment
            + pullback_depth_score
            + compression_score
            + session_context_score
            + liquidity_score
            + low_confidence_penalty
            + missing_level_penalty
        )
        score = max(0.0, min(1.0, round(score, 4)))

        return {
            "quality_score": score,
            "components": {
                "base_setup_weight": base_setup_weight,
                "trend_alignment": trend_alignment,
                "pullback_depth": pullback_depth_score,
                "compression_active": compression_score,
                "session_context": session_context_score,
                "liquidity": liquidity_score,
                "low_confidence_penalty": low_confidence_penalty,
                "missing_level_penalty": missing_level_penalty,
            },
            "session_context": session,
            "liquidity_threshold": liquidity_threshold,
        }
