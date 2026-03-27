from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class LevelEngine:
    """Canonical shared level engine used by all strategies."""

    _ROUNDING = 6

    def compute_levels(
        self,
        symbol: str,
        candles: list,
        intraday_data: dict,
        premarket_data: dict,
    ) -> dict:
        intraday_candles = self._extract_candles(intraday_data, fallback=candles)
        premarket_candles = self._extract_candles(premarket_data)
        closes = [
            c for c in (self._safe_float(self._read(candle, "close")) for candle in intraday_candles) if c is not None
        ]

        current_price = self._resolve_current_price(candles=candles, intraday_data=intraday_data, closes=closes)
        prior_close = self._resolve_prior_close(candles=candles, intraday_data=intraday_data)

        core_levels = {
            "premarket_high": self._series_max(premarket_candles, "high"),
            "premarket_low": self._series_min(premarket_candles, "low"),
            "hod": self._series_max(intraday_candles, "high"),
            "lod": self._series_min(intraday_candles, "low"),
            "prior_close": prior_close,
            "vwap": self._compute_vwap(intraday_candles),
            "ema_9": self._ema(closes, 9),
            "ema_20": self._ema(closes, 20),
        }

        active_breakout_range = self._derive_active_breakout_range(core_levels)
        missing_level_flags = sorted([f"MISSING_{key.upper()}" for key, value in core_levels.items() if value is None])

        provenance = self._build_provenance(
            core_levels=core_levels,
            intraday_candles=intraday_candles,
            premarket_candles=premarket_candles,
            intraday_data=intraday_data,
            candles=candles,
            active_breakout_range=active_breakout_range,
            current_price=current_price,
        )

        levels = {
            "symbol": str(symbol),
            **core_levels,
            "whole_dollar_levels": self._whole_levels(current_price),
            "half_dollar_levels": self._half_levels(current_price),
            "active_breakout_range": active_breakout_range,
            "provenance": provenance,
            "missing_level_flags": missing_level_flags,
            "computed_at": self._computed_at(candles, intraday_candles, premarket_candles),
            # backward compatibility shims
            "ema9": core_levels["ema_9"],
            "ema20": core_levels["ema_20"],
            "whole_levels": self._whole_levels(current_price),
            "half_levels": self._half_levels(current_price),
            "support_levels": self._pivot_levels(intraday_candles, use_high=False),
            "resistance_levels": self._pivot_levels(intraday_candles, use_high=True),
        }

        if missing_level_flags:
            print(f"[LEVEL_ENGINE] symbol={symbol} missing={missing_level_flags}")
        print(
            "[LEVEL_ENGINE] "
            f"symbol={symbol} pmh={levels.get('premarket_high')} pml={levels.get('premarket_low')} "
            f"hod={levels.get('hod')} lod={levels.get('lod')} prior_close={levels.get('prior_close')} "
            f"vwap={levels.get('vwap')} ema_9={levels.get('ema_9')} ema_20={levels.get('ema_20')}"
        )
        return levels

    def _extract_candles(self, payload: dict | None, fallback: list | None = None) -> list:
        if isinstance(payload, dict):
            raw = payload.get("candles")
            if isinstance(raw, list):
                return raw
        return list(fallback or [])

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

    def _series_max(self, candles: list, field: str) -> float | None:
        values = [v for v in (self._safe_float(self._read(candle, field)) for candle in candles) if v is not None]
        return None if not values else round(max(values), self._ROUNDING)

    def _series_min(self, candles: list, field: str) -> float | None:
        values = [v for v in (self._safe_float(self._read(candle, field)) for candle in candles) if v is not None]
        return None if not values else round(min(values), self._ROUNDING)

    def _compute_vwap(self, candles: list) -> float | None:
        total_pv = 0.0
        total_volume = 0.0
        for candle in candles:
            high = self._safe_float(self._read(candle, "high"))
            low = self._safe_float(self._read(candle, "low"))
            close = self._safe_float(self._read(candle, "close"))
            volume = self._safe_float(self._read(candle, "volume")) or 0.0
            if high is None or low is None or close is None:
                continue
            typical_price = (high + low + close) / 3.0
            total_pv += typical_price * volume
            total_volume += volume
        if total_volume <= 0:
            return None
        return round(total_pv / total_volume, self._ROUNDING)

    def _ema(self, closes: list[float], period: int) -> float | None:
        if not closes:
            return None
        multiplier = 2.0 / (period + 1)
        ema_value = float(closes[0])
        for close in closes[1:]:
            ema_value = (float(close) * multiplier) + (ema_value * (1.0 - multiplier))
        return round(ema_value, self._ROUNDING)

    def _resolve_current_price(self, candles: list, intraday_data: dict, closes: list[float]) -> float | None:
        candidates = [
            self._safe_float((intraday_data or {}).get("last_price") if isinstance(intraday_data, dict) else None),
            self._safe_float((intraday_data or {}).get("price") if isinstance(intraday_data, dict) else None),
            closes[-1] if closes else None,
            self._safe_float(self._read(candles[-1], "close")) if candles else None,
        ]
        for candidate in candidates:
            if candidate is not None:
                return candidate
        return None

    def _resolve_prior_close(self, candles: list, intraday_data: dict) -> float | None:
        if isinstance(intraday_data, dict):
            for key in ("prior_close", "previous_close", "prev_close"):
                candidate = self._safe_float(intraday_data.get(key))
                if candidate is not None:
                    return round(candidate, self._ROUNDING)
        if len(candles) >= 2:
            candidate = self._safe_float(self._read(candles[-2], "close"))
            if candidate is not None:
                return round(candidate, self._ROUNDING)
        return None

    def _derive_active_breakout_range(self, core_levels: dict[str, float | None]) -> dict[str, float | None]:
        lower = core_levels.get("premarket_high")
        upper = core_levels.get("hod")
        if lower is None and upper is None:
            return {"lower": None, "upper": None, "width": None, "status": "MISSING"}
        if lower is None:
            lower = upper
        if upper is None:
            upper = lower
        if lower is not None and upper is not None and upper < lower:
            lower, upper = upper, lower
        width = None if lower is None or upper is None else round(max(upper - lower, 0.0), self._ROUNDING)
        status = "DERIVED" if width is not None else "PARTIAL"
        return {"lower": lower, "upper": upper, "width": width, "status": status}

    def _build_provenance(
        self,
        *,
        core_levels: dict[str, float | None],
        intraday_candles: list,
        premarket_candles: list,
        intraday_data: dict,
        candles: list,
        active_breakout_range: dict[str, float | None],
        current_price: float | None,
    ) -> dict[str, str]:
        provenance: dict[str, str] = {}
        provenance["premarket_high"] = "premarket_candles" if premarket_candles and core_levels.get("premarket_high") is not None else "missing"
        provenance["premarket_low"] = "premarket_candles" if premarket_candles and core_levels.get("premarket_low") is not None else "missing"
        provenance["hod"] = "intraday_candles" if intraday_candles and core_levels.get("hod") is not None else "missing"
        provenance["lod"] = "intraday_candles" if intraday_candles and core_levels.get("lod") is not None else "missing"
        provenance["prior_close"] = "intraday_data" if isinstance(intraday_data, dict) and any(k in intraday_data for k in ("prior_close", "previous_close", "prev_close")) else ("candles[-2].close" if len(candles) >= 2 and core_levels.get("prior_close") is not None else "missing")
        provenance["vwap"] = "intraday_candles" if core_levels.get("vwap") is not None else "missing_or_zero_volume"
        provenance["ema_9"] = "intraday_close_series" if core_levels.get("ema_9") is not None else "missing_close_series"
        provenance["ema_20"] = "intraday_close_series" if core_levels.get("ema_20") is not None else "missing_close_series"
        provenance["whole_dollar_levels"] = "derived_from_current_price" if current_price is not None else "missing_current_price"
        provenance["half_dollar_levels"] = "derived_from_current_price" if current_price is not None else "missing_current_price"
        provenance["active_breakout_range"] = f"derived:{active_breakout_range.get('status', 'UNKNOWN').lower()}"
        return provenance

    def _whole_levels(self, current_price: float | None, radius: int = 5) -> list[float]:
        if current_price is None:
            return []
        center = int(round(current_price))
        start = max(center - radius, 0)
        end = center + radius
        return [float(v) for v in range(start, end + 1)]

    def _half_levels(self, current_price: float | None, radius: int = 5) -> list[float]:
        if current_price is None:
            return []
        center = int(round(current_price))
        start = max(center - radius, 0)
        end = center + radius
        return [round(value + 0.5, self._ROUNDING) for value in range(start, end)]

    def _pivot_levels(self, candles: list, use_high: bool, neighbors: int = 2) -> list[float]:
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
        return sorted(set(pivots))

    def _computed_at(self, *series: list) -> str:
        timestamps: list[datetime] = []
        for candles in series:
            for candle in candles:
                timestamp = self._read(candle, "timestamp")
                if isinstance(timestamp, datetime):
                    if timestamp.tzinfo is None:
                        timestamps.append(timestamp.replace(tzinfo=timezone.utc))
                    else:
                        timestamps.append(timestamp.astimezone(timezone.utc))
        if timestamps:
            return max(timestamps).isoformat()
        return datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
