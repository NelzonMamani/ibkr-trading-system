"""Ross RVOL policy section."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.strategies.ross_momentum.strategy_policy import StockSelectionSpec


class RvolQuality(str, Enum):
    MISSING = "MISSING"
    BELOW_DISCOVERY = "BELOW_DISCOVERY"
    WATCHLIST_ACCEPTABLE = "WATCHLIST_ACCEPTABLE"
    SESSION_FOCUS_ACCEPTABLE = "SESSION_FOCUS_ACCEPTABLE"
    LIVE_QUALITY = "LIVE_QUALITY"


@dataclass(frozen=True)
class RvolDecision:
    quality: RvolQuality
    satisfied: bool
    live_quality: bool
    threshold: float
    live_quality_threshold: float
    reason: str


@dataclass(frozen=True)
class RvolPolicy:
    minimum: float
    watchlist_min: float
    focus_min: float
    session_watchlist_min: dict[str, float]
    session_focus_min: dict[str, float]
    live_quality_min: float = 5.0

    @classmethod
    def from_stock_selection(cls, stock_selection: StockSelectionSpec) -> "RvolPolicy":
        return cls(
            minimum=float(stock_selection.rvol_min),
            watchlist_min=float(stock_selection.watchlist_rvol_min),
            focus_min=float(stock_selection.focus_rvol_min),
            session_watchlist_min=dict(stock_selection.session_watchlist_rvol_min),
            session_focus_min=dict(stock_selection.session_focus_rvol_min),
        )

    def watchlist_threshold_for(self, session: str) -> float:
        return self._threshold_for(session, self.session_watchlist_min, self.watchlist_min)

    def focus_threshold_for(self, session: str) -> float:
        return self._threshold_for(session, self.session_focus_min, self.focus_min)

    def assess(self, rvol: float | None, session: str, *, focus: bool = False) -> RvolDecision:
        threshold = self.focus_threshold_for(session) if focus else self.watchlist_threshold_for(session)
        if rvol is None:
            return RvolDecision(
                quality=RvolQuality.MISSING,
                satisfied=False,
                live_quality=False,
                threshold=threshold,
                live_quality_threshold=self.live_quality_min,
                reason="missing_rvol",
            )
        value = float(rvol)
        if value < threshold:
            return RvolDecision(
                quality=RvolQuality.BELOW_DISCOVERY,
                satisfied=False,
                live_quality=False,
                threshold=threshold,
                live_quality_threshold=self.live_quality_min,
                reason="below_rvol_threshold",
            )
        if value >= self.live_quality_min:
            return RvolDecision(
                quality=RvolQuality.LIVE_QUALITY,
                satisfied=True,
                live_quality=True,
                threshold=threshold,
                live_quality_threshold=self.live_quality_min,
                reason="rvol_live_quality",
            )
        quality = RvolQuality.SESSION_FOCUS_ACCEPTABLE if focus else RvolQuality.WATCHLIST_ACCEPTABLE
        return RvolDecision(
            quality=quality,
            satisfied=True,
            live_quality=False,
            threshold=threshold,
            live_quality_threshold=self.live_quality_min,
            reason="rvol_session_threshold",
        )

    def _threshold_for(self, session: str, mapping: dict[str, float], default: float) -> float:
        normalized = _normalize_session(session)
        return float(mapping.get(normalized, mapping.get(_canonical_session(normalized), default)))


def _canonical_session(normalized: str) -> str:
    if normalized.startswith("RTH"):
        return "RTH_OPEN"
    return normalized


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
