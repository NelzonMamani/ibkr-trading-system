# src/config/risk_profiles.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict


@dataclass(frozen=True)
class RiskProfile:
    """
    RiskProfile is CONFIGURATION ONLY.

    It must not contain strategy logic.
    It only constrains/clamps an OrderIntent produced by a strategy.

    Any field set to None means "no constraint here; defer to strategy/default system risk".
    """

    name: str

    # Position sizing clamps
    max_shares: Optional[int] = None
    max_position_value_pct: Optional[float] = None   # % of equity (e.g., 0.5 means 0.5%)
    max_risk_per_trade_pct: Optional[float] = None   # % of equity at stop distance

    # Scaling / adds
    allow_scaling: bool = True
    max_adds: Optional[int] = None                   # None means no explicit cap beyond system defaults

    # Daily constraints
    daily_max_loss_pct: Optional[float] = None       # % of equity
    daily_max_trades: Optional[int] = None

    # Safety enforcement toggles
    enforce_hard_stops: bool = True                  # disallow intents without stop
    enforce_max_spread: Optional[float] = None       # optional spread cap (e.g. 0.05 = $0.05)


# ---- Authoritative profiles ----

NORMAL = RiskProfile(
    name="NORMAL",
    # Let strategy/system sizing determine most sizing.
    max_shares=None,
    max_position_value_pct=5.0,       # example: max 5% of equity per position
    max_risk_per_trade_pct=1.0,       # example: risk 1% of equity per trade (at stop)
    allow_scaling=True,
    max_adds=2,
    daily_max_loss_pct=3.0,           # example: stop trading after -3% day
    daily_max_trades=None,
    enforce_hard_stops=True,
    enforce_max_spread=None,
)

MICRO = RiskProfile(
    name="MICRO",
    # “Same logic, tiny size”
    max_shares=1,
    max_position_value_pct=0.5,       # tighter cap (optional)
    max_risk_per_trade_pct=0.1,       # tiny risk (optional)
    allow_scaling=False,
    max_adds=0,
    daily_max_loss_pct=0.5,
    daily_max_trades=5,
    enforce_hard_stops=True,
    enforce_max_spread=None,
)

SMALL = RiskProfile(
    name="SMALL",
    # A practical intermediate profile
    max_shares=None,
    max_position_value_pct=1.5,
    max_risk_per_trade_pct=0.25,
    allow_scaling=True,
    max_adds=1,
    daily_max_loss_pct=1.0,
    daily_max_trades=8,
    enforce_hard_stops=True,
    enforce_max_spread=None,
)


RISK_PROFILES: Dict[str, RiskProfile] = {
    "NORMAL": NORMAL,
    "MICRO": MICRO,
    "SMALL": SMALL,
}
