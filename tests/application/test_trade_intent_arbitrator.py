from src.application.arbitration.trade_intent_arbitrator import (
    ArbitrationContext,
    TradeIntentArbitrator,
)
from src.models.data_models import TradeIntent


def _intent(
    symbol: str,
    direction: str,
    confidence: float,
    *,
    strategy_name: str = "s",
    expected_rr: float | None = None,
    liquidity_score: float | None = None,
) -> TradeIntent:
    intent = TradeIntent(
        symbol=symbol,
        direction=direction,
        strategy_name=strategy_name,
        confidence=confidence,
        rationale=f"{symbol}-{direction}",
    )
    if expected_rr is not None:
        intent.expected_rr = expected_rr
    if liquidity_score is not None:
        intent.liquidity_score = liquidity_score
    return intent


def test_arbitration_keeps_single_symbol_winner() -> None:
    arbitrator = TradeIntentArbitrator()
    context = ArbitrationContext(max_positions=5, max_intents_per_cycle=5)
    intents = [
        _intent("AAPL", "LONG", 0.9, strategy_name="alpha"),
        _intent("AAPL", "SHORT", 0.8, strategy_name="beta"),
    ]

    final = arbitrator.arbitrate(intents, context)

    assert len(final) == 1
    assert final[0].symbol == "AAPL"
    assert final[0].direction == "LONG"


def test_arbitration_honors_global_limits() -> None:
    arbitrator = TradeIntentArbitrator()
    context = ArbitrationContext(max_positions=2, max_intents_per_cycle=3)
    intents = [
        _intent("AAA", "LONG", 0.9),
        _intent("BBB", "LONG", 0.8),
        _intent("CCC", "LONG", 0.7),
        _intent("DDD", "LONG", 0.6),
    ]

    final = arbitrator.arbitrate(intents, context)

    assert [intent.symbol for intent in final] == ["AAA", "BBB"]


def test_arbitration_deduplicates_identical_intents() -> None:
    arbitrator = TradeIntentArbitrator()
    context = ArbitrationContext(max_positions=5, max_intents_per_cycle=5)
    duplicated = _intent("MSFT", "LONG", 0.7, strategy_name="alpha")
    intents = [duplicated, duplicated]

    final = arbitrator.arbitrate(intents, context)

    assert len(final) == 1
