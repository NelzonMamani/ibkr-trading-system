"""Learning-only telemetry for statistical intraday momentum."""

from __future__ import annotations

from typing import Mapping

from src.strategy_portfolio.contracts import AllowState

from .signal_engine.features import FeatureVector
from .signal_engine.regime import RegimeState
from .signal_engine.scoring import ScoreState
from .strategy_policy import StatisticalIntradayMomentumPolicy


def build_telemetry(
    policy: StatisticalIntradayMomentumPolicy,
    context: Mapping[str, object],
    features: FeatureVector,
    score: ScoreState,
    regime: RegimeState | None,
    reasons: list[str] | None = None,
    allow_state: AllowState | None = None,
) -> dict[str, object]:
    return {
        "strategy_id": policy.name,
        "strategy_version": policy.version,
        "symbol": context.get("symbol"),
        "timestamp": context.get("now_ts"),
        "allow_state": (allow_state or AllowState.DISALLOW).value,
        "reasons": reasons or [],
        "features": {
            "return_1m": features.return_1m,
            "return_5m": features.return_5m,
            "return_15m": features.return_15m,
            "volatility": features.volatility,
            "volume_accel": features.volume_accel,
            "persistence": features.persistence,
            "time_of_day_bucket": features.time_of_day_bucket,
        },
        "score": {
            "value": score.score,
            "entry_threshold": score.entry_threshold,
            "hold_threshold": score.hold_threshold,
            "exit_threshold": score.exit_threshold,
        },
        "regime": {
            "tradeable": regime.is_tradeable if regime else False,
            "volatility_ok": regime.volatility_ok if regime else False,
            "liquidity_ok": regime.liquidity_ok if regime else False,
            "time_window_ok": regime.time_window_ok if regime else False,
            "spread_ok": regime.spread_ok if regime else False,
        },
    }
