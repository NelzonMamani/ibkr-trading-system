from pathlib import Path
from types import SimpleNamespace

from src.config.config_resolver import set_config_overrides
from src.core_engine import orchestrator
from src.core_engine.state import SessionState


def test_empty_scan_injects_fallback_and_writes_summary(monkeypatch, capsys) -> None:
    set_config_overrides(
        {
            "RUN_MODE": "SIM",
            "RUN_MODE_EFFECTIVE": "SIM",
            "FORCE_DEBUG_TRADES": False,
            "EXECUTION_ENABLED": False,
        }
    )
    try:
        monkeypatch.setattr(
            orchestrator,
            "run_scanner_cycle",
            lambda **_: {
                "topn_count": 0,
                "survivors_count": 0,
                "watchlist_k_symbols": [],
                "focus_m_symbols": [],
                "watchlist_k": [],
                "focus_m": [],
                "candidates": [],
                "drop_reason_summary": {},
                "data_quality_by_symbol": {},
            },
        )

        fake_summary = SimpleNamespace(
            best_long_setup=None,
            best_short_setup=None,
            combined_rationale_text="none",
            all_results=[],
        )
        monkeypatch.setattr(orchestrator.PatternEvaluator, "evaluate", lambda self, _: fake_summary)
        monkeypatch.setattr(orchestrator, "build_trade_intents", lambda *_args, **_kwargs: [])
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

        orchestrator.run_cycle(cycle_id=77, mode_value="SIM", forced_session_state=SessionState.REG)
        output = capsys.readouterr().out
    finally:
        set_config_overrides(None)

    assert "[SCANNER][FALLBACK_INJECTED]" in output
    assert "[PIPELINE][SUMMARY]" in output
    assert "symbols_processed=" in output
    assert "setups_detected=" in output
    assert "triggers_fired=" in output

    report_path = Path("data/audit/pipeline_determinism_report.json")
    assert report_path.exists()
    payload = report_path.read_text(encoding="utf-8")
    assert '"cycle_id": 77' in payload


def test_force_debug_trades_guarantees_intent(monkeypatch) -> None:
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
                "watchlist_k": [{"symbol": "AAPL"}],
                "focus_m": [{"symbol": "AAPL"}],
                "candidates": [{"symbol": "AAPL"}],
                "drop_reason_summary": {},
                "data_quality_by_symbol": {"AAPL": []},
            },
        )
        fake_summary = SimpleNamespace(
            best_long_setup=None,
            best_short_setup=None,
            combined_rationale_text="none",
            all_results=[],
        )
        monkeypatch.setattr(orchestrator.PatternEvaluator, "evaluate", lambda self, _: fake_summary)
        monkeypatch.setattr(orchestrator, "build_trade_intents", lambda *_args, **_kwargs: [])
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

        summary = orchestrator.run_cycle(cycle_id=99, mode_value="SIM", forced_session_state=SessionState.REG)
    finally:
        set_config_overrides(None)

    assert len(summary.intents) >= 1
    assert any(intent.intent_id.startswith("forced-debug-") for intent in summary.intents)
