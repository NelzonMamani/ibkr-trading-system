from __future__ import annotations

from typing import Any


class SetupEngine:
    """Detects high-level trading setups from structure + levels."""

    _ROUNDING = 6

    def compute_setups(
        self,
        candles: list,
        levels: dict,
        structure: dict,
    ) -> list[dict]:
        normalized_levels = levels if isinstance(levels, dict) else {}
        normalized_structure = structure if isinstance(structure, dict) else {}
        last_close = self._last_close(candles)
        if last_close is None:
            return []

        setups: list[dict] = []

        premarket_high = self._safe_float(normalized_levels.get("premarket_high"))
        if premarket_high is not None and last_close >= premarket_high:
            setups.append(
                self._build_setup(
                    setup_family="PREMARKET_HIGH_BREAK",
                    context="breakout",
                    trigger_level=premarket_high,
                    confidence="MEDIUM",
                )
            )

        hod = self._safe_float(normalized_levels.get("hod"))
        if hod is not None and last_close >= hod:
            setups.append(
                self._build_setup(
                    setup_family="HOD_BREAK",
                    context="breakout",
                    trigger_level=hod,
                    confidence="MEDIUM",
                )
            )

        trend = str(normalized_structure.get("trend") or "").upper()
        ema9 = self._safe_float(normalized_levels.get("ema9"))
        if trend == "UP" and self._within_pct(last_close, ema9, pct=0.005):
            setups.append(
                self._build_setup(
                    setup_family="EMA_PULLBACK",
                    context="pullback",
                    trigger_level=ema9,
                    confidence="MEDIUM",
                )
            )

        vwap = self._safe_float(normalized_levels.get("vwap"))
        previous_close = self._previous_close(candles)
        if vwap is not None and previous_close is not None and previous_close < vwap and last_close > vwap:
            setups.append(
                self._build_setup(
                    setup_family="VWAP_RECLAIM",
                    context="reclaim",
                    trigger_level=vwap,
                    confidence="MEDIUM",
                )
            )

        swing_high = self._safe_float(self._latest_swing_high(normalized_structure))
        if trend == "SIDEWAYS" and swing_high is not None and last_close > swing_high:
            setups.append(
                self._build_setup(
                    setup_family="RANGE_BREAK",
                    context="breakout",
                    trigger_level=swing_high,
                    confidence="LOW",
                )
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

    def _within_pct(self, a: float | None, b: float | None, pct: float = 0.005) -> bool:
        if a is None or b is None:
            return False
        if b == 0:
            return False
        return abs(a - b) / abs(b) <= pct

    @staticmethod
    def _latest_swing_high(structure: dict) -> float | None:
        swing_highs = structure.get("swing_highs")
        if isinstance(swing_highs, list) and swing_highs:
            return swing_highs[-1]
        return structure.get("last_higher_high")

    def _build_setup(
        self,
        *,
        setup_family: str,
        context: str,
        trigger_level: float | None,
        confidence: str,
    ) -> dict:
        normalized_trigger = None if trigger_level is None else round(float(trigger_level), self._ROUNDING)
        return {
            "setup_family": setup_family,
            "context": context,
            "trigger_level": normalized_trigger,
            "confidence": confidence,
        }
