from __future__ import annotations

from typing import Any

from src.strategies.common.triggers.trigger_flat_top_breakout import evaluate_flat_top_breakout_trigger
from src.strategies.common.triggers.trigger_first_pullback import evaluate_first_pullback_trigger
from src.strategies.common.triggers.trigger_micro_pullback import evaluate_micro_pullback_trigger
from src.strategies.common.triggers.trigger_orb import evaluate_orb_trigger


class TriggerEngine:
    """Shared trigger engine mapping setup candidates to actionability states."""

    _ROUNDING = 6
    _FAMILY_ALIASES = {
        "ORB": "OPENING_RANGE_BREAKOUT",
        "PREMARKET_HIGH_BREAK": "PREMARKET_HIGH_BREAK",
        "PMH_BREAK": "PREMARKET_HIGH_BREAK",
        "MOMENTUM_RECLAIM": "VWAP_RECLAIM_CONTINUATION",
        "ASCENDING_TRIANGLE_BREAKOUT": "ASCENDING_TRIANGLE_BREAKOUT",
        "PENNANT_BREAK": "PENNANT_BREAK",
    }

    def evaluate_triggers(
        self,
        *,
        symbol: str,
        candles: list,
        setups: list[dict],
        levels: dict,
        structure: dict,
    ) -> list[dict]:
        if not setups:
            print(f"[TRIGGER_ENGINE] symbol={symbol} evaluated=0 ready=0")
            return []

        last_candle = candles[-1] if candles else None
        prev_candle = candles[-2] if len(candles) > 1 else None
        last_close = self._safe_float(self._read(last_candle, "close")) if last_candle else None
        last_high = self._safe_float(self._read(last_candle, "high")) if last_candle else None
        last_low = self._safe_float(self._read(last_candle, "low")) if last_candle else None
        prev_close = self._safe_float(self._read(prev_candle, "close")) if prev_candle else None

        outputs: list[dict] = []
        for setup in setups:
            if not bool(setup.get("setup_detected", True)):
                continue
            setup_family = str(setup.get("setup_family_id") or "").upper()
            if setup_family == "FLAT_TOP_BREAKOUT":
                flat_top_trigger = evaluate_flat_top_breakout_trigger(
                    setup,
                    {
                        **(levels if isinstance(levels, dict) else {}),
                        "candles": list(candles or []),
                    },
                )
                output = {
                    "symbol": str(symbol),
                    "setup_family_id": setup.get("setup_family_id"),
                    "setup_name": setup.get("setup_name"),
                    "trigger_type": str(flat_top_trigger.get("trigger_type") or "BREAKOUT_HIGH"),
                    "trigger_state": str(flat_top_trigger.get("trigger_state") or "BLOCKED"),
                    "trigger_ready_now": bool(flat_top_trigger.get("trigger_ready_now")),
                    "trigger_event_emitted": bool(flat_top_trigger.get("trigger_event_emitted")),
                    "trigger_reason": str(flat_top_trigger.get("trigger_reason") or "flat_top_breakout_armed"),
                    "trigger_price_reference": self._safe_float(flat_top_trigger.get("trigger_price_reference")),
                    "invalidation_price_reference": self._safe_float(flat_top_trigger.get("invalidation_price_reference")),
                    "execution_refinement_mode": str(flat_top_trigger.get("execution_refinement_mode") or "NONE"),
                    "stop_anchor_type": str(setup.get("invalidation_anchor") or "STRUCTURE"),
                    "trigger_quality_flags": sorted(
                        set(
                            [*flat_top_trigger.get("trigger_quality_flags", []), *setup.get("quality_flags", [])]
                        )
                    ),
                }
                outputs.append(output)
                continue
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
                prev_close=prev_close,
                setup=setup,
                levels=levels,
                structure=structure,
                candles=candles,
            )
            if str(setup.get("setup_family_id") or "").upper() == "GAP_GO":
                print(
                    "[TRIGGER][GAP_GO] "
                    f"symbol={symbol} trigger={trigger_type} fired={bool(trigger_ready_now)}"
                )
            trigger_state = "FIRED" if trigger_ready_now else "ARMED"
            if "BLOCKED" in set(str(flag).upper() for flag in quality_flags):
                trigger_state = "BLOCKED"
            output = {
                "symbol": str(symbol),
                "setup_family_id": setup.get("setup_family_id"),
                "setup_name": setup.get("setup_name"),
                "trigger_type": trigger_type,
                "trigger_state": trigger_state,
                "trigger_ready_now": trigger_ready_now,
                "trigger_event_emitted": bool(trigger_ready_now),
                "trigger_reason": trigger_reason,
                "trigger_price_reference": trigger_price_reference,
                "invalidation_price_reference": invalidation_price_reference,
                "execution_refinement_mode": str(setup.get("execution_refinement_mode") or "NONE"),
                "stop_anchor_type": str(setup.get("invalidation_anchor") or "STRUCTURE"),
                "trigger_quality_flags": sorted(set(quality_flags + [*setup.get("quality_flags", [])])),
            }
            outputs.append(output)

        print(
            "[TRIGGER_ENGINE] "
            f"symbol={symbol} evaluated={len(outputs)} ready={sum(1 for t in outputs if t.get('trigger_ready_now'))}"
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
        raw_family = str(setup_family or "").upper()
        family = self._FAMILY_ALIASES.get(raw_family, raw_family)
        mapping = {
            "PREMARKET_HIGH_BREAK": "premarket_high",
            "FIRST_PULLBACK": "ema_9",
            "MICRO_PULLBACK": "ema_9",
            "BULL_FLAG": "active_breakout_range.upper",
            "FLAT_TOP_BREAKOUT": "hod",
            "HOD_BREAK": "hod",
            "VWAP_RECLAIM_CONTINUATION": "vwap",
            "CONSOLIDATION_BREAKOUT": "active_breakout_range.upper",
            "ASCENDING_TRIANGLE_BREAKOUT": "active_breakout_range.upper",
            "PENNANT_BREAK": "active_breakout_range.upper",
            "MOMENTUM_RECLAIM": "vwap",
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
        explicit_invalidation = self._safe_float(setup.get("invalidation_level"))
        if explicit_invalidation is not None:
            return explicit_invalidation
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
        prev_close: float | None,
        setup: dict,
        levels: dict,
        structure: dict,
        candles: list,
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
        structure_is_actionable = bool(structure.get("is_actionable"))

        setup_family = str(setup.get("setup_family_id") or "").upper()
        if setup_family == "GAP_GO":
            ready, reason = self._evaluate_gap_go_trigger(
                trigger_type=trigger_type,
                trigger_price_reference=trigger_price_reference,
                last_close=last_close,
                last_high=last_high,
                prev_close=prev_close,
                levels=levels,
            )
        elif setup_family in {"OPENING_RANGE_BREAKOUT", "ORB"}:
            orb_trigger = evaluate_orb_trigger(
                setup,
                {
                    **(levels if isinstance(levels, dict) else {}),
                    "candles": list(candles or []),
                },
            )
            ready = bool(orb_trigger.get("trigger_ready_now"))
            reason = str(orb_trigger.get("trigger_reason") or "orb_trigger_not_ready")
            trigger_type = str(orb_trigger.get("trigger_type") or trigger_type)
            flags.append(str(orb_trigger.get("trigger_state") or ("FIRED" if ready else "ARMED")))
            print(f"[TRIGGER][ORB] fired={ready} reason={reason}")
        elif setup_family in {"FIRST_PULLBACK"}:
            pullback_trigger = evaluate_first_pullback_trigger(
                setup,
                {
                    **(levels if isinstance(levels, dict) else {}),
                    "candles": list(candles or []),
                },
            )
            ready = bool(pullback_trigger.get("trigger_ready_now"))
            reason = str(pullback_trigger.get("trigger_reason") or "first_pullback_trigger_not_ready")
            trigger_type = str(pullback_trigger.get("trigger_type") or trigger_type)
            flags.append(str(pullback_trigger.get("trigger_state") or ("FIRED" if ready else "ARMED")))
            trigger_price_reference = self._safe_float(
                pullback_trigger.get("trigger_price_reference")
            ) or trigger_price_reference
            invalidation_price_reference = self._safe_float(
                pullback_trigger.get("invalidation_price_reference")
            ) or invalidation_price_reference
        elif setup_family in {"MICRO_PULLBACK"}:
            micro_pullback_trigger = evaluate_micro_pullback_trigger(
                setup,
                {
                    **(levels if isinstance(levels, dict) else {}),
                    "candles": list(candles or []),
                },
            )
            ready = bool(micro_pullback_trigger.get("trigger_ready_now"))
            reason = str(micro_pullback_trigger.get("trigger_reason") or "micro_pullback_trigger_not_ready")
            trigger_type = str(micro_pullback_trigger.get("trigger_type") or trigger_type)
            flags.append(str(micro_pullback_trigger.get("trigger_state") or ("FIRED" if ready else "ARMED")))
            trigger_price_reference = self._safe_float(micro_pullback_trigger.get("trigger_price_reference"))
            invalidation_price_reference = self._safe_float(micro_pullback_trigger.get("invalidation_price_reference"))
            setup["execution_refinement_mode"] = micro_pullback_trigger.get("execution_refinement_mode")
        elif trigger_type in {"BREAKOUT_HIGH", "HOD_BREAK", "PMH_BREAK", "RANGE_BREAK", "PULLBACK_HIGH_BREAK"}:
            ready, reason = self._evaluate_breakout_trigger(
                last_close=last_close,
                last_high=last_high,
                trigger_price_reference=trigger_price_reference,
                structure=structure,
                structure_is_actionable=structure_is_actionable,
                invalidation_price_reference=invalidation_price_reference,
                flags=flags,
            )
        elif trigger_type == "BREAK_AND_HOLD":
            ready = last_close >= trigger_price_reference and impulse_active
            reason = "break_and_hold_confirmed" if ready else "break_and_hold_not_confirmed"
        elif trigger_type == "RECLAIM":
            ready = last_close >= trigger_price_reference and "RECLAIM" in reclaim_state
            reason = "reclaim_already_confirmed" if ready else "reclaim_not_confirmed"
        else:
            ready = last_high is not None and last_high >= trigger_price_reference
            reason = "high_tagged_trigger" if ready else "trigger_not_tagged"

        if consolidation_active and trigger_type in {"RANGE_BREAK", "BREAK_AND_HOLD"}:
            flags.append("CONSOLIDATION_CONTEXT")
        if invalidation_price_reference is None:
            flags.append("MISSING_INVALIDATION_REFERENCE")
        invalidation_violated = invalidation_price_reference is not None and last_close <= invalidation_price_reference
        if invalidation_violated:
            flags.append("NEAR_INVALIDATION")
            ready = False
            reason = "at_or_below_invalidation"

        return ready, reason, flags

    def _evaluate_gap_go_trigger(
        self,
        *,
        trigger_type: str,
        trigger_price_reference: float,
        last_close: float,
        last_high: float | None,
        prev_close: float | None,
        levels: dict,
    ) -> tuple[bool, str]:
        premarket_high = self._safe_float(levels.get("premarket_high"))
        hod = self._safe_float(levels.get("hod"))
        trigger_type = str(trigger_type or "BREAKOUT_HIGH").upper()
        if trigger_type == "PMH_BREAK":
            level = premarket_high if premarket_high is not None else trigger_price_reference
            ready = last_close >= level
            return ready, "gap_go_pmh_break" if ready else "gap_go_pmh_not_broken"
        if trigger_type == "HOD_BREAK":
            level = hod if hod is not None else trigger_price_reference
            ready = last_close >= level
            return ready, "gap_go_hod_break" if ready else "gap_go_hod_not_broken"
        if trigger_type == "BREAK_AND_HOLD":
            hold_level = trigger_price_reference
            ready = last_close >= hold_level and prev_close is not None and prev_close >= hold_level
            return ready, "gap_go_break_and_hold" if ready else "gap_go_break_and_hold_not_confirmed"
        ready = last_high is not None and last_high > trigger_price_reference
        return ready, "gap_go_prev_high_break" if ready else "gap_go_prev_high_not_broken"

    def _evaluate_breakout_trigger(
        self,
        *,
        last_close: float,
        last_high: float | None,
        trigger_price_reference: float,
        structure: dict,
        structure_is_actionable: bool,
        invalidation_price_reference: float | None,
        flags: list[str],
    ) -> tuple[bool, str]:
        ready = last_close >= trigger_price_reference
        reason = "breakout_already_through_level" if ready else "BREAKOUT_NOT_CLEARED"
        previous_pullback_high = self._safe_float(structure.get("previous_pullback_high"))
        session_label = str(structure.get("session_context") or "").upper()
        session_is_pre = session_label in {"PRE", "PREMARKET"}
        pre_activation = bool(structure.get("pre_activation_ready"))
        invalidation_violated = invalidation_price_reference is not None and last_close <= invalidation_price_reference
        if (
            bool(structure.get("pullback_active"))
            and last_high is not None
            and previous_pullback_high is not None
            and last_high > previous_pullback_high
        ):
            ready = True
            reason = "FIRST_NEW_HIGH"
            flags.append("FIRST_NEW_HIGH")
        elif (
            session_is_pre
            and pre_activation
            and structure_is_actionable
            and invalidation_violated is False
            and last_close >= trigger_price_reference
        ):
            ready = True
            reason = "PRE_ACTIVATION_BREAKOUT"
            flags.append("PRE_ACTIVATION_TRIGGER")
            symbol = str(structure.get("symbol") or "UNKNOWN")
            print(f"[ROSS][PRE_TRIGGER_PROMOTION] symbol={symbol} reason=PRE_ACTIVATION_BREAKOUT")
        return ready, reason
