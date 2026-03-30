from __future__ import annotations

from dataclasses import dataclass

from src.strategies.ross_momentum_strategy_v1 import RossMomentumStrategyV1


@dataclass
class _Levels:
    key_levels: dict
    hod: float | None = None
    lod: float | None = None


@dataclass
class _Inputs:
    levels: _Levels
    candles: list


@dataclass
class _Pattern:
    pattern_id: str


@dataclass
class _Trace:
    pattern_id: str
    setup_family_id: str
    detected: bool


@dataclass
class _Result:
    setup_id: str
    setup_family_id: str
    detected: bool


def test_orb_trade_uses_orh_orl_without_hod_lod_fallback() -> None:
    trade = RossMomentumStrategyV1._build_trade_from_pattern(
        _Pattern(pattern_id="P_ORB"),
        _Inputs(levels=_Levels(key_levels={"OPENING_RANGE_HIGH": 10.3, "OPENING_RANGE_LOW": 9.95}, hod=11.0, lod=9.2), candles=[]),
        selected_trigger={"trigger_price_reference": 10.3},
    )
    assert trade == (10.3, 9.95)

    blocked = RossMomentumStrategyV1._build_trade_from_pattern(
        _Pattern(pattern_id="P_ORB"),
        _Inputs(levels=_Levels(key_levels={}, hod=11.0, lod=9.2), candles=[]),
        selected_trigger={"trigger_price_reference": None},
    )
    assert blocked is None


def test_untrusted_patterns_are_filtered_with_explicit_log(capsys) -> None:
    strategy = RossMomentumStrategyV1()
    strategy._trusted_setup_families = {"OPENING_RANGE_BREAKOUT", "GAP_GO", "BULL_FLAG"}

    setups = [
        {"setup_family_id": "OPENING_RANGE_BREAKOUT", "setup_detected": True, "setup_name": "P_ORB"},
        {"setup_family_id": "HOD_BREAK", "setup_detected": True, "setup_name": "P_HOD_BREAK"},
    ]
    traces = [
        _Trace(pattern_id="P_ORB", setup_family_id="OPENING_RANGE_BREAKOUT", detected=True),
        _Trace(pattern_id="P_HOD_BREAK", setup_family_id="HOD_BREAK", detected=True),
    ]
    results = [
        _Result(setup_id="P_ORB", setup_family_id="OPENING_RANGE_BREAKOUT", detected=True),
        _Result(setup_id="P_HOD_BREAK", setup_family_id="HOD_BREAK", detected=True),
    ]

    trusted_setups = strategy._filter_trusted_setups(symbol="TEST", setups=setups)
    trusted_traces = strategy._filter_trusted_pattern_traces(symbol="TEST", pattern_traces=traces)
    trusted_results = strategy._filter_trusted_pattern_results(symbol="TEST", results=results)

    assert [item["setup_family_id"] for item in trusted_setups] == ["OPENING_RANGE_BREAKOUT"]
    assert [item.pattern_id for item in trusted_traces] == ["P_ORB"]
    assert [item.setup_id for item in trusted_results] == ["P_ORB"]

    out = capsys.readouterr().out
    assert "[ROSS][PATTERN_SKIP] symbol=TEST pattern=P_HOD_BREAK reason=UNTRUSTED_SETUP_NOT_ENABLED" in out
