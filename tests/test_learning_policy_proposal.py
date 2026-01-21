from __future__ import annotations

from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root))
sys.path.append(str(repo_root / "src"))

from learning.models import LearningDataset, LearningTrade
from dataclasses import asdict

from learning.policy_proposal import propose_policy, validate_policy_schema
from strategies.ross_momentum.strategy_policy import RossMomentumPolicy


def test_policy_proposal_requires_min_trades():
    baseline = RossMomentumPolicy()
    dataset = LearningDataset(trades=[])
    proposal, diff, rationale = propose_policy(
        baseline=baseline, dataset=dataset, min_trades=3
    )
    assert proposal is None
    assert diff == {}
    assert rationale == {}


def test_policy_proposal_schema_matches():
    baseline = RossMomentumPolicy()
    trades = [
        LearningTrade(
            strategy_name="ROSS_MOMENTUM",
            symbol="AAPL",
            entry_time=None,
            exit_time=None,
            entry_price=10.0,
            exit_price=11.0,
            pnl=1.0,
            pnl_pct=10.0,
            gate_context={
                "last_price": 10.0,
                "gap_pct": 12.0,
                "rvol": 6.0,
                "float_millions": 15.0,
                "volume": 1200000,
                "premarket_volume": 200000,
                "spread_pct": 0.02,
                "dollar_volume": 12000000.0,
            },
        )
        for _ in range(5)
    ]
    dataset = LearningDataset(trades=trades)
    proposal, diff, _ = propose_policy(
        baseline=baseline, dataset=dataset, min_trades=5
    )
    assert proposal is not None
    assert validate_policy_schema(asdict(baseline), proposal)
    assert isinstance(diff, dict)
