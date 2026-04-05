from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.time.market_regimes import resolve_market_regime_context, resolve_regime_policy


ET = ZoneInfo("America/New_York")


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 4, 3, hour, minute, tzinfo=ET)


def test_market_regime_default_mapping() -> None:
    assert resolve_market_regime_context(_dt(4, 30)).regime == "NORMAL"
    assert resolve_market_regime_context(_dt(9, 45)).regime == "FAST"
    assert resolve_market_regime_context(_dt(10, 45)).regime == "NORMAL"
    assert resolve_market_regime_context(_dt(12, 30)).regime == "SLOW"
    assert resolve_market_regime_context(_dt(15, 45)).regime == "NORMAL"
    assert resolve_market_regime_context(_dt(20, 30)).regime == "DEAD"


def test_market_regime_policy_shapes() -> None:
    dead = resolve_regime_policy("DEAD")
    assert dead.execution_speed == "RESTRICTED"
    assert dead.rvol_strictness == "VERY_HIGH_OR_BLOCK"

    fast = resolve_regime_policy("FAST")
    assert fast.execution_speed == "FAST"
    assert fast.pct_change_strictness == "LOW"
