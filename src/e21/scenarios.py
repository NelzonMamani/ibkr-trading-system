"""Scenario library for E21 trading-ready verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.foundation_detectors import SetupContext


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    description: str
    context: SetupContext
    validations: List[str]


def _make_candle(open_price: float, close: float, high: float, low: float, volume: float) -> Candle:
    return Candle(
        open=open_price,
        close=close,
        high=high,
        low=low,
        volume=volume,
    )


def _steady_uptrend(start: float, steps: Iterable[float]) -> List[Candle]:
    candles: List[Candle] = []
    price = start
    for step in steps:
        open_price = price
        close = price + step
        high = max(open_price, close) + 0.2
        low = min(open_price, close) - 0.2
        candles.append(_make_candle(open_price, close, high, low, volume=12000))
        price = close
    return candles


def _steady_downtrend(start: float, steps: Iterable[float]) -> List[Candle]:
    candles: List[Candle] = []
    price = start
    for step in steps:
        open_price = price
        close = price - step
        high = max(open_price, close) + 0.2
        low = min(open_price, close) - 0.2
        candles.append(_make_candle(open_price, close, high, low, volume=12000))
        price = close
    return candles


def _range_bound(start: float, deltas: Iterable[float]) -> List[Candle]:
    candles: List[Candle] = []
    price = start
    for delta in deltas:
        open_price = price
        close = price + delta
        high = max(open_price, close) + 0.15
        low = min(open_price, close) - 0.15
        candles.append(_make_candle(open_price, close, high, low, volume=9000))
        price = close
    return candles


def _base_levels(prior_close: float) -> dict[str, float]:
    return {
        "LVL_PRIOR_DAY_CLOSE": prior_close,
        "LVL_KEY_LEVEL": prior_close + 1.0,
        "LVL_HIGH_OF_DAY": prior_close + 2.5,
    }


def _base_zones(prior_close: float) -> dict[str, tuple[float, float]]:
    return {
        "ZONE_DEMAND": (prior_close + 0.5, prior_close - 0.5),
        "ZONE_SUPPLY": (prior_close + 2.0, prior_close + 1.3),
    }


def _gap_and_go_basic() -> ScenarioDefinition:
    prior_close = 10.0
    candles = _steady_uptrend(11.0, [0.4, 0.5, 0.6, 0.4])
    context = SetupContext(
        candles=candles,
        levels=_base_levels(prior_close),
        zones=_base_zones(prior_close),
        indicators={"opening_range_high": 12.2, "opening_range_low": 10.8},
        flags={"gap_and_go": True},
    )
    return ScenarioDefinition(
        scenario_id="SCN_GAP_AND_GO_BASIC",
        description="Gap up with bullish continuation and opening range break.",
        context=context,
        validations=["detect_setup_family", "level_interaction", "opening_range"],
    )


def _vwap_reclaim_basic() -> ScenarioDefinition:
    prior_close = 20.0
    candles = _steady_uptrend(19.4, [0.2, 0.25, 0.3, 0.35])
    context = SetupContext(
        candles=candles,
        levels=_base_levels(prior_close),
        zones=_base_zones(prior_close),
        indicators={"vwap": 19.8, "avg_range": 0.6},
        flags={"vwap_reclaim": True},
    )
    return ScenarioDefinition(
        scenario_id="SCN_VWAP_RECLAIM_BASIC",
        description="Price reclaims VWAP with steady bid.",
        context=context,
        validations=["detect_setup_family", "vwap_structure"],
    )


def _bull_flag_compression() -> ScenarioDefinition:
    prior_close = 15.0
    candles = _range_bound(15.5, [0.2, -0.1, 0.05, -0.03, 0.02])
    context = SetupContext(
        candles=candles,
        levels=_base_levels(prior_close),
        zones=_base_zones(prior_close),
        indicators={"avg_range": 0.4},
        flags={"bull_flag": True, "compression": True},
    )
    return ScenarioDefinition(
        scenario_id="SCN_BULL_FLAG_COMPRESSION",
        description="Bull flag with compressing ranges.",
        context=context,
        validations=["compression_structure", "detect_setup_family"],
    )


def _head_and_shoulders() -> ScenarioDefinition:
    prior_close = 30.0
    candles = [
        _make_candle(30.2, 30.6, 30.9, 30.1, 10000),
        _make_candle(30.6, 30.4, 30.7, 30.2, 9800),
        _make_candle(30.4, 31.1, 31.3, 30.3, 12000),
        _make_candle(31.1, 30.5, 31.15, 30.4, 11000),
        _make_candle(30.5, 30.7, 30.8, 30.2, 10500),
    ]
    context = SetupContext(
        candles=candles,
        levels=_base_levels(prior_close),
        zones=_base_zones(prior_close),
        indicators={"avg_range": 0.8},
        flags={"head_and_shoulders": True},
    )
    return ScenarioDefinition(
        scenario_id="SCN_HEAD_AND_SHOULDERS_BASIC",
        description="Head and shoulders baseline swing structure.",
        context=context,
        validations=["detect_setup_family", "range_structure"],
    )


def _range_break_and_fail() -> ScenarioDefinition:
    prior_close = 12.0
    candles = _range_bound(12.1, [0.1, -0.08, 0.12, -0.15, 0.18])
    context = SetupContext(
        candles=candles,
        levels=_base_levels(prior_close),
        zones=_base_zones(prior_close),
        indicators={"avg_range": 0.35},
        flags={"range_failure": True},
    )
    return ScenarioDefinition(
        scenario_id="SCN_RANGE_BREAK_AND_FAIL",
        description="Range break and failure back into the band.",
        context=context,
        validations=["range_structure", "detect_setup_family"],
    )


def _liquidity_sweep_reclaim() -> ScenarioDefinition:
    prior_close = 18.0
    candles = _steady_downtrend(18.1, [0.2, 0.25, 0.1, 0.05])
    context = SetupContext(
        candles=candles,
        levels=_base_levels(prior_close),
        zones=_base_zones(prior_close),
        indicators={"avg_range": 0.5},
        flags={"liquidity_sweep": True, "vwap_reclaim": True},
    )
    return ScenarioDefinition(
        scenario_id="SCN_LIQUIDITY_SWEEP_RECLAIM",
        description="Sweep and reclaim near demand zone.",
        context=context,
        validations=["detect_setup_family", "zone_interaction"],
    )


def _no_trade_context_veto() -> ScenarioDefinition:
    prior_close = 25.0
    candles = _steady_uptrend(25.2, [0.1, 0.1, 0.08])
    context = SetupContext(
        candles=candles,
        levels=_base_levels(prior_close),
        zones=_base_zones(prior_close),
        indicators={"avg_range": 0.3},
        flags={"no_trade": True},
    )
    return ScenarioDefinition(
        scenario_id="SCN_NO_TRADE_CONTEXT_VETO",
        description="No-trade context veto at portfolio normalisation.",
        context=context,
        validations=["no_trade_veto"],
    )


def _portfolio_non_interference() -> ScenarioDefinition:
    prior_close = 40.0
    candles = _range_bound(40.1, [0.05, -0.04, 0.03, -0.02])
    context = SetupContext(
        candles=candles,
        levels=_base_levels(prior_close),
        zones=_base_zones(prior_close),
        indicators={"avg_range": 0.2},
        flags={},
    )
    return ScenarioDefinition(
        scenario_id="SCN_PORTFOLIO_NON_INTERFERENCE",
        description="Portfolio arbitration does not mutate strategy signals.",
        context=context,
        validations=["non_interference"],
    )


def _mode_parity() -> ScenarioDefinition:
    prior_close = 50.0
    candles = _steady_uptrend(50.2, [0.15, 0.12, 0.1])
    context = SetupContext(
        candles=candles,
        levels=_base_levels(prior_close),
        zones=_base_zones(prior_close),
        indicators={"avg_range": 0.25},
        flags={},
    )
    return ScenarioDefinition(
        scenario_id="SCN_MODE_PARITY_SIM_PAPER_READONLY",
        description="Mode parity placeholder across SIM/PAPER/READ_ONLY/LIVE.",
        context=context,
        validations=["mode_parity_matrix"],
    )


def scenario_library() -> Dict[str, ScenarioDefinition]:
    scenarios = [
        _gap_and_go_basic(),
        _vwap_reclaim_basic(),
        _bull_flag_compression(),
        _head_and_shoulders(),
        _range_break_and_fail(),
        _liquidity_sweep_reclaim(),
        _no_trade_context_veto(),
        _portfolio_non_interference(),
        _mode_parity(),
    ]
    return {scenario.scenario_id: scenario for scenario in scenarios}


def list_scenario_ids() -> List[str]:
    return list(scenario_library().keys())


def get_scenario(scenario_id: str) -> ScenarioDefinition:
    scenarios = scenario_library()
    if scenario_id not in scenarios:
        raise KeyError(f"Unknown scenario_id: {scenario_id}")
    return scenarios[scenario_id]


def all_scenarios() -> List[ScenarioDefinition]:
    library = scenario_library()
    return [library[key] for key in sorted(library)]


def default_context() -> SetupContext:
    return _gap_and_go_basic().context
