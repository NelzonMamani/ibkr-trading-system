from __future__ import annotations

from src.core.portfolio.portfolio_arbitrator import PortfolioArbitrator
from src.core.portfolio.portfolio_state import PortfolioState
from src.models.data_models import TradeIntent


def _intent(symbol: str, confidence: float, *, allowed: bool = True, execution_blocked: bool = False) -> TradeIntent:
    intent = TradeIntent(
        symbol=symbol,
        direction="LONG",
        strategy_name="ross_momentum",
        confidence=confidence,
        rationale=f"intent-{symbol}",
    )
    intent.allowed = allowed
    intent.execution_blocked = execution_blocked
    intent.rvol = confidence * 5.0
    intent.pattern_quality_score = confidence
    intent.spread_quality_score = confidence
    intent.proximity_to_key_level = confidence
    intent.entry_price = 10.0
    intent.quantity = 10
    return intent


def _patch_limits(monkeypatch, *, max_positions: int, max_portfolio: float, max_position: float) -> None:
    limits = {
        "LIFECYCLE_MAX_POSITIONS": max_positions,
        "LIFECYCLE_MAX_PORTFOLIO_EXPOSURE": max_portfolio,
        "LIFECYCLE_MAX_POSITION_EXPOSURE": max_position,
    }
    monkeypatch.setattr(
        "src.core.portfolio.portfolio_arbitrator.get_config",
        lambda key: limits[key],
    )


def test_multiple_intents_highest_score_selected(monkeypatch):
    _patch_limits(monkeypatch, max_positions=5, max_portfolio=10_000.0, max_position=10_000.0)
    arbitrator = PortfolioArbitrator()
    intents = [_intent("AAA", 0.2), _intent("BBB", 0.9), _intent("CCC", 0.5)]

    selected = arbitrator.select_trades(intents, PortfolioState())

    assert [intent.symbol for intent in selected][:1] == ["BBB"]


def test_capital_limit_blocks_excess_trades(monkeypatch):
    _patch_limits(monkeypatch, max_positions=5, max_portfolio=200.0, max_position=200.0)
    arbitrator = PortfolioArbitrator()
    intents = [_intent("AAA", 0.9), _intent("BBB", 0.8), _intent("CCC", 0.7)]

    selected = arbitrator.select_trades(intents, PortfolioState())

    assert [intent.symbol for intent in selected] == ["AAA", "BBB"]


def test_max_positions_enforced(monkeypatch):
    _patch_limits(monkeypatch, max_positions=2, max_portfolio=10_000.0, max_position=10_000.0)
    arbitrator = PortfolioArbitrator()
    intents = [_intent("AAA", 0.9), _intent("BBB", 0.8), _intent("CCC", 0.7)]

    selected = arbitrator.select_trades(intents, PortfolioState())

    assert len(selected) == 2
    assert [intent.symbol for intent in selected] == ["AAA", "BBB"]


def test_deterministic_ordering(monkeypatch):
    _patch_limits(monkeypatch, max_positions=5, max_portfolio=10_000.0, max_position=10_000.0)
    arbitrator = PortfolioArbitrator()
    left = _intent("AAA", 0.7)
    right = _intent("BBB", 0.7)

    first = arbitrator.select_trades([right, left], PortfolioState())
    second = arbitrator.select_trades([left, right], PortfolioState())

    assert [intent.symbol for intent in first] == ["AAA", "BBB"]
    assert [intent.symbol for intent in second] == ["AAA", "BBB"]


def test_empty_input_safe(monkeypatch):
    _patch_limits(monkeypatch, max_positions=5, max_portfolio=10_000.0, max_position=10_000.0)
    arbitrator = PortfolioArbitrator()

    selected = arbitrator.select_trades([], PortfolioState())

    assert selected == []


def test_risk_blocked_trades_excluded(monkeypatch):
    _patch_limits(monkeypatch, max_positions=5, max_portfolio=10_000.0, max_position=10_000.0)
    arbitrator = PortfolioArbitrator()
    intents = [
        _intent("AAA", 0.9, allowed=False),
        _intent("BBB", 0.8, execution_blocked=True),
        _intent("CCC", 0.7),
    ]

    selected = arbitrator.select_trades(intents, PortfolioState())

    assert [intent.symbol for intent in selected] == ["CCC"]
