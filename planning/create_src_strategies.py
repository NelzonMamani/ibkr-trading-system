# create_src_strategies.py
from pathlib import Path

BASE = Path("src") / "strategies"

# Clean strategy names — NO catalogue prefixes
STRATEGIES = [
    "ross_momentum",
    "statistical_intraday_momentum",
    "mean_reversion",
    "long_horizon_value",
    "opening_drive",
    "vwap_reclaim",
    "power_hour",
    "volatility_expansion",
    "range_bound_fade",
    "support_resistance_channel",
    "event_earnings_reaction",
    "event_news_shock_continuation",
    "volatility_contraction_breakout",
    "volatility_carry_risk_premium",
    "pairs_divergence_reversion",
    "cross_sectional_relative_strength_rotation",
    "time_based_seasonality",
    "trend_following_classic",
    "long_horizon_quality_compounder",
    "regime_adaptive_meta_allocator",
]

POLICY_TEMPLATE = """\
\"\"\"{module_path}

Strategy Policy (TEMPLATE)

IMPORTANT
- This is the sovereign strategy policy.
- The Trading OS must NEVER violate these rules.
- Defaults are LOCKED unless explicitly changed via optimisation epoch.

This file is intentionally verbose and heavily commented.
\"\"\"

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class StrategyPolicy:
    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    name: str = "{strategy_name}"
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
"""

ALGO_TEMPLATE = """\
# {strategy_name} — Strategy Algorithm (DRAFT)

This document defines the FULL end-to-end algorithm.

This is NOT code.
This is the authoritative human-readable trading logic.

----------------------------------------------------------------------
1. EDGE DEFINITION
----------------------------------------------------------------------
What inefficiency does this strategy exploit?

----------------------------------------------------------------------
2. UNIVERSE & ELIGIBILITY
----------------------------------------------------------------------
- Symbol source
- Liquidity requirements
- Price range
- Exclusions

----------------------------------------------------------------------
3. DATA REQUIREMENTS
----------------------------------------------------------------------
- Timeframes
- Indicators
- Levels / zones
- Market context

----------------------------------------------------------------------
4. SETUP DETECTION (E18)
----------------------------------------------------------------------
Which setup families are allowed and why.

----------------------------------------------------------------------
5. ENTRY LOGIC
----------------------------------------------------------------------
Conditions → Trigger → Confirmations → Trade Intent

----------------------------------------------------------------------
6. POSITION MANAGEMENT
----------------------------------------------------------------------
- Adds
- Partial exits
- Trailing logic
- Time stops

----------------------------------------------------------------------
7. EXIT & INVALIDATION
----------------------------------------------------------------------
- Profit targets
- Structural invalidation
- Hard stops
- Emergency exits

----------------------------------------------------------------------
8. RISK CONTROLS
----------------------------------------------------------------------
- Per-trade risk
- Per-day limits
- Kill-switch conditions

----------------------------------------------------------------------
9. RECOVERY & RESILIENCE
----------------------------------------------------------------------
- Network disconnect
- Order reconciliation
- State rebuild

----------------------------------------------------------------------
10. MODE SEMANTICS
----------------------------------------------------------------------
SIM | PAPER | READ_ONLY | LIVE

Status: DRAFT — to be completed during strategy planning
"""


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)

    for slug in STRATEGIES:
        strategy_path = BASE / slug

        # Do not overwrite existing strategies
        if strategy_path.exists():
            continue

        strategy_path.mkdir(parents=True, exist_ok=True)
        (strategy_path / "__init__.py").write_text("", encoding="utf-8")

        module_path = f"src/strategies/{slug}/strategy_policy.py"

        (strategy_path / "strategy_policy.py").write_text(
            POLICY_TEMPLATE.format(
                module_path=module_path,
                strategy_name=slug,
            ),
            encoding="utf-8",
        )

        (strategy_path / "ALGORITHM.md").write_text(
            ALGO_TEMPLATE.format(strategy_name=slug),
            encoding="utf-8",
        )

    print(f"Strategy folders created (existing ones untouched): {BASE}")


if __name__ == "__main__":
    main()
