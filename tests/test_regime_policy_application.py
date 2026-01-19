from __future__ import annotations

from dataclasses import dataclass

from src.config.config_resolver import set_config_overrides
from src.models.data_models import TradeIntent
from src.regime.contracts import FeatureVector, RegimeLabel, RegimeSnapshot
from src.regime.policy import RegimePolicy
from src.strategy.strategy_runner import StrategyRunner


@dataclass
class FakeStrategy:
    name: str

    def evaluate(self, pattern_results, signals=None):
        return [
            TradeIntent(
                symbol="AAPL",
                direction="LONG",
                strategy_name=self.name,
                confidence=1.0,
                rationale="test",
            )
        ]


def test_policy_weights_apply_to_intents():
    overrides = {
        "ADAPTIVE_REGIME_POLICY_ENABLED": True,
        "ADAPTIVE_REGIME_MIN_CONFIDENCE_TO_APPLY": 0.5,
        "ADAPTIVE_REGIME_STRATEGY_WEIGHTING_MODE": "WEIGHT",
        "ADAPTIVE_REGIME_ALLOWED_SESSIONS": ["REGULAR"],
        "ADAPTIVE_REGIME_ALLOWED_STRATEGY_WEIGHTS": [0.0, 0.4, 0.6],
    }
    set_config_overrides(overrides)
    try:
        snapshot = RegimeSnapshot(
            label=RegimeLabel.OPENING_MOMENTUM,
            confidence=0.8,
            session="REGULAR",
            features=FeatureVector(
                session="REGULAR",
                universe_count=1,
                median_spread_bps=10.0,
                pct_missing_prices=0.0,
                pct_missing_volume=0.0,
                median_rvol=1.0,
                median_gap_pct=1.0,
                top1_momentum_move_pct=1.0,
                news_density_proxy=0.0,
                liquidity_thin_flag=False,
            ),
        )
        decision = RegimePolicy().decide(snapshot, timestamp_utc=None)
        runner = StrategyRunner(
            strategies=[
                FakeStrategy(name="RossMomentumStrategyV1"),
                FakeStrategy(name="GapAndGoStrategy"),
            ]
        )
        intents = runner.generate_trade_intents([], policy_decision=decision, signals=None)
        confidences = sorted(intent.confidence for intent in intents)
        assert confidences == [0.4, 0.6]
    finally:
        set_config_overrides(None)
