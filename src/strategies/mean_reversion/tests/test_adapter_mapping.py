from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from pytest import approx

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.strategies.mean_reversion.adapters import (
    build_scanner_facts,
    policy_decision_to_model_intent,
)
from src.strategies.mean_reversion.mean_reversion_strategy_policy import (
    PolicyDecision,
    ScannerFacts,
    TradeIntent,
    Side,
    OrderType,
    TimeInForce,
)
from src.strategies.mean_reversion.strategy import MeanReversionStrategy


def test_build_scanner_facts_prefers_snapshot_prices() -> None:
    candidate = SimpleNamespace(
        symbol="TEST",
        last_price=10.0,
        bid=9.9,
        ask=10.1,
        spread=0.2,
        rvol=2.1,
        catalyst_present=True,
        halted=False,
        ssr=False,
    )
    snapshot = MarketSnapshot(
        symbol="TEST",
        bid=10.4,
        ask=10.6,
        last=10.5,
        asof_utc=datetime(2024, 1, 2, 15, 0, tzinfo=timezone.utc),
    )
    facts = build_scanner_facts(
        candidate,
        snapshot,
        timestamp_utc="2024-01-02T15:00:00+00:00",
        session_label="REG",
    )
    assert facts.last == 10.5
    assert facts.spread == approx(0.2)
    assert facts.rvol == 2.1
    assert facts.has_fresh_news is True
    assert facts.is_rth is True
    assert facts.minutes_since_open == 30


def test_policy_decision_maps_to_model_intent() -> None:
    intent = TradeIntent(
        symbol="MRV",
        side=Side.LONG,
        entry_type=OrderType.MARKET,
        entry_price=None,
        tif=TimeInForce.DAY,
        stop_price=9.5,
        target_price=12.0,
        thesis="test",
        notes="note",
    )
    decision = PolicyDecision(
        allowed=True,
        symbol="MRV",
        reason="APPROVED",
        setup="TEST_SETUP",
        intent=intent,
        diagnostics={"rr": 1.5},
    )
    facts = ScannerFacts(
        symbol="MRV",
        last=10.0,
        vwap=9.8,
        ema9=None,
        ema20=None,
        atr=0.5,
    )
    mapped = policy_decision_to_model_intent(
        decision,
        facts=facts,
        strategy_name="MeanReversionStrategy",
        trader_type="QUANT",
        data_quality_flags=["FLAG"],
    )
    assert mapped is not None
    assert mapped.direction == "LONG"
    assert mapped.stop_loss_price == 9.5
    assert mapped.take_profit_price == 12.0
    assert mapped.pattern_name == "TEST_SETUP"
    assert mapped.data_quality_flags == ["FLAG"]


def test_mean_reversion_emits_intent_in_read_only() -> None:
    strategy = MeanReversionStrategy()
    candidate = SimpleNamespace(
        symbol="REV",
        last_price=110.0,
        vwap=100.0,
        ema9=100.0,
        ema20=100.0,
        atr=5.0,
        spread=0.1,
        rvol=2.0,
        rejection_wick_up_flag=True,
        failed_breakout_up_flag=True,
        catalyst_present=False,
        halted=False,
        ssr=False,
    )
    intents = strategy.process_watchlist(
        watchlist=[candidate],
        snapshots={},
        session_label="REG",
        timestamp_utc="2024-01-02T15:00:00+00:00",
        mode=RunMode.READ_ONLY,
        session_phase="MORNING",
    )
    assert len(intents) == 1
