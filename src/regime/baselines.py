from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Dict, Iterable, List

from src.regime.contracts import FeatureVector


@dataclass(frozen=True)
class BaselineStats:
    count: int
    rolling_mean: float | None
    rolling_std: float | None
    ewma_mean: float | None
    q25: float | None
    q50: float | None
    q75: float | None

    def to_payload(self) -> Dict[str, float | None]:
        return {
            "count": self.count,
            "rolling_mean": self.rolling_mean,
            "rolling_std": self.rolling_std,
            "ewma_mean": self.ewma_mean,
            "q25": self.q25,
            "q50": self.q50,
            "q75": self.q75,
        }


class BaselineStore:
    def __init__(
        self,
        window: int,
        alpha: float,
        *,
        persist_path: str | None = "data/regime_baselines.json",
        persist_enabled: bool = True,
    ) -> None:
        self.window = int(window)
        self.alpha = float(alpha)
        self.persist_path = persist_path
        self.persist_enabled = bool(persist_enabled)
        self._windows: Dict[str, List[float]] = {}
        self._ewma: Dict[str, float] = {}
        if self.persist_enabled and self.persist_path:
            self._load()

    def update(self, features: FeatureVector) -> None:
        updates = _extract_numeric_features(features)
        for name, value in updates.items():
            if value is None:
                continue
            window = self._windows.setdefault(name, [])
            window.append(float(value))
            if len(window) > self.window:
                window.pop(0)
            if name not in self._ewma:
                self._ewma[name] = float(value)
            else:
                self._ewma[name] = (self.alpha * float(value)) + (
                    (1.0 - self.alpha) * self._ewma[name]
                )
        if self.persist_enabled and self.persist_path:
            self._persist()

    def snapshot(self) -> Dict[str, BaselineStats]:
        snapshot: Dict[str, BaselineStats] = {}
        for name, window in self._windows.items():
            if not window:
                snapshot[name] = BaselineStats(0, None, None, self._ewma.get(name), None, None, None)
                continue
            mean = sum(window) / len(window)
            variance = sum((value - mean) ** 2 for value in window) / len(window)
            std = variance**0.5 if variance >= 0 else 0.0
            sorted_window = sorted(window)
            snapshot[name] = BaselineStats(
                count=len(window),
                rolling_mean=_round(mean),
                rolling_std=_round(std),
                ewma_mean=_round(self._ewma.get(name)),
                q25=_round(_quantile(sorted_window, 0.25)),
                q50=_round(_quantile(sorted_window, 0.50)),
                q75=_round(_quantile(sorted_window, 0.75)),
            )
        return snapshot

    def snapshot_payload(self) -> Dict[str, Dict[str, float | None]]:
        return {name: stats.to_payload() for name, stats in self.snapshot().items()}

    def _persist(self) -> None:
        if not self.persist_path:
            return
        payload = {
            "version": 1,
            "window": self.window,
            "alpha": self.alpha,
            "windows": self._windows,
            "ewma": self._ewma,
        }
        os.makedirs(os.path.dirname(self.persist_path) or ".", exist_ok=True)
        with open(self.persist_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2)

    def _load(self) -> None:
        if not self.persist_path or not os.path.exists(self.persist_path):
            return
        with open(self.persist_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.window = int(payload.get("window", self.window))
        self.alpha = float(payload.get("alpha", self.alpha))
        self._windows = {
            key: [float(value) for value in values]
            for key, values in payload.get("windows", {}).items()
        }
        self._ewma = {key: float(value) for key, value in payload.get("ewma", {}).items()}


def _extract_numeric_features(features: FeatureVector) -> Dict[str, float | None]:
    return {
        "median_spread_bps": features.median_spread_bps,
        "pct_missing_prices": features.pct_missing_prices,
        "pct_missing_volume": features.pct_missing_volume,
        "median_rvol": features.median_rvol,
        "median_gap_pct": features.median_gap_pct,
        "top1_momentum_move_pct": features.top1_momentum_move_pct,
        "news_density_proxy": features.news_density_proxy,
        "return_volatility_proxy": features.return_volatility_proxy,
        "range_expansion_proxy": features.range_expansion_proxy,
        "orderbook_quality_proxy": features.orderbook_quality_proxy,
    }


def _quantile(sorted_values: Iterable[float], q: float) -> float | None:
    values = list(sorted_values)
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return float(values[lower] * (1 - weight) + values[upper] * weight)


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)
