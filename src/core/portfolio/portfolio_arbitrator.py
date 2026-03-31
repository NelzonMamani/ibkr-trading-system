from __future__ import annotations

from typing import Any

from src.config.config_resolver import get_config
from src.core.portfolio.portfolio_state import PortfolioState
from src.models.data_models import TradeIntent


class PortfolioArbitrator:
    """Deterministic portfolio-level ranking and capital allocation gate."""

    def select_trades(
        self,
        trade_intents: list[TradeIntent],
        portfolio_state: PortfolioState,
    ) -> list[TradeIntent]:
        """
        Deterministically select best trades given capital + risk constraints.
        """

        candidates = [
            intent
            for intent in (trade_intents or [])
            if bool(getattr(intent, "allowed", True))
            and not bool(getattr(intent, "execution_blocked", False))
        ]

        scored = [
            (
                self._score_intent(intent),
                str(getattr(intent, "symbol", "") or ""),
                str(getattr(intent, "strategy_name", "") or ""),
                str(getattr(intent, "direction", "") or ""),
                str(getattr(intent, "decision_id", "") or ""),
                str(getattr(intent, "intent_id", "") or ""),
                intent,
            )
            for intent in candidates
        ]
        scored.sort(key=lambda row: (-row[0], row[1], row[2], row[3], row[4], row[5]))

        max_positions = int(get_config("LIFECYCLE_MAX_POSITIONS"))
        max_portfolio_exposure = float(get_config("LIFECYCLE_MAX_PORTFOLIO_EXPOSURE"))
        max_position_exposure = float(get_config("LIFECYCLE_MAX_POSITION_EXPOSURE"))

        current_open_positions = int(getattr(portfolio_state, "total_open_positions", 0) or 0)
        current_exposure = float(getattr(portfolio_state, "total_exposure", 0.0) or 0.0)

        selected: list[TradeIntent] = []
        next_exposure = current_exposure
        next_open_positions = current_open_positions

        for score, *_tie, intent in scored:
            _ = score
            intent_exposure = self._resolve_intent_exposure(intent)
            if intent_exposure > max_position_exposure:
                continue
            if next_exposure + intent_exposure > max_portfolio_exposure:
                continue
            if next_open_positions + 1 > max_positions:
                continue
            selected.append(intent)
            next_exposure += intent_exposure
            next_open_positions += 1

        top_symbol = "NONE"
        top_score = 0.0
        if scored:
            top_score = float(scored[0][0])
            top_symbol = str(scored[0][1] or "NONE")

        print(
            "[ARBITRATOR] "
            f"total_candidates={len(candidates)} "
            f"selected={len(selected)} "
            f"rejected={max(0, len(candidates) - len(selected))} "
            f"top_symbol={top_symbol} score={top_score:.2f}"
        )

        return selected

    def _score_intent(self, intent: Any) -> float:
        confidence = self._clamp01(self._to_float(getattr(intent, "confidence", 0.0), 0.0))

        relative_volume_raw = getattr(intent, "relative_volume_score", None)
        if relative_volume_raw is None:
            relative_volume_raw = getattr(intent, "rvol", None)
        relative_volume_score = self._normalize_relative_volume(relative_volume_raw)

        pattern_quality_raw = getattr(intent, "pattern_quality_score", None)
        pattern_quality_score = self._normalize_optional_score(
            pattern_quality_raw,
            fallback=confidence if getattr(intent, "pattern_name", None) else 0.0,
        )

        spread_quality_raw = getattr(intent, "spread_quality_score", None)
        spread_quality_score = self._normalize_spread_quality(spread_quality_raw, intent)

        proximity_raw = getattr(intent, "proximity_to_key_level", None)
        proximity_score = self._normalize_optional_score(proximity_raw, fallback=0.5)

        return (
            confidence * 0.4
            + relative_volume_score * 0.2
            + pattern_quality_score * 0.2
            + spread_quality_score * 0.1
            + proximity_score * 0.1
        )

    def _resolve_intent_exposure(self, intent: Any) -> float:
        direct = self._to_float(
            getattr(intent, "position_exposure", None)
            or getattr(intent, "requested_exposure", None)
            or getattr(intent, "trade_value", None)
            or getattr(intent, "exposure", None),
            0.0,
        )
        if direct > 0:
            return direct

        qty = int(
            self._to_float(
                getattr(intent, "quantity", None)
                or getattr(intent, "requested_quantity", None)
                or getattr(intent, "max_position_size", None),
                1.0,
            )
        )
        if qty <= 0:
            qty = 1

        price = self._to_float(
            getattr(intent, "entry_price", None)
            or getattr(intent, "price", None)
            or getattr(intent, "raw_price", None),
            0.0,
        )
        return max(0.0, qty * price)

    @staticmethod
    def _to_float(value: Any, default: float) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _clamp01(cls, value: float) -> float:
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    def _normalize_optional_score(self, value: Any, fallback: float) -> float:
        if value is None:
            return self._clamp01(fallback)
        raw = self._to_float(value, fallback)
        if raw > 1.0:
            raw = raw / 100.0 if raw > 10.0 else raw
        return self._clamp01(raw)

    def _normalize_relative_volume(self, value: Any) -> float:
        if value is None:
            return 0.0
        raw = self._to_float(value, 0.0)
        if raw <= 0:
            return 0.0
        if raw <= 1.0:
            return self._clamp01(raw)
        return self._clamp01(raw / 5.0)

    def _normalize_spread_quality(self, spread_quality_raw: Any, intent: Any) -> float:
        if spread_quality_raw is not None:
            return self._normalize_optional_score(spread_quality_raw, fallback=0.0)

        spread = self._to_float(getattr(intent, "spread", None), 0.0)
        price = self._to_float(
            getattr(intent, "entry_price", None)
            or getattr(intent, "price", None),
            0.0,
        )
        if spread <= 0.0 or price <= 0.0:
            return 0.5
        spread_pct = spread / price
        return self._clamp01(1.0 - (spread_pct / 0.02))
