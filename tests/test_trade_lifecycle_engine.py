from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.core.engines.position_management_engine import ManagedPosition
from src.core.engines.trade_lifecycle_engine import LifecycleEvent, NativeValuationObservation, TradeLifecycleEngine
from src.core.portfolio.broker_position_adapter import BrokerPositionSnapshot
from src.models.data_models import ExecutionResult, RiskDecision, TradeIntent
from src.scanner.result_models import CandidateMetrics


@pytest.fixture
def native_lifecycle(isolated_runtime_schema):
    from src.storage.storage_engine import StorageEngine
    set_config_overrides({"PERSISTENCE_SQLITE_PATH": str(isolated_runtime_schema),
        "PERSISTENCE_ENABLED": True, "PERSISTENCE_BACKEND": "sqlite", "PERSIST_FLUSH_EACH_CYCLE": True})
    storage = StorageEngine()
    try:
        engine = TradeLifecycleEngine(storage)
        engine._test_native_valuation_client = SimpleNamespace(client_id=71, _position_connection_epoch=3, isConnected=lambda: True)
        yield engine, storage
    finally:
        storage.shutdown()
        set_config_overrides(None)


def _native_event(event_id, event_type, quantity, price, *, native_id=71,
                  timestamp="2026-10-20T13:35:00+00:00", root="NATIVE-ROOT"):
    event = LifecycleEvent(event_id, root, "JPM", "LONG", event_type, quantity, price,
        timestamp, order_id=str(native_id), execution_id="EXEC-" + event_id,
        source="native_cached_fill", metadata={"feedback_id": "FB-" + event_id})
    identity = dict(root_order_id=root, account="SYNTHETIC_TEST", strategy="RossMomentumStrategyV1",
        native_order_id=str(native_id), client_id=71, connection_epoch=3, con_id=123, symbol="JPM", side="LONG")
    return event, identity


def _apply_native(engine, event, identity, before):
    trade = engine.apply_event(event, strict=True, native_identity=identity,
        expected_quantity=before, strategy_name=identity["strategy"], stop_price=10.0)
    engine.complete_native_feedback(event.metadata["feedback_id"])
    return trade


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


def test_native_feedback_commits_partial_loss_and_duplicate_once(native_lifecycle):
    import json
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 2, 10.5)
    engine.require_native_feedback('FB-entry', identity)
    assert not engine.native_feedback_snapshot()['available']
    trade = engine.apply_event(entry, strict=True, native_identity=identity,
        expected_quantity=0, stop_price=10.0)
    assert trade.quantity_open == 2 and storage.fetch_trade_lifecycle_events()[0]['event_id'] == 'entry'
    assert not engine.native_feedback_snapshot()['available']  # Caller completion is separate.
    engine.complete_native_feedback('FB-entry')
    partial, child = _native_event('partial', 'STOP_EXIT', 1, 10.25, native_id=72,
        timestamp='2026-10-20T13:35:10+00:00')
    _apply_native(engine, partial, child, 2)
    snapshot = engine.native_feedback_snapshot()
    assert snapshot['available'] and snapshot['events'][-1]['metadata']['realized_increment'] == -.25
    assert not snapshot['events'][-1]['metadata']['terminal']
    assert trade.quantity_open == 1 and trade.gross_realized_pnl == -.25
    final, child = _native_event('final', 'STOP_EXIT', 1, 10., native_id=72,
        timestamp='2026-10-20T13:35:20+00:00')
    _apply_native(engine, final, child, 1)
    _apply_native(engine, final, child, 1)
    assert trade.quantity_open == 0 and trade.quantity_closed == 2 and trade.gross_realized_pnl == -.75
    assert trade.target_price is None and trade.stop_price == 10.
    assert len(storage.fetch_trade_lifecycle_events()) == len(engine.native_feedback_snapshot()['events']) == 3
    persisted = storage.fetch_trade_lifecycle_trades()[0]
    assert persisted['gross_realized_pnl'] == -.75 and persisted['status'] == 'CLOSED'
    final_payload = json.loads(storage.fetch_trade_lifecycle_events()[-1]['payload_json'])
    assert final_payload['native_identity']['account'] == 'SYNTHETIC_TEST'
    assert final_payload['terminal'] and final_payload['quantity_before'] == 1 and final_payload['quantity_after'] == 0


def test_native_terminal_time_tracks_execution_time_not_arrival(native_lifecycle):
    engine, _ = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 2, 10.5,
        timestamp='2026-10-19T13:35:00+00:00')
    _apply_native(engine, entry, identity, 0)
    newer, child = _native_event('newer', 'STOP_EXIT', 1, 10.25, native_id=72,
        timestamp='2026-10-20T13:35:10+00:00')
    _apply_native(engine, newer, child, 2)
    older, child = _native_event('older', 'STOP_EXIT', 1, 10., native_id=72,
        timestamp='2026-10-19T13:35:20+00:00')
    trade = _apply_native(engine, older, child, 1)
    snapshot = engine.native_feedback_snapshot()
    assert snapshot['events'][-1]['timestamp'] == '2026-10-19T13:35:20+00:00'
    assert trade.closed_at == snapshot['events'][-1]['metadata']['terminal_timestamp'] == '2026-10-20T13:35:10+00:00'


@pytest.mark.parametrize('fault', ['root', 'account', 'side', 'quantity', 'prior_quantity', 'naive_time', 'target_event', 'price'])
def test_native_invalid_fill_cannot_clamp_or_merge_ownership(native_lifecycle, fault):
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 2, 10.5)
    _apply_native(engine, entry, identity, 0)
    event, identity = _native_event('exit', 'STOP_EXIT', 1, 10.25, native_id=72)
    before = 2
    if fault == 'root':
        event.lifecycle_trade_id = identity['root_order_id'] = 'OTHER-ROOT'
    elif fault == 'account': identity['account'] = 'OTHER-ACCOUNT'
    elif fault == 'side': event.side = 'SELL'
    elif fault == 'quantity': event.quantity = 3
    elif fault == 'prior_quantity': before = 1
    elif fault == 'naive_time': event.timestamp = '2026-10-20T13:35:00'
    elif fault == 'target_event': event.event_type = 'TAKE_PROFIT_FILLED'
    elif fault == 'price': event.price = float('nan')
    with pytest.raises((ValueError, RuntimeError)):
        _apply_native(engine, event, identity, before)
    assert engine.get_trade('NATIVE-ROOT').quantity_open == 2
    assert engine.get_trade('NATIVE-ROOT').gross_realized_pnl == 0
    assert engine.get_trade('NATIVE-ROOT').target_price is None
    assert len(storage.fetch_trade_lifecycle_events()) == 1
    assert engine.native_feedback_snapshot()['uncertain'] and not engine.native_feedback_snapshot()['available']
    with pytest.raises(RuntimeError, match='UNCERTAIN'):
        engine.apply_event(event, strict=True, native_identity=identity, expected_quantity=before, stop_price=10.)


def test_native_pair_failure_keeps_memory_uncertain_and_rolls_back_pair(native_lifecycle, monkeypatch):
    engine, storage = native_lifecycle
    write = storage._store.insert_trade_lifecycle_events
    def fail_after_event_write(events):
        write(events)
        raise OSError('synthetic canonical event write acknowledgement lost')
    monkeypatch.setattr(storage._store, 'insert_trade_lifecycle_events', fail_after_event_write)
    entry, identity = _native_event('entry', 'ENTRY_FILL', 1, 10.5)
    with pytest.raises(OSError):
        _apply_native(engine, entry, identity, 0)
    assert engine.get_trade('NATIVE-ROOT').quantity_open == 1  # Applied memory is not rolled back/fabricated away.
    assert storage.fetch_trade_lifecycle_trades() == storage.fetch_trade_lifecycle_events() == []
    assert not engine.native_feedback_snapshot()['available'] and engine.native_feedback_snapshot()['events'] == []
    with pytest.raises(RuntimeError): engine.complete_native_feedback('FB-entry')
    with pytest.raises(RuntimeError, match='UNCERTAIN'):
        _apply_native(engine, entry, identity, 0)
    assert storage._store.commit_each_write and not storage._store.connection.in_transaction


def test_native_lost_commit_acknowledgement_does_not_grant_retry(native_lifecycle, monkeypatch):
    engine, storage = native_lifecycle
    connection = storage._store.connection
    class LostCommitAcknowledgement:
        def __getattr__(self, name): return getattr(connection, name)
        def commit(self):
            connection.commit()
            raise OSError('synthetic committed canonical pair acknowledgement lost')
    entry, identity = _native_event('entry', 'ENTRY_FILL', 1, 10.5)
    with monkeypatch.context() as patch:
        patch.setattr(storage._store, 'connection', LostCommitAcknowledgement())
        with pytest.raises(OSError): _apply_native(engine, entry, identity, 0)
    assert len(storage.fetch_trade_lifecycle_trades()) == len(storage.fetch_trade_lifecycle_events()) == 1
    assert engine.get_trade('NATIVE-ROOT').quantity_open == 1
    assert not engine.native_feedback_snapshot()['available'] and engine.native_feedback_snapshot()['events'] == []
    with pytest.raises(RuntimeError, match='UNCERTAIN'): _apply_native(engine, entry, identity, 0)
    assert len(storage.fetch_trade_lifecycle_events()) == 1


def test_native_pending_may_gain_first_security_fact_but_committed_binding_cannot_change(native_lifecycle):
    engine, _ = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 1, 10.5)
    incomplete = dict(identity); incomplete.pop('con_id')
    engine.require_native_feedback('FB-entry', incomplete)
    _apply_native(engine, entry, identity, 0)
    exit_event, child = _native_event('exit', 'STOP_EXIT', 1, 10.25, native_id=72)
    child['con_id'] = 456
    with pytest.raises(ValueError, match='OWNERSHIP_CONFLICT'):
        _apply_native(engine, exit_event, child, 1)
    assert engine.get_trade('NATIVE-ROOT').quantity_open == 1
    assert not engine.native_feedback_snapshot()['available']


def test_native_real_execution_identity_dedupes_and_rejects_price_conflict(native_lifecycle):
    engine, storage = native_lifecycle
    event, identity = _native_event('entry', 'ENTRY_FILL', 1, 10.5)
    _apply_native(engine, event, identity, 0)
    duplicate, binding = _native_event('duplicate-id', 'ENTRY_FILL', 1, 10.5)
    duplicate.execution_id = event.execution_id
    _apply_native(engine, duplicate, binding, 0)
    assert engine.get_trade('NATIVE-ROOT').quantity_open == 1
    assert len(storage.fetch_trade_lifecycle_events()) == 1 and engine.native_feedback_snapshot()['available']
    conflict, binding = _native_event('contradiction', 'ENTRY_FILL', 1, 10.75)
    conflict.execution_id = event.execution_id
    with pytest.raises(ValueError, match='EXECUTION_CONFLICT'):
        _apply_native(engine, conflict, binding, 0)
    assert engine.get_trade('NATIVE-ROOT').entry_avg_price == 10.5
    assert not engine.native_feedback_snapshot()['available']
    assert len(storage.fetch_trade_lifecycle_events()) == 1


def test_native_disabled_storage_cannot_acknowledge_feedback(native_lifecycle):
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 1, 10.5)
    storage.enabled = False
    try:
        with pytest.raises(RuntimeError, match='STORAGE_UNAVAILABLE'):
            _apply_native(engine, entry, identity, 0)
    finally:
        storage.enabled = True
    assert storage.fetch_trade_lifecycle_trades() == storage.fetch_trade_lifecycle_events() == []
    assert not engine.native_feedback_snapshot()['available']
    with pytest.raises(RuntimeError, match='UNCERTAIN'):
        _apply_native(engine, entry, identity, 0)


def test_native_snapshot_exposes_untracked_canonical_mutation_as_unavailable(native_lifecycle):
    engine, storage = native_lifecycle
    event, identity = _native_event('entry', 'ENTRY_FILL', 1, 10.5)
    _apply_native(engine, event, identity, 0)
    # The old generic observer API remains nonblocking. It is not authority to
    # alter the native producer's committed quantity/basis without its feedback.
    engine.apply_event(LifecycleEvent('legacy', 'NATIVE-ROOT', 'JPM', 'LONG',
        'ENTRY_FILL', 1, 11., '2026-10-20T13:36:00+00:00'))
    assert engine.get_trade('NATIVE-ROOT').quantity_open == 2
    snapshot = engine.native_feedback_snapshot()
    assert not snapshot['available'] and snapshot['reason'] == 'NATIVE_LIFECYCLE_SNAPSHOT_CONFLICT'
    assert snapshot['events'][0]['metadata']['quantity_after'] == 1
    assert len(storage.fetch_trade_lifecycle_events()) == 2


def test_native_reopened_root_clears_close_until_final_flat(native_lifecycle):
    engine, storage = native_lifecycle
    first, root = _native_event('entry-first', 'ENTRY_FILL', 1, 10.5)
    _apply_native(engine, first, root, 0)
    first_exit, child = _native_event('exit-first', 'STOP_EXIT', 1, 10.25,
        native_id=72, timestamp='2026-10-20T13:35:10+00:00')
    trade = _apply_native(engine, first_exit, child, 1)
    assert trade.closed_at == '2026-10-20T13:35:10+00:00' and trade.quantity_open == 0
    # This is another factual DELTA of the same accepted entry, not a request
    # or permission for a new discretionary entry/root.
    later_entry, root = _native_event('entry-remainder', 'ENTRY_FILL', 1, 10.75,
        timestamp='2026-10-20T13:35:20+00:00')
    assert _apply_native(engine, later_entry, root, 0) is trade
    assert trade.quantity_open == 1 and trade.closed_at is None
    assert trade.stop_price == 10. and trade.target_price is None
    assert trade.gross_realized_pnl == -.25 and trade.entry_avg_price == 10.75
    assert engine.native_feedback_snapshot()['available']
    final, child = _native_event('exit-final', 'STOP_EXIT', 1, 10.5,
        native_id=72, timestamp='2026-10-20T13:35:30+00:00')
    _apply_native(engine, final, child, 1)
    snapshot = engine.native_feedback_snapshot()
    assert snapshot['available'] and len(snapshot['trades']) == 1
    assert trade.status == 'CLOSED' and trade.closed_at == '2026-10-20T13:35:30+00:00'
    assert trade.quantity_closed == 2 and trade.gross_realized_pnl == -.5
    assert snapshot['events'][-1]['metadata']['terminal_timestamp'] == trade.closed_at
    assert len(storage.fetch_trade_lifecycle_trades()) == 1
    assert len(storage.fetch_trade_lifecycle_events()) == 4


def test_native_pair_rejects_independent_snapshot_drift_without_overwrite(native_lifecycle):
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 1, 10.5)
    _apply_native(engine, entry, identity, 0)
    # Deliberate corrupt/independent-writer control, not positive provenance.
    connection = storage._store.connection
    connection.execute("UPDATE trade_lifecycle_trades SET quantity_open=2 WHERE lifecycle_trade_id='NATIVE-ROOT'")
    connection.commit()
    exit_event, child = _native_event('exit', 'STOP_EXIT', 1, 10.25, native_id=72)
    with pytest.raises(RuntimeError, match='STORED_TRADE_CONFLICT'):
        _apply_native(engine, exit_event, child, 1)
    assert engine.get_trade('NATIVE-ROOT').quantity_open == 0  # Correct applied facts remain inspectable.
    assert storage.fetch_trade_lifecycle_trades()[0]['quantity_open'] == 2  # No invented reconciliation.
    assert len(storage.fetch_trade_lifecycle_events()) == 1
    snapshot = engine.native_feedback_snapshot()
    assert snapshot['uncertain'] and not snapshot['available']
    with pytest.raises(RuntimeError, match='UNCERTAIN'):
        _apply_native(engine, exit_event, child, 1)


def test_native_exit_before_earliest_entry_is_unavailable_without_application(native_lifecycle):
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 1, 10.5,
        timestamp='2026-10-20T13:35:00+00:00')
    _apply_native(engine, entry, identity, 0)
    exit_event, child = _native_event('exit-before-entry', 'STOP_EXIT', 1, 10.25,
        native_id=72, timestamp='2026-10-19T13:35:00+00:00')
    error = None
    try:
        _apply_native(engine, exit_event, child, 1)
    except ValueError as exc:
        error = exc
    trade = engine.get_trade('NATIVE-ROOT')
    observed = dict(quantity=trade.quantity_open, pnl=trade.gross_realized_pnl,
        closed_at=trade.closed_at, persisted_events=storage.fetch_trade_lifecycle_events())
    assert error is not None and str(error) == 'NATIVE_LIFECYCLE_EXIT_BEFORE_ENTRY', observed
    assert trade.quantity_open == 1 and trade.gross_realized_pnl == 0 and trade.closed_at is None
    assert len(storage.fetch_trade_lifecycle_events()) == 1
    snapshot = engine.native_feedback_snapshot()
    assert snapshot['uncertain'] and not snapshot['available']
    assert snapshot['events'][0]['event_type'] == 'ENTRY_FILL'


@pytest.mark.parametrize('case', ['equal_to_earliest', 'equal_to_latest_entry'])
def test_native_entry_time_bound_preserves_equal_exit(native_lifecycle, case):
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry-first', 'ENTRY_FILL', 1, 10.5,
        timestamp='2026-10-20T13:35:00+00:00')
    _apply_native(engine, entry, identity, 0)
    quantity_before = 1
    timestamp = entry.timestamp
    if case == 'equal_to_latest_entry':
        later_entry, identity = _native_event('entry-later', 'ENTRY_FILL', 1, 10.75,
            timestamp='2026-10-20T13:36:00+00:00')
        _apply_native(engine, later_entry, identity, 1)
        quantity_before = 2
        timestamp = later_entry.timestamp
    exit_event, child = _native_event('exit', 'STOP_EXIT', 1, 10.25,
        native_id=72, timestamp=timestamp)
    trade = _apply_native(engine, exit_event, child, quantity_before)
    snapshot = engine.native_feedback_snapshot()
    assert snapshot['available'] and trade.quantity_open == quantity_before - 1
    assert snapshot['events'][-1]['timestamp'] == timestamp
    assert len(storage.fetch_trade_lifecycle_events()) == quantity_before + 1


@pytest.mark.parametrize('direction', ['exit_before_later_entry', 'entry_before_committed_exit'])
def test_native_cross_type_chronology_cannot_apply_an_unknown_historical_basis(native_lifecycle, direction):
    engine, storage = native_lifecycle
    first, identity = _native_event('entry-first', 'ENTRY_FILL', 1, 10.75,
        timestamp='2026-10-20T13:35:00+00:00')
    _apply_native(engine, first, identity, 0)
    if direction == 'exit_before_later_entry':
        later, identity = _native_event('entry-later', 'ENTRY_FILL', 1, 10.5,
            timestamp='2026-10-20T13:36:00+00:00')
        _apply_native(engine, later, identity, 1)
        event, binding = _native_event('cross-exit', 'STOP_EXIT', 1, 10.6,
            native_id=72, timestamp='2026-10-20T13:35:30+00:00')
        quantity_before = 2
    else:
        prior_exit, child = _native_event('exit-first', 'STOP_EXIT', 1, 10.6,
            native_id=72, timestamp='2026-10-20T13:35:30+00:00')
        _apply_native(engine, prior_exit, child, 1)
        event, binding = _native_event('cross-entry', 'ENTRY_FILL', 1, 10.5,
            timestamp='2026-10-20T13:35:20+00:00')
        quantity_before = 0
    trade = engine.get_trade('NATIVE-ROOT')
    prior = (trade.quantity_open, trade.gross_realized_pnl, trade.entry_avg_price, trade.closed_at)
    error = None
    try:
        _apply_native(engine, event, binding, quantity_before)
    except ValueError as exc:
        error = exc
    observed = dict(prior=prior, quantity=trade.quantity_open, pnl=trade.gross_realized_pnl,
        entry_avg_price=trade.entry_avg_price, closed_at=trade.closed_at,
        persisted_events=storage.fetch_trade_lifecycle_events())
    assert error is not None and str(error) == 'NATIVE_LIFECYCLE_CROSS_FILL_CHRONOLOGY_UNAVAILABLE', observed
    assert (trade.quantity_open, trade.gross_realized_pnl, trade.entry_avg_price, trade.closed_at) == prior
    assert event.event_id not in engine._event_ids_seen
    assert len(storage.fetch_trade_lifecycle_events()) == 2
    snapshot = engine.native_feedback_snapshot()
    assert snapshot['uncertain'] and not snapshot['available']


def test_native_out_of_order_entries_before_any_exit_keep_weighted_basis(native_lifecycle):
    engine, storage = native_lifecycle
    later, identity = _native_event('entry-later', 'ENTRY_FILL', 1, 10.75,
        timestamp='2026-10-20T13:36:00+00:00')
    _apply_native(engine, later, identity, 0)
    earlier, identity = _native_event('entry-earlier', 'ENTRY_FILL', 1, 10.5,
        timestamp='2026-10-20T13:35:00+00:00')
    trade = _apply_native(engine, earlier, identity, 1)
    assert trade.quantity_open == 2 and trade.entry_avg_price == 10.625 and trade.gross_realized_pnl == 0
    assert trade.opened_at == earlier.timestamp and trade.stop_price == 10. and trade.target_price is None
    assert engine.native_feedback_snapshot()['available']
    assert len(storage.fetch_trade_lifecycle_events()) == 2


def test_native_entry_equal_to_prior_exit_retains_existing_coarse_time_order(native_lifecycle):
    engine, _ = native_lifecycle
    first, identity = _native_event('entry-first', 'ENTRY_FILL', 1, 10.75,
        timestamp='2026-10-20T13:35:00+00:00')
    _apply_native(engine, first, identity, 0)
    exit_event, child = _native_event('exit-first', 'STOP_EXIT', 1, 10.6,
        native_id=72, timestamp='2026-10-20T13:35:30+00:00')
    trade = _apply_native(engine, exit_event, child, 1)
    prior_pnl = trade.gross_realized_pnl
    entry, identity = _native_event('entry-remainder', 'ENTRY_FILL', 1, 10.5,
        timestamp=exit_event.timestamp)
    _apply_native(engine, entry, identity, 0)
    # Equal broker timestamps preserve the established arrival/accounting order;
    # this control supplies no finer physical-order or broker certification.
    assert trade.quantity_open == 1 and trade.entry_avg_price == 10.5
    assert trade.gross_realized_pnl == prior_pnl and trade.closed_at is None
    assert trade.stop_price == 10. and trade.target_price is None
    assert engine.native_feedback_snapshot()['available']


def _native_valuation(engine, **changes):
    requirement = engine.native_valuation_requirements()[0]
    return NativeValuationObservation(**{key: value for key, value in requirement.items()
        if key != 'native_order_id'}, price=10.25, market_timestamp='2026-10-20T13:35:10+00:00',
        acquisition_completed_at='2026-10-20T13:35:11+00:00', request_id=101,
        source='IBKR', timestamp_kind='LAST_TRADE', market_data_type='LIVE', completed=True,
        **changes)


VALUATION_NOW = datetime(2026, 10, 20, 13, 35, 12, tzinfo=timezone.utc)


def test_native_valuation_commits_audit_pair_without_creating_a_fill(native_lifecycle):
    engine, storage = native_lifecycle
    event, identity = _native_event('entry', 'ENTRY_FILL', 2, 10.5)
    original = _apply_native(engine, event, identity, 0)
    before = engine._trade_snapshot_payload(original)
    observed = _native_valuation(engine)
    marked = engine.apply_native_valuation(observed, now=VALUATION_NOW, max_age_seconds=15, source_client=engine._test_native_valuation_client)
    assert original.last_mark_price is None  # Copy-on-write publication.
    assert engine.get_trade('NATIVE-ROOT') is marked and marked.last_mark_price == 10.25
    assert marked.unrealized_pnl == -.5
    after = engine._trade_snapshot_payload(marked)
    assert {key: value for key, value in before.items() if key not in {'last_mark_price', 'unrealized_pnl', 'updated_at'}} == {
        key: value for key, value in after.items() if key not in {'last_mark_price', 'unrealized_pnl', 'updated_at'}}
    assert marked.source_execution_ids == {'EXEC-entry'}
    assert marked.stop_price == 10 and marked.target_price is None
    assert len(engine.native_feedback_snapshot()['events']) == 1
    persisted = storage.fetch_trade_lifecycle_events()
    assert len(persisted) == 2 and {row['event_type'] for row in persisted} == {'ENTRY_FILL', 'NATIVE_MARK'}
    mark = next(row for row in persisted if row['event_type'] == 'NATIVE_MARK')
    assert mark['quantity'] == 0 and mark['execution_id'] is None
    assert storage.fetch_trade_lifecycle_trades()[0]['unrealized_pnl'] == -.5
    snapshot = engine.native_valuation_snapshot(now=VALUATION_NOW, max_age_seconds=15)
    assert snapshot['available'] and snapshot['unrealized_pnl'] == -.5
    assert snapshot['marks'][0]['basis_event_ids'] == ('entry',)
    assert engine.apply_native_valuation(observed, now=VALUATION_NOW, max_age_seconds=15, source_client=engine._test_native_valuation_client) is marked
    assert len(storage.fetch_trade_lifecycle_events()) == 2


@pytest.mark.parametrize('changes', [
    {'root_order_id': 'OTHER'}, {'account': 'OTHER'}, {'strategy': 'OTHER'}, {'symbol': 'AAPL'},
    {'side': 'SHORT'}, {'con_id': 124}, {'con_id': True}, {'client_id': 72},
    {'connection_epoch': 4}, {'quantity': 1}, {'quantity': True}, {'entry_avg_price': 11.},
    {'basis_event_ids': ('missing',)}, {'basis_event_ids': ['entry']},
    {'last_fill_timestamp': '2026-10-20T13:34:59+00:00'}, {'price': True},
    {'price': float('nan')}, {'price': 0}, {'request_id': True}, {'request_id': 0},
    {'source': 'SIM'}, {'timestamp_kind': 'CLOSE'}, {'market_data_type': 'DELAYED'},
    {'completed': False}, {'completed': 1}, {'quality_flags': ('ERROR',)}, {'quality_flags': []},
    {'market_timestamp': '2026-10-20T13:34:59+00:00'},
    {'market_timestamp': '2026-10-20T13:35:13+00:00'},
    {'market_timestamp': '2026-10-20T13:35:10'},
    {'acquisition_completed_at': '2026-10-20T13:35:09+00:00'},
    {'acquisition_completed_at': '2026-10-20T13:35:13+00:00'},
])
def test_native_valuation_rejects_unbound_or_incomplete_quote_without_financial_poison(native_lifecycle, changes):
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 2, 10.5)
    trade = _apply_native(engine, entry, identity, 0)
    observation = replace(_native_valuation(engine), **changes)
    with pytest.raises(ValueError):
        engine.apply_native_valuation(observation, now=VALUATION_NOW, max_age_seconds=15, source_client=engine._test_native_valuation_client)
    assert trade.last_mark_price is None and trade.unrealized_pnl == 0
    assert len(storage.fetch_trade_lifecycle_events()) == 1
    assert engine.native_feedback_snapshot()['available']
    assert not engine.native_valuation_snapshot(now=VALUATION_NOW, max_age_seconds=15)['available']
    assert not engine._native_valuation_uncertain


def test_native_valuation_freshness_inclusive_boundary_and_refresh_revocation(native_lifecycle):
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 1, 10.5)
    _apply_native(engine, entry, identity, 0)
    observation = _native_valuation(engine)
    boundary = VALUATION_NOW + timedelta(seconds=13)
    engine.apply_native_valuation(observation, now=boundary, max_age_seconds=15, source_client=engine._test_native_valuation_client)
    assert engine.native_valuation_snapshot(now=boundary, max_age_seconds=15)['available']
    assert not engine.native_valuation_snapshot(now=boundary + timedelta(microseconds=1), max_age_seconds=15)['available']
    assert not engine.native_valuation_snapshot(now=VALUATION_NOW - timedelta(seconds=3), max_age_seconds=15)['available']
    engine.mark_native_valuation_unavailable('NATIVE-ROOT', 'CURRENT_QUOTE_MISSING')
    snapshot = engine.native_valuation_snapshot(now=VALUATION_NOW, max_age_seconds=15)
    assert not snapshot['available'] and snapshot['reason'] == 'CURRENT_QUOTE_MISSING'
    assert engine.native_feedback_snapshot()['available'] and not engine.native_feedback_snapshot()['native_unrealized_marks_present']
    # A completed fresh acquisition can supersede unavailable facts, not an
    # unknown persistence attempt. Identical already-committed facts dedupe.
    engine.apply_native_valuation(observation, now=VALUATION_NOW, max_age_seconds=15, source_client=engine._test_native_valuation_client)
    assert engine.native_valuation_snapshot(now=VALUATION_NOW, max_age_seconds=15)['available']
    assert len(storage.fetch_trade_lifecycle_events()) == 2


@pytest.mark.parametrize('failure', ['before_write', 'lost_ack'])
def test_native_valuation_write_uncertainty_preserves_factual_fill_and_never_retries(native_lifecycle, monkeypatch, failure):
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 2, 10.5)
    original = _apply_native(engine, entry, identity, 0)
    observation = _native_valuation(engine)
    persist = storage.persist_native_lifecycle_feedback
    calls = []
    def interrupted(*args, **kwargs):
        calls.append(args[1]['event_type'])
        if failure == 'lost_ack':
            persist(*args, **kwargs)
        raise OSError('MARK_WRITE_UNKNOWN')
    monkeypatch.setattr(storage, 'persist_native_lifecycle_feedback', interrupted)
    with pytest.raises(OSError, match='MARK_WRITE_UNKNOWN'):
        engine.apply_native_valuation(observation, now=VALUATION_NOW, max_age_seconds=15, source_client=engine._test_native_valuation_client)
    assert engine.get_trade('NATIVE-ROOT') is original and original.last_mark_price is None
    assert engine.native_feedback_snapshot()['available']
    assert not engine.native_valuation_snapshot(now=VALUATION_NOW, max_age_seconds=15)['available']
    persisted = storage.fetch_trade_lifecycle_trades()[0]
    assert persisted['last_mark_price'] == (10.25 if failure == 'lost_ack' else None)
    monkeypatch.setattr(storage, 'persist_native_lifecycle_feedback', persist)
    with pytest.raises(RuntimeError, match='UNCERTAIN'):
        engine.apply_native_valuation(observation, now=VALUATION_NOW, max_age_seconds=15, source_client=engine._test_native_valuation_client)
    assert calls == ['NATIVE_MARK']
    exit_event, child = _native_event('partial', 'STOP_EXIT', 1, 10.25,
        native_id=72, timestamp='2026-10-20T13:35:20+00:00')
    trade = _apply_native(engine, exit_event, child, 2)
    assert trade.quantity_open == 1 and trade.gross_realized_pnl == -.25
    assert trade.last_mark_price is None and trade.unrealized_pnl == 0
    assert engine.native_feedback_snapshot()['available']
    snapshot = engine.native_valuation_snapshot(now=VALUATION_NOW + timedelta(seconds=10), max_age_seconds=15)
    assert not snapshot['available'] and snapshot['uncertain'] == {'NATIVE-ROOT': 'MARK_WRITE_UNKNOWN'}
    final, child = _native_event('final', 'STOP_EXIT', 1, 10.25,
        native_id=72, timestamp='2026-10-20T13:35:21+00:00')
    _apply_native(engine, final, child, 1)
    assert engine.native_feedback_snapshot()['available'] and trade.quantity_open == 0
    snapshot = engine.native_valuation_snapshot(now=VALUATION_NOW + timedelta(seconds=10), max_age_seconds=15)
    assert not snapshot['available'] and snapshot['uncertain']  # Flat is not recovery clearing.
    assert [row['event_type'] for row in engine.native_feedback_snapshot()['events']] == ['ENTRY_FILL', 'STOP_EXIT', 'STOP_EXIT']


def test_native_valuation_superseded_by_actual_partial_fill_requires_new_basis(native_lifecycle):
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 2, 10.5)
    _apply_native(engine, entry, identity, 0)
    observation = _native_valuation(engine)
    engine.apply_native_valuation(observation, now=VALUATION_NOW, max_age_seconds=15, source_client=engine._test_native_valuation_client)
    exit_event, child = _native_event('partial', 'PARTIAL_EXIT', 1, 10.25,
        native_id=72, timestamp='2026-10-20T13:35:20+00:00')
    trade = _apply_native(engine, exit_event, child, 2)
    assert trade.quantity_open == 1 and trade.last_mark_price is None and trade.unrealized_pnl == 0
    assert not engine.native_valuation_snapshot(now=VALUATION_NOW + timedelta(seconds=10), max_age_seconds=15)['available']
    with pytest.raises(ValueError, match='EVIDENCE_INVALID'):
        engine.apply_native_valuation(observation, now=VALUATION_NOW + timedelta(seconds=10), max_age_seconds=15, source_client=engine._test_native_valuation_client)
    requirement = engine.native_valuation_requirements()[0]
    assert requirement['basis_event_ids'] == ('entry', 'partial')
    assert requirement['last_fill_timestamp'] == '2026-10-20T13:35:20+00:00'
    current = replace(observation, quantity=1, basis_event_ids=requirement['basis_event_ids'],
        last_fill_timestamp=requirement['last_fill_timestamp'], market_timestamp='2026-10-20T13:35:21+00:00',
        acquisition_completed_at='2026-10-20T13:35:22+00:00', request_id=102)
    engine.apply_native_valuation(current, now=VALUATION_NOW + timedelta(seconds=10), max_age_seconds=15, source_client=engine._test_native_valuation_client)
    snapshot = engine.native_valuation_snapshot(now=VALUATION_NOW + timedelta(seconds=10), max_age_seconds=15)
    assert snapshot['available'] and snapshot['unrealized_pnl'] == -.25
    assert engine.native_feedback_snapshot()['events'][-1]['metadata']['quantity_after'] == 1


def test_native_valuation_cold_rows_and_legacy_handmark_are_not_scoped_authority(native_lifecycle):
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 1, 10.5)
    _apply_native(engine, entry, identity, 0)
    engine.apply_mark_price(trade_id='NATIVE-ROOT', price=10.25)
    assert engine.native_feedback_snapshot()['available']
    assert not engine.native_feedback_snapshot()['native_unrealized_marks_present']
    assert not engine.native_valuation_snapshot(now=VALUATION_NOW, max_age_seconds=15)['available']
    cold = TradeLifecycleEngine(storage)
    cold.recover_open_state()
    assert cold.native_valuation_requirements() == [] and cold._native_valuations == {}
    assert cold.get_trade('NATIVE-ROOT').last_mark_price == 10.25  # Inspection only.
    with pytest.raises(ValueError, match='COMMITTED_OPEN_ROOT_REQUIRED'):
        cold.apply_native_valuation(_native_valuation(engine), now=VALUATION_NOW, max_age_seconds=15, source_client=engine._test_native_valuation_client)


@pytest.mark.parametrize('change', ['same_scope_replacement', 'epoch_changed', 'disconnected', 'stopped'])
def test_native_valuation_rechecks_actual_client_object_scope_at_admission(native_lifecycle, change):
    from threading import Event
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 1, 10.5)
    _apply_native(engine, entry, identity, 0)
    client = engine._test_native_valuation_client
    engine.apply_native_valuation(_native_valuation(engine), now=VALUATION_NOW, max_age_seconds=15, source_client=client)
    expected_client = client
    if change == 'same_scope_replacement':
        expected_client = SimpleNamespace(client_id=71, _position_connection_epoch=3, isConnected=lambda: True)
    elif change == 'epoch_changed':
        client._position_connection_epoch = 4
    elif change == 'disconnected':
        client.isConnected = lambda: False
    else:
        client._stop_event = Event()
        client._stop_event.set()
    snapshot = engine.native_valuation_snapshot(now=VALUATION_NOW, max_age_seconds=15,
        expected_source_client=expected_client)
    assert not snapshot['available'] and snapshot['reason'] == 'NATIVE_VALUATION_SOURCE_SCOPE_CHANGED'
    assert engine.native_feedback_snapshot()['available']
    assert len(storage.fetch_trade_lifecycle_events()) == 2


@pytest.mark.parametrize('interruption', ['factual_fill', 'scope_change'])
def test_native_valuation_postwrite_change_cannot_overwrite_current_financial_facts(native_lifecycle, monkeypatch, interruption):
    engine, storage = native_lifecycle
    entry, identity = _native_event('entry', 'ENTRY_FILL', 2, 10.5)
    _apply_native(engine, entry, identity, 0)
    observation = _native_valuation(engine)
    client = engine._test_native_valuation_client
    persist = storage.persist_native_lifecycle_feedback
    def changed_after_commit(*args, **kwargs):
        receipt = persist(*args, **kwargs)
        if args[1]['event_type'] == 'NATIVE_MARK':
            if interruption == 'scope_change':
                client._position_connection_epoch += 1
            else:
                partial, child = _native_event('raced-partial', 'STOP_EXIT', 1, 10.25,
                    native_id=72, timestamp='2026-10-20T13:35:20+00:00')
                _apply_native(engine, partial, child, 2)
        return receipt
    monkeypatch.setattr(storage, 'persist_native_lifecycle_feedback', changed_after_commit)
    error = 'BASIS_CHANGED_DURING_PERSISTENCE' if interruption == 'factual_fill' else 'SOURCE_CHANGED_DURING_PERSISTENCE'
    with pytest.raises(RuntimeError, match=error):
        engine.apply_native_valuation(observation, now=VALUATION_NOW, max_age_seconds=15, source_client=client)
    current = engine.get_trade('NATIVE-ROOT')
    persisted = storage.fetch_trade_lifecycle_trades()[0]
    assert current.last_mark_price is None  # No post-write stale publication.
    assert current.quantity_open == (1 if interruption == 'factual_fill' else 2)
    assert current.gross_realized_pnl == (-.25 if interruption == 'factual_fill' else 0)
    assert persisted['quantity_open'] == current.quantity_open
    assert persisted['gross_realized_pnl'] == current.gross_realized_pnl
    assert engine.native_feedback_snapshot()['available']
    assert engine.native_valuation_snapshot(now=VALUATION_NOW, max_age_seconds=15)['uncertain']
    # The committed mark's audit remains; financial fill IDs never include it.
    assert any(row['event_type'] == 'NATIVE_MARK' for row in storage.fetch_trade_lifecycle_events())
    assert all(row['event_type'] != 'NATIVE_MARK' for row in engine.native_feedback_snapshot()['events'])
