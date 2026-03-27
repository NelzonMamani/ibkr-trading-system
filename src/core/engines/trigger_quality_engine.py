from __future__ import annotations

from typing import Any


class TriggerQualityEngine:
    """Scores trigger quality and maps to deterministic permission tiers."""

    _ROUNDING = 4
    _HIGH_FAMILIES = {"PREMARKET_HIGH_BREAK", "FIRST_PULLBACK", "HOD_BREAK"}
    _MEDIUM_FAMILIES = {"MICRO_PULLBACK", "BULL_FLAG"}

    @classmethod
    def evaluate_trigger_quality(
        cls,
        trigger: dict | None,
        setup: dict | None,
        structure: dict | None,
        levels: dict | None,
        tradability_context: dict | None,
    ) -> dict:
        trigger_payload = trigger or {}
        setup_payload = setup or {}
        structure_payload = structure or {}
        levels_payload = levels or {}
        tradability_payload = tradability_context or {}

        setup_family = str(
            setup_payload.get("setup_family_id")
            or setup_payload.get("setup_family")
            or trigger_payload.get("setup_family_id")
            or "UNKNOWN"
        ).upper()
        trend = str(
            structure_payload.get("dominant_direction")
            or structure_payload.get("trend")
            or "UNKNOWN"
        ).upper()

        quality_flags = {
            str(flag).upper()
            for flag in (
                list(setup_payload.get("quality_flags") or [])
                + list(setup_payload.get("blocking_flags") or [])
                + list(trigger_payload.get("trigger_quality_flags") or [])
            )
            if flag
        }

        if setup_family == "GENERIC_MOMENTUM_PROBE":
            quality_flags.add("FALLBACK_SETUP")
            return cls._build(
                score=0.1,
                tier="LOW",
                flags=quality_flags,
                rejection_reason="fallback_probe_blocked",
            )

        if "LOW_CONFIDENCE" in quality_flags:
            return cls._build(
                score=0.2,
                tier="LOW",
                flags=quality_flags,
                rejection_reason="low_confidence_flag",
            )

        structure_aligned = cls._structure_aligned(
            setup_family=setup_family,
            trend=trend,
            trigger_payload=trigger_payload,
            structure_payload=structure_payload,
            levels_payload=levels_payload,
        )

        if setup_family in cls._HIGH_FAMILIES and trend == "UP" and structure_aligned:
            score = 0.82
            if "MISSING_TRIGGER_REFERENCE" in quality_flags:
                score -= 0.2
                quality_flags.add("DEGRADED_TRIGGER_REFERENCE")
            return cls._build(score=score, tier="HIGH", flags=quality_flags)

        if setup_family in cls._MEDIUM_FAMILIES and trend in {"UP", "UNKNOWN"}:
            score = 0.58
            if str(tradability_payload.get("session") or "").upper().startswith("PRE"):
                score -= 0.05
                quality_flags.add("PREMARKET_MEDIUM_QUALITY")
            return cls._build(score=score, tier="MEDIUM", flags=quality_flags)

        rejection_reason = "setup_family_not_permitted"
        if trend not in {"UP", "UNKNOWN"}:
            rejection_reason = f"trend_not_supported:{trend}"
        elif not structure_aligned:
            rejection_reason = "structure_not_aligned"

        return cls._build(score=0.35, tier="LOW", flags=quality_flags, rejection_reason=rejection_reason)

    @classmethod
    def _build(cls, *, score: float, tier: str, flags: set[str], rejection_reason: str | None = None) -> dict:
        return {
            "quality_score": round(max(0.0, min(1.0, float(score))), cls._ROUNDING),
            "quality_tier": str(tier).upper(),
            "quality_flags": sorted(flags),
            "rejection_reason": rejection_reason,
        }

    @staticmethod
    def _structure_aligned(
        *,
        setup_family: str,
        trend: str,
        trigger_payload: dict,
        structure_payload: dict,
        levels_payload: dict,
    ) -> bool:
        if trend == "DOWN":
            return False
        if setup_family in {"FIRST_PULLBACK", "MICRO_PULLBACK"}:
            return bool(structure_payload.get("pullback_depth"))
        if setup_family in {"HOD_BREAK", "PREMARKET_HIGH_BREAK"}:
            trigger_reference = trigger_payload.get("trigger_price_reference")
            hod = levels_payload.get("hod")
            if trigger_reference is None or hod is None:
                return True
            try:
                return float(trigger_reference) >= float(hod)
            except (TypeError, ValueError):
                return False
        return True


def evaluate_trigger_quality(
    trigger: dict | None,
    setup: dict | None,
    structure: dict | None,
    levels: dict | None,
    tradability_context: dict | None,
) -> dict:
    """Backwards-compatible function API for trigger quality evaluation."""

    return TriggerQualityEngine.evaluate_trigger_quality(
        trigger=trigger,
        setup=setup,
        structure=structure,
        levels=levels,
        tradability_context=tradability_context,
    )
