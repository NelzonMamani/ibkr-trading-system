from decimal import Decimal
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from models.data_models import PatternResult  # noqa: E402
from signals.types import SignalDecision, SignalEvent, SignalType  # noqa: E402
from strategy.signal_adapter import SignalToIntentAdapter  # noqa: E402


def _make_event(
    symbol: str, signal_type: SignalType, confidence: float
) -> SignalEvent:
    return SignalEvent(
        signal_type=signal_type,
        symbol=symbol,
        tick=1,
        decision=SignalDecision.SIGNAL,
        confidence=confidence,
        rationale=f"Teaching signal for {symbol}",
        entry_level=Decimal("12.40"),
        stop_level=Decimal("12.10"),
        target_level=None,
        invalidation_level=Decimal("12.00"),
        source="TestSignal",
    )


def test_selects_highest_priority_signal_per_symbol():
    adapter = SignalToIntentAdapter()
    events_by_symbol = {
        "ABC": [
            _make_event("ABC", SignalType.ORB_1M, 0.9),
            _make_event("ABC", SignalType.HOD_BREAK, 0.4),
        ]
    }

    intents = adapter.to_trade_intents(
        signal_events_by_symbol=events_by_symbol,
        pattern_results=[],
        scanner_candidates=[],
        tick=1,
    )

    assert len(intents) == 1
    intent = intents[0]
    assert intent.symbol == "ABC"
    assert intent.strategy_name == "GapAndGoStrategy"
    assert intent.trader_type == "SCALPER"
    assert intent.confidence == 0.4


def test_confidence_merge_uses_pattern_cap():
    adapter = SignalToIntentAdapter()
    events_by_symbol = {
        "XYZ": [_make_event("XYZ", SignalType.BULL_FLAG, 0.6)]
    }
    patterns = [
        PatternResult(
            symbol="XYZ",
            pattern_name="Gap and Go (Teaching)",
            confidence=0.96,
            rationale="Pattern rationale",
        )
    ]

    intents = adapter.to_trade_intents(
        signal_events_by_symbol=events_by_symbol,
        pattern_results=patterns,
        scanner_candidates=[],
        tick=1,
    )

    assert len(intents) == 1
    assert intents[0].confidence == pytest.approx(0.95)
    assert "Pattern=Gap and Go (Teaching)" in intents[0].rationale


def test_global_cap_limits_to_three_intents():
    adapter = SignalToIntentAdapter()
    events_by_symbol = {
        "AAA": [_make_event("AAA", SignalType.MICRO_PULLBACK, 0.1)],
        "BBB": [_make_event("BBB", SignalType.MICRO_PULLBACK, 0.9)],
        "CCC": [_make_event("CCC", SignalType.MICRO_PULLBACK, 0.8)],
        "DDD": [_make_event("DDD", SignalType.MICRO_PULLBACK, 0.7)],
    }

    intents = adapter.to_trade_intents(
        signal_events_by_symbol=events_by_symbol,
        pattern_results=[],
        scanner_candidates=[],
        tick=1,
    )

    assert len(intents) == 3
    symbols = {intent.symbol for intent in intents}
    assert symbols == {"BBB", "CCC", "DDD"}
