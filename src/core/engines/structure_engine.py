from __future__ import annotations

from typing import Any


class StructureEngine:
    """Derives market structure context from candles."""

    _ROUNDING = 6

    def compute_structure(
        self,
        candles: list,
    ) -> dict:
        structure = {
            "trend": None,
            "structure_state": None,
            "last_higher_high": None,
            "last_higher_low": None,
            "last_lower_high": None,
            "last_lower_low": None,
            "swing_highs": [],
            "swing_lows": [],
        }
        if len(candles) < 5:
            return structure

        swing_highs = self._pivot_levels(candles, use_high=True)
        swing_lows = self._pivot_levels(candles, use_high=False)
        structure["swing_highs"] = swing_highs
        structure["swing_lows"] = swing_lows

        trend = self._detect_trend(swing_highs=swing_highs, swing_lows=swing_lows)
        structure["trend"] = trend
        if trend == "UP":
            structure["last_higher_high"] = swing_highs[-1]
            structure["last_higher_low"] = swing_lows[-1]
        elif trend == "DOWN":
            structure["last_lower_high"] = swing_highs[-1]
            structure["last_lower_low"] = swing_lows[-1]

        structure["structure_state"] = self._detect_structure_state(
            trend=trend,
            candles=candles,
            structure=structure,
        )
        return structure

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
    def _detect_trend(*, swing_highs: list[float], swing_lows: list[float]) -> str | None:
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "SIDEWAYS" if (swing_highs or swing_lows) else None
        highs_rising = swing_highs[-1] > swing_highs[-2]
        lows_rising = swing_lows[-1] > swing_lows[-2]
        highs_falling = swing_highs[-1] < swing_highs[-2]
        lows_falling = swing_lows[-1] < swing_lows[-2]
        if highs_rising and lows_rising:
            return "UP"
        if highs_falling and lows_falling:
            return "DOWN"
        return "SIDEWAYS"

    def _detect_structure_state(self, *, trend: str | None, candles: list, structure: dict) -> str | None:
        if trend is None:
            return None
        if trend == "SIDEWAYS":
            return "RANGE"

        last_close = self._safe_float(self._read(candles[-1], "close")) if candles else None
        if last_close is None:
            return "RANGE"

        if trend == "UP":
            last_higher_high = self._safe_float(structure.get("last_higher_high"))
            last_higher_low = self._safe_float(structure.get("last_higher_low"))
            if last_higher_high is not None and last_close >= last_higher_high:
                return "IMPULSE"
            if last_higher_low is not None and last_close < last_higher_low:
                return "PULLBACK"
            return "PULLBACK"

        last_lower_low = self._safe_float(structure.get("last_lower_low"))
        last_lower_high = self._safe_float(structure.get("last_lower_high"))
        if last_lower_low is not None and last_close <= last_lower_low:
            return "IMPULSE"
        if last_lower_high is not None and last_close > last_lower_high:
            return "PULLBACK"
        return "PULLBACK"
