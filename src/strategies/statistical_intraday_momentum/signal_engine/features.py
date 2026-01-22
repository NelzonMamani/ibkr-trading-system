"""Feature extraction helpers for statistical intraday momentum."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev
from typing import Iterable, Mapping


@dataclass(frozen=True)
class FeatureVector:
    """Lightweight container for deterministic features."""

    return_1m: float
    return_5m: float
    return_15m: float
    volatility: float
    volume_accel: float
    persistence: float
    time_of_day_bucket: str


def _extract_series(bars: Iterable[Mapping[str, float]], key: str) -> list[float]:
    return [float(bar[key]) for bar in bars if key in bar]


def compute_returns(prices: list[float]) -> list[float]:
    if len(prices) < 2:
        return []
    return [(prices[i] / prices[i - 1]) - 1.0 for i in range(1, len(prices))]


def compute_return(prices: list[float]) -> float:
    if len(prices) < 2:
        return 0.0
    return (prices[-1] / prices[0]) - 1.0


def realized_volatility(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    return pstdev(returns)


def volume_acceleration(bars_1m: list[Mapping[str, float]], window: int = 5) -> float:
    volumes = _extract_series(bars_1m, "volume")
    if len(volumes) < window * 2:
        return 0.0
    recent = sum(volumes[-window:])
    prior = sum(volumes[-window * 2 : -window])
    if prior <= 0:
        return 0.0
    return (recent / prior) - 1.0


def persistence(returns: list[float], window: int = 10) -> float:
    if len(returns) < window:
        return 0.0
    recent = returns[-window:]
    positives = sum(1 for value in recent if value > 0)
    return positives / window


def build_feature_vector(
    bars_1m: list[Mapping[str, float]],
    bars_5m: list[Mapping[str, float]],
    time_of_day_bucket: str,
) -> FeatureVector:
    closes_1m = _extract_series(bars_1m, "close")
    closes_5m = _extract_series(bars_5m, "close")

    return_1m = compute_return(closes_1m[-2:])
    return_5m = compute_return(closes_1m[-6:])
    return_15m = compute_return(closes_1m[-16:])

    returns_1m = compute_returns(closes_1m)
    vol = realized_volatility(returns_1m[-15:])

    volume_accel = volume_acceleration(bars_1m)
    persistence_score = persistence(returns_1m, window=10)

    return FeatureVector(
        return_1m=return_1m,
        return_5m=return_5m,
        return_15m=return_15m,
        volatility=vol,
        volume_accel=volume_accel,
        persistence=persistence_score,
        time_of_day_bucket=time_of_day_bucket,
    )
