from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.capital_management_authority import CapitalDecisionStatus, CapitalManagementAuthority
from src.core.event_collector import EventCollector
from src.core.strategy_arbitration_authority import (
    StrategyArbitrationAuthority,
    StrategyArbitrationStatus,
    StrategyIntentCandidate,
)
from src.core.strategy_capital_allocation_authority import (
    StrategyAllocationStatus,
    StrategyCapitalAllocationAuthority,
)


NOW = datetime(2026, 6, 5, 14, 30, tzinfo=timezone.utc)


def _candidate(
    intent_id: str,
    *,
    strategy_id: str = "alpha",
    symbol: str = "AAPL",
    side: str = "LONG",
    quantity: int = 1,
    notional: float = 100.0,
    priority: int = 0,
    confidence: float = 0.5,
    score: float | None = None,
    timestamp: datetime | None = None,
    setup_id: str | None = "setup",
    risk_hint: float | None = None,
    capital_hint: float | None = None,
) -> StrategyIntentCandidate:
    return StrategyIntentCandidate(
        intent_id=intent_id,
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        requested_quantity=quantity,
        requested_notional=notional,
        priority=priority,
        confidence=confidence,
        score=confidence if score is None else score,
        timestamp=timestamp or NOW,
        setup_id=setup_id,
        risk_hint=risk_hint,
        capital_hint=capital_hint,
    )


def test_p9_replay_is_deterministic_for_same_inputs() -> None:
    authority = StrategyArbitrationAuthority()
    intents = [
        _candidate("beta-aapl", strategy_id="beta", priority=2, confidence=0.9),
        _candidate("alpha-aapl", strategy_id="alpha", priority=2, confidence=0.9),
    ]

    first = authority.arbitrate(list(reversed(intents)), run_mode="LIVE", now=NOW)
    second = authority.arbitrate(intents, run_mode="LIVE", now=NOW)

    assert first.selected_intent_ids == ["alpha-aapl"]
    assert second.selected_intent_ids == ["alpha-aapl"]
    assert first.deterministic_seed == second.deterministic_seed
    assert first.ranking_order == second.ranking_order


def test_p9_priority_then_confidence_selects_winner() -> None:
    authority = StrategyArbitrationAuthority()

    priority_decision = authority.arbitrate(
        [
            _candidate("low-priority", strategy_id="alpha", priority=1, confidence=0.99),
            _candidate("high-priority", strategy_id="beta", priority=5, confidence=0.2),
        ],
        run_mode="LIVE",
        now=NOW,
    )
    confidence_decision = authority.arbitrate(
        [
            _candidate("lower-confidence", strategy_id="alpha", priority=3, confidence=0.4),
            _candidate("higher-confidence", strategy_id="beta", priority=3, confidence=0.8),
        ],
        run_mode="LIVE",
        now=NOW,
    )

    assert priority_decision.selected_intent_ids == ["high-priority"]
    assert confidence_decision.selected_intent_ids == ["higher-confidence"]


def test_p9_rejects_stale_and_disabled_intents() -> None:
    authority = StrategyArbitrationAuthority(disabled_strategies={"disabled"})

    decision = authority.arbitrate(
        [
            _candidate("stale", strategy_id="alpha", timestamp=NOW - timedelta(minutes=10)),
            _candidate("disabled", strategy_id="disabled"),
            _candidate("fresh", strategy_id="fresh", symbol="MSFT"),
        ],
        run_mode="LIVE",
        now=NOW,
    )

    assert decision.selected_intent_ids == ["fresh"]
    assert decision.reasons["stale"] == "STALE_INTENT"
    assert decision.reasons["disabled"] == "STRATEGY_DISABLED"


def test_p9_same_symbol_conflicts_resolve_to_one_winner() -> None:
    authority = StrategyArbitrationAuthority()

    same_direction = authority.arbitrate(
        [
            _candidate("alpha-long", strategy_id="alpha", side="LONG", priority=1),
            _candidate("beta-long", strategy_id="beta", side="LONG", priority=3),
        ],
        run_mode="LIVE",
        now=NOW,
    )
    opposing = authority.arbitrate(
        [
            _candidate("alpha-long", strategy_id="alpha", side="LONG", priority=1),
            _candidate("beta-short", strategy_id="beta", side="SHORT", priority=3),
        ],
        run_mode="LIVE",
        now=NOW,
    )

    assert same_direction.selected_intent_ids == ["beta-long"]
    assert same_direction.reasons["alpha-long"] == "DUPLICATE_SYMBOL"
    assert opposing.selected_intent_ids == ["beta-short"]
    assert opposing.reasons["alpha-long"] == "OPPOSING_INTENT"


def test_p9_same_strategy_duplicate_intents_are_deduplicated() -> None:
    authority = StrategyArbitrationAuthority()

    decision = authority.arbitrate(
        [
            _candidate("first", strategy_id="alpha", priority=1, confidence=0.6),
            _candidate("second", strategy_id="alpha", priority=1, confidence=0.9),
        ],
        run_mode="LIVE",
        now=NOW,
    )

    assert decision.selected_intent_ids == ["second"]
    assert decision.reasons["first"] == "DUPLICATE_STRATEGY_INTENT"


def test_p9_read_only_and_recovery_incomplete_do_not_select_executable_intents() -> None:
    authority = StrategyArbitrationAuthority()

    read_only = authority.arbitrate([_candidate("read-only")], run_mode="READ_ONLY", now=NOW)
    recovery_block = authority.arbitrate(
        [_candidate("recovery")],
        run_mode="LIVE",
        now=NOW,
        recovery_complete=False,
    )

    assert read_only.status == StrategyArbitrationStatus.READ_ONLY_BLOCKED
    assert read_only.selected_intents == []
    assert recovery_block.status == StrategyArbitrationStatus.RECOVERY_NOT_COMPLETE
    assert recovery_block.selected_intents == []


def test_p9_rejected_intents_are_audited() -> None:
    collector = EventCollector()
    authority = StrategyArbitrationAuthority(event_collector=collector)

    decision = authority.arbitrate(
        [
            _candidate("winner", strategy_id="alpha", priority=10),
            _candidate("loser", strategy_id="beta", priority=1),
        ],
        run_mode="LIVE",
        now=NOW,
    )

    events = collector.filter_by_type("STRATEGY_ARBITRATION_DECISION")
    assert len(events) == 1
    assert events[0].payload["arbitration_id"] == decision.arbitration_id
    assert events[0].payload["selected_intent_ids"] == ["winner"]
    assert events[0].payload["rejected_intent_ids"] == ["loser"]


def test_p9_does_not_increase_size_or_bypass_p8_or_p7() -> None:
    authority = StrategyArbitrationAuthority()
    p9_decision = authority.arbitrate(
        [_candidate("intent", strategy_id="alpha", quantity=10, notional=1_000.0)],
        run_mode="LIVE",
        now=NOW,
    )
    selected = p9_decision.selected_intents[0]

    p8 = StrategyCapitalAllocationAuthority(
        run_mode="LIVE",
        strategy_limits={"ALPHA": {"enabled": True, "allocation_pct": 0.01, "max_positions": 5}},
    )
    p8_decision = p8.evaluate_entry(
        run_mode="LIVE",
        strategy_id=selected.strategy_id,
        symbol=selected.symbol,
        side=selected.side,
        requested_quantity=selected.requested_quantity,
        reference_price=100.0,
        available_capital=10_000.0,
        account_equity=10_000.0,
        recovery_complete=True,
        reserve=False,
    )

    p7 = CapitalManagementAuthority(
        run_mode="LIVE",
        account_equity=10_000.0,
        available_capital=50.0,
        buying_power=50.0,
        broker_truth_available=True,
    )
    p7_decision = p7.evaluate_entry(
        run_mode="LIVE",
        strategy_id=selected.strategy_id,
        symbol=selected.symbol,
        side=selected.side,
        requested_quantity=selected.requested_quantity,
        reference_price=100.0,
        recovery_complete=True,
        risk_approved=True,
        reserve=False,
    )

    assert selected.requested_quantity == 10
    assert p8_decision.status == StrategyAllocationStatus.STRATEGY_CAPITAL_EXCEEDED
    assert p7_decision.status == CapitalDecisionStatus.INSUFFICIENT_CAPITAL
