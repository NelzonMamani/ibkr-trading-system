from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.models.data_models import TradeIntent


@dataclass(frozen=True)
class ArbitrationContext:
    max_positions: int
    max_intents_per_cycle: int


@dataclass(frozen=True)
class _ScoredIntent:
    intent: TradeIntent
    score: float


class TradeIntentArbitrator:
    """Pure intent arbitration layer: validate, score, rank, and filter intents."""

    def arbitrate(
        self,
        intents: list[TradeIntent],
        context: ArbitrationContext,
    ) -> list[TradeIntent]:
        if not intents:
            return []

        print(f"[ARBITRATION][INPUT] count={len(intents)}")
        valid_intents = self._validate(intents)
        scored = self._score(valid_intents)
        ranked = sorted(
            scored,
            key=lambda item: (
                -item.score,
                str(getattr(item.intent, "symbol", "")).upper(),
                str(getattr(item.intent, "strategy_name", "")).lower(),
                str(getattr(item.intent, "direction", "")).upper(),
            ),
        )
        print(
            "[ARBITRATION][RANKED] "
            f"count={len(ranked)} top={self._rank_preview(ranked)}"
        )
        filtered = self._resolve_conflicts(ranked)
        print(
            "[ARBITRATION][FILTERED] "
            f"count={len(filtered)} symbols={sorted({i.symbol for i in filtered})}"
        )
        final = self._apply_global_limits(filtered, context)
        print(
            "[ARBITRATION][FINAL] "
            f"count={len(final)} max_positions={context.max_positions} "
            f"max_intents_per_cycle={context.max_intents_per_cycle}"
        )
        return final

    def _validate(self, intents: Iterable[TradeIntent]) -> list[TradeIntent]:
        valid: list[TradeIntent] = []
        for intent in intents:
            symbol = str(getattr(intent, "symbol", "")).strip().upper()
            direction = str(getattr(intent, "direction", "")).strip().upper()
            if not symbol:
                continue
            if direction not in {"LONG", "SHORT"}:
                continue
            valid.append(intent)
        return valid

    def _score(self, intents: Iterable[TradeIntent]) -> list[_ScoredIntent]:
        scored: list[_ScoredIntent] = []
        for intent in intents:
            confidence = self._clamp(
                self._to_float(getattr(intent, "confidence", 0.0), 0.0)
            )
            expected_rr = self._clamp(
                self._to_float(
                    getattr(intent, "expected_rr", None)
                    or getattr(intent, "expected_risk_reward", None),
                    0.0,
                )
            )
            liquidity_score = self._clamp(
                self._to_float(
                    getattr(intent, "liquidity_score", None)
                    or getattr(intent, "relative_volume_score", None)
                    or getattr(intent, "rvol", None),
                    0.0,
                )
            )
            score = confidence * 0.5 + expected_rr * 0.3 + liquidity_score * 0.2
            scored.append(_ScoredIntent(intent=intent, score=score))
        return scored

    def _resolve_conflicts(self, ranked: list[_ScoredIntent]) -> list[TradeIntent]:
        kept_by_symbol: dict[str, TradeIntent] = {}
        seen_intents: set[tuple[str, str, str, str]] = set()
        for entry in ranked:
            intent = entry.intent
            symbol = str(getattr(intent, "symbol", "")).upper()
            strategy_name = str(getattr(intent, "strategy_name", "")).lower()
            direction = str(getattr(intent, "direction", "")).upper()
            dedupe_key = (
                symbol,
                strategy_name,
                direction,
                str(getattr(intent, "rationale", "")),
            )
            if dedupe_key in seen_intents:
                continue
            seen_intents.add(dedupe_key)
            if symbol in kept_by_symbol:
                continue
            kept_by_symbol[symbol] = intent
        return list(kept_by_symbol.values())

    def _apply_global_limits(
        self,
        intents: list[TradeIntent],
        context: ArbitrationContext,
    ) -> list[TradeIntent]:
        max_intents = max(int(context.max_intents_per_cycle or 0), 0)
        max_positions = max(int(context.max_positions or 0), 0)
        limited = intents
        if max_intents > 0:
            limited = limited[:max_intents]
        if max_positions > 0:
            limited = limited[:max_positions]
        return limited

    @staticmethod
    def _to_float(value: object, default: float) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clamp(value: float) -> float:
        if value <= 0.0:
            return 0.0
        if value >= 1.0:
            return 1.0
        return value

    @staticmethod
    def _rank_preview(ranked: list[_ScoredIntent]) -> str:
        if not ranked:
            return "none"
        preview = ranked[:3]
        return ",".join(
            f"{item.intent.symbol}:{item.score:.3f}:{item.intent.direction}" for item in preview
        )
