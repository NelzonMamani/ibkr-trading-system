from src.strategies.common.candles.candle_types import Candle
from src.strategies.common.candles.functional import close_location_value, range_expansion
from src.strategies.common.candles.multi_candle import (
    detect_inside_bar,
    detect_outside_bar,
)
from src.strategies.common.candles.single_candle import (
    detect_dragonfly_doji,
    detect_gravestone_doji,
    detect_hanging_man,
    detect_inverted_hammer,
)


def test_single_candle_additional_patterns():
    inverted = Candle(open=10, high=14.5, low=9.9, close=11.5, volume=1000)
    assert detect_inverted_hammer(inverted) is not None

    hanging = Candle(open=10, high=10.2, low=8.0, close=9.5, volume=1000)
    assert detect_hanging_man(hanging) is not None

    dragonfly = Candle(open=10, high=10.1, low=8.0, close=10.02, volume=1000)
    assert detect_dragonfly_doji(dragonfly) is not None

    gravestone = Candle(open=10, high=12.0, low=9.9, close=10.01, volume=1000)
    assert detect_gravestone_doji(gravestone) is not None


def test_multi_candle_inside_outside_bar():
    first = Candle(open=10, high=12, low=9, close=11, volume=1000)
    inside = Candle(open=10.5, high=11.5, low=9.5, close=11, volume=1000)
    outside = Candle(open=9.5, high=12.5, low=8.5, close=12.2, volume=1000)

    assert detect_inside_bar([first, inside]) is not None
    assert detect_outside_bar([first, outside]) is not None


def test_functional_behaviours():
    candle = Candle(open=10, high=12, low=9, close=11, volume=1000)
    evidence = range_expansion(candle, avg_range=2.0, multiplier=1.2)
    assert evidence.detected is True

    clv = close_location_value(candle)
    assert clv.measurements["clv"] > 0
