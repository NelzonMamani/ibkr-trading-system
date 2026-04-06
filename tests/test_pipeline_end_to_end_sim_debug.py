from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.core_engine import orchestrator
from src.core_engine.state import SessionState


def test_sim_debug_forced_trade_runs_full_pipeline(monkeypatch, capsys) -> None:
    set_config_overrides(
        {
            "RUN_MODE": "SIM",
            "RUN_MODE_EFFECTIVE": "SIM",
            "FORCE_DEBUG_TRADES": True,
            "EXECUTION_ENABLED": False,
        }
    )
    try:
        monkeypatch.setattr(
            orchestrator,
            "run_scanner_cycle",
            lambda **_: {
                "topn_count": 1,
                "survivors_count": 1,
                "watchlist_k_symbols": ["AAPL"],
                "focus_m_symbols": ["AAPL"],
                "watchlist_k": [{"symbol": "AAPL", "last_price": 20.0, "snapshot_last_price": 20.0, "snapshot_bid": 19.95, "snapshot_ask": 20.05}],
                "focus_m": [{"symbol": "AAPL", "last_price": 20.0, "snapshot_last_price": 20.0, "snapshot_bid": 19.95, "snapshot_ask": 20.05}],
                "drop_reason_summary": {},
                "data_quality_by_symbol": {"AAPL": []},
            },
        )

        fake_setup = SimpleNamespace(pattern_name="TEST_SETUP", confidence=0.91)
        fake_summary = SimpleNamespace(
            best_long_setup=fake_setup,
            best_short_setup=None,
            combined_rationale_text="deterministic setup",
            all_results=[],
        )
        monkeypatch.setattr(
            orchestrator.PatternEvaluator,
            "evaluate",
            lambda self, _: fake_summary,
        )
        monkeypatch.setattr(orchestrator, "build_trade_intents", lambda *_: [])
        monkeypatch.setattr(
            orchestrator,
            "build_execution_intent",
            lambda **_: SimpleNamespace(
                strategy_name="ross_momentum",
                mode="SIM",
                session_phase="MORNING",
                trade_enabled=False,
                scan_only=True,
                enforcement="TEST",
            ),
        )

        summary = orchestrator.run_cycle(
            cycle_id=1,
            mode_value="SIM",
            forced_session_state=SessionState.REG,
        )
        output = capsys.readouterr().out
    finally:
        set_config_overrides(None)

    assert len(summary.intents) > 0
    assert any(
        decision.decision in {"ALLOW", "ALLOW_WITH_CONSTRAINTS"} and decision.approved_quantity > 0
        for decision in summary.risk_decisions
    )
    assert len(summary.execution_events) == 1
    assert summary.execution_events[0].action == "BLOCKED"
    assert summary.execution_events[0].detail == "reason=SCAN_ONLY_OR_DISABLED"
    assert "[DEBUG][FORCED_PATH] intent_created" in output
    assert "[DEBUG][FORCED_PATH] passed_risk" in output
    assert "[DEBUG][FORCED_PATH] selected_by_arbitrator" in output
    assert "[EXECUTION][SKIPPED] symbol=AAPL reason=SCAN_ONLY_OR_DISABLED" in output
