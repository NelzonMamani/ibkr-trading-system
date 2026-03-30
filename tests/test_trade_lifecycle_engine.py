from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.core.engines.position_management_engine import ManagedPosition
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
