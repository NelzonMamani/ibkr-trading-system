from __future__ import annotations

from typing import Any


class PatternEngine:
    """Ross-first confirmation engine for validating setup quality before triggers."""

    def evaluate_pattern(
        self,
        *,
        symbol: str,
        setup_output: dict[str, Any],
        candles: list,
        indicators: dict | None = None,
        volume_context: dict | None = None,
        levels: dict | None = None,
        liquidity_context: dict | None = None,
    ) -> dict[str, Any]:
        setup_family = str(setup_output.get("setup_family") or "UNKNOWN")
        print(f"[ROSS][PATTERN][CHECK] symbol={symbol} setup={setup_family}")

        if not bool(setup_output.get("setup_valid")):
            reason = "setup_invalid"
            print(f"[ROSS][PATTERN][REJECT] symbol={symbol} reason={reason}")
            return {
                "pattern_valid": False,
                "pattern_reason": reason,
                "confirmation_tags": [],
                "disqualifying_flags": [reason],
            }

        if len(candles or []) < 3:
            reason = "insufficient_candles"
            print(f"[ROSS][PATTERN][REJECT] symbol={symbol} reason={reason}")
            return {
                "pattern_valid": False,
                "pattern_reason": reason,
                "confirmation_tags": [],
                "disqualifying_flags": [reason],
            }

        lows = [self._safe_float(self._read(candle, "low")) for candle in candles[-4:]]
        highs = [self._safe_float(self._read(candle, "high")) for candle in candles[-4:]]
        volumes = [self._safe_float(self._read(candle, "volume")) for candle in candles[-6:]]
        closes = [self._safe_float(self._read(candle, "close")) for candle in candles[-4:]]

        pullback_low = self._safe_float(setup_output.get("pullback_low"))
        candidate_entry = self._safe_float(setup_output.get("candidate_entry_level"))
        confirmation_tags: list[str] = []
        disqualifying_flags: list[str] = []

        if len(lows) >= 2 and lows[-2] is not None and lows[-1] is not None:
            if lows[-1] >= lows[-2]:
                confirmation_tags.append("HIGHER_LOW_OR_STABLE_LOW")
            elif abs(lows[-2] - lows[-1]) <= max(0.01, lows[-2] * 0.002):
                confirmation_tags.append("HIGHER_LOW_OR_STABLE_LOW")
            else:
                disqualifying_flags.append("LOWER_LOW_PULLBACK")

        if len(highs) >= 3 and all(v is not None for v in highs[-3:]):
            cha = max(highs[-3:]) - min(highs[-3:])
            if candidate_entry and candidate_entry > 0 and cha / candidate_entry <= 0.03:
                confirmation_tags.append("TIGHT_PULLBACK")
            else:
                disqualifying_flags.append("CHAOTIC_PULLBACK")

        if len(volumes) >= 4 and all(v is not None for v in volumes[-4:]):
            impulse_volume = max(volumes[:-2]) if volumes[:-2] else None
            pullback_volume = max(volumes[-2:])
            if impulse_volume and pullback_volume <= impulse_volume:
                confirmation_tags.append("PULLBACK_VOLUME_LIGHTER_THAN_IMPULSE")
            elif impulse_volume:
                disqualifying_flags.append("PULLBACK_VOLUME_TOO_HEAVY")

        last_low = next((v for v in reversed(lows) if v is not None), None)
        if pullback_low is not None and last_low is not None and last_low < pullback_low:
            disqualifying_flags.append("BROKE_BELOW_PULLBACK_LOW")
        else:
            confirmation_tags.append("PULLBACK_LOW_HELD")

        if len(closes) >= 3 and all(v is not None for v in closes[-3:]):
            if closes[-1] >= min(closes[-3:]):
                confirmation_tags.append("FRONT_SIDE_MOMENTUM_INTACT")
            else:
                disqualifying_flags.append("FRONT_SIDE_MOMENTUM_INVALIDATED")

        pattern_valid = len(disqualifying_flags) == 0 and len(confirmation_tags) > 0
        reason = "pattern_confirmed" if pattern_valid else "pattern_rejected"

        if pattern_valid:
            print(
                "[ROSS][PATTERN][VALID] "
                f"symbol={symbol} tags={sorted(set(confirmation_tags))}"
            )
        else:
            print(
                "[ROSS][PATTERN][REJECT] "
                f"symbol={symbol} reason={reason} flags={sorted(set(disqualifying_flags))}"
            )

        return {
            "pattern_valid": pattern_valid,
            "pattern_reason": reason,
            "confirmation_tags": sorted(set(confirmation_tags)),
            "disqualifying_flags": sorted(set(disqualifying_flags)),
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
