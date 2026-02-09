from __future__ import annotations

from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from config.config_resolver import set_config_overrides
from config.runtime_config import get_learning_enabled
from learning.models import LearningDataset, LearningTrade
from learning.policy_proposal import propose_policy
from learning.storage import compute_hash
from strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def test_learning_disabled_in_live_mode_by_default():
    set_config_overrides(
        {
            "RUN_MODE": "LIVE",
            "RUN_MODE_EFFECTIVE": "LIVE",
            "LEARNING_ENABLED": True,
            "LEARNING_LIVE_ENABLED": False,
        }
    )
    try:
        assert get_learning_enabled() is False
    finally:
        set_config_overrides(None)


def test_learning_proposal_determinism():
    baseline = RossMomentumPolicy()
    trades = [
        LearningTrade(
            strategy_name="ROSS_MOMENTUM",
            symbol="AAA",
            entry_time=None,
            exit_time=None,
            entry_price=10.0,
            exit_price=12.0,
            pnl=1.0,
            pnl_pct=10.0,
            gate_context={
                "last_price": 8.0,
                "gap_pct": 14.0,
                "rvol": 6.0,
                "float_millions": 18.0,
                "volume": 1200000,
                "premarket_volume": 200000,
                "spread_pct": 0.02,
                "dollar_volume": 14000000.0,
            },
        ),
        LearningTrade(
            strategy_name="ROSS_MOMENTUM",
            symbol="BBB",
            entry_time=None,
            exit_time=None,
            entry_price=11.0,
            exit_price=13.0,
            pnl=2.0,
            pnl_pct=15.0,
            gate_context={
                "last_price": 12.0,
                "gap_pct": 18.0,
                "rvol": 7.0,
                "float_millions": 16.0,
                "volume": 1400000,
                "premarket_volume": 210000,
                "spread_pct": 0.03,
                "dollar_volume": 16000000.0,
            },
        ),
        LearningTrade(
            strategy_name="ROSS_MOMENTUM",
            symbol="CCC",
            entry_time=None,
            exit_time=None,
            entry_price=9.0,
            exit_price=10.0,
            pnl=1.5,
            pnl_pct=12.0,
            gate_context={
                "last_price": 9.0,
                "gap_pct": 16.0,
                "rvol": 5.5,
                "float_millions": 19.0,
                "volume": 1300000,
                "premarket_volume": 190000,
                "spread_pct": 0.025,
                "dollar_volume": 15000000.0,
            },
        ),
    ]
    dataset_a = LearningDataset(trades=list(trades))
    dataset_b = LearningDataset(trades=list(reversed(trades)))
    proposal_a, diff_a, rationale_a = propose_policy(
        baseline=baseline, dataset=dataset_a, min_trades=3
    )
    proposal_b, diff_b, rationale_b = propose_policy(
        baseline=baseline, dataset=dataset_b, min_trades=3
    )
    assert proposal_a == proposal_b
    assert diff_a == diff_b
    assert rationale_a == rationale_b


def test_learning_storage_hash_stability():
    payload_a = {"b": 2, "a": {"y": 1, "x": 2}}
    payload_b = {"a": {"x": 2, "y": 1}, "b": 2}
    assert compute_hash(payload_a) == compute_hash(payload_b)
