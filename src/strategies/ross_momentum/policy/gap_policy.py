"""Ross gap and percent-change policy section."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy, StockSelectionSpec


class GapQuality(str, Enum):
    MISSING = "MISSING"
    BELOW_DISCOVERY = "BELOW_DISCOVERY"
    DISCOVERY = "DISCOVERY"
    SESSION_ADAPTATION = "SESSION_ADAPTATION"
    LIVE_QUALITY = "LIVE_QUALITY"
    ABOVE_MAX = "ABOVE_MAX"


@dataclass(frozen=True)
class GapDecision:
    quality: GapQuality
    satisfied: bool
    live_quality: bool
    threshold: float
    live_quality_threshold: float
    reason: str


@dataclass(frozen=True)
class GapPolicy:
    min_pct: float
    premarket_min_pct: float
    max_pct: float | None
    discovery_min_pct: float = 5.0

    @classmethod
    def from_policy(cls, policy: RossMomentumPolicy) -> "GapPolicy":
        return cls.from_stock_selection(policy.stock_selection)

    @classmethod
    def from_stock_selection(cls, stock_selection: StockSelectionSpec) -> "GapPolicy":
        return cls(
            min_pct=float(stock_selection.gap_min_pct),
            premarket_min_pct=5.0,
            max_pct=stock_selection.gap_max_pct,
        )

    @property
    def live_quality_min_pct(self) -> float:
        return max(float(self.min_pct), 10.0)

    def discovery_threshold_for(self, session: str) -> float:
        normalized = _normalize_session(session)
        if normalized in {"PRE", "OVN", "AH"}:
            return float(self.premarket_min_pct)
        return float(self.discovery_min_pct)

    def focus_threshold_for(self, session: str) -> float:
        normalized = _normalize_session(session)
        if normalized in {"PRE", "OVN", "AH"}:
            return float(self.premarket_min_pct)
        return float(self.live_quality_min_pct)

    def assess(self, pct_change: float | None, session: str, *, focus: bool = False) -> GapDecision:
        threshold = self.focus_threshold_for(session) if focus else self.discovery_threshold_for(session)
        live_threshold = self.live_quality_min_pct
        if pct_change is None:
            return GapDecision(
                quality=GapQuality.MISSING,
                satisfied=False,
                live_quality=False,
                threshold=threshold,
                live_quality_threshold=live_threshold,
                reason="missing_pct_change",
            )
        value = float(pct_change)
        if self.max_pct is not None and value > float(self.max_pct):
            return GapDecision(
                quality=GapQuality.ABOVE_MAX,
                satisfied=False,
                live_quality=False,
                threshold=threshold,
                live_quality_threshold=live_threshold,
                reason="above_max_pct_change",
            )
        if value < threshold:
            return GapDecision(
                quality=GapQuality.BELOW_DISCOVERY,
                satisfied=False,
                live_quality=False,
                threshold=threshold,
                live_quality_threshold=live_threshold,
                reason="below_pct_change_threshold",
            )
        if value >= live_threshold:
            return GapDecision(
                quality=GapQuality.LIVE_QUALITY,
                satisfied=True,
                live_quality=True,
                threshold=threshold,
                live_quality_threshold=live_threshold,
                reason="pct_change_live_quality",
            )
        normalized = _normalize_session(session)
        quality = GapQuality.SESSION_ADAPTATION if normalized in {"PRE", "OVN", "AH"} else GapQuality.DISCOVERY
        return GapDecision(
            quality=quality,
            satisfied=True,
            live_quality=False,
            threshold=threshold,
            live_quality_threshold=live_threshold,
            reason="pct_change_session_adaptation" if quality == GapQuality.SESSION_ADAPTATION else "pct_change_discovery",
        )


def _normalize_session(session: str) -> str:
    normalized = str(session or "").strip().upper()
    aliases = {
        "PREMARKET": "PRE",
        "AFTER_HOURS": "AH",
        "REG": "RTH_OPEN",
        "REGULAR": "RTH_OPEN",
        "RTH": "RTH_OPEN",
        "MORNING": "RTH_OPEN",
        "OPENING": "RTH_OPEN",
        "MIDDAY": "RTH_MID",
        "AFTERNOON": "RTH_LATE",
        "POWER_HOUR": "RTH_LATE",
    }
    return aliases.get(normalized, normalized)
