from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketRegimeContext:
    regime: str
    asof_et: datetime
    source: str
    notes: str
    liquidity_profile: str
    volatility_profile: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["asof_et"] = self.asof_et.isoformat()
        return payload


@dataclass(frozen=True)
class MarketRegimePolicy:
    regime: str
    rvol_strictness: str
    pct_change_strictness: str
    spread_tolerance: str
    liquidity_requirement: str
    execution_speed: str
    notes: str

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_market_regime_context(now: datetime, *, source: str = "US_EQUITY_DEFAULT") -> MarketRegimeContext:
    now_et = now.astimezone(ET)
    t = now_et.timetz().replace(tzinfo=None)

    if _in_range(t, time(4, 0), time(9, 30)):
        regime = "NORMAL"
    elif _in_range(t, time(9, 30), time(10, 30)):
        regime = "FAST"
    elif _in_range(t, time(10, 30), time(11, 30)):
        regime = "NORMAL"
    elif _in_range(t, time(11, 30), time(15, 30)):
        regime = "SLOW"
    elif _in_range(t, time(15, 30), time(16, 0)):
        regime = "NORMAL"
    else:
        regime = "DEAD"

    return MarketRegimeContext(
        regime=regime,
        asof_et=now_et,
        source=source,
        notes=f"default_et_mapping::{regime}",
        liquidity_profile=("LOW" if regime in {"SLOW", "DEAD"} else "MEDIUM_TO_HIGH"),
        volatility_profile=("HIGH" if regime == "FAST" else "LOW" if regime == "DEAD" else "MEDIUM"),
    )


def resolve_regime_policy(regime: str) -> MarketRegimePolicy:
    value = str(regime or "NORMAL").upper()
    if value == "FAST":
        return MarketRegimePolicy(value, "LOW", "LOW", "MEDIUM", "MEDIUM", "FAST", "aggressive_validations")
    if value == "SLOW":
        return MarketRegimePolicy(value, "HIGH", "HIGH", "TIGHT", "HIGH", "SLOWER", "selective_structural_only")
    if value == "DEAD":
        return MarketRegimePolicy(value, "VERY_HIGH_OR_BLOCK", "VERY_HIGH_OR_BLOCK", "VERY_TIGHT", "VERY_HIGH", "RESTRICTED", "entries_expected_blocked_for_ross")
    return MarketRegimePolicy("NORMAL", "MEDIUM", "MEDIUM", "MEDIUM", "MEDIUM", "NORMAL", "baseline")


def _in_range(value: time, start: time, end: time) -> bool:
    return start <= value < end
