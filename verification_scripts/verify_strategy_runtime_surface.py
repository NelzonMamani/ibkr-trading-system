from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config.config_resolver import set_config_overrides
from src.strategies.strategy_registry import build_default_registry
from src.strategy.strategy_runner import StrategyRunner


def main() -> None:
    registry = build_default_registry()
    registry_ids = sorted(meta.strategy_id for meta in registry.list_metadata())
    assert registry_ids == ["mean_reversion", "ross_momentum"]

    try:
        set_config_overrides(
            {
                "RUN_MODE": "LIVE",
                "SELECTED_STRATEGY": "",
                "ROSS_MOMENTUM_STRATEGY_ENABLED": False,
                "STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED": False,
                "MEAN_REVERSION_STRATEGY_ENABLED": False,
                "LONG_HORIZON_VALUE_STRATEGY_ENABLED": False,
                "ENABLED_STRATEGIES": {
                    "GapAndGoStrategy": False,
                    "MomentumContinuationStrategy": False,
                },
            }
        )
        runner = StrategyRunner()
        active = [strategy.name for strategy in runner.strategies]
        assert "GapAndGoStrategy" not in active
        assert "MomentumContinuationStrategy" not in active
        print(f"strategy_runner_active={active}")
    finally:
        set_config_overrides(None)

    print(f"strategy_registry_ids={registry_ids}")
    print("verify_strategy_runtime_surface: PASS")


if __name__ == "__main__":
    main()
