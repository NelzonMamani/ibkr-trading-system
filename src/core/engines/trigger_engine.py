from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TriggerEngine:
    """Shared trigger engine mapping setup candidates to actionability states."""

    _ROUNDING = 6

    def evaluate_triggers(
        self,
        *,
        symbol: str,
        candles: list,
        setups: list[dict],
        levels: dict,
        structure: dict,
    ) -> list[dict]:
        last_candle = candles[-1] if candles else None
        last_close = self._safe_float(self._read(last_candle, "close")) if last_candle else None
        last_high = self._safe_float(self._read(last_candle, "high")) if last_candle else None
        last_low = self._safe_float(self._read(last_candle, "low")) if last_candle else None
        structure_is_valid = bool((structure or {}).get("is_valid"))
        if not structure_is_valid:
            logger.debug(
                "[TRIGGER_ENGINE] symbol=%s skipped: invalid_structure reason=%s",
                symbol,
                (structure or {}).get("reason_code"),
            )
            return []

        outputs: list[dict] = []
        for setup in setups or []:
            required_types = [str(t).upper() for t in (setup.get("required_trigger_types") or [])]
            trigger_type = required_types[0] if required_types else "BREAKOUT_HIGH"

            trigger_price_reference = self._safe_float(setup.get("trigger_level"))
            if trigger_price_reference is None:
                trigger_price_reference = self._resolve_level_for_setup(setup_family=setup.get("setup_family_id"), levels=levels)

            invalidation_price_reference = self._resolve_invalidation(
                setup=setup,
                levels=levels,
                structure=structure,
                last_low=last_low,
            )
            trigger_ready_now, trigger_reason, quality_flags = self._is_ready(
                trigger_type=trigger_type,
                trigger_price_reference=trigger_price_reference,
                invalidation_price_reference=invalidation_price_reference,
                last_close=last_close,
                last_high=last_high,
                setup=setup,
                structure=structure,
            )
            output = {
                "symbol": str(symbol),
                "setup_family_id": setup.get("setup_family_id"),
                "setup_name": setup.get("setup_name"),
                "trigger_type": trigger_type,
                "trigger_ready_now": trigger_ready_now,
                "trigger_reason": trigger_reason,
                "trigger_price_reference": trigger_price_reference,
                "invalidation_price_reference": invalidation_price_reference,
                "stop_anchor_type": str(setup.get("invalidation_anchor") or "STRUCTURE"),
                "trigger_quality_flags": sorted(set(quality_flags + [*setup.get("quality_flags", [])])),
            }
            outputs.append(output)

        logger.debug(
            "[TRIGGER_ENGINE] symbol=%s evaluated=%s ready=%s",
            symbol,
            len(outputs),
            sum(1 for t in outputs if t.get("trigger_ready_now")),
        )
        return outputs

    @staticmethod
    def _read(item: Any, field: str) -> Any:
        if isinstance(item, dict):
            return item.get(field)
        return getattr(item, field, None)

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    def _resolve_level_for_setup(self, *, setup_family: str | None, levels: dict) -> float | None:
        family = str(setup_family or "").upper()
        mapping = {
            "PREMARKET_HIGH_BREAK": "premarket_high",
            "OPENING_RANGE_BREAKOUT": "active_breakout_range.upper",
            "FIRST_PULLBACK": "ema_9",
            "MICRO_PULLBACK": "ema_9",
            "BULL_FLAG": "active_breakout_range.upper",
            "FLAT_TOP_BREAKOUT": "hod",
            "HOD_BREAK": "hod",
            "VWAP_RECLAIM_CONTINUATION": "vwap",
            "CONSOLIDATION_BREAKOUT": "active_breakout_range.upper",
        }
        key = mapping.get(family)
        if not key:
            return None
        if "." in key:
            root, child = key.split(".", 1)
            nested = levels.get(root, {}) if isinstance(levels.get(root), dict) else {}
            return self._safe_float(nested.get(child))
        return self._safe_float(levels.get(key))

    def _resolve_invalidation(self, *, setup: dict, levels: dict, structure: dict, last_low: float | None) -> float | None:
        anchor = str(setup.get("invalidation_anchor") or "").lower()
        if "premarket_low" in anchor:
            return self._safe_float(levels.get("premarket_low"))
        if "vwap" in anchor:
            return self._safe_float(levels.get("vwap"))
        if "pullback" in anchor or "flag_low" in anchor or "consolidation_low" in anchor:
            return self._safe_float((structure.get("pullback_depth") or {}).get("anchor_low")) or last_low
        return last_low

    def _is_ready(
        self,
        *,
        trigger_type: str,
        trigger_price_reference: float | None,
        invalidation_price_reference: float | None,
        last_close: float | None,
        last_high: float | None,
        setup: dict,
        structure: dict,
    ) -> tuple[bool, str, list[str]]:
        flags: list[str] = []
        if trigger_price_reference is None:
            flags.append("MISSING_TRIGGER_REFERENCE")
            return False, "trigger_reference_missing", flags
        if last_close is None:
            flags.append("MISSING_LAST_CLOSE")
            return False, "last_close_missing", flags

        trigger_type = str(trigger_type or "BREAKOUT_HIGH").upper()
        reclaim_state = str(structure.get("reclaim_state") or "NONE").upper()
        consolidation_active = bool(structure.get("consolidation_active"))
        impulse_active = bool(structure.get("impulse_active"))

        if trigger_type in {"BREAKOUT_HIGH", "HOD_BREAK", "PMH_BREAK", "RANGE_BREAK", "PULLBACK_HIGH_BREAK"}:
            ready = last_close >= trigger_price_reference
            reason = "price_above_trigger" if ready else "price_below_trigger"
        elif trigger_type == "BREAK_AND_HOLD":
            ready = last_close >= trigger_price_reference and impulse_active
            reason = "break_and_hold_confirmed" if ready else "break_and_hold_not_confirmed"
        elif trigger_type == "RECLAIM":
            ready = last_close >= trigger_price_reference and "RECLAIM" in reclaim_state
            reason = "reclaim_confirmed" if ready else "reclaim_not_confirmed"
        else:
            ready = last_high is not None and last_high >= trigger_price_reference
            reason = "high_tagged_trigger" if ready else "trigger_not_tagged"

        if consolidation_active and trigger_type in {"RANGE_BREAK", "BREAK_AND_HOLD"}:
            flags.append("CONSOLIDATION_CONTEXT")
        if invalidation_price_reference is None:
            flags.append("MISSING_INVALIDATION_REFERENCE")
        if invalidation_price_reference is not None and last_close <= invalidation_price_reference:
            flags.append("NEAR_INVALIDATION")
            ready = False
            reason = "at_or_below_invalidation"

        return ready, reason, flags
