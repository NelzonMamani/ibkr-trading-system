from __future__ import annotations

from typing import Any


class TriggerEngine:
    """Shared trigger engine mapping setup candidates to actionability states."""

    _ROUNDING = 6

    def evaluate(
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

        outputs: list[dict] = []
        for setup in setups or []:
            required_types = [str(t).upper() for t in (setup.get("required_trigger_types") or [])]
            trigger_type = required_types[0] if required_types else "BREAKOUT"
            trigger_type = self._canonical_trigger_type(trigger_type)

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
                last_low=last_low,
                setup=setup,
                structure=structure,
                levels=levels,
            )
            output = {
                "symbol": str(symbol),
                "setup_family_id": setup.get("setup_family_id"),
                "setup_name": setup.get("setup_name"),
                "setup_direction": str(setup.get("direction") or "LONG").upper(),
                "structure_context": {
                    "trend": str(structure.get("trend") or "").upper(),
                    "dominant_direction": str(structure.get("dominant_direction") or "").upper(),
                    "reclaim_state": str(structure.get("reclaim_state") or "").upper(),
                },
                "trigger_type": trigger_type,
                "trigger_ready_now": trigger_ready_now,
                "trigger_reason": trigger_reason,
                "trigger_price_reference": trigger_price_reference,
                "invalidation_price_reference": invalidation_price_reference,
                "entry_price": trigger_price_reference,
                "stop_reference": invalidation_price_reference,
                "stop_anchor_type": str(setup.get("invalidation_anchor") or "STRUCTURE"),
                "trigger_quality_flags": sorted(set(quality_flags + [*setup.get("quality_flags", [])])),
            }
            outputs.append(output)

        print(
            "[TRIGGER_ENGINE] "
            f"symbol={symbol} evaluated={len(outputs)} ready={sum(1 for t in outputs if t.get('trigger_ready_now'))}"
        )
        return outputs

    def evaluate_triggers(
        self,
        *,
        symbol: str,
        candles: list,
        setups: list[dict],
        levels: dict,
        structure: dict,
    ) -> list[dict]:
        # Backward compatibility for existing callers.
        return self.evaluate(
            symbol=symbol,
            candles=candles,
            setups=setups,
            levels=levels,
            structure=structure,
        )

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

    @staticmethod
    def _canonical_trigger_type(trigger_type: str) -> str:
        normalized = str(trigger_type or "").upper()
        aliases = {
            "BREAKOUT_HIGH": "BREAKOUT",
            "PMH_BREAK": "BREAKOUT",
            "RANGE_BREAK": "BREAKOUT",
            "PULLBACK_HIGH_BREAK": "PULLBACK_ENTRY",
            "BREAK_AND_HOLD": "PULLBACK_ENTRY",
            "RECLAIM": "RECLAIM",
            "HOD_BREAK": "HOD_LOD_BREAK",
            "LOD_BREAK": "HOD_LOD_BREAK",
        }
        return aliases.get(normalized, normalized or "BREAKOUT")

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
        last_low: float | None,
        setup: dict,
        structure: dict,
        levels: dict,
    ) -> tuple[bool, str, list[str]]:
        flags: list[str] = []
        if trigger_price_reference is None:
            flags.append("MISSING_TRIGGER_REFERENCE")
            return False, "trigger_reference_missing", flags
        if last_close is None:
            flags.append("MISSING_LAST_CLOSE")
            return False, "last_close_missing", flags

        trigger_type = self._canonical_trigger_type(trigger_type)
        reclaim_state = str(structure.get("reclaim_state") or "NONE").upper()
        consolidation_active = bool(structure.get("consolidation_active"))
        impulse_active = bool(structure.get("impulse_active"))
        vwap = self._safe_float(levels.get("vwap"))
        ema9 = self._safe_float(levels.get("ema_9") or levels.get("ema9"))

        if trigger_type == "BREAKOUT":
            ready = last_close >= trigger_price_reference
            reason = "breakout_confirmed" if ready else "breakout_not_confirmed"
        elif trigger_type == "PULLBACK_ENTRY":
            ready = last_close >= trigger_price_reference and impulse_active
            reason = "pullback_continuation_confirmed" if ready else "pullback_continuation_not_confirmed"
        elif trigger_type == "RECLAIM":
            reclaim_reference = next((v for v in (vwap, ema9, trigger_price_reference) if v is not None), trigger_price_reference)
            ready = (
                last_close >= reclaim_reference
                and "RECLAIM" in reclaim_state
                and (last_low is None or last_low <= reclaim_reference)
            )
            reason = "reclaim_confirmed" if ready else "reclaim_not_confirmed"
        elif trigger_type == "HOD_LOD_BREAK":
            ready = last_close >= trigger_price_reference
            reason = "hod_lod_break_confirmed" if ready else "hod_lod_break_not_confirmed"
        else:
            ready = last_high is not None and last_high >= trigger_price_reference
            reason = "high_tagged_trigger" if ready else "trigger_not_tagged"

        if consolidation_active and trigger_type in {"BREAKOUT", "PULLBACK_ENTRY"}:
            flags.append("CONSOLIDATION_CONTEXT")
        if invalidation_price_reference is None:
            flags.append("MISSING_INVALIDATION_REFERENCE")
        if invalidation_price_reference is not None and last_close <= invalidation_price_reference:
            flags.append("NEAR_INVALIDATION")
            ready = False
            reason = "at_or_below_invalidation"

        return ready, reason, flags
