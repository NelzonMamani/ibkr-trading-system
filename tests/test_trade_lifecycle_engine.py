from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.core.engines.position_management_engine import ManagedPosition
from src.core.engines.trade_lifecycle_engine import LifecycleEvent, TradeLifecycleEngine
from src.core.portfolio.broker_position_adapter import BrokerPositionSnapshot
from src.models.data_models import ExecutionResult, RiskDecision, TradeIntent
from src.scanner.result_models import CandidateMetrics


@dataclass
class _PriceFeedStub:
    price: float = 11.25

    def get_price(self, _symbol: str) -> float:
        return self.price


def _candidate(symbol: str = "AAPL") -> CandidateMetrics:
    return CandidateMetrics(
        symbol=symbol,
        con_id=1,
        exchange="SMART",
        session_label="PRE",
        session_phase="PRE",
        last_price=11.0,
        prev_close=10.0,
        ref_close_rth=10.0,
        reference_price=10.0,
        reference_label="PRE",
        reference_source="TEST",
        reference_quality_tier="PRIMARY",
        reference_resolved=True,
        gap_pct=5.0,
        pct_change=10.0,
        pct_change_resolved=10.0,
        pct_change_qualification_usable=True,
        pct_change_execution_usable=True,
        pct_change_source_quality="PRIMARY",
        pct_change_degraded=False,
        pct_change_synthetic=False,
        pct_change_failure_reason=None,
        gap_pct_resolved=5.0,
        gap_source="TEST",
        context_status="LIVE",
        execution_ready=True,
        prep_only=False,
        live_rvol_deferred=False,
        prep_seeded=True,
        live_confirmation_pending=False,
        watchlist_source="TEST",
        promotion_reason="TEST",
        ibkr_change_pct=None,
        pct_source="TEST",
        open_relative_pct_change=None,
        hod_pct=1.0,
        rvol=3.0,
        rvol_discovery=3.0,
        rvol_phase=3.0,
        phase_volume_ratio=1.0,
        relative_volume=3.0,
        avg_volume_20d=100000,
        adv20_resolved=True,
        degraded_adv20=False,
        adv20_source="TEST",
        rvol_status="RESOLVED",
        rvol_failure_reason=None,
        rvol_degraded=False,
        rvol_qualification_usable=True,
        rvol_execution_usable=True,
        degraded_rvol_gate_bypass=False,
        float_shares=10000000,
        float_source="cache",
        float_asof="2026-01-01T00:00:00+00:00",
        float_cache_hit=True,
        float_millions=10.0,
        volume=200000,
        premarket_volume=50000,
        dollar_volume=1_000_000.0,
        bid=11.0,
        ask=11.01,
        spread=0.01,
        spread_pct=0.1,
        halted=False,
        ssr=False,
        catalyst_present=True,
        catalyst_summary="test",
        news_count=1,
        fresh_news_count=1,
        stale_news_count=0,
        top_news_title="test",
        top_news_age_hours=0.1,
        top_news_catalyst_tag="NEWS",
        news_source_mode="TEST",
        news_asof="2026-01-01T00:00:00+00:00",
        data_quality_ok=True,
        data_quality_flags=[],
        drop_reasons=[],
        rank_score=1.0,
        rank_components={"score": 1.0},
        timestamp_utc="2026-01-01T00:00:00+00:00",
        gate_checks={},
    )


def _build_orchestrator(monkeypatch) -> CoreOrchestrator:
    set_config_overrides(
        {
            "RUN_MODE": "SIM",
            "EXECUTION_ENABLED": True,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
            "SESSION_PHASE_OVERRIDE": "PREMARKET",
        }
    )
    row = _candidate()

    monkeypatch.setattr(
        "src.core.orchestrator.run_scanner_cycle",
        lambda **_kwargs: {
            "candidate_metrics": [row],
            "watchlist_k": [row],
            "watchlist_k_symbols": ["AAPL"],
            "focus_m": [row],
            "focus_m_symbols": ["AAPL"],
            "universe_top_n": [{"symbol": "AAPL"}],
            "candidates": [row],
        },
    )
    monkeypatch.setattr(
        "src.core.orchestrator.resolve_watchlist_selector",
        lambda *_: (lambda observations, _policy: observations),
    )
    monkeypatch.setattr("src.core.orchestrator.resolve_policy_v2", lambda *_: None)

    orchestrator = CoreOrchestrator()
    orchestrator.price_feed = _PriceFeedStub()
    orchestrator.market_data_snapshot_manager = SimpleNamespace(
        batch_snapshots=lambda _symbols: ({}, [])
    )
    orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **_kwargs: None
    orchestrator.strategy_runner.process = lambda **_kwargs: [
        TradeIntent(
            symbol="AAPL",
            direction="LONG",
            strategy_name="ross_momentum",
            confidence=0.9,
            rationale="lifecycle test",
        )
    ]
    orchestrator.risk_engine.evaluate_trade_intent = lambda _intent, _tick: RiskDecision(
        symbol="AAPL",
        allowed=True,
        max_position_size=100,
        risk_level="LOW",
        rationale="approved",
        direction="LONG",
        trader_type="SYSTEM",
        strategy_name="ross_momentum",
        stop_loss_price=10.5,
    )
    orchestrator.execution_engine.execute_trade = lambda _decision: ExecutionResult(
        symbol="AAPL",
        trader_type="SYSTEM",
        attempted=True,
        status="FILLED",
        rationale="filled",
        direction="LONG",
        quantity=10,
        filled_quantity=10,
        entry_price=11.0,
        raw_price=11.0,
        client_order_id="TEST-ORDER-1",
    )
    return orchestrator


def test_lifecycle_registration_failure_does_not_break_run_once(monkeypatch) -> None:
    orchestrator = _build_orchestrator(monkeypatch)
    monkeypatch.setattr(
        orchestrator,
        "_register_trade_lifecycle_on_execution",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("register failed")),
    )
    try:
        assert orchestrator.run_once() is True
    finally:
        set_config_overrides(None)


def test_lifecycle_reconcile_failure_does_not_break_cycle(monkeypatch) -> None:
    orchestrator = _build_orchestrator(monkeypatch)
    monkeypatch.setattr(
        orchestrator,
        "_reconcile_lifecycle_with_managed_position",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("reconcile failed")),
    )
    try:
        assert orchestrator.run_once() is True
    finally:
        set_config_overrides(None)


def test_lifecycle_mark_to_market_failure_is_non_blocking(monkeypatch) -> None:
    orchestrator = _build_orchestrator(monkeypatch)
    monkeypatch.setattr(
        orchestrator,
        "_mark_open_trades_to_market",
        lambda: (_ for _ in ()).throw(RuntimeError("mark failed")),
    )
    try:
        assert orchestrator.run_once() is True
    finally:
        set_config_overrides(None)


def test_lifecycle_summary_failure_is_non_blocking(monkeypatch) -> None:
    orchestrator = _build_orchestrator(monkeypatch)
    monkeypatch.setattr(
        orchestrator,
        "_summarize_trade_lifecycle_session",
        lambda: (_ for _ in ()).throw(RuntimeError("summary failed")),
    )
    try:
        assert orchestrator.run_once() is True
    finally:
        set_config_overrides(None)


def test_no_lifecycle_registration_when_execution_artifact_invalid(capsys) -> None:
    set_config_overrides({"RUN_MODE": "SIM", "EXECUTION_ENABLED": False})
    orchestrator = CoreOrchestrator()
    try:
        managed = ManagedPosition(
            symbol="AAPL",
            side="LONG",
            quantity=10,
            entry_price=11.0,
            stop_price=10.5,
        )
        result = ExecutionResult(
            symbol="AAPL",
            trader_type="SYSTEM",
            attempted=False,
            status="REJECTED",
            rationale="rejected",
            quantity=0,
            filled_quantity=0,
            entry_price=0.0,
        )
        assert (
            orchestrator._register_trade_lifecycle_on_execution(
                execution_result=result,
                managed_position=managed,
            )
            is None
        )
        assert "[LIFECYCLE][SKIP] stage=register" in capsys.readouterr().out
    finally:
        set_config_overrides(None)


def test_run_once_success_semantics_do_not_depend_on_lifecycle(monkeypatch) -> None:
    orchestrator = _build_orchestrator(monkeypatch)
    monkeypatch.setattr(
        orchestrator,
        "_register_trade_lifecycle_on_execution",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("broken register")),
    )
    monkeypatch.setattr(
        orchestrator,
        "_reconcile_lifecycle_with_managed_position",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("broken reconcile")),
    )
    monkeypatch.setattr(
        orchestrator,
        "_mark_open_trades_to_market",
        lambda: (_ for _ in ()).throw(RuntimeError("broken mark")),
    )
    monkeypatch.setattr(
        orchestrator,
        "_summarize_trade_lifecycle_session",
        lambda: (_ for _ in ()).throw(RuntimeError("broken summary")),
    )
    try:
        assert orchestrator.run_once() is True
    finally:
        set_config_overrides(None)


class _FailingLifecyclePersistence:
    def upsert_trade_lifecycle_trade(self, _payload):
        raise RuntimeError("persist trade failed")

    def insert_trade_lifecycle_event(self, _payload):
        raise RuntimeError("persist event failed")

    def insert_trade_lifecycle_reconciliation_event(self, _payload):
        raise RuntimeError("persist reconcile failed")

    def insert_trade_lifecycle_summary(self, _payload):
        raise RuntimeError("persist summary failed")

    def fetch_trade_lifecycle_trades(self):
        raise RuntimeError("load failed")


def _event(event_id: str, event_type: str, qty: int, price: float, side: str = "LONG") -> LifecycleEvent:
    return LifecycleEvent(
        event_id=event_id,
        lifecycle_trade_id="T1",
        symbol="AAPL",
        side=side,
        event_type=event_type,
        quantity=qty,
        price=price,
        timestamp="2026-01-01T00:00:00+00:00",
        order_id=f"O-{event_id}",
        execution_id=f"E-{event_id}",
    )


def test_entry_partial_exit_final_exit_and_marks() -> None:
    engine = TradeLifecycleEngine()
    engine.apply_event(_event("1", "ENTRY_FILL", 10, 10.0))
    engine.apply_event(_event("2", "ENTRY_FILL", 10, 12.0))
    trade = engine.get_trade("T1")
    assert trade is not None
    assert trade.quantity_open == 20
    assert round(trade.entry_avg_price, 6) == 11.0
    engine.apply_event(_event("3", "PARTIAL_EXIT", 5, 13.0))
    trade = engine.get_trade("T1")
    assert trade is not None
    assert trade.status == "PARTIALLY_CLOSED"
    assert trade.quantity_open == 15
    assert trade.quantity_closed == 5
    assert round(trade.gross_realized_pnl, 6) == 10.0
    engine.apply_mark_price(trade_id="T1", price=12.5)
    assert round(engine.get_trade("T1").unrealized_pnl, 6) == 22.5
    engine.apply_event(_event("4", "STOP_EXIT", 15, 12.0))
    trade = engine.get_trade("T1")
    assert trade is not None
    assert trade.status == "CLOSED"
    assert trade.quantity_open == 0
    assert round(trade.gross_realized_pnl, 6) == 25.0
    engine.apply_mark_price(trade_id="T1", price=15.0)
    assert trade.unrealized_pnl == 0.0


def test_duplicate_event_id_and_payload_are_idempotent() -> None:
    engine = TradeLifecycleEngine()
    event = _event("1", "ENTRY_FILL", 10, 10.0)
    engine.apply_event(event)
    engine.apply_event(event)
    engine.apply_event(
        LifecycleEvent(
            event_id="2",
            lifecycle_trade_id="T1",
            symbol="AAPL",
            side="LONG",
            event_type="ENTRY_FILL",
            quantity=10,
            price=10.0,
            timestamp="2026-01-01T00:00:01+00:00",
            order_id=event.order_id,
            execution_id=event.execution_id,
        )
    )
    trade = engine.get_trade("T1")
    assert trade is not None
    assert trade.quantity_open == 10
    summary = engine.summarize_session_metrics()
    assert summary["duplicate_events_ignored"] == 2


def test_reconciliation_orphan_and_drift_flags() -> None:
    engine = TradeLifecycleEngine()
    orphan = engine.apply_reconciliation_snapshot(symbol="AAPL", runtime_quantity=5, runtime_avg_entry=10.0)
    assert orphan["classification"] == "EXTERNAL"
    engine.apply_event(_event("1", "ENTRY_FILL", 10, 10.0))
    drift = engine.apply_reconciliation_snapshot(symbol="AAPL", runtime_quantity=7, runtime_avg_entry=10.0)
    assert drift["classification"] == "MISMATCH"
    report = engine.get_drift_report()
    assert len(report) >= 2


def test_recovery_loads_open_without_reopening_closed() -> None:
    class _RecoveryPersistence:
        def fetch_trade_lifecycle_trades(self):
            return [
                {
                    "lifecycle_trade_id": "OPEN1",
                    "symbol": "AAPL",
                    "side": "LONG",
                    "status": "OPEN",
                    "opened_at": "2026-01-01T00:00:00+00:00",
                    "quantity_open": 5,
                    "quantity_closed": 0,
                    "entry_avg_price": 10.0,
                },
                {
                    "lifecycle_trade_id": "CLOSED1",
                    "symbol": "MSFT",
                    "side": "LONG",
                    "status": "CLOSED",
                    "opened_at": "2026-01-01T00:00:00+00:00",
                    "closed_at": "2026-01-01T00:10:00+00:00",
                    "quantity_open": 0,
                    "quantity_closed": 5,
                    "entry_avg_price": 20.0,
                },
            ]

    engine = TradeLifecycleEngine(persistence_adapter=_RecoveryPersistence())
    result = engine.recover_open_state()
    assert result["ok"] is True
    assert result["open_loaded"] == 1
    assert engine.find_open_trade_id_for_symbol("AAPL") == "OPEN1"
    assert engine.find_open_trade_id_for_symbol("MSFT") is None


def test_persistence_and_recovery_failures_are_non_blocking() -> None:
    engine = TradeLifecycleEngine(persistence_adapter=_FailingLifecyclePersistence())
    engine.apply_event(_event("1", "ENTRY_FILL", 10, 10.0))
    reconcile = engine.apply_reconciliation_snapshot(symbol="AAPL", runtime_quantity=10, runtime_avg_entry=10.0)
    assert reconcile["status"] == "MATCH"
    summary = engine.summarize_session_metrics()
    assert summary["total_lifecycle_trades_seen"] == 1
    recovery = engine.recover_open_state()
    assert recovery["degraded"] is True


def test_broker_reconcile_lifecycle_open_broker_flat_orphaned() -> None:
    engine = TradeLifecycleEngine()
    engine.apply_event(_event("1", "ENTRY_FILL", 10, 10.0))
    findings = engine.reconcile_with_broker_snapshot(
        [BrokerPositionSnapshot(symbol="AAPL", quantity=0, avg_entry_price=0.0, timestamp="2026-01-01T00:00:00+00:00")]
    )
    assert findings[0]["classification"] == "ORPHAN"
    assert findings[0]["severity"] == "CRITICAL"
    assert engine.find_open_trade_id_for_symbol("AAPL") is None


def test_broker_reconcile_broker_open_lifecycle_missing_orphaned() -> None:
    engine = TradeLifecycleEngine()
    findings = engine.reconcile_with_broker_snapshot(
        [BrokerPositionSnapshot(symbol="AAPL", quantity=10, avg_entry_price=10.0, timestamp="2026-01-01T00:00:00+00:00")]
    )
    assert findings[0]["classification"] == "EXTERNAL"
    assert findings[0]["severity"] == "CRITICAL"


def test_broker_reconcile_qty_mismatch_drifted() -> None:
    engine = TradeLifecycleEngine()
    engine.apply_event(_event("1", "ENTRY_FILL", 10, 10.0))
    findings = engine.reconcile_with_broker_snapshot(
        [BrokerPositionSnapshot(symbol="AAPL", quantity=8, avg_entry_price=10.0, timestamp="2026-01-01T00:00:00+00:00")]
    )
    assert findings[0]["classification"] == "MISMATCH"
    assert findings[0]["severity"] == "WARNING"


def test_portfolio_aggregation_and_closed_trade_exclusion() -> None:
    engine = TradeLifecycleEngine()
    engine.apply_event(_event("1", "ENTRY_FILL", 10, 10.0))
    engine.apply_event(
        LifecycleEvent(
            event_id="2",
            lifecycle_trade_id="T2",
            symbol="MSFT",
            side="LONG",
            event_type="ENTRY_FILL",
            quantity=5,
            price=20.0,
            timestamp="2026-01-01T00:00:00+00:00",
        )
    )
    engine.apply_event(_event("3", "STOP_EXIT", 10, 12.0))
    state = engine.build_portfolio_state()
    assert state.total_open_positions == 1
    assert state.total_exposure == 100.0
    assert state.total_realized_pnl == 20.0
    assert state.symbols_open == ["MSFT"]


def test_risk_signals_drawdown_and_drift_triggered() -> None:
    engine = TradeLifecycleEngine()
    engine.apply_event(_event("1", "ENTRY_FILL", 10, 10.0))
    trade = engine.get_trade("T1")
    assert trade is not None
    trade.gross_realized_pnl = -350.0
    trade.status = "DRIFTED"
    trade.drift_flags.add("BROKER_QTY_MISMATCH")
    signals = engine.compute_lifecycle_risk_signals()
    assert signals.max_drawdown_breached is True
    assert signals.drift_detected is True


def test_broker_fetch_failure_and_reconcile_failure_are_non_blocking(monkeypatch) -> None:
    orchestrator = _build_orchestrator(monkeypatch)

    class _BrokenAdapter:
        def fetch_broker_positions(self):
            raise RuntimeError("broker down")

    orchestrator._broker_position_adapter = _BrokenAdapter()
    monkeypatch.setattr(
        orchestrator.trade_lifecycle_engine,
        "reconcile_with_broker_snapshot",
        lambda _snapshot: (_ for _ in ()).throw(RuntimeError("reconcile explode")),
    )
    try:
        assert orchestrator.run_once() is True
    finally:
        set_config_overrides(None)
