"""src/strategies/pairs_divergence_reversion/strategy_policy.py

Strategy Policy (TEMPLATE)

IMPORTANT
- This is the sovereign strategy policy.
- The Trading OS must NEVER violate these rules.
- Defaults are LOCKED unless explicitly changed via optimisation epoch.

This file is intentionally verbose and heavily commented.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class StrategyPolicy:
    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    name: str = "pairs_divergence_reversion"
    version: str = "v0_draft"

    # ------------------------------------------------------------------
    # Universe / symbol selection
    # ------------------------------------------------------------------
    universe_source: str = "SCANNER"  # SCANNER | CONFIG_SYMBOLS
    watchlist_limit_k: int = 15
    focus_limit_m: int = 5

    # ------------------------------------------------------------------
    # Allowed foundation components (E18)
    # ------------------------------------------------------------------
    allowed_setup_families: Sequence[str] = ()
    allowed_entry_triggers: Sequence[str] = ()
    required_conditions: Sequence[str] = ()
    required_confirmations: Sequence[str] = ()

    # ------------------------------------------------------------------
    # Risk & permissions
    # ------------------------------------------------------------------
    max_consecutive_losses: int = 3
    max_daily_loss: Optional[float] = None
    max_open_positions: int = 1

    # ------------------------------------------------------------------
    # Execution preferences (non-binding hints)
    # ------------------------------------------------------------------
    order_type_primary: str = "LIMIT"
    allow_market_orders: bool = False


POLICY = StrategyPolicy()
