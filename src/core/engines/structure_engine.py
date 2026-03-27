from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class StructureEngine:
    """Shared market structure engine with explainable state output."""

    _ROUNDING = 6
    STRUCTURE_MIN_CANDLES_HARD = 15
    STRUCTURE_MIN_CANDLES_PREFERRED = 20

    def compute_structure(self, candles: list) -> dict:
        structure = {
            "dominant_direction": "UNKNOWN",
            "impulse_active": False,
            "pullback_active": False,
            "consolidation_active": False,
            "compression_active": False,
            "exhaustion_warning": False,
            "reclaim_state": "NONE",
            "rejection_state": "NONE",
            "extension_state": "NONE",
            "pullback_depth": {"pct": None, "anchor_high": None, "anchor_low": None},
            "range_width": {"abs": None, "pct_of_price": None},
            "trend_phase": "UNDEFINED",
            "stair_step_state": "UNKNOWN",
            "structure_quality_flags": [],
            "swing_highs": [],
            "swing_lows": [],
            # backward compatibility fields
            "trend": "UNKNOWN",
            "structure_state": None,
            "last_higher_high": None,
            "last_higher_low": None,
            "last_lower_high": None,
            "last_lower_low": None,
            "is_valid": False,
            "reason_code": "UNINITIALIZED",
            "explain": [],
        }
        if len(candles) < 3:
            structure["structure_quality_flags"] = ["INSUFFICIENT_CANDLES", "LOW_CONFIDENCE"]
            structure["trend"] = "SIDEWAYS" if candles else "UNKNOWN"
            structure["structure_state"] = "RANGE" if candles else None
            structure["reason_code"] = "INSUFFICIENT_CANDLES"
            logger.debug(
                "[STRUCTURE_ENGINE] candles=%s quality=%s",
                len(candles),
                structure["structure_quality_flags"],
            )
            return structure

        highs = [self._safe_float(self._read(c, "high")) for c in candles]
        lows = [self._safe_float(self._read(c, "low")) for c in candles]
        closes = [self._safe_float(self._read(c, "close")) for c in candles]
        opens = [self._safe_float(self._read(c, "open")) for c in candles]

        swing_highs = self._pivot_levels(candles, use_high=True)
        swing_lows = self._pivot_levels(candles, use_high=False)
        structure["swing_highs"] = swing_highs
        structure["swing_lows"] = swing_lows

        trend = self._detect_trend(swing_highs=swing_highs, swing_lows=swing_lows)
        if trend in {"UNKNOWN", "SIDEWAYS"}:
            trend = self._infer_direction_from_closes(closes=closes, current_trend=trend)
        dominant_direction = {"UP": "LONG", "DOWN": "SHORT", "SIDEWAYS": "NEUTRAL", "UNKNOWN": "UNKNOWN"}.get(trend, "UNKNOWN")
        structure["trend"] = trend
        structure["dominant_direction"] = dominant_direction

        last_close = self._last_valid(closes)
        recent_high = self._window_max(highs, window=min(5, len(highs)))
        recent_low = self._window_min(lows, window=min(5, len(lows)))

        impulse_active = False
        pullback_active = False
        if last_close is not None and recent_high is not None and recent_low is not None:
            width = max(recent_high - recent_low, 0.0)
            recent_closes = [value for value in closes[-5:] if value is not None]
            impulse_active = bool(
                width > 0
                and (
                    (trend == "UP" and any(close >= recent_high - (0.15 * width) for close in recent_closes))
                    or (trend == "DOWN" and any(close <= recent_low + (0.15 * width) for close in recent_closes))
                )
            )
            pullback_active = bool(
                width > 0
                and (
                    (trend == "UP" and any(close <= recent_high - (0.4 * width) for close in recent_closes))
                    or (trend == "DOWN" and any(close >= recent_low + (0.4 * width) for close in recent_closes))
                )
            )

        range_abs = None
        range_pct = None
        if recent_high is not None and recent_low is not None:
            range_abs = round(max(recent_high - recent_low, 0.0), self._ROUNDING)
            if last_close and last_close > 0:
                range_pct = round(range_abs / last_close, self._ROUNDING)

        consolidation_active = bool(range_pct is not None and range_pct <= 0.02)
        compression_active = bool(range_pct is not None and range_pct <= 0.01)

        pullback_depth = self._pullback_depth(trend=trend, recent_high=recent_high, recent_low=recent_low, last_close=last_close)
        exhaustion_warning = bool(
            trend in {"UP", "DOWN"}
            and pullback_depth["pct"] is not None
            and pullback_depth["pct"] >= 0.75
        )

        reclaim_state, rejection_state, extension_state = self._context_states(
            trend=trend,
            opens=opens,
            closes=closes,
            highs=highs,
            lows=lows,
        )

        structure_state = "RANGE" if trend == "SIDEWAYS" or consolidation_active else ("IMPULSE" if impulse_active else "PULLBACK")
        trend_phase = "TRENDING" if trend in {"UP", "DOWN"} else "BASING"
        stair_step_state = "STAIR_STEP" if trend in {"UP", "DOWN"} and len(swing_highs) >= 2 and len(swing_lows) >= 2 else "NO_STAIR_STEP"

        flags: list[str] = []
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            flags.append("LIMITED_SWING_CONTEXT")
        if self._has_missing_ohlc(highs=highs, lows=lows, closes=closes):
            flags.append("PARTIAL_OHLC_DATA")
        if trend == "UNKNOWN":
            flags.append("TREND_UNRESOLVED")
            flags.append("LOW_CONFIDENCE")

        structure.update(
            {
                "impulse_active": impulse_active,
                "pullback_active": pullback_active,
                "consolidation_active": consolidation_active,
                "compression_active": compression_active,
                "exhaustion_warning": exhaustion_warning,
                "reclaim_state": reclaim_state,
                "rejection_state": rejection_state,
                "extension_state": extension_state,
                "pullback_depth": pullback_depth,
                "range_width": {"abs": range_abs, "pct_of_price": range_pct},
                "trend_phase": trend_phase,
                "stair_step_state": stair_step_state,
                "structure_quality_flags": flags,
                "structure_state": structure_state,
                "last_higher_high": swing_highs[-1] if trend == "UP" and swing_highs else None,
                "last_higher_low": swing_lows[-1] if trend == "UP" and swing_lows else None,
                "last_lower_high": swing_highs[-1] if trend == "DOWN" and swing_highs else None,
                "last_lower_low": swing_lows[-1] if trend == "DOWN" and swing_lows else None,
                "explain": [
                    f"trend={trend}",
                    f"dominant_direction={dominant_direction}",
                    f"structure_state={structure_state}",
                    f"range_pct={range_pct}",
                ],
            }
        )
        is_valid, reason_code = self._validate_structure(
            candles=candles,
            impulse_active=impulse_active,
            pullback_active=pullback_active,
        )
        structure["is_valid"] = is_valid
        structure["reason_code"] = reason_code
        logger.debug(
            "[STRUCTURE_ENGINE] trend=%s direction=%s impulse=%s pullback=%s consolidation=%s compression=%s valid=%s reason=%s flags=%s",
            trend,
            dominant_direction,
            impulse_active,
            pullback_active,
            consolidation_active,
            compression_active,
            is_valid,
            reason_code,
            flags,
        )
        return structure

    def _validate_structure(
        self,
        *,
        candles: list,
        impulse_active: bool,
        pullback_active: bool,
    ) -> tuple[bool, str]:
        candle_count = len(candles or [])
        if candle_count < self.STRUCTURE_MIN_CANDLES_HARD:
            return False, "INSUFFICIENT_CANDLES"
        if not impulse_active:
            return False, "NO_IMPULSE"
        if not pullback_active:
            return False, "NO_PULLBACK"
        if candle_count < self.STRUCTURE_MIN_CANDLES_PREFERRED:
            return True, "VALID_LOW_SAMPLE_SIZE"
        return True, "VALID"

    @staticmethod
    def _read(item: Any, field: str) -> Any:
        return item.get(field) if isinstance(item, dict) else getattr(item, field, None)

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    def _pivot_levels(self, candles: list, *, use_high: bool, neighbors: int = 2) -> list[float]:
        if len(candles) < (neighbors * 2) + 1:
            return []
        field = "high" if use_high else "low"
        pivots: list[float] = []
        for idx in range(neighbors, len(candles) - neighbors):
            center = self._safe_float(self._read(candles[idx], field))
            if center is None:
                continue
            left = [self._safe_float(self._read(candles[i], field)) for i in range(idx - neighbors, idx)]
            right = [self._safe_float(self._read(candles[i], field)) for i in range(idx + 1, idx + neighbors + 1)]
            neighborhood = [v for v in left + right if v is not None]
            if len(neighborhood) < neighbors * 2:
                continue
            is_pivot = all(center > value for value in neighborhood) if use_high else all(center < value for value in neighborhood)
            if is_pivot:
                pivots.append(round(center, self._ROUNDING))
        return pivots

    @staticmethod
    def _detect_trend(*, swing_highs: list[float], swing_lows: list[float]) -> str:
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "SIDEWAYS" if (swing_highs or swing_lows) else "UNKNOWN"
        highs_rising = swing_highs[-1] > swing_highs[-2]
        lows_rising = swing_lows[-1] > swing_lows[-2]
        highs_falling = swing_highs[-1] < swing_highs[-2]
        lows_falling = swing_lows[-1] < swing_lows[-2]
        if highs_rising and lows_rising:
            return "UP"
        if highs_falling and lows_falling:
            return "DOWN"
        return "SIDEWAYS"

    @staticmethod
    def _infer_direction_from_closes(*, closes: list[float | None], current_trend: str) -> str:
        valid = [c for c in closes[-10:] if c is not None]
        if len(valid) < 3:
            return current_trend
        first = valid[0]
        last = valid[-1]
        if first <= 0:
            return current_trend
        change = (last - first) / first
        if change >= 0.015:
            return "UP"
        if change <= -0.015:
            return "DOWN"
        return current_trend

    @staticmethod
    def _window_max(values: list[float | None], window: int) -> float | None:
        valid = [v for v in values[-window:] if v is not None]
        return None if not valid else max(valid)

    @staticmethod
    def _window_min(values: list[float | None], window: int) -> float | None:
        valid = [v for v in values[-window:] if v is not None]
        return None if not valid else min(valid)

    @staticmethod
    def _last_valid(values: list[float | None]) -> float | None:
        for value in reversed(values):
            if value is not None:
                return value
        return None

    @staticmethod
    def _has_missing_ohlc(*, highs: list[float | None], lows: list[float | None], closes: list[float | None]) -> bool:
        return any(v is None for v in highs[-5:] + lows[-5:] + closes[-5:])

    def _pullback_depth(
        self,
        *,
        trend: str,
        recent_high: float | None,
        recent_low: float | None,
        last_close: float | None,
    ) -> dict[str, float | None]:
        if recent_high is None or recent_low is None or last_close is None or recent_high == recent_low:
            return {"pct": None, "anchor_high": recent_high, "anchor_low": recent_low}
        width = max(recent_high - recent_low, 1e-9)
        if trend == "UP":
            pct = (recent_high - last_close) / width
        elif trend == "DOWN":
            pct = (last_close - recent_low) / width
        else:
            pct = 0.0
        return {
            "pct": round(max(0.0, min(1.0, pct)), self._ROUNDING),
            "anchor_high": round(recent_high, self._ROUNDING),
            "anchor_low": round(recent_low, self._ROUNDING),
        }

    def _context_states(
        self,
        *,
        trend: str,
        opens: list[float | None],
        closes: list[float | None],
        highs: list[float | None],
        lows: list[float | None],
    ) -> tuple[str, str, str]:
        if len(closes) < 2:
            return "NONE", "NONE", "NONE"
        prev_close = self._last_valid(closes[:-1])
        last_close = self._last_valid(closes)
        last_open = self._last_valid(opens)
        prev_high = self._last_valid(highs[:-1])
        prev_low = self._last_valid(lows[:-1])

        reclaim_state = "NONE"
        rejection_state = "NONE"
        extension_state = "NONE"
        if prev_close is not None and last_close is not None:
            if trend == "UP" and last_close > prev_close:
                reclaim_state = "BULLISH_RECLAIM"
            elif trend == "DOWN" and last_close < prev_close:
                reclaim_state = "BEARISH_RECLAIM"

        if last_open is not None and last_close is not None and prev_high is not None and prev_low is not None:
            if last_close < last_open and last_close < prev_high:
                rejection_state = "TOP_REJECTION"
            elif last_close > last_open and last_close > prev_low:
                rejection_state = "BOTTOM_REJECTION"

        if last_close is not None and prev_close is not None:
            move = abs(last_close - prev_close)
            price_ref = max(abs(prev_close), 1e-6)
            if move / price_ref >= 0.015:
                extension_state = "EXTENDED"
            else:
                extension_state = "NORMAL"
        return reclaim_state, rejection_state, extension_state
