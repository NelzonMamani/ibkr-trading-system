from __future__ import annotations

from typing import Any


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
        if last_close is None:
            print("[SETUP_ENGINE] no setups: missing_last_close")
            return []

        setups: list[dict] = []

        def add_candidate(setup: dict | None) -> None:
            if not setup:
                return
            setups.append(setup)

        trend = str(normalized_structure.get("trend") or "").upper()
        premarket_high = self._safe_float(normalized_levels.get("premarket_high"))
        hod = self._safe_float(normalized_levels.get("hod"))
        vwap = self._safe_float(normalized_levels.get("vwap"))
        ema9 = self._safe_float(normalized_levels.get("ema_9") or normalized_levels.get("ema9"))
        range_info = normalized_levels.get("active_breakout_range") if isinstance(normalized_levels.get("active_breakout_range"), dict) else {}
        range_upper = self._safe_float((range_info or {}).get("upper"))
        range_lower = self._safe_float((range_info or {}).get("lower"))
        pullback_depth = self._safe_float((normalized_structure.get("pullback_depth") or {}).get("pct"))
        prev_close = self._previous_close(candles)
        pullback_high = self._safe_float(
            normalized_levels.get("pullback_high")
            or normalized_levels.get("first_pullback_high")
            or normalized_levels.get("micro_pullback_high")
        )
        micro_range_high = self._safe_float(
            normalized_levels.get("micro_range_high")
            or normalized_levels.get("micro_pullback_high")
            or range_upper
        )
        near_high_band = 0.0025
        near_hod = bool(hod is not None and last_close >= hod * (1.0 - near_high_band))
        early_session = str(session_context or "").upper() in {"PRE", "PREMARKET", "RTH_OPEN", "OPENING_DRIVE", "MORNING_MOMENTUM", "EARLY"}
        sequence_first_pullback = self._has_impulse_pullback_continuation(candles)
        contraction_active = self._has_range_contraction(candles)

        first_pullback_trigger = bool(
            pullback_high is not None
            and prev_close is not None
            and prev_close < pullback_high <= last_close
            and (hod is None or last_close < hod)
        )
        first_pullback_valid = bool(
            trend == "UP"
            and sequence_first_pullback
            and bool(normalized_structure.get("pullback_active"))
            and pullback_depth is not None
            and pullback_depth <= 0.5
            and first_pullback_trigger
        )

        micro_pullback_trigger = bool(
            micro_range_high is not None and prev_close is not None and prev_close < micro_range_high <= last_close
        )
        micro_pullback_valid = bool(
            trend == "UP"
            and bool(normalized_structure.get("compression_active"))
            and pullback_depth is not None
            and pullback_depth <= 0.3
            and micro_pullback_trigger
        )

        bull_flag_trigger = bool(
            range_upper is not None
            and prev_close is not None
            and prev_close < range_upper <= last_close
        )
        bull_flag_valid = bool(
            trend == "UP"
            and bool(normalized_structure.get("impulse_active"))
            and bool(normalized_structure.get("consolidation_active"))
            and contraction_active
            and bull_flag_trigger
        )

        pmh_trigger = bool(
            premarket_high is not None
            and prev_close is not None
            and prev_close < premarket_high <= last_close
        )
        premarket_high_break_valid = bool(
            pmh_trigger
            and early_session
        )

        hod_break_valid = bool(
            hod is not None
            and prev_close is not None
            and prev_close < hod <= last_close
            and near_hod
        )

        # Structural distinction hard-constraint: these setup families must not fire on the same candle.
        distinction_flags = {
            "FIRST_PULLBACK": first_pullback_valid,
            "MICRO_PULLBACK": micro_pullback_valid,
            "BULL_FLAG": bull_flag_valid,
            "HOD_BREAK": hod_break_valid,
            "PREMARKET_HIGH_BREAK": premarket_high_break_valid,
        }
        primary_setup = self._primary_distinct_setup(distinction_flags)
        for key in tuple(distinction_flags.keys()):
            distinction_flags[key] = bool(primary_setup == key)
        first_pullback_valid = distinction_flags["FIRST_PULLBACK"]
        micro_pullback_valid = distinction_flags["MICRO_PULLBACK"]
        bull_flag_valid = distinction_flags["BULL_FLAG"]
        hod_break_valid = distinction_flags["HOD_BREAK"]
        premarket_high_break_valid = distinction_flags["PREMARKET_HIGH_BREAK"]
        print("[SETUP_ENGINE][DISTINCTION_CHECK]")
        print(
            f"symbol={normalized_levels.get('symbol') or normalized_levels.get('ticker') or 'UNKNOWN'} "
            f"first_pullback={first_pullback_valid} micro_pullback={micro_pullback_valid} "
            f"bull_flag={bull_flag_valid} hod_break={hod_break_valid}"
        )

        add_candidate(
            self._setup_break(
                family="PREMARKET_HIGH_BREAK",
                name="Premarket High Break",
                direction="LONG",
                rationale="Price pressing through premarket high.",
                confidence=0.64,
                trigger_types=["PMH_BREAK", "BREAKOUT_HIGH"],
                invalidation_anchor="premarket_low",
                condition=premarket_high_break_valid,
                levels=normalized_levels,
                quality_flags=["EARLY_SESSION"] if early_session else ["OUTSIDE_EARLY_SESSION"],
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
                condition=first_pullback_valid,
                levels=normalized_levels,
                quality_flags=["STRUCTURE_SEQUENCE"],
                blocking_flags=[] if trend == "UP" else ["TREND_NOT_UP"],
            )
        )

        add_candidate(
            self._setup_break(
                family="MICRO_PULLBACK",
                name="Micro Pullback",
                direction="LONG",
                rationale="Uptrend micro pause with compression and impulse potential.",
                confidence=0.58,
                trigger_types=["MICRO_RANGE_BREAK"],
                invalidation_anchor="micro_pullback_low",
                condition=micro_pullback_valid,
                levels=normalized_levels,
                quality_flags=["MICRO_STRUCTURE", "COMPRESSION_ACTIVE"],
                blocking_flags=[] if trend == "UP" else ["TREND_NOT_UP"],
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
                condition=bull_flag_valid,
                levels=normalized_levels,
                quality_flags=["IMPULSE_PLUS_CONSOLIDATION", "RANGE_CONTRACTION"],
                blocking_flags=[] if trend == "UP" else ["TREND_NOT_UP"],
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
                condition=hod_break_valid,
                levels=normalized_levels,
                quality_flags=["NEAR_HIGHS"],
                blocking_flags=[] if hod is not None else ["MISSING_HOD"],
            )
        )

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
            if ema9 is None:
                setup["quality_flags"].append("EMA9_MISSING")
        print(
            "[SETUP_ENGINE] "
            f"produced={len(setups)} families={[item.get('setup_family_id') for item in setups]}"
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
            "direction": direction,
            "rationale": rationale,
            "confidence": round(max(0.0, min(1.0, confidence)), self._ROUNDING),
            "quality_flags": sorted(set(str(flag) for flag in quality_flags if flag)),
            "blocking_flags": sorted(set(str(flag) for flag in blocking_flags if flag)),
            "invalidation_anchor": invalidation_anchor,
            "required_trigger_types": [str(t).upper() for t in trigger_types],
            # backward compatibility fields expected by some existing consumers
            "context": "continuation" if "PULLBACK" in family or "RECLAIM" in family else "breakout",
            "trigger_level": self._primary_trigger_level(family=family, levels=levels),
            "confidence_label": "HIGH" if confidence >= 0.67 else ("MEDIUM" if confidence >= 0.55 else "LOW"),
        }
        return setup

    def _has_impulse_pullback_continuation(self, candles: list) -> bool:
        if len(candles) < 4:
            return False
        closes = [self._safe_float(self._read(c, "close")) for c in candles[-6:]]
        if any(v is None for v in closes):
            return False
        first, second, third, fourth = closes[-4:]
        return bool(second > first and third < second and fourth > third and fourth >= second)

    def _has_range_contraction(self, candles: list) -> bool:
        if len(candles) < 5:
            return False
        window = candles[-5:]
        widths: list[float] = []
        for candle in window:
            high = self._safe_float(self._read(candle, "high"))
            low = self._safe_float(self._read(candle, "low"))
            if high is None or low is None:
                return False
            widths.append(max(high - low, 0.0))
        head = sum(widths[:2]) / 2.0
        tail = sum(widths[-2:]) / 2.0
        return bool(head > 0 and tail <= head * 0.85)

    @staticmethod
    def _primary_distinct_setup(flags: dict[str, bool]) -> str | None:
        priority = [
            "PREMARKET_HIGH_BREAK",
            "FIRST_PULLBACK",
            "MICRO_PULLBACK",
            "BULL_FLAG",
            "HOD_BREAK",
        ]
        for family in priority:
            if flags.get(family):
                return family
        return None

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
