from __future__ import annotations

from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.core.orchestrator import CoreOrchestrator
from src.models.data_models import TradeIntent


def _candidate(symbol: str, score: float) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        last_price=10.0 + score,
        gap_pct=score,
        pct_change=score,
        rvol=2.5,
        volume=1_500_000,
        dollar_volume=15_000_000.0,
        rank_score=score,
        session_label="PRE",
        float_shares=12_000_000,
    )


def test_live_pipeline_bridge_logs_watchlist_focus_strategy_and_summary(monkeypatch, capsys):
    set_config_overrides(
        {
            "RUN_MODE": "READ_ONLY",
            "EXECUTION_ENABLED": False,
            "ROSS_MOMENTUM_STRATEGY_ENABLED": True,
            "SELECTED_STRATEGY": "ross_momentum",
            "SESSION_PHASE_OVERRIDE": "PREMARKET",
            "TOPN_REFRESH_SECONDS": 0,
            "WATCHLIST_REFRESH_SECONDS": 0,
            "FOCUS_REFRESH_SECONDS": 0,
            "TOPN_MAX_SYMBOLS_PER_STRATEGY": 15,
            "WATCHLIST_MAX_SYMBOLS_PER_STRATEGY": 15,
            "FOCUS_MAX_SYMBOLS_PER_STRATEGY": 5,
        }
    )

    watchlist = [_candidate("AAPL", 10.0), _candidate("MSFT", 9.0)]
    focus = [_candidate("AAPL", 10.0)]

    def _scanner_cycle(**kwargs):
        return {
            "candidate_metrics": watchlist,
            "watchlist_k": watchlist,
            "watchlist_k_symbols": [row.symbol for row in watchlist],
            "focus_m": focus,
            "focus_m_symbols": [row.symbol for row in focus],
            "candidates": focus,
            "universe_top_n": [{"symbol": row.symbol} for row in watchlist],
        }

    monkeypatch.setattr("src.core.orchestrator.run_scanner_cycle", _scanner_cycle)

    orchestrator = CoreOrchestrator()
    orchestrator._refresh_manual_focus_if_due = lambda *_args, **_kwargs: []
    orchestrator._resolve_manual_focus_candidates = lambda **kwargs: ([], [])
    orchestrator.market_data_snapshot_manager = SimpleNamespace(batch_snapshots=lambda symbols: ({}, []))
    orchestrator.strategy_runner.receive_watchlist_snapshot = lambda **kwargs: None
    orchestrator.strategy_runner.process = lambda **kwargs: [
        TradeIntent(
            symbol="AAPL",
            direction="LONG",
            strategy_name="ross_momentum",
            confidence=0.9,
            rationale="bridge test",
            pattern_name="ROSS_TEST_SETUP",
        )
    ]

    try:
        assert orchestrator.run_once() is True
    finally:
        set_config_overrides({})

    output = capsys.readouterr().out
    assert "[WATCHLIST] size=2 symbols=['AAPL', 'MSFT']" in output
    assert "[FOCUS] size=1 symbols=['AAPL']" in output
    assert "[STRATEGY] runner=ross_momentum symbol=AAPL stage=evaluate" in output
    assert "[INTENT] symbol=AAPL side=LONG" in output
    assert "[DECISION] symbol=AAPL verdict=emit_intent setup=ROSS_TEST_SETUP executable=false" in output
    assert "[PIPELINE] scanner_kept=2 watchlist=2 focus=1 evaluated=1 intents=1" in output
