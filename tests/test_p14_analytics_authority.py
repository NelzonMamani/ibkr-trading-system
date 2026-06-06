from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.core.analytics_authority import AnalyticsAuthority
from src.core.event_collector import EventCollector
from src.core.events import SystemEvent
from src.models.execution_result import ExecutionResult


NOW = datetime(2026, 6, 5, 14, 0, tzinfo=timezone.utc)


def _closed_payload(
    *,
    trade_id: str = "T-1",
    pnl: float = 10.0,
    symbol: str = "AAPL",
    strategy: str = "ross_momentum",
    setup: str = "OPENING_DRIVE",
    exit_category: str = "EXIT_TARGET",
    exit_reason: str = "TARGET_HIT",
    timestamp: datetime = NOW,
) -> dict:
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "trader_type": strategy,
        "strategy_name": strategy,
        "setup_family": setup,
        "pattern_name": setup,
        "entry_tick": 1,
        "exit_tick": 2,
        "entry_price": 100.0,
        "exit_price": 110.0,
        "raw_price": 110.0,
        "slippage_applied": 0.0,
        "execution_price": 110.0,
        "direction": "LONG",
        "quantity": 1,
        "exit_category": exit_category,
        "exit_reason": exit_reason,
        "pnl": pnl,
        "net_realised_pnl": pnl,
        "gross_realised_pnl": pnl,
        "commission": 0.0,
        "hold_duration_ticks": 1,
        "min_hold_ticks": 1,
        "max_hold_ticks": 10,
        "stop_loss_price": 95.0,
        "take_profit_price": 110.0,
        "timestamp": timestamp.isoformat(),
    }


def _record_closed(events: EventCollector, **overrides: object) -> None:
    payload = _closed_payload(**overrides)
    events.emit(
        event_type="TRADE_CLOSED",
        source="unit",
        payload=payload,
        timestamp=NOW,
    )


def _record_blocked(events: EventCollector, reason: str = "RISK_BLOCK") -> None:
    events.emit(
        event_type="TRADE_BLOCKED",
        source="unit",
        payload={
            "symbol": "AAPL",
            "trader_type": "ross_momentum",
            "strategy_name": "ross_momentum",
            "reason_code": reason,
            "human_readable_rationale": reason,
            "reason": reason,
        },
        timestamp=NOW,
    )


class _Store:
    def __init__(self, *, outcomes: list[dict] | None = None, events: list[dict] | None = None) -> None:
        self.outcomes = outcomes or []
        self.events = events or []

    def fetch_trade_outcomes(self, _run_id: str) -> list[dict]:
        return list(self.outcomes)

    def fetch_events(self, _run_id: str) -> list[dict]:
        return list(self.events)


class _BrokenStore:
    def fetch_trade_outcomes(self, _run_id: str) -> list[dict]:
        raise RuntimeError("database unavailable")

    def fetch_events(self, _run_id: str) -> list[dict]:
        return []


class _Storage:
    run_id = "run-p14"

    def __init__(self, store: object) -> None:
        self._store = store


def _authority(events: EventCollector | None = None, storage: object | None = None) -> AnalyticsAuthority:
    return AnalyticsAuthority(event_collector=events or EventCollector(), storage_engine=storage)


def test_empty_history_returns_zeroed_snapshot_without_incomplete_data() -> None:
    snapshot = _authority().evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.trade_count == 0
    assert snapshot.realized_pnl == 0.0
    assert snapshot.unrealized_pnl == 0.0
    assert snapshot.incomplete_data is False
    assert snapshot.data_quality_issue_count == 0


def test_closed_winning_trade_updates_win_gross_profit_and_realized_pnl() -> None:
    events = EventCollector()
    _record_closed(events, pnl=25.0)

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.trade_count == 1
    assert snapshot.win_count == 1
    assert snapshot.gross_profit == 25.0
    assert snapshot.realized_pnl == 25.0


def test_closed_losing_trade_updates_loss_gross_loss_and_realized_pnl() -> None:
    events = EventCollector()
    _record_closed(events, pnl=-7.5, exit_category="EXIT_STOP_LOSS", exit_reason="STOP_LOSS_HIT")

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.loss_count == 1
    assert snapshot.gross_loss == -7.5
    assert snapshot.realized_pnl == -7.5
    assert snapshot.stop_loss_exit_count == 1


def test_mixed_trades_calculate_win_rate_profit_factor_and_expectancy() -> None:
    events = EventCollector()
    _record_closed(events, trade_id="T-WIN", pnl=30.0)
    _record_closed(events, trade_id="T-LOSS", pnl=-10.0)
    _record_closed(events, trade_id="T-FLAT", pnl=0.0, exit_category="EXIT_STRATEGY")

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="PAPER",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.win_rate == 0.3333
    assert snapshot.profit_factor == 3.0
    assert snapshot.expectancy == 6.67
    assert snapshot.breakeven_count == 1
    assert snapshot.max_drawdown == -10.0


def test_blocked_trades_count_by_block_reason() -> None:
    events = EventCollector()
    _record_blocked(events, "P8_ALLOCATION_EXCEEDED")
    _record_blocked(events, "P8_ALLOCATION_EXCEEDED")

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="PAPER",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.blocked_trade_count == 2
    assert snapshot.block_reason_counts["P8_ALLOCATION_EXCEEDED"] == 2
    assert snapshot.breakdowns["block_reason"]["P8_ALLOCATION_EXCEEDED"]["blocked_trade_count"] == 2


def test_exit_reasons_are_classified() -> None:
    events = EventCollector()
    _record_closed(events, trade_id="STOP", pnl=-2.0, exit_category="EXIT_STOP_LOSS")
    _record_closed(events, trade_id="TARGET", pnl=5.0, exit_category="EXIT_TARGET")
    _record_closed(events, trade_id="TRAIL", pnl=3.0, exit_category="EXIT_TRAILING_STOP")
    _record_closed(events, trade_id="MANUAL", pnl=1.0, exit_category="MANUAL_EXIT")
    _record_closed(events, trade_id="UNKNOWN", pnl=0.0, exit_category="EXIT_OTHER")

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.stop_loss_exit_count == 1
    assert snapshot.target_exit_count == 1
    assert snapshot.trailing_exit_count == 1
    assert snapshot.manual_exit_count == 1
    assert snapshot.unknown_exit_count == 1


def test_strategy_symbol_and_setup_breakdowns_work() -> None:
    events = EventCollector()
    _record_closed(events, trade_id="A", pnl=10.0, symbol="AAPL", strategy="ross_momentum", setup="OPENING_DRIVE")
    _record_closed(events, trade_id="B", pnl=-4.0, symbol="MSFT", strategy="mean_reversion", setup="GAP_FILL")

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.breakdowns["strategy_key"]["ross_momentum"]["trade_count"] == 1
    assert snapshot.breakdowns["symbol"]["MSFT"]["realized_pnl"] == -4.0
    assert snapshot.breakdowns["setup_family"]["OPENING_DRIVE"]["realized_pnl"] == 10.0


def test_strategy_level_filter_returns_only_requested_strategy() -> None:
    events = EventCollector()
    _record_closed(events, trade_id="A", pnl=10.0, strategy="ross_momentum")
    _record_closed(events, trade_id="B", pnl=-4.0, strategy="mean_reversion")

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        strategy_key="ross_momentum",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.strategy_key == "ross_momentum"
    assert snapshot.trade_count == 1
    assert snapshot.realized_pnl == 10.0


def test_symbol_level_filter_returns_only_requested_symbol() -> None:
    events = EventCollector()
    _record_closed(events, trade_id="A", pnl=10.0, symbol="AAPL")
    _record_closed(events, trade_id="B", pnl=-4.0, symbol="MSFT")

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        symbol="MSFT",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.symbol == "MSFT"
    assert snapshot.trade_count == 1
    assert snapshot.realized_pnl == -4.0


def test_setup_family_filter_returns_only_requested_setup() -> None:
    events = EventCollector()
    _record_closed(events, trade_id="A", pnl=10.0, setup="OPENING_DRIVE")
    _record_closed(events, trade_id="B", pnl=-4.0, setup="GAP_FILL")

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        setup_family="GAP_FILL",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.setup_family == "GAP_FILL"
    assert snapshot.trade_count == 1
    assert snapshot.realized_pnl == -4.0


def test_missing_pnl_is_flagged_and_not_invented() -> None:
    events = EventCollector()
    payload = _closed_payload(trade_id="NO-PNL", pnl=0.0)
    for key in ("pnl", "net_realised_pnl", "gross_realised_pnl"):
        payload.pop(key, None)
    events.record_event(SystemEvent(event_type="TRADE_CLOSED", source="unit", payload=payload, timestamp=NOW))

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.trade_count == 1
    assert snapshot.realized_pnl == 0.0
    assert snapshot.win_count == 0
    assert snapshot.loss_count == 0
    assert "MISSING_REALIZED_PNL" in {issue.code for issue in snapshot.data_quality_issues}


def test_missing_identifiers_are_flagged() -> None:
    row = _closed_payload(trade_id="T-MISSING", pnl=3.0)
    row.pop("trade_id")
    row.pop("strategy_name")
    row.pop("trader_type")
    row.pop("setup_family")
    row.pop("pattern_name")
    storage = _Storage(_Store(outcomes=[row]))

    snapshot = _authority(storage=storage).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        now=NOW,
        emit_audit_event=False,
    )

    issue_codes = {issue.code for issue in snapshot.data_quality_issues}
    assert "MISSING_TRADE_ID" in issue_codes
    assert "MISSING_STRATEGY_KEY" in issue_codes
    assert "MISSING_SETUP_FAMILY" in issue_codes


def test_storage_unavailable_produces_analytics_degradation() -> None:
    storage = _Storage(_BrokenStore())

    snapshot = _authority(storage=storage).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="LIVE",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.incomplete_data is True
    assert "STORAGE_UNAVAILABLE" in {issue.code for issue in snapshot.data_quality_issues}


def test_p10_daily_risk_events_are_counted() -> None:
    events = EventCollector()
    events.record_event(
        SystemEvent(
            event_type="DAILY_RISK_DECISION",
            source="DailyRiskGovernor",
            payload={"blocks_new_entries": True, "status": "MANAGED_ONLY"},
            timestamp=NOW,
        )
    )

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="PAPER",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.daily_risk_lock_count == 1


def test_p11_recovery_events_are_counted() -> None:
    events = EventCollector()
    events.record_event(
        SystemEvent(
            event_type="AUTONOMOUS_RECOVERY_DECISION",
            source="AutonomousRecoveryAuthority",
            payload={
                "blocks_new_entries": True,
                "recovery_status": "MANAGED_ONLY",
            },
            timestamp=NOW,
        )
    )

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="PAPER",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.recovery_lock_count == 1
    assert snapshot.recovery_status_counts["MANAGED_ONLY"] == 1


def test_analytics_snapshot_emits_audit_event() -> None:
    events = EventCollector()
    _record_closed(events, pnl=11.0)

    snapshot = _authority(events).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        now=NOW,
    )

    audit_events = events.filter_by_type("ANALYTICS_SNAPSHOT")
    assert len(audit_events) == 1
    assert audit_events[0].payload["realized_pnl"] == snapshot.realized_pnl


def test_read_only_can_evaluate_without_mutating_authority_state() -> None:
    events = EventCollector()
    _record_closed(events, pnl=9.0)
    authority = _authority(events)

    snapshot = authority.evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="READ_ONLY",
        now=NOW,
    )

    assert snapshot.realized_pnl == 9.0
    assert authority.last_snapshot is None
    assert events.filter_by_type("ANALYTICS_SNAPSHOT")


def test_sim_and_paper_snapshots_match_for_identical_data() -> None:
    events = EventCollector()
    _record_closed(events, trade_id="T-SAME", pnl=15.0)
    authority = _authority(events)

    sim = authority.evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        now=NOW,
        emit_audit_event=False,
    )
    paper = authority.evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="PAPER",
        now=NOW,
        emit_audit_event=False,
    )

    assert sim.trade_count == paper.trade_count
    assert sim.realized_pnl == paper.realized_pnl
    assert sim.win_rate == paper.win_rate
    assert sim.breakdowns["symbol"] == paper.breakdowns["symbol"]


def test_execution_failures_from_results_are_counted() -> None:
    failed = ExecutionResult(
        symbol="AAPL",
        trader_type="ross_momentum",
        attempted=True,
        status="FAILED",
        rationale="BROKER_REJECTED",
    )

    snapshot = _authority().evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        now=NOW,
        execution_results=[failed],
        emit_audit_event=False,
    )

    assert snapshot.attempted_trade_count == 1
    assert snapshot.execution_failure_count == 1


def test_lifecycle_unrealized_pnl_is_included() -> None:
    lifecycle = SimpleNamespace(
        get_open_lifecycle_trades=lambda: [
            SimpleNamespace(trade_id="OPEN-1", unrealized_pnl=-2.5, status="OPEN")
        ]
    )

    snapshot = AnalyticsAuthority(trade_lifecycle_engine=lifecycle).evaluate(
        run_id="run-p14",
        trading_day="2026-06-05",
        run_mode="SIM",
        now=NOW,
        emit_audit_event=False,
    )

    assert snapshot.unrealized_pnl == -2.5
