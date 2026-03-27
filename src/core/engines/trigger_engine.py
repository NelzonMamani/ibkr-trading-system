from __future__ import annotations

from typing import Any


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
        if not self._is_actionable_structure(structure):
            print(f"[TRIGGER_ENGINE] symbol={symbol} evaluated=0 reason=STRUCTURE_NOT_ACTIONABLE")
            return []

        last_candle = candles[-1] if candles else None
        last_close = self._safe_float(self._read(last_candle, "close")) if last_candle else None
        last_high = self._safe_float(self._read(last_candle, "high")) if last_candle else None
        last_low = self._safe_float(self._read(last_candle, "low")) if last_candle else None

        outputs: list[dict] = []
        for setup in setups or []:
            setup_family_id = str(setup.get("setup_family_id") or setup.get("setup_family") or "").upper()
            trigger_family_id = self.resolve_trigger_family_for_setup(setup_family_id)
            print(
                "[ROSS][TRIGGER_MAPPING] "
                f"symbol={symbol} setup={setup_family_id or 'UNKNOWN'} trigger_family={trigger_family_id}"
            )
            if not trigger_family_id:
                print(
                    "[ROSS][NO_TRIGGER_MAPPING] "
                    f"symbol={symbol} setup={setup_family_id or 'UNKNOWN'}"
                )
                continue

            trigger_type = self._resolve_trigger_type(setup=setup, trigger_family_id=trigger_family_id)
            entry_price_reference = self._safe_float(setup.get("trigger_level"))
            if entry_price_reference is None:
                entry_price_reference = self._resolve_level_for_setup(setup_family=setup_family_id, levels=levels)

            invalidation_price_reference = self._resolve_invalidation(
                setup=setup,
                levels=levels,
                structure=structure,
                last_low=last_low,
            )
            trigger_ready_now, trigger_reason, quality_flags = self._evaluate_trigger_family(
                trigger_family_id=trigger_family_id,
                trigger_type=trigger_type,
                entry_price_reference=entry_price_reference,
                invalidation_price_reference=invalidation_price_reference,
                last_close=last_close,
                last_high=last_high,
                setup=setup,
                structure=structure,
            )
            output = {
                "symbol": str(symbol),
                "setup_family_id": setup_family_id,
                "setup_name": setup.get("setup_name"),
                "trigger_family_id": trigger_family_id,
                "trigger_type": trigger_type,
                "trigger_ready_now": trigger_ready_now,
                "trigger_reason": trigger_reason,
                "entry_price_reference": entry_price_reference,
                "trigger_price_reference": entry_price_reference,
                "invalidation_price_reference": invalidation_price_reference,
                "stop_anchor_type": str(setup.get("invalidation_anchor") or "STRUCTURE"),
                "quality_flags": sorted(set(quality_flags + [*setup.get("quality_flags", [])])),
                "trigger_quality_flags": sorted(set(quality_flags + [*setup.get("quality_flags", [])])),
            }
            outputs.append(output)

        print(
            "[TRIGGER_ENGINE] "
            f"symbol={symbol} evaluated={len(outputs)} ready={sum(1 for t in outputs if t.get('trigger_ready_now'))}"
        )
        return outputs

    @staticmethod
    def _is_actionable_structure(structure: dict) -> bool:
        if isinstance(structure, dict) and "is_actionable" in structure:
            return bool(structure.get("is_actionable"))
        return True

    @staticmethod
    def resolve_trigger_family_for_setup(setup_family_id: str | None) -> str | None:
        family = str(setup_family_id or "").upper()
        mapping = {
            "PREMARKET_HIGH_BREAK": "BREAKOUT_TRIGGER",
            "HOD_BREAK": "BREAKOUT_TRIGGER",
            "RANGE_BREAKOUT": "BREAKOUT_TRIGGER",
            "RANGE_BREAK": "BREAKOUT_TRIGGER",
            "CONSOLIDATION_BREAKOUT": "BREAKOUT_TRIGGER",
            "FLAT_TOP_BREAKOUT": "BREAKOUT_TRIGGER",
            "BULL_FLAG": "BREAKOUT_TRIGGER",
            "OPENING_RANGE_BREAKOUT": "ORB_TRIGGER",
            "ORB_BREAKOUT": "ORB_TRIGGER",
            "ORB": "ORB_TRIGGER",
            "FIRST_PULLBACK": "PULLBACK_RECLAIM_TRIGGER",
            "MICRO_PULLBACK": "PULLBACK_RECLAIM_TRIGGER",
            "VWAP_RECLAIM": "RECLAIM_TRIGGER",
            "VWAP_RECLAIM_CONTINUATION": "RECLAIM_TRIGGER",
            "EMA_RECLAIM": "RECLAIM_TRIGGER",
            "EMA_PULLBACK": "RECLAIM_TRIGGER",
        }
        return mapping.get(family)

    def _resolve_trigger_type(self, *, setup: dict, trigger_family_id: str) -> str:
        required_types = [str(t).upper() for t in (setup.get("required_trigger_types") or [])]
        if required_types:
            return required_types[0]
        default_by_family = {
            "BREAKOUT_TRIGGER": "BREAKOUT_HIGH",
            "ORB_TRIGGER": "RANGE_BREAK",
            "PULLBACK_RECLAIM_TRIGGER": "PULLBACK_HIGH_BREAK",
            "RECLAIM_TRIGGER": "RECLAIM",
        }
        return default_by_family.get(trigger_family_id, "BREAKOUT_HIGH")

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

    def _evaluate_trigger_family(
        self,
        *,
        trigger_family_id: str,
        trigger_type: str,
        entry_price_reference: float | None,
        invalidation_price_reference: float | None,
        last_close: float | None,
        last_high: float | None,
        setup: dict,
        structure: dict,
    ) -> tuple[bool, str, list[str]]:
        if trigger_family_id in {"BREAKOUT_TRIGGER", "ORB_TRIGGER"}:
            return self._evaluate_breakout_trigger(
                trigger_type=trigger_type,
                entry_price_reference=entry_price_reference,
                invalidation_price_reference=invalidation_price_reference,
                last_close=last_close,
                last_high=last_high,
                structure=structure,
            )
        if trigger_family_id == "PULLBACK_RECLAIM_TRIGGER":
            return self._evaluate_pullback_reclaim_trigger(
                entry_price_reference=entry_price_reference,
                invalidation_price_reference=invalidation_price_reference,
                last_close=last_close,
                last_high=last_high,
                structure=structure,
            )
        if trigger_family_id == "RECLAIM_TRIGGER":
            return self._evaluate_reclaim_trigger(
                entry_price_reference=entry_price_reference,
                invalidation_price_reference=invalidation_price_reference,
                last_close=last_close,
                structure=structure,
            )
        return False, "NO_TRIGGER_MAPPING", ["NO_TRIGGER_MAPPING"]

    def _evaluate_breakout_trigger(
        self,
        *,
        trigger_type: str,
        entry_price_reference: float | None,
        invalidation_price_reference: float | None,
        last_close: float | None,
        last_high: float | None,
        structure: dict,
    ) -> tuple[bool, str, list[str]]:
        flags: list[str] = []
        if entry_price_reference is None:
            flags.append("MISSING_TRIGGER_REFERENCE")
            return False, "NO_TRIGGER_CANDIDATE", flags
        if last_close is None:
            flags.append("MISSING_LAST_CLOSE")
            return False, "last_close_missing", flags

        trigger_type = str(trigger_type or "BREAKOUT_HIGH").upper()
        consolidation_active = bool(structure.get("consolidation_active"))
        impulse_active = bool(structure.get("impulse_active"))

        if trigger_type in {"BREAKOUT_HIGH", "HOD_BREAK", "PMH_BREAK", "RANGE_BREAK", "PULLBACK_HIGH_BREAK"}:
            ready = last_close >= entry_price_reference
            reason = "BREAKOUT_CLEARED" if ready else "BREAKOUT_NOT_CLEARED"
        elif trigger_type == "BREAK_AND_HOLD":
            ready = last_close >= entry_price_reference and impulse_active
            reason = "BREAKOUT_CLEARED" if ready else "TRIGGER_WAITING_FOR_HIGH_BREAK"
        else:
            ready = last_high is not None and last_high >= entry_price_reference
            reason = "BREAKOUT_CLEARED" if ready else "TRIGGER_WAITING_FOR_HIGH_BREAK"

        if consolidation_active and trigger_type in {"RANGE_BREAK", "BREAK_AND_HOLD"}:
            flags.append("CONSOLIDATION_CONTEXT")
        if invalidation_price_reference is None:
            flags.append("MISSING_INVALIDATION_REFERENCE")
        if invalidation_price_reference is not None and last_close <= invalidation_price_reference:
            flags.append("NEAR_INVALIDATION")
            ready = False
            reason = "at_or_below_invalidation"

        return ready, reason, flags

    def _evaluate_pullback_reclaim_trigger(
        self,
        *,
        entry_price_reference: float | None,
        invalidation_price_reference: float | None,
        last_close: float | None,
        last_high: float | None,
        structure: dict,
    ) -> tuple[bool, str, list[str]]:
        flags: list[str] = []
        if entry_price_reference is None:
            flags.append("MISSING_TRIGGER_REFERENCE")
            return False, "TRIGGER_WAITING_FOR_PULLBACK_RECLAIM", flags
        if last_close is None:
            flags.append("MISSING_LAST_CLOSE")
            return False, "last_close_missing", flags
        pullback_active = bool(structure.get("pullback_active"))
        impulse_active = bool(structure.get("impulse_active"))
        ready = bool((last_close >= entry_price_reference or (last_high is not None and last_high >= entry_price_reference)) and (impulse_active or pullback_active))
        reason = "PULLBACK_RECLAIM_CONFIRMED" if ready else "TRIGGER_WAITING_FOR_PULLBACK_RECLAIM"
        if invalidation_price_reference is None:
            flags.append("MISSING_INVALIDATION_REFERENCE")
        elif last_close <= invalidation_price_reference:
            flags.append("NEAR_INVALIDATION")
            return False, "at_or_below_invalidation", flags
        return ready, reason, flags

    def _evaluate_reclaim_trigger(
        self,
        *,
        entry_price_reference: float | None,
        invalidation_price_reference: float | None,
        last_close: float | None,
        structure: dict,
    ) -> tuple[bool, str, list[str]]:
        flags: list[str] = []
        if entry_price_reference is None:
            flags.append("MISSING_TRIGGER_REFERENCE")
            return False, "TRIGGER_WAITING_FOR_RECLAIM_CONFIRMATION", flags
        if last_close is None:
            flags.append("MISSING_LAST_CLOSE")
            return False, "last_close_missing", flags
        reclaim_state = str(structure.get("reclaim_state") or "NONE").upper()
        ready = last_close >= entry_price_reference and "RECLAIM" in reclaim_state
        reason = "RECLAIM_CONFIRMED" if ready else "RECLAIM_NOT_CONFIRMED"
        if invalidation_price_reference is None:
            flags.append("MISSING_INVALIDATION_REFERENCE")
        elif last_close <= invalidation_price_reference:
            flags.append("NEAR_INVALIDATION")
            return False, "at_or_below_invalidation", flags
        return ready, reason, flags
