from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SetupEngine:
    """Shared setup engine translating level + structure context into setup candidates."""

    _ROUNDING = 6

    def compute_setups(
        self,
        candles: list,
        levels: dict,
        structure: dict,
        *,
        session_context: str | None = None,
        tradability_context: dict | None = None,
    ) -> list[dict]:
        normalized_levels = levels if isinstance(levels, dict) else {}
        normalized_structure = structure if isinstance(structure, dict) else {}
        last_close = self._last_close(candles)
        last_high = self._last_high(candles)
        if last_close is None:
            logger.debug("[SETUP_ENGINE] no setups: missing_last_close")
            return []
        if not bool(normalized_structure.get("is_valid")):
            logger.debug(
                "[SETUP_ENGINE] no setups: invalid_structure reason=%s",
                normalized_structure.get("reason_code"),
            )
            return []

        setups: list[dict] = []

        def add_candidate(setup: dict | None) -> None:
            if not setup:
                return
            setups.append(setup)

        trend = str(normalized_structure.get("trend") or "").upper()
        trend_allows_long = trend in {"UP", "UNKNOWN"}
        trend_quality_flags = ["LOW_STRUCTURE_CONFIDENCE"] if trend == "UNKNOWN" else []
        premarket_high = self._safe_float(normalized_levels.get("premarket_high"))
        hod = self._safe_float(normalized_levels.get("hod"))
        vwap = self._safe_float(normalized_levels.get("vwap"))
        ema9 = self._safe_float(normalized_levels.get("ema_9") or normalized_levels.get("ema9"))
        range_info = normalized_levels.get("active_breakout_range") if isinstance(normalized_levels.get("active_breakout_range"), dict) else {}
        range_upper = self._safe_float((range_info or {}).get("upper"))
        range_lower = self._safe_float((range_info or {}).get("lower"))
        pullback_depth = self._safe_float((normalized_structure.get("pullback_depth") or {}).get("pct"))

        add_candidate(
            self._setup_break(
                family="PREMARKET_HIGH_BREAK",
                name="Premarket High Break",
                direction="LONG",
                rationale="Price pressing through premarket high.",
                confidence=0.64,
                trigger_types=["PMH_BREAK", "BREAKOUT_HIGH"],
                invalidation_anchor="premarket_low",
                condition=(premarket_high is not None and last_close >= premarket_high),
                levels=normalized_levels,
                quality_flags=["LEVEL_CONFLUENCE"] if premarket_high is not None else ["MISSING_PMH"],
                blocking_flags=[] if premarket_high is not None else ["MISSING_PREMARKET_HIGH"],
            )
        )

        add_candidate(
            self._setup_break(
                family="OPENING_RANGE_BREAKOUT",
                name="Opening Range Breakout",
                direction="LONG",
                rationale="Break above active opening range upper bound.",
                confidence=0.62,
                trigger_types=["RANGE_BREAK", "BREAK_AND_HOLD"],
                invalidation_anchor="active_breakout_range.lower",
                condition=(range_upper is not None and last_close >= range_upper),
                levels=normalized_levels,
                quality_flags=[],
                blocking_flags=[] if range_upper is not None else ["MISSING_ACTIVE_BREAKOUT_RANGE"],
            )
        )

        add_candidate(
            self._setup_break(
                family="FIRST_PULLBACK",
                name="First Pullback Continuation",
                direction="LONG",
                rationale="Trend up with controlled pullback depth and reclaim posture.",
                confidence=0.66,
                trigger_types=["PULLBACK_HIGH_BREAK", "RECLAIM"],
                invalidation_anchor="pullback_low",
                condition=(
                    trend_allows_long
                    and bool(normalized_structure.get("pullback_active"))
                    and pullback_depth is not None
                    and pullback_depth <= 0.55
                ),
                levels=normalized_levels,
                quality_flags=[*trend_quality_flags],
                blocking_flags=[] if trend_allows_long else ["TREND_NOT_UP"],
            )
        )

        add_candidate(
            self._setup_break(
                family="MICRO_PULLBACK",
                name="Micro Pullback",
                direction="LONG",
                rationale="Uptrend micro pause with compression and impulse potential.",
                confidence=0.58,
                trigger_types=["PULLBACK_HIGH_BREAK"],
                invalidation_anchor="micro_pullback_low",
                condition=(trend_allows_long and bool(normalized_structure.get("compression_active"))),
                levels=normalized_levels,
                quality_flags=["MICRO_STRUCTURE", *trend_quality_flags],
                blocking_flags=[] if trend_allows_long else ["TREND_NOT_UP"],
            )
        )

        add_candidate(
            self._setup_break(
                family="BULL_FLAG",
                name="Bull Flag",
                direction="LONG",
                rationale="Impulse + orderly consolidation suggests continuation flag.",
                confidence=0.6,
                trigger_types=["RANGE_BREAK", "BREAK_AND_HOLD"],
                invalidation_anchor="flag_low",
                condition=(
                    trend_allows_long
                    and bool(normalized_structure.get("consolidation_active"))
                    and bool(normalized_structure.get("impulse_active"))
                ),
                levels=normalized_levels,
                quality_flags=[*trend_quality_flags],
                blocking_flags=[] if trend_allows_long else ["TREND_NOT_UP"],
            )
        )

        flat_top_level = self._safe_float(normalized_levels.get("resistance_levels", [None])[-1] if normalized_levels.get("resistance_levels") else None)
        add_candidate(
            self._setup_break(
                family="FLAT_TOP_BREAKOUT",
                name="Flat Top Breakout",
                direction="LONG",
                rationale="Range ceiling repeatedly tested; breakout candidate.",
                confidence=0.59,
                trigger_types=["BREAKOUT_HIGH", "RANGE_BREAK"],
                invalidation_anchor="range_floor",
                condition=(flat_top_level is not None and last_close >= flat_top_level),
                levels=normalized_levels,
                quality_flags=["RANGE_PRESSURE"],
                blocking_flags=[] if flat_top_level is not None else ["MISSING_FLAT_TOP_LEVEL"],
            )
        )

        add_candidate(
            self._setup_break(
                family="HOD_BREAK",
                name="High Of Day Break",
                direction="LONG",
                rationale="High of day breach under positive momentum.",
                confidence=0.67,
                trigger_types=["HOD_BREAK", "BREAKOUT_HIGH"],
                invalidation_anchor="prior_pivot_low",
                condition=(hod is not None and ((last_close is not None and last_close >= hod) or (last_high is not None and last_high >= hod))),
                levels=normalized_levels,
                quality_flags=[],
                blocking_flags=[] if hod is not None else ["MISSING_HOD"],
            )
        )

        prev_close = self._previous_close(candles)
        add_candidate(
            self._setup_break(
                family="VWAP_RECLAIM_CONTINUATION",
                name="VWAP Reclaim Continuation",
                direction="LONG",
                rationale="Price reclaimed VWAP and held above.",
                confidence=0.61,
                trigger_types=["RECLAIM", "BREAK_AND_HOLD"],
                invalidation_anchor="vwap",
                condition=(vwap is not None and prev_close is not None and prev_close < vwap and last_close > vwap),
                levels=normalized_levels,
                quality_flags=[] if vwap is not None else ["MISSING_VWAP"],
                blocking_flags=[] if vwap is not None else ["MISSING_VWAP"],
            )
        )

        add_candidate(
            self._setup_break(
                family="CONSOLIDATION_BREAKOUT",
                name="Consolidation Breakout",
                direction="LONG",
                rationale="Tight range resolved with directional expansion.",
                confidence=0.57,
                trigger_types=["RANGE_BREAK", "BREAKOUT_HIGH"],
                invalidation_anchor="consolidation_low",
                condition=(
                    bool(normalized_structure.get("consolidation_active"))
                    and range_upper is not None
                    and last_close >= range_upper
                ),
                levels=normalized_levels,
                quality_flags=[],
                blocking_flags=[] if range_upper is not None else ["MISSING_ACTIVE_BREAKOUT_RANGE"],
            )
        )

        for setup in setups:
            setup["session_context"] = str(session_context or "UNKNOWN").upper()
            setup["tradability_context"] = dict(tradability_context or {})
            setup["structure_context"] = {
                "trend": normalized_structure.get("trend"),
                "dominant_direction": normalized_structure.get("dominant_direction"),
                "impulse_active": bool(normalized_structure.get("impulse_active")),
                "consolidation_active": bool(normalized_structure.get("consolidation_active")),
                "pullback_active": bool(normalized_structure.get("pullback_active")),
                "compression_active": bool(normalized_structure.get("compression_active")),
            }
            setup["levels_context"] = {
                "premarket_high": normalized_levels.get("premarket_high"),
                "premarket_low": normalized_levels.get("premarket_low"),
                "hod": normalized_levels.get("hod"),
                "lod": normalized_levels.get("lod"),
                "vwap": normalized_levels.get("vwap"),
                "active_breakout_range": normalized_levels.get("active_breakout_range"),
            }
            if ema9 is None:
                setup["quality_flags"].append("EMA9_MISSING")
        logger.debug(
            "[SETUP_ENGINE] produced=%s families=%s",
            len(setups),
            [item.get("setup_family_id") for item in setups],
        )
        return setups

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

    def _last_close(self, candles: list) -> float | None:
        if not candles:
            return None
        return self._safe_float(self._read(candles[-1], "close"))

    def _previous_close(self, candles: list) -> float | None:
        if len(candles) < 2:
            return None
        return self._safe_float(self._read(candles[-2], "close"))

    def _last_high(self, candles: list) -> float | None:
        if not candles:
            return None
        return self._safe_float(self._read(candles[-1], "high"))

    def _setup_break(
        self,
        *,
        family: str,
        name: str,
        direction: str,
        rationale: str,
        confidence: float,
        trigger_types: list[str],
        invalidation_anchor: str,
        condition: bool,
        levels: dict,
        quality_flags: list[str],
        blocking_flags: list[str],
    ) -> dict | None:
        if not condition:
            return None
        setup = {
            "setup_family_id": family,
            "setup_family": family,
            "setup_name": name,
            "pattern_name": name,
            "direction": direction,
            "rationale": rationale,
            "confidence": round(max(0.0, min(1.0, confidence)), self._ROUNDING),
            "quality_flags": sorted(set(str(flag) for flag in quality_flags if flag)),
            "blocking_flags": sorted(set(str(flag) for flag in blocking_flags if flag)),
            "invalidation_anchor": invalidation_anchor,
            "invalidation_level": self._resolve_invalidation_level(invalidation_anchor=invalidation_anchor, levels=levels),
            "required_trigger_types": [str(t).upper() for t in trigger_types],
            # backward compatibility fields expected by some existing consumers
            "context": "continuation" if "PULLBACK" in family or "RECLAIM" in family else "breakout",
            "trigger_level": self._primary_trigger_level(family=family, levels=levels),
            "confidence_label": "HIGH" if confidence >= 0.67 else ("MEDIUM" if confidence >= 0.55 else "LOW"),
        }
        return setup

    def _resolve_invalidation_level(self, *, invalidation_anchor: str, levels: dict) -> float | None:
        mapping = {
            "premarket_low": "premarket_low",
            "vwap": "vwap",
            "active_breakout_range.lower": "active_breakout_range.lower",
            "range_floor": "active_breakout_range.lower",
        }
        key = mapping.get(str(invalidation_anchor or "").lower())
        if not key:
            return None
        if "." in key:
            root, child = key.split(".", 1)
            payload = levels.get(root, {}) if isinstance(levels.get(root), dict) else {}
            return self._safe_float(payload.get(child))
        return self._safe_float(levels.get(key))

    def _primary_trigger_level(self, *, family: str, levels: dict) -> float | None:
        mapping = {
            "PREMARKET_HIGH_BREAK": "premarket_high",
            "HOD_BREAK": "hod",
            "VWAP_RECLAIM_CONTINUATION": "vwap",
            "OPENING_RANGE_BREAKOUT": "active_breakout_range.upper",
            "CONSOLIDATION_BREAKOUT": "active_breakout_range.upper",
            "FLAT_TOP_BREAKOUT": "hod",
            "BULL_FLAG": "active_breakout_range.upper",
            "FIRST_PULLBACK": "ema_9",
            "MICRO_PULLBACK": "ema_9",
        }
        key = mapping.get(family)
        if not key:
            return None
        if "." in key:
            root, child = key.split(".", 1)
            payload = levels.get(root, {}) if isinstance(levels.get(root), dict) else {}
            return self._safe_float(payload.get(child))
        return self._safe_float(levels.get(key))
