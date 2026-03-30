from __future__ import annotations

from typing import Any

from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_inputs import (
    IndicatorSet,
    LevelSet,
    LiquidityContext,
    PatternInputs,
)
from src.strategies.ross_momentum.patterns.pattern_registry import RossPatternRegistry
from src.strategies.ross_momentum.patterns.pattern_types import PatternResult
from src.strategies.strategy_contracts import SessionContext


class SetupEngine:
    """Shared setup engine delegating setup detection to the Ross pattern registry."""

    _SESSION_ALIASES: dict[str, SessionContext] = {
        "PRE": SessionContext.PRE,
        "PREMARKET": SessionContext.PRE,
        "REGULAR": SessionContext.REGULAR,
        "RTH": SessionContext.REGULAR,
        "AFTER": SessionContext.AFTER,
        "POST": SessionContext.AFTER,
        "AFTER_HOURS": SessionContext.AFTER,
    }

    def compute_setups(
        self,
        candles: list,
        levels: dict,
        structure: dict,
        *,
        symbol: str = "UNKNOWN",
        timeframe: str = "1m",
        session_context: str | SessionContext | None = None,
        tradability_context: dict | None = None,
    ) -> list[dict]:
        print(f"[SETUP_ENGINE][CALL] symbol={symbol}")

        normalized_levels = levels if isinstance(levels, dict) else {}
        normalized_structure = structure if isinstance(structure, dict) else {}
        normalized_tradability = tradability_context if isinstance(tradability_context, dict) else {}

        pattern_inputs = PatternInputs(
            symbol=str(symbol),
            timeframe=str(timeframe),
            candles=self._coerce_candles(candles),
            session_context=self._normalize_session_context(session_context),
            levels=self._build_level_set(normalized_levels),
            indicators=self._build_indicator_set(normalized_levels),
            liquidity_context=self._build_liquidity_context(normalized_tradability),
            data_quality_flags=list(normalized_structure.get("structure_quality_flags") or []),
        )

        registry = RossPatternRegistry()
        pattern_results = registry.run(pattern_inputs)
        setups = [self._to_setup_result(result) for result in pattern_results if result.detected]

        print(f"[SETUP_ENGINE][RESULT] symbol={symbol} setups={len(setups)}")
        return setups

    def _coerce_candles(self, candles: list) -> list[Candle]:
        converted: list[Candle] = []
        for candle in candles or []:
            if isinstance(candle, Candle):
                converted.append(candle)
                continue
            open_ = self._safe_float(self._read(candle, "open"))
            high = self._safe_float(self._read(candle, "high"))
            low = self._safe_float(self._read(candle, "low"))
            close = self._safe_float(self._read(candle, "close"))
            volume = self._safe_float(self._read(candle, "volume"))
            if None in (open_, high, low, close, volume):
                continue
            converted.append(
                Candle(
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    timestamp=self._read(candle, "timestamp"),
                )
            )
        return converted

    def _normalize_session_context(self, session_context: str | SessionContext | None) -> SessionContext:
        if isinstance(session_context, SessionContext):
            return session_context
        key = str(session_context or "REGULAR").upper()
        return self._SESSION_ALIASES.get(key, SessionContext.REGULAR)

    def _build_level_set(self, levels: dict) -> LevelSet:
        key_levels = levels.get("key_levels") if isinstance(levels.get("key_levels"), dict) else {}
        return LevelSet(
            premarket_high=self._safe_float(levels.get("premarket_high")),
            premarket_low=self._safe_float(levels.get("premarket_low")),
            hod=self._safe_float(levels.get("hod")),
            lod=self._safe_float(levels.get("lod")),
            prior_close=self._safe_float(levels.get("prior_close")),
            key_levels={str(k): float(v) for k, v in key_levels.items() if self._safe_float(v) is not None},
        )

    def _build_indicator_set(self, levels: dict) -> IndicatorSet:
        return IndicatorSet(
            ema9=self._safe_float(levels.get("ema_9") or levels.get("ema9")),
            ema20=self._safe_float(levels.get("ema_20") or levels.get("ema20")),
            ema50=self._safe_float(levels.get("ema_50") or levels.get("ema50")),
            ema200=self._safe_float(levels.get("ema_200") or levels.get("ema200")),
            vwap=self._safe_float(levels.get("vwap")),
        )

    def _build_liquidity_context(self, tradability_context: dict) -> LiquidityContext:
        return LiquidityContext(
            spread=self._safe_float(tradability_context.get("spread")),
            float_millions=self._safe_float(tradability_context.get("float_millions")),
            rvol=self._safe_float(tradability_context.get("rvol")),
        )

    def _to_setup_result(self, pattern_result: PatternResult) -> dict:
        trigger_type = str(pattern_result.trigger_type or "BREAKOUT_HIGH").upper()
        return {
            "setup_family_id": str(pattern_result.setup_family_id or pattern_result.setup_id),
            "setup_family": str(pattern_result.setup_id),
            "setup_name": str(pattern_result.pattern_name),
            "pattern_name": str(pattern_result.pattern_name),
            "direction": str(pattern_result.direction.value if hasattr(pattern_result.direction, "value") else pattern_result.direction),
            "rationale": str(pattern_result.rationale_text or ""),
            "confidence": float(pattern_result.confidence),
            "quality_flags": sorted({*list(pattern_result.setup_quality_tags or []), *list(pattern_result.tags or [])}),
            "risk_flags": list(pattern_result.risk_flags or []),
            "required_trigger_types": [trigger_type],
            "trigger_level": self._safe_float(pattern_result.trigger_level),
            "invalidation_level": self._safe_float(pattern_result.invalidation_level),
            "invalidation_anchor": "pattern_stop" if pattern_result.invalidation_level is not None else "STRUCTURE",
        }

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
