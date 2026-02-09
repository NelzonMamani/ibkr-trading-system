from src.strategies.common import foundation
from src.strategies.common.foundation_detectors import (
    SetupContext,
    SETUP_DETECTORS,
    detect_all_setups,
    detect_level_interaction,
    detect_setup_family,
    detect_zone_interaction,
)
from src.strategies.common.candles.candle_types import Candle


def test_setup_detector_registry_matches_canonical_list():
    assert set(SETUP_DETECTORS.keys()) == set(foundation.SETUP_FAMILIES)
    results = detect_all_setups(SetupContext([]))
    assert all(result.setup_family_id in foundation.SETUP_FAMILIES for result in results)


def test_gap_and_go_detection_positive():
    candles = [
        Candle(102, 105, 101, 104, 1000),
        Candle(104, 106, 103, 105, 1000),
        Candle(105, 107, 104, 106, 1000),
    ]
    context = SetupContext(candles, levels={"LVL_PRIOR_DAY_CLOSE": 100})
    result = detect_setup_family("SF_GAP_AND_GO", context)
    assert result.detected is True


def test_vwap_reclaim_detection_positive():
    candles = [
        Candle(101, 102, 98, 99, 1000),
        Candle(99, 103, 98, 101, 1000),
    ]
    context = SetupContext(candles, indicators={"vwap": 100})
    result = detect_setup_family("SF_VWAP_RECLAIM", context)
    assert result.detected is True


def test_head_and_shoulders_detection_positive():
    candles = [
        Candle(10, 11, 9, 10, 1000),
        Candle(10, 12, 9, 11, 1000),
        Candle(11, 15, 10, 12, 1000),
        Candle(12, 12, 10, 11, 1000),
        Candle(11, 11, 9, 10, 1000),
    ]
    context = SetupContext(candles)
    result = detect_setup_family("SF_HEAD_AND_SHOULDERS", context)
    assert result.detected is True


def test_range_structure_and_level_zone_helpers():
    candles = [
        Candle(10, 10.5, 9.8, 10.1, 1000),
        Candle(10.1, 10.4, 9.9, 10.0, 1000),
        Candle(10.0, 10.3, 9.9, 10.1, 1000),
    ]
    context = SetupContext(candles)
    results = detect_all_setups(context)
    assert len(results) == len(foundation.SETUP_FAMILIES)
    level_result = detect_level_interaction(10.02, 10.0, tolerance=0.01)
    zone_result = detect_zone_interaction(10.05, (9.9, 10.2))
    assert level_result.detected is True
    assert zone_result.detected is True
